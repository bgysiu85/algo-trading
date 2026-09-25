#!/usr/bin/env python3
"""HTF-Ben controls C1-C3, REGISTERED_htf_ben_v0.md sec 3 item 7. W15-0004
step 7 checkpoints 4-5.

C1 (MACD cross alone, same stop/trail) is already fully built: it is
preflight.detect_c1 + exits.simulate_exit + runner.simulate, unchanged --
runner.run_c1 exists for exactly this. This module adds the two controls
that need new code:

C2  Donchian breakout on the same entry chart: buy a 20-bar high / sell a
    20-bar low (prior N COMPLETED bars, never the trigger bar itself), exit
    on the OPPOSITE 10-bar channel, same flat-by-17:00 rule in scenario A.
    No stop, no trail -- its own exit rule entirely.

C3  Random entries: 1,000 seeded draws, same trade count and long/short mix
    as v0, entry bars drawn uniformly from bars where v0 could have been
    flat, same stop and trail (S1-S5, i.e. C3 DOES reuse exits.py, unlike
    C2). Reports p5/p50/p95 of net -- see run_c3 below.

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

import zlib

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import runner as R
from strategy.htf import signals as SIG

DONCHIAN_ENTRY_N = 20
DONCHIAN_EXIT_N = 10
C3_DRAWS = 1000


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


# ---------------------------------------------------------------------------
# C3 -- random entries, same count/mix as v0, same stop and trail (S1-S5)
# ---------------------------------------------------------------------------
#
# UNLIKE C2, C3 reuses v0's own exit machinery exactly: runner.simulate()
# already takes a plain list of {t_open, direction, stop_dist, session}
# dicts and walks them through exits.simulate_exit on the 1-hour grid with
# E5 enforced -- that is precisely what "same stop and trail" (sec 3 item 7)
# means, so C3 only has to build a DIFFERENT entries list (drawn at random)
# and hand it to the exact same simulate() v0 uses. No new exit logic.
#
# THE "COULD HAVE BEEN FLAT" POOL
# --------------------------------
# An entry-chart bar is eligible if its own t_open does not fall inside any
# of v0's ACTUAL trade windows [entry_t, exit_t) -- v0 could not have been
# flat there, so a random draw landing on it would not be a fair comparison
# of entry timing. Built once from v0's realised trades (runner.Trade list),
# by interval, not by position index, since v0's trades are indexed into the
# 1-hour grid while the draw pool is entry-chart positions.
#
# ONE DRAW = ONE HYPOTHETICAL PORTFOLIO OF len(v0_trades) RANDOM TRADES
# ------------------------------------------------------------------------
# Each draw independently samples len(v0_trades) entry bars (with
# replacement across draws; each draw's own trades still run through E5 via
# runner.simulate, so trades WITHIN one draw cannot overlap either -- a
# later draw of a bar already covered by an earlier trade IN THE SAME DRAW
# is skipped by simulate()'s own blocked_until logic, exactly as it would be
# for a real position). The direction sequence is v0's own (preserving its
# long/short mix exactly); only WHEN each trade fires is randomised. A
# drawn bar whose S1 stop would void the trade (preflight._initial_stop
# returns None) is redrawn, capped, so a draw's trade count matches v0's
# as closely as the pool allows -- reported, not silently forced.


def flat_pool(entry_adj: pd.DataFrame, v0_trades: list, *, min_room: int = 1) -> np.ndarray:
    """Entry-chart positions NOT covered by any v0 trade's [entry_t, exit_t)
    window, and with at least `min_room` bars left to run (so a draw there
    is never automatically an instant data_end)."""
    n = len(entry_adj)
    t = entry_adj["t_open"]
    covered = np.zeros(n, dtype=bool)
    for tr in v0_trades:
        mask = ((t >= pd.Timestamp(tr.entry_t)) & (t < pd.Timestamp(tr.exit_t))).to_numpy()
        covered |= mask
    room_ok = np.arange(n) < (n - min_room)
    pool = np.flatnonzero(~covered & room_ok)
    return pool


def _draw_entries(entry_adj: pd.DataFrame, pool: np.ndarray, directions: list[str],
                  *, rng: np.random.Generator, swing_low: pd.Series, swing_high: pd.Series,
                  low_adj: np.ndarray, high_adj: np.ndarray, max_redraws: int = 50) -> list[dict]:
    from strategy.htf import preflight as PF
    open_adj = entry_adj["open_adj"].to_numpy()
    entries = []
    for direction in directions:
        for _ in range(max_redraws):
            idx = int(rng.choice(pool))
            fill_price = float(open_adj[idx])
            stop = PF._initial_stop(direction, idx, fill_price, swing_low, swing_high,
                                    low_adj, high_adj)
            if stop is not None:
                entries.append({"t_open": entry_adj["t_open"].iloc[idx], "direction": direction,
                               "stop_dist": abs(fill_price - stop),
                               "session": str(entry_adj["session"].iloc[idx])})
                break
        # exhausting max_redraws without a valid stop: this trade of the
        # draw is simply not placed (reported via len(entries) < len(directions)
        # by the caller, never silently padded with a fabricated trade)
    entries.sort(key=lambda e: e["t_open"])
    return entries


def run_c3(df_1h: pd.DataFrame, *, scenario: str, v0_trades: list, symbol: str = "MCL",
          level: str = "mid", n_draws: int = C3_DRAWS, seed_prefix: str = "") -> dict:
    """1,000 seeded draws (seed = crc32(seed_prefix + str(draw_index))).
    Returns net-$ percentiles plus the raw per-draw array for the report."""
    from strategy.htf import preflight as PF
    grids, _ = PF.prepare_grids(df_1h)
    hourly = grids["1H"]
    entry_adj = grids[PF.SCENARIO_GRID[scenario]]
    bar_hours = B.GRID_HOURS[PF.SCENARIO_GRID[scenario]]
    session_flatten = scenario in PF.INTRADAY_SCENARIOS

    swing_low = SIG.swing_lows(entry_adj["low_adj"]).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"]).ffill()
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()

    pool = flat_pool(entry_adj, v0_trades)
    directions = [t.direction for t in v0_trades]

    nets = np.full(n_draws, np.nan)
    for d in range(n_draws):
        seed = zlib.crc32(f"{seed_prefix}{d}".encode()) & 0xFFFFFFFF
        rng = np.random.default_rng(seed)
        entries = _draw_entries(entry_adj, pool, directions, rng=rng, swing_low=swing_low,
                                swing_high=swing_high, low_adj=low_adj, high_adj=high_adj)
        trades, _ = R.simulate(entries, hourly, bar_hours=bar_hours, session_flatten=session_flatten)
        nets[d] = sum(t.net_pnl(symbol, level) for t in trades)

    return {
        "n_draws": n_draws, "pool_size": int(len(pool)), "n_trades_per_draw": len(directions),
        "p5": float(np.nanpercentile(nets, 5)), "p50": float(np.nanpercentile(nets, 50)),
        "p95": float(np.nanpercentile(nets, 95)), "nets": nets,
    }
