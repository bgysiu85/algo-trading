#!/usr/bin/env python3
"""Does ADDING shares on a recovered pullback beat simply starting bigger?

    python -m common.pyramid_study

Ben's question after the scale-out exit was rejected: forget the selling --
if a pullback recovers, just buy MORE. Nothing is sold early, so none of the
sell-low / buy-back-higher cost that sank the scale-out applies.

THE CONTROL IS THE WHOLE STUDY
------------------------------
On a dataset whose average trade is positive, ANY extra size looks better.
100 -> 200 shares doubles the P/L and proves nothing. So a pyramid that
builds 100 -> 200 is not compared against 100 shares; it is compared against
**200 shares held from the entry**. If the pyramid only matches that, the
timing is worth nothing and the gain was leverage all along.

Three things are reported for every configuration:

  net           what it made
  per $ risked  net divided by the capital actually tied up (max shares held
                x entry price, summed over trades). This is the number that is
                comparable across sizes -- P/L alone is not.
  max notional  the largest single position in dollars, against net liq
                $4,131.89. A configuration the account cannot fund is not a
                configuration.

Concentration (drop-top-5) is reported too, because a size increase magnifies
the tail as much as the middle.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.analysis import load_sessions, LIVE
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")
NET_LIQ = 4_131.89

# Measured live 2026-09-03 (common/friction.py), charged per share TRANSACTED
# so that added shares are actually paid for.
SLIP_PER_SHARE = (0.0590 - 0.0164) / 2
REBUY_SLIP_BPS = 40.0


def run(sessions, **kw):
    per_sym, rows = {}, []
    for symbol, date_str, df in sessions:
        for t in S.backtest_session(
                df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET,
                **LIVE, rebuy_slip_bps=REBUY_SLIP_BPS, **kw):
            real = t.net - t.shares_traded * SLIP_PER_SHARE
            per_sym[symbol] = per_sym.get(symbol, 0.0) + real
            rows.append((real, t.max_qty, t.entry_price, t.adds))
    if not rows:
        return None
    net = sum(r[0] for r in rows)
    capital = sum(r[1] * r[2] for r in rows)
    top = sorted(per_sym.values(), reverse=True)
    return dict(
        trades=len(rows), net=net, per=net / len(rows),
        drop5=net - sum(top[:5]),
        ret=100.0 * net / capital if capital else 0.0,
        max_notional=max(r[1] * r[2] for r in rows),
        max_shares=max(r[1] for r in rows),
        adds=sum(r[3] for r in rows),
    )


def show(tag, r):
    if r is None:
        print(f"  {tag:<38}  (no trades)")
        return
    flag = "  <-- exceeds account" if r["max_notional"] > NET_LIQ else ""
    print(f"  {tag:<38} ${r['net']:>8,.0f} ${r['per']:>7.2f} "
          f"${r['drop5']:>8,.0f} {r['ret']:>7.3f}% "
          f"{r['max_shares']:>5} ${r['max_notional']:>8,.0f}{flag}")


HEAD = (f"  {'configuration':<38} {'net':>9} {'per tr':>8} {'drop5':>9} "
        f"{'per $':>8} {'maxsh':>5} {'max notional':>9}")


def main() -> int:
    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    early = [s for s in sessions if s[1] < split]
    late = [s for s in sessions if s[1] >= split]
    print(f"{len(sessions)} sessions, holdout split {split}, "
          f"net liq ${NET_LIQ:,.2f}\n")

    print("1. FLAT SIZE -- the control. Size is a near-pure multiplier, so")
    print("   these are what any pyramid has to beat, not the 100-share row.")
    print(HEAD)
    flat = {}
    for q in (100, 150, 200, 300, 400):
        flat[q] = run(sessions, entry_shares=q)
        show(f"flat {q} shares from entry", flat[q])

    print("\n2. PYRAMID -- enter 100, add on a pullback that reclaims its peak")
    print(HEAD)
    best = None
    for pull in (1.0, 2.0, 2.5, 3.0, 4.0):
        for add in (50, 100, 200):
            for cap in (1, 2, None):
                r = run(sessions, entry_shares=100, pyramid_qty=add,
                        pyramid_pullback_pct=pull, max_adds=cap)
                tag = (f"100 +{add} on -{pull:g}% dip, "
                       f"max {cap if cap else 'inf'} adds")
                show(tag, r)
                if r and (best is None or r["ret"] > best[1]["ret"]):
                    best = (dict(entry_shares=100, pyramid_qty=add,
                                 pyramid_pullback_pct=pull, max_adds=cap), r)

    print("\n3. THE COMPARISON THAT MATTERS")
    print("   Each pyramid against the FLAT size closest to what it builds to.")
    print(HEAD)
    for pull, add, cap, ctrl in ((2.5, 100, 1, 200), (2.5, 100, 2, 300),
                                 (2.0, 100, 1, 200), (1.0, 100, 1, 200),
                                 (2.5, 50, 1, 150), (2.5, 200, 1, 300)):
        r = run(sessions, entry_shares=100, pyramid_qty=add,
                pyramid_pullback_pct=pull, max_adds=cap)
        show(f"pyramid 100 +{add} @-{pull:g}% x{cap}", r)
        show(f"   control: flat {ctrl}", flat[ctrl])
        if r:
            print(f"   -> pyramid earns {r['ret']:.3f}% per $ vs "
                  f"{flat[ctrl]['ret']:.3f}% flat: "
                  f"{'BETTER' if r['ret'] > flat[ctrl]['ret'] else 'WORSE'}\n")

    if best:
        kw, r = best
        print("4. HOLDOUT on the best pyramid by return per dollar")
        print(f"   {kw}")
        print(HEAD)
        show("early half", run(early, **kw))
        show("late  half", run(late, **kw))
        ctrl = min(flat, key=lambda q: abs(q - r["max_shares"]))
        show(f"early, flat {ctrl} control", run(early, entry_shares=ctrl))
        show(f"late,  flat {ctrl} control", run(late, entry_shares=ctrl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
