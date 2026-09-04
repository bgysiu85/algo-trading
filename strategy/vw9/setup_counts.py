#!/usr/bin/env python3
"""
VW9 pre-flight measurement -- vw9_strategy_spec.md §8.3 "Setup counts":

    "How many Setup A and Setup B triggers fire per pair per session at each
    timeframe, before gates? This sets the sample size and is the go/no-go.
    E15's equivalent gate was ~0.3 completed setups per pair; VW9 should
    produce considerably more, since it re-enters and requires no crossover.
    If VW9-5 produces more than ~5 triggers per pair per session the gates
    are too loose and the strategy is closer to noise-trading than to the
    sources' intent."

This is offline analysis over bars ALREADY cached by data_ib.py -- it makes
no IB connection itself. Run data_ib.py first:

    .\\.venv\\Scripts\\python.exe -m common.data_ib
    .\\.venv\\Scripts\\python.exe -m strategy.vw9.setup_counts

Reuses the same 407 symbol/date pairs as MCL by default (both specs' §1:
"Reuse the existing 407 ticker/date pairs so [E15/VW9] is comparable to
V7/MC5 on the same tape"), read from traded_pairs.json --
not duplicated into this folder, so there is one source of truth for the
pair list.

OUTPUT
------
- A per-pair-per-timeframe summary printed to stdout (§8.3's own report:
  mean/median triggers per pair, Setup A vs B split, go/no-go flag).
- setup_counts_trades.csv: every individual trigger found, one row each,
  with entry_ref/structure_low already computed -- this is also the raw
  material §8.4 (distributions) will need next, so it's written now rather
  than thrown away.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import load_cached_bars, load_pairs, window_dir
from common.indicators import resample_bars
from strategy.vw9.vw9 import find_setups

ET = ZoneInfo("America/New_York")
SESSION_START, SESSION_END = "04:00", "20:00"
TIMEFRAMES = (5, 15)

# §8.3's own stated go/no-go line: "If VW9-5 produces more than ~5 triggers
# per pair per session the gates are too loose". Applied here as a flag on
# both timeframes' mean, since the reasoning (window model, re-entry,
# no-crossover-required) applies less strongly but not zero to 15m too.
NOISE_TRADING_THRESHOLD = 5.0


def session_slice(bars: pd.DataFrame, date_str: str) -> pd.DataFrame:
    """04:00-20:00 ET on the target date only. Defensive: data_ib.py already
    requests roughly this window, but IB's '1 D' duration is not a hard
    contract about exactly which bars come back, and stray bars from the
    edges (or a rollover) must not leak into the count."""
    local = bars.index.tz_convert(ET)
    target = pd.Timestamp(date_str).date()
    mask = ((local.date == target)
             & (local.time >= pd.Timestamp(SESSION_START).time())
             & (local.time < pd.Timestamp(SESSION_END).time()))
    return bars[mask]


def count_for_pair(bars_1m: pd.DataFrame, date_str: str) -> dict[int, list]:
    """Setups at every timeframe in TIMEFRAMES, for one pair's session."""
    sess_1m = session_slice(bars_1m, date_str)
    out: dict[int, list] = {}
    for tf in TIMEFRAMES:
        bars_tf = sess_1m if tf == 1 else resample_bars(sess_1m, tf)
        out[tf] = find_setups(bars_tf) if len(bars_tf) else []
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="VW9 §8.3 setup-count pre-flight measurement")
    ap.add_argument("--pairs", default="var/state/traded_pairs.json")
    ap.add_argument("--bars-cache", default="bar_cache",
                    help="cache ROOT; the 1d_to_2000 window is read from it")
    ap.add_argument("--out", default="setup_counts_trades.csv")
    ap.add_argument("--limit", type=int, help="only the first N pairs (quick trial)")
    args = ap.parse_args()

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"{pairs_path} not found -- run data_ib.py first, or point --pairs "
              f"at the right traded_pairs.json")
        return 1
    pairs = load_pairs(pairs_path)
    if args.limit:
        pairs = pairs[: args.limit]

    # Must match data_ib.py's window, or this reads an empty directory and
    # reports "no cached bars" for data that is actually present.
    bars_cache = window_dir(Path(args.bars_cache), "1 D", "2000")
    rows: list[dict] = []
    n_total = len(pairs)
    n_cached = n_missing = 0

    for p in pairs:
        sym, date_str = p["symbol"], p["date"]
        bars_1m = load_cached_bars(bars_cache, sym, date_str)
        if bars_1m is None or bars_1m.empty:
            n_missing += 1
            continue
        n_cached += 1

        by_tf = count_for_pair(bars_1m, date_str)
        for tf, setups in by_tf.items():
            for s in setups:
                rows.append({
                    "symbol": sym, "date": date_str, "timeframe": tf,
                    "kind": s.kind, "trigger_time": s.trigger_time,
                    "bar_index": s.bar_index, "entry_ref": s.entry_ref,
                    "structure_low": s.structure_low,
                })
        # ensure every cached pair contributes a zero-row per timeframe so
        # the mean in summarise() is computed over ALL pairs with bars, not
        # just the ones that happened to produce a trigger
        for tf in TIMEFRAMES:
            if not by_tf.get(tf):
                rows.append({"symbol": sym, "date": date_str, "timeframe": tf,
                            "kind": None, "trigger_time": None, "bar_index": None,
                            "entry_ref": None, "structure_low": None})

    print(f"pairs: {n_total} total, {n_cached} with cached bars, "
          f"{n_missing} missing (run data_ib.py to fetch them)\n")

    if not rows:
        print("no cached bars found -- nothing to measure. Run data_ib.py first.")
        return 1

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df[df['kind'].notna()])} trigger rows to {args.out}\n")

    triggers_only = df[df["kind"].notna()]
    per_pair_all = df.groupby(["symbol", "date", "timeframe"]).apply(
        lambda g: int(g["kind"].notna().sum()), include_groups=False)

    print("=" * 70)
    print("  §8.3 SETUP COUNTS -- before §4.3 gates")
    print("=" * 70)
    for tf in TIMEFRAMES:
        counts = per_pair_all.xs(tf, level="timeframe")
        a = int(((triggers_only["timeframe"] == tf) & (triggers_only["kind"] == "A")).sum())
        b = int(((triggers_only["timeframe"] == tf) & (triggers_only["kind"] == "B")).sum())
        mean_c = round(counts.mean(), 3) if len(counts) else 0.0
        median_c = round(counts.median(), 3) if len(counts) else 0.0
        label = f"VW9-{tf}"
        print(f"\n  {label}  ({len(counts)} pairs with cached bars)")
        print(f"    Setup A (VWAP reclaim)   {a:>5}")
        print(f"    Setup B (9 EMA retest)   {b:>5}")
        print(f"    total triggers           {a + b:>5}")
        print(f"    mean / pair / session    {mean_c:>8.3f}")
        print(f"    median / pair / session  {median_c:>8.3f}")
        print(f"    max / pair               {int(counts.max()) if len(counts) else 0:>5}")
        if tf == 5 and mean_c > NOISE_TRADING_THRESHOLD:
            print(f"    ^^ ABOVE the spec's noise-trading threshold "
                  f"(~{NOISE_TRADING_THRESHOLD}/pair/session).")
            print("       Gates are too loose at this timeframe -- see §8.3.")
        elif mean_c < 0.05:
            print("    ^^ Very low. Compare against E15's ~0.3/pair gate before "
                  "treating this as viable sample size (§7 item 3 of the E15 spec).")

    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
