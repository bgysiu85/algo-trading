#!/usr/bin/env python3
"""W16 session baselines: B1 (opening-range breakout), B2 (overnight hold),
B3 (VWAP flip) -- one session (or session pair) at a time, from RTH 1-minute
bars. REGISTERED_w16_session_baselines.md sec 3 (the rules) and sec 6.3
(gate G4, look-ahead guards). Board W16-0003 subitem 3.

WHAT A "TRADE RECORD" IS, AND WHY THIS FILE COMPUTES NO DOLLARS
--------------------------------------------------------------------------
Every function below returns plain dicts: session/date, direction, entry/
exit time+price+fill_kind, exit_reason, stop/target levels (B1 only), and a
`void`/`skip` reason where one applies. Raw index prices only -- no tick
value, no commission, no P&L anywhere in this file. That split matters for
gate G2 (REGISTERED sec 0: "the runner refuses P&L" in pre-flight mode):
`strategy.w16.preflight` calls exactly these functions and reports counts
and $ *distances* (stop distance, range width -- point differences times
strategy.w16.costs.POINT_VALUE, not a booked profit or loss) without ever
importing `pnl_dollars` or `trade_cost`; `strategy.w16.runner` calls the
SAME functions and adds cost/P&L on top. One detection engine, two
consumers -- not two copies that could silently drift apart on what counts
as an entry.

LOOK-AHEAD GUARDS (gate G4) -- WHAT EACH RULE MAY READ, BY CONSTRUCTION
--------------------------------------------------------------------------
* B1's opening range (H, L) is built ONLY from bars starting 09:30..09:59
  (`orb_session`'s `range_bars` slice); no bar at or after 10:00 can move it,
  by construction of the slice bounds, not by a runtime check.
* Every entry fills at the NEXT bar's open, never the triggering bar's own
  close or a later bar's open -- `fill_idx = trigger_idx + 1` is the only
  place a fill index is set, in both B1 and B3.
* B1's stop/target are tested starting at the FILL bar's own high/low
  (fill_idx itself) and never a bar before it -- the loop in
  `_orb_walk_exit` starts at `range(fill_idx, len(bars))`, so a bar with
  index < fill_idx is structurally unreachable from that loop.
  test_signals.py's look-ahead tests mutate a bar's timestamp by one minute
  and assert the resulting range/trigger/fill changes, which is the
  "a one-bar shift breaks it" form REGISTERED sec 6.3 asks for.
* B2's exit price is the NEXT session's 09:30 open, read from that session's
  own first bar and never a later one (`overnight_trade` indexes bar 0 of
  the next-day frame it is given, nothing else).
* B3's VWAP at bar t is a cumulative sum over bars 0..t of THE SAME SESSION
  ONLY (`_session_vwap` resets every call to a fresh session frame); a
  signal at bar t fills at bar t+1's open, same rule as B1.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd

from strategy.w16.sessions import (has_valid_open, orb_time_exit,
                                   session_close_time, session_window_mask)

TICK = 0.25          # index points (strategy.w16.costs.TICK_POINTS)


def _naive_et(df: pd.DataFrame) -> pd.DatetimeIndex:
    from strategy.w16.readback import local_naive_et
    return local_naive_et(df.index)


def _held_id(df: pd.DataFrame) -> np.ndarray:
    if "held_id" in df.columns:
        return df["held_id"].to_numpy()
    if "instrument_id" in df.columns:
        return df["instrument_id"].to_numpy()
    return np.full(len(df), -1)


# ---------------------------------------------------------------------
# B1 -- opening-range breakout (long + short, 2:1)
# ---------------------------------------------------------------------

def orb_session(df_session: pd.DataFrame, date_str: str, *, market: str,
                target_r: float = 2.0) -> dict:
    """One session's B1 outcome. `df_session` is that date's bars, RTH-
    windowed for that date already (strategy.w16.sessions.session_window_mask
    applied by the caller) and sorted ascending. Returns
    {"skipped": bool, "range_high", "range_low", "range_width", "trade": dict|None}.
    `trade` is None iff no trigger fired in the entry window; a trigger
    always produces exactly one trade record (entered, voided, or -- if the
    archive is missing bars past the trigger -- flagged "incomplete")."""
    if not has_valid_open(df_session):
        return {"skipped": True, "range_high": None, "range_low": None,
                "range_width": None, "trade": None}

    bars = df_session.sort_index()
    naive = _naive_et(bars)
    t = naive.time

    range_mask = (t >= dtime(9, 30)) & (t < dtime(10, 0))
    range_bars = bars[range_mask]
    H = float(range_bars["high"].max())
    L = float(range_bars["low"].min())
    W = H - L

    exit_t = orb_time_exit(date_str)
    exit_minutes = exit_t.hour * 60 + exit_t.minute
    entry_start = dtime(10, 0)
    entry_end_minutes = exit_minutes - 2                # "...15:28" = 15:30 - 2
    entry_end = dtime(entry_end_minutes // 60, entry_end_minutes % 60)
    entry_mask = (t >= entry_start) & (t <= entry_end)
    entry_bars = bars[entry_mask]

    trigger_pos = None
    direction = None
    for pos in range(len(entry_bars)):
        c = float(entry_bars["close"].iloc[pos])
        if c > H:
            trigger_pos, direction = pos, "long"
            break
        if c < L:
            trigger_pos, direction = pos, "short"
            break

    if trigger_pos is None:
        return {"skipped": False, "range_high": H, "range_low": L,
                "range_width": W, "trade": None}

    trigger_ts = entry_bars.index[trigger_pos]
    all_pos = bars.index.get_loc(trigger_ts)
    fill_idx = all_pos + 1
    if fill_idx >= len(bars):
        return {"skipped": False, "range_high": H, "range_low": L,
                "range_width": W,
                "trade": {"date": date_str, "market": market, "baseline": "B1",
                          "direction": direction, "voided": True,
                          "void_reason": "no bar after trigger to fill on"}}

    fill_price = float(bars["open"].iloc[fill_idx])
    stop = L if direction == "long" else H
    stop_dist = abs(fill_price - stop)
    target = (fill_price + target_r * stop_dist if direction == "long"
              else fill_price - target_r * stop_dist)

    if (direction == "long" and fill_price <= stop) or \
       (direction == "short" and fill_price >= stop):
        return {"skipped": False, "range_high": H, "range_low": L, "range_width": W,
                "trade": {"date": date_str, "market": market, "baseline": "B1",
                          "direction": direction, "voided": True,
                          "void_reason": "fill already beyond stop (gap through range)",
                          "fill_price": fill_price, "stop": stop}}

    exit_price, exit_reason = walk_stop_target_time_exit(
        bars, naive, fill_idx, direction, stop, target, exit_t)

    trade = {
        "date": date_str, "market": market, "baseline": "B1",
        "direction": direction, "voided": False,
        "fill_time": str(bars.index[fill_idx]), "fill_price": fill_price,
        "stop": stop, "target": target, "stop_dist": stop_dist,
        "exit_price": exit_price, "exit_reason": exit_reason,
        "entry_fill_kind": "market_or_stop",
        "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
    }
    return {"skipped": False, "range_high": H, "range_low": L, "range_width": W,
            "trade": trade}


def walk_stop_target_time_exit(bars: pd.DataFrame, naive: pd.DatetimeIndex,
                               fill_idx: int, direction: str, stop: float,
                               target: float, exit_bar_time: dtime) -> tuple[float, str]:
    """Shared by orb_session and the C-B1 control (strategy.w16.controls):
    from `fill_idx` (inclusive) forward, exit at the stop (gap-fill aware),
    at the target (only on a >=1-tick-through trade), or at the open of the
    first bar whose start is >= `exit_bar_time` -- whichever comes first,
    stop winning a same-bar tie (sec 3.1). Falls back to the last available
    close if the archive runs out first (should not happen on real data;
    flagged by its own exit_reason so it is never silently mistaken for a
    real exit)."""
    for j in range(fill_idx, len(bars)):
        bar = bars.iloc[j]
        bt = naive[j].time()
        if bt >= exit_bar_time:
            return float(bar["open"]), "time_exit"
        hi, lo, op = float(bar["high"]), float(bar["low"]), float(bar["open"])
        if direction == "long":
            hit_stop = lo <= stop
            hit_target = hi >= target + TICK
        else:
            hit_stop = hi >= stop
            hit_target = lo <= target - TICK
        if hit_stop:
            return (op if _gapped(op, stop, direction) else stop), "stop"
        if hit_target:
            return target, "target"
    return float(bars["close"].iloc[-1]), "data_ended_before_exit"


def _gapped(open_px: float, stop: float, direction: str) -> bool:
    return (open_px <= stop) if direction == "long" else (open_px >= stop)


# ---------------------------------------------------------------------
# B2 -- overnight hold (long only)
# ---------------------------------------------------------------------

def overnight_trade(df_day: pd.DataFrame, df_next_day: pd.DataFrame,
                    date_str: str, next_date_str: str, *, market: str) -> dict:
    """One (day, next trading day) pair. Both frames are that date's RTH-
    windowed bars. Returns a trade dict, or a dict with "skipped": True if
    either session has no usable close/open bar."""
    if df_day.empty or df_next_day.empty:
        return {"skipped": True, "reason": "missing session bars", "trade": None}
    day_sorted = df_day.sort_index()
    next_sorted = df_next_day.sort_index()
    entry_bar = day_sorted.iloc[-1]           # the 15:59 (or early-close) bar
    exit_bar = next_sorted.iloc[0]            # the 09:30 bar
    entry_held = _held_id(day_sorted)[-1]
    exit_held = _held_id(next_sorted)[0]
    voided = bool(entry_held != exit_held)
    trade = {
        "date": date_str, "next_date": next_date_str, "market": market,
        "baseline": "B2", "direction": "long",
        "entry_price": float(entry_bar["close"]), "exit_price": float(exit_bar["open"]),
        "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop",
        "voided": voided,
        "void_reason": ("roll spans the hold (different instrument_id)" if voided else None),
    }
    return {"skipped": False, "trade": trade}


# ---------------------------------------------------------------------
# B3 -- VWAP flip
# ---------------------------------------------------------------------

def _session_vwap(bars: pd.DataFrame) -> np.ndarray:
    tp = (bars["high"].to_numpy() + bars["low"].to_numpy() + bars["close"].to_numpy()) / 3.0
    vol = bars["volume"].to_numpy(dtype=float)
    cum_pv = np.cumsum(tp * vol)
    cum_v = np.cumsum(vol)
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap = np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    return vwap


def vwap_flip_session(df_session: pd.DataFrame, date_str: str, *, market: str) -> dict:
    """One session's B3 outcome: {"skipped", "n_flips", "trades": [...]}.
    `df_session` is that date's RTH-windowed bars, sorted ascending. Every
    element of "trades" is one leg (an entry, or a flip's paired exit+entry,
    or the final flat-at-close exit) -- REGISTERED sec 3.3: "A reversal is
    two trades: the exit of one and the entry of the next, each charged its
    own fees and slippage." Legs are later paired into round-trip trades by
    the caller (adjacent exit/entry legs at the same flip share nothing but
    chronology, so pairing is the runner's job, not this function's)."""
    if not has_valid_open(df_session):
        return {"skipped": True, "n_flips": 0, "legs": []}

    bars = df_session.sort_index()
    naive = _naive_et(bars)
    t = naive.time
    close_t = session_close_time(date_str)
    close_minutes = close_t.hour * 60 + close_t.minute
    signal_end_minutes = close_minutes - 3            # "...15:57" = 16:00 - 3
    signal_end = dtime(signal_end_minutes // 60, signal_end_minutes % 60)
    signal_mask = (t >= dtime(9, 30)) & (t <= signal_end)

    vwap = _session_vwap(bars)
    closes = bars["close"].to_numpy()
    opens = bars["open"].to_numpy()
    n = len(bars)

    position = None            # "long" | "short" | None
    legs = []
    n_flips = 0
    for i in range(n):
        if not signal_mask[i]:
            continue
        if np.isnan(vwap[i]):
            continue
        want = "long" if closes[i] > vwap[i] else ("short" if closes[i] < vwap[i] else None)
        if want is None or want == position:
            continue
        fill_idx = i + 1
        if fill_idx >= n:
            continue                      # nothing left to fill on; not a flip
        fill_price = float(opens[fill_idx])
        fill_time = str(bars.index[fill_idx])
        if position is not None:
            legs.append({"date": date_str, "market": market, "baseline": "B3",
                        "leg": "exit", "direction": position,
                        "price": fill_price, "time": fill_time,
                        "fill_kind": "market_or_stop", "reason": "flip"})
        legs.append({"date": date_str, "market": market, "baseline": "B3",
                    "leg": "entry", "direction": want,
                    "price": fill_price, "time": fill_time,
                    "fill_kind": "market_or_stop", "reason": "flip"})
        position = want
        n_flips += 1

    if position is not None:
        last_close = float(closes[-1])
        legs.append({"date": date_str, "market": market, "baseline": "B3",
                    "leg": "exit", "direction": position,
                    "price": last_close, "time": str(bars.index[-1]),
                    "fill_kind": "market_or_stop", "reason": "flat_at_close"})

    return {"skipped": False, "n_flips": n_flips, "legs": legs}


def pair_b3_legs(legs: list[dict]) -> list[dict]:
    """entry/exit legs (in chronological order, one session's own) -> round
    trip trade dicts with entry_price/exit_price/direction, one per position
    held. An unmatched leading "entry" with no following "exit" (should not
    happen -- every session ends flat_at_close) is returned voided rather
    than silently dropped."""
    trades = []
    open_entry = None
    for leg in legs:
        if leg["leg"] == "entry":
            open_entry = leg
        elif leg["leg"] == "exit":
            if open_entry is None:
                trades.append({"date": leg["date"], "market": leg["market"],
                              "baseline": "B3", "direction": leg["direction"],
                              "voided": True, "void_reason": "exit with no matching entry"})
                continue
            trades.append({
                "date": open_entry["date"], "market": open_entry["market"], "baseline": "B3",
                "direction": open_entry["direction"], "voided": False,
                "entry_price": open_entry["price"], "entry_time": open_entry["time"],
                "exit_price": leg["price"], "exit_time": leg["time"],
                "exit_reason": leg["reason"],
                "entry_fill_kind": open_entry["fill_kind"], "exit_fill_kind": leg["fill_kind"],
            })
            open_entry = None
    if open_entry is not None:
        trades.append({"date": open_entry["date"], "market": open_entry["market"],
                      "baseline": "B3", "direction": open_entry["direction"],
                      "voided": True, "void_reason": "entry with no matching exit"})
    return trades
