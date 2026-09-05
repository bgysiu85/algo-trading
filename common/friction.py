#!/usr/bin/env python3
"""
Measure execution friction from the live fill logs. No IB, no market data.

    python -m common.friction                       # every session in var/fills
    python -m common.friction --session 20260903    # one session
    python -m common.friction --shares 100          # scale to a different size

WHY THIS EXISTS
---------------
The single most load-bearing number in this project is "~$4.26 per round trip",
and it comes from ONE session (2026-09-03). Every acceptance decision is
measured against it: apex-on was rejected because +$3.86/trade does not clear
it, apex-off accepted because +$7.79 does. If that figure is understated the
edge is not thin, it is absent -- and the backtest would never show it.

`claude/mcl_robustness_analysis.md` therefore lists "re-measure friction every
live session" as standing work. This makes that a one-command job instead of a
hand analysis, so the estimate accumulates a sample size instead of staying at
n=1.

WHAT FRICTION MEANS HERE
------------------------
It is the execution cost the backtest does NOT already model -- not the total
cost. The engine already charges $0.005/share commission and one tick of
slippage each way. This measures the slippage BEYOND that reference, which is
what `slippage_vs_ref` in the fill log records.

SIGN CONVENTION, WHICH IS EASY TO GET BACKWARDS
-----------------------------------------------
trader.py computes the COST as (fill - ref) on a buy and (ref - fill) on a
sell, then logs its NEGATION. So in the CSV:

    slippage_vs_ref > 0  ->  FAVOURABLE (bought below / sold above reference)
    slippage_vs_ref < 0  ->  UNFAVOURABLE

Both directions use the same convention, so they can be summed directly. The
column comment in trader.py's FIELDS says "fill - ref_close", which describes
the quantity before that negation -- read the code, not the comment.

The asymmetry is the finding worth watching: buys have come in favourable and
sells unfavourable, because exits are trailing stops firing into a falling bid
with no resting stop at the broker (outside RTH, IBKR takes Day Limit orders
only). More trailing exits therefore means more exposure to the worse side --
which is exactly what removing the apex exit did.
"""

from __future__ import annotations

import argparse
import collections
import csv
import statistics
import sys
from pathlib import Path

FILLS_DIR = Path("var/fills")

# NOTE there is deliberately no commission constant here. This module measures
# the PRICE gap -- where the order actually filled against the price the engine
# modelled -- and commission is charged separately, per order, by
# common/commissions.py in both the backtest and the live trader. A constant
# here (there used to be one, unused, at the old flat $0.005/share) invites the
# reader to think commission has been netted out of these figures. It has not.

# The published figure, for comparison. One session, 2026-09-03.
PUBLISHED_ROUND_TRIP_100 = 4.26

FILLED = ("FILLED", "PARTIAL_FILL")

# The exit mix the SHIPPED configuration produces, from the V11 (apex OFF,
# MACD>0 ON) cell of common/sweep_variants.py over 373 cached sessions:
# 533 trailing-stop exits against 27 at the window close, no apex exits at all.
# Kept here because it is what makes the measured friction comparable -- or
# not -- to what live will actually pay. See exit_mix_warning().
SHIPPED_EXIT_MIX = {"trailing_stop": 0.95, "window_close": 0.05}


