#!/usr/bin/env python3
"""TL-bounce 27-cell neighbour grid (unranked; robustness check only).
W15-0016. REGISTERED_tl_bounce.md sec 3 "Neighbour grid" and sec 4
criterion 8 ("at least 18 of the 27 neighbour cells net > $0").

    touch buffer {0.15, 0.25, 0.35} x ATR
  x close-through buffer {0.05, 0.10, 0.20} x ATR
  x pivot L=R {3, 5, 8}
  = 27 cells, "bounce" (the main rule set only -- variants/controls are
    "never ranked", sec 2.5's own header), 4-hour chart, 1 MCL, mid
    friction, TRAINING SIDE ONLY, net per cell and the share net positive.

E0's own higher-chart line geometry stays at its registered default
(PIVOT_R) for every cell -- sec 3 names the entry line's own pivot size as
the swept dimension, not E0's separate filter, and E0 does not depend on
the grid's varied R/buffers, so it is computed ONCE and reused across all
27 cells rather than rebuilt 27 times for an unchanged result.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from strategy.htf.signals import swing_highs, swing_lows
from strategy.tl_bounce import engine as E
from strategy.tl_bounce import lines as L
from strategy.tl_bounce.signals import Signals
from strategy.tl_bounce.spec import (GRID_PIVOT_R, GRID_TOUCH_BUF, GRID_X1_BUF,
                                     TRAIN_END, TRAIN_START, TRAIL_L, TRAIL_R)

N_CELLS = len(GRID_TOUCH_BUF) * len(GRID_X1_BUF) * len(GRID_PIVOT_R)
assert N_CELLS == 27


def cells():
    """The 27 (touch_buf, x1_buf, pivot_R) combinations, fixed product
    order, so a grid's cell list is reproducible."""
    return list(itertools.product(GRID_TOUCH_BUF, GRID_X1_BUF, GRID_PIVOT_R))


def _cell_sig(entry_frame: pd.DataFrame, *, touch_buf: float, x1_buf: float, R: int,
             e0: np.ndarray | None) -> Signals:
    o, h, lo, c = (entry_frame[k + "_adj"].to_numpy(dtype=float) for k in
                   ("open", "high", "low", "close"))
    lns = L.entry_lines(o, h, lo, c, R=R, x1_buf=x1_buf)
    touch_long, touch_short = L.touch_signals(lo, h, c, lns, buf=touch_buf)
    swlo = pd.Series(swing_lows(pd.Series(lo), TRAIL_L, TRAIL_R)).ffill().to_numpy()
    swhi = pd.Series(swing_highs(pd.Series(h), TRAIL_L, TRAIL_R)).ffill().to_numpy()
    return Signals(o, h, lo, c, lns.atr, lns.sup, lns.sup_breaks, lns.res, lns.res_breaks,
                   touch_long, touch_short, swlo, swhi, e0)


def run_grid(entry_frame: pd.DataFrame, higher_frame: pd.DataFrame, higher_bar_hours: int,
            hourly: pd.DataFrame, *, symbol: str = "MCL", level: str = "mid",
            qty: int = 1) -> dict:
    e0 = L.e0_filter(entry_frame, higher_frame, higher_bar_hours)

    rows = []
    for touch_buf, x1_buf, R in cells():
        sig = _cell_sig(entry_frame, touch_buf=touch_buf, x1_buf=x1_buf, R=R, e0=e0)
        trades, counts = E.simulate_market(entry_frame, higher_frame, higher_bar_hours, hourly,
                                           e0_on=True, x1_on=True, allow_reentry=True, sig=sig)
        train_trades = [t for t in trades
                        if TRAIN_START <= str(t.session)[:10] <= TRAIN_END]
        net = sum(t.net_pnl(symbol, level, qty) for t in train_trades)
        rows.append({"touch_buf": touch_buf, "x1_buf": x1_buf, "pivot_R": R,
                    "net": net, "trades": len(train_trades)})

    n_positive = sum(1 for r in rows if r["net"] > 0)
    return {"cells": rows, "n_positive": n_positive, "n_total": len(rows),
           "share_positive": n_positive / len(rows) if rows else 0.0}
