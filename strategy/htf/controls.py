#!/usr/bin/env python3
"""HTF-Ben controls C1-C3, REGISTERED_htf_ben_v0.md sec 3 item 7. W15-0004
step 7 checkpoint 4.

C1 (MACD cross alone, same stop/trail) is already fully built: it is
preflight.detect_c1 + exits.simulate_exit + runner.simulate, unchanged --
runner.run_c1 exists for exactly this. This module adds the two controls
that do NOT reuse the S1-S5 stop/trail:

C2  Donchian breakout on the same entry chart: buy a 20-bar high / sell a
    20-bar low (prior N COMPLETED bars, never the trigger bar itself), exit
    on the OPPOSITE 10-bar channel, same flat-by-17:00 rule in scenario A.
    No stop, no trail -- its own exit rule entirely.

C3  Random entries: 1,000 seeded draws, same trade count and long/short mix
    as v0, entry bars drawn uniformly from bars where v0 could have been
    flat, same stop and trail (S1-S5, i.e. C3 DOES reuse exits.py, unlike
    C2). Reports p5/p50/p95 of net -- built in the next checkpoint.

WHY C2 NEVER TOUCHES THE 1-HOUR GRID (unlike v0/C1 via runner.py)
----------------------------------------------------------------------
v0/C1 need the 1-hour grid because S3 (trail level, entry-chart cadence)
and S4 (stop test, hourly cadence) are two different granularities of the
same rule (exits.py's own docstring). C2 has no such split: REGISTERED sec
3 item 7 states the channel exit with no hourly-precision requirement, so
it is tested at the SAME granularity it is computed at -- the entry chart
itself. bars.back_adjust attaches 'adj_offset' and 'held_id' to whatever
frame it is given (its own docstring: "at whatever granularity it's
given"), so entry_adj (2H/4H, already back-adjusted by
preflight.prepare_grids) already carries everything needed for the
raw-conversion identity raw = adj - adj_offset at its OWN rows, with no
cross-grid t_open lookup and no risk of the two grids' independently
accumulated offsets disagreeing around a roll.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import runner as R
from strategy.htf import signals as SIG

DONCHIAN_ENTRY_N = 20
DONCHIAN_EXIT_N = 10


def detect_c2(entry_adj: pd.DataFrame, *, scenario: str, bar_hours: int) -> tuple[list[dict], dict]:
    """Every Donchian breakout trigger, time-ordered, E5-UNAWARE (mirrors
    preflight.detect_v0/detect_c1's own convention -- E5 is applied by
    simulate_c2 below, same split as runner.simulate for v0/C1)."""
    n = len(entry_adj)
    close = entry_adj["close_adj"].to_numpy()
    entry_hi = entry_adj["high_adj"].shift(1).rolling(DONCHIAN_ENTRY_N).max().to_numpy()
    entry_lo = entry_adj["low_adj"].shift(1).rolling(DONCHIAN_ENTRY_N).min().to_numpy()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    intraday = scenario in ("A-2H", "A-1H", "A-4H")

    counts = {"triggers": 0, "lapsed": 0, "blocked_end_of_session": 0, "entries": 0}
    entries = []
    for i in range(n):
        if np.isnan(entry_hi[i]) or np.isnan(entry_lo[i]):
            continue
        if close[i] > entry_hi[i]:
            direction = "long"
        elif close[i] < entry_lo[i]:
            direction = "short"
        else:
            continue
        counts["triggers"] += 1
        fill_idx = i + 1
        if fill_idx >= n:
            counts["lapsed"] += 1
            continue
        if intraday and bool(last_bar[fill_idx]):
            counts["blocked_end_of_session"] += 1
            continue
        counts["entries"] += 1
        entries.append({"fill_idx": fill_idx, "direction": direction,
                        "session": str(entry_adj["session"].iloc[fill_idx])})
    return entries, counts


def simulate_c2(entries: list[dict], entry_adj: pd.DataFrame, *, bar_hours: int,
                session_flatten: bool) -> tuple[list["R.Trade"], int]:
    """E5-enforced walk over detect_c2's candidates, entirely on entry_adj
    (see module docstring for why no 1H grid is needed here). Returns
    (taken_trades, n_ignored_in_position), same shape as runner.simulate."""
    n = len(entry_adj)
    open_ = entry_adj["open_adj"].to_numpy()
    high = entry_adj["high_adj"].to_numpy()
    low = entry_adj["low_adj"].to_numpy()
    close = entry_adj["close_adj"].to_numpy()
    offset = entry_adj["adj_offset"].to_numpy()
    exit_hi = pd.Series(high).shift(1).rolling(DONCHIAN_EXIT_N).max().to_numpy()
    exit_lo = pd.Series(low).shift(1).rolling(DONCHIAN_EXIT_N).min().to_numpy()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    t_open = entry_adj["t_open"]

    trades: list[R.Trade] = []
    n_ignored = 0
    blocked_until_idx = -1

    for e in entries:
        fill_idx = e["fill_idx"]
        if fill_idx <= blocked_until_idx:
            n_ignored += 1
            continue
        direction = e["direction"]
        is_long = direction == "long"

        exit_idx = None
        exit_price_adj = None
        reason = None
        for pos in range(fill_idx, n):
            level = exit_lo[pos] if is_long else exit_hi[pos]
            if not np.isnan(level):
                hit = (low[pos] <= level) if is_long else (high[pos] >= level)
                if hit:
                    if is_long:
                        px = open_[pos] if open_[pos] <= level else level
                    else:
                        px = open_[pos] if open_[pos] >= level else level
                    exit_idx, exit_price_adj, reason = pos, float(px), "channel_exit"
                    break
            if session_flatten and bool(last_bar[pos]):
                exit_idx, exit_price_adj, reason = pos, float(close[pos]), "session_flat"
                break
        if exit_idx is None:
            exit_idx, exit_price_adj, reason = n - 1, float(close[n - 1]), "data_end"

        fill_adj = float(open_[fill_idx])
        fill_raw = fill_adj - float(offset[fill_idx])
        exit_raw = exit_price_adj - float(offset[exit_idx])
        n_rolls = R._count_rolls(entry_adj, fill_idx, exit_idx)

        trades.append(R.Trade(
            session=e["session"], direction=direction, entry_t=t_open.iloc[fill_idx],
            fill_adj=fill_adj, fill_raw=fill_raw, stop_dist=float("nan"),
            initial_stop_adj=float("nan"), start_pos=fill_idx, exit_pos=exit_idx,
            exit_t=t_open.iloc[exit_idx], exit_price_adj=exit_price_adj,
            exit_price_raw=exit_raw, exit_reason=reason, trail_started=False,
            n_rolls=n_rolls,
        ))
        blocked_until_idx = exit_idx

    return trades, n_ignored


def run_c2(df_1h: pd.DataFrame, *, scenario: str):
    from strategy.htf import preflight as P
    grids, _ = P.prepare_grids(df_1h)
    entry_adj = grids[P.SCENARIO_GRID[scenario]]
    bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
    entries, counts = detect_c2(entry_adj, scenario=scenario, bar_hours=bar_hours)
    session_flatten = scenario in P.INTRADAY_SCENARIOS
    trades, n_ignored = simulate_c2(entries, entry_adj, bar_hours=bar_hours,
                                    session_flatten=session_flatten)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts
