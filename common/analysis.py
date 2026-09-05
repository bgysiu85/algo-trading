#!/usr/bin/env python3
"""
Offline analyses over the cached bars. No IB, no pacing, seconds.

    python -m common.analysis --test all
    python -m common.analysis --test holdout
    python -m common.analysis --test concurrency --caps 1 2 3 6

Five questions, in the order they matter:

  holdout      Does apex-off still win when the decision is not made on the
               same data it is measured on? We chose it using all 375
               sessions and reported how good it looks on those 375. This
               splits by DATE and checks both halves.

  concurrency  Is the headline reachable? backtest_session runs each
               symbol/date independently and sums the P&L, as though every
               simultaneous signal could be taken. Live there is one account
               and MAX_SYMBOLS_SAFE = 6.

  trail        With the apex exit gone, the 5% trailing stop and the 09:30
               close ARE the exit logic. 5% was inherited, never justified.

  friction     Roughly half the edge is execution cost. At what friction
               level does this stop being profitable?

  entry        Bounds the intrabar-entry idea: close - low on the entry bar
               is the most perfect timing could ever have gained.

WHY THIS MONKEYPATCHES TRAIL_PCT
--------------------------------
`use_apex` and `require_macd_pos` are per-call overrides on
backtest_session(); TRAIL_PCT is still a module constant. Adding a third
parameter would be the consistent fix, but strategy/mcl/mcl.py is live
trading code that changed today, and an exploratory script is a poor reason
to touch it again before a session. So the sweep sets and restores the
constant around each run, single-threaded, in a try/finally. If the trail
becomes a real tunable, give it the parameter treatment and delete this note.
"""

from __future__ import annotations

import argparse
import collections
import statistics
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.cache_io import (window_dir, check_sessions, slice_sessions,
                             SHARED_DURATION, SHARED_END_HHMM,
                             BACKTEST_SESSIONS, BACKTEST_END_HHMM)
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")

# The shipped configuration, and V7 for comparison.
LIVE = dict(use_apex=False, require_macd_pos=True)
V7 = dict(use_apex=True, require_macd_pos=True)

# Measured on 2026-09-03: net round-trip slippage beyond the one tick each way
# the engine already models, on 100 shares. BUY came in favourable
# (+$0.0164/share), SELL unfavourable (-$0.0590), net -$0.0426/share.
MEASURED_FRICTION = 4.26


# --------------------------------------------------------------- loading

def load_sessions(cache_root: Path):
    """(symbol, date, frame) sliced exactly as the backtest engine slices."""
    d = window_dir(cache_root, SHARED_DURATION, SHARED_END_HHMM)
    files = sorted(d.glob("*.csv.gz"))
    if not files:
        sys.exit(f"{d}/ is empty. Run main.py --mode backtest --strategy mcl first.")
    end_h, end_m = int(BACKTEST_END_HHMM[:2]), int(BACKTEST_END_HHMM[2:])
    out, skipped = [], 0
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
        df = df.sort_index()
        want_end = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=end_h, minute=end_m, tzinfo=ET)
        if check_sessions(df, want_end, BACKTEST_SESSIONS) < BACKTEST_SESSIONS:
            skipped += 1
            continue
        sl = slice_sessions(df, want_end, BACKTEST_SESSIONS)
        if not sl.empty:
            out.append((symbol, date_str, sl))
    if skipped:
        print(f"  ({skipped} session(s) skipped: too short for full warm-up)")
    return out


def run(sessions, opts, trail_pct: float | None = None):
    """Every trade across every session, tagged with its symbol and date."""
    original = S.TRAIL_PCT
    try:
        if trail_pct is not None:
            S.TRAIL_PCT = trail_pct
        out = []
        for symbol, date_str, df in sessions:
            for t in S.backtest_session(df, datetime.strptime(date_str, "%Y-%m-%d").date(),
                                        ET, **opts):
                t.symbol = symbol
                t.date = date_str
                out.append(t)
        return out
    finally:
        S.TRAIL_PCT = original


def stats(trades, label=""):
    if not trades:
        return dict(label=label, n=0, net=0.0, per=0.0, win=0.0)
    net = sum(t.net for t in trades)
    per_sym = collections.defaultdict(float)
    for t in trades:
        per_sym[t.symbol] += t.net
    top = sorted(per_sym.values(), reverse=True)
    return dict(label=label, n=len(trades), net=net, per=net / len(trades),
                win=sum(1 for t in trades if t.net > 0) / len(trades) * 100,
                syms=len(per_sym), drop5=net - sum(top[:5]))


