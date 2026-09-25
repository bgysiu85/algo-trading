#!/usr/bin/env python3
"""W07-0012 subitem 2: sample-pull Alpaca IEX minute bars for a stratified
sample of the swing point-in-time universe, and measure the coverage gap
against the EOD closes `pit_universe.py` already pulled -- the coverage risk
`w07_0012_intraday_data_options_20260925.md` flagged for the free/IEX-only
route, priced BEFORE Ben spends anything on the EODHD intraday upgrade.

    $env:ALPACA_API_KEY_ID = op read "op://Trading/Alpaca/key-id"
    $env:ALPACA_API_SECRET_KEY = op read "op://Trading/Alpaca/secret-key"
    python -m strategy.swing.alpaca_coverage_probe --sample 40 --dates 20 --confirm
    python -m strategy.swing.alpaca_coverage_probe --self-test

WHY THIS EXISTS
---------------
`docs/research/REGISTERED_swing_v0.md` S2.3 needs an intraday quote at three
fixed clock times a session -- 09:30 (open), 11:30 (midday), 15:30 (close)
ET -- for roughly 900 point-in-time names back to 2016-05-10. Only daily EOD
bars exist on disk (`var/swing_pit/eod/*.csv`). Three sources were priced in
`w07_0012_intraday_data_options_20260925.md`: a paid EODHD intraday upgrade
(~EUR30/mo, 1-min bars from 2004), Polygon.io ($79/mo, only reaches 10 years
back), and Alpaca's free IEX-only historical bars -- coverage unmeasured.
Ben's decision, 2026-09-25: "Let's try Alpaca first. If there is still gap,
then we go for EODHD." This is that measurement, on a SAMPLE rather than the
full universe, so the EODHD decision does not wait on a 900-symbol,
10-year pull that may turn out to be unnecessary (subitem 4 reviews this and
decides; this script only measures).

WHAT "GAP" MEANS HERE
----------------------
IEX is one exchange among many; a name can go minutes without an IEX print
even while it trades briskly elsewhere. A bucket fill needs the last trade AT
OR BEFORE the bucket's clock time -- the same rule a live order follows -- so
this probe does not require an exact-minute bar. It walks backward from the
bucket time through the pulled session and reports how far back it had to
go. Three outcomes per (symbol, date, bucket):

  HIT       a bar at or within TOLERANCE_MIN minutes of the bucket time
  BACKFILL  the nearest at-or-before bar exists but is further back than
            that -- usable, but the fill would be stale
  MISSING   no bar at or before the bucket anywhere in the pulled window

The close-bucket price is also compared against `pit_universe.py`'s own EOD
close for that date (`gap_bps`) -- IEX is one exchange's tape, not the
consolidated one, so its last print of the day need not equal the officially
reported close.

SAMPLING, NOT A FULL PULL
--------------------------
`--sample` codes (default 40) are drawn from `membership.csv` with
`random.Random(--seed)`, at least half of them codes that were EVER
delisted from the index (`Spell.is_delisted`) -- delisted names are the
coverage risk the options doc actually flagged, and an all-current sample
would answer an easier question than the one being asked. `--dates` trading
dates (default 20) are drawn uniformly at random from the point-in-time
window (2016-05-10 by default, per the spec, to today), weekdays only, same
seed. A (symbol, date) pair is skipped -- no request spent -- unless the date
falls inside one of that symbol's own membership spells AND
`pit_universe.py` already has an EOD close for it; a hole in the EOD archive
is `pit_universe.py`'s coverage question, not this one's. One Alpaca request
per surviving (symbol, date) pair: the whole 09:25-15:35 ET session in a
single 1-minute-bar call, so a sample of 40 x 20 is at most 800 requests,
not 2,400.

PRICED BEFORE PULLED (`PROGRAM_INDEX` SS1: a tool that can spend HOURS states
that number too, even at $0 of billing)
-------------------------------------------------------------------------
The plan (request count, estimated wall clock at `ALPACA_PACE_S`) is printed
and the probe stops without `--confirm`.

NO REPO IMPORTS BEYOND THE PACKAGE ITSELF
-------------------------------------------
Same convention as the rest of `strategy/swing/`: standard library only,
plus `from strategy.swing import pit_universe as P` for the membership/EOD
readers `pit_universe.py` already owns -- the same reuse `pit_validate.py`
makes, so this is not a second CSV parser for the same files.

THE KEY
-------
Read from `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` and nowhere else --
the same two names `common/news_pull.py` already uses for the same vendor,
so one 1Password item serves both. No `--key` flag: a flag puts a key in
PowerShell history. Both are scrubbed from everything this tool prints.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from strategy.swing import pit_universe as P

Refused = P.Refused


class InvalidSymbol(Exception):
    """Alpaca rejected the symbol outright (HTTP 400) -- it is not a real
    ticker, not a coverage gap. `pit_universe.py`'s own EODHD membership data
    carries codes like 'NFX_OLD' for a name later reused by an unrelated
    company (the same class of thing `pit_validate.py`'s RENAME check exists
    for); EODHD accepts that as a code, Alpaca does not. Caught in
    run_pairs() and reported in its own section, never silently merged into
    MISSING (a real Alpaca gap) or allowed to abort the whole sample)."""

API_BARS = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
ENV_KEY_ID = "ALPACA_API_KEY_ID"
ENV_SECRET = "ALPACA_API_SECRET_KEY"
ALPACA_PACE_S = 0.35     # same measured free-tier pace common/news_pull.py uses

DEFAULT_OUT = Path("var") / "swing_pit"
DEFAULT_WINDOW_START = dt.date(2016, 5, 10)   # REGISTERED_swing_v0.md S6's window start

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# REGISTERED_swing_v0.md S2.3
BUCKETS: list[tuple[str, dt.time]] = [
    ("open", dt.time(9, 30)),
    ("midday", dt.time(11, 30)),
    ("close", dt.time(15, 30)),
]
SESSION_FETCH_START = dt.time(9, 25)
SESSION_FETCH_END = dt.time(15, 35)
TOLERANCE_MIN = 5.0      # HIT vs BACKFILL boundary, in minutes


# --------------------------------------------------------------------------
# the keys, and keeping them out of everything we print
# --------------------------------------------------------------------------

def api_keys(env: dict | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    key_id = (env.get(ENV_KEY_ID) or "").strip()
    secret = (env.get(ENV_SECRET) or "").strip()
    missing = [n for n, v in ((ENV_KEY_ID, key_id), (ENV_SECRET, secret)) if not v]
    if missing:
        raise Refused(
            f"{' and '.join(missing)} not set. In the same PowerShell window:\n"
            f'  $env:{ENV_KEY_ID} = op read "op://Trading/Alpaca/key-id"\n'
            f'  $env:{ENV_SECRET} = op read "op://Trading/Alpaca/secret-key"')
    for name, v in ((ENV_KEY_ID, key_id), (ENV_SECRET, secret)):
        if v.startswith("op://"):
            raise Refused(f"{name} holds an op:// reference, not the secret. "
                          "Wrap it in `op read \"...\"` so 1Password resolves it.")
    return key_id, secret


def scrub(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
            text = text.replace(urllib.parse.quote(s, safe=""), "***")
    return text


# --------------------------------------------------------------------------
# HTTP, injectable so the tests never touch the network
# --------------------------------------------------------------------------

# fetch(symbol, date) -> the raw Alpaca "bars" list for that session window
Fetch = Callable[[str, dt.date], list[dict]]


def et_session_bounds_utc(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, SESSION_FETCH_START, tzinfo=ET).astimezone(UTC)
    end = dt.datetime.combine(day, SESSION_FETCH_END, tzinfo=ET).astimezone(UTC)
    return start, end


def rfc3339(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def http_fetch_factory(key_id: str, secret: str, pause: float = ALPACA_PACE_S,
                       retries: int = 4) -> Fetch:
    def fetch(symbol: str, day: dt.date) -> list[dict]:
        start_utc, end_utc = et_session_bounds_utc(day)
        params = {
            "timeframe": "1Min",
            "start": rfc3339(start_utc),
            "end": rfc3339(end_utc),
            "feed": "iex",
            "adjustment": "raw",
            "limit": 1000,
        }
        url = (API_BARS.format(symbol=urllib.parse.quote(symbol, safe="")) +
              "?" + urllib.parse.urlencode(params))
        req = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json"})
        delay = 2.0
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = json.loads(r.read().decode("utf-8"))
                time.sleep(pause)
                return body.get("bars") or []
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return []
                if e.code in (401, 403):
                    raise Refused(
                        f"Alpaca refused the key for {symbol} (HTTP {e.code}). "
                        "Check the key pair and the account's market-data "
                        "entitlement.") from None
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                if e.code == 400:
                    raise InvalidSymbol(symbol) from None
                raise RuntimeError(
                    scrub(f"HTTP {e.code} on {symbol} {day}", key_id, secret)
                ) from None
            except urllib.error.URLError as e:
                if attempt < retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(scrub(
                    f"network error on {symbol} {day}: {e.reason}",
                    key_id, secret)) from None
        raise RuntimeError(f"gave up on {symbol} {day}")
    return fetch


# --------------------------------------------------------------------------
# EOD closes, read the way pit_universe.py wrote them
# --------------------------------------------------------------------------

def load_eod_closes(path: Path) -> dict[dt.date, float]:
    if not path.exists():
        return {}
    out: dict[dt.date, float] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = P.to_date(r.get("date"))
            c = r.get("close")
            if d is None or c in (None, ""):
                continue
            try:
                out[d] = float(c)
            except ValueError:
                continue
    return out


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------

def pick_sample_symbols(spells: Iterable[P.Spell], n: int, seed: int,
                        min_delisted_frac: float = 0.5) -> list[str]:
    """At least half the sample (when enough exist) are codes that were EVER
    delisted from the index -- the coverage risk actually in question."""
    by_code: dict[str, list[P.Spell]] = {}
    for s in spells:
        by_code.setdefault(s.code, []).append(s)
    codes = sorted(by_code)
    if n >= len(codes):
        return codes
    delisted = [c for c in codes if any(s.is_delisted for s in by_code[c])]
    current = [c for c in codes if c not in set(delisted)]
    rng = random.Random(seed)
    n_delisted = min(len(delisted), max(1, round(n * min_delisted_frac))) if delisted else 0
    n_current = min(n - n_delisted, len(current))
    n_delisted = min(n - n_current, len(delisted))
    chosen = set(rng.sample(delisted, n_delisted)) if n_delisted else set()
    chosen |= set(rng.sample(current, n_current)) if n_current else set()
    if len(chosen) < n:
        rest = [c for c in codes if c not in chosen]
        chosen |= set(rng.sample(rest, min(n - len(chosen), len(rest))))
    return sorted(chosen)


def pick_sample_dates(window_start: dt.date, window_end: dt.date, n: int,
                      seed: int) -> list[dt.date]:
    """n weekday dates drawn uniformly at random from the window, seeded."""
    if n <= 0 or window_end < window_start:
        return []
    span = (window_end - window_start).days
    rng = random.Random(seed)
    out: set[dt.date] = set()
    tries = 0
    max_tries = max(200, n * 50)
    while len(out) < n and tries < max_tries:
        tries += 1
        d = window_start + dt.timedelta(days=rng.randint(0, span))
        if d.weekday() < 5:
            out.add(d)
    return sorted(out)


def member_dates_with_eod(spells_for_code: list[P.Spell], dates: list[dt.date],
                          eod_closes: dict[dt.date, float]) -> list[dt.date]:
    return [d for d in dates
           if d in eod_closes and any(s.covers(d) for s in spells_for_code)]


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    symbol: str
    date: dt.date
    bucket: str
    target_et: str
    bar_et: str | None
    minutes_back: float | None
    alpaca_price: float | None
    eod_close: float | None
    gap_bps: float | None
    status: str          # HIT / BACKFILL / MISSING

    def row(self) -> list:
        f = lambda v: "" if v is None else v
        return [self.symbol, self.date.isoformat(), self.bucket, self.target_et,
                f(self.bar_et), f(round(self.minutes_back, 2) if self.minutes_back is not None else None),
                f(round(self.alpaca_price, 4) if self.alpaca_price is not None else None),
                f(self.eod_close), f(round(self.gap_bps, 2) if self.gap_bps is not None else None),
                self.status]


OBS_FIELDS = ["symbol", "date", "bucket", "target_et", "bar_et", "minutes_back",
             "alpaca_price", "eod_close", "gap_bps", "status"]


def bar_et_time(bar: dict) -> dt.datetime:
    ts = str(bar["t"]).replace("Z", "+00:00")
    return dt.datetime.fromisoformat(ts).astimezone(ET)


def invalid_symbol_observations(symbol: str, day: dt.date,
                                eod_close: float | None) -> list[Observation]:
    """One row per bucket for a symbol Alpaca rejected outright (HTTP 400) --
    not a coverage gap, so never carries HIT/BACKFILL/MISSING."""
    return [Observation(symbol, day, bucket, btime.isoformat(), None, None,
                        None, eod_close, None, "INVALID_SYMBOL")
           for bucket, btime in BUCKETS]


def evaluate_day(symbol: str, day: dt.date, bars: list[dict],
                 eod_close: float | None) -> list[Observation]:
    parsed = sorted(((bar_et_time(b), b) for b in bars if "t" in b),
                    key=lambda x: x[0])
    out = []
    for bucket, btime in BUCKETS:
        target = dt.datetime.combine(day, btime, tzinfo=ET)
        candidates = [(t, b) for t, b in parsed if t <= target]
        if not candidates:
            out.append(Observation(symbol, day, bucket, btime.isoformat(),
                                   None, None, None, eod_close, None, "MISSING"))
            continue
        t, b = candidates[-1]
        minutes_back = (target - t).total_seconds() / 60.0
        price = float(b["c"])
        status = "HIT" if minutes_back <= TOLERANCE_MIN else "BACKFILL"
        gap_bps = None
        if bucket == "close" and eod_close:
            gap_bps = (price - eod_close) / eod_close * 10000.0
        out.append(Observation(symbol, day, bucket, btime.isoformat(),
                               t.isoformat(), minutes_back, price, eod_close,
                               gap_bps, status))
    return out


# --------------------------------------------------------------------------
# plan (priced before pulled) and the run
# --------------------------------------------------------------------------

def build_plan(spells: list[P.Spell], out_dir: Path, sample_n: int, dates_n: int,
              seed: int, window_start: dt.date, window_end: dt.date
              ) -> tuple[list[tuple[str, dt.date, float]], dict]:
    by_code: dict[str, list[P.Spell]] = {}
    for s in spells:
        by_code.setdefault(s.code, []).append(s)
    symbols = pick_sample_symbols(spells, sample_n, seed)
    dates = pick_sample_dates(window_start, window_end, dates_n, seed)
    pairs: list[tuple[str, dt.date, float]] = []
    per_symbol_eod: dict[str, dict[dt.date, float]] = {}
    for sym in symbols:
        eod = load_eod_closes(out_dir / "eod" / f"{P.file_stem(sym)}.csv")
        per_symbol_eod[sym] = eod
        for d in member_dates_with_eod(by_code[sym], dates, eod):
            pairs.append((sym, d, eod[d]))
    n_delisted = sum(1 for s in symbols if any(sp.is_delisted for sp in by_code[s]))
    plan = {
        "symbols_sampled": len(symbols),
        "symbols_ever_delisted": n_delisted,
        "dates_sampled": len(dates),
        "pairs_to_pull": len(pairs),
        "pairs_skipped_no_eod_or_not_member": len(symbols) * len(dates) - len(pairs),
    }
    return pairs, plan


def cost_lines(plan: dict, pace_s: float = ALPACA_PACE_S) -> list[str]:
    n = plan["pairs_to_pull"]
    secs = n * pace_s
    return [
        f"plan: {plan['symbols_sampled']} symbols sampled "
        f"({plan['symbols_ever_delisted']} of them ever delisted from the "
        f"index) x {plan['dates_sampled']} sampled dates",
        f"{plan['pairs_skipped_no_eod_or_not_member']} (symbol, date) pairs "
        "skipped -- not a member that day, or pit_universe.py has no EOD "
        "close for it",
        f"{n} Alpaca requests to make (one per surviving pair, whole "
        "session in one call)",
        f"estimated wall clock at {pace_s}s/request: {secs / 60:.1f} minutes",
        "cost: $0 -- Alpaca's free IEX historical bars; this states the "
        "wall-clock, not a dollar figure (PROGRAM_INDEX S1)",
    ]


def run_pairs(fetch: Fetch, pairs: list[tuple[str, dt.date, float]],
             log=print) -> tuple[list[Observation], set[str]]:
    """Returns (observations, symbols Alpaca rejected outright as HTTP 400).
    A rejected symbol is not a coverage gap -- it is skipped and the run
    continues rather than aborting on the first bad ticker label."""
    out: list[Observation] = []
    invalid_symbols: set[str] = set()
    for i, (sym, d, eod_close) in enumerate(pairs, 1):
        try:
            bars = fetch(sym, d)
        except InvalidSymbol:
            invalid_symbols.add(sym)
            out.extend(invalid_symbol_observations(sym, d, eod_close))
        else:
            out.extend(evaluate_day(sym, d, bars, eod_close))
        if i % 50 == 0:
            log(f"  {i}/{len(pairs)} symbol-days pulled")
    if invalid_symbols:
        log(f"  {len(invalid_symbols)} symbol(s) rejected outright by Alpaca "
           f"(HTTP 400, not a coverage gap): {', '.join(sorted(invalid_symbols))}")
    return out, invalid_symbols


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def _pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100.0 * n / d:.1f}%"


def build_report(obs: list[Observation], delisted_symbols: set[str],
                 plan: dict, invalid_symbols: set[str] | None = None) -> str:
    invalid_symbols = invalid_symbols or set()
    L = ["Alpaca IEX coverage probe -- W07-0012 subitem 2", ""]
    L += [f"  {k}: {v}" for k, v in plan.items()]
    L.append("")

    if invalid_symbols:
        L.append(f"SYMBOLS ALPACA REJECTED OUTRIGHT (HTTP 400, not a coverage "
                 f"gap -- {len(invalid_symbols)} of {plan['symbols_sampled']} "
                 "sampled; excluded from every table below)")
        for s in sorted(invalid_symbols):
            tag = " (ever delisted)" if s in delisted_symbols else ""
            L.append(f"  {s}{tag}")
        L.append("")

    # coverage tables only ever score a real Alpaca answer (HIT/BACKFILL/
    # MISSING); a rejected symbol's rows are reported above, not folded in
    # here as if Alpaca had answered and simply had no bar.
    coverage_obs = [o for o in obs if o.status != "INVALID_SYMBOL"]

    by_bucket: dict[str, dict[str, int]] = {b: {"HIT": 0, "BACKFILL": 0, "MISSING": 0}
                                            for b, _ in BUCKETS}
    for o in coverage_obs:
        by_bucket[o.bucket][o.status] += 1

    L.append("COVERAGE BY BUCKET (all sampled symbol-days)")
    L.append(f"  {'bucket':<8} {'hit':>6} {'backfill':>10} {'missing':>9} {'n':>6}")
    for bucket, _ in BUCKETS:
        c = by_bucket[bucket]
        n = sum(c.values())
        L.append(f"  {bucket:<8} {_pct(c['HIT'], n):>6} {_pct(c['BACKFILL'], n):>10} "
                 f"{_pct(c['MISSING'], n):>9} {n:>6}")
    L.append("")

    def split(pred, label):
        rows = [o for o in coverage_obs if pred(o)]
        by_b: dict[str, dict[str, int]] = {b: {"HIT": 0, "BACKFILL": 0, "MISSING": 0}
                                           for b, _ in BUCKETS}
        for o in rows:
            by_b[o.bucket][o.status] += 1
        L.append(f"COVERAGE -- {label} ({len({o.symbol for o in rows})} symbols, "
                 f"{len(rows)} symbol-day-buckets)")
        for bucket, _ in BUCKETS:
            c = by_b[bucket]
            n = sum(c.values())
            L.append(f"  {bucket:<8} {_pct(c['HIT'], n):>6} {_pct(c['BACKFILL'], n):>10} "
                     f"{_pct(c['MISSING'], n):>9} {n:>6}")
        L.append("")

    split(lambda o: o.symbol in delisted_symbols, "ever delisted from the index")
    split(lambda o: o.symbol not in delisted_symbols, "still current")

    gaps = [o.gap_bps for o in coverage_obs if o.bucket == "close" and o.gap_bps is not None]
    L.append("CLOSE-BUCKET PRICE vs pit_universe.py's EOD CLOSE, in bps (|gap|)")
    if gaps:
        abs_gaps = sorted(abs(g) for g in gaps)
        L.append(f"  n={len(abs_gaps)}  median={statistics.median(abs_gaps):.2f}  "
                 f"p90={abs_gaps[min(len(abs_gaps) - 1, int(0.9 * len(abs_gaps)))]:.2f}  "
                 f"max={abs_gaps[-1]:.2f}")
    else:
        L.append("  n=0 -- no close-bucket bar had both an Alpaca price and an "
                 "EOD close to compare")
    L.append("")

    worst = sorted({o.symbol for o in coverage_obs},
                   key=lambda s: sum(1 for o in coverage_obs if o.symbol == s and
                                     o.status == "MISSING"), reverse=True)[:10]
    L.append("SYMBOLS WITH THE MOST MISSING BUCKETS (top 10)")
    for s in worst:
        n_missing = sum(1 for o in coverage_obs if o.symbol == s and o.status == "MISSING")
        n_total = sum(1 for o in coverage_obs if o.symbol == s)
        if n_missing:
            tag = " (ever delisted)" if s in delisted_symbols else ""
            L.append(f"  {s:<8}{tag}  {n_missing}/{n_total} bucket-days missing")
    L.append("")
    L.append("This report measures coverage; it does not decide. Subitem 4 "
             "(Ben) reviews it and approves the EODHD top-up only if the gap "
             "is material.")
    return "\n".join(L) + "\n"


def write_obs_csv(path: Path, obs: list[Observation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(OBS_FIELDS)
        for o in obs:
            w.writerow(o.row())


# --------------------------------------------------------------------------
# self-test (no network, no real var/swing_pit needed)
# --------------------------------------------------------------------------

def self_test() -> list[str]:
    import tempfile

    sample_day = dt.date(2020, 6, 15)     # inside ALL three spells' coverage below
    spells = [
        P.Spell("sp500", "GOOD", "Still Here Inc", dt.date(2015, 1, 1), None,
               True, False),
        P.Spell("sp500", "GONE", "Delisted Co", dt.date(2015, 1, 1),
               dt.date(2020, 6, 30), False, True),
        P.Spell("sp500", "BAD_OLD", "Reused Ticker Co", dt.date(2015, 1, 1),
               dt.date(2020, 6, 30), False, True),
    ]

    def bar(hhmm: str, close: float) -> dict:
        return {"t": f"{sample_day.isoformat()}T{hhmm}:00Z", "o": close,
               "h": close, "l": close, "c": close, "v": 100}

    # 2020-06-15 is EDT (UTC-4): 09:30 ET open bucket = 13:30Z.
    good_bars = [bar("13:30", 10.0),      # exact open
                bar("15:30", 10.5),      # midday bucket is 15:30Z -- exact
                # no bar near the close bucket (19:30Z) -- nearest before it
                # is the midday bar, 4 hours back: BACKFILL, not MISSING
                ]
    gone_bars: list[dict] = []           # nothing prints all day -> MISSING x3

    def fake_fetch(symbol: str, day: dt.date) -> list[dict]:
        if symbol == "GOOD":
            return good_bars
        if symbol == "BAD_OLD":
            # Alpaca doesn't recognize an EODHD-internal reuse label --
            # simulates the real NFX_OLD crash this fix addresses.
            raise InvalidSymbol(symbol)
        return gone_bars

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        eod_dir = out / "eod"
        eod_dir.mkdir(parents=True)
        with (eod_dir / "GOOD.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            w.writerow({"date": sample_day.isoformat(), "open": 9.9, "high": 10.6,
                       "low": 9.8, "close": 10.4, "adjusted_close": 10.4,
                       "volume": 1000})
        with (eod_dir / "GONE.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            w.writerow({"date": sample_day.isoformat(), "open": 5.0, "high": 5.1,
                       "low": 4.9, "close": 5.0, "adjusted_close": 5.0,
                       "volume": 500})
        with (eod_dir / "BAD_OLD.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            w.writerow({"date": sample_day.isoformat(), "open": 7.0, "high": 7.1,
                       "low": 6.9, "close": 7.0, "adjusted_close": 7.0,
                       "volume": 200})

        pairs, plan = build_plan(spells, out, sample_n=3, dates_n=1, seed=1,
                                 window_start=sample_day, window_end=sample_day)
        assert plan["symbols_sampled"] == 3, plan
        assert plan["pairs_to_pull"] == 3, plan   # all three cover the sample day

        obs, invalid_symbols = run_pairs(fake_fetch, pairs, log=lambda m: None)
        assert len(obs) == 9, len(obs)   # 3 symbols x 3 buckets
        assert invalid_symbols == {"BAD_OLD"}, invalid_symbols

        good = {o.bucket: o for o in obs if o.symbol == "GOOD"}
        assert good["open"].status == "HIT" and good["open"].minutes_back == 0, good
        assert good["midday"].status == "HIT", good
        assert good["close"].status == "BACKFILL", good
        assert good["close"].minutes_back == 240.0, good
        # close-bucket gap: alpaca last price 10.5 vs EOD close 10.4
        assert good["close"].gap_bps is not None and abs(
            good["close"].gap_bps - ((10.5 - 10.4) / 10.4 * 10000)) < 1e-6, good

        gone = {o.bucket: o for o in obs if o.symbol == "GONE"}
        assert all(o.status == "MISSING" for o in gone.values()), gone

        bad = {o.bucket: o for o in obs if o.symbol == "BAD_OLD"}
        assert all(o.status == "INVALID_SYMBOL" for o in bad.values()), bad

        report = build_report(obs, delisted_symbols={"GONE", "BAD_OLD"}, plan=plan,
                              invalid_symbols=invalid_symbols)
        assert "ever delisted from the index" in report
        assert "GONE" in report        # shows up as a symbol with missing buckets
        assert "REJECTED OUTRIGHT" in report and "BAD_OLD" in report
        # a rejected symbol must never leak into the worst-missing-buckets
        # table as if Alpaca had simply had no bar for it
        assert "BAD_OLD" not in report.split("MOST MISSING BUCKETS")[1]

    return ["self-test passed: HIT / BACKFILL / MISSING classified correctly, "
           "the close-bucket bps gap matched by hand, an HTTP-400 rejection "
           "(NFX_OLD-style code) was skipped and reported separately instead "
           "of aborting the run, and the delisted split and worst-symbols "
           "table both surfaced the all-missing name"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sample", type=int, default=40, help="number of symbols")
    p.add_argument("--dates", type=int, default=20, help="number of sample dates")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--window-start", default=DEFAULT_WINDOW_START.isoformat())
    p.add_argument("--window-end", default=None,
                   help="default: today")
    p.add_argument("--confirm", action="store_true",
                   help="required to actually pull from Alpaca")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0

    out = a.out_dir
    membership = out / "membership.csv"
    if not membership.exists():
        sys.exit(f"{membership} does not exist -- run "
                 "`python -m strategy.swing.pit_universe constituents` and "
                 "`prices` first (W07-0002).")
    spells = P.read_membership(membership)
    window_start = dt.date.fromisoformat(a.window_start)
    window_end = (dt.date.fromisoformat(a.window_end) if a.window_end
                 else dt.date.today())

    pairs, plan = build_plan(spells, out, a.sample, a.dates, a.seed,
                             window_start, window_end)
    for line in cost_lines(plan):
        print(line)
    if not a.confirm:
        print("\nstopped: pass --confirm to actually pull from Alpaca "
             "(PROGRAM_INDEX SS1: priced before pulled).")
        return 1

    key_id, secret = api_keys()
    fetch = http_fetch_factory(key_id, secret)
    try:
        obs, invalid_symbols = run_pairs(fetch, pairs)
    except RuntimeError as e:
        print(f"STOPPED: {scrub(str(e), key_id, secret)}", file=sys.stderr)
        return 2

    by_code: dict[str, list[P.Spell]] = {}
    for s in spells:
        by_code.setdefault(s.code, []).append(s)
    delisted_symbols = {c for c, ss in by_code.items() if any(s.is_delisted for s in ss)}

    write_obs_csv(out / "alpaca_coverage_obs.csv", obs)
    report = build_report(obs, delisted_symbols, plan, invalid_symbols)
    (out / "alpaca_coverage_report.txt").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"written to {out / 'alpaca_coverage_report.txt'} and "
         f"{out / 'alpaca_coverage_obs.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
