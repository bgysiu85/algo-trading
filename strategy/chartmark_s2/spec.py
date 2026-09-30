#!/usr/bin/env python3
"""CHARTMARK-S v2 (short, two-tier confirmation entry): every registered constant in one place. W15-0039 sub 3.
REGISTERED_chartmark_short_v2.md sec 2. Everything not listed here (X1, order machine E1-E5, backstop, exits P0/P1, costs,
controls, grid, holdout) is CHARTMARK-S v1's, imported unchanged from strategy.chartmark_s. Nothing here is tuned; a change
after a result is a new hypothesis.

Interpretations fixed BEFORE any count or return was computed (PRE-RUN; none changes a registered number):
  K1  Tier A = EMA9[t] < EMA21[t] (strict). EMA9[t] == EMA21[t] is Tier B territory (sec 2.1 says "EMA9[t] >= EMA21[t]").
  K2  Tier B needs bar t-1, so it is false at t = 0. B2 tolerance is 2 ticks (0.02), fixed in every grid cell.
  K3  Context = X1 and (Tier A or Tier B) and flat, and ATR / MACD histogram / EMA21 defined (A0 is the ATR at the last
      context bar, as v1 J1). X2 (EMA9 >= EMA21 - 0.25 ATR) and X3 (histogram falling) do not exist in v2.
  K4  A trade's tier is the tier true on the LAST context bar, i.e. bar t-1 of the fill bar t (the bar whose close set the
      working level). A Tier B context lasts one bar because B1-B3 are bar-specific, so a Tier B order lives one bar unless
      the next bar's context is Tier A or Tier B again (then E2 re-sets it); the tier is then the latest bar's.
  K5  V-A = only Tier A can create a context; V-B = only Tier B. V-RANGE, V-SESSION, V-AVOID = the base plus the v1 filter.
      V-WIDE and V-CLOSE9 (v1 reported variants) are NOT v2 variants.
  K6  G6 (sec 5): "fills within 1 bar" = an engine fill whose bar open is within one hour of the marked bar open (NY time of
      the TradingView CL1! bars). The two accepted marks must be filled AND: 9 Sep 22:00 within 2 ticks (0.02) of 96.25, as
      registered; 11 Sep 01:00 "near 102.09" is fixed here as within 0.25 (a quarter of a dollar, about a quarter of the ATR
      of 1.0 on that day). The seen bars are the 2026 bars (8 Sep 2026 onward), where CL traded 90-105.
  K7  Counts by tier are reported per year and overall; "share of context bars" = context bars true for Tier A vs Tier B
      over the training frame (bars where the context holds, before the order machine's flat / cooldown rules).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from strategy.chartmark_s.spec import (FEE, LEVELS, MULT, TICK, TICK_USD, per_side,    # noqa: F401  (shared IBKR costs)
                                       AVOID_SLOPE, AVOID_LOOK, AVOID_MIN_LOW, AVOID_VOLSMA, ATR_LEN,   # noqa: F401
                                       TOP_N, RANGE_N, RANGE_MIN, SESSION_FIRST, SESSION_LAST, POKE_TICKS,   # noqa: F401
                                       GRID_X1, GRID_P1, GRID_CUT)                                      # noqa: F401

RETEST_TICKS = 2          # B2 tolerance: high[t] >= EMA9[t] - 2 ticks
TIER_A, TIER_B = 1, 2


@dataclass(frozen=True)
class Params:
    x1_window: int = 16       # X1: bars since the 20-bar high <= this
    p1_arm: float = 1.0       # A0 units travelled to arm P1
    cut_ticks: int = 2        # P0 level = EMA9[j-1] + cut_ticks
    backstop_n: int = 20
    K: int = 6                # E3 timeout
    tiers: str = "AB"         # "AB" base, "A" = V-A, "B" = V-B
    rng: bool = False         # V-RANGE
    session: bool = False     # V-SESSION
    avoid: bool = False       # V-AVOID (v1 Amendment A.1)
    wide: bool = False        # exit-engine flags used by v1's run_position; never set in v2
    close9: bool = False


BASE = Params()
VARIANTS = {
    "BASE": BASE,
    "V-A": replace(BASE, tiers="A"),
    "V-B": replace(BASE, tiers="B"),
    "V-RANGE": replace(BASE, rng=True),
    "V-SESSION": replace(BASE, session=True),
    "V-AVOID": replace(BASE, avoid=True),
}
