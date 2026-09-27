#!/usr/bin/env python3
"""W07-0012 subitem 5 (part 1 of 2): pull EODHD 1-minute intraday bars for the
swing point-in-time universe and extract SWING-v0's three registered entry
buckets (`docs/research/REGISTERED_swing_v0.md` S2.3: `open` 09:30, `midday`
11:30, `close` 15:30 ET) for every (symbol, date) that was both a point-in-time
member (`reversal_v0.load_universe`) and has an EOD close on file
(`pit_universe.py`'s own `eod/<code>.csv`) -- the same gating the Alpaca
coverage probe used, so this pulls exactly what the fill engine (part 2, not
yet built) will actually consume, not a symbol's whole trading history.

    $env:EODHD_API_KEY = op read "op://Trading/EODHD/api-token"
    python -m strategy.swing.intraday_pull --confirm
    python -m strategy.swing.intraday_pull --self-test

WHY THIS EXISTS, AND WHY NOW
------------------------------
The Alpaca coverage probe (`alpaca_coverage_probe.py`, subitem 2/3) measured
free IEX-only bars as 100% MISSING for 2016-2019 and ~80-90% hit/backfill from
2020 -- a material gap against the swing window's 2016-05-10 start. Ben
approved the EODHD "EOD + Intraday -- All World Extended" upgrade on that
finding (subitem 4, 2026-09-25) and has now upgraded the plan (same account,
same `EODHD_API_KEY` already used for daily EOD in `pit_universe.py`). This is
the pull that upgrade was for.

WHY CHUNKED, NOT ONE REQUEST PER (SYMBOL, DATE)
--------------------------------------------------
The Alpaca probe spent one request per (symbol, date) pair because it only
needed a 40x20 SAMPLE. Pulling the full ~900-symbol, ~10-year universe that
way would be roughly 900 x 2,600 = 2.3M requests. EODHD's intraday endpoint
takes a `from`/`to` window and returns every 1-minute bar in it in one call,
so this pulls `MAX_CHUNK_TRADING_DAYS` (default 60, chosen with margin under
the ~120-calendar-day per-request cap `w07_0012_intraday_data_options_20260925.md`
inferred from EODHD's docs, not confirmed) trading days at a time -- one call
covers ~60 symbol-days instead of 60 separate calls. The options doc's
~27,000-call estimate assumed a similar chunking ratio.

DISCOVER THE REAL PER-REQUEST CAP, DO NOT ASSUME IT
------------------------------------------------------
If EODHD's real window cap is smaller than assumed, a chunk silently comes
back covering only part of the requested range -- the bars are there for some
dates and absent for others with no error raised. `stage_pull` checks this
directly: for every date in a chunk that has an EOD close on file (so the
market was open and the name traded) but returns literally zero bars anywhere
in the chunk's response, that date is logged to `intraday_chunk_gaps.csv`
rather than silently recorded as a real MISSING bucket -- a systematic gap at
the chunk boundary is a discovered cap, not a coverage finding, and the two
must not be conflated (`w07_0012_intraday_data_options_20260925.md` caveat).

WHAT "HIT" / "BACKFILL" / "MISSING" MEAN HERE
------------------------------------------------
Same definitions the Alpaca probe used and the same tolerance (walking
backward from the bucket time so a live order's own rule is what prices the
fill, never look-ahead): HIT (bar within `TOLERANCE_MIN` minutes of the
bucket), BACKFILL (nearest at-or-before bar exists but is further back),
MISSING (no bar at or before the bucket anywhere in the chunk's response for
that date).

RESUMABLE, ONE FILE PER SYMBOL
----------------------------------
`intraday/<code>.csv` existing already is skipped (matching `pit_universe.py`
stage_prices's own convention) unless `--refresh` -- an interrupted run
continues where it stopped, spending no repeat calls.

PRICED BEFORE PULLED (`PROGRAM_INDEX` S1)
--------------------------------------------
The plan (symbols, chunk count = API calls) is printed and the pull stops
without `--confirm`.

NO REPO IMPORTS BEYOND THE PACKAGE ITSELF
---------------------------------------------
Same convention as the rest of `strategy/swing/`: standard library only, plus
`pit_universe` (the EODHD fetch factory, key handling, `Spell`/membership
readers this module already owns) and `reversal_v0` (the point-in-time
universe loader and its guards) -- both siblings in this package, not a
second implementation of either.

THE KEY
-------
Same `EODHD_API_KEY` `pit_universe.py` already uses -- one subscription, one
key, no new vendor. No `--key` flag (a flag puts a key in PowerShell
history). Scrubbed from everything this tool prints.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from zoneinfo import ZoneInfo

from strategy.swing import pit_universe as P
from strategy.swing import reversal_v0 as R

DEFAULT_PIT_DIR = Path("var") / "swing_pit"
INTRADAY_SUBDIR = "intraday"
CHUNK_GAPS_NAME = "intraday_chunk_gaps.csv"
INTERVAL = "1m"
INTRADAY_PACE_S = 0.2   # gentler than pit_universe's 0.05s -- larger payload per call

# 2026-09-27: a real pull took ~1.5 days against a 147.6-minute estimate.
# cost_lines()'s estimate only ever counted this pace's post-call sleep, never
# the real network round-trip nor pit_universe.http_fetch_factory's own
# retry/backoff on HTTP 429/500/502/503/504 (2s, 4s, 8s, 16s -- up to +30s on
# a single call retried 4 times). Any single fetch() call taking longer than
# this threshold almost certainly means that backoff fired at least once, so
# stage_pull uses it to count "probably-throttled" calls without needing
# pit_universe.py itself to report retry counts.
SLOW_CALL_THRESHOLD_S = 5.0

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
TOLERANCE_MIN = 5.0

MAX_CHUNK_TRADING_DAYS = 60   # ~84 calendar days with weekends -- margin under
                              # the ~120-day cap w07_0012_intraday_data_options
                              # _20260925.md inferred (not confirmed) from EODHD's docs
MAX_CHUNK_GAP_DAYS = 30       # start a new chunk after a gap this long -- avoids
                              # spanning a symbol's membership hole in one call

OBS_FIELDS = ["date", "bucket", "target_et", "bar_et", "minutes_back",
             "price", "status"]


# --------------------------------------------------------------------------
# HTTP: EODHD's intraday endpoint via pit_universe's own fetch factory --
# same {API}/{path}?{params} shape, same key, same retry/backoff.
# --------------------------------------------------------------------------

Fetch = Callable[[str, dt.date, dt.date], list[dict]]


def et_session_bounds_utc(first: dt.date, last: dt.date) -> tuple[int, int]:
    start = dt.datetime.combine(first, SESSION_FETCH_START, tzinfo=ET).astimezone(UTC)
    end = dt.datetime.combine(last, SESSION_FETCH_END, tzinfo=ET).astimezone(UTC)
    return int(start.timestamp()), int(end.timestamp())


def intraday_fetch_factory(underlying: P.Fetch, interval: str = INTERVAL) -> Fetch:
    """Wraps pit_universe's own http_fetch_factory result: same key, retries,
    and 401/403/NotFound handling, this module only supplies the intraday
    path and params. A 404 (P.NotFound) means no data in this window --
    returned as [], not an error, same as pit_universe's own price pull."""
    def fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
        unix_from, unix_to = et_session_bounds_utc(first, last)
        try:
            bars = P.records(underlying(f"intraday/{P.eod_symbol(code)}", {
                "interval": interval, "from": unix_from, "to": unix_to,
                "fmt": "json"}))
        except P.NotFound:
            return []
        return bars
    return fetch


