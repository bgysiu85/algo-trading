#!/usr/bin/env python3
"""W16 BB-v0: bar-only entry batch -- ABD (ATR-band dip buy), SSS
(shooting-star short), TMB (Trader Math breakout, incl. hurst_proxy() and
autocorr_lag5()), CRT (Candle Range Theory 3-candle), NRS (NR4 compression
squeeze, incl. a 1-hour Globex resampler anchored 18:00 ET and its
chandelier trail). docs/research/REGISTERED_w16_bar_batch.md. Board
W16-0008 subitem 3.

SAME SPLIT AS strategy.w16.signals / strategy.w16.drift_vwap -- NO DOLLARS
HERE. Every generate_*_trades function below returns plain dicts (raw
index prices, a "voided" flag, an exit_reason, entry_fill_kind/
exit_fill_kind) -- no tick value, no commission, no P&L. strategy.w16.
bb_runner prices them with strategy.w16.runner.price_all/summarize, the
same pattern REGISTERED_w16_session_baselines.md's and REGISTERED_
w16_drift_vwap.md's engines already use.

LOOK-AHEAD GUARDS (sec 6.2) -- WHAT EACH RULE MAY READ, BY CONSTRUCTION
------------------------------------------------------------------------
* ABD's band for bar j reads only close_(j-1) and ATR_(j-1) (`atr[j - 1]`,
  `closes[j - 1]` -- never index j or later).
* SSS enters at bar j+1's open and exits at bar j+2's open, never bar j's
  own close (`entry_idx = j + 1`, `exit_idx = entry_idx + hold_bars`).
* TMB's HP/AC/5-bar-high at bar k use only bars <= k (`hurst_proxy`,
  `autocorr_lag5` and the `highs[k - 5:k]` slice, which excludes k);
  fill is at bar k+1's open. The trailing stop at minute i uses
  `running_hh` accumulated only from bars < i (`_tmb_walk`: the extreme
  is folded in AFTER a bar's own stop/target check, for use starting the
  NEXT minute).
* CRT's C2 condition is read at C2's close; the entry stop is live only
  inside C3's own window (`_crt_series_events`'s per-bar slice), and the
  target/stop come from C1/C2 values fixed at C2's close.
* NRS's squeeze test at bar k uses ranges of bars <= k (`squeeze_flag`).
  Orders are armed only once bar k has fully closed (the `h_pos`
  advance loop in `generate_nrs_trades` arms `pending` at the same
  moment it processes bar k's own completion) and are live only during
  bar k+1's own window; the chandelier at hour m uses only bars <= m
  (folded in at that same completion moment, before any minute of
  bar m+1 is examined).
* Resampled bars are not usable before their own last minute has closed
  -- inherited unchanged from strategy.w16.sessions.resample_session_bars
  (label="left", closed="left").
* Exit walks start at the fill minute; the fill minute's own range can
  hit a stop (tested) but never a target (inherited from
  strategy.w16.drift_vwap.fast_walk_stop_target_time_exit, reused here
  for ABD/CRT, and reimplemented the same way in `_tmb_walk`).
* The holdout refusal lives in strategy.w16.bb_holdout, mutation-tested
  there.

WHAT THIS FIRST BUILD DOES NOT YET COVER
------------------------------------------------------------------------
The reported-only variants listed at the end of each REGISTERED sec 3.x
subsection (touch fills, mirrored sides not already parameterised here,
CRT re-break entry, NRS 5-candle/day-session/squeeze-bar-stop readings)
are NOT implemented in this module. strategy.w16.bb_runner's reported-
variants block covers ES and the ones this module already parameterises
(TMB mirrored short, SSS prior-day-red is NOT covered either); the rest
are flagged TODO on the board (a follow-up subitem) rather than guessed
at under time pressure. Nothing scored (sec 9) depends on them.
"""
from __future__ import annotations

import math
from datetime import time as dtime

import numpy as np
import pandas as pd

from strategy.w16.drift_vwap import fast_walk_stop_target_time_exit
from strategy.w16.sessions import resample_session_bars, session_close_time
from strategy.w16.signals import TICK, _gapped, _held_id, _naive_et

# ---------------------------------------------------------------------
# common: day-session flat time, tick rounding, session cleanliness,
# continuous cross-day resampling, Wilder ATR with the roll-aware TR rule
# ---------------------------------------------------------------------

FLAT_OFFSET_MIN = 5     # "flat at 15:55" = 5 minutes before the session's own close (sec 2)


