#!/usr/bin/env python3
"""Every fixed value BREIT-CAP uses, with where REGISTERED_breit_cap.md fixes it. Nothing here comes
from a measurement of returns; a change is a PRE-RUN amendment or a new hypothesis (sec 9)."""
from __future__ import annotations

from dataclasses import dataclass, replace

# --- the qualifying run: sec 2.2 ------------------------------------------------------------
K_MIN = 4                 # STATED 4-9 bars in his examples; >= 4 is our choice
Q2_ATR = 3.0              # (choice) D >= 3 x ATR[O]
Q3_SD = 2.0               # (choice) Bollinger (20, 2.0); the scan itself is STATED
BB_LEN = 20

# --- the grade and the size: sec 2.3 --------------------------------------------------------
G_SPEED_TR = 1.5          # largest TR of the last 2 run bars >= 1.5 x ATR[O]
G_LEGS_MIN = 3            # >= 3 down-legs from the 60-bar high to the run low
LEG_WINDOW = 60
LEG_ATR = 1.0             # zigzag reversal = 1.0 x ATR[O]
G_VOL_X = 2.0             # max volume of the last 3 run bars >= 2.0 x its own prior 20-bar average
VOL_AVG = 20
BORING_WIN = 250          # ATR[O]/price <= the market's own median over the prior 250 bars
G_LONG_RUN = 6            # k >= 6
RISK_BY_GRADE = ((0, 1, 0.005), (2, 3, 0.010), (4, 5, 0.020))    # long-side risk by grade band
SHORT_FACTOR = 0.5        # "way less on the short side": half of the long-side risk
FLAT_RISK = 0.01          # the flat-1% variant and control C2

# --- exits: sec 2.4 -----------------------------------------------------------------------
TICKS_BEYOND = 1          # entry buy-stop = prior high + 1 tick; stop = lowest low of the run - 1 tick

# --- grid: sec 3 item 7 -----------------------------------------------------------------------
GRID_Q2 = (2.0, 3.0, 4.0)
GRID_K = (3, 4, 5)
GRID_SD = (1.5, 2.0, 2.5)

# --- bar: sec 5.2 ------------------------------------------------------------------------------
MIN_ENTRIES = 150
MIN_VOLUME_COVERAGE = 0.99     # G1: held-contract daily volume non-zero on >= 99% of training bars

B = "B"                        # the trade arm tag


def grade_risk(grade: int) -> float:
    for lo, hi, r in RISK_BY_GRADE:
        if lo <= grade <= hi:
            return r
    raise ValueError(grade)


@dataclass(frozen=True)
class Params:
    k_min: int = K_MIN
    q2: float = Q2_ATR
    q3_sd: float = Q3_SD
    require_q2q3: bool = True      # control C2 = the unfiltered reversal turns this off
    sizing: str = "graded"         # "graded" | "flat" (1% both sides)
    sides: tuple = (1, -1)
    min_grade: int = 0
    target: str | None = None      # None | "50" | "ma"

    def with_(self, **kw) -> "Params":
        return replace(self, **kw)


PRIMARY = Params()
VARIANTS: dict[str, Params] = {
    "system": PRIMARY,
    "long-only": PRIMARY.with_(sides=(1,)),
    "short-only": PRIMARY.with_(sides=(-1,)),
    "flat-1pct": PRIMARY.with_(sizing="flat"),
    "grade>=2": PRIMARY.with_(min_grade=2),
    "+50pct-target": PRIMARY.with_(target="50"),
    "+MA-target": PRIMARY.with_(target="ma"),
    "k>=5": PRIMARY.with_(k_min=5),
}
C2_UNFILTERED = PRIMARY.with_(require_q2q3=False, sizing="flat")
