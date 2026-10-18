#!/usr/bin/env python3
"""Online rising-support-line tracker for X-ALERT. W15-0053 sub 2 (gates G4, G8).

WHAT THIS IS. A bar-by-bar copy of the state machine in common/tl_v0_lines.walk_and_breaks (the TL-v0 line: pivot lows
L = R, validity / span guard, line goes cold the instant it breaks and re-arms only on the next valid pivot pair), with ONE
addition: after each closed bar it can say what the line will be worth at the NEXT bar (`proj_next`). The frozen module
returns a line value only for bars already processed, and its value at bar j already includes a pivot confirmed AT j, so it
cannot give "the level working in bar j from pivots confirmed <= j-1" without being edited (REGISTERED_exit_cmp.md sec 6).
The module is not edited. This tracker is proven bar-for-bar identical to it (line values and breaks, real-shaped and random
series) in tests/exitmgr/test_lines.py, and it reads only indices <= j so the live manager can feed it closed bars.
"""
from __future__ import annotations

import math

import numpy as np

from common.tl_v0_lines import BUFFER_MULT, MAX_SPAN   # the frozen constants, imported not copied


class SupportLine:
    """kind is always 'low' (a rising support line under pivot lows)."""

    def __init__(self, R: int = 5, buf: float = BUFFER_MULT):
        self.R, self.buf = int(R), float(buf)
        self.last_two: list[tuple[int, float]] = []
        self.active: tuple[int, float, float] | None = None     # (ref_idx, ref_val, slope)
        self.on = False

    def update(self, j: int, low, close, atr) -> tuple[float, bool]:
        """Process closed bar j (arrays are read at indices <= j only). Returns (line value at j or nan, broke at j)."""
        R = self.R
        i = j - R
        if i >= R and low[i] <= np.min(low[i - R: j + 1]):          # a pivot low confirmed at j
            self.last_two.append((i, float(low[i])))
            if len(self.last_two) > 2:
                self.last_two = self.last_two[-2:]
            if len(self.last_two) == 2:
                (p1, v1), (p2, v2) = self.last_two
                slope = (v2 - v1) / (p2 - p1)
                valid = (v2 > v1) and (p2 - p1) <= MAX_SPAN
                if valid:
                    for k in range(p1 + 1, j):
                        lv = v2 + slope * (k - p2)
                        if lv - close[k] > self.buf * atr[k]:
                            valid = False
                            break
                self.active = (p2, v2, slope) if valid else None
                self.on = valid
            else:
                self.active, self.on = None, False
        line, broke = math.nan, False
        if self.on and self.active is not None:
            ref_idx, ref_val, slope = self.active
            line = ref_val + slope * (j - ref_idx)
            if line - close[j] > self.buf * atr[j]:
                broke, self.on = True, False
        return line, broke

    def proj_next(self, j: int) -> float:
        """After bar j has been processed: the line's value at bar j+1, or nan when no line is armed. Uses state only."""
        if not (self.on and self.active is not None):
            return math.nan
        ref_idx, ref_val, slope = self.active
        return ref_val + slope * (j + 1 - ref_idx)


def track(low, close, atr, R: int = 5, buf: float = BUFFER_MULT):
    """Run the tracker over whole arrays. Returns (line, breaks, proj_next); proj_next[j] is the level that works in bar j+1
    and depends on bars <= j only."""
    n = len(close)
    line, brk, prj = np.full(n, np.nan), np.zeros(n, bool), np.full(n, np.nan)
    t = SupportLine(R, buf)
    for j in range(n):
        line[j], brk[j] = t.update(j, low, close, atr)
        prj[j] = t.proj_next(j)
    return line, brk, prj