def bb_flat_time(date_str: str) -> dtime:
    """15:55, or 12:55 on an early-close day (sec 2's day-session rules,
    same shape as strategy.w16.drift_vwap.dvp_flat_time)."""
    close = session_close_time(date_str)
    minutes = close.hour * 60 + close.minute - FLAT_OFFSET_MIN
    return dtime(minutes // 60, minutes % 60)


def _t2m(t: dtime) -> int:
    return t.hour * 60 + t.minute


def round_tick(x: float, *, direction: str = "nearest") -> float:
    """`x` rounded to the nearest 0.25-pt tick. direction: 'nearest' (the
    default), 'down' (ABD's band, sec 3.1) or 'up'."""
    if direction == "down":
        return math.floor(round(x / TICK, 6)) * TICK
    if direction == "up":
        return math.ceil(round(x / TICK, 6)) * TICK
    return round(x / TICK) * TICK


def round_distance_tick(x: float) -> float:
    """A stop/target/reward DISTANCE rounded to the nearest tick, with a
    1-tick minimum (sec 3.1/3.4's "rounded to the nearest tick, minimum
    1 tick")."""
    ticks = max(round(x / TICK), 1)
    return ticks * TICK


def session_is_clean(df_session: pd.DataFrame, date_str: str, *, gap_minutes: int = 5) -> bool:
    """sec 2: "A session missing its 09:30 1-minute bar, or with a gap of
    more than 5 minutes between 1-minute bars inside 09:30-16:00, is
    skipped and counted." Unlike strategy.w16.sessions.has_valid_open
    (which only gap-checks the first hour by default), this checks the
    WHOLE RTH window -- every BB-v0 day-session rule trades all day, not
    just the open."""
    if df_session.empty:
        return False
    naive = _naive_et(df_session)
    if naive.time.min() != dtime(9, 30):
        return False
    minutes = sorted((naive.hour * 60 + naive.minute).tolist())
    for a, b in zip(minutes, minutes[1:]):
        if b - a > gap_minutes:
            return False
    return True


def build_day_session_series(frames: dict[str, pd.DataFrame], dates, bar_minutes: int) -> pd.DataFrame:
    """Concatenate resample_session_bars(frames[d], bar_minutes) for every
    CLEAN session date, in day order -- the continuous "regular-hours
    chart" series rules A (ABD) and C (TMB) run their ATR/HP/AC history on
    (sec 2: "Indicator history ... run on the continuous series of
    day-session bars across days"). A skipped (unclean) session
    contributes no bars, so a rule's history has a gap there, not a
    fabricated bar."""
    parts = []
    for d in sorted(str(x) for x in dates):
        day = frames.get(d)
        if day is None or day.empty or not session_is_clean(day, d):
            continue
        rb = resample_session_bars(day, bar_minutes)
        if not rb.empty:
            parts.append(rb)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def wilder_atr(bars: pd.DataFrame, period: int, *, held_id=None) -> np.ndarray:
    """Wilder ATR (RMA) over `bars` (needs high/low/close columns). sec 2's
    roll rule: TR = H-L (not the usual max(H,prior_close)-min(L,prior_
    close)) whenever `held_id[i] != held_id[i-1]` -- a roll bar's TR never
    reads a prior-contract close. Index 0 has no prior bar at all, so
    TR_0 = H_0 - L_0 unconditionally. Returns a float array, NaN before
    the RMA seeds at index period-1 (Wilder's own seeding: a simple
    average of the first `period` TRs)."""
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    n = len(bars)
    if held_id is None:
        held_id = _held_id(bars)
    tr = np.empty(n, dtype=float)
    if n:
        tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        if held_id[i] != held_id[i - 1]:
            tr[i] = highs[i] - lows[i]
        else:
            tr[i] = max(highs[i], closes[i - 1]) - min(lows[i], closes[i - 1])
    atr = np.full(n, np.nan)
    if n >= period:
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def log_returns_roll_aware(bars: pd.DataFrame, *, held_id=None) -> np.ndarray:
    """r_t = ln(C_t / C_(t-1)), NaN at t==0 and at any bar whose
    `held_id` differs from the prior bar's (sec 2: "a roll ... its 1-bar
    return is missing")."""
    closes = bars["close"].to_numpy(dtype=float)
    n = len(bars)
    if held_id is None:
        held_id = _held_id(bars)
    r = np.full(n, np.nan)
    for i in range(1, n):
        if held_id[i] == held_id[i - 1] and closes[i - 1] > 0 and closes[i] > 0:
            r[i] = math.log(closes[i] / closes[i - 1])
    return r


def _walk_1m_fixed(day1m: pd.DataFrame, fill_ts, direction: str, stop: float,
                   target: float, date_str: str):
    """Exit walk on 1-minute bars from `fill_ts` (inclusive) to the
    session's own flat time (bb_flat_time), fixed stop/target -- used by
    ABD and CRT. Reuses strategy.w16.drift_vwap.fast_walk_stop_target_
    time_exit (generic, not DVP-specific). Returns (exit_price,
    exit_reason, exit_ts, voided, same_bar_tie)."""
    bars = day1m.sort_index()
    naive = _naive_et(bars)
    minute_of_day = (naive.hour * 60 + naive.minute).to_numpy()
    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    held = _held_id(bars)
    fill_idx = int(bars.index.get_indexer([fill_ts])[0])
    if fill_idx < 0:
        fill_idx = int(bars.index.searchsorted(fill_ts))
    flat_minute = _t2m(bb_flat_time(date_str))
    exit_price, exit_reason, exit_idx, tie = fast_walk_stop_target_time_exit(
        minute_of_day, opens, highs, lows, fill_idx, direction, stop, target, flat_minute)
    exit_ts = bars.index[exit_idx]
    voided = bool(held[fill_idx] != held[exit_idx])
    return exit_price, exit_reason, exit_ts, voided, tie


# ---------------------------------------------------------------------
# Rule A -- ABD: ATR-band dip buy (sec 3.1). Scored: NQ. Long only.
# ---------------------------------------------------------------------

def generate_abd_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                        atr_mult: float = 3.1, target_mult: float = 2.0,
                        stop_mult: float = 1.5) -> list[dict]:
    """atr_mult/target_mult(+stop_mult, scaled together): sec 7.3 grid
    dimensions (registered 3.1 / (2.0, 1.5)). Long only."""
    bars5 = build_day_session_series(frames, dates, 5)
    if bars5.empty:
        return []
    held = _held_id(bars5)
    atr = wilder_atr(bars5, 14, held_id=held)
    naive5 = _naive_et(bars5)
    dates5 = naive5.strftime("%Y-%m-%d").to_numpy()
    times5 = naive5.time
    closes = bars5["close"].to_numpy(dtype=float)
    n = len(bars5)

    trades: list[dict] = []
    for j in range(1, n):
        t = times5[j]
        if t == dtime(9, 30) or t < dtime(9, 35) or t > dtime(15, 50):
            continue
        a_prev = atr[j - 1]
        if not np.isfinite(a_prev):
            continue
        date_str = str(dates5[j])
        band = round_tick(closes[j - 1] - atr_mult * a_prev, direction="down")

        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        bar_start = bars5.index[j]
        bar_end = bar_start + pd.Timedelta(minutes=5)
        window = day1m[(day1m.index >= bar_start) & (day1m.index < bar_end)].sort_index()
        fill_price = None
        fill_ts = None
        for ts, row in window.iterrows():
            op = float(row["open"])
            if op <= band:
                fill_price, fill_ts = op, ts
                break
            if float(row["low"]) <= band - TICK:
                fill_price, fill_ts = band, ts
                break
        if fill_price is None:
            continue

        target_dist = round_distance_tick(target_mult * a_prev)
        stop_dist = round_distance_tick(stop_mult * a_prev)
        target = fill_price + target_dist
        stop = fill_price - stop_dist
        if fill_price <= stop:
            trades.append({"date": date_str, "market": market, "baseline": "ABD",
                          "direction": "long", "voided": True,
                          "void_reason": "fill already at/through stop", "fill_price": fill_price,
                          "stop": stop, "band": band, "atr_prev": a_prev})
            continue

        exit_price, exit_reason, exit_ts, voided, tie = _walk_1m_fixed(
            day1m, fill_ts, "long", stop, target, date_str)
        trades.append({
            "date": date_str, "market": market, "baseline": "ABD",
            "direction": "long", "voided": voided,
            "fill_time": str(fill_ts), "fill_price": fill_price,
            "band": band, "atr_prev": a_prev, "stop": stop, "target": target,
            "stop_dist": stop_dist, "target_dist": target_dist,
            "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
            "entry_fill_kind": "target",
            "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
            "same_bar_tie": tie,
        })
    return trades


