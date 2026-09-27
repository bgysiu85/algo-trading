#!/usr/bin/env python3
"""HTF-Ben v2 neighbour grid, REGISTERED_htf_ben_v2.md sec 4 criterion 8,
sec 5.3. W15-0021.

Sec 5.3: v1's own 24-cell entry-side grid already showed v1's entries are
not fragile (24/24 net-positive) -- not re-asked here, because v2 changes
nothing about entries. What v2 changes is the exit, so this grid re-tests
the EXIT parameters instead, using v0's original exit-grid dimensions:
swing size L = R in {2, 3} (S1) x trail trigger in {$0.10, $0.20, $0.40}
(S2) -- 6 cells (2 x 3), net at mid friction, training side, scenario B.
Criterion 8's bar is 4 of 6 (sec 4 item 8) -- the same ~two-thirds bar as
v0's 12/18 and v1's 16/24, scaled to a smaller, exit-only grid.

Every cell is v2 run again (v2_runner.run_v2, entries fixed at v1's own
registered settings -- cross_window/curl/F1/F2 never vary here, only
swing_LR and trail_trigger) with one of the 6 (swing_LR, trail_trigger)
pairs swapped in -- nothing here is a new backtest engine, it is v2's own
engine run 6 times. "Reported, unranked" (sec 3 item 7, sec 5.3): this
module never picks a best cell, it only counts how many of the 6 are
net-positive.
"""
from __future__ import annotations

import itertools

import pandas as pd

from strategy.htf import v2_runner as V2R

SWING_SIZES = (2, 3)                 # sec 5.3: "swing size L = R in {2, 3}"
TRAIL_TRIGGERS = (0.10, 0.20, 0.40)  # sec 5.3: "trail trigger in {$0.10, $0.20, $0.40}"

N_CELLS = len(SWING_SIZES) * len(TRAIL_TRIGGERS)
assert N_CELLS == 6


def cells():
    """The 6 (swing_LR, trail_trigger) combinations, in a fixed order
    (product order) so a grid's cell list is reproducible."""
    return list(itertools.product(SWING_SIZES, TRAIL_TRIGGERS))


def cell_id(swing_LR: int, trail_trigger: float) -> str:
    return f"swing{swing_LR}_trail{trail_trigger:.2f}"


def run_cell(df_1h: pd.DataFrame, *, scenario: str, q_h: float, q_e: float,
            swing_LR: int, trail_trigger: float, symbol: str = "MCL",
            level: str = "mid", train_start=None, train_end=None) -> dict:
    """One neighbour-grid cell: v2's full entry rule set (nothing disabled
    -- unlike C1) with this cell's own swing_LR/trail_trigger. net/
    trades_taken are at `symbol`/`level` friction (mid, per sec 5.3).

    train_start/train_end (same convention as neighbours.py's/v1_grid.py's
    own run_grid): if given, net/trades_taken are summed over trades whose
    own entry SESSION falls in [train_start, train_end] only. Left None
    (the default) for a quick check on a short synthetic archive where a
    date filter would empty every cell -- a real run passes
    strategy.htf.preflight.TRAIN_START/TRAIN_END."""
    trades, counts = V2R.run_v2(df_1h, scenario=scenario, q_h=q_h, q_e=q_e,
                                swing_LR=swing_LR, trail_trigger=trail_trigger)
    if train_start is not None or train_end is not None:
        trades = [t for t in trades
                 if (train_start is None or pd.Timestamp(t.session).date() >= train_start)
                 and (train_end is None or pd.Timestamp(t.session).date() <= train_end)]
    net = sum(t.net_pnl(symbol, level) for t in trades)
    return {
        "cell": cell_id(swing_LR, trail_trigger),
        "swing_LR": swing_LR, "trail_trigger": trail_trigger,
        "net": net, "trades_taken": len(trades), "counts": counts,
    }


def run_grid(df_1h: pd.DataFrame, *, scenario: str = "B", q_h: float, q_e: float,
            symbol: str = "MCL", level: str = "mid", train_start=None,
            train_end=None) -> dict:
    """All 6 cells, reported unranked (sec 5.3) -- callers must not sort
    `cells` by net; the order here is a fixed nested loop (swing_LR, then
    trail_trigger), not a ranking. train_start/train_end: see run_cell."""
    rows = [
        run_cell(df_1h, scenario=scenario, q_h=q_h, q_e=q_e, swing_LR=swing_LR,
                trail_trigger=trail_trigger, symbol=symbol, level=level,
                train_start=train_start, train_end=train_end)
        for swing_LR in SWING_SIZES for trail_trigger in TRAIL_TRIGGERS
    ]
    n_positive = sum(1 for r in rows if r["net"] > 0)
    return {
        "scenario": scenario, "symbol": symbol, "level": level,
        "n_cells": len(rows), "n_net_positive": n_positive,
        "share_net_positive": n_positive / len(rows) if rows else float("nan"),
        "cells": rows,
    }
