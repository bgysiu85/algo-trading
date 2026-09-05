#!/usr/bin/env python3
"""
TRAIL_PCT decision study -- the four checks mcl_robustness_analysis.md requires
before the trail is allowed to move off 5%.

    python -m common.trail_study
    python -m common.trail_study --candidates 5 8 10 --resamples 10000

WHY THIS EXISTS SEPARATELY FROM analysis.py --test trail
--------------------------------------------------------
`analysis.py --test trail` prints one column per trail value over the whole
sample. That table is what raised the question -- 5% is the trough on both net
and drop5 -- but it is also exactly the shape a curve-fit takes: a continuous
parameter, one dataset, pick the best cell. The robustness doc says so itself
and lists what a real decision needs. This runs that list:

  1. temporal holdout      the effect must appear in BOTH halves, split fixed
                           at the date analysis.py already uses. NOT swept --
                           sweeping the split point reintroduces the fitting
                           the test exists to detect.
  2. paired bootstrap      same symbols, different trail. 10,000 resamples OF
                           SYMBOLS, reporting the delta's 95% CI and
                           P(improvement > 0). Two independent bootstraps
                           would answer a different, easier question.
  3. source of gains       broad, or a handful of runners? The apex result was
                           honest about being tail-carried; this must be too.
  4. hold time             median hold goes 2 -> 7 -> 14 bars across the range.
                           That is not a tuning tweak, it is a different
                           strategy, and it has an operational cost: the trail
                           is software-managed inside the running process, so
                           longer holds mean more wall-clock exposure to a
                           crash leaving a position unprotected.

Everything runs against the shipped configuration (apex OFF, MACD>0 ON), since
that is what the trail would actually be changed on top of.

FRICTION IS THE SCOREBOARD, NOT NET
-----------------------------------
Every candidate is also reported after the measured ~$4.26/round-trip. A wider
trail takes fewer trades, so it pays less total friction -- which flatters it
in a way the raw net column hides. The break-even column is the honest one.
"""

from __future__ import annotations

import argparse
import collections
import random
import statistics
import sys
from pathlib import Path

from common.analysis import load_sessions, run, LIVE, MEASURED_FRICTION

INCUMBENT = 5.0
CURVE = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
HOLDOUT_SPLIT = None  # computed from the data, same rule as analysis.py


# ------------------------------------------------------------------ helpers

def per_symbol(trades, universe) -> dict:
    """Net by symbol, zero-filled over a fixed universe.

    Zero-filling matters: a symbol that trades at 5% but not at 15% has a real
    delta, and dropping it from one side would silently compare different
    universes.
    """
    d = {s: 0.0 for s in universe}
    for t in trades:
        d[t.symbol] += t.net
    return d


def summarise(trades, label):
    if not trades:
        return dict(label=label, n=0, net=0.0, per=0.0, win=0.0,
                    drop1=0.0, drop3=0.0, drop5=0.0, med=0, p90=0, p95=0, mx=0)
    net = sum(t.net for t in trades)
    by = collections.defaultdict(float)
    for t in trades:
        by[t.symbol] += t.net
    top = sorted(by.values(), reverse=True)
    holds = sorted(t.bars_held for t in trades)

    def pct(p):
        return holds[min(len(holds) - 1, int(len(holds) * p))]

    return dict(
        label=label, n=len(trades), net=net, per=net / len(trades),
        win=sum(1 for t in trades if t.net > 0) / len(trades) * 100,
        syms=len(by),
        drop1=net - sum(top[:1]), drop3=net - sum(top[:3]), drop5=net - sum(top[:5]),
        med=statistics.median(holds), p90=pct(0.90), p95=pct(0.95), mx=holds[-1],
        friction=net - MEASURED_FRICTION * len(trades),
        breakeven=net / len(trades),
    )


def paired_bootstrap(base_by_sym, cand_by_sym, resamples, seed=20260905):
    """Resample SYMBOLS with replacement; the statistic is the summed delta.

    Pairing is the point. The same symbol contributes its base and its
    candidate net together, so symbol-level variation -- which dominates here,
    since a few runners carry the sample -- cancels out of the comparison
    instead of swamping it.
    """
    syms = sorted(base_by_sym)
    deltas = [cand_by_sym[s] - base_by_sym[s] for s in syms]
    n = len(deltas)
    rng = random.Random(seed)
    tot = []
    for _ in range(resamples):
        tot.append(sum(deltas[rng.randrange(n)] for _ in range(n)))
    tot.sort()
    lo = tot[int(resamples * 0.025)]
    hi = tot[int(resamples * 0.975)]
    p_gt0 = sum(1 for v in tot if v > 0) / resamples * 100
    return sum(deltas), lo, hi, p_gt0


