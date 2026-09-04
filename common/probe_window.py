#!/usr/bin/env python3
"""Check that one shared superset fetch can replace the two current pulls.

    python main.py --mode probe-window --limit 4

WHY THIS EXISTS RATHER THAN JUST SHIPPING THE CHANGE
----------------------------------------------------
The arithmetic is settled: "3 D" ending 20:00 spans both windows, and slicing
it reproduces each one exactly on synthetic bars. What is NOT settled is
whether IB's "3 D" response contains the same bars its "2 D" and "1 D"
responses would -- boundary inclusivity, session-edge handling, holidays and
half-days are IB's behaviour, not arithmetic, and this repo has already paid
twice for assuming IB behaves as documented (throttling returned as empty
lists; split-adjusted prices served as if raw).

So: fetch all three windows for a handful of pairs, slice the superset, and
compare bar-for-bar. Costs three requests per pair. If it reports a clean
match, set SHARED_WINDOW and the big pull halves. If it does not, the report
says exactly which bars differ.

Read-only: requests history, places nothing. Paper port by default.
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
    sys.exit("ib_async not installed.  pip install -r requirements.txt")

from common import session_lock
from common.cache_io import load_pairs, slice_window

ET = ZoneInfo("America/New_York")
PAPER_PORTS = {4002: "IB Gateway paper", 7497: "TWS paper"}
LIVE_PORTS = {4001: "IB Gateway LIVE", 7496: "TWS LIVE"}
REQUEST_INTERVAL_S = 12.5

# (label, durationStr, end hour, end minute, duration_days for slicing)
WINDOWS = [
    ("backtest", "2 D", 9, 30, 2),
    ("data_ib", "1 D", 20, 0, 1),
]
SUPERSET = ("3 D", 20, 0)


async def _fetch(ib, contract, date_str, duration, end_h, end_m):
    end = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=end_h, minute=end_m, tzinfo=ET)
    await asyncio.sleep(REQUEST_INTERVAL_S)
    data = await ib.reqHistoricalDataAsync(
        contract, endDateTime=end, durationStr=duration,
        barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=2)
    if not data:
        return None
    df = util.df(data)
    if df is None or df.empty:
        return None
    df = df.rename(columns=str.lower)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def _compare(label, direct, sliced) -> bool:
    if direct is None:
        print(f"    {label:9} direct request returned nothing -- inconclusive")
        return True
    if sliced is None or sliced.empty:
        print(f"    {label:9} MISMATCH: superset slice is empty, direct has {len(direct)}")
        return False
    missing = direct.index.difference(sliced.index)
    extra = sliced.index.difference(direct.index)
    cols = ["open", "high", "low", "close", "volume"]
    common = direct.index.intersection(sliced.index)
    drift = float((direct.loc[common, cols] - sliced.loc[common, cols]).abs().max().max()) \
        if len(common) else float("nan")
    ok = not len(missing) and not len(extra) and (drift == 0.0)
    print(f"    {label:9} direct {len(direct):5}  sliced {len(sliced):5}  "
          f"missing {len(missing):4}  extra {len(extra):4}  value drift {drift:.2e}  "
          f"{'MATCH' if ok else 'MISMATCH'}")
    if len(missing):
        print(f"              first missing: {list(missing[:3])}")
    if len(extra):
        print(f"              first extra:   {list(extra[:3])}")
    return ok


async def main_async(args) -> int:
    if args.port in LIVE_PORTS:
        print(f"REFUSING: port {args.port} is {LIVE_PORTS[args.port]}.")
        return 1
    live = session_lock.active()
    if live:
        print("REFUSING: " + session_lock.describe(live))
        return 1

    pairs = load_pairs(Path(args.pairs))[: args.limit]
    if not pairs:
        print(f"no pairs in {args.pairs}")
        return 1

    ib = IB()
    try:
        await ib.connectAsync("127.0.0.1", args.port, clientId=args.client_id, timeout=15)
    except Exception as e:  # noqa: BLE001
        print(f"could not connect to 127.0.0.1:{args.port} -- {e}")
        return 1

    all_ok = True
    try:
        for p in pairs:
            sym, date_str = p["symbol"], p["date"]
            got = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
            if not got:
                print(f"  {sym} {date_str}: could not qualify -- skipped")
                continue
            contract = got[0]
            print(f"  {sym} {date_str}")

            sup = await _fetch(ib, contract, date_str, *SUPERSET[:1], SUPERSET[1], SUPERSET[2])
            if sup is None:
                print("    superset returned nothing -- inconclusive")
                continue

            for label, duration, eh, em, days in WINDOWS:
                direct = await _fetch(ib, contract, date_str, duration, eh, em)
                end = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    hour=eh, minute=em, tzinfo=ET)
                all_ok &= _compare(label, direct, slice_window(sup, end, days))
    finally:
        ib.disconnect()

    print()
    if all_ok:
        print("SUPERSET IS SAFE for the pairs probed. Set SHARED_WINDOW to halve")
        print("the pull. Note this is evidence, not proof -- holidays and")
        print("half-days are the cases most likely to differ.")
    else:
        print("SUPERSET IS NOT SAFE as configured -- see the mismatches above.")
        print("Do NOT enable SHARED_WINDOW. The two windows stay separate.")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Probe whether one superset fetch replaces two")
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--limit", type=int, default=4, help="pairs to probe (3 requests each)")
    p.add_argument("--port", type=int, default=4002)
    p.add_argument("--client-id", type=int, default=39)
    args = p.parse_args(argv)
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
