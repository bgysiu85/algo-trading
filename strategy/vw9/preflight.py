#!/usr/bin/env python3
"""
VW9 pre-flight measurements -- vw9_strategy_spec.md §8.1, §8.2, §8.4, §8.5.

    python -m strategy.vw9.preflight
    python -m strategy.vw9.preflight --test dv        # just the §8.2 sweep
    python -m strategy.vw9.preflight --limit 50       # quick trial

§8.3 (setup counts, the go/no-go) already lives in setup_counts.py and has
passed: VW9-5 averages 3.32 triggers per pair per session, VW9-15 1.38, both
under the ~5 noise threshold. This is everything that comes after it -- the
measurements that are supposed to replace twelve guessed parameters with
numbers, and the ones the spec is most emphatic about:

  §8.1 bar availability   What fraction of intervals produce a bar, and WHEN
                          does bar 9 actually close? §0 claims VW9-5 reaches
                          04:45 and VW9-15 reaches 06:15. Those figures assume
                          every interval prints. On a thin low-float name they
                          are lower bounds, and if the real median is much
                          later then §0's whole reason for building VW9 --
                          reaching into the 04:00-06:30 window that carried
                          93% of V7's P/L -- is wrong.

  §8.2 dollar volume      Sets MIN_TRIGGER_DV_PER_MIN, which the engine
                          currently carries as the spec's own naive placeholder
                          ($20k/30s scaled linearly to $40k/min). §6: "do not
                          guess this one". The failure mode is specific and
                          documented: the 6,000-share floor in V5 removed eight
                          of 21 names ENTIRELY, and the excluded names held
                          ~$872 of winners against ~$115 of losers. So this
                          reports names-eliminated at each threshold, not just
                          bars-eliminated.

  §8.4 distributions      (close-ema9)/atr14 at trigger, pullback depth and
                          length, bars below VWAP before a reclaim. Replaces
                          MAX_EXT_ATR, MAX_PULLBACK_BARS, MIN_BELOW_BARS,
                          RECLAIM_LOOKBACK, PULLBACK_CTRL_ATR.

  §8.5 VWAP degeneracy    The bar at which |close-vwap|/close first exceeds 1%.
                          With one bar VWAP IS that bar's typical price, so an
                          early "price above VWAP" is a coin flip on where the
                          bar closed in its own range. If 1% separation is
                          routinely not reached until bar 5, MIN_VWAP_BARS = 3
                          is too permissive and the early pre-market signals
                          VW9 exists to capture are being generated against a
                          VWAP that is still just the opening print.

CALIBRATE TOWARD THE TIGHT END
------------------------------
E15 §4 records the lesson and it applies here: relaxing a restrictive rule
produced 75% more trades and LESS money -- the restrictiveness was doing the
work. Where a distribution is read for a threshold, the tight end of it is the
starting point, not the median.
"""

from __future__ import annotations

import argparse
import collections
import statistics
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import (load_cached_bars, load_pairs, slice_sessions,
                             window_dir, SHARED_DURATION, SHARED_END_HHMM)
from common.indicators import resample_bars
from strategy.vw9 import vw9 as V

ET = ZoneInfo("America/New_York")
SESSION_START, SESSION_END = dtime(4, 0), dtime(20, 0)
RTH_START, RTH_END = dtime(9, 30), dtime(16, 0)
TIMEFRAMES = (5, 15)

# Candidate MIN_TRIGGER_DV_PER_MIN values, dollars of bar dollar-volume per
# minute of bar. The engine currently ships 40,000 -- the spec's placeholder.
DV_CANDIDATES = [1_000, 2_500, 5_000, 10_000, 20_000, 40_000, 80_000]


def block(ts) -> str:
    t = ts.astimezone(ET).time()
    if t < RTH_START:
        return "PRE"
    if t < RTH_END:
        return "RTH"
    return "POST"


