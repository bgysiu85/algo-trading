#!/usr/bin/env python3
"""TL-bounce full backtest engine: E1-E4 entries (one at a time, for real,
against each taken trade's ACTUAL 1-hour-precise exit time), S1-S2/X1 exits
via exits.py, raw-series $ booking via strategy.htf.costs, roll legs counted
via strategy.htf.runner._count_rolls. W15-0016. REGISTERED_tl_bounce.md sec
2.1-2.5, 3.

WHY THIS DOES NOT REUSE sim.py's WALK
-------------------------------------
sim.py (G2, W15-0015) tests the stop against the ENTRY-CHART bar's own
low/high -- a documented approximation, "consequential for booked $ ...
but not, on a first-order basis, for G2's own counts" (its own docstring).
Booking real dollars IS what this module is for, so it cannot use that
approximation: a fill's exit is only known for real by walking the 1-hour
grid (exits.simulate_trade_exit). This module reimplements E1-E4's touch/
fill/void detection (identical logic to sim.py's steps 1-2, 5-6) but hands
each fill straight to the 1-hour exit walk instead of continuing its own
bar-by-bar loop, then resumes scanning for the next touch strictly after
the bar the exit belongs to (sec 2.2 E4: "the exit bar itself cannot be a
touch bar").

BOUNCE-ONCE IS STILL "NO RE-ENTRY AT ALL", NOT "PER LINE"
-----------------------------------------------------------
Same documented, narrower-than-registered approximation as sim.py (its own
docstring): common/tl_v0_lines.py tracks only one active line per kind, with
no line-identity, so "one entry per line" cannot yet be told apart from "no
re-entry at all" once any entry has been taken. Carried forward unchanged
here rather than fixed by editing that shared module unreviewed; flagged
again in report.py's caveats. Does not affect "bounce" (the only candidate
that can spend the holdout or clear sec 4's bar) or any other variant.

WHY THE HOURLY FILL/STOP ARE RE-ANCHORED, NOT USED AS-IS FROM entry_frame
----------------------------------------------------------------------------
Same reasoning as strategy.htf.runner.simulate's own re-anchoring (its
docstring): entry_frame's own back-adjustment and the hourly grid's are
accumulated independently and only guaranteed to agree away from a roll.
The STOP DISTANCE (not the absolute level) computed from entry_frame at the
touch bar is preserved; the anchor point becomes the hourly grid's own
open at the fill hour.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf import costs as C
from strategy.htf.runner import _count_rolls
from strategy.tl_bounce import exits as EX
from strategy.tl_bounce import lines as L
from strategy.tl_bounce.signals import Signals, market_signals
from strategy.tl_bounce.spec import STOP_BUF

TICK = 0.01   # sec 2.3 S1's "1 tick"


@dataclass
class Trade:
    session: str
    direction: str
    entry_t: pd.Timestamp
    fill_raw: float
    stop_dist: float
    exit_t: pd.Timestamp
    exit_price_raw: float
    exit_reason: str
    trail_started: bool
    n_rolls: int
    is_reentry: bool

    def gross_pnl(self, symbol: str, qty: int = 1) -> float:
        return C.pnl_dollars(symbol, self.fill_raw, self.exit_price_raw, self.direction, qty)

    def cost(self, symbol: str, level: str, qty: int = 1) -> float:
        return C.round_trip_cost(symbol, level, n_round_trips=1 + self.n_rolls, qty=qty)

    def net_pnl(self, symbol: str, level: str, qty: int = 1) -> float:
        return self.gross_pnl(symbol, qty) - self.cost(symbol, level, qty)


@dataclass
class Counts:
    touch_bars: int = 0
    touch_long: int = 0
    touch_short: int = 0
    held: int = 0
    e0_blocked: int = 0
    ignored_in_position: int = 0
    voided: int = 0
    entries: int = 0
    re_entries: int = 0
    exit_stop: int = 0
    exit_x1: int = 0
    exit_data_end: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _s1_long(sup_j, atr_j, lo_j):
    return min(sup_j - STOP_BUF * atr_j, lo_j - TICK)


def _s1_short(res_j, atr_j, hi_j):
    return max(res_j + STOP_BUF * atr_j, hi_j + TICK)


def simulate_market(entry_frame: pd.DataFrame, higher_frame: pd.DataFrame | None,
                    higher_bar_hours: int | None, hourly: pd.DataFrame, *,
                    e0_on: bool, x1_on: bool, allow_reentry: bool,
                    sig: Signals | None = None
                    ) -> tuple[list[Trade], Counts]:
    """entry_frame/higher_frame: back-adjusted grids (strategy.htf.bars,
    same convention as strategy.tl_bounce.preflight.prepare_grids). hourly:
    the back-adjusted 1H grid built from the SAME df_1h. Returns
    (taken_trades, counts) -- taken_trades carry raw-series prices, ready
    for strategy.htf.costs/book.

    `sig`: a pre-built Signals object, for a caller that needs non-default
    line parameters (grid.py's 27-cell neighbour sweep, W15-0016 sec 3,
    which varies touch buffer / close-through buffer / pivot R -- none of
    which signals.market_signals' own default call exposes). Left None for
    every ordinary caller, which builds it here exactly as before."""
    if sig is None:
        e0 = (L.e0_filter(entry_frame, higher_frame, higher_bar_hours)
             if (e0_on and higher_frame is not None) else None)
        sig = market_signals(entry_frame, e0=e0)
    n = sig.n
    o, lo_arr, hi_arr = sig.o, sig.l, sig.h
    tl_arr, ts_arr = sig.touch_long, sig.touch_short

    entry_t_open = entry_frame["t_open"]
    offset = entry_frame["adj_offset"].to_numpy()
    sessions = entry_frame["session"].astype(str).to_numpy()
    hourly_open = hourly["open_adj"].to_numpy()
    hourly_offset = hourly["adj_offset"].to_numpy()
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t_open)
    hourly_t_open = hourly["t_open"]

    trades: list[Trade] = []
    k = Counts()
    # sec 3's touch counts are unconditional, every bar, matching sim.py's
    # own per-bar accounting -- computed once, vectorised, rather than
    # incrementally inside the walk below. Found in independent review
    # (2026-09-28): the walk's j-jump on a taken trade (E4: "the exit bar
    # itself cannot be a touch bar") skips revisiting bars fill_j..
    # exit_bucket_j, which would otherwise undercount touch_bars for every
    # bar the outer loop never lands on again.
    k.touch_bars = int(np.sum(tl_arr | ts_arr))
    k.touch_long = int(np.sum(tl_arr))
    k.touch_short = int(np.sum(ts_arr))

    has_entered = False
    j = 0

    while j < n:
        last_bar = (j == n - 1)
        tl, ts = bool(tl_arr[j]), bool(ts_arr[j])

        if last_bar:
            break

        e0_dir = None if sig.e0 is None else sig.e0[j]
        direction, s0 = None, None
        if tl and not np.isnan(sig.sup[j]) and (allow_reentry or not has_entered):
            if e0_dir is None or e0_dir == 1:
                direction, s0 = "long", _s1_long(sig.sup[j], sig.atr[j], lo_arr[j])
            elif e0_dir is not None:
                k.e0_blocked += 1
        if direction is None and ts and not np.isnan(sig.res[j]) and (allow_reentry or not has_entered):
            if e0_dir is None or e0_dir == -1:
                direction, s0 = "short", _s1_short(sig.res[j], sig.atr[j], hi_arr[j])
            elif e0_dir is not None:
                k.e0_blocked += 1

        if direction is None:
            j += 1
            continue

        k.held += 1
        fill_j = j + 1
        o_fill_entry_chart = o[fill_j]
        voided = ((direction == "long" and o_fill_entry_chart <= s0) or
                 (direction == "short" and o_fill_entry_chart >= s0))
        if voided:
            k.voided += 1
            j += 1
            continue

        is_re = has_entered
        has_entered = True
        k.entries += 1
        if is_re:
            k.re_entries += 1

        stop_dist = abs(o_fill_entry_chart - s0)
        start_pos = EX.find_start_pos(hourly_t_open, entry_t_open.iloc[fill_j])
        fill_adj_1h = float(hourly_open[start_pos])
        initial_stop_1h = (fill_adj_1h - stop_dist) if direction == "long" else (fill_adj_1h + stop_dist)

        outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=fill_j,
                                         start_pos=start_pos, direction=direction,
                                         initial_stop=initial_stop_1h, x1_on=x1_on)

        if outcome.reason in (EX.R_INITIAL_STOP, EX.R_TRAILED_STOP):
            k.exit_stop += 1
        elif outcome.reason == EX.R_X1:
            k.exit_x1 += 1
        else:
            k.exit_data_end += 1

        exit_bucket_j = outcome.exit_bucket_j
        if exit_bucket_j > fill_j:
            ign_mask = tl_arr[fill_j:exit_bucket_j] | ts_arr[fill_j:exit_bucket_j]
            k.ignored_in_position += int(np.sum(ign_mask))

        fill_raw = fill_adj_1h - float(hourly_offset[start_pos])
        exit_raw = outcome.exit_price - float(hourly_offset[outcome.exit_pos])
        n_rolls = _count_rolls(hourly, start_pos, outcome.exit_pos)

        trades.append(Trade(
            session=sessions[fill_j], direction=direction, entry_t=entry_t_open.iloc[fill_j],
            fill_raw=fill_raw, stop_dist=stop_dist,
            exit_t=hourly_t_open.iloc[outcome.exit_pos], exit_price_raw=exit_raw,
            exit_reason=EX.REASONS[outcome.reason], trail_started=outcome.trail_started,
            n_rolls=n_rolls, is_reentry=is_re,
        ))

        j = max(exit_bucket_j + 1, fill_j + 1)

    return trades, k