# ---------------------------------------------------------------------
# Rule B -- SSS: shooting-star short, one-bar hold (sec 3.2). Scored: NQ.
# Short only.
# ---------------------------------------------------------------------

def generate_sss_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                        wick_mult: float = 2.0, hold_bars: int = 1) -> list[dict]:
    """wick_mult/hold_bars: sec 7.3 grid dimensions (registered 2.0 / 1).
    Short only. Per-session (no cross-day continuity needed -- no ATR)."""
    trades: list[dict] = []
    for date_str in sorted(str(d) for d in dates):
        day = frames.get(date_str)
        if day is None or day.empty or not session_is_clean(day, date_str):
            continue
        bars5 = resample_session_bars(day, 5)
        if bars5.empty:
            continue
        naive = _naive_et(bars5)
        times = naive.time
        opens = bars5["open"].to_numpy(dtype=float)
        highs = bars5["high"].to_numpy(dtype=float)
        lows = bars5["low"].to_numpy(dtype=float)
        closes = bars5["close"].to_numpy(dtype=float)
        held = _held_id(bars5)
        n = len(bars5)

        next_eligible = 0
        for j in range(n):
            if j < next_eligible:
                continue
            if not (dtime(9, 30) <= times[j] <= dtime(15, 45)):
                continue
            U = highs[j] - max(opens[j], closes[j])
            D = min(opens[j], closes[j]) - lows[j]
            B = abs(closes[j] - opens[j])
            if not (U >= wick_mult * B and D <= 0.1 * U and U >= TICK):
                continue
            entry_idx = j + 1
            exit_idx = j + 1 + hold_bars          # entry at j+1, hold N bars -> exit at j+1+N
            if exit_idx >= n:
                continue
            fill_price = float(opens[entry_idx])
            exit_price = float(opens[exit_idx])
            voided = bool(held[entry_idx] != held[exit_idx])
            trades.append({
                "date": date_str, "market": market, "baseline": "SSS",
                "direction": "short", "voided": voided,
                "fill_time": str(bars5.index[entry_idx]), "fill_price": fill_price,
                "exit_time": str(bars5.index[exit_idx]), "exit_price": exit_price,
                "exit_reason": "time_exit",
                "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop",
            })
            next_eligible = exit_idx
    return trades


# ---------------------------------------------------------------------
# Rule C -- TMB: Trader Math breakout (sec 3.3). Scored: NQ. Long only
# (mirror_short=True generates the reported mirrored short).
# ---------------------------------------------------------------------

def hurst_proxy(bars: pd.DataFrame, atr20: np.ndarray) -> np.ndarray:
    """sec 3.3: HP_k = 100 * ln(R_k / ATR20_k) / ln(20), R_k = the 20-bar
    high-low range k-19..k (inclusive). NaN where the 20-bar window is
    incomplete, ATR20_k is not finite/positive, or R_k <= 0. OUR
    CONSTRUCTION, not the source's undisclosed formula (sec 3.3)."""
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    n = len(bars)
    hp = np.full(n, np.nan)
    for k in range(19, n):
        r_k = highs[k - 19:k + 1].max() - lows[k - 19:k + 1].min()
        a = atr20[k]
        if r_k <= 0 or not np.isfinite(a) or a <= 0:
            continue
        hp[k] = 100.0 * math.log(r_k / a) / math.log(20)
    return hp


def autocorr_lag5(returns: np.ndarray) -> np.ndarray:
    """sec 3.3: AC_k = Pearson r(r_t, r_(t-5)) for t = k-19..k (20 bars).
    Needs all 20 pairs valid (neither r_t nor r_(t-5) NaN); NaN otherwise
    (sec 3.2: "it needs 20 valid pairs, otherwise the bar has no
    signal" -- near a roll, or before bar 24)."""
    n = len(returns)
    ac = np.full(n, np.nan)
    for k in range(24, n):
        xs, ys = [], []
        for t in range(k - 19, k + 1):
            rt, rt5 = returns[t], returns[t - 5]
            if np.isfinite(rt) and np.isfinite(rt5):
                xs.append(rt)
                ys.append(rt5)
        if len(xs) < 20:
            continue
        xa, ya = np.array(xs), np.array(ys)
        if xa.std() == 0 or ya.std() == 0:
            continue
        ac[k] = float(np.corrcoef(xa, ya)[0, 1])
    return ac


