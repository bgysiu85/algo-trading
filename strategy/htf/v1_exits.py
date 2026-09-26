#!/usr/bin/env python3
"""HTF-Ben v1 exit simulation: v0's S1/S2 (initial stop, half-profit trail,
unchanged) plus X1 (opposite MACD-histogram-zero cross) and X2 (EMA9 turn),
whichever comes first. W15-0011, REGISTERED_htf_ben_v1.md sec 2.2.

WHY THIS IS ITS OWN WALK, NOT A WRAPPER AROUND exits.simulate_exit
---------------------------------------------------------------------
X1/X2 are evaluated "on the close of any entry-chart bar after the fill
bar" -- i.e. once per completed entry-chart bucket, exactly the granularity
strategy/htf/exits.py's own walk already recomputes the S2 trail at (that
module's own docstring: "S3 says the trail is checked ... once per
completed entry-chart bar"). So this reuses that walk's bucket-boundary
structure verbatim (same peak/trail/stop arithmetic, same 1-hour-grid S4
stop test, same session-flatten check) and adds ONE thing at each bucket
transition: whether the entry-chart bar that JUST closed fired X1 or X2, in
which case the position exits immediately at THIS hour's own open -- which
is, by construction of the transition happening exactly on entering a new
bucket, the very "next bar's open" the rule calls for.

'WHICHEVER COMES FIRST', WITHOUT EXTRA BOOKKEEPING
-------------------------------------------------------
REGISTERED sec 2.2: "If a stop and a signal exit fall in the same bar, the
stop ... takes precedence when it is hit before that bar closes; otherwise
the signal exit fills at the next open." This walk's own per-hour stop test
already runs BEFORE the bucket-boundary code that would check X1/X2 for the
bar that just closed -- so a stop hit anywhere inside that bar already
returns, and the X1/X2 check for it is never reached. No separate
"signal armed" state is carried across iterations: the check happens once,
at the transition, and returns immediately if it fires, which is exactly
"the next bar's open" (this transition's own `pos`).

ASSUMPTION FLAGGED, same spirit as v1_lines.py's/v1_signals.py's own notes:
sec 2.2 does not say which of X1/X2 wins if both fire on the same bar; this
checks X1 first (an arbitrary but fixed tie-break). It also reads "hist
crosses to <=0" (X1, long) as the same boundary convention E1a's own
up-cross uses (hist[t-1] <= 0 < hist[t]), mirrored: hist[t-1] > 0 AND
hist[t] <= 0 -- not signals.macd_cross_down, whose own boundary (prev >= 0,
now < 0) differs by one tie case.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf import exits as EX

TRAIL_TRIGGER = EX.TRAIL_TRIGGER

# R_INITIAL_STOP=0, R_TRAILED_STOP=1 kept at the same positions as exits.py's
# own codes so a shared REASONS lookup by position stays meaningful; X1/X2
# inserted before the shared SESSION_FLAT/DATA_END tail.
R_INITIAL_STOP, R_TRAILED_STOP, R_X1, R_X2, R_SESSION_FLAT, R_DATA_END = range(6)
REASONS = ("initial_stop", "trailed_stop", "x1_opposite_cross", "x2_ema9_turn",
          "session_flat", "data_end")


@dataclass
class ExitOutcomeV1:
    exit_pos: int
    exit_price: float
    reason: int
    trail_started: bool


def entry_bar_lookup(entry_adj: pd.DataFrame) -> dict:
    """{(session, bucket): row position in entry_adj}. An hourly grid row's
    own (session, bar // bar_hours) key lands on exactly this entry-chart
    bar's row -- bars.resample() makes 'bar' the bucket index on both grids
    (its own docstring), so this needs no timestamp arithmetic."""
    sessions = entry_adj["session"].to_numpy()
    bars = entry_adj["bar"].to_numpy()
    return {(s, int(b)): i for i, (s, b) in enumerate(zip(sessions, bars))}


def x_signal_series(hist: pd.Series, ema9: pd.Series):
    """(x1_long, x1_short, x2_long, x2_short), all on the entry chart.
    X1 long: hist crosses to <= 0 (hist = MACD - signal; a MACD-below-
    signal cross). X1 short is the mirror (crosses to >= 0). X2 long:
    EMA9[b] < EMA9[b-1]; X2 short is the mirror."""
    prev = hist.shift(1)
    x1_long = ((prev > 0) & (hist <= 0)).fillna(False)
    x1_short = ((prev < 0) & (hist >= 0)).fillna(False)
    x2_long = (ema9 < ema9.shift(1)).fillna(False)
    x2_short = (ema9 > ema9.shift(1)).fillna(False)
    return x1_long, x1_short, x2_long, x2_short


def simulate_exit_v1(hourly: pd.DataFrame, entry_lookup: dict, *, start_pos: int,
                     fill_entry_idx: int, direction: str, fill_price: float,
                     initial_stop: float, bar_hours: int, session_flatten: bool,
                     x1_long: np.ndarray, x1_short: np.ndarray,
                     x2_long: np.ndarray, x2_short: np.ndarray,
                     trail_trigger: float = TRAIL_TRIGGER) -> ExitOutcomeV1:
    """v0's S1/S2/S3/S4 walk (exits.simulate_exit) plus X1/X2, 'whichever
    comes first' (module docstring). `fill_entry_idx` is the fill bar's own
    row position in entry_adj -- X1/X2 are only evaluated for entry-chart
    bars strictly after it (sec 2.2: 'any entry-chart bar after the fill
    bar'), so the fill bar's own bucket transition is skipped."""
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
    peak = fill_price
    trail_started = False
    bucket_extreme = None
    prev_key = None

    for pos in range(start_pos, n):
        row = hourly.iloc[pos]
        key = (row["session"], int(row["bar"]) // bar_hours)
        if prev_key is not None and key != prev_key:
            if is_long:
                peak = max(peak, bucket_extreme)
                if peak - fill_price >= trail_trigger:
                    candidate = fill_price + (peak - fill_price) / 2.0
                    new_stop = max(stop, candidate)
                    if new_stop > stop:
                        trail_started = True
                    stop = new_stop
            else:
                peak = min(peak, bucket_extreme)
                if fill_price - peak >= trail_trigger:
                    candidate = fill_price - (fill_price - peak) / 2.0
                    new_stop = min(stop, candidate)
                    if new_stop < stop:
                        trail_started = True
                    stop = new_stop
            bucket_extreme = None

            closed_idx = entry_lookup.get(prev_key)
            if closed_idx is not None and closed_idx > fill_entry_idx:
                x1_ok = bool(x1_long[closed_idx]) if is_long else bool(x1_short[closed_idx])
                x2_ok = bool(x2_long[closed_idx]) if is_long else bool(x2_short[closed_idx])
                if x1_ok or x2_ok:
                    reason = R_X1 if x1_ok else R_X2
                    return ExitOutcomeV1(pos, float(open_[pos]), reason, trail_started)
        prev_key = key

        if is_long:
            hit = low[pos] <= stop
        else:
            hit = high[pos] >= stop
        if hit:
            if is_long:
                px = open_[pos] if open_[pos] <= stop else stop
            else:
                px = open_[pos] if open_[pos] >= stop else stop
            reason = R_TRAILED_STOP if trail_started else R_INITIAL_STOP
            return ExitOutcomeV1(pos, float(px), reason, trail_started)

        if session_flatten and EX._is_session_last_hour(hourly, pos):
            return ExitOutcomeV1(pos, float(close[pos]), R_SESSION_FLAT, trail_started)

        bucket_extreme = (high[pos] if bucket_extreme is None else max(bucket_extreme, high[pos])) \
            if is_long else \
            (low[pos] if bucket_extreme is None else min(bucket_extreme, low[pos]))

    return ExitOutcomeV1(n - 1, float(close[n - 1]), R_DATA_END, trail_started)