# --------------------------------------------------------------------------
# eligible dates for a code: point-in-time member AND has an EOD close --
# same gating alpaca_coverage_probe.py's member_dates_with_eod used.
# --------------------------------------------------------------------------

def eligible_dates(spells_for_code: list[P.Spell],
                   eod_dates: Iterable) -> list[dt.date]:
    return sorted(d for d in eod_dates if any(s.covers(d) for s in spells_for_code))


def chunk_dates(dates: list[dt.date], max_days: int = MAX_CHUNK_TRADING_DAYS,
                max_gap_days: int = MAX_CHUNK_GAP_DAYS) -> list[list[dt.date]]:
    """Splits sorted dates into runs of at most `max_days`, starting a new
    chunk early if consecutive dates are more than `max_gap_days` apart (a
    hole in the symbol's own membership or EOD coverage) -- keeps each
    request's from/to span tight rather than covering dead time."""
    chunks: list[list[dt.date]] = []
    cur: list[dt.date] = []
    for d in dates:
        if cur and (len(cur) >= max_days or (d - cur[-1]).days > max_gap_days):
            chunks.append(cur)
            cur = []
        cur.append(d)
    if cur:
        chunks.append(cur)
    return chunks


# --------------------------------------------------------------------------
# bar -> ET, and the HIT/BACKFILL/MISSING classification (same rule the
# Alpaca probe used: walk backward from the bucket, no look-ahead)
# --------------------------------------------------------------------------

