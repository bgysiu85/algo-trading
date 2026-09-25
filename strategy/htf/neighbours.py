#!/usr/bin/env python3
"""HTF-Ben neighbour grid. W15-0004 step 7 checkpoint 7.
REGISTERED_htf_ben_v0.md sec 3 item 8 and sec 4 criterion 8.

"Neighbour grid (reported, unranked): trail trigger in {$0.10, $0.20,
$0.40}, confirmation window in {1, 2, 3} bars, swing size L = R in {2, 3}
-- 18 cells per scenario, net at mid friction, and the share of cells that
are net positive."

Every cell is v0 run again with one or more of those three parameters
swapped in (runner.run_v0's trail_trigger/confirm_window/swing_LR kwargs,
added in this checkpoint) -- nothing here is a new backtest engine, it is
the same engine run 18 times per scenario. "Reported, unranked" (sec 3
item 8) means this module never picks a best cell; it only counts how many
of the 18 are net-positive, which is what sec 4 criterion 8 scores (>= 12
of 18). The REGISTERED v0 cell (trail=$0.20, window=2, swing=2) is one of
the 18 and is not distinguished from the others in the grid's own output
-- callers wanting v0's own headline number already have it from
runner.run_v0's default call, separately.
"""
from __future__ import annotations

import itertools

import pandas as pd

from strategy.htf import runner as R

TRAIL_TRIGGERS = (0.10, 0.20, 0.40)
CONFIRM_WINDOWS = (1, 2, 3)
SWING_SIZES = (2, 3)

N_CELLS = len(TRAIL_TRIGGERS) * len(CONFIRM_WINDOWS) * len(SWING_SIZES)
assert N_CELLS == 18


def cells():
    """The 18 (trail_trigger, confirm_window, swing_LR) combinations, in a
    fixed order (product order) so a grid's cell list is reproducible."""
    return list(itertools.product(TRAIL_TRIGGERS, CONFIRM_WINDOWS, SWING_SIZES))


def run_grid(df_1h: pd.DataFrame, *, scenario: str, symbol: str = "MCL",
            level: str = "mid", qty: int = 1, train_start=None, train_end=None) -> dict:
    """Runs v0 18 times for one scenario, each with one cell's parameters.
    If train_start/train_end are given, each cell's net is summed over
    trades whose own session falls in [train_start, train_end] only (the
    training side, sec 5.2's window) -- the caller passes preflight's
    TRAIN_START/TRAIN_END for a real run; left None for a quick check on a
    short synthetic archive where a date filter would empty every cell.

    Returns {"cells": [{"trail_trigger", "confirm_window", "swing_LR",
    "net", "trades"}], "n_positive": int, "n_total": 18,
    "share_positive": float}.
    """
    rows = []
    for trail_trigger, confirm_window, swing_LR in cells():
        trades, _ = R.run_v0(df_1h, scenario=scenario, trail_trigger=trail_trigger,
                             confirm_window=confirm_window, swing_LR=swing_LR)
        if train_start is not None or train_end is not None:
            trades = [t for t in trades
                     if (train_start is None or pd.Timestamp(t.session).date() >= train_start)
                     and (train_end is None or pd.Timestamp(t.session).date() <= train_end)]
        net = sum(t.net_pnl(symbol, level, qty) for t in trades)
        rows.append({"trail_trigger": trail_trigger, "confirm_window": confirm_window,
                    "swing_LR": swing_LR, "net": net, "trades": len(trades)})

    n_positive = sum(1 for r in rows if r["net"] > 0)
    return {"cells": rows, "n_positive": n_positive, "n_total": len(rows),
           "share_positive": n_positive / len(rows) if rows else 0.0}