def load(pairs, cache_dir, limit):
    """(symbol, date, 1-minute session frame) for every pair with cached bars."""
    d = window_dir(Path(cache_dir), SHARED_DURATION, SHARED_END_HHMM)
    out, missing = [], 0
    for p in pairs[:limit] if limit else pairs:
        sym, ds = p["symbol"], p["date"]
        df = load_cached_bars(d, sym, ds)
        if df is None or df.empty:
            missing += 1
            continue
        want_end = datetime.strptime(ds, "%Y-%m-%d").replace(
            hour=SESSION_END.hour, minute=SESSION_END.minute, tzinfo=ET)
        sl = slice_sessions(df, want_end, 1)
        if sl is None or sl.empty:
            missing += 1
            continue
        out.append((sym, ds, sl))
    return out, missing


def pctile(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * p))]


# --------------------------------------------------------------- §8.1

def test_bar_availability(sessions):
    print("\n" + "=" * 82)
    print("  §8.1 BAR AVAILABILITY -- does VW9 actually reach pre-market?")
    print("=" * 82)
    print("  §0 claims bar 9 closes 04:45 on 5m and 06:15 on 15m, ASSUMING every")
    print("  interval prints a bar. These are the measured times.\n")

    print(f"  {'tf':>4} {'pairs':>6} {'bar-9 p10':>10} {'median':>9} {'p90':>9} "
          f"{'claimed':>9} {'% reaching 06:30':>17}")
    print("  " + "-" * 72)
    for tf in TIMEFRAMES:
        times, before_0630 = [], 0
        for _sym, _ds, df in sessions:
            r = resample_bars(df, tf)
            if len(r) < V.EMA_FAST:
                continue
            t9 = r.index[V.EMA_FAST - 1].astimezone(ET)
            mins = t9.hour * 60 + t9.minute
            times.append(mins)
            if mins <= 6 * 60 + 30:
                before_0630 += 1
        if not times:
            continue
        claimed = "04:45" if tf == 5 else "06:15"

        def hhmm(m):
            return f"{int(m)//60:02d}:{int(m)%60:02d}"
        print(f"  {tf:>3}m {len(times):>6} {hhmm(pctile(times,0.10)):>10} "
              f"{hhmm(statistics.median(times)):>9} {hhmm(pctile(times,0.90)):>9} "
              f"{claimed:>9} {before_0630/len(times)*100:>16.1f}%")

    print("\n  Interval fill rate -- fraction of possible bars that actually print:")
    print(f"  {'tf':>4} {'PRE':>8} {'RTH':>8} {'POST':>8}")
    print("  " + "-" * 34)
    for tf in TIMEFRAMES:
        got = collections.Counter()
        for _sym, _ds, df in sessions:
            r = resample_bars(df, tf)
            for ts in r.index:
                got[block(ts)] += 1
        # possible intervals per session per block, at this timeframe
        poss = {"PRE": (5 * 60 + 30) // tf, "RTH": (6 * 60 + 30) // tf,
                "POST": (4 * 60) // tf}
        n = len(sessions)
        print(f"  {tf:>3}m " + " ".join(
            f"{got[b]/(poss[b]*n)*100:>7.1f}%" for b in ("PRE", "RTH", "POST")))
    print("\n  A low PRE fill rate is the dominant effect on this universe and")
    print("  means '9 bars' is not '45 minutes'.")


# --------------------------------------------------------------- §8.2

def test_dollar_volume(sessions):
    print("\n" + "=" * 82)
    print("  §8.2 DOLLAR VOLUME -- sets MIN_TRIGGER_DV_PER_MIN. Do not guess it.")
    print("=" * 82)

    for tf in TIMEFRAMES:
        per_min_by_block = collections.defaultdict(list)
        name_max = {}          # best per-minute DV each NAME ever reaches
        for sym, _ds, df in sessions:
            r = resample_bars(df, tf)
            if r.empty:
                continue
            dv = (r["close"] * r["volume"]) / tf          # dollars per minute
            for ts, v in dv.items():
                per_min_by_block[block(ts)].append(float(v))
            name_max[sym] = max(name_max.get(sym, 0.0), float(dv.max()))

        print(f"\n  --- {tf}-minute bars ---")
        print(f"  {'block':>6} {'n bars':>8} {'p10':>12} {'median':>12} {'p90':>12}")
        print("  " + "-" * 54)
        for b in ("PRE", "RTH", "POST"):
            xs = per_min_by_block[b]
            if not xs:
                continue
            print(f"  {b:>6} {len(xs):>8} {pctile(xs,0.10):>12,.0f} "
                  f"{statistics.median(xs):>12,.0f} {pctile(xs,0.90):>12,.0f}")

        allx = [v for xs in per_min_by_block.values() for v in xs]
        names = len(name_max)
        print(f"\n  Threshold sweep. 'names killed' is the failure mode that matters:")
        print(f"  the V5 share floor removed 8 of 21 names ENTIRELY, and they held")
        print(f"  ~$872 of winners against ~$115 of losers.\n")
        print(f"  {'$/min floor':>12} {'bars kept':>11} {'names killed':>14} {'':>4}")
        print("  " + "-" * 46)
        for c in DV_CANDIDATES:
            kept = sum(1 for v in allx if v >= c) / len(allx) * 100
            killed = sum(1 for v in name_max.values() if v < c)
            mark = "  <-- shipped" if c == V.MIN_VWAP_DOLLAR_VOL / 1.25 else ""
            mark = "  <-- shipped placeholder" if c == 40_000 else mark
            print(f"  {c:>12,} {kept:>10.1f}% {killed:>8} / {names:<5}{mark}")


# --------------------------------------------------------------- §8.5

def test_vwap_degeneracy(sessions):
    print("\n" + "=" * 82)
    print("  §8.5 VWAP DEGENERACY -- is MIN_VWAP_BARS = 3 too permissive?")
    print("=" * 82)
    print("  With one bar, VWAP IS that bar's typical price. 'Price above VWAP'")
    print("  is then a coin flip on where the bar closed in its own range.")
    print("  Measured: the first bar at which |close - vwap| / close exceeds 1%.\n")

    print(f"  {'tf':>4} {'pairs':>6} {'median bar':>11} {'p75':>6} {'p90':>6} "
          f"{'never':>7} {'>= bar 3 by':>12}")
    print("  " + "-" * 60)
    for tf in TIMEFRAMES:
        firsts, never = [], 0
        for _sym, _ds, df in sessions:
            r = resample_bars(df, tf)
            if len(r) < 3:
                continue
            ind = V.apply_indicators(r)
            sep = (ind["close"] - ind["vwap"]).abs() / ind["close"]
            hit = sep[sep > 0.01]
            if hit.empty:
                never += 1
            else:
                firsts.append(int(ind.index.get_loc(hit.index[0])) + 1)
        if not firsts:
            continue
        by3 = sum(1 for f in firsts if f <= 3) / len(firsts) * 100
        print(f"  {tf:>3}m {len(firsts)+never:>6} {statistics.median(firsts):>11.0f} "
              f"{pctile(firsts,0.75):>6} {pctile(firsts,0.90):>6} {never:>7} "
              f"{by3:>11.1f}%")
    print("\n  '>= bar 3 by' is the fraction that HAVE separated by MIN_VWAP_BARS.")
    print("  A low number means the gate admits signals against a VWAP that is")
    print("  still essentially the opening print.")


# --------------------------------------------------------------- §8.4

def test_distributions(sessions):
    print("\n" + "=" * 82)
    print("  §8.4 DISTRIBUTIONS -- the numbers that replace the guesses")
    print("=" * 82)

    for tf in TIMEFRAMES:
        ext, below, pb_len, pb_depth = [], [], [], []
        kinds = collections.Counter()
        for _sym, _ds, df in sessions:
            r = resample_bars(df, tf)
            if len(r) < V.EMA_FAST + 2:
                continue
            ind = V.apply_indicators(r)
            try:
                setups = V.find_setups(r)
            except Exception:  # noqa: BLE001
                continue
            for s in setups:
                kinds[s.kind] += 1
                i = s.bar_index
                a = ind["atr14"].iloc[i]
                e = ind["ema9"].iloc[i]
                c = ind["close"].iloc[i]
                if pd.notna(a) and a > 0 and pd.notna(e):
                    ext.append(float((c - e) / a))
                if s.kind == "A":
                    # how many consecutive BEARISH bars preceded the reclaim
                    n = 0
                    j = i - 1
                    while j >= 0 and ind["regime"].iloc[j] == V.REGIME_BEARISH:
                        n += 1
                        j -= 1
                    below.append(n)
                elif s.pullback_start_idx is not None:
                    pb_len.append(i - s.pullback_start_idx)
                    if pd.notna(a) and a > 0:
                        hi = float(ind["close"].iloc[s.pullback_start_idx:i + 1].max())
                        lo = float(ind["low"].iloc[s.pullback_start_idx:i + 1].min())
                        pb_depth.append((hi - lo) / float(a))

        print(f"\n  --- {tf}-minute bars ---  Setup A {kinds['A']}, Setup B {kinds['B']}")
        rows = [
            ("(close-ema9)/atr14 at trigger", ext, "MAX_EXT_ATR", V.__dict__.get("MAX_EXT_ATR", 2.0)),
            ("bars below VWAP before reclaim", below, "MIN_BELOW_BARS", V.MIN_BELOW_BARS),
            ("pullback length (bars)", pb_len, "MAX_PULLBACK_BARS", V.MAX_PULLBACK_BARS),
            ("pullback depth (ATR)", pb_depth, "PULLBACK_CTRL_ATR", V.PULLBACK_CTRL_ATR),
        ]
        print(f"  {'measure':<32} {'n':>5} {'p10':>8} {'median':>8} {'p75':>8} "
              f"{'p90':>8} {'current':>18}")
        print("  " + "-" * 94)
        for label, xs, pname, pval in rows:
            if not xs:
                print(f"  {label:<32} {0:>5} {'--':>8} {'--':>8} {'--':>8} {'--':>8} "
                      f"{pname+'='+str(pval):>18}")
                continue
            print(f"  {label:<32} {len(xs):>5} {pctile(xs,0.10):>8.2f} "
                  f"{statistics.median(xs):>8.2f} {pctile(xs,0.75):>8.2f} "
                  f"{pctile(xs,0.90):>8.2f} {pname+'='+str(pval):>18}")
    print("\n  Calibrate toward the TIGHT end of each distribution, not the median:")
    print("  E15 §4 and the armBars relaxation both found restrictiveness was")
    print("  doing the real work.")


def main() -> int:
    ap = argparse.ArgumentParser(description="VW9 §8.1/8.2/8.4/8.5 pre-flight")
    ap.add_argument("--pairs", default="var/state/traded_pairs.json")
    ap.add_argument("--bars-cache", default="bar_cache")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--test", default="all",
                    choices=["all", "bars", "dv", "vwap", "dist"])
    a = ap.parse_args()

    pairs = load_pairs(Path(a.pairs))
    sessions, missing = load(pairs, a.bars_cache, a.limit)
    print(f"{len(sessions)} pairs with cached bars, {missing} missing "
          f"(of {len(pairs)} total)")

    if a.test in ("all", "bars"):
        test_bar_availability(sessions)
    if a.test in ("all", "dv"):
        test_dollar_volume(sessions)
    if a.test in ("all", "vwap"):
        test_vwap_degeneracy(sessions)
    if a.test in ("all", "dist"):
        test_distributions(sessions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
