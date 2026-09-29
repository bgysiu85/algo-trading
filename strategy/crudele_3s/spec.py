#!/usr/bin/env python3
"""Every fixed value CRUDELE-3S uses, with where REGISTERED_crudele_3s.md fixes it.

Nothing here comes from a measurement of returns. A change is a PRE-RUN amendment with a reason
that does not mention a result, or it is a new hypothesis (sec 9 of the registration).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# --- indicators: sec 2.2 --------------------------------------------------
BB_LEN = 20                # STATED
BB_SD = 3.0                # STATED ("20 period three standard deviation")
BWR_WIN = 250              # (choice) percentile-rank window, bars
SMA_EXIT = 8               # his 8/21/34; type is our choice

# --- state machine: sec 2.3 ------------------------------------------------
SQ_THR = 0.25              # (choice) BWR <= 0.25 ...
SQ_COUNT, SQ_OF = 5, 10    # (choice) ... on at least 5 of the last 10 bars
BOX_LEN = 20               # (choice) range box = highest high / lowest low of the last 20 bars
EXP_BARS = 3               # (choice) BW rose on each of the last 3 bars
C_GRACE = 5                # (choice) T may fire within 5 bars of leaving C
T_TIMEOUT = 60             # (choice) T times out after 60 bars with no band peak
IN_FALLS = 2               # (choice) bands come in = BW falls on 2 consecutive bars
MR_ARM = 20                # (choice) MR armed for 20 bars

# --- setups: sec 2.4 -------------------------------------------------------
FIB_ENTRY, FIB_TARGET = 0.30, 0.50     # STATED (30 / 50); measured from the peak (see Amendment A)
MR_TIME_STOP = 10          # (choice)
C_TIME_STOP = 5            # (choice)
C_STOP_ATR = 0.10          # (choice) poke-bar extreme + 0.10 x ATR
RISK_T, RISK_MR, RISK_C = 0.01, 0.005, 0.01   # 1% / 0.5% (STATED "small"; 0.5 ours) / 1%

ARM_T, ARM_MR, ARM_C = "T", "MR", "C"
ARMS = (ARM_T, ARM_MR, ARM_C)

# --- grid: sec 3 item 7 -----------------------------------------------------
GRID_BWR = (0.20, 0.25, 0.33)
GRID_EXP = (2, 3, 4)
GRID_MA = (8, 21, 34)

# --- bar: sec 5.2 -----------------------------------------------------------
MIN_ENTRIES = 150          # fewer -> stop as underpowered, back to Ben before any P&L
MIN_ARM_ENTRIES = 30       # an arm below this is "too few to read" (does not stop the study)


@dataclass(frozen=True)
class Params:
    sd: float = BB_SD
    bwr_thr: float = SQ_THR
    exp_bars: int = EXP_BARS
    exit_ma: int = SMA_EXIT
    t_free: bool = False           # variant "T without squeeze"
    beacon_mr: bool = False        # variant "MR-Beacon" (Amendment A)
    arms: tuple = ARMS             # variants: each arm alone, No-C

    def with_(self, **kw) -> "Params":
        return replace(self, **kw)


PRIMARY = Params()
VARIANTS: dict[str, Params] = {
    "system": PRIMARY,
    "T-only": PRIMARY.with_(arms=(ARM_T,)),
    "MR-only": PRIMARY.with_(arms=(ARM_MR,)),
    "C-only": PRIMARY.with_(arms=(ARM_C,)),
    "No-C": PRIMARY.with_(arms=(ARM_T, ARM_MR)),
    "T-no-squeeze": PRIMARY.with_(t_free=True),
    "SD-2.5": PRIMARY.with_(sd=2.5),
    "MR-Beacon": PRIMARY.with_(beacon_mr=True),
}
INDEX_SLICE = ("ES", "RTY")        # sec 2.6: his stated scope (NQ is not in the archive)
