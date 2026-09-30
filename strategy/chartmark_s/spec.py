#!/usr/bin/env python3
"""CHARTMARK-S v1 (short): every registered constant in one place. W15-0032 sub 8.
REGISTERED_chartmark_short_v1.md sec 2 and Amendment A. Nothing here is tuned; a change after a result is a new hypothesis.
Costs, tick and multipliers are shared with the long side (strategy.chartmark.spec, IBKR, Amendment A.3 / sec 2.5).

Interpretations fixed here BEFORE any count or return was computed (PRE-RUN; none changes a registered number):
  J1  A0 = ATR(14) at the LAST context bar (the bar before the fill bar) -- the reference engine2.py convention.
  J2  X1: the bar of the highest high of bars t-19..t; ties resolve to the OLDEST bar (numpy argmax), as in the reference.
  J3  Backstop = highest high of the 20 bars ending at the entry bar INCLUSIVE, + 1 tick. Because the entry bar's own high is
      in the window the level is always above that bar's high, so "same-bar" backstop touches are 0 by construction (reported).
  J4  travelled = entry - lowest close since entry, entry bar's close included; P1 is live from the bar AFTER the bar whose
      close first shows travelled >= arm. A poke needs P1 live at the start of the bar (prior state).
  J5  Simultaneous levels in one bar: the LOWEST fill price wins (the one price reaches first as it rises); a tie at the open
      resolves P0, then P1, then backstop.
  J6  Both the P0 cut and P1 poke/retest levels use EMA9[j-1] + 2 ticks. The grid "P0 cut buffer" changes ONLY the P0 level.
  J7  No maximum holding time (none is registered). An open position at the last bar exits at that close ("data_end").
  J8  A roll (held_id changes between bars j and j+1) cancels a working entry order and blocks a new one at j; an open
      position is carried through and pays two extra sides (long-side convention I6).
  J9  Criterion 5 volatility = the long side's I9 (net / std of daily realised net P&L, mid, 1 MCL).
  J10 C3: single-trade outcomes from the OPEN of a random bar (any hour, no session filter) with the sec 2.3-2.4 exits from
      the bars ending at the bar before; ATR taken at the bar before entry; independent trades (overlap allowed).
      Seed default_rng([crc32(str(d)), crc32("CL-S"), N]). Random entry price = open (a market-style entry), as in the long C3.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from strategy.chartmark.spec import (FEE, LEVELS, MULT, TICK, TICK_USD, per_side,   # noqa: F401  (shared IBKR costs)
                                     AVOID_SLOPE, AVOID_LOOK, AVOID_MIN_LOW, AVOID_VOLSMA, ATR_LEN)

TOP_N = 20              # X1 window
RANGE_N = 120           # V-RANGE window
RANGE_MIN = 0.6
SESSION_FIRST, SESSION_LAST = 2, 12
XTOL = 0.25             # X2
POKE_TICKS = 2          # J6


@dataclass(frozen=True)
class Params:
    x1_window: int = 16       # X1: bars since the 20-bar high <= this
    p1_arm: float = 1.0       # A0 units travelled to arm P1
    cut_ticks: int = 2        # P0 level = EMA9[j-1] + cut_ticks
    backstop_n: int = 20
    K: int = 6                # E3 timeout
    rng: bool = False         # V-RANGE
    session: bool = False     # V-SESSION
    wide: bool = False        # V-WIDE: no P0 cut
    close9: bool = False      # V-CLOSE9: P1 replaced by first close above EMA9 -> next open
    avoid: bool = False       # V-AVOID (Amendment A.1)


BASE = Params()
VARIANTS = {
    "BASE": BASE,
    "V-RANGE": replace(BASE, rng=True),
    "V-SESSION": replace(BASE, session=True),
    "V-WIDE": replace(BASE, wide=True),
    "V-CLOSE9": replace(BASE, close9=True),
    "V-AVOID": replace(BASE, avoid=True),
}
GRID_X1 = (10, 16, 24)
GRID_P1 = (0.75, 1.0, 1.5)
GRID_CUT = (0, 2, 4)