def bar_et_time(bar: dict) -> dt.datetime | None:
    ts = bar.get("timestamp")
    if ts is None:
        return None
    try:
        return dt.datetime.fromtimestamp(int(ts), tz=UTC).astimezone(ET)
    except (TypeError, ValueError, OSError):
        return None


@dataclass(frozen=True)
class Observation:
    date: dt.date
    bucket: str
    target_et: str
    bar_et: str | None
    minutes_back: float | None
    price: float | None
    status: str   # HIT / BACKFILL / MISSING

    def row(self) -> list:
        f = lambda v: "" if v is None else v
        return [self.date.isoformat(), self.bucket, self.target_et, f(self.bar_et),
                f(round(self.minutes_back, 2) if self.minutes_back is not None else None),
                f(round(self.price, 4) if self.price is not None else None),
                self.status]


def evaluate_day(day: dt.date, bars_by_et_date: dict) -> list[Observation]:
    """`bars_by_et_date` is this day's own slice of a chunk's bars (already
    filtered to `day`), each as (et_datetime, price), sorted."""
    parsed = bars_by_et_date.get(day, [])
    out = []
    for bucket, btime in BUCKETS:
        target = dt.datetime.combine(day, btime, tzinfo=ET)
        candidates = [(t, px) for t, px in parsed if t <= target]
        if not candidates:
            out.append(Observation(day, bucket, btime.isoformat(), None, None,
                                   None, "MISSING"))
            continue
        t, px = candidates[-1]
        minutes_back = (target - t).total_seconds() / 60.0
        status = "HIT" if minutes_back <= TOLERANCE_MIN else "BACKFILL"
        out.append(Observation(day, bucket, btime.isoformat(), t.isoformat(),
                               minutes_back, px, status))
    return out


def group_bars_by_et_date(bars: list[dict]) -> dict:
    out: dict = {}
    for b in bars:
        t = bar_et_time(b)
        if t is None:
            continue
        try:
            px = float(b["close"])
        except (TypeError, ValueError, KeyError):
            continue
        out.setdefault(t.date(), []).append((t, px))
    for d in out:
        out[d].sort(key=lambda tp: tp[0])
    return out


# --------------------------------------------------------------------------
# the pull
# --------------------------------------------------------------------------

def build_plan(spells: list[P.Spell], out_dir: Path,
               refresh: bool = False) -> tuple[dict, dict]:
    """code -> list[list[date]] (chunks to pull) for every code not already
    covered by an existing intraday/<code>.csv (unless refresh), plus a plan
    summary dict for cost_lines. All-standard-library, no network."""
    by_code: dict[str, list[P.Spell]] = {}
    for s in spells:
        by_code.setdefault(s.code, []).append(s)
    codes = sorted(by_code)
    eod_dir = out_dir / "eod"
    prices = R.load_prices(codes, eod_dir)
    intraday_dir = out_dir / INTRADAY_SUBDIR

    plan: dict[str, list[list[dt.date]]] = {}
    n_skipped = 0
    for code in codes:
        out_path = intraday_dir / f"{P.file_stem(code)}.csv"
        if out_path.exists() and not refresh:
            n_skipped += 1
            continue
        series = prices.get(code)
        if not series:
            continue
        dates = eligible_dates(by_code[code], series.keys())
        if not dates:
            continue
        chunks = chunk_dates(dates)
        if chunks:
            plan[code] = chunks
    n_calls = sum(len(v) for v in plan.values())
    n_symbol_days = sum(len(c) for chunks in plan.values() for c in chunks)
    summary = {
        "codes_total": len(codes),
        "codes_skipped_existing": n_skipped,
        "codes_to_pull": len(plan),
        "api_calls": n_calls,
        "symbol_days": n_symbol_days,
    }
    return plan, summary


