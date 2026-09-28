#!/usr/bin/env python3
"""W16 session-baselines controls: C-B1 (random entry), C-O2 (intraday
complement), C-O3 (random window), C-B3 (random flips).
REGISTERED_w16_session_baselines.md sec 7.1. Board W16-0003 subitem 3.

SEEDING: every draw's seed is `zlib.crc32(str(draw_number).encode())` (sec
7.1: "1,000 seeded draws each, seed = zlib.crc32 of draw number"), so draw 0
of C-B1 on ES and draw 0 of C-B1 on NQ use the SAME seed on purpose --
reproducible across a re-run, and across markets, is the point (comparing
"how ES's random-entry control behaves under draw 7" to "how NQ's does" is
only a fair comparison if draw 7 means the same seed both times).
"""
from __future__ import annotations

import zlib
from datetime import time as dtime

import numpy as np
import pandas as pd

from strategy.w16.signals import walk_stop_target_time_exit
from strategy.w16.sessions import orb_time_exit

N_DRAWS = 1000


def draw_rng(draw_idx: int) -> np.random.Generator:
    seed = zlib.crc32(str(draw_idx).encode())
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------
# C-B1 -- random entry (matched to B1's real trades)
# ---------------------------------------------------------------------

def c_b1_draw(real_trades: list[dict], session_bars: dict[str, pd.DataFrame],
             draw_idx: int, *, naive_cache: dict | None = None) -> list[dict]:
    """One draw: for each real (non-voided) B1 trade, a control trade on
    the SAME day, SAME long/short mix, SAME stop distance in points and
    SAME 2:1 target, but entered at a uniformly random bar start in
    10:01..15:29 rather than at the real trigger (sec 7.1's C-B1 row).
    `session_bars[date]` must be that date's RTH-windowed, sorted bars.
    `naive_cache` (optional, see `naive_time_cache`): {date: naive_index}
    precomputed once by the caller and shared across all 1,000 draws."""
    rng = draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        bars = session_bars[date_str]
        if naive_cache is not None:
            naive = naive_cache[date_str]
        else:
            from strategy.w16.readback import local_naive_et
            naive = local_naive_et(bars.index)
        t = naive.time
        window_mask = (t >= dtime(10, 1)) & (t <= dtime(15, 29))
        candidates = np.where(window_mask)[0]
        candidates = candidates[candidates < len(bars) - 1]   # needs a next bar to fill on
        if len(candidates) == 0:
            continue
        pos = int(rng.integers(0, len(candidates)))
        fill_idx = int(candidates[pos])
        fill_price = float(bars["open"].iloc[fill_idx])
        direction = rt["direction"]
        stop_dist = rt["stop_dist"]
        stop = fill_price - stop_dist if direction == "long" else fill_price + stop_dist
        target = (fill_price + 2.0 * stop_dist if direction == "long"
                  else fill_price - 2.0 * stop_dist)
        exit_t = orb_time_exit(date_str)
        exit_price, exit_reason = walk_stop_target_time_exit(
            bars, naive, fill_idx, direction, stop, target, exit_t)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-B1",
                   "draw": draw_idx, "direction": direction, "voided": False,
                   "fill_price": fill_price, "stop": stop, "target": target,
                   "stop_dist": stop_dist, "exit_price": exit_price,
                   "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


# ---------------------------------------------------------------------
# C-O2 -- intraday complement (deterministic, sec 3.2's own reported variant)
# ---------------------------------------------------------------------

def c_o2_trades(real_b2_trades: list[dict], session_bars: dict[str, pd.DataFrame]
                ) -> list[dict]:
    """Long 09:30 open -> 16:00 (or early-close) close, same days B2 traded
    (its non-voided ones), same costs. Not randomized -- sec 7.1 gives this
    one exact rule, not a draw."""
    out = []
    for rt in real_b2_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        bars = session_bars[date_str].sort_index()
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-O2",
                   "direction": "long", "voided": False,
                   "entry_price": float(bars["open"].iloc[0]),
                   "exit_price": float(bars["close"].iloc[-1]),
                   "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop"})
    return out


