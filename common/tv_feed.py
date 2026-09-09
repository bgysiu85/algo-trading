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
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from common import notify
from common.tv_screener import (CHANGE_COLUMN, COLUMNS, FILTERS, MARKET,
                                PRICE_MAX, PRICE_MIN, check_response,
                                failing_clauses)

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


def fetch(limit: int = MAX_SYMBOLS) -> list[dict]:
    body = _scan(tv_payload(limit))
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


def _scan(payload: dict) -> dict:
    """One POST to the scanner endpoint. Split out of fetch() so the drop
    lookup shares exactly the request the feed itself makes, and so a test can
    replace the network in one place instead of patching urllib."""
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0"})
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

    Holds ORDER, not membership. Nothing is ever forgotten except by the size
    cap, and the cap always takes from the cold end.
    """

    def __init__(self, max_symbols: int = MAX_SYMBOLS):
        self.max_symbols = max_symbols
        self.last_seen: dict[str, float] = {}
        self.ever: dict[str, dict] = {}

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
            ln.strip() for ln in path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#"))
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = (f"# {header}\n" if header else "") + body + ("\n" if body else "")
    tmp.write_text(text)
    os.replace(tmp, path)
    return body != existing


def in_session(now: datetime) -> bool:
    return SESSION_START <= now.timetz().replace(tzinfo=None) < SESSION_END


def main() -> int:
    ap = argparse.ArgumentParser(description="TradingView screen -> watchlist.txt")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    ap.add_argument("--out", type=Path, default=WATCHLIST)
    ap.add_argument("--max-symbols", type=int, default=MAX_SYMBOLS)
    ap.add_argument("--once", action="store_true", help="one poll, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="never write the file")
    ap.add_argument("--all-hours", action="store_true",
                    help="ignore the 04:00-09:30 ET window")
    ap.add_argument("--no-telegram", action="store_true",
                    help="run without notifications even if configured")
    ap.add_argument("--heartbeat", type=float, default=3600.0,
                    help="seconds between 'feed alive' messages; 0 disables")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    rank = Ranking(a.max_symbols)
    backoff = 0.0
    tg = notify.Notifier() if a.no_telegram else notify.Notifier.from_env()
    # Previous poll's HOT+WARM set. Changes are reported against what was
    # SCREENING, not against the file: the file only ever grows, so diffing it
    # would report an "add" once and never a "remove".
    prev_screening: set[str] = set()
    last_beat = time.monotonic()

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
            rows = fetch(a.max_symbols)
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
                       f"hot={len(hot)} warm={len(warm)} cold={len(cold)}")
            if changed:
                LOG.info("watchlist -> %d symbols  HOT %s | WARM %s | COLD %s",
                         len(symbols), hot or "-", warm or "-",
                         cold[:5] or "-")

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