def cost_lines(summary: dict, pace_s: float = INTRADAY_PACE_S) -> list[str]:
    n = summary["api_calls"]
    secs = n * pace_s
    return [
        f"plan: {summary['codes_to_pull']} symbols to pull "
        f"({summary['codes_skipped_existing']} already have a file, skipped) "
        f"out of {summary['codes_total']} in the point-in-time universe",
        f"{summary['symbol_days']} symbol-days covered across {n} chunked "
        f"API calls (up to {MAX_CHUNK_TRADING_DAYS} trading days per call)",
        f"estimated wall clock at {pace_s}s/request: {secs / 60:.1f} minutes "
        "-- a best-case FLOOR: excludes the real network round-trip per call "
        "and any rate-limit backoff (2026-09-27: a real run took ~1.5 days "
        "against this estimate's 147.6 minutes; see the timestamped progress "
        "lines and slow-call count once running for the real pace)",
        "cost: counted against your EODHD plan's daily call allowance, not "
        "billed per call beyond the subscription "
        "(PROGRAM_INDEX S1 -- states the number, not just the dollar figure)",
    ]


def stage_pull(fetch: Fetch, plan: dict, out_dir: Path,
              log: Callable[[str], None] = print,
              slow_threshold_s: float = SLOW_CALL_THRESHOLD_S) -> dict:
    """Writes each symbol's intraday/<code>.csv as soon as that symbol's own
    chunks are done (already resumable -- an interrupted run's completed
    symbols are skipped by `build_plan` next time). The chunk-gaps log is
    now held to the SAME discipline: earlier versions of this function
    buffered every gap row in memory and wrote `intraday_chunk_gaps.csv`
    only after the whole plan finished, so ANY exception mid-run (a network
    error, an HTTP error from `fetch` -- see `main()`'s handling of a 402
    quota wall below) silently discarded every gap already found, even
    after tens of thousands of real API calls had already paid for that
    diagnosis. The gaps file is opened once up front (appending to a prior
    run's file rather than overwriting it, so gap history accumulates
    across resumed runs) and each row is flushed as it is found.

    2026-09-27: also times every `fetch()` call. `cost_lines()`'s estimate
    only ever counted `INTRADAY_PACE_S`'s post-call sleep, never the real
    network round-trip nor `pit_universe.http_fetch_factory`'s own
    retry/backoff on a throttled (HTTP 429) or transient (5xx) response -- a
    real run took ~1.5 days against a 147.6-minute estimate and there was no
    way to tell why after the fact. Any single call slower than
    `slow_threshold_s` almost certainly means that backoff fired, so this
    counts those calls and reports a running average pace and elapsed wall
    clock, so a slow run is diagnosable WHILE it happens instead of only
    after it crashes."""
    intraday_dir = out_dir / INTRADAY_SUBDIR
    intraday_dir.mkdir(parents=True, exist_ok=True)
    gaps_path = out_dir / CHUNK_GAPS_NAME
    gaps_is_new = not gaps_path.exists()
    stats = {"codes_pulled": 0, "api_calls": 0, "chunk_gaps": 0,
             "fetch_seconds_total": 0.0, "slow_calls": 0, "slowest_call_s": 0.0}
    run_started = time.monotonic()
    codes = sorted(plan)
    log(f"  starting at {dt.datetime.now().strftime('%H:%M:%S')}, "
       f"{len(codes)} symbols to pull")
    with gaps_path.open("a", newline="", encoding="utf-8") as gaps_f:
        gaps_w = csv.writer(gaps_f)
        if gaps_is_new:
            gaps_w.writerow(["code", "date", "chunk_from", "chunk_to"])
            gaps_f.flush()
        for i, code in enumerate(codes, 1):
            obs: list[Observation] = []
            for chunk in plan[code]:
                first, last = chunk[0], chunk[-1]
                call_started = time.monotonic()
                bars = fetch(code, first, last)
                call_s = time.monotonic() - call_started
                stats["api_calls"] += 1
                stats["fetch_seconds_total"] += call_s
                if call_s > slow_threshold_s:
                    stats["slow_calls"] += 1
                    stats["slowest_call_s"] = max(stats["slowest_call_s"], call_s)
                by_date = group_bars_by_et_date(bars)
                for day in chunk:
                    if day not in by_date:
                        gaps_w.writerow([code, day.isoformat(), first.isoformat(),
                                        last.isoformat()])
                        gaps_f.flush()
                        stats["chunk_gaps"] += 1
                    obs.extend(evaluate_day(day, by_date))
            path = intraday_dir / f"{P.file_stem(code)}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(OBS_FIELDS)
                for o in obs:
                    w.writerow(o.row())
            stats["codes_pulled"] += 1
            if i % 20 == 0:
                elapsed_s = time.monotonic() - run_started
                avg_s = stats["fetch_seconds_total"] / stats["api_calls"]
                log(f"  [{dt.datetime.now().strftime('%H:%M:%S')}, "
                   f"{elapsed_s / 60:.1f} min elapsed] {i}/{len(codes)} symbols "
                   f"pulled ({stats['api_calls']} API calls so far, "
                   f"{avg_s:.2f}s/call avg, {stats['slow_calls']} probably-"
                   f"throttled (>{slow_threshold_s:.0f}s), "
                   f"{stats['chunk_gaps']} chunk gaps flagged)")
    if stats["api_calls"]:
        avg_s = stats["fetch_seconds_total"] / stats["api_calls"]
        pace_line = (f"  average pace this run: {avg_s:.2f}s/call actual vs "
                    f"{INTRADAY_PACE_S}s/call estimated")
        if stats["slow_calls"]:
            pace_line += (f" ({stats['slow_calls']} calls over "
                          f"{slow_threshold_s:.0f}s, likely rate-limit "
                          f"backoff -- slowest was "
                          f"{stats['slowest_call_s']:.1f}s)")
        else:
            pace_line += " (no probably-throttled calls)"
        log(pace_line)
    if stats["chunk_gaps"]:
        log(f"  {stats['chunk_gaps']} chunk gap(s) this run, written "
           f"as they were found to {gaps_path} -- a date with an EOD close "
           "on file that came back with zero intraday bars anywhere in its "
           "chunk's response. A few, scattered, look like real no-print "
           "days; many clustered at the same offset from a chunk's start "
           "suggests the real per-request window cap is smaller than the "
           f"{MAX_CHUNK_TRADING_DAYS}-trading-day assumption -- re-check "
           "before trusting the fill engine's MISSING counts (see "
           "`probe_window` / `--probe CODE` for a one-call direct "
           "measurement of the real cap, cheaper than reading this file's "
           "pattern).")
    return stats