# ---------------------------------------------------------------------
# C-O3 -- random window (matched to B2's real hold lengths)
# ---------------------------------------------------------------------

def c_o3_draw(real_b2_trades: list[dict], full_index: pd.DatetimeIndex,
             price_at: "pd.Series", draw_idx: int, *,
             candidates_cache: dict | None = None) -> list[dict]:
    """One draw: for each real (non-voided) B2 trade, a long hold of
    EXACTLY the same wall-clock length, starting at a uniformly random
    minute of `full_index` such that both the start and the (start +
    length) minute have a bar (sec 7.1's C-O3 row -- holds may span the
    daily pause, as B2's own do). `full_index` is every 1-minute bar
    timestamp across the WHOLE training archive for one market (not just
    RTH -- a random start can land anywhere), sorted, tz-aware; `price_at`
    is a pd.Series of close price indexed the same way, used for both the
    start and end price (a random start is not guaranteed to land on a
    session's own open, so the OPEN/CLOSE distinction B2 itself uses does
    not apply here -- the close of whichever bar is drawn is used at both
    ends, which is what "starting at a uniformly random minute" means when
    the minute need not be a session boundary).
    `candidates_cache` (optional, see `o3_candidates_cache`): {length:
    (candidates, end_positions)} precomputed once by the caller and shared
    across all 1,000 draws -- valid start/end positions depend only on
    `full_index` and `length`, not on draw_idx, so recomputing them with an
    O(len(full_index)) array op per trade per draw (the original behaviour
    when this is omitted) does not scale to a multi-year archive: measured
    at ~116h for one market's 1,000 draws at real archive scale before
    this cache existed."""
    rng = draw_rng(draw_idx)
    idx_arr = full_index.values
    out = []
    for rt in real_b2_trades:
        if rt.get("voided"):
            continue
        entry_ts = pd.Timestamp(rt["entry_time"]) if "entry_time" in rt else None
        length = rt.get("hold_length")
        if length is None:
            continue
        length = pd.Timedelta(length)
        if candidates_cache is not None and length in candidates_cache:
            candidates, end_positions = candidates_cache[length]
        else:
            end_positions = np.searchsorted(idx_arr, idx_arr + np.timedelta64(length))
            valid = (end_positions < len(idx_arr)) & (idx_arr[np.clip(end_positions, 0, len(idx_arr) - 1)]
                                                      == (idx_arr + np.timedelta64(length)))
            candidates = np.where(valid)[0]
        if len(candidates) == 0:
            continue
        pos = int(rng.integers(0, len(candidates)))
        start_i = int(candidates[pos])
        end_i = int(end_positions[start_i])
        start_ts, end_ts = full_index[start_i], full_index[end_i]
        out.append({"market": rt["market"], "baseline": "C-O3", "draw": draw_idx,
                   "direction": "long", "voided": False,
                   "entry_time": str(start_ts), "exit_time": str(end_ts),
                   "entry_price": float(price_at.loc[start_ts]),
                   "exit_price": float(price_at.loc[end_ts]),
                   "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop"})
    return out


# ---------------------------------------------------------------------
# C-B3 -- random flips (matched to B3's real flip counts, per day)
# ---------------------------------------------------------------------

