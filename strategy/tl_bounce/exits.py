#!/usr/bin/env python3
"""1-hour-granularity exit walk for a filled TL-bounce trade: S1 initial
stop, S2 trail (line/swing formula), X1 close-through-the-line exit. W15-0016
(the full backtest engine). REGISTERED_tl_bounce.md sec 2.3.

Mirrors strategy/htf/exits.py's split between the two rules' cadences: the
trail LEVEL is recomputed once per completed ENTRY-CHART bar (from the same
Signals arrays signals.py/sim.py already build), but the stop is TESTED
every 1-hour bar so the exit hour is known exactly -- sec 2.3 "Fills":
"stops tested on 1-hour bars ... as HTF-Ben v0 S3-S4". Unlike HTF-Ben v0,
there is NO session flatten here: sec 2.3 "No target -- we want to get in
for this entire trend."

WHY THE TRAIL FORMULA IS RE-IMPLEMENTED HERE RATHER THAN IMPORTED FROM sim.py
-------------------------------------------------------------------------------
sim.py's own module docstring freezes it as "G2's walk ... NOT the full
backtest engine" -- already delivered, tested and committed for W15-0015.
Rather than refactor a delivered, tested module to serve a second caller,
this module reimplements S2's formula exactly as sim.py's step 4 does it,
and tests/strategy/tl_bounce/test_exits.py::test_trail_matches_sim_formula
cross-checks the two bar-for-bar on a shared synthetic Signals fixture, so a
drift between them would fail loudly rather than silently.

WHY EXIT_BUCKET_J IS RETURNED, NOT JUST THE 1H POSITION
------------------------------------------------------------
engine.py needs to know which ENTRY-CHART bar the exit belongs to, both to
resume the E1-E4 scan strictly after it (sec 2.2 E4: "the exit bar itself
cannot be a touch bar") and to count "ignored_in_position" touch bars for
sec 3's counts. Returning the 1H position alone would make the caller
re-derive that bucket a second time from the same bucket_idx array this
module already walks.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.tl_bounce.spec import STOP_BUF

R_INITIAL_STOP, R_TRAILED_STOP, R_X1, R_DATA_END = range(4)
REASONS = ("initial_stop", "trailed_stop", "X1", "data_end")


@dataclass
class ExitOutcome:
    exit_pos: int          # iloc into the 1H grid
    exit_bucket_j: int     # entry-chart bar index the exit hour belongs to
    exit_price: float      # back-adjusted (1H grid's own series)
    reason: int
    trail_started: bool


def trail_candidate(sup_j: float, res_j: float, swing_low_j: float, swing_high_j: float,
                    atr_j: float, direction: str) -> float:
    """S2's candidate new stop level from one entry-chart bar's own close
    values -- the same formula strategy.tl_bounce.sim.simulate's step 4
    applies inline, exposed here as a pure function so it can be called at
    1-hour-walk bucket boundaries AND cross-checked against sim.py's own
    walk in tests."""
    if direction == "long":
        line_ref = sup_j if not np.isnan(sup_j) else np.inf
        return min(swing_low_j, line_ref) - STOP_BUF * atr_j
    else:
        line_ref = res_j if not np.isnan(res_j) else -np.inf
        return max(swing_high_j, line_ref) + STOP_BUF * atr_j


def x1_fires(sup_breaks_j: bool, res_breaks_j: bool, direction: str) -> bool:
    return bool(sup_breaks_j) if direction == "long" else bool(res_breaks_j)


def simulate_trade_exit(hourly: pd.DataFrame, bucket_idx: np.ndarray, sig, *,
                        fill_j: int, start_pos: int, direction: str, initial_stop: float,
                        x1_on: bool) -> ExitOutcome:
    """hourly: the back-adjusted 1H grid (strategy.htf.bars.back_adjust of
    strategy.htf.bars.resample(df_1h, "1H")), with 'open_adj'/'high_adj'/
    'low_adj'/'close_adj' columns. bucket_idx: len(hourly) int array,
    bucket_idx[p] = the entry-chart bar index 1H row p falls inside (see
    engine.hourly_bucket_index). sig: the entry-chart Signals for THIS
    market/chart (signals.market_signals's own object; sup/res/swing_low/
    swing_high/atr/sup_breaks/res_breaks all indexed by entry-chart bar).
    fill_j: entry-chart bar whose OPEN is the fill (E2 -- touch bar + 1).
    start_pos: hourly.iloc[start_pos] must be the fill hour (its own
    t_open aligned to fill_j's t_open, same convention as
    strategy.htf.exits.find_start_pos -- engine.py's job to align).
    initial_stop: an absolute price level on the SAME back-adjusted series
    as `hourly` (engine.py re-anchors the entry-chart-derived stop
    DISTANCE onto the hourly grid's own fill price before calling this,
    same convention as strategy.htf.runner.simulate's own re-anchoring,
    for the same reason: the entry-chart and hourly grids' back-adjustment
    offsets are independently accumulated and only guaranteed to agree
    away from a roll)."""
    n = len(hourly)
    if start_pos >= n:
        raise IndexError("start_pos beyond the end of the hourly grid")
    is_long = direction == "long"
    if not is_long and direction != "short":
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")

    open_ = hourly["open_adj"].to_numpy()
    high = hourly["high_adj"].to_numpy()
    low = hourly["low_adj"].to_numpy()
    close = hourly["close_adj"].to_numpy()

    stop = initial_stop
    trail_started = False
    j = fill_j
    n_sig = sig.n

    for pos in range(start_pos, n):
        cur_j = int(bucket_idx[pos])
        if cur_j != j:
            exit_here = False
            for bj in range(j, min(cur_j, n_sig)):
                cand = trail_candidate(sig.sup[bj], sig.res[bj], sig.swing_low[bj],
                                       sig.swing_high[bj], sig.atr[bj], direction)
                if np.isfinite(cand):
                    new_stop = max(stop, cand) if is_long else min(stop, cand)
                    if (is_long and new_stop > stop) or ((not is_long) and new_stop < stop):
                        trail_started = True
                    stop = new_stop
                if x1_on and x1_fires(sig.sup_breaks[bj], sig.res_breaks[bj], direction):
                    exit_here = True
                    break
            j = cur_j
            if exit_here:
                return ExitOutcome(pos, cur_j, float(open_[pos]), R_X1, trail_started)

        hit = (low[pos] <= stop) if is_long else (high[pos] >= stop)
        if hit:
            if is_long:
                px = open_[pos] if open_[pos] <= stop else stop
            else:
                px = open_[pos] if open_[pos] >= stop else stop
            reason = R_TRAILED_STOP if trail_started else R_INITIAL_STOP
            return ExitOutcome(pos, cur_j, float(px), reason, trail_started)

        if pos == n - 1:
            return ExitOutcome(pos, cur_j, float(close[pos]), R_DATA_END, trail_started)

    return ExitOutcome(n - 1, j, float(close[n - 1]), R_DATA_END, trail_started)


def hourly_bucket_index(hourly_t_open: pd.Series, entry_t_open: pd.Series) -> np.ndarray:
    """bucket_idx[p] = the entry-chart bar index whose bucket the hourly
    row p (by its own t_open) falls inside -- the largest entry-chart
    t_open <= the hourly row's own t_open (entry-chart buckets are
    contiguous and start at their own t_open, strategy.htf.bars.resample's
    own convention, so this is a plain right-side search)."""
    idx = np.searchsorted(entry_t_open.to_numpy(), hourly_t_open.to_numpy(), side="right") - 1
    return idx.astype(np.int64)


def find_start_pos(hourly_t_open: pd.Series, t_open) -> int:
    """The hourly grid's row position AT OR IMMEDIATELY AFTER a fill's own
    t_open -- identical convention to strategy.htf.exits.find_start_pos
    (see its own docstring for why a real archive gap can make this not an
    exact match, and why the first-available-hour reading is correct)."""
    pos = int(hourly_t_open.searchsorted(pd.Timestamp(t_open), side="left"))
    if pos >= len(hourly_t_open):
        raise KeyError(f"no hourly bar at or after t_open={t_open!r}")
    return pos