def _tmb_walk(bars1m: pd.DataFrame, naive1m: pd.DatetimeIndex, fill_idx: int,
             atr_k: float, flat_minute: int, direction: str):
    """TMB's own exit walk: target = fill +/- 5*ATR20_k (fixed); stop =
    fill -/+ 4*ATR20_k initially, then after each COMPLETED 1-minute bar,
    stop = max/min(stop, extreme-since-entry -/+ 4*ATR20_k) -- ATR20_k
    stays fixed at entry, only the extreme (and so the stop) moves. A
    minute's own stop/target check uses the stop as of the START of that
    minute (i.e. built from bars strictly before it); the extreme/stop
    update for the NEXT minute happens only after this minute's own
    check clears (sec 6.2's look-ahead guard)."""
    opens = bars1m["open"].to_numpy(dtype=float)
    highs = bars1m["high"].to_numpy(dtype=float)
    lows = bars1m["low"].to_numpy(dtype=float)
    closes = bars1m["close"].to_numpy(dtype=float)
    minute_of_day = (naive1m.hour * 60 + naive1m.minute).to_numpy()
    n = len(bars1m)
    fill_price = opens[fill_idx]
    target_dist = round_distance_tick(5 * atr_k)
    stop_dist = round_distance_tick(4 * atr_k)
    if direction == "long":
        stop = fill_price - stop_dist
        target = fill_price + target_dist
    else:
        stop = fill_price + stop_dist
        target = fill_price - target_dist
    extreme = fill_price

    for i in range(fill_idx, n):
        if minute_of_day[i] >= flat_minute:
            return float(opens[i]), "time_exit", i
        lo, hi, op = lows[i], highs[i], opens[i]
        if direction == "long":
            hit_stop = lo <= stop
            hit_target = hi >= target + TICK
        else:
            hit_stop = hi >= stop
            hit_target = lo <= target - TICK
        if hit_stop:
            price = op if _gapped(op, stop, direction) else stop
            return price, "stop", i
        if hit_target:
            return float(target), "target", i
        if direction == "long":
            extreme = max(extreme, hi)
            stop = max(stop, extreme - stop_dist)
        else:
            extreme = min(extreme, lo)
            stop = min(stop, extreme + stop_dist)
    return float(closes[-1]), "data_ended_before_exit", n - 1


def generate_tmb_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                        hp_threshold: float = 50.0, ac_threshold: float = -0.10,
                        mirror_short: bool = False) -> list[dict]:
    """hp_threshold/ac_threshold: sec 7.3 grid dimensions (registered
    50 / -0.10). Long only unless mirror_short=True (sec 3.3's reported
    mirrored short: HP>threshold, AC<=threshold, close below the prior
    5 bars' low; target 5 ATR below, 4 ATR trailing stop above)."""
    bars15 = build_day_session_series(frames, dates, 15)
    if bars15.empty:
        return []
    held = _held_id(bars15)
    atr20 = wilder_atr(bars15, 20, held_id=held)
    returns = log_returns_roll_aware(bars15, held_id=held)
    hp = hurst_proxy(bars15, atr20)
    ac = autocorr_lag5(returns)
    naive15 = _naive_et(bars15)
    dates15 = naive15.strftime("%Y-%m-%d").to_numpy()
    times15 = naive15.time
    highs = bars15["high"].to_numpy(dtype=float)
    lows = bars15["low"].to_numpy(dtype=float)
    closes = bars15["close"].to_numpy(dtype=float)
    opens15 = bars15["open"].to_numpy(dtype=float)
    n = len(bars15)

    trades: list[dict] = []
    for k in range(5, n):
        if not (dtime(9, 30) <= times15[k] <= dtime(15, 30)):
            continue
        if not (np.isfinite(hp[k]) and np.isfinite(ac[k]) and np.isfinite(atr20[k])):
            continue
        if not (hp[k] > hp_threshold and ac[k] <= ac_threshold):
            continue
        prior_hi = highs[k - 5:k].max()
        prior_lo = lows[k - 5:k].min()
        if not mirror_short:
            if not (closes[k] > prior_hi):
                continue
            direction = "long"
        else:
            if not (closes[k] < prior_lo):
                continue
            direction = "short"
        if k + 1 >= n:
            continue
        date_str = str(dates15[k])
        if str(dates15[k + 1]) != date_str:
            continue          # defensive: the 15:30 signal cutoff should make this unreachable

        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        bars1m = day1m.sort_index()
        naive1m = _naive_et(bars1m)
        entry_ts = bars15.index[k + 1]
        fill_idx = int(bars1m.index.get_indexer([entry_ts])[0])
        if fill_idx < 0:
            continue
        flat_minute = _t2m(bb_flat_time(date_str))
        exit_price, exit_reason, exit_pos = _tmb_walk(
            bars1m, naive1m, fill_idx, atr20[k], flat_minute, direction)
        held1m = _held_id(bars1m)
        voided = bool(held1m[fill_idx] != held1m[exit_pos])
        target_dist = round_distance_tick(5 * atr20[k])
        stop_dist = round_distance_tick(4 * atr20[k])
        trades.append({
            "date": date_str, "market": market,
            "baseline": "TMB-short" if mirror_short else "TMB",
            "direction": direction, "voided": voided,
            "fill_time": str(entry_ts), "fill_price": float(opens15[k + 1]),
            "hp": float(hp[k]), "ac": float(ac[k]), "atr20": float(atr20[k]),
            "stop_dist": stop_dist, "target_dist": target_dist,
            "exit_time": str(bars1m.index[exit_pos]), "exit_price": exit_price,
            "exit_reason": exit_reason,
            "entry_fill_kind": "market_or_stop",
            "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
        })
    return trades


# ---------------------------------------------------------------------
# Rule D -- CRT: Candle Range Theory 3-candle (sec 3.4). Scored: NQ. Both
# sides.
# ---------------------------------------------------------------------

