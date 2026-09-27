#!/usr/bin/env python3
"""Per-bar TL-bounce signal arrays for one entry-chart market: lines +
touches (lines.py) plus the S2 trail's swing pivots and the E0 filter,
assembled into one Signals object sim.py walks. REGISTERED_tl_bounce.md
sec 2.1-2.3.

Swing pivots for S2 (L=R=2, "confirmed at its 2nd right-hand bar") reuse
strategy.htf.signals.swing_lows/swing_highs verbatim -- the identical
definition (confirmed swing extreme, known at p+R) HTF-Ben v0's S1 uses,
just at TL-bounce's own TRAIL_L/TRAIL_R.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf.signals import swing_highs, swing_lows
from strategy.tl_bounce.lines import EntryLines, entry_lines, touch_signals
from strategy.tl_bounce.spec import TRAIL_L, TRAIL_R


@dataclass
class Signals:
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    atr: np.ndarray
    sup: np.ndarray          # rising (support) line value, NaN if not armed
    sup_breaks: np.ndarray   # X1-long trigger
    res: np.ndarray          # falling (resistance) line value, NaN if not armed
    res_breaks: np.ndarray   # X1-short trigger
    touch_long: np.ndarray
    touch_short: np.ndarray
    swing_low: np.ndarray    # ffilled: most recent confirmed swing low as of j
    swing_high: np.ndarray   # ffilled: most recent confirmed swing high as of j
    e0: np.ndarray | None    # +1/-1/0 higher-chart filter, None = off (bounce-noE0)

    @property
    def n(self) -> int:
        return len(self.c)


def market_signals(frame: pd.DataFrame, *, e0: np.ndarray | None = None) -> Signals:
    """`frame` is a back-adjusted entry-chart frame (bars.back_adjust output:
    open_adj/high_adj/low_adj/close_adj columns). `e0`, if given, is
    lines.e0_filter's output aligned to this frame (None disables the
    filter -- the bounce-noE0 variant, sec 2.5)."""
    o, h, lo, c = (frame[k + "_adj"].to_numpy(dtype=float) for k in
                   ("open", "high", "low", "close"))
    lines = entry_lines(o, h, lo, c)
    touch_long, touch_short = touch_signals(lo, h, c, lines)
    swlo = pd.Series(swing_lows(pd.Series(lo), TRAIL_L, TRAIL_R)).ffill().to_numpy()
    swhi = pd.Series(swing_highs(pd.Series(h), TRAIL_L, TRAIL_R)).ffill().to_numpy()
    return Signals(o, h, lo, c, lines.atr, lines.sup, lines.sup_breaks,
                   lines.res, lines.res_breaks, touch_long, touch_short,
                   swlo, swhi, e0)
