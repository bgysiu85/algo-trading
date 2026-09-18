#!/usr/bin/env python3
"""Poll the TradingView screen and keep watchlist.txt current.

    python -m common.tv_feed                     # 10s poll, pre-market only
    python -m common.tv_feed --once --dry-run    # one call, print, write nothing
    python -m common.tv_feed --interval 30

WHAT THIS IS FOR
----------------
common/tv_screener.py pins the screen. This runs it on a loop and writes the
result to the file brokers/ibkr/trader.py reads. The screener MCP tool cannot
be called from Python -- it is a Claude-facing tool -- so this posts the same
query to TradingView's own scanner endpoint, which is where that
{"left", "operation", "right"} syntax comes from in the first place.

RANKING, NOT MEMBERSHIP (Ben, 2026-09-05: "do not remove but deprioritise")
--------------------------------------------------------------------------
A symbol that drops out of the screen is NOT deleted. Dropping mid-session is
how you orphan a position you are holding, and pre-market screens flicker --
a name can fail `rel vol >= 5` for one poll and pass the next. So the file is
ordered rather than filtered, in three tiers:

    HOT   passing the screen right now, and inside MCL's $2-20 band
    WARM  passing the screen but OUTSIDE the band -- the screen has no upper
          price bound, so it surfaces names the strategy will refuse at entry
          (brokers/ibkr/trader.py logs SKIPPED_PRICE_BAND). They stay visible
          but never displace a tradeable name.
    COLD  passed earlier in the session, not passing now, most recent first

Order matters downstream: the trader walks the file in order, and with
MAX_CONCURRENT_POSITIONS = 2 the earlier symbols are the ones that get to
open a position.

WHY THERE IS A CAP ON THE FILE
------------------------------
Each watchlist symbol costs an IB contract qualification and a streaming market
data line, and both are scarce -- qualification is paced (~60 requests / 10 min
account-wide, and IB signals throttling by returning EMPTY LISTS rather than
errors), and a typical account carries ~100 data lines. An unbounded file that
only ever grows would quietly exhaust both, so COLD entries are trimmed from
the back.

POLL INTERVAL
-------------
10s by default, as asked. Worth knowing what that does and does not buy: this
endpoint is a request/response snapshot, not a stream, and TradingView's own
figures do not necessarily update every 10 seconds -- polling faster than the
data changes only spends requests. A pre-market session is 5.5 hours, so 10s is
~1,980 calls; if TradingView starts throttling, the loop backs off rather than
hammering (see BACKOFF below) and the interval is the first thing to raise.

ONE WRITER ONLY
---------------
brokers/ibkr/scanner.py writes the same file from IB's scanner. Run one or the
other, never both, or they will overwrite each other's results every few
seconds.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import notify, session_lock
from common.tv_screener import (CHANGE_COLUMN, COLUMNS, FILTERS, MARKET,
                                PRICE_MAX, PRICE_MIN, VOLUME_COLUMN,
                                check_response, failing_clauses)

LOG = logging.getLogger("tv_feed")
ET = ZoneInfo("America/New_York")

ENDPOINT = f"https://scanner.tradingview.com/{MARKET}/scan"
# THE SAME FILE THE TRADER READS. It was Path("watchlist.txt") -- the repo
# ROOT -- while brokers/ibkr/trader.py and brokers/ibkr/scanner.py both default
# to var/watchlist.txt. Nothing failed: this feed would log "watchlist -> 7
# symbols" while the trader logged "watchlist is empty -- watching nothing",
# both correct about different files, and a whole session would be watched by
# nobody. tests/common/test_tv_feed.py pins the three together.
WATCHLIST = Path("var/watchlist.txt")

SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)

DEFAULT_INTERVAL = 10.0
MAX_SYMBOLS = 40          # IB data lines and qualification pacing, see above
REQUEST_TIMEOUT = 8.0

# Backoff. Consecutive failures double the wait, to a ceiling, and one success
# resets it. Without this a TradingView outage becomes 6 requests a minute of
# useless traffic for five hours, which is how an IP gets blocked.
BACKOFF_START = 15.0
BACKOFF_MAX = 300.0

# --- the login, and the column that says whether it worked --------------------
#
# The scanner endpoint is posted to with no cookie, so Ben's TradingView premium
# entitlement has never reached it. Whether that means the rows are DELAYED is
# answered by TradingView's own `update_mode` column, and until the probe has
# run neither answer is assumed here: this module gains the ability to send the
# cookie and to READ the column, and changes nothing when the environment is
# empty.
#
# BOTH COOKIES OR NEITHER. TradingView signs the session. `sessionid` alone is
# accepted and served ANONYMOUSLY -- so a half-set environment would look
# logged in, behave delayed, and produce no error anywhere. Never a CLI flag:
# the rule DATABENTO_API_KEY carries, because a flag puts the secret in shell
# history.
COOKIE_ENV = "TV_SESSIONID"
SIGN_ENV = "TV_SESSIONID_SIGN"
MODE_COLUMN = "update_mode"


def cookie_header(sid: str | None, sign: str | None) -> str | None:
    """The Cookie header, or None when the pair is incomplete -- never a
    partial header, which would be an anonymous request wearing a login."""
    if not sid or not sign:
        return None
    return f"sessionid={sid}; sessionid_sign={sign}"


def session_cookie() -> str | None:
    """The cookie from the environment, with the half-set case named loudly."""
    sid, sign = os.environ.get(COOKIE_ENV), os.environ.get(SIGN_ENV)
    header = cookie_header(sid, sign)
    if header is None and (sid or sign):
        LOG.error("only ONE of %s / %s is set. TradingView signs the session, "
                  "so a half-set pair is served ANONYMOUSLY -- the feed would "
                  "look logged in and read delayed data. Sending NO cookie.",
                  COOKIE_ENV, SIGN_ENV)
    return header


def mode_verdict(value) -> str:
    """What `update_mode` says, in one word. "streaming" is real time; anything
    containing "delayed" is not, and TradingView spells the delay into the
    value (`delayed_streaming_900` is fifteen minutes), so the raw string is
    printed beside the verdict rather than reduced to a boolean."""
    if value is None:
        return "UNKNOWN"
    v = str(value).lower()
    if "delayed" in v:
        return "DELAYED"
    if "streaming" in v or v in ("realtime", "real_time"):
        return "STREAMING"
    return "UNRECOGNISED"


def tv_payload(limit: int = MAX_SYMBOLS) -> dict:
    """Translate the screener definition into TradingView's own wire format.

    Deliberately built FROM common/tv_screener.FILTERS rather than restated, so
    a change to the screen cannot silently fail to reach the live feed.
    """
    return {
        "filter": [dict(f) for f in FILTERS],
        "options": {"lang": "en"},
        "markets": [MARKET],
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": list(COLUMNS),
        # Ranked on the SCREEN's column: the trader walks the file in order,
        # and with MAX_CONCURRENT_POSITIONS = 2 the top of the file is what
        # gets to open a position. Sorting on a different column than the one
        # filtered would rank by a number the screen no longer uses.
        "sort": {"sortBy": CHANGE_COLUMN, "sortOrder": "desc"},
        "range": [0, limit],
    }


def parse(body: dict) -> list[dict]:
    """TradingView returns {"data": [{"s": "NASDAQ:AOUT", "d": [...]}, ...]}
    with `d` positional against the columns requested."""
    rows = []
    for item in body.get("data") or []:
        sym = item.get("s", "")
        vals = item.get("d") or []
        row = dict(zip(COLUMNS, vals))
        row["symbol"] = sym
        row["ticker"] = sym.split(":")[-1]
        rows.append(row)
    return rows


def fetch(limit: int = MAX_SYMBOLS, cookie: str | None = None) -> list[dict]:
    body = _scan(tv_payload(limit), cookie)
    # THE RULE tv_screener.py states and this feed was not following: the
    # server accepts a clause it cannot apply, returns a plausible result set,
    # and lists the dropped clause under ignored_filters. A feed that does not
    # read that key writes an unfiltered watchlist and reports success. Logged
    # as a warning on every poll it happens, so it cannot be missed once.
    ignored = check_response(body)
    if ignored:
        LOG.warning("TradingView IGNORED filter(s) %s -- the rows below are NOT "
                    "screened on them. Check the column name.", ignored)
    return parse(body)


def _scan(payload: dict, cookie: str | None = None) -> dict:
    """One POST to the scanner endpoint. Split out of fetch() so the drop
    lookup shares exactly the request the feed itself makes, and so a test can
    replace the network in one place instead of patching urllib.

    `cookie` is a complete Cookie header and is NEVER logged.
    """
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
        return json.load(r)


def tickers_payload(symbols: list[str]) -> dict:
    """The same columns, for named symbols, with NO filter clauses.

    This is the only way to say WHY a name dropped. The screen is applied
    server-side, so a name that stops passing returns no row at all, and the
    poll that dropped it carries no information about it beyond its absence.
    Asking for the symbol explicitly and unfiltered gets its current values
    back, and tv_screener.failing_clauses() then names the clause it now fails.

    `symbols` are full TradingView symbols ("NASDAQ:WYHG"), not tickers.
    """
    return {
        "filter": [],
        "options": {"lang": "en"},
        "markets": [MARKET],
        "symbols": {"query": {"types": []}, "tickers": list(symbols)},
        "columns": list(COLUMNS),
        "range": [0, len(symbols)],
    }


def explain_drops(symbols: list[str]) -> dict[str, str]:
    """ticker -> why it stopped screening. Never raises, never stalls the poll.

    One extra request, and only on a poll where something actually dropped,
    which is rare. It is wrapped because this is a cosmetic feature sitting
    inside the loop that keeps the watchlist current: a TradingView hiccup here
    must cost a reason string, never a poll. On failure the names come back
    with no reason at all, and the message simply omits it.
    """
    if not symbols:
        return {}
    try:
        rows = parse(_scan(tickers_payload(symbols)))
    except Exception as e:                                    # noqa: BLE001
        LOG.info("could not look up why %d name(s) dropped (%s: %s)",
                 len(symbols), type(e).__name__, e)
        return {}

    out: dict[str, str] = {}
    seen = set()
    for row in rows:
        seen.add(row["ticker"])
        out[row["ticker"]] = notify.drop_reason(failing_clauses(row))
    # A symbol the UNFILTERED query does not return either is not "failing a
    # clause" -- it is gone from the scanner altogether (halted, delisted, or
    # not carried). Naming a clause for it would be a lie.
    for s in symbols:
        t = s.split(":")[-1]
        if t not in seen:
            out[t] = "no longer returned by the scanner"
    return {k: v for k, v in out.items() if v}


def in_band(row: dict) -> bool:
    """MCL's band, applied to the pre-market price the screen sorts on."""
    px = row.get("premarket_close")
    return px is not None and PRICE_MIN <= px <= PRICE_MAX