def _crt_stop_fill(window: pd.DataFrame, level_hi: float, level_lo: float):
    """First 1-minute bar (chronological) in `window` whose high/low
    crosses either stop level. Returns (direction, fill_ts, fill_price)
    or (None, None, None) if neither triggers; direction is "both" (a
    void, sec 3.4: "a C2 that sweeps both sides is not a setup" is a
    DIFFERENT both-side case -- this is C3's OWN both-levels case, not
    explicitly named in sec 3.4 but handled the same defensive way NRS's
    identical situation is: sec 3.5's "voided and counted")."""
    for ts, row in window.iterrows():
        hi, lo, op = float(row["high"]), float(row["low"]), float(row["open"])
        hit_hi = hi >= level_hi
        hit_lo = lo <= level_lo
        if hit_hi and hit_lo:
            return "both", ts, None
        if hit_hi:
            return "long", ts, max(op, level_hi)
        if hit_lo:
            return "short", ts, min(op, level_lo)
    return None, None, None


def _crt_series_events(bars_n: pd.DataFrame, day1m: pd.DataFrame, window_end: dtime, period_minutes: int):
    """Every setup on one series (15/30/60-min day-session bars): C1=bar
    i, C2=bar i+1, C3=bar i+2. Returns a list of dicts, each either
    {"kind": "both_sweep", ...} (counted, never a trade) or {"kind":
    "setup", "direction", "H1", "L1", "fill_time"|None, "fill_price"|None,
    "void": bool}."""
    highs = bars_n["high"].to_numpy(dtype=float)
    lows = bars_n["low"].to_numpy(dtype=float)
    closes = bars_n["close"].to_numpy(dtype=float)
    n = len(bars_n)
    day1m_sorted = day1m.sort_index()
    events = []
    for i in range(n - 2):
        H1, L1 = highs[i], lows[i]
        H2, L2, C2 = highs[i + 1], lows[i + 1], closes[i + 1]
        swept_low = L2 < L1
        swept_high = H2 > H1
        inside_close = L1 <= C2 <= H1
        if swept_low and swept_high:
            events.append({"i": i, "period": period_minutes, "kind": "both_sweep"})
            continue
        bullish = swept_low and inside_close
        bearish = swept_high and inside_close
        if not (bullish or bearish):
            continue
        direction = "long" if bullish else "short"
        c3_start = bars_n.index[i + 2]
        c3_end = c3_start + pd.Timedelta(minutes=period_minutes)
        window = day1m_sorted[(day1m_sorted.index >= c3_start) & (day1m_sorted.index < c3_end)]
        naive_win = _naive_et(window)
        window = window[naive_win.time < window_end]
        level_hi = round_tick(H2 + TICK)
        level_lo = round_tick(L2 - TICK)
        kind, fill_ts, fill_price = _crt_stop_fill(window, level_hi, level_lo)
        events.append({"i": i, "period": period_minutes, "kind": "setup", "direction": direction,
                      "H1": H1, "L1": L1, "fill_time": fill_ts,
                      "fill_price": fill_price if kind == direction else None,
                      "void": kind == "both"})
    return events


def generate_crt_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                        reward_risk: float = 1.5, window_end: dtime = dtime(12, 0)) -> list[dict]:
    """reward_risk/window_end: sec 7.3 grid dimensions (registered
    1.5 / 12:00). Both sides. No Mondays."""
    period_priority = {15: 0, 30: 1, 60: 2}
    trades: list[dict] = []
    for date_str in sorted(str(d) for d in dates):
        if pd.Timestamp(date_str).dayofweek == 0:            # Monday
            continue
        day = frames.get(date_str)
        if day is None or day.empty or not session_is_clean(day, date_str):
            continue
        day1m = day.sort_index()

        candidates = []
        void_events = []
        for period in (15, 30, 60):
            bars_n = resample_session_bars(day, period)
            if len(bars_n) < 3:
                continue
            for ev in _crt_series_events(bars_n, day1m, window_end, period):
                if ev["kind"] != "setup":
                    continue
                if ev["void"]:
                    void_events.append(ev)
                elif ev["fill_time"] is not None:
                    candidates.append(ev)

        # A void C3 (both levels hit in one 1-minute bar) is itself a filled
        # event in time -- it can still be the day's EARLIEST outcome, ending
        # the day, even though it opens no position (sec 3.4 gives no
        # explicit rule for this exact case; treated the same defensive way
        # sec 3.5 treats NRS's identical situation: "voided and counted").
        all_events = candidates + [dict(v, fill_price=None) for v in void_events]
        if not all_events:
            continue
        all_events.sort(key=lambda e: (e["fill_time"], period_priority[e["period"]]))
        winner = all_events[0]

        if winner.get("fill_price") is None and winner.get("void"):
            trades.append({"date": date_str, "market": market, "baseline": "CRT",
                          "direction": None, "voided": True,
                          "void_reason": "C3 bar reached both stop levels",
                          "period_minutes": winner["period"],
                          "fill_time": str(winner["fill_time"])})
            continue

        direction = winner["direction"]
        H1, L1 = winner["H1"], winner["L1"]
        fill_price = winner["fill_price"]
        fill_ts = winner["fill_time"]
        target = H1 if direction == "long" else L1
        reward = (target - fill_price) if direction == "long" else (fill_price - target)
        if reward <= 0:
            trades.append({"date": date_str, "market": market, "baseline": "CRT",
                          "direction": direction, "voided": True,
                          "void_reason": "reward <= 0 at fill (fill at/through target)",
                          "fill_time": str(fill_ts), "fill_price": fill_price,
                          "target": target, "period_minutes": winner["period"]})
            continue

        risk_dist = round_distance_tick(reward / reward_risk)
        stop = fill_price - risk_dist if direction == "long" else fill_price + risk_dist

        exit_price, exit_reason, exit_ts, voided, tie = _walk_1m_fixed(
            day1m, fill_ts, direction, stop, target, date_str)
        trades.append({
            "date": date_str, "market": market, "baseline": "CRT",
            "direction": direction, "voided": voided,
            "period_minutes": winner["period"], "fill_time": str(fill_ts), "fill_price": fill_price,
            "H1": H1, "L1": L1, "stop": stop, "target": target,
            "stop_dist": risk_dist, "reward": reward,
            "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
            "entry_fill_kind": "market_or_stop",
            "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
            "same_bar_tie": tie,
        })
    return trades