def probe_window(fetch: Fetch, code: str, lookback_days: int = 3650) -> dict:
    """Issues ONE request across a wide window (default ~10 years) and
    reports the actual span of bars EODHD returns for `code` -- measures the
    real per-request window cap directly, with a single API call, instead
    of inferring it destructively from however many chunk-gap rows a full
    pull happens to produce. Run this BEFORE resuming a large pull whenever
    the per-symbol-day chunk-gap rate looks high (see the module docstring
    and `stage_pull`'s own log line)."""
    today = dt.date.today()
    first = today - dt.timedelta(days=lookback_days)
    bars = fetch(code, first, today)
    if not bars:
        return {"code": code, "requested_from": first.isoformat(),
                "requested_to": today.isoformat(), "bars": 0,
                "actual_first": None, "actual_last": None,
                "actual_calendar_days": None}
    by_date = group_bars_by_et_date(bars)
    dates = sorted(by_date)
    return {
        "code": code, "requested_from": first.isoformat(),
        "requested_to": today.isoformat(), "bars": len(bars),
        "actual_first": dates[0].isoformat(), "actual_last": dates[-1].isoformat(),
        "actual_calendar_days": (dates[-1] - dates[0]).days,
    }


def format_probe(result: dict) -> str:
    if result["bars"] == 0:
        return (f"probe {result['code']}: requested {result['requested_from']} "
               f"to {result['requested_to']}, got 0 bars back -- inconclusive "
               "(check the symbol is a real, currently-covered EODHD code).")
    return (
        f"probe {result['code']}: requested {result['requested_from']} to "
        f"{result['requested_to']} ({lookback_calendar_days(result)} calendar "
        f"days) in ONE call -- got {result['bars']} bars back, actually "
        f"spanning {result['actual_first']} to {result['actual_last']} "
        f"({result['actual_calendar_days']} calendar days).\n"
        f"If the actual span is much shorter than the requested one, THAT "
        f"gap is EODHD's real per-request window cap -- compare it against "
        f"the {MAX_CHUNK_TRADING_DAYS}-trading-day (~{MAX_CHUNK_TRADING_DAYS * 7 // 5} "
        "calendar day) assumption `chunk_dates` uses and shrink "
        "MAX_CHUNK_TRADING_DAYS if the real cap is smaller.")


