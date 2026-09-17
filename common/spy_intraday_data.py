#!/usr/bin/env python3
"""Bars for the market-intraday-momentum study (H-S1 / H-S2), from IB.

    .venv\\Scripts\\python.exe -m common.spy_intraday_data --probe
    .venv\\Scripts\\python.exe -m common.spy_intraday_data --pull --bars "30 mins" --symbols SPY QQQ IWM
    .venv\\Scripts\\python.exe -m common.spy_intraday_data --pull --bars "5 mins"  --symbols SPY

Registration: claude/spy_intraday_spec_20260917.md. Read section 4 before
changing anything here; three of its data traps are the reason this module
exists rather than a dozen lines of reqHistoricalData.

WHY A PROBE COMES FIRST, AND WHY THE WINDOW IS NOT ASSUMED
-----------------------------------------------------------
The spec registers 2015-01-01 -> present, about 2,900 sessions. Nothing in
this project has ever measured how far back IB actually returns 30-minute or
5-minute bars, and every other channel has been checked and cannot reach that
window:

    Alpha Vantage intraday    premium on the current key (re-confirmed 2026-09-17)
    tvremix (TradingView)     5,000 bars max -- 30m reaches 2025-03-05 only
    TradingView desktop MCP   500 bars per call
    IBKR MCP get_price_history  errors; other IBKR MCP calls on the same login work
    Databento / any public HTTP no egress from the analysis environment

So IB through this module is the only channel that can reach the registered
window, and whether it does is a MEASUREMENT, not an assumption. --probe walks
a year ladder per bar size and reports the earliest date that returns bars. If
the answer is later than 2015-01-01 the window is re-registered before any P/L
is computed -- section 12 step 1 stops there on purpose.

WHICH PRICES, AND WHY THESE BAR SIZES
--------------------------------------
With useRTH=True the 30-minute RTH grid is exactly the thirteen bars
09:30, 10:00, ... 15:30, and the four prices the rule needs are bar CLOSES:

    prior 16:00 close   close of the PRIOR session's 15:30 bar
    10:00               close of the 09:30 bar
    15:30               close of the 15:00 bar
    16:00               close of the 15:30 bar

A bar is labelled by the START of its interval, so reading the OPEN of the
10:00 bar for the 10:00 price would be the same number by a different route on
a liquid ETF and a different number on a gap. Closes, throughout.

5-minute bars are needed twice and are not optional:
    sigma1            realised vol of 09:30-10:00 -- six 5-minute returns
    boundary surface  r1 at 10:05 / 10:15, entry at 15:25 / 15:35 (spec 8.5)

1-minute is the sigma1 the spec would prefer. IB is believed to hold roughly
six months of it, which would cover about 2% of the window, so 5-minute is
registered as the proxy and the overlap where BOTH exist is the agreement
check. --probe measures all three so that choice rests on a number.

ADJUSTMENT -- THE TRAP THAT COST VW9 ITS HEADLINE
--------------------------------------------------
whatToShow="TRADES", always, for every symbol and every bar size. IB returns
those split-adjusted and NOT dividend-adjusted, so the series is CONSISTENTLY
unadjusted for dividends -- which is what spec section 4 requires, and it is
also the right choice rather than merely a permitted one:

    r1 spans the overnight boundary. On an ex-dividend morning the price
    really does open lower by the dividend, and the strategy holds nothing
    overnight, so it never receives the dividend. Unadjusted prices are what
    a live trader would have seen at 10:00. A dividend-ADJUSTED series would
    remove a gap that actually happened.

SPY, QQQ and IWM have had no split in the registered window, so split
adjustment cannot move anything here either. The failure mode the spec warns
about is MIXING the two, which one whatToShow for the whole pull makes
impossible. SOURCE.txt records it beside the bars so a later reader cannot
mistake which series this is.

WHAT AN EMPTY RESPONSE MEANS
-----------------------------
IB signals pacing by returning an EMPTY LIST rather than an error (section 5,
and common/history_probe.py was written for the same reason). An empty
response is therefore ambiguous: no data at that date, or throttled. Both the
probe and the puller re-ask a known-good control window before believing an
empty, and record the ambiguity when they cannot tell.

RESUMABLE BY CONSTRUCTION
--------------------------
One CSV per symbol per chunk, skipped if present. A 5-minute pull of the full
window is hours of paced requests; it must survive being interrupted, and
re-running it must be free. --pull prints the request count and the wall-clock
estimate and refuses to start without --confirm, for the same reason
common/databento_fetch.py prices a query before it spends: a tool that can
cost hours states the number first.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, util
except ImportError:  # pragma: no cover
    sys.exit("ib_async not installed.  pip install ib_async pandas")

from brokers.ibkr.trader import LIVE_PORTS, PAPER_PORTS
from common.report_io import emit

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

CACHE_ROOT = Path("bar_cache_spy")
WHAT_TO_SHOW = "TRADES"
USE_RTH = True

# MEASURED, 2026-09-17, by --probe-duration on this account. NOT the values in
# IB's documented table, which are what the first version of this module used:
#
#     bar size     documented     measured     what it changes
#     30 mins      1 M            1 Y          172 chunks -> 26
#     5 mins       1 W            3 M          713 chunks -> 104
#     1 min        1 D            1 M          about ten hours -> about one
#
# The 1-minute row is the one that matters. At "1 D" a full-window 1-minute
# pull is roughly ten hours for one symbol, which is why the spec registered a
# 5-minute PROXY for sigma1. At "1 M" it is about an hour, so sigma1 is
# computed from real 1-minute bars and the proxy is not needed at all.
#
# None of the measured responses were truncated: "1 Y" at 30 mins returned
# 12.95 bars per session over 251 sessions, "1 M" at 1 min returned 390 bars
# per session over 21. They were measured on a RECENT window, and IB has been
# known to answer a too-long request for OLD data with a short window rather
# than an error -- so every chunk's returned span is checked against the step
# it was supposed to cover, and the chunks overlap regardless.
MAX_DURATION = {"30 mins": "1 Y", "5 mins": "3 M", "1 min": "1 M"}

# The STEP is deliberately shorter than the duration, so consecutive chunks
# OVERLAP. IB's "1 M" is a calendar month -- 28 to 31 days -- so a 30-day step
# leaves a one-day hole in every 31-day month, and a hole in a bar cache does
# not announce itself: it reappears later as a session silently missing from
# the study. Overlapping costs a few more requests and duplicate rows, which
# de-duplicate on assembly. Coverage is still MEASURED there rather than
# assumed, because a step that is right in theory has been wrong before.
CHUNK_DAYS = {"30 mins": 330, "5 mins": 80, "1 min": 25}

# WAS {"1 min": 3}, on the spec's belief that IB holds about six months of
# 1-minute history. The probe of 2026-09-17 answered for 2023, 2024, 2025 and
# 2026 -- every year the cap allowed -- so the belief is wrong and the cap was
# measuring itself. Removed: 1-minute now walks the same ladder as the others,
# because whether sigma1 can be computed from REAL 1-minute bars rather than a
# 5-minute proxy is the difference between amendment E being needed and not.
PROBE_YEARS_BACK: dict[str, int] = {}

# IB rejects a duration longer than it allows for a given bar size, and the
# documented table is not the same on every account or every era. This is the
# ladder the duration probe walks. What it finds sets the CHUNK SIZE, which is
# the whole cost of the pull: 1-minute bars at "1 D" per request is about ten
# hours for one symbol, and at "1 W" it is two.
DURATION_LADDER = {
    "30 mins": ("1 M", "2 M", "3 M", "6 M", "1 Y"),
    "5 mins": ("1 W", "2 W", "1 M", "2 M", "3 M"),
    "1 min": ("1 D", "2 D", "1 W", "2 W", "1 M"),
}

REQUEST_INTERVAL_S = 12.5      # common/backtest.py's pacing; IB's cap is account-wide
RETRY_BACKOFF_S = 20.0
EMPTY_RETRIES = 2

BAR_SLUG = {"30 mins": "30min", "5 mins": "5min", "1 min": "1min"}

# The probe's control window: recent, liquid, certainly present. If a request
# for a 2008 date comes back empty AND this does too, the empty means paced.
CONTROL_DAYS_AGO = 5


def slug(bars: str) -> str:
    return BAR_SLUG[bars]


def cache_dir(bars: str, symbol: str) -> Path:
    return CACHE_ROOT / slug(bars) / symbol


# Qualified contracts, cached for the life of the process. QUALIFICATION IS
# PACED TOO (section 5), so re-qualifying on every historical request would
# double the load against a cap that is account-wide and shared with the live
# trader -- and IB answers a breached cap with empty lists, which this module
# would then have to spend a further request disambiguating. Qualify once.
_QUALIFIED: dict[str, Stock] = {}


def contract(symbol: str) -> Stock:
    # SPY, QQQ and IWM are ARCA/NASDAQ listed; SMART routing resolves all three
    # and the primaryExchange disambiguates the qualify.
    primary = {"SPY": "ARCA", "QQQ": "NASDAQ", "IWM": "ARCA"}.get(symbol, "NASDAQ")
    return Stock(symbol, "SMART", "USD", primaryExchange=primary)


async def qualified(ib, symbol: str) -> Stock | None:
    if symbol in _QUALIFIED:
        return _QUALIFIED[symbol]
    c = contract(symbol)
    try:
        await ib.qualifyContractsAsync(c)
    except Exception:                                         # noqa: BLE001
        return None
    _QUALIFIED[symbol] = c
    return c


def to_frame(bars) -> pd.DataFrame:
    """IB bars -> a frame indexed by ET timestamps, named ts_et.

    formatDate=2 gives UTC epoch seconds, which is unambiguous in a way the
    string form is not; the conversion to ET happens here, once, and the index
    is NAMED ts_et so that no downstream reader can repeat the MCL mistake of
    reading a UTC column as if it were ET.
    """
    df = util.df(bars)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(columns=str.lower)
    ts = pd.to_datetime(df["date"], utc=True).dt.tz_convert(ET)
    df = df.drop(columns=["date"])
    df.insert(0, "ts_et", ts)
    df = df.set_index("ts_et").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep]


async def request(ib, symbol: str, end_utc: datetime, bars: str,
                  duration: str) -> tuple[pd.DataFrame, str]:
    """One paced historical request. Returns (frame, status).

    status is "ok", "empty" or an error string. An empty frame with status
    "ok" cannot occur -- empty is its own status precisely because IB uses it
    for two different things.
    """
    c = await qualified(ib, symbol)
    if c is None:
        return pd.DataFrame(), f"qualify failed: {symbol}"
    try:
        data = await ib.reqHistoricalDataAsync(
            c, endDateTime=end_utc, durationStr=duration,
            barSizeSetting=bars, whatToShow=WHAT_TO_SHOW,
            useRTH=USE_RTH, formatDate=2)
    except Exception as e:                                    # noqa: BLE001
        return pd.DataFrame(), f"error: {e}"
    if not data:
        return pd.DataFrame(), "empty"
    return to_frame(data), "ok"


async def control_ok(ib, symbol: str, bars: str) -> bool:
    """Is IB answering at all right now? Distinguishes 'no data' from 'paced'."""
    end = datetime.now(UTC) - timedelta(days=CONTROL_DAYS_AGO)
    df, status = await request(ib, symbol, end, bars, MAX_DURATION[bars])
    return status == "ok" and not df.empty


# --------------------------------------------------------------------------
# probe
# --------------------------------------------------------------------------

async def probe(ib, symbol: str, bars: str, years: list[int]) -> list[dict]:
    rows = []
    for y in years:
        # Mid-June: away from both DST transitions and every holiday cluster,
        # so an empty answer is about DEPTH and not about the week chosen.
        end = datetime(y, 6, 15, tzinfo=ET).astimezone(UTC)
        df, status = await request(ib, symbol, end, bars, MAX_DURATION[bars])
        await asyncio.sleep(REQUEST_INTERVAL_S)
        row = {"year": y, "status": status, "bars": len(df)}
        if status == "empty":
            # Ambiguous until the control answers.
            alive = await control_ok(ib, symbol, bars)
            await asyncio.sleep(REQUEST_INTERVAL_S)
            row["status"] = "no data" if alive else "AMBIGUOUS (paced?)"
        elif status == "ok" and not df.empty:
            row["first"] = str(df.index[0])
            row["last"] = str(df.index[-1])
            row["sessions"] = df.index.normalize().nunique()
        rows.append(row)
    return rows


async def probe_duration(ib, symbol: str, bars: str) -> list[dict]:
    """How much can IB actually be asked for in one request, at this bar size?"""
    rows = []
    # A month back, so the window is whole sessions and not a partial today.
    end = datetime.now(UTC) - timedelta(days=30)
    for dur in DURATION_LADDER[bars]:
        df, status = await request(ib, symbol, end, bars, dur)
        await asyncio.sleep(REQUEST_INTERVAL_S)
        row = {"duration": dur, "status": status, "bars": len(df)}
        if status == "ok" and not df.empty:
            row["sessions"] = int(df.index.normalize().nunique())
            row["first"] = str(df.index[0])[:16]
            row["last"] = str(df.index[-1])[:16]
        elif status == "empty":
            alive = await control_ok(ib, symbol, bars)
            await asyncio.sleep(REQUEST_INTERVAL_S)
            row["status"] = "rejected" if alive else "AMBIGUOUS (paced?)"
        rows.append(row)
    return rows


def render_duration(results: dict) -> list[str]:
    L = ["", "MAX DURATION PER REQUEST -- this is the whole cost of the pull",
         ""]
    for bars, rows in results.items():
        L.append(f"{bars}")
        best = None
        for r in rows:
            if r["status"] == "ok":
                best = r["duration"]
                L.append(f"    {r['duration']:<5} OK   {r['bars']:>6} bars  "
                         f"{r.get('sessions', 0):>3} sessions  "
                         f"{r.get('first', '')} -> {r.get('last', '')}")
            else:
                L.append(f"    {r['duration']:<5} {r['status']}")
        L.append(f"    largest that answered: {best or 'NONE'}")
        L.append("")
    L += ["  A LONGER DURATION THAT ANSWERS IS NOT AUTOMATICALLY SAFE.",
          "  Compare the sessions returned against the sessions the window",
          "  contains: IB will sometimes answer a too-long request with a",
          "  TRUNCATED window rather than an error, and a chunk size set from",
          "  that silently leaves holes -- which, for r1, is a wrong number",
          "  rather than a missing one. The pull overlaps its chunks for this",
          "  reason and the assertion pass counts the gaps regardless."]
    return L


def render_probe(results: dict, symbol: str, now: datetime) -> list[str]:
    L = ["IB DEPTH PROBE -- how far back SPY intraday bars actually go", "",
         f"  asked at   {now:%Y-%m-%d %H:%M:%S} ET",
         f"  symbol     {symbol}",
         f"  settings   whatToShow={WHAT_TO_SHOW}  useRTH={USE_RTH}",
         "",
         "  The registered window is 2015-01-01 -> present (spec section 4).",
         "  This measures whether IB can serve it. An EMPTY response from IB",
         "  means either 'no data' or 'you are being paced' -- every empty",
         "  below was re-checked against a recent control window before being",
         "  called one or the other.", ""]
    for bars, rows in results.items():
        L.append(f"{bars}   (max {MAX_DURATION[bars]} per request)")
        for r in rows:
            if r["status"] == "ok":
                L.append(f"    {r['year']}   {r['bars']:>6} bars  "
                         f"{r.get('sessions', 0):>3} sessions  "
                         f"{str(r.get('first', ''))[:16]} -> "
                         f"{str(r.get('last', ''))[:16]}")
            else:
                L.append(f"    {r['year']}   {r['status']}")
        ok = [r["year"] for r in rows if r["status"] == "ok"]
        L.append(f"    earliest year answering: {min(ok) if ok else 'NONE'}")
        L.append("")
    L += ["WHAT TO DO WITH THIS", "",
          "  30 mins reaching 2015 -- H-S1 runs on the registered window and",
          "    the four prices the rule needs are all 30-minute bar closes.",
          "  5 mins NOT reaching 2015 -- sigma1 and the boundary surface are",
          "    limited to the years it does reach. H-S2 is then registered on",
          "    the shorter window, as an amendment, BEFORE it is run.",
          "  1 min reaching only months -- expected. It is the agreement check",
          "    for the 5-minute sigma1 proxy over the overlap, not the source.",
          "  Anything AMBIGUOUS -- pacing, not depth. Re-run that bar size;",
          "    do not read it as an absence."]
    return L


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------

def chunk_ends(start: date, end: date, bars: str) -> list[date]:
    """Chunk boundaries, newest first.

    Walks BACKWARDS from the end so that an interrupted pull has the most
    recent history on disk, which is the part every other check needs first.
    """
    step = CHUNK_DAYS[bars]
    out, cur = [], end
    while cur > start:
        out.append(cur)
        cur = cur - timedelta(days=step)
    return out


def chunk_path(bars: str, symbol: str, end: date) -> Path:
    return cache_dir(bars, symbol) / f"{symbol}_{end:%Y%m%d}.csv"


def write_source(bars: str) -> None:
    """Name the tape beside the bars. Section 1: a report names its tape."""
    d = CACHE_ROOT / slug(bars)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOURCE.txt").write_text(
        f"source        IB reqHistoricalData\n"
        f"whatToShow    {WHAT_TO_SHOW}\n"
        f"useRTH        {USE_RTH}\n"
        f"barSize       {bars}\n"
        f"adjustment    split-adjusted, NOT dividend-adjusted -- consistently\n"
        f"              unadjusted across the whole pull. See the module\n"
        f"              docstring: r1 spans the overnight boundary and the\n"
        f"              strategy never holds overnight, so the as-traded gap\n"
        f"              is the one a live trader would have seen.\n"
        f"timestamps    ET, index named ts_et, bar labelled by interval START\n",
        encoding="utf-8")


async def pull(ib, symbol: str, bars: str, start: date, end: date,
               log) -> dict:
    d = cache_dir(bars, symbol)
    d.mkdir(parents=True, exist_ok=True)
    ends = chunk_ends(start, end, bars)
    stat = {"symbol": symbol, "chunks": len(ends), "fetched": 0, "skipped": 0,
            "empty": 0, "ambiguous": 0, "errors": 0, "rows": 0, "short": 0}
    for i, ce in enumerate(ends, 1):
        p = chunk_path(bars, symbol, ce)
        if p.exists():
            stat["skipped"] += 1
            continue
        end_utc = datetime(ce.year, ce.month, ce.day, tzinfo=ET).astimezone(UTC)
        df, status = pd.DataFrame(), ""
        for attempt in range(EMPTY_RETRIES + 1):
            df, status = await request(ib, symbol, end_utc, bars,
                                       MAX_DURATION[bars])
            await asyncio.sleep(REQUEST_INTERVAL_S)
            if status != "empty":
                break
            alive = await control_ok(ib, symbol, bars)
            await asyncio.sleep(REQUEST_INTERVAL_S)
            if alive:
                break                      # genuinely no data for this chunk
            log(f"    paced at {ce} -- backing off {RETRY_BACKOFF_S}s "
                f"(attempt {attempt + 1})")
            await asyncio.sleep(RETRY_BACKOFF_S)
        if status == "ok" and not df.empty:
            # TRUNCATION GUARD. A chunk is meant to reach back at least as far
            # as the NEXT chunk's end, or the two do not meet and the cache
            # has a hole. A hole is not a NaN for this study -- r1 reads the
            # prior session's close, so it silently computes across the gap.
            span = (ce - df.index[0].date()).days
            if span < CHUNK_DAYS[bars]:
                stat["short"] += 1
                log(f"    SHORT CHUNK at {ce}: reached back {span} days, "
                    f"step is {CHUNK_DAYS[bars]} -- possible hole")
            df.to_csv(p, encoding="utf-8")
            stat["fetched"] += 1
            stat["rows"] += len(df)
        elif status == "empty":
            stat["empty"] += 1
        elif status.startswith("error") or status.startswith("qualify"):
            stat["errors"] += 1
            log(f"    {ce}  {status}")
        if i % 25 == 0:
            log(f"    {symbol} {bars}: {i}/{len(ends)} chunks, "
                f"{stat['fetched']} fetched, {stat['rows']} rows")
    return stat


def estimate(symbols: list[str], bars: str, start: date, end: date) -> dict:
    ends = chunk_ends(start, end, bars)
    todo = sum(1 for s in symbols for e in ends
               if not chunk_path(bars, s, e).exists())
    return {"chunks_total": len(ends) * len(symbols), "chunks_todo": todo,
            "minutes": round(todo * REQUEST_INTERVAL_S / 60.0, 1)}


# --------------------------------------------------------------------------

async def main_async(args) -> int:
    if args.port in LIVE_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is {LIVE_PORTS[args.port]}. "
                 f"Paper ports are {sorted(PAPER_PORTS)}.")
    if args.port not in PAPER_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is not a known paper port "
                 f"{sorted(PAPER_PORTS)}.")

    if args.duration:
        MAX_DURATION[args.bars] = args.duration
    if args.chunk_days:
        CHUNK_DAYS[args.bars] = args.chunk_days
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    if args.pull:
        est = estimate(args.symbols, args.bars, start, end)
        print(f"{args.bars}: {est['chunks_todo']} of {est['chunks_total']} "
              f"chunks still to fetch across {len(args.symbols)} symbol(s)")
        print(f"estimated wall clock at {REQUEST_INTERVAL_S}s pacing: "
              f"~{est['minutes']} minutes, plus back-off on any paced chunk")
        print("bars already on disk are skipped, so re-running this is free")
        if not args.confirm:
            print("\nnothing fetched. add --confirm to start.")
            return 0

    ib = IB()
    await ib.connectAsync(args.host, args.port, clientId=args.client_id)
    try:
        if args.probe:
            results = {}
            for bars in args.probe_bars:
                floor = args.probe_from
                back = PROBE_YEARS_BACK.get(bars)
                if back is not None:
                    floor = max(floor, date.today().year - back)
                years = list(range(date.today().year, floor - 1, -1))
                results[bars] = await probe(ib, args.symbols[0], bars, years)
            dur_results = {}
            if args.probe_duration:
                for bars in args.duration_bars:
                    dur_results[bars] = await probe_duration(
                        ib, args.symbols[0], bars)
            body = render_probe(results, args.symbols[0], datetime.now(ET))
            if dur_results:
                body += render_duration(dur_results)
            emit("\n".join(body),
                 args.out or "var/reports/spy_intraday_probe.txt",
                 header="common.spy_intraday_data --probe")
            return 0

        write_source(args.bars)
        stats = []
        for s in args.symbols:
            print(f"pulling {s} {args.bars} {start} -> {end}")
            stats.append(await pull(ib, s, args.bars, start, end, print))
    finally:
        ib.disconnect()

    L = [f"SPY INTRADAY PULL -- {args.bars}", "",
         f"  window   {start} -> {end}",
         f"  cache    {CACHE_ROOT / slug(args.bars)}", ""]
    for st in stats:
        L.append(f"  {st['symbol']:<5} {st['fetched']:>4} fetched  "
                 f"{st['skipped']:>4} already on disk  {st['rows']:>8} rows  "
                 f"{st['empty']} empty  {st['errors']} errors  "
                 f"{st['short']} SHORT")
    L += ["", "  An 'empty' chunk is a chunk IB has no data for, confirmed",
          "  against a live control window at the time it was asked. It is",
          "  NOT the same as a chunk that was never requested.",
          "",
          "  A 'SHORT' chunk reached back less far than the step it was meant",
          "  to cover, which is how IB answers a too-long request for old",
          "  data. Any SHORT count above zero means the cache may have holes;",
          "  the assertion pass counts them by name."]
    emit("\n".join(L), args.out or
         f"var/reports/spy_intraday_pull_{slug(args.bars)}.txt",
         header=f"common.spy_intraday_data --pull --bars '{args.bars}'")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--probe", action="store_true",
                   help="measure how far back IB serves each bar size")
    p.add_argument("--probe-from", type=int, default=2004,
                   help="oldest year the ladder reaches back to")
    p.add_argument("--probe-bars", nargs="+",
                   default=["30 mins", "5 mins", "1 min"])
    p.add_argument("--duration-bars", nargs="+",
                   default=["30 mins", "5 mins", "1 min"],
                   help="bar sizes for --probe-duration; independent of "
                        "--probe-bars so the year ladder and the duration "
                        "ladder can be scoped separately")
    p.add_argument("--probe-duration", action="store_true",
                   help="also measure the largest duration IB answers per "
                        "bar size -- this sets the chunk size, and the chunk "
                        "size is the cost of the pull")
    p.add_argument("--pull", action="store_true")
    p.add_argument("--confirm", action="store_true",
                   help="required by --pull; without it only the estimate prints")
    p.add_argument("--bars", default="30 mins",
                   choices=["30 mins", "5 mins", "1 min"])
    p.add_argument("--duration", default=None,
                   help="override the per-request duration with a MEASURED "
                        "one from --probe-duration. Registering the value is "
                        "the point: the chunk size decides the cost and, if "
                        "IB truncates a too-long window, the coverage.")
    p.add_argument("--chunk-days", type=int, default=None,
                   help="step between chunk ends; must be SHORTER than "
                        "--duration so consecutive chunks overlap")
    p.add_argument("--symbols", nargs="+", default=["SPY"])
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=29,
                   help="not the trader's 17 and not history_probe's 23")
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not (args.probe or args.pull):
        sys.exit("pass --probe or --pull")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