class Ranking:
    """Session-scoped memory of what has screened, newest interest first.

    Holds ORDER, not membership. Within a session nothing is forgotten except
    by the size cap, and the cap always takes from the cold end -- Ben,
    2026-09-05: "do not remove but deprioritise".

    THE WORD `Session-scoped` WAS A DESCRIPTION, NOT A MECHANISM
    -------------------------------------------------------------
    Until 2026-09-12 nothing here knew what a session was. `ever` simply never
    forgot, so a process spanning midnight carried yesterday's names into
    today's file as COLD -- and the trader arms every name in the file, in
    order. The archived watchlists show it plainly:

        09-08  hot=2 cold=4   BNC WYHG QCML HCWB SLE ISPC
        09-09  hot=5 cold=8   ... | BNC WYHG            <- 09-08's, still cold
        09-10  hot=2 cold=9   ... | BIAF RML ODD SUNE IRD  <- 09-09's

    Five of 09-10's seven `screen_validate` "misses" are that list. The
    simulation was right about every one: they were not on the screen that
    day, they were left in the file.

    `begin_session(day)` is the mechanism the docstring always claimed. It is
    explicit rather than inferred from `now` inside `update()` because `tiers()`
    is called BEFORE `update()` on every poll, so a roll hidden in `update`
    would report one tiering and write another.
    """

    def __init__(self, max_symbols: int = MAX_SYMBOLS):
        self.max_symbols = max_symbols
        self.last_seen: dict[str, float] = {}
        self.ever: dict[str, dict] = {}
        self.session = None

    def begin_session(self, day) -> bool:
        """Start `day`. Clears the memory if this is a NEW session.

        Returns True when it cleared, so the caller can log it -- a silent
        clear and a silent non-clear look identical in a file, which is how
        this went unnoticed for four sessions.
        """
        if self.session == day:
            return False
        rolled = bool(self.ever) and self.session is not None
        self.session = day
        self.last_seen.clear()
        self.ever.clear()
        return rolled

    def update(self, rows: list[dict], now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        hot, warm = [], []
        for r in rows:
            t = r["ticker"]
            self.last_seen[t] = now
            self.ever[t] = r
            (hot if in_band(r) else warm).append(t)

        current = set(hot) | set(warm)
        cold = sorted((t for t in self.ever if t not in current),
                      key=lambda t: -self.last_seen[t])
        ordered = hot + warm + cold
        return ordered[: self.max_symbols]

    def tiers(self, rows: list[dict]) -> tuple[list[str], list[str], list[str]]:
        hot = [r["ticker"] for r in rows if in_band(r)]
        warm = [r["ticker"] for r in rows if not in_band(r)]
        current = set(hot) | set(warm)
        cold = sorted((t for t in self.ever if t not in current),
                      key=lambda t: -self.last_seen[t])
        return hot, warm, cold


def check_update_mode(cookie: str | None) -> tuple[str, object]:
    """Ask TradingView whether these rows are real time, ONCE, at startup.

    Returns (verdict, raw value). Never raises: a feed that will not start
    because a diagnostic failed is worse than one that starts without it.

    WHY AT STARTUP AND WHY LOUDLY. A TradingView cookie expires. An expired one
    does not error -- the endpoint simply serves the anonymous feed, and a
    delayed watchlist is indistinguishable from a real-time one by looking at
    it. So the one moment this can be caught for free is the moment the process
    starts, and it has to be said in a line nobody can mistake for routine.

    The column is asked for in its OWN request rather than added to the poll's
    columns, so the 1,980 polls of a session stay byte-identical to what they
    were before this existed.
    """
    payload = tv_payload(1)
    payload["columns"] = list(COLUMNS) + [MODE_COLUMN]
    try:
        body = _scan(payload, cookie)
    except Exception as e:                                    # noqa: BLE001
        LOG.warning("could not read %s (%s: %s) -- proceeding without it",
                    MODE_COLUMN, type(e).__name__, e)
        return "UNKNOWN", None
    raw = None
    for item in (body.get("data") or []):
        row = dict(zip(list(COLUMNS) + [MODE_COLUMN], item.get("d") or []))
        if row.get(MODE_COLUMN) is not None:
            raw = row[MODE_COLUMN]
            break
    verdict = mode_verdict(raw)
    if verdict == "STREAMING":
        LOG.info("%s = %r -- REAL TIME%s", MODE_COLUMN, raw,
                 " (signed in)" if cookie else " (anonymous)")
    elif verdict == "DELAYED" and cookie:
        LOG.error("%s = %r -- THE COOKIE IS NOT WORKING. A cookie was sent and "
                  "the rows are still DELAYED: it has most likely expired. The "
                  "watchlist is being built from delayed data and looks "
                  "identical to a real-time one.", MODE_COLUMN, raw)
    elif verdict == "DELAYED":
        LOG.warning("%s = %r -- these rows are DELAYED, and no cookie is set "
                    "(%s / %s).", MODE_COLUMN, raw, COOKIE_ENV, SIGN_ENV)
    else:
        LOG.warning("%s = %r -- not recognised as streaming or delayed.",
                    MODE_COLUMN, raw)
    return verdict, raw


class Arrivals:
    """When each name first reached the watchlist, appended as it happens.

    THE MEASUREMENT THIS PROJECT CANNOT MAKE RETROSPECTIVELY. The handover asks
    for the distribution of how late the feed is, by comparing each name's
    first appearance against the minute the tape says it first met the screen.
    The archive cannot answer it: `var/archive/watchlist_YYYYMMDD.txt` is a
    SINGLE 09:29 snapshot with no per-name arrival times, and the only stamps on
    record are the blocked entries -- which is why that reading has n = 8.

    So the arrival time is recorded from now on. One line per name per session,
    written the first time it is written to the watchlist, appended so a crash
    keeps what it had. After a week this is a distribution instead of an
    anecdote, and it costs one small file a day.
    """

    def __init__(self, root: Path = Path("var/archive")):
        self.root = root
        self.session = None
        self.seen: set[str] = set()

    def path_for(self, day) -> Path:
        return self.root / f"watchlist_arrivals_{day:%Y%m%d}.csv"

    def begin_session(self, day) -> None:
        if self.session != day:
            self.session = day
            self.seen.clear()

    def record(self, symbols: list[str], tiers: dict[str, str], now) -> list[str]:
        """Append any name not yet seen this session. Returns those names.

        Never raises: this is telemetry sitting inside the loop that keeps the
        watchlist current, and a disk hiccup must cost a row, never a poll.
        """
        new = [t for t in symbols if t not in self.seen]
        if not new:
            return []
        self.seen.update(new)
        try:
            path = self.path_for(now)
            fresh = not path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="") as fh:
                if fresh:
                    fh.write("ticker,first_et,tier\n")
                for t in new:
                    fh.write(f"{t},{now:%Y-%m-%d %H:%M:%S},{tiers.get(t, '')}\n")
        except Exception as e:                                # noqa: BLE001
            LOG.info("could not record arrivals (%s: %s)", type(e).__name__, e)
        return new


