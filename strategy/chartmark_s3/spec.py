#!/usr/bin/env python3
"""CHARTMARK-S v3 (short): CHARTMARK-S v2 with Tier B's condition B1 removed. W15-0042 sub 3.
REGISTERED_chartmark_short_v3.md sec 2. Everything else (X1, Tier A, B2-B4, the order machine, backstop, exits, costs, controls,
grid, criteria, holdout) is v2's / v1's, imported unchanged. Nothing here is tuned. Interpretations K1-K7 (v2 Amendment 1) apply;
K2's clause "Tier B needs bar t-1" no longer applies (Tier B uses bar t only). New here:
  L1  The base has b1 = False. V-B1 is the v2 base (b1 = True), reported for reference only, never ranked.
  L2  V-A is identical to v2's V-A (Tier A has no B1); V-B here is the v3 Tier B (no B1).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from strategy.chartmark_s2.spec import (FEE, LEVELS, MULT, TICK, TICK_USD, per_side, TIER_A, TIER_B, RETEST_TICKS,   # noqa: F401
                                        TOP_N, RANGE_N, RANGE_MIN, SESSION_FIRST, SESSION_LAST, POKE_TICKS,           # noqa: F401
                                        GRID_X1, GRID_P1, GRID_CUT)                                                    # noqa: F401


@dataclass(frozen=True)
class Params:
    x1_window: int = 16
    p1_arm: float = 1.0
    cut_ticks: int = 2
    backstop_n: int = 20
    K: int = 6
    tiers: str = "AB"         # "AB" base, "A", "B"
    b1: bool = False          # v3: B1 removed. True = v2's Tier B (V-B1)
    rng: bool = False
    session: bool = False
    avoid: bool = False
    wide: bool = False        # v1 exit-engine flags; never set
    close9: bool = False


BASE = Params()
VARIANTS = {
    "BASE": BASE,
    "V-A": replace(BASE, tiers="A"),
    "V-B": replace(BASE, tiers="B"),
    "V-B1": replace(BASE, b1=True),
    "V-RANGE": replace(BASE, rng=True),
    "V-SESSION": replace(BASE, session=True),
    "V-AVOID": replace(BASE, avoid=True),
}
