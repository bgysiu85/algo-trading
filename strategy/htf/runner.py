#!/usr/bin/env python3
"""HTF-Ben runner: turns G2 preflight's independently-scored triggers into a
real, E5-enforced trade ledger with raw-series dollar P&L. W15-0004 step 7
checkpoint 3. REGISTERED_htf_ben_v0.md sec 2.1-2.5.

WHY THIS SITS ON TOP OF preflight.py RATHER THAN REPLACING IT
----------------------------------------------------------------
preflight.detect_v0/detect_c1 score every MACD trigger independently (their
own docstrings: E5 "one position at a time" is deliberately NOT applied,
because that needs to know when the prior trade exited, which needs exit
simulation, which G2 is forbidden from doing). Their entries list is
therefore an UPPER BOUND, time-ordered by construction (the detection loop
walks i in order). This module walks that same list once more, in order,
and applies E5 for real: a candidate whose fill bar is still inside an open
position is skipped (counted as ignored_in_position, per sec 3 item 8),
using each taken trade's ACTUAL exit time from exits.simulate_exit -- not a
fixed holding period.

WHY THE FILL/STOP ARE RE-ANCHORED TO THE 1-HOUR GRID, NOT REUSED AS-IS
--------------------------------------------------------------------------
preflight's fill_price and stop come from the entry-chart back-adjusted grid
(entry_adj, sec 2.1's "signal series"). exits.simulate_exit walks the
1-HOUR back-adjusted grid (its own docstring explains why: S3 vs S4 are two
different granularities of the same rule). A 2H/4H bucket's own
back-adjustment offset and the 1H grid's offset are computed independently
(each from its own held_id-change sequence) and are only guaranteed to
agree away from a roll -- so this module re-reads the fill price at the
SAME t_open from the 1-hour grid via exits.find_start_pos, which returns
that exact hourly row when the archive has one there (the ordinary case:
an entry-chart bucket's t_open is its first source hour's own t_open,
bars.resample()'s docstring) and the first REAL hour at or after it
otherwise -- a real gap inside that bucket (G1's own gaps_over reports
these exist; find_start_pos's own docstring has the full reasoning), not a
bug to raise on. It then rebuilds the initial stop there as fill_1h +/-
stop_dist, where
stop_dist (a $ distance, not a price level) is untouched from preflight's
own S1 computation. Walking the exit and pricing the roll on one single
series this way is what keeps "its stop moved by the same roll gap so its
distance is unchanged" (sec 2.1) true by construction rather than by a
separate correction step.

RAW P&L, SEC 2.1
-----------------
bars.back_adjust keeps the original raw open/high/low/close columns beside
the *_adj ones it adds, plus a per-row 'adj_offset' (the cumulative roll
gap folded into that row) and 'held_id'. Since adj = raw + offset at every
row, raw = adj - offset always -- so this module never re-derives a raw
price from OHLC logic a second time; it takes exits.py's back-adjusted
fill/exit price and subtracts that row's own offset. Subtracting a
DIFFERENT row's offset at the exit than at the entry is exactly what makes
a roll between them show up as the registered roll gap in the raw P&L,
with no special-casing.

Any held_id change strictly between the fill row and the exit row (both
inclusive of the exit, exclusive of the fill -- a roll AT the fill bar
itself cannot happen, the position does not exist before it) is one roll
leg: sec 2.1's "closed at the last 1-hour close of the old contract and
reopened at the first 1-hour open of the new one, with a full round-trip
cost charged" is priced as one extra round trip per roll (costs.py's
n_round_trips), not modelled bar-by-bar as two separate raw trades -- the
net raw P&L across the crossing is unaffected by which of the two
equivalent bookkeepings is used (both sum to the same raw close-to-close
telescoping sum), and only the cost differs, which this module charges
explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import costs as C
from strategy.htf import exits as E
from strategy.htf import preflight as P
from strategy.htf import tl_variant as TLV


@dataclass
class Trade:
    session: str
    direction: str
    entry_t: pd.Timestamp
    fill_adj: float
    fill_raw: float
    stop_dist: float
    initial_stop_adj: float
    start_pos: int
    exit_pos: int
    exit_t: pd.Timestamp
    exit_price_adj: float
    exit_price_raw: float
    exit_reason: str
    trail_started: bool
    n_rolls: int

    def gross_pnl(self, symbol: str, qty: int = 1) -> float:
        return C.pnl_dollars(symbol, self.fill_raw, self.exit_price_raw, self.direction, qty)

    def cost(self, symbol: str, level: str, qty: int = 1) -> float:
        return C.round_trip_cost(symbol, level, n_round_trips=1 + self.n_rolls, qty=qty)

    def net_pnl(self, symbol: str, level: str, qty: int = 1) -> float:
        return self.gross_pnl(symbol, qty) - self.cost(symbol, level, qty)


def _count_rolls(hourly: pd.DataFrame, start_pos: int, exit_pos: int) -> int:
    """held_id changes in (start_pos, exit_pos] -- a roll strictly after the
    fill and at or before the exit. A change AT start_pos itself is not a
    roll of this trade (the position opens there; nothing was held before it
    within this trade)."""
    if exit_pos <= start_pos:
        return 0
    held = hourly["held_id"].to_numpy()
    window = held[start_pos:exit_pos + 1]
    return int((window[1:] != window[:-1]).sum())


def simulate(entries: list[dict], hourly: pd.DataFrame, *, bar_hours: int,
            session_flatten: bool, trail_trigger: float = E.TRAIL_TRIGGER) -> tuple[list[Trade], int]:
    """entries: preflight's time-ordered, E5-UNAWARE candidate list (each
    dict has 'direction', 'stop_dist', 't_open'). Returns (taken_trades,
    n_ignored_in_position) -- E5 applied here, for real, against each taken
    trade's own simulated exit time. trail_trigger defaults to S2's
    registered $0.20/bbl; overridable only for the neighbour grid."""
    trades: list[Trade] = []
    n_ignored = 0
    blocked_until: pd.Timestamp | None = None

    for e in entries:
        t_open = pd.Timestamp(e["t_open"])
        if blocked_until is not None and t_open <= blocked_until:
            n_ignored += 1
            continue
        try:
            start_pos = E.find_start_pos(hourly, t_open)
        except KeyError:
            # find_start_pos already falls back across a real gap (its own
            # docstring); reaching here means there is nothing left at or
            # after t_open in the hourly grid AT ALL -- the fill is past the
            # end of the archive, which should not happen for an entry
            # bars.resample already proved has data, so a miss here is a
            # caller bug (e.g. the two grids built from different archives),
            # not a data gap -- surfaced, not swallowed
            raise
        fill_adj = float(hourly["open_adj"].iloc[start_pos])
        stop_dist = float(e["stop_dist"])
        direction = e["direction"]
        initial_stop_adj = (fill_adj - stop_dist) if direction == "long" else (fill_adj + stop_dist)

        outcome = E.simulate_exit(hourly, start_pos=start_pos, direction=direction,
                                  fill_price=fill_adj, initial_stop=initial_stop_adj,
                                  bar_hours=bar_hours, session_flatten=session_flatten,
                                  trail_trigger=trail_trigger)

        offset = hourly["adj_offset"].to_numpy()
        fill_raw = fill_adj - float(offset[start_pos])
        exit_raw = outcome.exit_price - float(offset[outcome.exit_pos])
        exit_t = hourly["t_open"].iloc[outcome.exit_pos]
        n_rolls = _count_rolls(hourly, start_pos, outcome.exit_pos)

        trades.append(Trade(
            session=str(e["session"]), direction=direction, entry_t=t_open,
            fill_adj=fill_adj, fill_raw=fill_raw, stop_dist=stop_dist,
            initial_stop_adj=initial_stop_adj, start_pos=start_pos,
            exit_pos=outcome.exit_pos, exit_t=exit_t,
            exit_price_adj=outcome.exit_price, exit_price_raw=exit_raw,
            exit_reason=E.REASONS[outcome.reason], trail_started=outcome.trail_started,
            n_rolls=n_rolls,
        ))
        blocked_until = exit_t

    return trades, n_ignored


def run_v0(df_1h: pd.DataFrame, *, scenario: str, trail_trigger: float = E.TRAIL_TRIGGER,
          confirm_window: int = 2, swing_LR: int = 2) -> tuple[list[Trade], dict]:
    """v0, one scenario, whole archive (caller slices to training/holdout by
    each trade's own session -- same convention as preflight.summarize).
    trail_trigger/confirm_window/swing_LR all default to the registered
    values; overridable only for the neighbour grid (REGISTERED sec 3 item
    8), which calls this with each of its 18 combinations."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    entries, counts = P.detect_v0(entry_adj, daily_adj, scenario=scenario,
                                  confirm_window=confirm_window, swing_LR=swing_LR)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = simulate(entries, hourly, bar_hours=bar_hours,
                                 session_flatten=session_flatten, trail_trigger=trail_trigger)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts


def run_c1(df_1h: pd.DataFrame, *, scenario: str) -> tuple[list[Trade], dict]:
    grids, _ = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    entries, counts = P.detect_c1(entry_adj, scenario=scenario)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = simulate(entries, hourly, bar_hours=bar_hours,
                                 session_flatten=session_flatten)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts


def run_v0_tl(df_1h: pd.DataFrame, *, scenario: str, trail_trigger: float = E.TRAIL_TRIGGER,
             confirm_window: int = 2, swing_LR: int = 2) -> tuple[list[Trade], dict]:
    """v0-TL, W15-0007 -- same shape as run_v0, with tl_variant.detect_v0_tl
    in place of preflight.detect_v0 (sec 2.6: 'E1-E4 plus' the trend-line
    gate; sec 2.6 also fixes the TL geometry to the 4-hour series for every
    scenario, so this always reads grids['4H'] for it, whatever scenario is
    asked for). Reported beside v0, never ranked (sec 2.6, sec 3)."""
    grids, daily_adj = P.prepare_grids(df_1h)
    hourly = grids["1H"]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    four_h_adj = grids["4H"]
    entries, counts = TLV.detect_v0_tl(entry_adj, daily_adj, four_h_adj, scenario=scenario,
                                       confirm_window=confirm_window, swing_LR=swing_LR)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = simulate(entries, hourly, bar_hours=bar_hours,
                                 session_flatten=session_flatten, trail_trigger=trail_trigger)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts
