#!/usr/bin/env python3
"""HTF-Ben v1's trend-line geometry: T (curl-route rejection) and F2
(last-touched-line direction filter). W15-0011, REGISTERED_htf_ben_v1.md
sec 2's Notation ("Line" ... "on the back-adjusted series") and sec 2.1's
T/F2 rows.

WHY THIS ALWAYS RUNS ON THE 4-HOUR FRAME, LIKE W15-0007's v0-TL
--------------------------------------------------------------------
Sec 2's Notation defines "Line" as "a 4-hour trend line from
common/tl_v0_lines.py ... on the back-adjusted series", and F1's own row
says "the N = 9 four-hour bars ending at c" in so many words -- unlike E1a/
E1b/E2, which are v0's E1 "unchanged" (and v0's Amendment 0 already reads
"4-hour bar" as "the scenario's own entry-chart bar" for THOSE rules), the
line machinery introduced fresh in this file is pinned to the 4-hour chart
regardless of scenario, exactly as W15-0007 built for v0-TL. So T and F2
both take a `four_h_adj` frame (prepared the same way as v0-TL's) and map
each entry-chart trigger's own t_open onto it via
strategy.htf.tl_variant.map_to_last_closed_4h -- the same no-lookahead,
global-timestamp lookup, reused rather than re-derived.

WHY tl_v0_lines' OWN "high"/"low" KIND NAMES MAP CLEANLY ONTO "rising"/
"falling"
---------------------------------------------------------------------------
common.tl_v0_lines.walk_line_and_breaks only ever validates a kind='low'
pair when the second pivot is HIGHER than the first (a rising support
line) and a kind='high' pair when the second pivot is LOWER (a falling
resistance line) -- see that module's own direction_ok test. So "the active
rising line" T wants for a long is exactly kind='low', and "the active
falling line" T wants for a short is exactly kind='high'; no extra slope
check is needed here.

ASSUMPTION FLAGGED (not settled by the registered text, same spirit as
tl_v0_lines.py's and tl_variant.py's own notes): "every close from k to t
is above the line" is read literally against `line[j]` at each bar j in
[k, t] as tl_v0_lines.walk_line_and_breaks returns it -- which can, on a
new pivot confirming, silently swap in a different (but still active,
still un-broken) line before t (tl_v0_lines.py's own documented judgement
call). This module does not try to track "the same line's identity"
separately; it reads T as "some active rising/falling line has had price
above/below it continuously from k to t", not "the identical line pair
throughout".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from common import tl_v0_lines as TL
from strategy.htf import tl_variant as TLV

LINE_LR = 5
F1_WINDOW_4H = 9        # REGISTERED sec 2.1 F1: "N = 9 four-hour bars"
F2_LOOKBACK_4H = 30      # REGISTERED sec 2.1 F2: "30 bars before c" (4-hour)
T_OFFSETS = (2, 3)       # REGISTERED sec 2.1 T: "t - k in {2, 3}"


def build_4h_lines(four_h_adj: pd.DataFrame, *, LR: int = LINE_LR):
    """Once-per-run geometry on the 4-hour frame: (line_low, line_high, atr)
    -- line_low[j]/line_high[j] is the active rising/falling line's level at
    bar j (NaN when none is active), atr is ATR(14) on the same frame.
    Shared by T and F2 so each caller does not re-run
    find_pivots/walk_line_and_breaks per trigger."""
    high = four_h_adj["high_adj"].to_numpy(dtype=float)
    low = four_h_adj["low_adj"].to_numpy(dtype=float)
    close = four_h_adj["close_adj"].to_numpy(dtype=float)
    n = len(close)
    atr = TL.atr14(high, low, close)

    pivots_low = TL.find_pivots(low, LR, "low")
    line_low, _ = TL.walk_line_and_breaks(n, pivots_low, LR, close, atr, "low")
    pivots_high = TL.find_pivots(high, LR, "high")
    line_high, _ = TL.walk_line_and_breaks(n, pivots_high, LR, close, atr, "high")
    return line_low, line_high, atr


def t_condition(direction: str, t4: int, four_h_adj: pd.DataFrame,
                line_low: np.ndarray, line_high: np.ndarray, atr: np.ndarray,
                *, offsets=T_OFFSETS, touch_mult: float = 0.25) -> bool:
    """T, REGISTERED sec 2.1: for `direction`, some bar k with t4 - k in
    `offsets` touched an active rising (long) / falling (short) line (low
    <= line + touch_mult*ATR[k], for long; mirrored for short) and closed
    back beyond it, every close from k to t4 stays beyond the line, and the
    line is still active at t4. t4 is the trigger bar's own last-closed-4H
    index (map_to_last_closed_4h) -- everything read here is at or before
    t4, so this never looks at a bar that has not closed as of the trigger."""
    if t4 < 0 or t4 >= len(four_h_adj):
        return False
    line = line_low if direction == "long" else line_high
    if np.isnan(line[t4]):
        return False   # sec 2.1: "the line is still active at t"
    low = four_h_adj["low_adj"].to_numpy(dtype=float)
    high = four_h_adj["high_adj"].to_numpy(dtype=float)
    close = four_h_adj["close_adj"].to_numpy(dtype=float)

    for off in offsets:
        k = t4 - off
        if k < 0 or np.isnan(line[k]):
            continue
        if direction == "long":
            touched = (low[k] - line[k]) <= touch_mult * atr[k]
            closed_beyond = close[k] > line[k]
        else:
            touched = (line[k] - high[k]) <= touch_mult * atr[k]
            closed_beyond = close[k] < line[k]
        if not (touched and closed_beyond):
            continue
        # every close from k to t4 (inclusive) must stay beyond an active line
        span_ok = True
        for j in range(k, t4 + 1):
            if np.isnan(line[j]):
                span_ok = False
                break
            beyond = (close[j] > line[j]) if direction == "long" else (close[j] < line[j])
            if not beyond:
                span_ok = False
                break
        if span_ok:
            return True
    return False


def f2_direction_block(direction: str, t4: int, four_h_adj: pd.DataFrame,
                       line_low: np.ndarray, line_high: np.ndarray, atr: np.ndarray,
                       *, lookback: int = F2_LOOKBACK_4H, touch_mult: float = 0.25) -> bool:
    """True iff F2 BLOCKS a trade in `direction` at t4: the most recently
    touched active line in the `lookback` 4-hour bars before t4 is a falling
    one (blocks longs) or a rising one (blocks shorts). No touched active
    line in the window -> no restriction (returns False for both
    directions). REGISTERED sec 2.1 F2: 'the active line most recently
    touched ... in the 30 bars before c'."""
    if t4 < 0:
        return False
    low = four_h_adj["low_adj"].to_numpy(dtype=float)
    high = four_h_adj["high_adj"].to_numpy(dtype=float)
    window_lo = max(0, t4 - lookback)

    last_touch_kind = None      # "low" (rising) or "high" (falling)
    last_touch_pos = -1
    for j in range(window_lo, t4):
        if not np.isnan(line_low[j]) and (low[j] - line_low[j]) <= touch_mult * atr[j]:
            if j > last_touch_pos:
                last_touch_pos, last_touch_kind = j, "low"
        if not np.isnan(line_high[j]) and (line_high[j] - high[j]) <= touch_mult * atr[j]:
            if j > last_touch_pos:
                last_touch_pos, last_touch_kind = j, "high"
    if last_touch_kind is None:
        return False
    if last_touch_kind == "high":     # falling line most recently touched -> no longs
        return direction == "long"
    return direction == "short"       # rising line most recently touched -> no shorts