def exit_mix_warning(rows, shares):
    """Is the measured friction representative of what the strategy now does?

    This is the sharpest thing in the report and the reason it exists.

    Friction is not one number, it is a per-exit-reason number, and the reasons
    have wildly different costs: a trailing stop fires INTO a falling bid with
    no resting stop at the broker, while an apex exit closes a position the
    trail has not touched, in whatever market happens to be there.

    The $4.26 estimate was measured on 2026-09-03, a session in which 84% of
    exits were apex_reversal. Apex was disabled on 2026-09-05, so roughly 95%
    of exits from here are trailing stops -- the expensive kind. The estimate
    was taken under an exit mix that no longer exists.

    This does not say friction is higher. It says the sample does not answer
    the question any more, which is worse than a wrong number because it looks
    like a right one.
    """
    sells = [r for r in rows if r["action"] == "SELL"]
    if not sells:
        return
    mix = collections.Counter(r.get("reason", "?") for r in sells)
    n = len(sells)
    trailing = [r["_slip"] for r in sells if r.get("reason") == "trailing_stop"]
    apex = [r["_slip"] for r in sells if r.get("reason") == "apex_reversal"]

    print("\n" + "=" * 78)
    print("  EXIT MIX -- is this friction estimate still representative?")
    print("=" * 78)
    print(f"  measured mix over {n} exits:")
    for reason, c in mix.most_common():
        print(f"    {reason:<20} {c:>4}  {c/n*100:>5.1f}%")
    print("\n  shipped configuration (apex OFF) produces, per the V11 backtest:")
    for reason, share in SHIPPED_EXIT_MIX.items():
        print(f"    {reason:<20} {'':>4}  {share*100:>5.1f}%")

    if apex and mix.get("apex_reversal", 0) / n > 0.25:
        print(f"\n  WARNING: {mix['apex_reversal']/n*100:.0f}% of measured exits are "
              f"apex_reversal, a rule that is now DISABLED.")
        print("  The friction estimate was taken under an exit mix the strategy no")
        print("  longer produces. It is not wrong, it is answering a stale question.")

    if trailing:
        m = statistics.fmean(trailing)
        print(f"\n  trailing-stop exits measured: n={len(trailing)}, "
              f"mean {m:+.4f}/share = ${-m*shares:,.2f} per {shares} sh")
        if apex:
            a = statistics.fmean(apex)
            print(f"  apex exits measured:          n={len(apex)}, "
                  f"mean {a:+.4f}/share = ${-a*shares:,.2f} per {shares} sh")
        if len(trailing) < 5:
            print(f"\n  With n={len(trailing)} trailing exits there is effectively NO "
                  "estimate for the\n  exit type that will now produce ~95% of "
                  "fills. This is the single\n  largest hole in the evidence chain "
                  "-- larger than any parameter question.")


def load(session: str | None, fills_dir: Path):
    """Rows that represent a real fill, grouped by session date."""
    if not fills_dir.exists():
        sys.exit(f"{fills_dir}/ does not exist. Nothing to measure yet.")
    files = sorted(fills_dir.glob("mcl_fills_*.csv"))
    if not files:
        sys.exit(f"no mcl_fills_*.csv in {fills_dir}/")

    by_session = collections.OrderedDict()
    for f in files:
        # mcl_fills_20260903.csv, and the rolled-aside mcl_fills_20260902_pre180819.csv
        stem = f.stem[len("mcl_fills_"):]
        day = stem.split("_")[0]
        if session and day != session:
            continue
        try:
            rows = list(csv.DictReader(f.open(newline="")))
        except OSError as e:  # noqa: BLE001
            print(f"  ! could not read {f.name}: {e}")
            continue
        keep = []
        for r in rows:
            if r.get("status") not in FILLED:
                continue
            try:
                r["_slip"] = float(r["slippage_vs_ref"])
                r["_qty"] = int(float(r["filled_qty"] or r["qty"] or 0))
            except (TypeError, ValueError):
                continue
            if r["_qty"] <= 0:
                continue
            keep.append(r)
        if keep:
            by_session.setdefault(day, []).extend(keep)
    if not by_session:
        sys.exit("no filled rows found" + (f" for session {session}" if session else ""))
    return by_session


def side_stats(rows, action):
    xs = [r["_slip"] for r in rows if r["action"] == action]
    if not xs:
        return None
    return dict(n=len(xs), mean=statistics.fmean(xs),
                median=statistics.median(xs), worst=min(xs), best=max(xs))