class Freshness:
    """Yesterday's screen, re-served. The gate that stops it reaching the file.

    REGISTERED_feed_freshness.md (H-F1), committed before this class existed.

    TradingView's `premarket_*` columns hold the PREVIOUS session's values until
    today's pre-market prints arrive, so the feed's first poll of a session
    returns **yesterday's screen as ordinary live rows**. The blocked files
    stamp them at 04:00:05, 04:00:06, 04:00:08 and 04:00:26 on four separate
    sessions -- before any bar of today has closed. Eighteen live names across
    seven sessions were this, and `screen_validate` had to set them aside before
    it could read its own verdict.

    THIS IS NOT THE CARRY-OVER `Ranking.begin_session` ALREADY FIXED
    ---------------------------------------------------------------
    That one was the ranker remembering across midnight, and the fix -- forget
    at the roll -- is correct and stays. It cannot touch this one, because here
    the names arrive **fresh from the endpoint**, as rows, carrying yesterday's
    numbers. A memory that forgets perfectly is no defence against a source that
    repeats itself.

    THE RULE, and it has no free parameter
    --------------------------------------
    A name may not reach the watchlist until its `premarket_volume` has been
    observed to CHANGE, at least once, this session. Nothing else distinguishes
    a stale row from a live one: the row does not carry its own age, and a
    name's volume is the one field that must move the moment it trades today.

    No threshold, no grace window, no clock -- deliberately. The four stamps
    above sit between 04:00:05 and 04:00:26, and a window fitted to them is
    precisely the kind of number §4 of the index has a row about.

    THE SAFETY PROPERTY, which is what makes this cheap
    --------------------------------------------------
    **It can only ever delay a name's FIRST appearance. It can never remove a
    name already in the file.** Admission is permanent for the session, so a
    name whose volume goes quiet later is untouched. That is what keeps this
    compatible with Ben's rule of 2026-09-05 -- do not remove, deprioritise --
    and with the fact that dropping a name mid-session orphans a held position.

    A HELD NAME IS WITHHELD ENTIRELY, NOT DEMOTED TO COLD
    ----------------------------------------------------
    COLD is an ordering, not a veto: the trader arms every symbol in the file.
    Writing a stale name as COLD would arm it, which is the defect.

    WHAT IT COSTS
    -------------
    One poll -- ten seconds -- for a name that is trading, and the screen's own
    `premarket_volume >= 100,000` clause means an admitted name has traded a
    hundred thousand shares since 04:00. On a mid-session restart every name is
    unproven again and each waits for its next print; accepted, and deliberately
    NOT bought back with a persisted state file read inside the live loop.
    """

    def __init__(self):
        self.session = None
        self.first_volume: dict[str, float] = {}
        self.admitted: set[str] = set()
        self.held: set[str] = set()

    def begin_session(self, day) -> bool:
        """Start `day`; clear the evidence if this is a NEW session.

        Returns True when it cleared, for the same reason `Ranking` does: a
        silent clear and a silent non-clear look identical in a log.
        """
        if self.session == day:
            return False
        rolled = bool(self.first_volume) and self.session is not None
        self.session = day
        self.first_volume.clear()
        self.admitted.clear()
        self.held.clear()
        return rolled

    @staticmethod
    def _volume(row: dict) -> float | None:
        """The row's pre-market volume, or None if it cannot be compared.

        NaN is excluded on purpose. `nan != anything` is True, so an unguarded
        comparison would read a NaN volume as "changed" and admit the row --
        the same NaN-is-not-None trap that produced a sign-flipped median in a
        study this morning.
        """
        v = row.get(VOLUME_COLUMN)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        v = float(v)
        return None if math.isnan(v) else v

    def admit(self, rows: list[dict]) -> tuple[list[dict], list[str]]:
        """(rows that may reach the ranker, tickers newly held this poll).

        The second element exists so the hold is logged the first time and not
        on every subsequent poll -- a line every ten seconds for five hours
        trains the reader to skip it, which is how the original defect survived
        four sessions of being printed.
        """
        out, newly_held = [], []
        for row in rows:
            t = row["ticker"]
            if t in self.admitted:
                out.append(row)
                continue
            vol = self._volume(row)
            if vol is None:
                # Cannot be shown to have moved. Withheld, and it says so.
                if t not in self.held:
                    self.held.add(t)
                    newly_held.append(t)
                continue
            if t not in self.first_volume:
                self.first_volume[t] = vol
                if t not in self.held:
                    self.held.add(t)
                    newly_held.append(t)
                continue
            if vol != self.first_volume[t]:
                self.admitted.add(t)
                self.held.discard(t)
                out.append(row)
        return out, newly_held


