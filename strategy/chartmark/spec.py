#!/usr/bin/env python3
"""CHARTMARK-v1 (long): every registered constant in one place. W15-0032 sub 4.
REGISTERED_chartmark_v1.md sec 2 and Amendment A. Nothing here is tuned; a change after a result is a new hypothesis.

Interpretations fixed here BEFORE any count or return was computed (PRE-RUN, listed in the handover):
  I1  A0 (ATR at entry) = ATR(14) at the close of the bar BEFORE the fill bar (known when the order was working).
  I2  "travelled" uses closes from the entry bar's close onward, evaluated at each close; a phase is live from the next bar.
  I3  P1/P2 working stop for bar j = max(S, EMA[j-1]) (S remains a floor). P2 is EMA21 replacing EMA9 (a loosening).
  I4  Sell-stop fills: min(level, open). A level above the open fills at the open.
  I5  V-STALL: checked at the close of bar e+N over closes e..e+N; level = entry + round-trip MID friction (MCL) in price. A
      level below the last close is a sell-stop; a level above it is a sell-limit (fills at max(level, open) when high >= level).
      Stops are tried before the limit in any bar that could trigger both.
  I6  A roll (held_id changes between bars j and j+1) cancels a working entry order and blocks a new one at j; an open
      position is carried through and pays two extra sides (the futbt convention). Prices are difference-back-adjusted.
  I7  X3 = the bar's OPEN hour, New York, 2..12 inclusive.
  I8  Initial stop uses the entry bar's own low (5 bars ending at the entry bar); it is live from the bar AFTER the entry
      bar (a 1H bar cannot show whether the low came before or after the fill). Entry bars whose own low sets the stop
      are counted in the pre-flight.
  I9  "Net per unit of realised volatility" (criterion 5) = net / standard deviation of daily realised net P&L (mid, 1 MCL)
      over the calendar days of the window, zeros on days with no exit.
  I10 C3 random entries are single-trade outcomes from the OPEN of a random in-session bar, stops as sec 2.3 from the
      bars ending at the bar before entry; trades are independent (overlap allowed). Seed as registered.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

TICK = 0.01
MULT = {"MCL": 100.0, "CL": 1000.0}
TICK_USD = {"MCL": 1.0, "CL": 10.0}

# Amendment A.3: IBKR Pro published, per contract per side (read 2026-09-30)
FEE = {"MCL": 0.77, "CL": 2.37}
LEVELS = ("low", "mid", "high")
_TICKS = {"low": 0, "mid": 1, "high": 2}


def per_side(sym: str, level: str) -> float:
    return FEE[sym] + _TICKS[level] * TICK_USD[sym]


def round_trip_price(sym: str = "MCL", level: str = "mid") -> float:
    """Round-trip friction in PRICE terms (V-STALL breakeven)."""
    return 2 * per_side(sym, level) / MULT[sym]


SESSION_FIRST, SESSION_LAST = 2, 12
ATR_LEN = 14
P2_ARM = 2.0
R_WICK, R_MIN_RANGE, R_LIFE = 0.5, 0.3, 3
STALL_PROGRESS = 0.5
AVOID_SLOPE, AVOID_LOOK, AVOID_MIN_LOW, AVOID_VOLSMA = 0.5, 10, 7, 20


@dataclass(frozen=True)
class Params:
    e1_lookback: int = 3          # E1 highest high of bars t-(L-1)..t
    stop_lookback: int = 5        # S lowest low of the L bars ending at the entry bar
    p1_arm: float = 1.0           # A0
    p2_arm: float = P2_ARM
    K: int = 6                    # E3 timeout
    session: bool = True          # X3
    x4: bool = False              # optional EMA9-converging gate
    x4_lb: int = 2
    p2: bool = True
    r: bool = True
    stall_n: int | None = None    # V-STALL N (3 or 4), None = off
    avoid: bool = False           # V-AVOID
    stall_rt: float = 0.0         # set from round_trip_price() when stall_n is on


BASE = Params()
VARIANTS = {
    "BASE": BASE,
    "V-STALL3": replace(BASE, stall_n=3, stall_rt=round_trip_price()),
    "V-STALL4": replace(BASE, stall_n=4, stall_rt=round_trip_price()),
    "X4": replace(BASE, x4=True),
    "NO-P2": replace(BASE, p2=False),
    "NO-R": replace(BASE, r=False),
    "SESSION-OFF": replace(BASE, session=False),
    "V-AVOID": replace(BASE, avoid=True),
}
GRID_E1 = (2, 3, 5)
GRID_P1 = (0.75, 1.0, 1.5)
GRID_STOP = (3, 5, 8)
