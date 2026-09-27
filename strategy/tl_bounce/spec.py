#!/usr/bin/env python3
"""Every fixed value the TL-bounce free steps (W15-0015) and backtest
(W15-0016) use, with where it was registered. REGISTERED_tl_bounce.md sec 2.

Nothing here is chosen from a measurement of returns (a change is a PRE-RUN
amendment with a reason that does not mention a result, or a new
registration -- sec 9).
"""
from __future__ import annotations

# --- market and grids: sec 2.1 -----------------------------------------
MARKET = "CL"
ENTRY_CHARTS: tuple[str, ...] = ("4H", "1H")          # 4H primary, 1H reported
HIGHER_CHART = {"4H": "1D", "1H": "4H"}                # E0's next-higher chart

# --- lines: sec 2.1 (common/tl_v0_lines.py, shared with TL-v0/HTF-Ben v1) --
PIVOT_L = PIVOT_R = 5           # confirmed-only pivots for the entry line
TRAIL_L = TRAIL_R = 2           # S2's swing-low/high pivots
ATR_LEN = 14
WARMUP_BARS = 200               # sec 2.1: "200-bar warm-up before any signal"

# --- entry / stop / trail buffers, x ATR(14): sec 2.2-2.3 -------------
TOUCH_BUF = 0.25                # E1: low[t] <= line[t] + TOUCH_BUF*ATR
X1_BUF = 0.10                   # line-break / close-through buffer (shared
                                 # with common/tl_v0_lines.BUFFER_MULT)
STOP_BUF = 0.25                 # S1/S2 buffer past the line/swing

# --- reported variants: sec 2.5 (fixed now, never ranked) ---------------
VARIANTS: tuple[str, ...] = ("bounce", "bounce-limit", "bounce-noX1",
                              "bounce-noE0", "bounce-once")

# --- sizing, account, costs: inherited from REGISTERED_htf_ben_v0.md
#     sec 2.5 with Amendment A (sec 2.4) --------------------------------
ACCOUNT_START = 10_000.0
RISK_PCTS: tuple[float, ...] = (0.01,)          # 1% of $10k and $22k, reported only
RISK_EQUITIES: tuple[float, ...] = (10_000.0, 22_000.0)
FRICTION: dict[str, float] = {"low": 1.09, "mid": 2.09, "high": 3.09}   # $/MCL/side
FRICTION_CL: dict[str, float] = {"low": 2.99, "mid": 12.99, "high": 22.99}
LEVELS: tuple[str, ...] = ("low", "mid", "high")

# --- training / holdout windows: sec 5.2 / sec 6 -------------------------
TRAIN_START = "2010-06-06"
TRAIN_END = "2021-12-31"
STOP_RULE_MIN_ENTRIES = 150     # sec 5.2: fewer 4H entries -> stop, back to Ben

# --- neighbour grid: sec 3 (27 cells, unranked; reported only here) -----
GRID_TOUCH_BUF = (0.15, 0.25, 0.35)
GRID_X1_BUF = (0.05, 0.10, 0.20)
GRID_PIVOT_R = (3, 5, 8)
