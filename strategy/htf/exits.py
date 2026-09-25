#!/usr/bin/env python3
"""HTF-Ben exit simulation (S1-S5, REGISTERED_htf_ben_v0.md sec 2.3). W15-0004
step 7.

WHAT THIS DOES AND DOES NOT DO
-------------------------------
Walks the BACK-ADJUSTED 1-hour series from an entry's fill forward, applying
S1 (initial stop, already computed by preflight._initial_stop and passed in),
S2 (half-profit trail), S3 (trail checked on completed ENTRY-CHART bars, a
new level takes effect only from the NEXT entry-chart bar) and S4 (the stop
itself is TESTED hour by hour, so the exit hour is known exactly, not just
the entry-chart bar it falls in). Scenario A additionally flattens at the
close of the session's last hourly bar (no new entry chart concept needed --
the session-end IS an hourly-bar event).

Deliberately does NOT price the exit (no slippage, no commission) and does
NOT know about rolls or the raw held-contract series: REGISTERED sec 2.1 puts
signal/trail computation on the back-adjusted series and P&L on the raw held
one ("its stop moved by the same roll gap so its distance is unchanged"), so
this module returns WHERE and WHY a position exits (an hourly-bar index into
the same 1H grid preflight.py already builds, plus the back-adjusted exit
price for record-keeping), and the runner (step 7's next piece) is what maps
that index onto the raw series, charges commission/slippage per REGISTERED
sec 2.5 and books roll legs. Keeping those separate is what makes each one
testable against a small hand-built frame instead of only against a full
archive.

WHY THE WALK USES THE 1-HOUR GRID, NOT THE ENTRY-CHART GRID
--------------------------------------------------------------
S3 says the trail is *checked* -- i.e. its LEVEL is recomputed -- once per
completed entry-chart bar. S4 says the stop is *tested* on 1-hour bars, "so
the time of the exit is known to the hour". Those are two different
granularities of the same rule, and simulating only at entry-chart-bar
resolution would silently lose intra-bar detail S4 explicitly asks for (a
4-hour bar's low reaching the stop on its very first hour vs its last is a
real difference in what actually happens, and in scenario A's flat-by-17:00
rule the exact hour also decides which trades even reach the flatten). So the
walk steps through the 1-hour back-adjusted frame (preflight.prepare_grids's
own grids["1H"]) and only reads/writes the trail level at the boundaries
between entry-chart buckets, derived from each hourly row's own 'bar' column
(REGISTERED sec 2.1's bucket numbering, 0..22 within a session) floor-divided
by the scenario's bar_hours -- so this module needs no timestamp arithmetic
of its own and inherits bars.py's DST/session handling for free.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRAIL_TRIGGER = 0.20   # $/bbl, S2, Ben's confirmed figure

# exit reason codes -- REGISTERED sec 3 item 4: "initial stop / trailed
# stop / 17:00 flat (A) / data end"
R_INITIAL_STOP, R_TRAILED_STOP, R_SESSION_FLAT, R_DATA_END = range(4)
REASONS = ("initial_stop", "trailed_stop", "session_flat", "data_end")


@dataclass
class ExitOutcome:
    exit_pos: int            # position (iloc) into the 1H grid passed in
    exit_price: float        # back-adjusted; NOT the raw-series P&L price
    reason: int
    trail_started: bool      # S2 ever triggered before this exit (sec 3 item 4)


def _bucket_key(hourly: pd.DataFrame, pos: int, bar_hours: int):
    row = hourly.iloc[pos]
    return (row["session"], int(row["bar"]) // bar_hours)


def _is_session_last_hour(hourly: pd.DataFrame, pos: int) -> bool:
    """True if this hourly row is the last one of its session (either the
    frame ends here, or the next row belongs to a different session) --
    matches signals.session_last_bar_mask's intent but at 1-hour granularity,
    since the flatten is an hourly-bar event regardless of the scenario's own
    entry-chart bar size."""
    if pos == len(hourly) - 1:
        return True
    return hourly["session"].iloc[pos + 1] != hourly["session"].iloc[pos]


def simulate_exit(hourly: pd.DataFrame, *, start_pos: int, direction: str,
                  fill_price: float, initial_stop: float, bar_hours: int,
                  session_flatten: bool, trail_trigger: float = TRAIL_TRIGGER) -> ExitOutcome:
    """hourly: the back-adjusted 1H grid (preflight.prepare_grids's
    grids["1H"]), with 'session', 'bar', 'open_adj'/'high_adj'/'low_adj'/
    'close_adj' columns. start_pos: hourly.iloc[start_pos] must be the fill
    hour (its open_adj equals fill_price -- the caller's job to align, same
    as preflight's own t_open-matching convention). trail_trigger defaults
    to the registered $0.20/bbl (S2); overridable only for the neighbour
    grid (REGISTERED sec 3 item 8: trail trigger in {$0.10, $0.20, $0.40})."""
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
    peak = fill_price               # highest high (long) / lowest low (short) since entry
    trail_started = False
    bucket_extreme = None           # accumulates this entry-chart bucket's own high/low
    prev_key = None

    for pos in range(start_pos, n):
        key = _bucket_key(hourly, pos, bar_hours)
        if prev_key is not None and key != prev_key:
            # the previous entry-chart bar just closed: fold its extreme into
            # peak and, only now, recompute the trail (S3: "a new stop takes
            # effect from the next bar" -- so this bucket's own hours, tested
            # below, still see the OLD stop; only pos+1 onward sees the new one)
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
        prev_key = key

        # S4: the resting stop tested against THIS hour, at the level fixed
        # as of the previous entry-chart bar's close (or S1's initial level
        # for the very first bucket).
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
            return ExitOutcome(pos, float(px), reason, trail_started)

        if session_flatten and _is_session_last_hour(hourly, pos):
            return ExitOutcome(pos, float(close[pos]), R_SESSION_FLAT, trail_started)

        bucket_extreme = (high[pos] if bucket_extreme is None else max(bucket_extreme, high[pos])) \
            if is_long else \
            (low[pos] if bucket_extreme is None else min(bucket_extreme, low[pos]))

    # ran off the end of the archive without a stop or a flatten
    return ExitOutcome(n - 1, float(close[n - 1]), R_DATA_END, trail_started)


def find_start_pos(hourly: pd.DataFrame, t_open) -> int:
    """The hourly grid's row position whose t_open matches an entry's fill
    t_open exactly -- bars.py's resample() sets an entry-chart bucket's
    t_open to its first source (here: first hourly) bar's own t_open, so this
    always finds a row, never interpolates. Raises if it does not (a caller
    bug, not a data gap -- the fill bar came FROM the archive)."""
    matches = np.flatnonzero((hourly["t_open"] == t_open).to_numpy())
    if len(matches) == 0:
        raise KeyError(f"no hourly bar at t_open={t_open!r}")
    return int(matches[0])
