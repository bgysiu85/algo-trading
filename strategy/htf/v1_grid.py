#!/usr/bin/env python3
"""HTF-Ben v1 neighbour grid, REGISTERED_htf_ben_v1.md sec 3. W15-0011.

Section 3, verbatim: "Neighbour grid (24 cells, reported unranked):
confirmation window {2, 3} x range length N {9, 12} x range percentile
{20, 25, 33} x X2 {1 bar, 2 bars}; net at mid friction per cell and the
share net positive." Section 3 also says, just above the table: "Nothing is
ranked. No 'best cell' table." -- this module reports every cell's own net
and the one summary share-net-positive figure; it does not sort or pick a
best cell, and report wiring (v1_report.py) must not either.

WHY EACH CELL RECOMPUTES q_h/q_e, RATHER THAN REUSING THE REGISTERED ONES
--------------------------------------------------------------------------
q_h and q_e are themselves defined AS "the Nth percentile of [the F1 ratio],
computed over training-side bars" (sec 2.1) -- for a GIVEN window N and a
GIVEN percentile. Amendment C's registered q_h=0.190280/q_e=0.501239 are
that computation at N=9, 25th percentile ONLY (v1's own primary cell, which
is why it is not run again below -- see PRIMARY_CELL). Every other cell in
this grid asks "what if N or the percentile were different", which changes
the very quantity q_h/q_e measures, not just how it's used -- so each cell
calls v1_preflight.compute_percentiles(window=N, pctl=P) itself, on the
same training-side 4-hour bars, exactly as G2 did for the registered pair.
This is looking, not spending: the neighbour grid is a reported diagnostic
(sec 3), never a candidate for the holdout (sec 2.4's table; v1-curl/
v1-F1/v1-F2/v1-X are the only registered ablations, and none of them is a
grid cell), so recomputing q_h/q_e per cell on training-side bars carries
no multiplicity cost against sec 7's registered budget.

WHY THIS CALLS v1_preflight.detect_v1 AND v1_runner.simulate_v1 DIRECTLY,
NOT v1_runner.run_v1
--------------------------------------------------------------------------
run_v1 always recomputes q_h/q_e's underlying ratio arrays at its own
f1_window default and does not accept a q_h/q_e computed at a DIFFERENT
window as an override that also changes which ratio array f1_blocked_at
reads against -- it has no x2_bars parameter either. Rather than grow
run_v1's signature with grid-only knobs it should never need outside this
module, run_cell below wires detect_v1/simulate_v1 itself, passing the
per-cell ratio_h/ratio_e/q_h/q_e/line_low/line_high/atr through exactly as
v1_preflight.run() already does for its own three ablations.
"""
from __future__ import annotations

import pandas as pd

from strategy.htf import bars as B
from strategy.htf import preflight as P
from strategy.htf import v1_exits as V1E
from strategy.htf import v1_lines as V1L
from strategy.htf import v1_preflight as V1P
from strategy.htf import v1_runner as V1R

CROSS_WINDOWS = (2, 3)          # sec 3: "confirmation window {2, 3}"
F1_WINDOWS = (9, 12)            # sec 3: "range length N {9, 12}"
F1_PERCENTILES = (20, 25, 33)   # sec 3: "range percentile {20, 25, 33}"
X2_BAR_COUNTS = (1, 2)          # sec 3: "X2 {1 bar, 2 bars}"
N_CELLS = len(CROSS_WINDOWS) * len(F1_WINDOWS) * len(F1_PERCENTILES) * len(X2_BAR_COUNTS)  # 24

# v1's own registered primary: cross_window=3 (CROSS_CONFIRM_WINDOW), N=9
# (F1_WINDOW_4H), 25th percentile, X2=1 bar. Already run and registered
# (Amendment C) -- flagged here, not skipped, so a caller iterating ALL_CELLS
# can tell v1's own numbers apart from a genuinely new grid cell without
# re-deriving the tuple by hand.
PRIMARY_CELL = (V1P.CROSS_CONFIRM_WINDOW, 9, V1P.F1_PERCENTILE, 1)


