#!/usr/bin/env python3
"""TL-bounce controls C1 (Donchian) and C2 (random entries). W15-0016.
REGISTERED_tl_bounce.md sec 3 "Controls":

    C1 Donchian on the entry chart: 20-bar breakout, 10-bar
       opposite-channel exit.
    C2 Random entries: 1,000 seeded draws (crc32 of draw number), matched
       to TL-bounce's trade count and long/short mix, entry bars drawn
       from bars where it was flat; initial stop at a distance drawn from
       TL-bounce's own stop distances; trailed by S2's swing rule without
       the line cap; no X1. p5/p50/p95 of net.

C3 (break entries, TL-v0's action-line rule) is NOT YET BUILT here, same
convention preflight.py already uses for it and for bounce-limit (both
"not_built": true in the report, never silently zero-filled) -- C3 is
"reported only" (sec 3), not one of sec 4's nine criteria, so it does not
gate the verdict; deferred rather than blocking C1/C2/the grid/the report.

WHY C1 NEEDS NO 1-HOUR PRECISION BUT C2 REUSES THE REAL EXIT WALK
----------------------------------------------------------------------
C1 has its own exit rule entirely (the opposite channel) with no stop/trail
of TL-bounce's own -- same reasoning as strategy.htf.controls' own C2
(Donchian) docstring: tested at the SAME granularity it is computed at, the
entry chart itself. C2's stop/trail IS TL-bounce's S1/S2 (sec 3: "trailed
by S2's swing rule"), so for a fair comparison it reuses exits.py's real
1-hour-precision walk exactly -- with the line term switched off (sup/res
forced NaN so exits.trail_candidate's min/max falls back to the swing term
alone, exactly "without the line cap") and x1_on=False (S1/S2 only, no
line-break exit to speak of once the line term is off).
"""
from __future__ import annotations

import dataclasses
import zlib

import numpy as np
import pandas as pd

from strategy.htf import costs as C
from strategy.htf.runner import _count_rolls
from strategy.tl_bounce import exits as EX
from strategy.tl_bounce.engine import Trade
from strategy.tl_bounce.signals import market_signals
from strategy.tl_bounce.spec import TRAIN_END, TRAIN_START

DONCHIAN_ENTRY_N = 20
DONCHIAN_EXIT_N = 10
C2_DRAWS = 1000


# ---------------------------------------------------------------------------
# C1 -- Donchian, entry-chart granularity, no stop/trail of its own
# ---------------------------------------------------------------------------

def detect_c1(entry_frame: pd.DataFrame) -> tuple[list[dict], dict]:
    n = len(entry_frame)
    close = entry_frame["close_adj"].to_numpy()
    entry_hi = entry_frame["high_adj"].shift(1).rolling(DONCHIAN_ENTRY_N).max().to_numpy()
    entry_lo = entry_frame["low_adj"].shift(1).rolling(DONCHIAN_ENTRY_N).min().to_numpy()

    counts = {"triggers": 0, "lapsed": 0, "entries": 0}
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
        counts["entries"] += 1
        entries.append({"fill_idx": fill_idx, "direction": direction,
                        "session": str(entry_frame["session"].iloc[fill_idx])})
    return entries, counts


def simulate_c1(entries: list[dict], entry_frame: pd.DataFrame) -> tuple[list[Trade], int]:
    n = len(entry_frame)
    open_ = entry_frame["open_adj"].to_numpy()
    high = entry_frame["high_adj"].to_numpy()
    low = entry_frame["low_adj"].to_numpy()
    close = entry_frame["close_adj"].to_numpy()
    offset = entry_frame["adj_offset"].to_numpy()
    exit_hi = pd.Series(high).shift(1).rolling(DONCHIAN_EXIT_N).max().to_numpy()
    exit_lo = pd.Series(low).shift(1).rolling(DONCHIAN_EXIT_N).min().to_numpy()
    t_open = entry_frame["t_open"]

    trades: list[Trade] = []
    n_ignored = 0
    blocked_until_idx = -1

    for e in entries:
        fill_idx = e["fill_idx"]
        if fill_idx <= blocked_until_idx:
            n_ignored += 1
            continue
        direction = e["direction"]
        is_long = direction == "long"

        exit_idx = exit_price_adj = reason = None
        for pos in range(fill_idx, n):
            level = exit_lo[pos] if is_long else exit_hi[pos]
            if not np.isnan(level):
                hit = (low[pos] <= level) if is_long else (high[pos] >= level)
                if hit:
                    px = (open_[pos] if ((is_long and open_[pos] <= level) or
                                        ((not is_long) and open_[pos] >= level)) else level)
                    exit_idx, exit_price_adj, reason = pos, float(px), "channel_exit"
                    break
        if exit_idx is None:
            exit_idx, exit_price_adj, reason = n - 1, float(close[n - 1]), "data_end"

        fill_adj = float(open_[fill_idx])
        fill_raw = fill_adj - float(offset[fill_idx])
        exit_raw = exit_price_adj - float(offset[exit_idx])
        n_rolls = _count_rolls(entry_frame, fill_idx, exit_idx)

        trades.append(Trade(
            session=e["session"], direction=direction, entry_t=t_open.iloc[fill_idx],
            fill_raw=fill_raw, stop_dist=float("nan"), exit_t=t_open.iloc[exit_idx],
            exit_price_raw=exit_raw, exit_reason=reason, trail_started=False,
            n_rolls=n_rolls, is_reentry=False,
        ))
        blocked_until_idx = exit_idx

    return trades, n_ignored


def run_c1(entry_frame: pd.DataFrame) -> tuple[list[Trade], dict]:
    entries, counts = detect_c1(entry_frame)
    trades, n_ignored = simulate_c1(entries, entry_frame)
    counts = dict(counts)
    counts["ignored_in_position"] = n_ignored
    counts["trades_taken"] = len(trades)
    return trades, counts


# ---------------------------------------------------------------------------
# C2 -- random entries, matched count/mix, S2's swing rule (no line, no X1)
# ---------------------------------------------------------------------------

def flat_pool(entry_frame: pd.DataFrame, bounce_trades: list[Trade], *, min_room: int = 1) -> np.ndarray:
    """Entry-chart positions not covered by any bounce trade's own
    [entry_t, exit_t) window (sec 3: 'entry bars drawn from bars where it
    was flat'), with at least min_room bars left to run, and RESTRICTED TO
    THE TRAINING WINDOW.

    WHY THE TRAINING-WINDOW RESTRICTION IS HERE, NOT LEFT TO THE CALLER
    ------------------------------------------------------------------------
    entry_frame is the FULL, un-truncated archive (prepare_grids never cuts
    to training -- G2's own established pattern, sim.py/preflight.py). C2's
    draws feed criterion 6 (sec 4), part of the TRAINING-SIDE pass/fail
    bar -- a draw landing on or after sec 6's holdout LOCK_FROM, or in the
    'seen, not evidence' window (sec 6), would leak exactly the data the
    holdout and the seen-window rule exist to keep out of that verdict.
    Found in independent review (2026-09-28): the un-filtered version drew
    from the whole archive and was invisible in every test because no
    synthetic fixture extended past TRAIN_END."""
    n = len(entry_frame)
    t = entry_frame["t_open"]
    covered = np.zeros(n, dtype=bool)
    for tr in bounce_trades:
        mask = ((t >= pd.Timestamp(tr.entry_t)) & (t < pd.Timestamp(tr.exit_t))).to_numpy()
        covered |= mask
    room_ok = np.arange(n) < (n - min_room)
    sessions = entry_frame["session"].astype(str).to_numpy()
    in_training = (sessions >= TRAIN_START) & (sessions <= TRAIN_END)
    return np.flatnonzero(~covered & room_ok & in_training)


def _draw_entries(entry_frame: pd.DataFrame, pool: np.ndarray, directions: list[str],
                  stop_dists: list[float], *, rng: np.random.Generator) -> list[dict]:
    t_open = entry_frame["t_open"]
    out = []
    for direction in directions:
        idx = int(rng.choice(pool))
        stop_dist = float(rng.choice(stop_dists))
        out.append({"idx": idx, "direction": direction, "stop_dist": stop_dist,
                   "session": str(entry_frame["session"].iloc[idx])})
    out.sort(key=lambda e: t_open.iloc[e["idx"]])
    return out


