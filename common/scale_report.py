#!/usr/bin/env python3
"""Read a scale_grid CSV and answer the only three questions that matter.

    python -m common.scale_report var/reports/scale_grid_peak.csv

    1. Is the in-sample optimum on a grid boundary? A boundary optimum means
       the search wanted to keep going, which almost always means the model is
       being arbitraged rather than a parameter fitted.
    2. Does the cell chosen on the EARLY half still work on the LATE half?
    3. Does it beat the no-scale-out baseline AT THE SAME TRAIL? Comparing a
       15% trail with scale-out against a 5% trail without it measures the
       trail, not the mechanic -- that confusion cost a whole round of this
       study.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from common.analysis import load_sessions
from common.scale_grid import prepare, evaluate, TRAILS


def baselines(prepared):
    """No scale-out at every trail. portion=0 makes the mechanic inert:
    sell_q rounds to 0 shares and the `1 <= sell_q` guard rejects it."""
    return {t: evaluate(prepared, t, 2.5, 0.0, 100) for t in TRAILS}


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "var/reports/scale_grid_peak.csv")
    rows = []
    with path.open() as fh:
        for r in csv.DictReader(fh):
            rows.append({k: (float(v) if v not in ("", "nan") else float("nan"))
                         for k, v in r.items()})

    sessions = load_sessions(Path("bar_cache"))
    dates = sorted({d for _, d, _ in sessions})
    split = dates[len(dates) // 2]
    base = baselines(prepare(sessions))
    early_base = baselines(prepare([s for s in sessions if s[1] < split]))
    late_base = baselines(prepare([s for s in sessions if s[1] >= split]))

    print(f"{len(rows):,} cells from {path}\n")

    # --- 1. in-sample optimum and whether it sits on a boundary -------------
    best = max(rows, key=lambda r: r["real_net"])
    edges = {
        "trail": (min(TRAILS), max(TRAILS)),
        "partial": (0.5, 5.0), "portion": (20.0, 80.0), "rebuy": (50.0, 150.0),
    }
    got = {"trail": best["trail_pct"], "partial": best["partial_pct"],
           "portion": best["portion_pct"], "rebuy": best["rebuy_qty"]}
    on_edge = [k for k, v in got.items() if v in edges[k]]
    print("IN-SAMPLE BEST (by real net, after measured slippage)")
    print(f"  trail {got['trail']}%  partial {got['partial']}%  "
          f"portion {got['portion']}%  rebuy {got['rebuy']:.0f}")
    print(f"  {best['trades']:.0f} trades  real ${best['real_net']:,.0f}  "
          f"${best['real_per_trade']:.2f}/trade  drop5 ${best['drop5']:,.0f}")
    b = base[got["trail"]]
    print(f"  baseline at the SAME trail: ${b['real']:,.0f}  "
          f"${b['real_per']:.2f}/trade over {b['trades']} trades")
    print(f"  boundary params: {on_edge or 'none'}  "
          f"({len(on_edge)}/4 pinned)")
    beat = sum(1 for r in rows
               if r["real_net"] > base[r["trail_pct"]]["real"])
    print(f"  cells beating their OWN-TRAIL baseline: {beat:,}/{len(rows):,} "
          f"({100*beat/len(rows):.0f}%)\n")

    # --- 2. honest holdout --------------------------------------------------
    pick = max(rows, key=lambda r: r["early_real"])
    print(f"HOLDOUT  (choose on dates < {split}, score on >= {split})")
    print(f"  chosen: trail {pick['trail_pct']}%  partial {pick['partial_pct']}%"
          f"  portion {pick['portion_pct']}%  rebuy {pick['rebuy_qty']:.0f}")
    eb = early_base[pick["trail_pct"]]
    lb = late_base[pick["trail_pct"]]
    print(f"  early  ${pick['early_real']:,.0f}  vs baseline ${eb['real']:,.0f}"
          f"   -> edge ${pick['early_real']-eb['real']:+,.0f}")
    print(f"  late   ${pick['late_real']:,.0f}  vs baseline ${lb['real']:,.0f}"
          f"   -> edge ${pick['late_real']-lb['real']:+,.0f}")
    print("  the LATE line is the only one that was not chosen on\n")

    # --- 3. the mechanic at the trail actually shipped ----------------------
    print("AT THE SHIPPED 5% TRAIL -- what the mechanic itself is worth")
    b5 = base[5.0]
    print(f"  baseline                     ${b5['real']:>9,.0f}  "
          f"${b5['real_per']:>6.2f}/trade  drop5 ${b5['net']-0:>9,.0f}")
    at5 = [r for r in rows if r["trail_pct"] == 5.0]
    at5.sort(key=lambda r: -r["real_net"])
    for r in at5[:8]:
        print(f"  p{r['partial_pct']:<4} x{r['portion_pct']:<4.0f}% "
              f"+{r['rebuy_qty']:<4.0f}sh         ${r['real_net']:>9,.0f}  "
              f"${r['real_per_trade']:>6.2f}/trade  drop5 ${r['drop5']:>9,.0f}"
              f"  ({r['real_net']-b5['real']:+,.0f})")
    worse = sum(1 for r in at5 if r["real_net"] <= b5["real"])
    print(f"  {worse}/{len(at5)} cells at this trail are NO BETTER than "
          f"doing nothing\n")

    # --- how much is the trail, how much is the size, how much is the idea --
    print("DECOMPOSITION of the in-sample best, one change at a time")
    steps = [
        ("baseline, 5% trail, no scale-out", base[5.0]["real"]),
        (f"...then trail {got['trail']}%", base[got["trail"]]["real"]),
        ("...then scale-out at the best cell", best["real_net"]),
    ]
    prev = None
    for label, v in steps:
        delta = "" if prev is None else f"   {v-prev:+,.0f}"
        print(f"  {label:<42} ${v:>9,.0f}{delta}")
        prev = v
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