# ------------------------------------------------------------------- report

def main() -> int:
    ap = argparse.ArgumentParser(description="TRAIL_PCT decision study")
    ap.add_argument("--cache-dir", default="bar_cache")
    ap.add_argument("--candidates", nargs="*", type=float, default=[8.0, 10.0, 15.0],
                    help="trail values to test against the 5%% incumbent")
    ap.add_argument("--resamples", type=int, default=10000)
    a = ap.parse_args()

    sessions = load_sessions(Path(a.cache_dir))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    print(f"{len(sessions)} sessions, {len({s for s,_,_ in sessions})} symbols in cache, "
          f"{len(dates)} dates {dates[0]}..{dates[-1]}")
    print(f"config: apex OFF, MACD>0 ON (the shipped one). friction ${MEASURED_FRICTION}/round trip\n")

    # ---------------------------------------------------------- 0. the curve
    print("=" * 100)
    print("  0. THE CURVE -- full sample, for shape only. Do not decide off this table.")
    print("=" * 100)
    hdr = (f"  {'trail':>6} {'trades':>7} {'net':>11} {'$/tr':>8} {'win%':>6} "
           f"{'drop5':>10} {'after fric':>11} {'med':>5} {'p90':>5} {'p95':>5} {'max':>6}")
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    curve = {}
    for tp in CURVE:
        s = summarise(run(sessions, LIVE, trail_pct=tp), f"{tp:g}%")
        curve[tp] = s
        mark = "  <-- current" if tp == INCUMBENT else ""
        print(f"  {tp:>5.0f}% {s['n']:>7} {s['net']:>+11,.2f} {s['per']:>+8.2f} "
              f"{s['win']:>6.1f} {s['drop5']:>+10,.2f} {s['friction']:>+11,.2f} "
              f"{s['med']:>5} {s['p90']:>5} {s['p95']:>5} {s['mx']:>6}{mark}")
    print("\n  'after fric' applies $4.26/trade. A wider trail takes fewer trades and so")
    print("  pays less total friction -- part of its apparent gain is that, not edge.")

    # -------------------------------------------------------- 1. the holdout
    print("\n" + "=" * 100)
    print(f"  1. TEMPORAL HOLDOUT -- split fixed at {split}, not swept")
    print("=" * 100)
    early = [s for s in sessions if s[1] < split]
    late = [s for s in sessions if s[1] >= split]
    print(f"  EARLY {len(early)} sessions   LATE {len(late)} sessions\n")
    print(f"  {'trail':>6} | {'EARLY net':>11} {'$/tr':>8} {'drop5':>10} "
          f"| {'LATE net':>11} {'$/tr':>8} {'drop5':>10} | {'both halves?':>13}")
    print("  " + "-" * 96)
    base_e = summarise(run(early, LIVE, trail_pct=INCUMBENT), "e")
    base_l = summarise(run(late, LIVE, trail_pct=INCUMBENT), "l")
    for tp in [INCUMBENT] + [c for c in a.candidates if c != INCUMBENT]:
        e = summarise(run(early, LIVE, trail_pct=tp), "e")
        l = summarise(run(late, LIVE, trail_pct=tp), "l")
        if tp == INCUMBENT:
            verdict = "(incumbent)"
        else:
            de, dl = e["net"] - base_e["net"], l["net"] - base_l["net"]
            verdict = "YES" if de > 0 and dl > 0 else ("no" if de <= 0 and dl <= 0 else "SPLIT")
            verdict = f"{verdict} {de:+,.0f}/{dl:+,.0f}"
        print(f"  {tp:>5.0f}% | {e['net']:>+11,.2f} {e['per']:>+8.2f} {e['drop5']:>+10,.2f} "
              f"| {l['net']:>+11,.2f} {l['per']:>+8.2f} {l['drop5']:>+10,.2f} | {verdict:>13}")
    print("\n  A candidate must improve in BOTH halves. One half is a fitted regime.")

    # ------------------------------------------------ 2/3. bootstrap + source
    universe = sorted({s for s, _, _ in sessions})
    base_trades = run(sessions, LIVE, trail_pct=INCUMBENT)
    base_by = per_symbol(base_trades, universe)

    print("\n" + "=" * 100)
    print(f"  2. PAIRED-BY-SYMBOL BOOTSTRAP vs {INCUMBENT:g}%  ({a.resamples:,} resamples of symbols)")
    print("=" * 100)
    print(f"  {'trail':>6} {'delta':>12} {'95% CI':>26} {'P(>0)':>8} "
          f"{'better':>7} {'worse':>6} {'same':>6} {'median':>8}")
    print("  " + "-" * 92)
    detail = {}
    for tp in a.candidates:
        if tp == INCUMBENT:
            continue
        cand_trades = run(sessions, LIVE, trail_pct=tp)
        cand_by = per_symbol(cand_trades, universe)
        delta, lo, hi, p = paired_bootstrap(base_by, cand_by, a.resamples)
        diffs = {s: cand_by[s] - base_by[s] for s in universe}
        better = sum(1 for v in diffs.values() if v > 0.005)
        worse = sum(1 for v in diffs.values() if v < -0.005)
        same = len(diffs) - better - worse
        med = statistics.median(diffs.values())
        detail[tp] = (diffs, cand_trades)
        print(f"  {tp:>5.0f}% {delta:>+12,.2f} {f'[{lo:+,.0f}, {hi:+,.0f}]':>26} "
              f"{p:>7.1f}% {better:>7} {worse:>6} {same:>6} {med:>+8.2f}")
    print("\n  P(>0) is the fraction of resamples in which the candidate beat 5%.")
    print("  A wide CI straddling zero means the sample cannot tell them apart.")

    print("\n" + "=" * 100)
    print("  3. WHERE THE MONEY COMES FROM -- broad, or a few runners?")
    print("=" * 100)
    for tp, (diffs, _) in detail.items():
        top = sorted(diffs.items(), key=lambda kv: kv[1], reverse=True)
        movers = [(s, v) for s, v in top if abs(v) > 0.005]
        gain_top5 = sum(v for _, v in top[:5])
        total = sum(diffs.values())
        share = (gain_top5 / total * 100) if total else 0.0
        print(f"\n  {tp:g}% vs {INCUMBENT:g}%   total {total:+,.2f}   "
              f"top-5 symbols contribute {gain_top5:+,.2f} ({share:.0f}%)")
        print("    best :  " + "  ".join(f"{s} {v:+,.0f}" for s, v in top[:5]))
        print("    worst:  " + "  ".join(f"{s} {v:+,.0f}" for s, v in top[-5:]))
        print(f"    symbols moved at all: {len(movers)} of {len(diffs)}")

    # ------------------------------------------------------- 4. hold and risk
    print("\n" + "=" * 100)
    print("  4. HOLD TIME -- the operational cost of a wider trail")
    print("=" * 100)
    print(f"  {'trail':>6} {'median':>7} {'p90':>6} {'p95':>6} {'max':>7} "
          f"{'>30 bars':>9} {'net in those':>13} {'worst trade':>12}")
    print("  " + "-" * 78)
    for tp in [INCUMBENT] + [c for c in a.candidates if c != INCUMBENT]:
        tr = detail[tp][1] if tp in detail else base_trades
        s = summarise(tr, "")
        long_ = [t for t in tr if t.bars_held > 30]
        worst = min((t.net for t in tr), default=0.0)
        print(f"  {tp:>5.0f}% {s['med']:>7} {s['p90']:>6} {s['p95']:>6} {s['mx']:>7} "
              f"{len(long_):>9} {sum(t.net for t in long_):>+13,.2f} {worst:>+12,.2f}")
    print("\n  The trail is software-managed INSIDE the running process. Outside RTH")
    print("  IBKR takes Day Limit orders only -- there is no native stop resting at")
    print("  the broker. A longer hold is more wall-clock exposure to a crash")
    print("  leaving a position with no protection at all. Past roughly 8% this")
    print("  needs a restart-safe stop, not just a better backtest number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
