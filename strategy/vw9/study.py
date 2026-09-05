#!/usr/bin/env python3
"""
VW9 backtest study -- vw9_strategy_spec.md §7 (the four cells) and §10 (what
the report must contain), run offline over the cached bars.

    python -m strategy.vw9.study                 # the §7 x exit-mode grid
    python -m strategy.vw9.study --test dv       # MIN_TRIGGER_DV_PER_MIN sweep
    python -m strategy.vw9.study --test detail   # blocks, setups, concentration

WHY NOT main.py --mode backtest --strategy vw9_5m
-------------------------------------------------
That path goes through common/backtest.py's Runner, which imports ib_async and
exits without it, and which fetches anything the cache is missing. This reads
the cache directly and makes no connection, so the whole grid -- four cells,
three exit modes, twelve backtests over 374 sessions -- runs in about a minute
and can be re-run as often as parameters change. The bars it sees are the same
ones the Runner would slice: one session ending 20:00, per BACKTEST_SESSIONS
on the vw9_5m/vw9_15m adapters.

§7's FOUR CELLS, AND WHY CELL D IS RUN ANYWAY
---------------------------------------------
A 9 EMA spans 45 minutes on 5-minute bars and 135 on 15-minute bars. Those are
different strategies wearing the same number, and the V4->V5 comparison was
contaminated by exactly that -- the timeframe halved AND every indicator length
halved in wall-clock terms at once. So:

                    5-minute        15-minute
  same length       A: EMA 9        B: EMA 9
  matched clock     C: EMA 27       D: EMA 3

A vs B is the headline. A vs D and B vs C isolate bar size at constant
wall-clock lookback; A vs C and B vs D isolate lookback at constant bar size.
Cell D (EMA 3 on 15m) will be jumpy and may be useless -- run it anyway,
because its uselessness is what makes A vs B interpretable.

EVERY NUMBER HERE CARRIES THE PRE-MARKET FILL WARNING
-----------------------------------------------------
§9: outside RTH, IBKR accepts Day Limit orders only. VW9-5 deliberately trades
04:00-06:30, the window the session-window test found carried 93% of V7's P/L
and also the window whose fills the backtest cannot model. P/L from the PRE
block is not comparable to P/L from RTH. The block split is therefore printed
alongside every headline, not as an appendix.
"""

from __future__ import annotations

import argparse
import collections
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.vw9 import backtest as B
from strategy.vw9.preflight import load, pctile
from common.cache_io import load_pairs

ET = ZoneInfo("America/New_York")

# §7's four cells: (label, timeframe minutes, ema_fast, wall-clock span)
CELLS = [
    ("A  5m EMA9",  5,  9,  "45 min"),
    ("B 15m EMA9", 15,  9,  "135 min"),
    ("C  5m EMA27", 5, 27,  "135 min"),
    ("D 15m EMA3", 15,  3,  "45 min"),
]

# Measured live, 2026-09-03, per 100-share round trip, beyond the tick each way
# the engine already models. See common/friction.py -- and note it was measured
# under an exit mix MCL no longer produces, so treat it as a floor.
FRICTION = 4.26


def run(sessions, tf, exit_mode, **params):
    out = []
    for sym, ds, df in sessions:
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        try:
            trades = B.backtest_session_tf(df, d, ET, tf,
                                           exit_mode=exit_mode, **params)
        except Exception:  # noqa: BLE001
            continue
        for t in trades:
            t.symbol, t.date = sym, ds
            out.append(t)
    return out


def summarise(trades):
    if not trades:
        return dict(n=0, net=0.0, per=0.0, win=0.0, drop1=0.0, drop3=0.0,
                    drop5=0.0, fric=0.0, syms=0, med=0)
    net = sum(t.net for t in trades)
    by = collections.defaultdict(float)
    for t in trades:
        by[t.symbol] += t.net
    top = sorted(by.values(), reverse=True)
    holds = sorted(t.bars_held for t in trades)
    return dict(
        n=len(trades), net=net, per=net / len(trades),
        win=sum(1 for t in trades if t.net > 0) / len(trades) * 100,
        syms=len(by), med=statistics.median(holds),
        drop1=net - sum(top[:1]), drop3=net - sum(top[:3]),
        drop5=net - sum(top[:5]),
        fric=net - FRICTION * len(trades),
    )


