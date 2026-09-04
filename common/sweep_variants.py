#!/usr/bin/env python3
"""
Compare strategy variants offline, over cached bars. No IB, no pacing, seconds.

    python sweep_variants.py                    # the 2x2
    python sweep_variants.py --detail           # per-variant exit breakdown
    python sweep_variants.py --csv out.csv      # write every trade

Requires a populated bar_cache/2d_to_0930/ -- run main.py --mode backtest once
to build it. After
that this runs as often as you like at no cost, which is the whole point: the
questions queued up (apex on/off, MACD > 0 on/off, and their interaction) each
needed a separate 85-minute paced IB pass before.

WHY A 2x2 AND NOT TWO SEPARATE TESTS
------------------------------------
V9 changed `MACD > 0` and the 3x volume surge simultaneously and the result was
uninterpretable -- an 81% expectancy collapse that could not be attributed to
either change. Two one-at-a-time tests would still miss an interaction, and an
interaction is exactly what is suspected here: dropping `MACD > 0` fires earlier
signals, which may only pay off if the exit lets them run.

So all four cells get measured on identical bars.
"""

from __future__ import annotations

import argparse
import pathlib

from common.cache_io import window_dir
import collections
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")

VARIANTS = [
    ("V7   apex ON  MACD>0",   dict(use_apex=True,  require_macd_pos=True)),
    ("V11  apex OFF MACD>0",   dict(use_apex=False, require_macd_pos=True)),
    ("V10  apex ON  no MACD>0", dict(use_apex=True,  require_macd_pos=False)),
    ("V12  apex OFF no MACD>0", dict(use_apex=False, require_macd_pos=False)),
]


def load_cache(cache_dir: Path):
    """Yield (symbol, date, frame) for every cached session."""
    files = sorted(cache_dir.glob("*.csv.gz"))
    if not files:
        sys.exit(f"{cache_dir}/ is empty. Run "
                 f"main.py --mode backtest --strategy mcl once to build it.")
    for f in files:
        stem = f.name[: -len(".csv.gz")]
        symbol, _, date_str = stem.rpartition("_")
        if not symbol:
            continue
        try:
            df = pd.read_csv(f, index_col=0, parse_dates=[0])
        except Exception:  # noqa: BLE001
            continue
        if df.empty:
            continue
        df.index = (df.index.tz_localize("UTC") if df.index.tz is None
                    else df.index.tz_convert("UTC"))
        yield symbol, date_str, df.sort_index()


def run(sessions, opts) -> list:
    out = []
    for symbol, date_str, df in sessions:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        for t in S.backtest_session(df, d, ET, **opts):
            t.symbol = symbol
            out.append(t)
    return out


def summarise(name: str, trades: list) -> dict:
    if not trades:
        return {"variant": name, "trades": 0, "net": 0.0}
    net = sum(t.net for t in trades)
    per = collections.defaultdict(float)
    for t in trades:
        per[t.symbol] += t.net
    top = sorted(per.values(), reverse=True)
    return {
        "variant": name,
        "trades": len(trades),
        "net": round(net, 2),
        "per_trade": round(net / len(trades), 2),
        "win": round(sum(1 for t in trades if t.net > 0) / len(trades) * 100, 1),
        "hold": round(sum(t.bars_held for t in trades) / len(trades), 1),
        "symbols": len(per),
        # Robustness is the number that killed V8 and V9. Concentration first.
        "drop1": round(net - sum(top[:1]), 2),
        "drop3": round(net - sum(top[:3]), 2),
        "drop5": round(net - sum(top[:5]), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline strategy variant sweep")
    ap.add_argument("--cache-dir", default="bar_cache",
                    help="cache ROOT; the 2d_to_0930 window is read from it")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--csv")
    a = ap.parse_args()

    # Same window backtest.py writes; reading the root would find nothing.
    sessions = list(load_cache(window_dir(Path(a.cache_dir), "2 D", "0930")))
    print(f"{len(sessions)} cached sessions\n")

    rows, all_trades = [], {}
    for name, opts in VARIANTS:
        trades = run(sessions, opts)
        all_trades[name] = trades
        rows.append(summarise(name, trades))

    hdr = (f"  {'variant':<24} {'trades':>7} {'net':>11} {'$/trade':>9} "
           f"{'win%':>6} {'hold':>6} {'drop3':>10} {'drop5':>10}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows:
        print(f"  {r['variant']:<24} {r['trades']:>7} {r['net']:>+11,.2f} "
              f"{r.get('per_trade', 0):>+9.2f} {r.get('win', 0):>6.1f} "
              f"{r.get('hold', 0):>6.1f} {r.get('drop3', 0):>+10,.2f} "
              f"{r.get('drop5', 0):>+10,.2f}")

    print("\n  drop3 / drop5 = net after removing the best 3 / 5 symbols.")
    print("  V8 and V9 were both rejected on these, not on headline net --")
    print("  a variant that only wins because of two names has not won.")

    if a.detail:
        for name, trades in all_trades.items():
            if not trades:
                continue
            print(f"\n  {name}")
            by = collections.defaultdict(list)
            for t in trades:
                by[t.reason].append(t.net)
            for reason, nets in sorted(by.items()):
                tot = sum(nets)
                print(f"    {reason:<16} n={len(nets):<5} net {tot:>+10,.2f}  "
                      f"avg {tot/len(nets):>+8.2f}  "
                      f"win {sum(1 for n in nets if n>0)/len(nets)*100:5.1f}%")

    if a.csv:
        recs = []
        for name, trades in all_trades.items():
            for t in trades:
                d = t.__dict__.copy()
                d["variant"] = name
                recs.append(d)
        pathlib.Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(recs).to_csv(a.csv, index=False)
        print(f"\n  {len(recs)} trades written to {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