def line(s):
    if not s["n"]:
        return f"  {s['label']:<28} no trades"
    return (f"  {s['label']:<28} {s['n']:>5} tr  {s['net']:>+10,.2f}  "
            f"{s['per']:>+7.2f}/tr  win {s['win']:>5.1f}%  "
            f"drop5 {s['drop5']:>+9,.2f}")


# --------------------------------------------------------------- 1. holdout

def test_holdout(sessions):
    print("\n" + "=" * 78)
    print("  1. TEMPORAL HOLDOUT -- was apex-off chosen on the data it is judged on?")
    print("=" * 78)
    dates = sorted({d for _, d, _ in sessions})
    mid = dates[len(dates) // 2]
    print(f"  {len(dates)} distinct dates, {dates[0]} .. {dates[-1]}   split at {mid}\n")

    for name, keep in (("EARLY", lambda d: d < mid), ("LATE ", lambda d: d >= mid)):
        sub = [s for s in sessions if keep(s[1])]
        a = stats(run(sub, V7), f"{name}  V7 (apex ON)")
        b = stats(run(sub, LIVE), f"{name}  apex OFF")
        print(f"  --- {name.strip()}: {len(sub)} sessions ---")
        print(line(a)); print(line(b))
        if a["n"] and b["n"]:
            print(f"      improvement {b['net'] - a['net']:>+10,.2f}"
                  f"   per trade {b['per'] - a['per']:>+6.2f}\n")

    print("  The improvement must appear in BOTH halves. Winning only in one")
    print("  means a regime was fitted, not a rule found.")


# ----------------------------------------------------------- 2. concurrency

def test_concurrency(sessions, caps):
    print("\n" + "=" * 78)
    print("  2. CONCURRENCY -- is the headline actually reachable?")
    print("=" * 78)
    trades = run(sessions, LIVE)
    for t in trades:
        t._in = pd.Timestamp(t.entry_time)
        t._out = pd.Timestamp(t.exit_time)
    total = sum(t.net for t in trades)
    print(f"  unconstrained: {len(trades)} trades, {total:+,.2f}"
          f"   (what backtest_session reports)\n")

    by_date = collections.defaultdict(list)
    for t in trades:
        by_date[t.date].append(t)

    overlaps = 0
    for day in by_date.values():
        day.sort(key=lambda t: t._in)
        for i, t in enumerate(day):
            if any(o._in <= t._in < o._out for o in day[:i]):
                overlaps += 1
    print(f"  trades entered while another was already open: {overlaps}"
          f"  ({overlaps/len(trades)*100:.1f}%)\n")

    print(f"  {'cap':>5}  {'taken':>6}  {'skipped':>8}  {'net':>12}  {'% of total':>11}")
    print("  " + "-" * 50)
    for cap in caps:
        taken, skipped = [], 0
        for day in by_date.values():
            open_until = []          # exit times of positions currently held
            for t in sorted(day, key=lambda t: t._in):
                open_until = [x for x in open_until if x > t._in]
                if len(open_until) < cap:
                    taken.append(t)
                    open_until.append(t._out)
                else:
                    skipped += 1
        net = sum(t.net for t in taken)
        print(f"  {cap:>5}  {len(taken):>6}  {skipped:>8}  {net:>+12,.2f}  "
              f"{net/total*100 if total else 0:>10.1f}%")

    print("\n  First-come-first-served, which is how the live trader behaves.")
    print("  If a low cap keeps most of the P&L, concurrency is a non-issue.")


# ---------------------------------------------------------------- 3. trail

def test_trail(sessions, trails):
    print("\n" + "=" * 78)
    print("  3. TRAIL_PCT -- the only exit parameter left after apex removal")
    print("=" * 78)
    print(f"  currently {S.TRAIL_PCT}%\n")
    print(f"  {'trail%':>7}  {'trades':>7}  {'net':>11}  {'$/trade':>9}  "
          f"{'win%':>6}  {'med hold':>9}  {'drop5':>10}")
    print("  " + "-" * 68)
    for tp in trails:
        tr = run(sessions, LIVE, trail_pct=tp)
        s = stats(tr)
        hold = statistics.median([t.bars_held for t in tr]) if tr else 0
        mark = "  <- current" if abs(tp - 5.0) < 1e-9 else ""
        print(f"  {tp:>7.1f}  {s['n']:>7}  {s['net']:>+11,.2f}  {s['per']:>+9.2f}  "
              f"{s['win']:>6.1f}  {hold:>9.0f}  {s['drop5']:>+10,.2f}{mark}")
    print("\n  A tighter trail cuts the long holds apex-removal just enabled,")
    print("  so it partly undoes that change -- read the curve, not one cell.")


# ------------------------------------------------------------- 4. friction

def test_friction(sessions):
    print("\n" + "=" * 78)
    print("  4. FRICTION -- how much execution cost does this survive?")
    print("=" * 78)
    for label, opts in (("V7 (apex ON)", V7), ("shipped (apex OFF)", LIVE)):
        tr = run(sessions, opts)
        if not tr:
            continue
        n, net = len(tr), sum(t.net for t in tr)
        be = net / n
        print(f"\n  {label}: {n} trades, {net:+,.2f}, {be:+.2f}/trade")
        print(f"    break-even friction: {be:+.2f}/round trip "
              f"({be/100:+.4f}/share on 100)")
        print(f"    {'friction/trade':>15}  {'net':>12}  {'$/trade':>9}")
        for f in (0.0, 1.0, 2.0, MEASURED_FRICTION, 6.0, 8.0):
            tag = "  <- measured 2026-09-03" if f == MEASURED_FRICTION else ""
            print(f"    {f:>15.2f}  {net - f*n:>+12,.2f}  {be - f:>+9.2f}{tag}")


# ---------------------------------------------------------------- 5. entry

def test_entry(sessions):
    print("\n" + "=" * 78)
    print("  5. ENTRY TIMING -- ceiling on what intrabar entry could ever gain")
    print("=" * 78)
    frames = {(sym, d): df for sym, d, df in sessions}
    gaps, entry_trades = [], []
    for t in run(sessions, LIVE):
        df = frames.get((t.symbol, t.date))
        if df is None:
            continue
        try:
            bar = df.loc[pd.Timestamp(t.entry_time)]
        except KeyError:
            continue
        lo, close = float(bar["low"]), float(bar["close"])
        if close > 0:
            gaps.append((close - lo, (close - lo) / close * 100))
            entry_trades.append(t)
    if not gaps:
        print("  could not match entry bars")
        return
    cents = sorted(g[0] for g in gaps)
    pcts = sorted(g[1] for g in gaps)
    q = lambda xs, p: xs[min(int(len(xs) * p), len(xs) - 1)]
    mean = sum(cents) / len(cents)
    print(f"  {len(gaps)} entries matched to their bar\n")
    print(f"    close - low    median ${q(cents,.5):.3f}   mean ${mean:.3f}"
          f"   p75 ${q(cents,.75):.3f}   p90 ${q(cents,.9):.3f}")
    print(f"    as pct of px   median {q(pcts,.5):.2f}%   p90 {q(pcts,.9):.2f}%")
    print(f"\n    PERFECT intrabar entry ceiling: {mean*100:+,.2f}/trade "
          f"on 100 shares")
    print("    (buying the exact low of every signal bar -- unachievable, but")
    print("     nothing about better entry timing can be worth more than this)")

    # The distribution matters more than the average. If the wide bars are the
    # ones that WIN, better entry amplifies winners; if they are the losers,
    # it mostly rescues bad trades, which is a different and weaker case.
    w = [g for g, t in zip(gaps, entry_trades) if t.net > 0]
    l = [g for g, t in zip(gaps, entry_trades) if t.net <= 0]
    if w and l:
        print(f"\n    on WINNING trades  n={len(w):<4} mean gap ${sum(x[0] for x in w)/len(w):.3f}")
        print(f"    on LOSING trades   n={len(l):<4} mean gap ${sum(x[0] for x in l)/len(l):.3f}")
        print("    Wider gaps on winners means better entry would amplify the")
        print("    tail; wider on losers means it mostly rescues bad trades.")

    print("\n  Compare against the current edge per trade. A ceiling far above")
    print("  it means tick data is worth buying; far below, the idea is dead.")
    print("  Expect heavy right skew -- the biggest winners enter on violent")
    print("  bars, which is exactly where the close is worst.")


# ----------------------------------------------------------------- driver

def main() -> int:
    ap = argparse.ArgumentParser(description="Offline analyses over cached bars")
    ap.add_argument("--test", default="all",
                    choices=["all", "holdout", "concurrency", "trail",
                             "friction", "entry"])
    ap.add_argument("--cache-dir", default="bar_cache")
    ap.add_argument("--caps", type=int, nargs="+", default=[1, 2, 3, 6])
    ap.add_argument("--trails", type=float, nargs="+",
                    default=[2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0])
    a = ap.parse_args()

    sessions = load_sessions(Path(a.cache_dir))
    print(f"{len(sessions)} cached sessions, "
          f"{len({s for s, _, _ in sessions})} symbols")

    which = ([a.test] if a.test != "all"
             else ["holdout", "concurrency", "trail", "friction", "entry"])
    for t in which:
        {"holdout": lambda: test_holdout(sessions),
         "concurrency": lambda: test_concurrency(sessions, a.caps),
         "trail": lambda: test_trail(sessions, a.trails),
         "friction": lambda: test_friction(sessions),
         "entry": lambda: test_entry(sessions)}[t]()
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