# ---------------------------------------------------------------------
# Rule E -- NRS: NR4 compression squeeze (sec 3.5). Scored: ES and NQ.
# Both sides. Full Globex, holds overnight.
# ---------------------------------------------------------------------

def build_globex_hourly(df_1m_full: pd.DataFrame) -> pd.DataFrame:
    """1-hour Globex bars anchored at 18:00 ET (sec 3.5): resample the
    FULL 1-minute archive (NOT RTH-windowed) on naive ET wall-clock time.
    One hour evenly divides 24, so every hourly grid line lands on a
    whole ET clock hour regardless of the resample origin -- 18:00,
    19:00, ..., 17:00 -- and the 17:00-18:00 daily pause simply has no
    1-minute bars to aggregate, so it produces no bar (dropped below),
    matching "23 a day, with no bar for the pause." `held_id` is carried
    from each hour's first 1-minute bar (roll detection), same convention
    as strategy.w16.sessions.resample_session_bars. The returned frame's
    index is NAIVE America/New_York (not tz-aware)."""
    from strategy.w16.readback import local_naive_et
    if df_1m_full.empty:
        return pd.DataFrame()
    df = df_1m_full.sort_index()
    naive = local_naive_et(df.index)
    held = _held_id(df)
    work = df[["open", "high", "low", "close", "volume"]].copy()
    work.index = naive
    work["_held"] = held
    grouped = work.resample("1h", label="left", closed="left")
    agg = {
        "open": grouped["open"].first(), "high": grouped["high"].max(),
        "low": grouped["low"].min(), "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(), "held_id": grouped["_held"].first(),
    }
    out = pd.DataFrame(agg)
    return out.dropna(subset=["open"])


def _cme_trading_day(naive_ts) -> str:
    """sec 3.5: the CME trading day a naive ET timestamp belongs to --
    the SAME calendar date before 18:00, the NEXT calendar date at/after
    18:00 ("the Sunday 18:00 open starts Monday's CME trading day")."""
    ts = pd.Timestamp(naive_ts)
    d = ts.normalize()
    if ts.time() >= dtime(18, 0):
        d = d + pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def nrs_cme_trading_days(df_1m_full: pd.DataFrame) -> list[str]:
    """Every distinct CME trading day (sec 3.5) present in the FULL
    1-minute archive -- what strategy.w16.bb_holdout.split_dates and G2's
    pre-flight both need for NRS, since its own calendar (18:00 ET
    rollover) differs from the XNYS trading-day calendar the other four
    rules use. Vectorised (not a per-timestamp _cme_trading_day call in a
    Python loop) so it stays cheap at full-archive scale."""
    from strategy.w16.readback import local_naive_et
    if df_1m_full.empty:
        return []
    naive = local_naive_et(df_1m_full.index)
    d = naive.normalize()
    late = naive.hour >= 18                # ts.time() >= 18:00:00 <=> hour >= 18
    d = d + pd.to_timedelta(late.astype(int), unit="D")
    return sorted(pd.Index(d.strftime("%Y-%m-%d")).unique().tolist())


def _nrs_close_trade(position: dict, exit_price: float, exit_reason: str, exit_ts, market: str) -> dict:
    return {
        "date": position["cme_day"], "market": market, "baseline": "NRS",
        "direction": position["direction"], "voided": False,
        "fill_time": position["fill_time"], "fill_price": position["fill_price"],
        "squeeze_bar_time": position["squeeze_bar_time"],
        "stop": position["stop"], "exit_time": str(exit_ts), "exit_price": exit_price,
        "exit_reason": exit_reason,
        "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop",
        # Kept so a control (bb_runner.py's C-N1) can replay this exact trade's
        # chandelier/roll/training-end exit walk from its real entry point
        # under a randomised side, without re-deriving the squeeze that led
        # to it. Internal bookkeeping only -- not part of the sec 4 report
        # shape and dropped before any trade dict reaches runner.summarize.
        "entry_hourly_idx": position["entry_hourly_idx"],
        "entry_idx_1m": position["entry_idx_1m"],
    }


def _nrs_precompute(df_1m_full: pd.DataFrame) -> dict | None:
    """The hourly/1-minute arrays generate_nrs_trades needs, built ONCE per
    (frames, market) pair. Neither depends on chandelier_mult/squeeze_len
    (sec 7.3 grid dimensions) nor on any control's randomised side, so a
    control that replays many draws against the same archive (bb_runner.py's
    C-N1, via _nrs_walk_from_entry) passes its own real run's `_pre` back in
    rather than paying this cost again per draw. Returns None for an empty
    archive -- callers treat that exactly as generate_nrs_trades' own empty-
    hourly guard did before this was split out."""
    from strategy.w16.readback import local_naive_et

    hourly = build_globex_hourly(df_1m_full)
    if hourly.empty:
        return None
    h_highs = hourly["high"].to_numpy(dtype=float)
    h_lows = hourly["low"].to_numpy(dtype=float)
    h_held = hourly["held_id"].to_numpy()
    h_atr = wilder_atr(hourly, 14, held_id=h_held)
    h_start = hourly.index                                   # naive ET, ascending
    n_h = len(hourly)
    h_cme_day = np.array([_cme_trading_day(ts) for ts in h_start])

    df1 = df_1m_full.sort_index()
    naive1 = local_naive_et(df1.index)
    return {
        "h_highs": h_highs, "h_lows": h_lows, "h_ranges": h_highs - h_lows,
        "h_held": h_held, "h_atr": h_atr, "h_start_vals": h_start.values, "n_h": n_h,
        "h_cme_day": h_cme_day,
        "m_opens": df1["open"].to_numpy(dtype=float), "m_highs": df1["high"].to_numpy(dtype=float),
        "m_lows": df1["low"].to_numpy(dtype=float), "m_closes": df1["close"].to_numpy(dtype=float),
        "m_held": _held_id(df1), "m_naive": naive1.values, "m_ts": df1.index, "n_m": len(df1),
    }