def c_b3_draw(real_flip_counts: dict[str, int], session_bars: dict[str, pd.DataFrame],
             draw_idx: int, *, naive_cache: dict | None = None) -> list[dict]:
    """One draw: for each day B3 had `n` real flips, `n` position changes
    at uniformly random bar closes 09:31..15:57, first side random, flat
    at the session's own close (sec 7.1's C-B3 row).
    `naive_cache` (optional, see `naive_time_cache`, built with `sort=True`
    to match the `.sort_index()` below): {date: naive_index} precomputed
    once by the caller and shared across all 1,000 draws."""
    rng = draw_rng(draw_idx)
    out = []
    for date_str, n_flips in real_flip_counts.items():
        if n_flips <= 0:
            continue
        bars = session_bars[date_str].sort_index()
        if naive_cache is not None:
            naive = naive_cache[date_str]
        else:
            from strategy.w16.readback import local_naive_et
            naive = local_naive_et(bars.index)
        t = naive.time
        window_mask = (t >= dtime(9, 31)) & (t <= dtime(15, 57))
        candidates = np.where(window_mask)[0]
        candidates = candidates[candidates < len(bars) - 1]
        if len(candidates) < n_flips:
            continue
        chosen = np.sort(rng.choice(candidates, size=n_flips, replace=False))
        position = "long" if rng.integers(0, 2) == 0 else "short"
        legs = []
        for signal_pos in chosen:
            fill_idx = int(signal_pos) + 1
            fill_price = float(bars["open"].iloc[fill_idx])
            fill_time = str(bars.index[fill_idx])
            legs.append({"date": date_str, "market": None, "baseline": "C-B3",
                        "draw": draw_idx, "leg": "exit", "direction": position,
                        "price": fill_price, "time": fill_time,
                        "fill_kind": "market_or_stop", "reason": "flip"})
            position = "short" if position == "long" else "long"
            legs.append({"date": date_str, "market": None, "baseline": "C-B3",
                        "draw": draw_idx, "leg": "entry", "direction": position,
                        "price": fill_price, "time": fill_time,
                        "fill_kind": "market_or_stop", "reason": "flip"})
        legs = legs[1:]     # the very first "exit" has no prior position; drop it
        legs.append({"date": date_str, "market": None, "baseline": "C-B3",
                    "draw": draw_idx, "leg": "exit", "direction": position,
                    "price": float(bars["close"].iloc[-1]), "time": str(bars.index[-1]),
                    "fill_kind": "market_or_stop", "reason": "flat_at_close"})
        out.extend(legs)
    return out

# ---------------------------------------------------------------------
# performance caches -- build once, share across all 1,000 draws
# ---------------------------------------------------------------------

def naive_time_cache(session_bars: dict[str, pd.DataFrame], dates, *,
                     sort: bool = False) -> dict:
    """{date: naive_index}, for `c_b1_draw`/`c_b3_draw`'s `naive_cache`.
    `sort=True` matches c_b3_draw's own `.sort_index()`; `sort=False`
    (default) matches c_b1_draw, which trusts session_bars is already
    sorted. Computing this once per date instead of once per trade per
    draw is what turns an O(n_trades * n_draws) tz conversion into
    O(n_dates)."""
    from strategy.w16.readback import local_naive_et
    cache = {}
    for date_str in dates:
        if date_str not in session_bars:
            continue
        bars = session_bars[date_str]
        idx = bars.sort_index().index if sort else bars.index
        cache[date_str] = local_naive_et(idx)
    return cache


def o3_candidates_cache(real_b2_trades: list[dict], full_index: pd.DatetimeIndex) -> dict:
    """{length: (candidates, end_positions)}, for `c_o3_draw`'s
    `candidates_cache` -- one entry per unique hold length across
    `real_b2_trades`, computed once (not once per trade per draw). See
    `c_o3_draw`'s docstring for why this matters at archive scale."""
    idx_arr = full_index.values
    cache: dict = {}
    for rt in real_b2_trades:
        if rt.get("voided"):
            continue
        length = rt.get("hold_length")
        if length is None:
            continue
        length = pd.Timedelta(length)
        if length in cache:
            continue
        end_positions = np.searchsorted(idx_arr, idx_arr + np.timedelta64(length))
        valid = (end_positions < len(idx_arr)) & (idx_arr[np.clip(end_positions, 0, len(idx_arr) - 1)]
                                                  == (idx_arr + np.timedelta64(length)))
        candidates = np.where(valid)[0]
        cache[length] = (candidates, end_positions)
    return cache

