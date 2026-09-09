#!/usr/bin/env python3
"""Do prices on this universe cluster at half and whole dollars?

    python -m common.price_grid

THE CLAIM, Ross Cameron via claude/warrior_2_flat_top.md §3
-----------------------------------------------------------
"Most stocks trade with a great deal of respect to half dollars and whole
dollars" (V-3HR 42:33). He shows resting size parked at $6.00, $7.40-7.50 and
$8.00 on one name all morning, and describes the space BETWEEN levels as
traversed fast because there are no orders there.

If that holds on our tape it changes what a flat-top detector is. Warrior 2 §3
puts it plainly: flat-top detection "may be substantially a price-grid problem
rather than a pattern-matching one" -- if the levels sit at round numbers we do
not detect flatness, we anticipate the level. And Warrior 2 §4's standalone
setup (buy at $7.99 for the break of $8.00) is then codeable from bars alone.

If it does NOT hold, both of those collapse and the flat-top work is a
pattern-matching problem after all.

THE CONTROL, WHICH IS THE WHOLE DESIGN
--------------------------------------
The naive test -- "are highs near round numbers more often than uniform?" --
cannot work. Price is not uniformly distributed: a stock that spends the
morning between $5.00 and $5.08 has every high near a round number by
construction, and the test would confirm the claim on a name that never went
near a level twice.

So the control is a PLACEBO GRID. Measure clustering at the claimed levels
(.00 and .50) and at quarter levels (.25 and .75) in the same bars, the same
way. The quarter levels are the same distance apart, drawn from the same price
distribution, and nobody claims anything about them. If the claimed levels beat
the placebo the effect is real; if the two agree, whatever was measured was the
price distribution and not a grid.

Arithmetic is done in integer CENTS. 5.15 is not exactly representable and a
float modulus produces distances of 0.009999999999999787 that a naive
"within a cent" test then misses.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from common.analysis import load_sessions
from common.report_io import emit

GRID_C = 50           # half dollars, in cents
PLACEBO_OFFSET_C = 25  # .25 / .75 -- same spacing, no claim attached
REPEAT_MIN = 3        # tags at one price before it counts as a level


def to_cents(prices) -> list[int]:
    """Exact integer cents. See the module docstring: float modulus on 5.15
    yields 0.00999999... and a "within one cent" test then silently misses."""
    return [int(round(float(p) * 100)) for p in prices if pd.notna(p)]


def distance(cents: int, offset: int = 0) -> int:
    """Cents to the nearest grid line, 0..GRID_C//2.

    `offset` shifts the grid: 0 gives the claimed levels (.00/.50), 25 gives
    the placebo (.25/.75).
    """
    r = (cents + offset) % GRID_C
    return min(r, GRID_C - r)


def profile(cents_list: list[int]) -> dict:
    """How close this population sits to the real grid and to the placebo."""
    if not cents_list:
        return {"n": 0}
    real = [distance(c) for c in cents_list]
    plac = [distance(c, PLACEBO_OFFSET_C) for c in cents_list]

    def within(ds, k):
        return 100.0 * sum(1 for d in ds if d <= k) / len(ds)

    return {
        "n": len(cents_list),
        "real_1c": within(real, 1), "plac_1c": within(plac, 1),
        "real_2c": within(real, 2), "plac_2c": within(plac, 2),
        "real_mean": sum(real) / len(real), "plac_mean": sum(plac) / len(plac),
    }


def repeat_levels(df: pd.DataFrame, k: int = REPEAT_MIN) -> list[int]:
    """Prices tagged as a bar HIGH at least k times in one session.

    This is the flat-top proxy: a level price keeps reaching and failing at is
    exactly what "a large resting seller" looks like in bar data. Highs only --
    a level that is repeatedly hit from below is the thing Warrior 2 is about,
    and pooling lows would dilute it with support.
    """
    c = Counter(to_cents(df["high"]))
    return [px for px, n in c.items() if n >= k]


def collect(sessions) -> dict[str, list[int]]:
    """Four populations, coarsest to most specific."""
    out: dict[str, list[int]] = {"all closes": [], "bar highs": [],
                                 "session extremes": [], "repeat levels": []}
    for _sym, _d, df in sessions:
        if df is None or df.empty:
            continue
        out["all closes"] += to_cents(df["close"])
        out["bar highs"] += to_cents(df["high"])
        out["session extremes"] += to_cents([df["high"].max(), df["low"].min()])
        out["repeat levels"] += repeat_levels(df)
    return out


def render(pops: dict[str, list[int]], n_sessions: int) -> list[str]:
    L = ["PRICE GRID -- do highs and levels sit at half and whole dollars?", "",
         f"  {n_sessions} cached sessions, 1-minute bars, integer cents",
         "  real grid    .00 and .50",
         "  placebo grid .25 and .75 -- same spacing, same bars, no claim",
         "",
         "  The placebo is the control. Price is not uniformly distributed, so",
         "  'close to a round number' happens without any grid at all. Only the",
         "  DIFFERENCE between the two columns is evidence.",
         "",
         f"  {'population':<18}{'n':>10}{'<=1c real':>11}{'placebo':>10}"
         f"{'<=2c real':>11}{'placebo':>10}{'mean real':>11}{'placebo':>10}"]

    rows = []
    for name, cents in pops.items():
        p = profile(cents)
        if not p["n"]:
            continue
        rows.append((name, p))
        L.append(f"  {name:<18}{p['n']:>10,}{p['real_1c']:>10.1f}%"
                 f"{p['plac_1c']:>9.1f}%{p['real_2c']:>10.1f}%"
                 f"{p['plac_2c']:>9.1f}%{p['real_mean']:>11.2f}"
                 f"{p['plac_mean']:>10.2f}")

    L.append("")
    if not rows:
        return L + ["  NO DATA."]

    d = dict(rows)
    base = d.get("all closes")
    if not base or not base["n"]:
        return L + ["  NO BASELINE."]

    # TWO CLAIMS, TWO CONTROLS, AND THEY GIVE DIFFERENT ANSWERS.
    #
    # The placebo answers "is there a grid at all". The BASELINE answers the
    # question Warrior 2 actually asks -- are LEVELS more gridded than prices
    # in general. A population inherits the tape's clustering just by being
    # made of prices, so beating the placebo is necessary and nowhere near
    # sufficient. Reading only the placebo column turns "prices cluster" into
    # "flat tops are predictable", which is a different and much stronger
    # claim that these numbers may not support.
    grid = base["real_1c"] - base["plac_1c"]
    L += ["CLAIM 1 -- is there a grid at all?", "",
          f"  Ordinary closes sit within a cent of .00/.50 "
          f"{base['real_1c']:.1f}% of the time, against "
          f"{base['plac_1c']:.1f}% for .25/.75.",
          f"  Lift {grid:+.1f} points"
          + (f", a factor of {base['real_1c'] / base['plac_1c']:.1f}."
             if base["plac_1c"] else "."), ""]
    L += (["  YES. The tape respects half and whole dollars.", ""] if grid > 2.0
          else ["  NO. Without a grid, nothing below can be read.", ""])

    L += ["CLAIM 2 -- are flat tops MORE gridded than ordinary prices?", ""]
    for name in ("repeat levels", "session extremes"):
        p = d.get(name)
        if not p or not p["n"]:
            continue
        excess = p["real_1c"] - base["real_1c"]
        L.append(f"  {name:<18}{p['real_1c']:>6.1f}% vs the "
                 f"{base['real_1c']:.1f}% baseline   excess {excess:+.1f} pts")
    L.append("")

    lv = d.get("repeat levels")
    if lv and lv["n"]:
        excess = lv["real_1c"] - base["real_1c"]
        if excess > 2.0:
            L += ["  YES. Flat-top levels can be anticipated from the price",
                  "  grid rather than detected as a shape.", ""]
        else:
            L += ["  NO. Repeat-tagged levels are no more likely to sit on a",
                  "  round number than any other price on the tape. The grid is",
                  "  real and flat tops do not preferentially live on it, so",
                  "  Warrior 2 §3's shortcut does not hold: detecting flat tops",
                  "  remains a pattern-matching problem.",
                  "",
                  "  Warrior 2 §4 -- the standalone half-dollar entry -- is NOT",
                  "  killed by this. It rests on claim 1, which passed. What",
                  "  fails is the stronger claim that the two are the same",
                  "  thing.", ""]

    ext = d.get("session extremes")
    if ext and ext["n"] and ext["real_1c"] - base["real_1c"] > 2.0:
        L += ["  Worth noting separately: the day's HIGH and LOW do cluster "
              "beyond",
              "  the baseline. Where a move stops is gridded even where "
              "consolidation",
              "  is not -- which is a claim about targets and exits rather "
              "than entries,",
              "  and nothing in the Warrior set makes it.", ""]

    L += ["WHAT THIS DOES NOT SHOW", "",
          "  Whether a level, once identified, is worth trading. Clustering is",
          "  a fact about where prices pause; it says nothing about what",
          "  happens after one breaks. That is a separate measurement and it",
          "  needs the strategy, not just the bars.",
          "",
          "  These are IB bars and they are SPLIT-ADJUSTED. An adjusted price",
          "  is not the price anyone traded at, so a real grid effect would be",
          "  smeared by the adjustment factor -- which biases this test TOWARD",
          "  finding nothing. Re-run on bar_cache_xnas before believing a null."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--repeat-min", type=int, default=REPEAT_MIN,
                   help="tags at one price before it counts as a level")
    p.add_argument("--out", default="var/reports/price_grid.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    sessions = load_sessions(Path(a.cache))
    pops = collect(sessions)
    emit("\n".join(render(pops, len(sessions))), a.out,
         header=f"common.price_grid  cache={a.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