def lookback_calendar_days(result: dict) -> int:
    a = dt.date.fromisoformat(result["requested_from"])
    b = dt.date.fromisoformat(result["requested_to"])
    return (b - a).days


# --------------------------------------------------------------------------
# self-test (offline, synthetic data and a fake fetch -- no network, no key)
# --------------------------------------------------------------------------

def self_test() -> list[str]:
    import tempfile

    spells = [
        P.Spell("sp500", "GOOD", "Still Here Inc", dt.date(2020, 1, 1), None,
               True, False),
    ]
    day1 = dt.date(2020, 6, 15)   # EDT
    day2 = dt.date(2020, 6, 16)

    def bar(day: dt.date, hhmm_utc: str, close: float) -> dict:
        d = dt.datetime.combine(day, dt.time.fromisoformat(hhmm_utc), tzinfo=UTC)
        return {"timestamp": int(d.timestamp()), "close": close}

    # day1: an exact-open bar and a stale-close bar (BACKFILL); day2: nothing
    # at all (a chunk gap OR a genuine no-print day -- self-test exercises
    # the gap-flagging path, since day2 has an EOD close but zero bars).
    fake_bars = [bar(day1, "13:30", 10.0), bar(day1, "15:29", 10.5)]

    def fake_fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
        assert code == "GOOD"
        assert first == day1 and last == day2, (first, last)
        return fake_bars   # nothing for day2 -- a manufactured chunk gap

    with tempfile.TemporaryDirectory() as t:
        out = Path(t)
        eod_dir = out / "eod"
        eod_dir.mkdir(parents=True)
        with (eod_dir / "GOOD.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            for d, px in [(day1, 10.4), (day2, 10.6)]:
                w.writerow({"date": d.isoformat(), "open": px, "high": px,
                           "low": px, "close": px, "adjusted_close": px,
                           "volume": 1000})

        plan, summary = build_plan(spells, out)
        assert summary["codes_to_pull"] == 1, summary
        assert plan["GOOD"] == [[day1, day2]], plan   # one chunk, both dates
        assert summary["api_calls"] == 1, summary
        assert summary["symbol_days"] == 2, summary

        stats = stage_pull(fake_fetch, plan, out, log=lambda m: None)
        assert stats["codes_pulled"] == 1 and stats["api_calls"] == 1, stats
        assert stats["chunk_gaps"] == 1, stats   # day2 flagged

        rows = list(csv.DictReader((out / "intraday" / "GOOD.csv").open(
            newline="", encoding="utf-8")))
        assert len(rows) == 6, len(rows)   # 2 days x 3 buckets
        by_key = {(r["date"], r["bucket"]): r for r in rows}
        assert by_key[(day1.isoformat(), "open")]["status"] == "HIT"
        assert by_key[(day1.isoformat(), "midday")]["status"] == "HIT"
        assert by_key[(day1.isoformat(), "close")]["status"] == "BACKFILL"
        assert by_key[(day2.isoformat(), "open")]["status"] == "MISSING"

        gaps_path = out / CHUNK_GAPS_NAME
        assert gaps_path.exists()
        gap_rows = list(csv.DictReader(gaps_path.open(newline="", encoding="utf-8")))
        assert len(gap_rows) == 1 and gap_rows[0]["date"] == day2.isoformat(), gap_rows

        # 2026-09-27: per-call timing -- a normal (fast) fetch never counts
        # as "probably-throttled"
        assert stats["fetch_seconds_total"] >= 0.0, stats
        assert stats["slow_calls"] == 0, stats

        # a call slower than slow_threshold_s IS counted -- this is how a
        # real run's rate-limit backoff (invisible from outside fetch(), see
        # pit_universe.http_fetch_factory's own retry loop) shows up without
        # pit_universe.py having to report retry counts itself
        def slow_fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
            time.sleep(0.02)
            return fake_bars

        with tempfile.TemporaryDirectory() as t2:
            out2 = Path(t2)
            eod2 = out2 / "eod"
            eod2.mkdir(parents=True)
            with (eod2 / "GOOD.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
                w.writeheader()
                for d, px in [(day1, 10.4), (day2, 10.6)]:
                    w.writerow({"date": d.isoformat(), "open": px, "high": px,
                               "low": px, "close": px, "adjusted_close": px,
                               "volume": 1000})
            plan_slow, _ = build_plan(spells, out2)
            slow_stats = stage_pull(slow_fetch, plan_slow, out2,
                                    log=lambda m: None, slow_threshold_s=0.01)
            assert slow_stats["slow_calls"] == 1, slow_stats
            assert slow_stats["slowest_call_s"] >= 0.02, slow_stats
            assert slow_stats["fetch_seconds_total"] >= 0.02, slow_stats

        # resumability: a second build_plan (no --refresh) must skip GOOD
        plan2, summary2 = build_plan(spells, out)
        assert summary2["codes_to_pull"] == 0, summary2
        assert summary2["codes_skipped_existing"] == 1, summary2

        # crash-safety: a gap flagged on an EARLIER symbol in the same
        # stage_pull call must already be on disk even if a LATER symbol's
        # fetch raises mid-run (2026-09-27: a real run lost 136k+ flagged
        # gaps this way when EODHD returned HTTP 402 partway through --
        # gaps must be written as found, not buffered until the whole plan
        # finishes). Two codes: BADCODE gaps on day2 like GOOD did, then
        # CRASHCODE's own fetch raises.
        bad_spell = P.Spell("sp500", "BADCODE", "Bad Co", dt.date(2020, 1, 1),
                            None, True, False)
        crash_spell = P.Spell("sp500", "CRASHCODE", "Crash Co", dt.date(2020, 1, 1),
                              None, True, False)
        with (eod_dir / "BADCODE.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            for d, px in [(day1, 20.0), (day2, 20.1)]:
                w.writerow({"date": d.isoformat(), "open": px, "high": px,
                           "low": px, "close": px, "adjusted_close": px,
                           "volume": 1000})
        with (eod_dir / "CRASHCODE.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=P.PRICE_FIELDS)
            w.writeheader()
            for d, px in [(day1, 30.0), (day2, 30.1)]:
                w.writerow({"date": d.isoformat(), "open": px, "high": px,
                           "low": px, "close": px, "adjusted_close": px,
                           "volume": 1000})

        def crashing_fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
            if code == "BADCODE":
                return fake_bars   # same manufactured gap on day2
            raise RuntimeError("HTTP 402 on intraday/CRASHCODE.US")

        plan3, _ = build_plan([bad_spell, crash_spell], out)
        assert set(plan3) == {"BADCODE", "CRASHCODE"}, plan3
        try:
            stage_pull(crashing_fetch, plan3, out, log=lambda m: None)
        except RuntimeError:
            pass
        else:
            raise AssertionError("stage_pull did not propagate CRASHCODE's "
                                 "fetch error")
        gap_rows_after_crash = list(csv.DictReader(
            gaps_path.open(newline="", encoding="utf-8")))
        # the original GOOD/day2 gap plus BADCODE/day2, both preserved --
        # appended to, never overwritten -- despite CRASHCODE crashing after
        assert len(gap_rows_after_crash) == 2, gap_rows_after_crash
        assert {r["code"] for r in gap_rows_after_crash} == {"GOOD", "BADCODE"}
        # CRASHCODE itself never got an intraday/<code>.csv (crashed before
        # any row was written) -- correctly NOT resumable-skipped next time
        assert not (out / "intraday" / "CRASHCODE.csv").exists()

        # chunking: a long, gappy date list splits on both size and the gap
        many_dates = [dt.date(2016, 1, 4) + dt.timedelta(days=i)
                     for i in range(70)]  # 70 > MAX_CHUNK_TRADING_DAYS (60)
        many_dates.append(many_dates[-1] + dt.timedelta(days=90))  # a big gap
        chunks = chunk_dates(many_dates)
        assert len(chunks) == 3, len(chunks)
        assert len(chunks[0]) == 60 and len(chunks[1]) == 10, [len(c) for c in chunks]

        # probe_window: one call, reports the ACTUAL span even when it is
        # narrower than requested (the real per-request cap discovery path)
        def narrow_fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
            assert code == "NARROW"
            # only 3 calendar days of bars come back, however wide the ask
            return [bar(first, "13:30", 1.0),
                   bar(first + dt.timedelta(days=1), "13:30", 1.1),
                   bar(first + dt.timedelta(days=2), "13:30", 1.2)]

        probe = probe_window(narrow_fetch, "NARROW", lookback_days=3650)
        assert probe["bars"] == 3, probe
        assert probe["actual_calendar_days"] == 2, probe   # first to first+2
        probe_text = format_probe(probe)
        # reports the ACTUAL span (2 days), not just the requested one
        # (3650 days) -- both numbers appear, but distinctly
        assert "2 calendar days" in probe_text, probe_text
        assert probe["actual_first"] in probe_text

        def empty_fetch(code: str, first: dt.date, last: dt.date) -> list[dict]:
            return []

        empty_probe = probe_window(empty_fetch, "EMPTY")
        assert empty_probe["bars"] == 0 and empty_probe["actual_first"] is None
        assert "inconclusive" in format_probe(empty_probe)

    return ["self-test passed: eligible-date gating (member AND EOD close), "
           "chunking by both size and gap, HIT/BACKFILL/MISSING classified "
           "correctly, resumability skipped an already-pulled symbol, a "
           "manufactured chunk gap was flagged rather than silently folded "
           "into MISSING, gap rows already found survive a later symbol's "
           "fetch crashing (the 2026-09-27 data-loss bug) rather than being "
           "lost with the whole in-memory buffer, the one-call window "
           "probe reports the real (not requested) span, and per-call "
           "timing correctly leaves a normal-speed run's slow-call count at "
           "zero while flagging a call slower than slow_threshold_s as "
           "probably rate-limit-throttled"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pit-dir", type=Path, default=DEFAULT_PIT_DIR)
    p.add_argument("--refresh", action="store_true",
                  help="re-pull symbols that already have an intraday/<code>.csv")
    p.add_argument("--confirm", action="store_true",
                  help="required to actually pull from EODHD")
    p.add_argument("--probe", metavar="CODE",
                  help="spend ONE real API call fetching a wide window for "
                       "CODE and report the actual span of bars returned -- "
                       "measures EODHD's real per-request window cap "
                       "directly. Does not touch the pull plan or --confirm.")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0

    if a.probe:
        key = P.api_key()
        underlying = P.http_fetch_factory(key, pause=INTRADAY_PACE_S)
        fetch = intraday_fetch_factory(underlying)
        try:
            result = probe_window(fetch, a.probe)
        except (P.Refused, RuntimeError) as e:
            print(f"STOPPED: {P.scrub(str(e), key)}", file=sys.stderr)
            return 2
        print(format_probe(result))
        return 0

    try:
        universe = R.load_universe(a.pit_dir)
    except (R.UniverseGuardRefused, R.HindsightError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2

    plan, summary = build_plan(list(universe.spells), a.pit_dir, refresh=a.refresh)
    for line in cost_lines(summary):
        print(line)
    if not a.confirm:
        print("\nstopped: pass --confirm to actually pull from EODHD "
             "(PROGRAM_INDEX S1: priced before pulled).")
        return 1
    if not plan:
        print("nothing to pull -- every symbol already has an intraday file "
             "(pass --refresh to re-pull).")
        return 0

    key = P.api_key()
    underlying = P.http_fetch_factory(key, pause=INTRADAY_PACE_S)
    fetch = intraday_fetch_factory(underlying)
    try:
        stats = stage_pull(fetch, plan, a.pit_dir)
    except (P.Refused, RuntimeError) as e:
        msg = P.scrub(str(e), key)
        print(f"STOPPED: {msg}", file=sys.stderr)
        if "HTTP 402" in msg:
            print(
                "HTTP 402 (Payment Required) from EODHD almost always means "
                "the plan's daily API call allowance is used up for today -- "
                "not a problem with this specific symbol. Check the usage "
                "page on your EODHD account dashboard for today's quota and "
                "when it resets, then re-run the SAME command once it has: "
                "every symbol that already has an intraday/<code>.csv is "
                "skipped automatically (see 'plan: ... already have a file, "
                "skipped' in the next run's own printed plan), so this "
                "resumes from exactly where it stopped rather than "
                "re-pulling anything.", file=sys.stderr)
        return 2

    avg_s = (stats["fetch_seconds_total"] / stats["api_calls"]
            if stats["api_calls"] else 0.0)
    print(f"\ndone: {stats['codes_pulled']} symbols pulled, "
         f"{stats['api_calls']} API calls ({avg_s:.2f}s/call avg, "
         f"{stats['slow_calls']} probably-throttled), "
         f"{stats['chunk_gaps']} chunk gaps "
         f"flagged -- see {a.pit_dir / INTRADAY_SUBDIR} and "
         f"{a.pit_dir / CHUNK_GAPS_NAME if stats['chunk_gaps'] else '(no gaps file written)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