def report_session(day, rows, shares, show_reasons):
    buys = side_stats(rows, "BUY")
    sells = side_stats(rows, "SELL")
    print(f"\n  --- {day} ---  {len(rows)} fills")

    if not (buys and sells):
        print("    incomplete: needs both buys and sells to form a round trip")
        return None

    print(f"    {'side':<6} {'n':>4} {'mean/sh':>10} {'median/sh':>11} "
          f"{'worst/sh':>10} {'best/sh':>9}")
    for name, s in (("BUY", buys), ("SELL", sells)):
        print(f"    {name:<6} {s['n']:>4} {s['mean']:>+10.4f} {s['median']:>+11.4f} "
              f"{s['worst']:>+10.4f} {s['best']:>+9.4f}")

    # A round trip is one buy plus one sell. Use the means so an unequal count
    # of buys and sells (an open position at session end) does not distort it.
    net_per_share = buys["mean"] + sells["mean"]
    friction_per_share = -net_per_share          # cost is positive
    rt = friction_per_share * shares

    print(f"\n    net slippage        {net_per_share:+.4f}/share "
          f"({'favourable' if net_per_share > 0 else 'unfavourable'})")
    print(f"    FRICTION            ${rt:,.2f} per {shares}-share round trip, "
          f"beyond the tick-each-way already modelled")
    print(f"    published figure    ${PUBLISHED_ROUND_TRIP_100:,.2f} "
          f"(2026-09-03, {shares} shares)")

    if show_reasons:
        by_reason = collections.defaultdict(list)
        for r in rows:
            if r["action"] == "SELL":
                by_reason[r.get("reason", "?")].append(r["_slip"])
        if by_reason:
            print("\n    sell slippage by exit reason "
                  "(trailing exits fire into a falling bid):")
            for reason, xs in sorted(by_reason.items(),
                                     key=lambda kv: statistics.fmean(kv[1])):
                print(f"      {reason:<20} n={len(xs):<4} "
                      f"mean {statistics.fmean(xs):+.4f}/share  "
                      f"= ${-statistics.fmean(xs)*shares:>7,.2f} per {shares} sh")

    return dict(day=day, fills=len(rows), buys=buys["n"], sells=sells["n"],
                buy_mean=buys["mean"], sell_mean=sells["mean"],
                per_share=friction_per_share, round_trip=rt)


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure execution friction from fill logs")
    ap.add_argument("--fills-dir", default=str(FILLS_DIR))
    ap.add_argument("--session", help="YYYYMMDD; default every session found")
    ap.add_argument("--shares", type=int, default=100,
                    help="round-trip size to quote (default 100, matching the "
                         "sizing rule and every published figure)")
    ap.add_argument("--no-reasons", action="store_true")
    a = ap.parse_args()

    by_session = load(a.session, Path(a.fills_dir))
    print(f"friction from {len(by_session)} session(s) in {a.fills_dir}/")
    print("positive slippage = favourable; friction is its negation, per "
          f"{a.shares}-share round trip")

    results = [r for r in (report_session(d, rows, a.shares, not a.no_reasons)
                           for d, rows in by_session.items()) if r]

    if not results:
        print("\nNo complete session. Nothing to aggregate.")
        return 0

    print("\n" + "=" * 78)
    print("  ACROSS SESSIONS -- this is what stops $4.26 being an n=1 figure")
    print("=" * 78)
    print(f"  {'session':<12} {'fills':>6} {'buy/sh':>9} {'sell/sh':>9} "
          f"{'friction':>12}")
    print("  " + "-" * 54)
    for r in results:
        print(f"  {r['day']:<12} {r['fills']:>6} {r['buy_mean']:>+9.4f} "
              f"{r['sell_mean']:>+9.4f} {r['round_trip']:>+12,.2f}")

    rts = [r["round_trip"] for r in results]
    total_fills = sum(r["fills"] for r in results)
    mean_rt = statistics.fmean(rts)
    print("  " + "-" * 54)
    print(f"  {'mean':<12} {total_fills:>6} {'':>9} {'':>9} {mean_rt:>+12,.2f}")
    if len(rts) > 1:
        print(f"  {'range':<12} {'':>6} {'':>9} {'':>9} "
              f"{f'{min(rts):,.2f} .. {max(rts):,.2f}':>12}")
        print(f"  {'stdev':<12} {'':>6} {'':>9} {'':>9} "
              f"{statistics.stdev(rts):>12,.2f}")

    all_rows = [r for rows in by_session.values() for r in rows]
    exit_mix_warning(all_rows, a.shares)

    print(f"\n  n = {len(rts)} session(s). The published $4.26 came from one.")
    print("  A strategy's $/trade must clear this figure to have any edge at all;")
    print("  MCL as shipped is +$7.79/trade before it.")
    if len(rts) < 3:
        print("\n  WARNING: fewer than 3 sessions. This is still an anecdote, not")
        print("  an estimate. Do not re-tune parameters against it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