def write_watchlist(path: Path, symbols: list[str], header: str = "") -> bool:
    """Atomic write. The trader may read this file at any moment, and a
    half-written file is a truncated watchlist rather than an error.

    Returns True if the file's symbol content actually changed, so a caller can
    avoid logging a line every 10 seconds when nothing has moved.
    """
    body = "\n".join(symbols)
    existing = ""
    if path.exists():
        existing = "\n".join(
            ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = (f"# {header}\n" if header else "") + body + ("\n" if body else "")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return body != existing


def in_session(now: datetime) -> bool:
    return SESSION_START <= now.timetz().replace(tzinfo=None) < SESSION_END


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="TradingView screen -> watchlist.txt")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    ap.add_argument("--out", type=Path, default=WATCHLIST)
    ap.add_argument("--max-symbols", type=int, default=MAX_SYMBOLS)
    ap.add_argument("--once", action="store_true", help="one poll, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="never write the file")
    ap.add_argument("--all-hours", action="store_true",
                    help="ignore the 04:00-09:30 ET window")
    notify.add_batch_arg(ap)
    ap.add_argument("--no-telegram", action="store_true",
                    help="run without notifications even if configured")
    ap.add_argument("--no-cookie", action="store_true",
                    help=f"ignore {COOKIE_ENV}/{SIGN_ENV} and poll anonymously")
    ap.add_argument("--heartbeat", type=float, default=3600.0,
                    help="seconds between 'feed alive' messages; 0 disables")
    return ap


def main(argv: list[str] | None = None) -> int:
    """Poll the screen and keep the watchlist current.

    Takes argv so main.py can run this in a thread beside the trader rather
    than only as its own process. Without it the embedded call would read
    sys.argv and pick up the TRADER's flags.
    """
    ap = build_parser()
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    rank = Ranking(a.max_symbols)
    fresh = Freshness()
    arrivals = Arrivals()
    cookie = None if a.no_cookie else session_cookie()
    check_update_mode(cookie)
    backoff = 0.0
    tg = (notify.Notifier() if a.no_telegram
          else notify.Notifier.from_env(a.telegram_batch_min))
    # Previous poll's HOT+WARM set. Changes are reported against what was
    # SCREENING, not against the file: the file only ever grows, so diffing it
    # would report an "add" once and never a "remove".
    prev_screening: set[str] = set()
    last_beat = time.monotonic()

    # ONE WRITER. --dry-run writes nothing, so it is not a writer and must
    # neither take the lock nor be blocked by one -- the whole point of
    # --dry-run is to check the endpoint while a real feed is running.
    if a.dry_run:
        return _loop(a, rank, fresh, arrivals, cookie, tg, prev_screening,
                     last_beat, backoff)
    held = session_lock.active(session_lock.WRITER_LOCK_PATH)
    if held:
        LOG.error("another watchlist writer is running -- %s",
                  session_lock.describe(held))
        LOG.error("Two writers take turns and the trader sees the watchlist "
                  "flip between two answers every few seconds. Stop that one "
                  "first.")
        return 2
    with session_lock.held("watchlist-writer", "tv_feed",
                           session_lock.WRITER_LOCK_PATH, out=str(a.out)):
        return _loop(a, rank, fresh, arrivals, cookie, tg, prev_screening,
                     last_beat, backoff)


def _loop(a, rank, fresh, arrivals, cookie, tg, prev_screening, last_beat,
          backoff) -> int:
    while True:
        now = datetime.now(ET)
        if not a.all_hours and not a.once and not in_session(now):
            if now.timetz().replace(tzinfo=None) >= SESSION_END:
                LOG.info("past %s ET, stopping", SESSION_END)
                return 0
            LOG.info("before %s ET, waiting", SESSION_START)
            time.sleep(30)
            continue

        try:
            rows = fetch(a.max_symbols, cookie)
            backoff = 0.0
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as e:
            backoff = min(max(backoff * 2, BACKOFF_START), BACKOFF_MAX)
            LOG.warning("screener call failed (%s: %s) — backing off %.0fs",
                        type(e).__name__, e, backoff)
            if a.once:
                return 1
            time.sleep(backoff)
            continue

        # Roll the ranker's memory BEFORE tiering, so the tiers reported and
        # the symbols written describe the same session.
        if rank.begin_session(now.date()):
            LOG.info("new session %s — ranker memory cleared; yesterday's "
                     "names no longer carry over as COLD", now.date())
        fresh.begin_session(now.date())
        arrivals.begin_session(now.date())

        # H-F1. Withhold rows that have not yet been shown to describe TODAY.
        # This runs BEFORE tiers() and update() and both are given the SAME
        # list, for the reason the roll is here rather than inside update():
        # a filter applied in one of them would report one tiering and write
        # another. A held name is withheld entirely rather than demoted to
        # COLD, because the trader arms COLD symbols too.
        rows, newly_held = fresh.admit(rows)
        if newly_held:
            LOG.info("holding %d name(s) until %s moves — a row can be "
                     "yesterday's screen until today's prints arrive: %s",
                     len(newly_held), VOLUME_COLUMN, ", ".join(newly_held))

        hot, warm, cold = rank.tiers(rows)
        symbols = rank.update(rows)

        screening = set(hot) | set(warm)
        added = sorted(screening - prev_screening)
        removed = sorted(prev_screening - screening)
        prev_screening = screening

        if a.dry_run:
            LOG.info("HOT %s | WARM %s | COLD %s",
                     hot or "-", warm or "-", cold[:5] or "-")
        else:
            changed = write_watchlist(
                a.out, symbols,
                header=f"tv_feed {now:%Y-%m-%d %H:%M:%S} ET  "
                       f"hot={len(hot)} warm={len(warm)} cold={len(cold)} "
                       f"held={len(fresh.held)}")
            if changed:
                LOG.info("watchlist -> %d symbols  HOT %s | WARM %s | COLD %s",
                         len(symbols), hot or "-", warm or "-",
                         cold[:5] or "-")
            # Written where the file is written, so a name is stamped at the
            # moment it could first be acted on -- not when it screened.
            #
            # `symbols` (what was WRITTEN) rather than the admitted rows (what
            # SCREENED). The two coincide for a name's FIRST appearance, since
            # a name cannot be COLD before it has been HOT -- so a mutation
            # swapping them survives the suite. An equivalent mutant, named
            # here rather than chased with a contrived test. They part company
            # only at the MAX_SYMBOLS cap: a name trimmed from the cold end and
            # later re-screened is in `rows` and not in `symbols`. The file is
            # the right answer, because this series measures when the TRADER
            # could have acted, and the trader reads the file.
            tiers = ({t: "hot" for t in hot} | {t: "warm" for t in warm}
                     | {t: "cold" for t in cold})
            arrivals.record(symbols, tiers, now)

        # One coalesced message per poll that changed something. Sending per
        # symbol would be up to 2,000 messages a session and would trip
        # Telegram's per-chat rate limit long before that.
        if added or removed:
            # Why each dropped name dropped. One extra request, only on a poll
            # that lost something, and only when there is somewhere to send it
            # -- with Telegram off this is pure cost.
            reasons = {}
            if removed and tg.enabled:
                reasons = explain_drops(
                    [rank.ever[t]["symbol"] for t in removed
                     if t in rank.ever and rank.ever[t].get("symbol")])
            tg.send(notify.watchlist_change(added, removed, hot, warm, cold,
                                            now=now, rows=rows,
                                            reasons=reasons))

        # A quiet pre-market produces no changes at all, which is exactly when
        # a crashed feed looks identical to a calm market from the phone.
        # force=True so the rate limiter cannot swallow the one message whose
        # whole purpose is to prove the process is alive.
        if a.heartbeat and time.monotonic() - last_beat >= a.heartbeat:
            tg.send(notify.heartbeat(len(rows), len(hot), len(warm), len(cold),
                                     stats=tg.stats(), now=now), force=True)
            last_beat = time.monotonic()
        if warm:
            LOG.info("outside MCL's $%.0f-%.0f band, deprioritised: %s",
                     PRICE_MIN, PRICE_MAX, ", ".join(warm))

        if a.once:
            tg.flush()
            LOG.info("%s", tg.stats())
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