def grid(sessions, dv):
    print("\n" + "=" * 104)
    print(f"  §7 FOUR CELLS x THREE EXIT MODES   (MIN_TRIGGER_DV_PER_MIN = {dv:,.0f})")
    print("=" * 104)
    hdr = (f"  {'cell':<12} {'span':>8} {'exit mode':<11} {'trades':>7} {'net':>11} "
           f"{'$/tr':>8} {'win%':>6} {'med':>4} {'drop3':>10} {'drop5':>10} "
           f"{'after fric':>11}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    results = {}
    for label, tf, ema, span in CELLS:
        for mode in B.EXIT_MODES:
            tr = run(sessions, tf, mode, ema_fast=ema, min_trigger_dv_per_min=dv)
            s = summarise(tr)
            results[(label, mode)] = (tr, s)
            print(f"  {label:<12} {span:>8} {mode:<11} {s['n']:>7} {s['net']:>+11,.2f} "
                  f"{s['per']:>+8.2f} {s['win']:>6.1f} {s['med']:>4} "
                  f"{s['drop3']:>+10,.2f} {s['drop5']:>+10,.2f} {s['fric']:>+11,.2f}")
        print()
    print("  'after fric' applies $4.26/trade, the MCL-measured figure. VW9's own")
    print("  friction is unmeasured and its pre-market fills are unmodelled.")
    return results


def dv_sweep(sessions):
    print("\n" + "=" * 96)
    print("  MIN_TRIGGER_DV_PER_MIN sweep -- §6 says do NOT guess this one")
    print("=" * 96)
    print("  §8.2 measured the median PRE 5m bar at $33,132/min. The shipped")
    print("  placeholder of $40,000 therefore rejects the median pre-market bar,")
    print("  in the window VW9 exists to trade.\n")
    hdr = (f"  {'$/min floor':>12} {'trades':>7} {'net':>11} {'$/tr':>8} {'win%':>6} "
           f"{'drop5':>10} {'after fric':>11} {'PRE trades':>11} {'PRE net':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for dv in (0, 1_000, 2_500, 5_000, 10_000, 20_000, 40_000, 80_000):
        tr = run(sessions, 5, "trail_atr", ema_fast=9, min_trigger_dv_per_min=dv)
        s = summarise(tr)
        pre = [t for t in tr if t.session_block == "PRE"]
        mark = "  <-- shipped" if dv == 40_000 else ""
        print(f"  {dv:>12,} {s['n']:>7} {s['net']:>+11,.2f} {s['per']:>+8.2f} "
              f"{s['win']:>6.1f} {s['drop5']:>+10,.2f} {s['fric']:>+11,.2f} "
              f"{len(pre):>11} {sum(t.net for t in pre):>+10,.2f}{mark}")
    print("\n  A floor is an ABSOLUTE threshold on a universe spanning a 340x range")
    print("  in per-bar volume -- the same shape as the 6,000-share floor that")
    print("  removed eight of 21 names and took $872 of winners with them.")


def detail(sessions, dv):
    print("\n" + "=" * 96)
    print("  §10 DETAIL -- best cell, broken out the way the spec requires")
    print("=" * 96)
    tr = run(sessions, 5, "trail_atr", ema_fast=9, min_trigger_dv_per_min=dv)
    if not tr:
        print("  no trades")
        return
    s = summarise(tr)
    print(f"  VW9-5, EMA9, trail_atr, dv floor {dv:,.0f}: {s['n']} trades, "
          f"{s['net']:+,.2f}, {s['per']:+.2f}/trade, {s['syms']} symbols\n")

    print("  by session block -- PRE fills are the ones the model cannot support:")
    print(f"    {'block':>6} {'trades':>7} {'net':>11} {'$/tr':>8} {'win%':>6}")
    for b in ("PRE", "RTH", "POST"):
        sub = [t for t in tr if t.session_block == b]
        if not sub:
            continue
        ss = summarise(sub)
        print(f"    {b:>6} {ss['n']:>7} {ss['net']:>+11,.2f} {ss['per']:>+8.2f} "
              f"{ss['win']:>6.1f}")

    print("\n  by setup -- A and B are different trades and may have opposite signs:")
    print(f"    {'setup':>6} {'trades':>7} {'net':>11} {'$/tr':>8} {'win%':>6}")
    for k in ("A", "B"):
        sub = [t for t in tr if t.setup_kind == k]
        if not sub:
            continue
        ss = summarise(sub)
        name = "A rec" if k == "A" else "B ret"
        print(f"    {name:>6} {ss['n']:>7} {ss['net']:>+11,.2f} {ss['per']:>+8.2f} "
              f"{ss['win']:>6.1f}")

    print("\n  entry-time histogram -- the direct test of §0's reason for existing:")
    hours = collections.Counter(
        pd.Timestamp(t.entry_time).tz_convert(ET).hour
        if pd.Timestamp(t.entry_time).tzinfo else pd.Timestamp(t.entry_time).hour
        for t in tr)
    for h in sorted(hours):
        bar = "#" * max(1, int(hours[h] / max(hours.values()) * 40))
        print(f"    {h:02d}:00 {hours[h]:>5}  {bar}")

    print("\n  concentration:")
    print(f"    drop top 1 {s['drop1']:>+12,.2f}")
    print(f"    drop top 3 {s['drop3']:>+12,.2f}")
    print(f"    drop top 5 {s['drop5']:>+12,.2f}")

    print("\n  exit reasons:")
    by = collections.defaultdict(list)
    for t in tr:
        by[t.reason].append(t.net)
    for reason, nets in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"    {reason:<16} n={len(nets):<5} net {sum(nets):>+11,.2f}  "
              f"avg {sum(nets)/len(nets):>+8.2f}  "
              f"win {sum(1 for n in nets if n>0)/len(nets)*100:5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="VW9 §7/§10 backtest study")
    ap.add_argument("--pairs", default="var/state/traded_pairs.json")
    ap.add_argument("--bars-cache", default="bar_cache")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dv", type=float, default=B.MIN_TRIGGER_DV_PER_MIN)
    ap.add_argument("--test", default="grid", choices=["grid", "dv", "detail", "all"])
    a = ap.parse_args()

    pairs = load_pairs(Path(a.pairs))
    sessions, missing = load(pairs, a.bars_cache, a.limit)
    print(f"{len(sessions)} sessions with cached bars, {missing} missing "
          f"(of {len(pairs)} pairs)")

    if a.test in ("grid", "all"):
        grid(sessions, a.dv)
    if a.test in ("dv", "all"):
        dv_sweep(sessions)
    if a.test in ("detail", "all"):
        detail(sessions, a.dv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
