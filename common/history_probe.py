#!/usr/bin/env python3
"""How much 1-minute history does IB actually return, and is MC5 warm at 04:00?

    python -m common.history_probe --symbols AAPL TSLA
    python -m common.history_probe                     # today's watchlist

H6 in claude/multi_strategy_trader_spec.md, and the last thing standing
between MC5 and a paper session that means anything.

THE QUESTION
------------
strategy/mc5/mc5.py needs MIN_BARS_REQUIRED five-minute bars before it will say
anything -- 40 of them, which is 3 hours 20 minutes of clock. MCL needs 40
ONE-minute bars, which is 40 minutes. The trader fetches durationStr="1 D".

A backtest cannot show this. backtest_session computes signals() over the whole
cached frame -- three days -- and only then restricts to the session date, so
its indicators are warm at 04:00 by construction. If "1 D" really means "since
this session's open", live MC5 is blind until about 07:20 and sits out more
than half of a 04:00-09:30 session, while every backtest figure for it assumes
otherwise.

WHY THIS IS A MEASUREMENT AND NOT A ONE-LINE CHANGE
---------------------------------------------------
"N D" counts TRADING SESSIONS, endpoint exclusive, and with useRTH=False it
includes extended hours -- so what "1 D" spans for a thinly traded small cap at
04:10 is genuinely not obvious, and guessing it wrong in either direction is
expensive. Asking for more history is not free either: IB paces historical
requests at roughly 60 per 10 minutes ACROSS ALL CONTRACTS and signals the
limit by returning EMPTY LISTS rather than errors, so a strategy that quietly
doubles its request size can go blind without saying so.

So this asks, records both, and computes what each would mean for each
strategy. It places no orders and refuses any port that is not a known paper
port -- the same guard brokers/ibkr/trader.py applies.

RUN IT DURING A SESSION. The answer depends on the time of day: at 04:10 "1 D"
may hold ten minutes or a full prior session, and only one of those is a
problem. Running it at 22:00 answers a question nobody asked.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, util
except ImportError:  # pragma: no cover
    sys.exit("ib_async not installed.  pip install ib_async pandas")

from brokers.ibkr.trader import LIVE_PORTS, PAPER_PORTS, parse_watchlist
from common.report_io import emit
from common import strategy_adapter as SA

ET = ZoneInfo("America/New_York")
DURATIONS = ("1 D", "2 D")


def buckets(df: pd.DataFrame, minutes: int) -> int:
    """Distinct strategy-sized bars this frame would resample to.

    Counted rather than divided: a bucket with no prints produces no row (see
    common/indicators.resample_bars), and on a thin pre-market name that is a
    large fraction of them. Dividing the minute count by 5 would overstate how
    warm MC5 is, which is the exact error this probe exists to avoid making.
    """
    if df is None or df.empty:
        return 0
    if minutes <= 1:
        return len(df)
    return df.index.floor(f"{minutes}min").nunique()


def measure(df: pd.DataFrame, adapters) -> list[dict]:
    out = []
    for a in adapters:
        need = getattr(a.module, "MIN_BARS_REQUIRED", 0)
        have = buckets(df, a.bar_minutes)
        out.append(dict(name=a.name, bar_minutes=a.bar_minutes,
                        need=need, have=have, warm=have >= need))
    return out


async def probe(ib, symbol: str, adapters) -> dict:
    row = {"symbol": symbol, "requests": 0, "by_duration": {}}
    c = Stock(symbol, "SMART", "USD", primaryExchange="NASDAQ")
    try:
        await ib.qualifyContractsAsync(c)
        row["requests"] += 1
    except Exception as e:                                    # noqa: BLE001
        row["error"] = f"qualify failed: {e}"
        return row
    for dur in DURATIONS:
        try:
            data = await ib.reqHistoricalDataAsync(
                c, endDateTime="", durationStr=dur, barSizeSetting="1 min",
                whatToShow="TRADES", useRTH=False, formatDate=2)
            row["requests"] += 1
        except Exception as e:                                # noqa: BLE001
            row["by_duration"][dur] = {"error": str(e)}
            continue
        if not data:
            # THE FAILURE MODE THAT LOOKS LIKE NO DATA. IB signals pacing by
            # returning an empty list, not an error, so this is recorded as
            # ambiguous rather than as "the symbol has no history".
            row["by_duration"][dur] = {"empty": True}
            continue
        df = util.df(data)
        df = df.rename(columns=str.lower)
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date").sort_index()
        local = df.index.tz_convert(ET)
        row["by_duration"][dur] = {
            "bars": len(df),
            "first": str(local[0]),
            "last": str(local[-1]),
            "span_h": round((local[-1] - local[0]).total_seconds() / 3600, 2),
            "strategies": measure(df, adapters),
        }
    return row


def render(rows, adapters, now) -> list[str]:
    L = ["IB HISTORY PROBE -- how much 1-minute history each duration returns",
         "",
         f"  asked at      {now:%Y-%m-%d %H:%M:%S} ET",
         f"  durations     {', '.join(DURATIONS)}",
         f"  strategies    " + ", ".join(
             f"{a.name} needs {getattr(a.module, 'MIN_BARS_REQUIRED', 0)} "
             f"x {a.bar_minutes}m bars" for a in adapters),
         "",
         "  The answer depends on the time of day. Read this only if it was",
         "  run inside a session.", ""]

    total_req = sum(r.get("requests", 0) for r in rows)
    for r in rows:
        L.append(f"{r['symbol']}")
        if "error" in r:
            L += [f"    {r['error']}", ""]
            continue
        for dur in DURATIONS:
            d = r["by_duration"].get(dur, {})
            if d.get("empty"):
                L.append(f"    {dur:<4} EMPTY LIST — IB signals pacing this "
                         "way, so this is ambiguous, not 'no data'")
                continue
            if "error" in d:
                L.append(f"    {dur:<4} error: {d['error']}")
                continue
            L.append(f"    {dur:<4} {d['bars']:>5} bars  {d['span_h']:>6.2f}h  "
                     f"{d['first'][11:16]} -> {d['last'][11:16]}")
            for s in d["strategies"]:
                mark = "warm" if s["warm"] else "COLD"
                L.append(f"           {s['name']:<5} {s['have']:>4} of "
                         f"{s['need']:>3} {s['bar_minutes']}m bars   {mark}")
        L.append("")

    L += ["WHAT IT COSTS", "",
          f"  {total_req} historical/qualify requests for {len(rows)} symbol(s).",
          "  IB paces at ~60 per 10 minutes ACROSS ALL CONTRACTS and signals",
          "  the limit by returning empty lists rather than errors. Whatever",
          "  duration the trader ends up asking for, it asks once per symbol",
          "  per minute — so the cost of a longer window is the SIZE of each",
          "  response, not the number of requests.",
          "",
          "READ IT THIS WAY", "",
          "  If MC5 is COLD on '1 D' and warm on '2 D', the trader needs the",
          "  longer duration before an MC5 session means anything, and the",
          "  change is one argument in _fetch_bars.",
          "  If MC5 is COLD on BOTH, the warm-up cannot be bought with history",
          "  at all at this time of day, and MC5 can only trade the back half",
          "  of a session — which is a fact about the strategy that belongs in",
          "  its spec, not a bug to fix.",
          "  If MC5 is warm on '1 D', H6 was a false alarm and the trader",
          "  changes nothing."]
    return L


async def main_async(args) -> int:
    if args.port in LIVE_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is {LIVE_PORTS[args.port]}. "
                 f"Paper ports are {sorted(PAPER_PORTS)}.")
    if args.port not in PAPER_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is not a known paper port "
                 f"{sorted(PAPER_PORTS)}.")

    symbols = args.symbols or parse_watchlist(Path(args.watchlist))
    if not symbols:
        sys.exit(f"no symbols: pass --symbols, or put tickers in "
                 f"{args.watchlist}")
    symbols = symbols[: args.limit]

    adapters = SA.build_all(args.strategy)
    ib = IB()
    await ib.connectAsync(args.host, args.port, clientId=args.client_id)
    try:
        rows = [await probe(ib, s, adapters) for s in symbols]
    finally:
        ib.disconnect()

    emit("\n".join(render(rows, adapters, datetime.now(ET))), args.out,
         header=f"common.history_probe  symbols={','.join(symbols)}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--watchlist", default="var/watchlist.txt")
    p.add_argument("--limit", type=int, default=4,
                   help="symbols to probe; each costs 3 IB requests")
    p.add_argument("--strategy", nargs="+", default=["mcl", "mc5"])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=23,
                   help="not the trader's 17 — this is meant to run alongside "
                        "a live session, and two clients cannot share an id")
    p.add_argument("--out", default="var/reports/history_probe.txt")
    a = p.parse_args(argv)
    return asyncio.run(main_async(a))


if __name__ == "__main__":
    sys.exit(main())
