#!/usr/bin/env python3
"""Separate the scale-out IDEA from the leverage it smuggles in.

    python -m common.scale_regimes

The 4,900-cell grid keeps returning a 4/4 boundary optimum -- widest trail,
smallest pullback, smallest portion sold, largest quantity bought back. Read
literally that is "sell as little as possible and buy back as much as possible
on every 0.5% wiggle", which is not an exit rule at all; it is an accumulator
whose position size compounds. A search that is free to add size will always
find that, on a dataset whose average trade is positive, so the grid cannot
answer whether the mechanic is any good.

So run it three ways, changing ONE thing:

    NEUTRAL   rebuy restores exactly what was sold; size is constant.
              This is the mechanic and nothing else.
    CAPPED    rebuy is a fixed quantity, but the position may never exceed
              max_position_shares. A real pyramid with a risk limit.
    UNCAPPED  what the grid searched. Reported with the position sizes it
              actually reaches, which is the part that disqualifies it.

The comparison in every case is against the SAME trail with no scale-out, so
what is being measured is the mechanic rather than the trail.
"""
from __future__ import annotations

from pathlib import Path

from common.analysis import load_sessions
from common.scale_grid import prepare, evaluate

ENTRY_SHARES = 100          # strategy/mcl/mcl.py size_for() over the $2-20 band
TRAILS = [5.0, 8.0, 10.0, 15.0]
PARTIALS = [0.5, 1.0, 2.5, 5.0]
PORTIONS = [20.0, 50.0, 75.0]


def line(tag, r, base):
    if r is None:
        return f"  {tag:<34}      (no trades)"
    d = r["real"] - base["real"]
    return (f"  {tag:<34} ${r['real']:>9,.0f}  ${r['real_per']:>6.2f}/tr  "
            f"drop5 ${r['drop5']:>8,.0f}  {d:>+9,.0f}  "
            f"maxq {r['max_qty']:>5}  cyc {r['cycles']:>5}")


def main() -> int:
    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    prepared = prepare(sessions)
    early = prepare([s for s in sessions if s[1] < split])
    late = prepare([s for s in sessions if s[1] >= split])

    for trail in TRAILS:
        base = evaluate(prepared, trail, 2.5, 0.0, 100)
        print(f"\n=== TRAIL {trail:g}%  "
              f"baseline ${base['real']:,.0f}  ${base['real_per']:.2f}/trade  "
              f"{base['trades']} trades ===")
        print("  regime / partial x portion              real    per-trade"
              "        drop5      vs base   max size  cycles")
        for partial in PARTIALS:
            for portion in PORTIONS:
                tag = f"NEUTRAL  p{partial:g}% x{portion:g}%"
                print(line(tag, evaluate(prepared, trail, partial, portion,
                                         None), base))
        # Capped growth: allow up to 2x the entry size, bought 100 at a time.
        for partial in PARTIALS:
            for portion in PORTIONS:
                tag = f"CAPPED2x p{partial:g}% x{portion:g}%"
                print(line(tag, evaluate(prepared, trail, partial, portion,
                                         100, max_position_shares=2 * ENTRY_SHARES),
                           base))

    # --- what the unconstrained grid winner actually asks for ---------------
    print("\n=== THE UNCAPPED GRID WINNER, with its size requirement ===")
    for label, prep in (("all", prepared), ("early", early), ("late", late)):
        base = evaluate(prep, 15.0, 2.5, 0.0, 100)
        r = evaluate(prep, 15.0, 0.5, 20.0, 150)
        print(f"  {label:<6} " + line("trail15 p0.5 x20 +150", r, base).strip())
    print("\n  Same cell with the position capped at 2x entry size:")
    for label, prep in (("all", prepared), ("early", early), ("late", late)):
        base = evaluate(prep, 15.0, 2.5, 0.0, 100)
        r = evaluate(prep, 15.0, 0.5, 20.0, 150,
                     max_position_shares=2 * ENTRY_SHARES)
        print(f"  {label:<6} " + line("trail15 p0.5 x20 +150 cap200", r, base).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