def cell_id(cross_window: int, f1_window: int, pctl: int, x2_bars: int) -> str:
    return f"cw{cross_window}_n{f1_window}_p{pctl}_x2b{x2_bars}"


def run_cell(df_1h: pd.DataFrame, *, scenario: str, cross_window: int, f1_window: int,
            pctl: int, x2_bars: int, trail_trigger: float = V1E.TRAIL_TRIGGER,
            symbol: str = "MCL", level: str = "mid", train_start=None,
            train_end=None) -> dict:
    """One neighbour-grid cell: v1's full rule set (curl route, F2, T, E3 --
    nothing here disables any of those, unlike the sec 2.4 ablations) with
    this cell's own cross_window/F1-window/F1-percentile/X2-bar-count.
    net/trades_taken are at `symbol`/`level` friction (mid, per sec 3).

    train_start/train_end (same convention as neighbours.py's own
    run_grid, sec 4 criterion 8's "training side"): if given, net/
    trades_taken are summed over trades whose own entry SESSION falls in
    [train_start, train_end] only. Left None (the default) for a quick
    check on a short synthetic archive where a date filter would empty
    every cell -- a real run passes v1_preflight.TRAIN_START/TRAIN_END."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    four_h_adj = grids["4H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]

    q_h, q_e, ratio_h, ratio_e, atr = V1P.compute_percentiles(four_h_adj, window=f1_window,
                                                              pctl=pctl)
    line_low, line_high, _ = V1L.build_4h_lines(four_h_adj)

    entries, counts = V1P.detect_v1(
        entry_adj, daily_adj, four_h_adj, scenario=scenario, q_h=q_h, q_e=q_e,
        cross_window=cross_window, f1_window=f1_window,
        line_low=line_low, line_high=line_high, atr=atr,
        ratio_h=ratio_h, ratio_e=ratio_e)

    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = V1R.simulate_v1(entries, hourly, entry_adj, bar_hours=bar_hours,
                                        session_flatten=session_flatten,
                                        trail_trigger=trail_trigger, x2_bars=x2_bars)
    if train_start is not None or train_end is not None:
        trades = [t for t in trades
                 if (train_start is None or pd.Timestamp(t.session).date() >= train_start)
                 and (train_end is None or pd.Timestamp(t.session).date() <= train_end)]
    net = sum(t.net_pnl(symbol, level) for t in trades)

    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return {
        "cell": cell_id(cross_window, f1_window, pctl, x2_bars),
        "cross_window": cross_window, "f1_window": f1_window, "f1_percentile": pctl,
        "x2_bars": x2_bars, "q_h": q_h, "q_e": q_e,
        "is_primary": (cross_window, f1_window, pctl, x2_bars) == PRIMARY_CELL,
        "net": net, "trades_taken": len(trades), "counts": counts,
    }


def run_grid(df_1h: pd.DataFrame, *, scenario: str = "B", symbol: str = "MCL",
            level: str = "mid", train_start=None, train_end=None) -> dict:
    """All 24 cells, reported unranked (sec 3: "Nothing is ranked. No 'best
    cell' table.") -- callers must not sort `cells` by net; the order here
    is a fixed nested loop (cross_window, then N, then percentile, then
    X2), not a ranking. train_start/train_end: see run_cell."""
    cells = [
        run_cell(df_1h, scenario=scenario, cross_window=cw, f1_window=n, pctl=p,
                x2_bars=x2b, symbol=symbol, level=level, train_start=train_start,
                train_end=train_end)
        for cw in CROSS_WINDOWS for n in F1_WINDOWS for p in F1_PERCENTILES
        for x2b in X2_BAR_COUNTS
    ]
    n_positive = sum(1 for c in cells if c["net"] > 0)
    return {
        "scenario": scenario, "symbol": symbol, "level": level,
        "n_cells": len(cells), "n_net_positive": n_positive,
        "share_net_positive": n_positive / len(cells) if cells else float("nan"),
        "cells": cells,
    }