def generate_nrs_trades(df_1m_full: pd.DataFrame, market: str, cme_train_days, *,
                        chandelier_mult: float = 3.0, squeeze_len: int = 4,
                        _pre: dict | None = None) -> list[dict]:
    """NRS -- NR4 compression squeeze (sec 3.5). `df_1m_full` is the FULL
    1-minute archive for this market (strategy.w16.preflight.load_root_
    bars' own output -- NOT RTH-windowed: NRS trades the whole Globex
    session and holds overnight). `cme_train_days`: the CME trading days
    (sec 3.5) in scope -- an order is armed only when its squeeze bar's
    own CME day is in this set. `_pre`: an already-built _nrs_precompute()
    bundle, to skip rebuilding it (internal use -- callers pass df_1m_full).

    chandelier_mult/squeeze_len: sec 7.3 grid dimensions (registered
    3.0 / 4).

    KNOWN SIMPLIFICATIONS (documented, not silently guessed at): the
    chandelier's first update, once the entry hour itself completes, uses
    that WHOLE hour's high/low (not just the portion after the fill) --
    a common, defensible convention the source's own description does not
    rule out. The roll exit is priced at the prior bar's close, 1 tick
    against the position (sec 4's "roll" fill kind)."""
    pre = _pre if _pre is not None else _nrs_precompute(df_1m_full)
    if pre is None:
        return []
    h_highs, h_lows, h_ranges = pre["h_highs"], pre["h_lows"], pre["h_ranges"]
    h_held, h_atr, h_start_vals, n_h = pre["h_held"], pre["h_atr"], pre["h_start_vals"], pre["n_h"]
    h_cme_day = pre["h_cme_day"]
    m_opens, m_highs, m_lows, m_closes = pre["m_opens"], pre["m_highs"], pre["m_lows"], pre["m_closes"]
    m_held, m_naive, m_ts, n_m = pre["m_held"], pre["m_naive"], pre["m_ts"], pre["n_m"]

    squeeze_flag = np.zeros(n_h, dtype=bool)
    for k in range(squeeze_len - 1, n_h):
        lo = k - (squeeze_len - 1)
        if len(set(h_held[lo:k + 1].tolist())) != 1:
            continue
        seg = h_ranges[lo:k + 1]
        if not np.isfinite(seg).all():
            continue
        if all(seg[t] >= seg[t + 1] for t in range(squeeze_len - 1)):
            squeeze_flag[k] = True

    train_set = {str(d) for d in cme_train_days}

    trades: list[dict] = []
    position = None
    day_used: set[str] = set()
    pending = None
    h_pos = -1

    def _arm(k):
        if k + 1 >= n_h:
            return None
        ws = h_start_vals[k + 1]
        return {"level_hi": round_tick(h_highs[k] + TICK), "level_lo": round_tick(h_lows[k] - TICK),
               "window_start": ws, "window_end": ws + np.timedelta64(1, "h"),
               "squeeze_idx": k, "cme_day": h_cme_day[k]}

    for m in range(n_m):
        ts_naive = m_naive[m]

        # LOOK-AHEAD GUARD: hour k is only "closed" -- its high/low/ATR
        # safe to read -- once ts_naive has reached the START OF THE NEXT
        # hour (h_start_vals[k+1]), i.e. hour k's own 60 minutes have all
        # occurred. Comparing against h_start_vals[h_pos+1] (hour k's OWN
        # start) instead would mark hour k closed the instant it begins,
        # exposing its still-forming high/low/ATR to the squeeze and
        # chandelier logic 59 minutes early -- so the bound below is
        # h_pos+2 (the start of the hour AFTER the candidate), not h_pos+1.
        while h_pos + 2 < n_h and h_start_vals[h_pos + 2] <= ts_naive:
            h_pos += 1
            closed = h_pos
            if position is not None and closed >= position["entry_hourly_idx"]:
                a = h_atr[closed]
                if np.isfinite(a):
                    if position["direction"] == "long":
                        position["extreme"] = max(position["extreme"], h_highs[closed])
                        position["stop"] = max(position["stop"], position["extreme"] - chandelier_mult * a)
                    else:
                        position["extreme"] = min(position["extreme"], h_lows[closed])
                        position["stop"] = min(position["stop"], position["extreme"] + chandelier_mult * a)
            # ATR14 must have seeded (np.isfinite) before an order can be sized --
            # a squeeze inside the first 13 hourly bars of the whole archive is
            # structurally impossible to size and is skipped, not guessed at.
            if position is None and pending is None and squeeze_flag[closed] and np.isfinite(h_atr[closed]):
                day = h_cme_day[closed]
                if day in train_set and day not in day_used:
                    pending = _arm(closed)

        if position is not None and m > position["entry_idx_1m"] and m_held[m] != m_held[m - 1]:
            prev_close = float(m_closes[m - 1])
            exit_price = prev_close - TICK if position["direction"] == "long" else prev_close + TICK
            trades.append(_nrs_close_trade(position, exit_price, "roll", m_ts[m - 1], market))
            position = None
            continue

        if position is not None:
            hi, lo, op = m_highs[m], m_lows[m], m_opens[m]
            if position["direction"] == "long" and lo <= position["stop"]:
                price = op if _gapped(op, position["stop"], "long") else position["stop"]
                trades.append(_nrs_close_trade(position, price, "stop", m_ts[m], market))
                position = None
            elif position["direction"] == "short" and hi >= position["stop"]:
                price = op if _gapped(op, position["stop"], "short") else position["stop"]
                trades.append(_nrs_close_trade(position, price, "stop", m_ts[m], market))
                position = None

        if position is None and pending is not None:
            if ts_naive >= pending["window_end"]:
                pending = None
            elif ts_naive >= pending["window_start"]:
                hit_hi = m_highs[m] >= pending["level_hi"]
                hit_lo = m_lows[m] <= pending["level_lo"]
                if hit_hi and hit_lo:
                    trades.append({"date": pending["cme_day"], "market": market, "baseline": "NRS",
                                  "direction": None, "voided": True,
                                  "void_reason": "1-minute bar reached both stop levels",
                                  "squeeze_bar_time": str(h_start_vals[pending["squeeze_idx"]])})
                    pending = None
                elif hit_hi or hit_lo:
                    direction = "long" if hit_hi else "short"
                    level = pending["level_hi"] if hit_hi else pending["level_lo"]
                    fill_price = max(m_opens[m], level) if direction == "long" else min(m_opens[m], level)
                    a0 = h_atr[pending["squeeze_idx"]]
                    stop0 = (fill_price - chandelier_mult * a0 if direction == "long"
                            else fill_price + chandelier_mult * a0)
                    position = {"direction": direction, "fill_price": fill_price, "entry_idx_1m": m,
                              "stop": stop0, "extreme": fill_price, "cme_day": pending["cme_day"],
                              "entry_hourly_idx": pending["squeeze_idx"] + 1,
                              "squeeze_bar_time": str(h_start_vals[pending["squeeze_idx"]]),
                              "fill_time": str(m_ts[m])}
                    day_used.add(pending["cme_day"])
                    pending = None

        if m == n_m - 1 and position is not None:
            trades.append(_nrs_close_trade(position, float(m_closes[m]), "training_end", m_ts[m], market))
            position = None

    return trades


