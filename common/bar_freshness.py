#!/usr/bin/env python3
"""Which minute is the trader actually acting on, and how stale is it?

    python -m common.bar_freshness --symbols BNC --seconds 180

THE OBSERVATION THIS EXISTS FOR, Ben 2026-09-09
------------------------------------------------
On BNC, TradingView signalled at 06:21 ET and filled at $5.10; the live trader
filled at 06:23 at $5.22. Two minutes and twelve cents.

One minute of that is expected and is not a defect: the strategy acts on a
CLOSED bar, so a signal formed by the 06:21 bar cannot be acted on until 06:22
at the earliest. TradingView's strategy tester marks the trade at the bar that
produced it; the trader marks it when the order filled. That is a difference in
BOOKKEEPING, not in behaviour.

THE SECOND MINUTE IS THE QUESTION, and there is a specific suspect:

    brokers/ibkr/trader._fetch_bars ends with
        return df.iloc[:-1] if len(df) > 1 else df
    commented "drop the still-forming bar so we only ever act on closed bars".

That is correct IF IB includes the forming minute in its response. If IB
returns only COMPLETED bars -- which it may, and which nothing here has ever
checked -- then the drop throws away a perfectly good closed bar and every
entry in this project's live history is one minute late. On a name moving 12c
in two minutes that is most of the gap.

WHAT IS MEASURED
----------------
The same request the trader makes, repeatedly, recording three things:

    now          the wall clock at the moment of the response
    raw last     the last bar in the response, before any trimming
    acted        what the trader would use, i.e. raw last minus one bar

The decisive comparison is `now` against `raw last`. If the raw response ends
at the minute in progress, the trim is right. If it ends at the last COMPLETED
minute, the trim is costing a minute on every signal.

PACING. This runs alongside a live session and spends the same budget: IB
allows about 60 historical requests per 10 minutes ACROSS ALL CONTRACTS, and
signals the limit by returning empty lists rather than errors. Defaults are
deliberately small -- one symbol, every 15 seconds, for three minutes, which is
12 requests. Raise them and you are taking budget from the trader.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from collections import Counter
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, util
except ImportError:  # pragma: no cover
    sys.exit("ib_async not installed.  pip install ib_async pandas")

from brokers.ibkr.trader import (HISTORY_DURATION, LIVE_PORTS, PAPER_PORTS,
                                 drop_forming_bar, parse_watchlist)
from common.report_io import emit

ET = ZoneInfo("America/New_York")


def classify(now: datetime, raw_last: pd.Timestamp) -> str:
    """Is the last bar of the response the forming minute, or a closed one?

    'forming'  raw last is the minute in progress -> the trader's trim is
               correct and hands the strategy the last CLOSED bar.
    'closed'   raw last is a minute that has already ended -> the trim throws
               away a good bar, and every signal is a minute late.
    'stale'    raw last is older still -> IB itself is behind, and no trim
               setting fixes that.
    """
    delta = (now - raw_last.to_pydatetime()).total_seconds()
    if delta < 60:
        return "forming"
    if delta < 120:
        return "closed"
    return "stale"


EDGE_S = 5

# The tape has to be printing for any of this to mean anything. 04:00-20:00 ET
# is the extended session; MCL's own window is the narrower 04:00-09:30.
TAPE_OPEN = dtime(4, 0)
TAPE_CLOSE = dtime(20, 0)


def tape_is_live(now: datetime) -> bool:
    """Is a live tape printing minute bars right now?

    WHY THIS IS A HARD REFUSAL AND NOT A WARNING. Outside the session the last
    bar in every response is hours old, so classify() returns 'stale' for every
    sample and render()'s verdict falls through to "no clear majority, re-run
    with more samples". That sentence is wrong in a specific and expensive way:
    it blames the sample size and invites a longer run, when the defect is the
    clock and no number of samples fixes it. An uninformative run that reads as
    an inconclusive measurement is the same failure shape as a control that
    divides nothing — the output cannot be told apart from the real answer.

    Weekends and the overnight gap only. Market holidays are NOT checked, so a
    holiday still produces the stale-majority run this guard exists to prevent;
    the render-side check below is the backstop for that.
    """
    if now.weekday() >= 5:
        return False
    return TAPE_OPEN <= now.time() < TAPE_CLOSE


def at_minute_edge(now: datetime) -> bool:
    """Is this sample taken too close to the minute boundary to trust?

    THE AMBIGUITY THIS EXISTS FOR. Sampled at 06:23:02, a feed that includes
    the forming minute should answer 06:23 -- but a feed that is two seconds
    behind answers 06:22, and 06:22 is 62 seconds old, which classify() calls
    'closed'. That is the WRONG verdict from a right feed, and it is exactly
    the verdict this probe was built to look for, so it would confirm the
    hypothesis by accident.

    Samples inside the first EDGE_S seconds of a minute are therefore recorded
    and shown but excluded from the counts the verdict is read off.
    """
    return now.second < EDGE_S


def sample(now: datetime, df: pd.DataFrame) -> dict:
    """One observation. `df` is the RAW response, untrimmed.

    `acted` comes from the TRADER's own trim, not from a copy of it here. A
    probe that reimplemented `iloc[:-1]` would keep reporting the old answer
    after the trim changed, which is the one failure this measurement cannot
    afford.
    """
    if df is None or df.empty:
        return {"now": now, "empty": True}
    raw_last = df.index[-1].tz_convert(ET)
    acted = drop_forming_bar(df).index[-1].tz_convert(ET)
    return {
        "now": now,
        "raw_last": raw_last,
        "acted": acted,
        "kind": classify(now, raw_last),
        "edge": at_minute_edge(now),
        "raw_lag_s": round((now - raw_last.to_pydatetime()).total_seconds(), 1),
        "acted_lag_s": round((now - acted.to_pydatetime()).total_seconds(), 1),
    }


async def watch(ib, symbol: str, seconds: int, interval: int) -> list[dict]:
    c = Stock(symbol, "SMART", "USD", primaryExchange="NASDAQ")
    await ib.qualifyContractsAsync(c)
    out = []
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        data = await ib.reqHistoricalDataAsync(
            c, endDateTime="", durationStr=HISTORY_DURATION,
            barSizeSetting="1 min", whatToShow="TRADES", useRTH=False,
            formatDate=2)
        now = datetime.now(ET)
        if not data:
            out.append({"now": now, "empty": True})
        else:
            df = util.df(data).rename(columns=str.lower)
            df["date"] = pd.to_datetime(df["date"], utc=True)
            out.append(sample(now, df.set_index("date").sort_index()))
        await asyncio.sleep(interval)
    return out


def render(by_symbol: dict, seconds: int, interval: int) -> list[str]:
    L = ["BAR FRESHNESS -- which minute the trader is actually acting on", "",
         f"  sampled every {interval}s for {seconds}s per symbol",
         f"  duration      {HISTORY_DURATION}, 1 min, useRTH=False — the same "
         "request the trader makes",
         "",
         "  One minute of lag is expected and is not a defect: the strategy",
         "  acts on a CLOSED bar. The question is whether there is a SECOND",
         "  minute, and whether _fetch_bars's trim is causing it.", ""]

    kinds: Counter = Counter()
    edges = 0
    for symbol, rows in by_symbol.items():
        good = [r for r in rows if not r.get("empty")]
        L.append(f"{symbol}   {len(good)} sample(s), "
                 f"{len(rows) - len(good)} empty")
        for r in good[:12]:
            L.append(f"    {r['now']:%H:%M:%S}  raw last {r['raw_last']:%H:%M}"
                     f"  -> acts on {r['acted']:%H:%M}   "
                     f"({r['kind']}, raw {r['raw_lag_s']:.0f}s, "
                     f"acted {r['acted_lag_s']:.0f}s)"
                     + ("   [minute edge, not counted]" if r["edge"] else ""))
        if len(good) > 12:
            L.append(f"    ... {len(good) - 12} more")
        for r in good:
            if r["edge"]:
                edges += 1
            else:
                kinds[r["kind"]] += 1
        if good:
            L.append(f"    median acted lag "
                     f"{statistics.median(r['acted_lag_s'] for r in good):.0f}s")
        L.append("")

    total = sum(kinds.values())
    L += ["WHAT THE RESPONSE ENDS WITH", ""]
    for kind in ("forming", "closed", "stale"):
        n = kinds.get(kind, 0)
        L.append(f"  {kind:<8} {n:>4}"
                 + (f"   {100 * n / total:5.1f}%" if total else ""))
    if edges:
        L.append(f"  (excluded {edges} sample(s) taken in the first {EDGE_S}s "
                 f"of a minute, where a")
        L.append("   feed running seconds behind is indistinguishable from "
                 "one that omits")
        L.append("   the forming bar — the exact confusion this probe must "
                 "not make)")
    L.append("")

    if total and kinds.get("closed", 0) > total * 0.5:
        L += ["  VERDICT: the response ends at the last COMPLETED minute, so",
              "  _fetch_bars's `df.iloc[:-1]` is discarding a bar that had",
              "  already closed. Every entry in this project's live history is",
              "  one minute later than the rule it implements, and the fix is",
              "  to trim only when the last bar is genuinely the minute in",
              "  progress.", ""]
    elif total and kinds.get("forming", 0) > total * 0.5:
        L += ["  VERDICT: the response includes the minute in progress, so the",
              "  trim is correct and the second minute is somewhere else --",
              "  the once-a-minute fetch cadence and BAR_MIN_INTERVAL_S are",
              "  the next places to look.", ""]
    elif total and kinds.get("stale", 0) > total * 0.5:
        # The backstop for a market holiday, a halted name, or a dead feed —
        # cases tape_is_live() cannot see from the clock alone. Say the run was
        # uninformative, NOT that the result was inconclusive: more samples
        # cannot fix a tape that is not printing, and telling Ben to re-run
        # longer would waste a session.
        L += ["  NO VERDICT — THE TAPE WAS NOT PRINTING. Most responses ended",
              "  in a bar more than two minutes old, so there was no minute in",
              "  progress to classify. A market holiday, a halted symbol or a",
              "  dead feed all look like this. This is not an inconclusive",
              "  measurement; it is a run that could not have concluded",
              "  anything, and more samples will not change it.", ""]
    else:
        L += ["  VERDICT: no clear majority. Re-run with more samples inside a",
              "  session before concluding anything.", ""]

    L += ["WHAT THIS CANNOT SEE", "",
          "  The order round trip. This measures how stale the DATA is when",
          "  the trader reads it, not how long IB then takes to fill. The fill",
          "  log's seconds_to_fill covers that and has been about 0.5s."]
    return L


async def main_async(a) -> int:
    if a.port in LIVE_PORTS:
        sys.exit(f"REFUSING TO RUN: port {a.port} is {LIVE_PORTS[a.port]}. "
                 f"Paper ports are {sorted(PAPER_PORTS)}.")
    if a.port not in PAPER_PORTS:
        sys.exit(f"REFUSING TO RUN: port {a.port} is not a known paper port "
                 f"{sorted(PAPER_PORTS)}.")
    now = datetime.now(ET)
    if not (a.anyway or tape_is_live(now)):
        sys.exit(
            f"REFUSING TO RUN: it is {now:%a %H:%M} ET and the tape is closed "
            f"({TAPE_OPEN:%H:%M}-{TAPE_CLOSE:%H:%M} ET, weekdays).\n"
            "This probe asks whether the LAST bar of a response is the minute "
            "in progress.\n"
            "With no tape there is no minute in progress, every sample reads "
            "'stale', and the\n"
            "report says 'no clear majority' — which looks like an "
            "inconclusive measurement\n"
            "rather than a run that could never have concluded anything.\n"
            "\n"
            "Run it inside the session, alongside the trader. --anyway "
            "overrides this.")
    symbols = a.symbols or parse_watchlist(Path(a.watchlist))
    if not symbols:
        sys.exit("no symbols: pass --symbols or fill the watchlist")
    symbols = symbols[: a.limit]

    ib = IB()
    await ib.connectAsync(a.host, a.port, clientId=a.client_id)
    try:
        by_symbol = {s: await watch(ib, s, a.seconds, a.interval)
                     for s in symbols}
    finally:
        ib.disconnect()

    emit("\n".join(render(by_symbol, a.seconds, a.interval)), a.out,
         header=f"common.bar_freshness  symbols={','.join(symbols)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--watchlist", default="var/watchlist.txt")
    p.add_argument("--limit", type=int, default=1,
                   help="symbols to watch. Each costs seconds/interval "
                        "requests, and the trader is spending the same budget")
    p.add_argument("--seconds", type=int, default=180)
    p.add_argument("--interval", type=int, default=15)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=24,
                   help="not the trader's 17 nor the history probe's 23")
    p.add_argument("--anyway", action="store_true",
                   help="run outside the session anyway. The report will be "
                        "all-stale and will say so; there is no reason to "
                        "pass this except to test the plumbing")
    p.add_argument("--out", default="var/reports/bar_freshness.txt")
    return p


def main(argv=None) -> int:
    return asyncio.run(main_async(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