def _simulate_c2_draw(entries: list[dict], entry_frame: pd.DataFrame, hourly: pd.DataFrame,
                      bucket_idx: np.ndarray, swing_sig) -> list[Trade]:
    n = len(entry_frame)
    open_ = entry_frame["open_adj"].to_numpy()
    offset = entry_frame["adj_offset"].to_numpy()
    hourly_open = hourly["open_adj"].to_numpy()
    hourly_offset = hourly["adj_offset"].to_numpy()
    t_open = entry_frame["t_open"]
    hourly_t_open = hourly["t_open"]

    trades: list[Trade] = []
    blocked_until_idx = -1
    for e in entries:
        idx = e["idx"]
        if idx <= blocked_until_idx or idx >= n - 1:
            continue
        if not (TRAIN_START <= str(entry_frame["session"].iloc[idx])[:10] <= TRAIN_END):
            continue    # belt-and-suspenders: pool is already training-only
        direction, stop_dist = e["direction"], e["stop_dist"]
        fill_j = idx
        start_pos = EX.find_start_pos(hourly_t_open, t_open.iloc[fill_j])
        fill_adj_1h = float(hourly_open[start_pos])
        initial_stop_1h = (fill_adj_1h - stop_dist if direction == "long"
                          else fill_adj_1h + stop_dist)
        outcome = EX.simulate_trade_exit(hourly, bucket_idx, swing_sig, fill_j=fill_j,
                                         start_pos=start_pos, direction=direction,
                                         initial_stop=initial_stop_1h, x1_on=False)
        fill_raw = fill_adj_1h - float(hourly_offset[start_pos])
        exit_raw = outcome.exit_price - float(hourly_offset[outcome.exit_pos])
        n_rolls = _count_rolls(hourly, start_pos, outcome.exit_pos)
        trades.append(Trade(
            session=e["session"], direction=direction, entry_t=t_open.iloc[fill_j],
            fill_raw=fill_raw, stop_dist=stop_dist, exit_t=hourly_t_open.iloc[outcome.exit_pos],
            exit_price_raw=exit_raw, exit_reason=EX.REASONS[outcome.reason],
            trail_started=outcome.trail_started, n_rolls=n_rolls, is_reentry=False,
        ))
        blocked_until_idx = outcome.exit_bucket_j
    return trades


def run_c2(entry_frame: pd.DataFrame, hourly: pd.DataFrame, bounce_trades: list[Trade], *,
          symbol: str = "MCL", level: str = "mid", n_draws: int = C2_DRAWS,
          seed_prefix: str = "") -> dict:
    """1,000 seeded draws. Returns net-$ percentiles plus the raw per-draw
    array (for the report)."""
    sig = market_signals(entry_frame, e0=None)
    swing_sig = dataclasses.replace(sig, sup=np.full(sig.n, np.nan),
                                    res=np.full(sig.n, np.nan))
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_frame["t_open"])

    pool = flat_pool(entry_frame, bounce_trades)
    directions = [t.direction for t in bounce_trades]
    stop_dists = [t.stop_dist for t in bounce_trades if np.isfinite(t.stop_dist)]

    if not pool.size or not directions or not stop_dists:
        return {"n_draws": n_draws, "pool_size": int(pool.size),
               "n_trades_per_draw": len(directions), "p5": None, "p50": None, "p95": None,
               "nets": np.array([])}

    nets = np.full(n_draws, np.nan)
    for d in range(n_draws):
        seed = zlib.crc32(f"{seed_prefix}{d}".encode()) & 0xFFFFFFFF
        rng = np.random.default_rng(seed)
        entries = _draw_entries(entry_frame, pool, directions, stop_dists, rng=rng)
        trades = _simulate_c2_draw(entries, entry_frame, hourly, bucket_idx, swing_sig)
        nets[d] = sum(t.net_pnl(symbol, level) for t in trades)

    return {
        "n_draws": n_draws, "pool_size": int(pool.size), "n_trades_per_draw": len(directions),
        "p5": float(np.nanpercentile(nets, 5)), "p50": float(np.nanpercentile(nets, 50)),
        "p95": float(np.nanpercentile(nets, 95)), "nets": nets,
    }