def _nrs_walk_from_entry(pre: dict, direction: str, fill_price: float, entry_idx_1m: int,
                         entry_hourly_idx: int, cme_day: str, squeeze_bar_time: str,
                         market: str, *, chandelier_mult: float = 3.0) -> dict:
    """Replay ONLY the chandelier/roll/training-end exit walk (the part of
    generate_nrs_trades from a position's first tick onward), starting at a
    REAL trade's exact entry point but under a substituted `direction` --
    the one piece bb_runner.py's C-N1 control needs ("if this exact squeeze
    had been traded the other way, what would have happened?") without
    re-deriving the squeeze/arming logic that found the entry in the first
    place. `pre` is the _nrs_precompute() bundle for the SAME df_1m_full the
    real trade came from (pass the real run's own `_pre`, not a fresh one --
    see _nrs_precompute's docstring); `entry_idx_1m`/`entry_hourly_idx` are
    the real trade's own fields (see _nrs_close_trade). Mirrors
    generate_nrs_trades' exit logic bar-for-bar, including its look-ahead
    guard on which hourly bar is "closed" -- a change there must be mirrored
    here too, and test_bb_runner.py's C-N1 test checks that directly against
    generate_nrs_trades rather than trusting the two stay in sync by hand."""
    h_highs, h_lows, h_atr = pre["h_highs"], pre["h_lows"], pre["h_atr"]
    h_start_vals, n_h = pre["h_start_vals"], pre["n_h"]
    m_opens, m_highs, m_lows, m_closes = pre["m_opens"], pre["m_highs"], pre["m_lows"], pre["m_closes"]
    m_held, m_ts, n_m = pre["m_held"], pre["m_ts"], pre["n_m"]

    a0 = h_atr[entry_hourly_idx - 1]
    stop0 = fill_price - chandelier_mult * a0 if direction == "long" else fill_price + chandelier_mult * a0
    position = {"direction": direction, "fill_price": fill_price, "entry_idx_1m": entry_idx_1m,
               "stop": stop0, "extreme": fill_price, "cme_day": cme_day,
               "entry_hourly_idx": entry_hourly_idx, "squeeze_bar_time": squeeze_bar_time,
               "fill_time": str(m_ts[entry_idx_1m])}

    # h_pos starts one hour behind entry_hourly_idx -- the real run's own
    # h_pos at the fill minute (see generate_nrs_trades: the fill window IS
    # entry_hourly_idx's own still-forming hour, not yet closed).
    h_pos = entry_hourly_idx - 1
    for m in range(entry_idx_1m, n_m):
        ts_naive = pre["m_naive"][m]

        while h_pos + 2 < n_h and h_start_vals[h_pos + 2] <= ts_naive:
            h_pos += 1
            closed = h_pos
            if closed >= position["entry_hourly_idx"]:
                a = h_atr[closed]
                if np.isfinite(a):
                    if position["direction"] == "long":
                        position["extreme"] = max(position["extreme"], h_highs[closed])
                        position["stop"] = max(position["stop"], position["extreme"] - chandelier_mult * a)
                    else:
                        position["extreme"] = min(position["extreme"], h_lows[closed])
                        position["stop"] = min(position["stop"], position["extreme"] + chandelier_mult * a)

        if m > position["entry_idx_1m"] and m_held[m] != m_held[m - 1]:
            prev_close = float(m_closes[m - 1])
            exit_price = prev_close - TICK if position["direction"] == "long" else prev_close + TICK
            return _nrs_close_trade(position, exit_price, "roll", m_ts[m - 1], market)

        if m > position["entry_idx_1m"]:
            hi, lo, op = m_highs[m], m_lows[m], m_opens[m]
            if position["direction"] == "long" and lo <= position["stop"]:
                price = op if _gapped(op, position["stop"], "long") else position["stop"]
                return _nrs_close_trade(position, price, "stop", m_ts[m], market)
            elif position["direction"] == "short" and hi >= position["stop"]:
                price = op if _gapped(op, position["stop"], "short") else position["stop"]
                return _nrs_close_trade(position, price, "stop", m_ts[m], market)

        if m == n_m - 1:
            return _nrs_close_trade(position, float(m_closes[m]), "training_end", m_ts[m], market)

    # Unreachable when entry_idx_1m < n_m (always true for a real trade's
    # own entry), kept only so the function has an explicit return on every
    # path rather than falling off the end.
    return _nrs_close_trade(position, float(m_closes[n_m - 1]), "training_end", m_ts[n_m - 1], market)
