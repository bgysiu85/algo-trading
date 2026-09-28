#!/usr/bin/env python3
"""DVP-v0: Conti "drift VWAP pullback" on NQ, 15-min trend filter + 5-min
trigger. REGISTERED_w16_drift_vwap.md (the file governs; this module
implements its sec 2/3/6). Board W16-0006 subitem 2.

SAME SPLIT AS strategy.w16.signals -- NO DOLLARS HERE
------------------------------------------------------------------------
Every function below returns plain dicts/lists of raw index prices --
no tick value, no commission, no P&L. `strategy.w16.dvp_runner --preflight`
calls only the trigger-scanning functions in this file (never the exit
walk, never a cost function) so gate G2's "no P&L in this mode" is a
structural fact, not a flag; `--backtest` calls the same detection
functions and prices the resulting trades with strategy.w16.costs /
strategy.w16.runner.price_trade, exactly the pattern
REGISTERED_w16_session_baselines.md's engine already uses for B1/B2/B3.

LOOK-AHEAD GUARDS (REGISTERED sec 6.2) -- WHAT EACH RULE MAY READ
------------------------------------------------------------------------
* The drift state at tau reads only 15-min bars whose CLOSE time is <= tau
  (`_drift_state_at`, a bisect over each bar's own close-time-in-minutes --
  a bar's close time is by construction assigned only once the bar's
  15-minute window has fully elapsed, so a bar cannot appear in the
  lookup table before its own close).
* VWAP_k and P1h_k are cumulative/lookback over 15-min bars 0..k only
  (`_vwap_15m` is a running cumsum; `_p1h_at` indexes bar (k-4) or the
  session open, never bar k or later).
* A trigger at trigger-bar j fills at bar j+1's open (`fill_idx = j + 1`
  is the only place a fill index is set) -- the open of the 1-minute bar
  starting at tau, never the triggering bar's own close.
* The exit walk (`fast_walk_stop_target_time_exit`) starts at the fill
  minute (inclusive) forward only -- see its own docstring.
* G-loss counts only trades that have CLOSED (their exit walk returned)
  before the next trigger bar is even considered -- the guardrail state
  (`n_losses`, `consecutive_losses`, `stopped_by_loss`) is updated once
  per completed trade, inside the same forward loop that walks trigger
  bars in ascending time order, so a later bar can never move it.
* `compute_p_ref` reads only sessions in [2020-01-02, 2023-12-29] --
  test_drift_vwap.py asserts adding a 2024 session does not change it.
* The holdout refusal lives in strategy.w16.dvp_holdout, mutation-tested
  there.
"""
from __future__ import annotations

import bisect
from datetime import time as dtime

import numpy as np
import pandas as pd

from strategy.w16.sessions import (has_valid_open, resample_session_bars,
                                   session_close_time)
from strategy.w16.signals import TICK, _gapped, _held_id, _naive_et

# ---------------------------------------------------------------------
# P_ref -- pinned by Amendment A (PRE-RUN), before any P&L exists.
# REGISTERED_w16_drift_vwap.md sec 3.4: "written into this file as
# Amendment A ... before the backtest runs." Until that amendment sets
# these, strategy.w16.dvp_runner's --backtest REFUSES to run for the
# market whose constant is still None (see dvp_runner.require_p_ref).
# compute_p_ref() below is what the pre-flight calls to print the number
# that Amendment A then pins here -- it is not read by any P&L path.
# ---------------------------------------------------------------------
P_REF_NQ = None
P_REF_ES = None

TRAIN_START_2020 = "2020-01-02"
TRAIN_END_2023 = "2023-12-29"

C3_THRESHOLD_DEFAULT = 0.001          # 0.10%, registered (sec 3.1, sec 7.4)
STOP_PTS = {"long": 80.0, "short": 80.0}
TARGET_PTS = {"long": 40.0, "short": 50.0}

LOSS_RULES = ("total", "consecutive", None)


def _apply_loss_rule(loss_rule: str | None, gross_pts: float, n_losses: int,
                     consecutive_losses: int) -> tuple[int, int, bool]:
    """One trade's raw-points outcome folded into the G-loss counters (sec
    3.3): a loss (gross_pts < 0) always increments both `n_losses` and
    `consecutive_losses`; a win resets `consecutive_losses` to 0 (and
    never touches `n_losses`, which counts losses ANYWHERE in the
    session). `loss_rule="total"` stops once `n_losses` reaches 2 (Conti's
    literal "max two losses a day"); `"consecutive"` stops once
    `consecutive_losses` reaches 2 (sec 3.3's "two consecutive" reading,
    sec 3.6's reported variant); `None` never stops (sec 3.6's "no
    guardrails" variant). Pulled out as its own pure function -- not
    inlined in `dvp_session`'s loop -- so the "at most 4 trades these
    differ only on a loss-win-loss day" claim (sec 3.3) is a direct,
    session-free unit test (test_drift_vwap.py) rather than something
    only provable by hand-engineering a full session's price path.
    Returns (new_n_losses, new_consecutive_losses, stopped)."""
    if gross_pts < 0:
        n_losses += 1
        consecutive_losses += 1
    else:
        consecutive_losses = 0
    stopped = ((loss_rule == "total" and n_losses >= 2) or
              (loss_rule == "consecutive" and consecutive_losses >= 2))
    return n_losses, consecutive_losses, stopped


# ---------------------------------------------------------------------
# 15-min VWAP and the C1/C2/C3 drift conditions (sec 3.1)
# ---------------------------------------------------------------------

def _vwap_15m(bars15: pd.DataFrame) -> np.ndarray:
    """VWAP_k for every 15-min bar k of one session: cumulative
    typical-price-times-volume over bars 0..k, divided by cumulative
    volume -- sec 3.1's V row, same formula as
    strategy.w16.signals._session_vwap (not imported: that helper is
    private to B3 and takes whatever bar size it's given; this is its own
    small function so a change to B3's VWAP can never silently change
    DVP-v0's)."""
    tp = (bars15["high"].to_numpy() + bars15["low"].to_numpy() + bars15["close"].to_numpy()) / 3.0
    vol = bars15["volume"].to_numpy(dtype=float)
    cum_pv = np.cumsum(tp * vol)
    cum_v = np.cumsum(vol)
    with np.errstate(divide="ignore", invalid="ignore"):
        vwap = np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    return vwap


def _p1h_at(k: int, session_open: float, closes: np.ndarray) -> float | None:
    """P1h_k (sec 3.1): the session's 09:30 open for k == 3 (bar 3 closes
    exactly one hour after the open); close_(k-4) for k >= 4; undefined
    (None) for k <= 2."""
    if k == 3:
        return session_open
    if k >= 4:
        return float(closes[k - 4])
    return None


def drift_states(bars15: pd.DataFrame, session_open: float, *,
                 c3_threshold: float = C3_THRESHOLD_DEFAULT
                 ) -> tuple[list[str | None], np.ndarray]:
    """Per-15-min-bar drift state ("LONG"/"SHORT"/None) for a whole
    session, plus each bar's own close-time-in-minutes-since-midnight
    (for `_drift_state_at`'s lookup). Bars k <= 2 are always None (sec
    3.1: "For k <= 2 the conditions are undefined")."""
    vwap = _vwap_15m(bars15)
    closes = bars15["close"].to_numpy()
    n = len(bars15)
    states: list[str | None] = [None] * n
    for k in range(3, n):
        p1h = _p1h_at(k, session_open, closes)
        if p1h is None or p1h == 0 or np.isnan(vwap[k]) or np.isnan(vwap[k - 1]):
            continue
        close_k = closes[k]
        c3 = close_k / p1h - 1.0
        long_ok = (close_k > vwap[k]) and (vwap[k] > vwap[k - 1]) and (c3 >= c3_threshold)
        short_ok = (close_k < vwap[k]) and (vwap[k] < vwap[k - 1]) and (c3 <= -c3_threshold)
        if long_ok:
            states[k] = "LONG"
        elif short_ok:
            states[k] = "SHORT"
    return states, closes


def _bar_start_minutes(naive_index: pd.DatetimeIndex) -> np.ndarray:
    return (naive_index.hour * 60 + naive_index.minute).to_numpy()


def _drift_close_minutes(naive15: pd.DatetimeIndex, bar_minutes: int = 15) -> np.ndarray:
    return _bar_start_minutes(naive15) + bar_minutes


def _drift_state_at(close_minutes: np.ndarray, states: list[str | None], tau_min: int
                    ) -> str | None:
    """The state of the latest 15-min bar whose close time is <= tau
    (sec 3.1: "The drift state at any moment tau is the state of the
    latest 15-min bar whose close time is <= tau"). `close_minutes` must
    be sorted ascending (true by construction: bars are built in session
    order). A one-minute shift in either array is the look-ahead-guard
    test (test_drift_vwap.py)."""
    pos = bisect.bisect_right(close_minutes.tolist(), tau_min) - 1
    if pos < 0:
        return None
    return states[pos]


# ---------------------------------------------------------------------
# time helpers (sec 3.3's clock-time guardrails)
# ---------------------------------------------------------------------

def dvp_open_time() -> dtime:
    return dtime(10, 30)


def dvp_late_time(date_str: str) -> dtime:
    """Last allowed FILL time: 15:30, or 12:30 on an early-close day (sec
    3.3 G-late)."""
    close = session_close_time(date_str)
    minutes = close.hour * 60 + close.minute - 30        # 16:00 -> 15:30 (and 13:00 -> 12:30)
    return dtime(minutes // 60, minutes % 60)


def dvp_flat_time(date_str: str) -> dtime:
    """Flat-by time: 15:55, or 12:55 on an early-close day (sec 3.3
    G-flat) -- five minutes before the session's own close, same shape as
    strategy.w16.sessions.orb_time_exit's "30 minutes before close"."""
    close = session_close_time(date_str)
    minutes = close.hour * 60 + close.minute - 5
    return dtime(minutes // 60, minutes % 60)


def _t2m(t: dtime) -> int:
    return t.hour * 60 + t.minute


# ---------------------------------------------------------------------
# price scaling (sec 3.4)
# ---------------------------------------------------------------------

def scaled_distance(pts: float, fill_price: float, p_ref: float | None, *,
                    scale: float = 1.0) -> float:
    """`pts` (80/40/50, sec 3.4) scaled by `scale` (sec 7.4 grid), then by
    fill_price/p_ref (sec 3.4's price-scaled mode) unless `p_ref` is None
    (the literal-points mode, sec 3.6/7.3: distances are raw points,
    unscaled by price), then rounded to the nearest 0.25-point tick with a
    1-tick minimum."""
    base = pts * scale
    distance = base if p_ref is None else base * fill_price / p_ref
    ticks = round(distance / TICK)
    ticks = max(ticks, 1)
    return ticks * TICK


# ---------------------------------------------------------------------
# fast vectorised exit walk -- numpy first-hit search, no per-bar python
# loop. Must be byte-identical to
# strategy.w16.signals.walk_stop_target_time_exit on the SAME inputs;
# test_drift_vwap.py proves it on randomised synthetic sessions.
# ---------------------------------------------------------------------

def fast_walk_stop_target_time_exit(minute_of_day: np.ndarray, opens: np.ndarray,
                                    highs: np.ndarray, lows: np.ndarray,
                                    fill_idx: int, direction: str, stop: float,
                                    target: float, exit_minute: int
                                    ) -> tuple[float, str, int, bool]:
    """`minute_of_day`/`opens`/`highs`/`lows`: one session's 1-minute bars
    as plain numpy arrays (precomputed once per session by the caller --
    this function itself does no pandas indexing, which is the whole
    point: the controls call it millions of times). Mirrors
    strategy.w16.signals.walk_stop_target_time_exit bar-for-bar:
    * a bar whose start is >= exit_minute is ALWAYS a time exit at its
      own open, checked BEFORE that bar's own stop/target (so a bar past
      the flat-by time is never also a stop/target bar);
    * otherwise a gap-through stop fills at that bar's open, a
      non-gapped stop fills at the stop level, and the stop wins a
      same-bar tie against the target.
    Returns (exit_price, exit_reason, exit_idx, same_bar_tie) --
    `same_bar_tie` is True iff the exiting bar independently satisfied
    BOTH the stop and the target condition (sec 3.4: "if one bar reaches
    both, the stop wins" -- reported, sec 4 item 3)."""
    n = len(minute_of_day)
    sub = np.arange(fill_idx, n)
    if len(sub) == 0:
        return float(opens[-1]) if n else float("nan"), "data_ended_before_exit", n - 1, False

    mins = minute_of_day[sub]
    if direction == "long":
        hit_stop = lows[sub] <= stop
        hit_target = highs[sub] >= target + TICK
    else:
        hit_stop = highs[sub] >= stop
        hit_target = lows[sub] <= target - TICK

    pre_exit = mins < exit_minute
    combined_hit = pre_exit & (hit_stop | hit_target)
    hit_positions = np.flatnonzero(combined_hit)
    time_positions = np.flatnonzero(~pre_exit)

    first_hit = int(hit_positions[0]) if len(hit_positions) else None
    first_time = int(time_positions[0]) if len(time_positions) else None

    if first_hit is not None and (first_time is None or first_hit < first_time):
        rel = first_hit
        idx = fill_idx + rel
        tie = bool(hit_stop[rel] and hit_target[rel])
        if hit_stop[rel]:
            op = float(opens[idx])
            price = op if _gapped(op, stop, direction) else stop
            return price, "stop", idx, tie
        return float(target), "target", idx, tie

    if first_time is not None:
        idx = fill_idx + first_time
        return float(opens[idx]), "time_exit", idx, False

    return float(opens[-1]), "data_ended_before_exit", n - 1, False


# ---------------------------------------------------------------------
# trigger detection -- shared by the lightweight pre-flight scan and the
# full backtest session function below.
# ---------------------------------------------------------------------

def _trigger_frame(df_session_1m: pd.DataFrame, trigger_minutes: int) -> pd.DataFrame:
    if trigger_minutes == 1:
        return df_session_1m.sort_index()
    return resample_session_bars(df_session_1m, trigger_minutes)


def _drift_frame(df_session_1m: pd.DataFrame) -> pd.DataFrame:
    return resample_session_bars(df_session_1m, 15)


def iter_triggers(df_session_1m: pd.DataFrame, date_str: str, *,
                  trigger_minutes: int = 5, c3_threshold: float = C3_THRESHOLD_DEFAULT):
    """Yield every qualifying trigger in one session, IGNORING position
    state (no re-arm, no G-four, no G-loss -- those need to know whether
    a real trade was open, which only `dvp_session` tracks). Each item:
    (j, direction, fill_idx, fill_price, fill_ts, tau_min). `j` is the
    trigger bar's own positional index (needed by `dvp_session` to walk
    forward from there); `fill_idx` is the SAME positional index into the
    same trigger frame (fill = open of bar j+1, sec 3.2 F), so a caller
    that wants a trade must still fetch bars.iloc[fill_idx]. Used by both
    `dvp_triggers_session` (pre-flight, sec 6.1: "the pre-flight counts
    triggers and first entries per day") and `dvp_session` (backtest)."""
    trig = _trigger_frame(df_session_1m, trigger_minutes)
    if len(trig) < 2:
        return
    drift15 = _drift_frame(df_session_1m)
    if drift15.empty:
        return
    session_open = float(df_session_1m.sort_index()["open"].iloc[0])
    states, closes15 = drift_states(drift15, session_open, c3_threshold=c3_threshold)
    naive15 = _naive_et(drift15)
    close_min15 = _drift_close_minutes(naive15)

    naive_trig = _naive_et(trig)
    trig_start_min = _bar_start_minutes(naive_trig)
    opens = trig["open"].to_numpy()
    closes = trig["close"].to_numpy()

    open_min = _t2m(dvp_open_time())
    late_min = _t2m(dvp_late_time(date_str))

    for j in range(len(trig) - 1):
        tau_min = trig_start_min[j] + trigger_minutes
        if tau_min < open_min or tau_min > late_min:
            continue
        o, c = float(opens[j]), float(closes[j])
        if c == o:
            continue                                    # doji: never a trigger
        color = "red" if c < o else "green"
        state = _drift_state_at(close_min15, states, tau_min)
        if state == "LONG" and color != "red":
            continue
        if state == "SHORT" and color != "green":
            continue
        if state not in ("LONG", "SHORT"):
            continue
        direction = "long" if state == "LONG" else "short"
        fill_idx = j + 1
        fill_price = float(opens[fill_idx])
        fill_ts = trig.index[fill_idx]
        yield j, direction, fill_idx, fill_price, fill_ts, tau_min


def dvp_triggers_session(df_session_1m: pd.DataFrame, date_str: str, *,
                         market: str, trigger_minutes: int = 5,
                         c3_threshold: float = C3_THRESHOLD_DEFAULT) -> dict:
    """G2 pre-flight, no P&L, no re-arm/guardrail state (sec 6.1: entries
    are counted "as if every trade ran to 15:55" -- i.e. every trigger is
    assumed fillable, capped only at G-four's 4/session, never at
    G-loss, which needs an outcome this function never computes). Returns
    {"skipped", "n_triggers", "n_entries_upper_bound" (min(n_triggers,4)),
    "first_direction" (the earliest trigger's direction, or None)}."""
    if not has_valid_open(df_session_1m, window_end=dtime(10, 30)):
        return {"skipped": True, "n_triggers": 0, "n_entries_upper_bound": 0,
               "first_direction": None}
    triggers = list(iter_triggers(df_session_1m, date_str, trigger_minutes=trigger_minutes,
                                  c3_threshold=c3_threshold))
    n = len(triggers)
    first_direction = triggers[0][1] if triggers else None
    return {"skipped": False, "n_triggers": n,
           "n_entries_upper_bound": min(n, 4), "first_direction": first_direction}


# ---------------------------------------------------------------------
# full session backtest (fills, guardrails, exit walk) -- sec 3 end to end
# ---------------------------------------------------------------------

def dvp_session(df_session_1m: pd.DataFrame, date_str: str, *, market: str,
                p_ref: float | None, trigger_minutes: int = 5,
                loss_rule: str | None = "total", scale: float = 1.0,
                c3_threshold: float = C3_THRESHOLD_DEFAULT) -> dict:
    """One session's DVP-v0 trades, end to end: triggers, fills, price-
    scaled stop/target, the 1-minute exit walk, and guardrails G-four/
    G-loss/G-flat (sec 3.2/3.3). `loss_rule`: "total" (registered: stop
    after the 2nd losing trade of the session, and cap at 4 -- sec 3.3
    G-loss/G-four together), "consecutive" (sec 3.6's reported variant:
    stop after 2 CONSECUTIVE losses, cap still 4), or None (sec 3.6's "no
    guardrails" variant: G-four and G-loss are BOTH lifted -- "all
    triggers taken" -- while G-open/G-late/G-one/G-flat still apply,
    exactly as sec 3.6 describes it). Returns {"skipped", "trades": [...]}."""
    if loss_rule not in LOSS_RULES:
        raise ValueError(f"unknown loss_rule {loss_rule!r}; expected one of {LOSS_RULES}")
    if not has_valid_open(df_session_1m, window_end=dtime(10, 30)):
        return {"skipped": True, "trades": []}

    bars1m = df_session_1m.sort_index()
    naive1m = _naive_et(bars1m)
    minute_of_day = _bar_start_minutes(naive1m)
    opens1 = bars1m["open"].to_numpy(dtype=float)
    highs1 = bars1m["high"].to_numpy(dtype=float)
    lows1 = bars1m["low"].to_numpy(dtype=float)
    held = _held_id(bars1m)
    flat_minute = _t2m(dvp_flat_time(date_str))

    trig = _trigger_frame(df_session_1m, trigger_minutes)
    naive_trig = _naive_et(trig)

    next_eligible_start = None            # naive Timestamp; None = anything eligible
    n_entries = 0
    n_losses = 0
    consecutive_losses = 0
    stopped_by_loss = False
    guardrails_on = loss_rule is not None
    trades: list[dict] = []

    for j, direction, fill_idx_trig, fill_price, fill_ts, tau_min in iter_triggers(
            df_session_1m, date_str, trigger_minutes=trigger_minutes, c3_threshold=c3_threshold):
        bar_start = naive_trig[j]
        if next_eligible_start is not None and bar_start < next_eligible_start:
            continue
        if guardrails_on and stopped_by_loss:
            break
        if guardrails_on and n_entries >= 4:
            break

        fill_ts_naive = naive_trig[fill_idx_trig]
        fill_idx_1m = int(np.searchsorted(minute_of_day, tau_min))
        # exact-position lookup (1-min bars are contiguous inside RTH; a
        # session with an internal gap simply has no bar at that minute,
        # which cannot happen at/after 10:30 once has_valid_open passed
        # its own <=5-minute gap check for 09:30-10:30, and any later gap
        # only means searchsorted lands on the next real bar -- still the
        # first bar AT OR AFTER tau, never one before it).
        if fill_idx_1m >= len(bars1m):
            continue

        stop_dist = scaled_distance(STOP_PTS[direction], fill_price, p_ref, scale=scale)
        target_dist = scaled_distance(TARGET_PTS[direction], fill_price, p_ref, scale=scale)
        if direction == "long":
            stop = fill_price - stop_dist
            target = fill_price + target_dist
        else:
            stop = fill_price + stop_dist
            target = fill_price - target_dist

        exit_price, exit_reason, exit_idx, same_bar_tie = fast_walk_stop_target_time_exit(
            minute_of_day, opens1, highs1, lows1, fill_idx_1m, direction, stop, target, flat_minute)

        exit_ts = bars1m.index[exit_idx]
        entry_held = held[fill_idx_1m]
        exit_held = held[exit_idx]
        voided = bool(entry_held != exit_held)

        gross_pts = (exit_price - fill_price) if direction == "long" else (fill_price - exit_price)

        trades.append({
            "date": date_str, "market": market, "baseline": "DVP",
            "direction": direction, "voided": voided,
            "void_reason": ("roll spans the trade (different instrument_id)" if voided else None),
            "trigger_bar_start": str(bar_start), "fill_time": str(fill_ts_naive),
            "fill_price": fill_price, "stop": stop, "target": target,
            "stop_dist": stop_dist, "target_dist": target_dist,
            "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
            "entry_fill_kind": "market_or_stop",
            "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
            "same_bar_tie": same_bar_tie,
        })

        n_entries += 1
        n_losses, consecutive_losses, stopped_by_loss = _apply_loss_rule(
            loss_rule, gross_pts, n_losses, consecutive_losses)

        next_eligible_start = naive1m[exit_idx]

    capped_by_four = bool(guardrails_on and n_entries >= 4)
    return {"skipped": False, "trades": trades, "capped_by_four": capped_by_four,
           "stopped_by_loss": bool(stopped_by_loss)}


# ---------------------------------------------------------------------
# session-list generators -- what strategy.w16.dvp_runner calls
# ---------------------------------------------------------------------

def generate_dvp_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                        p_ref: float | None, trigger_minutes: int = 5,
                        loss_rule: str | None = "total", scale: float = 1.0,
                        c3_threshold: float = C3_THRESHOLD_DEFAULT) -> list[dict]:
    """The full backtest's trade list for one (market, date set): every
    session's `dvp_session` trades, concatenated in date order. `dates`
    need not all be present in `frames` -- a missing date is silently
    skipped (same convention as strategy.w16.runner.generate_b1_trades)."""
    out: list[dict] = []
    for date_str in sorted(str(d) for d in dates):
        if date_str not in frames:
            continue
        res = dvp_session(frames[date_str], date_str, market=market, p_ref=p_ref,
                          trigger_minutes=trigger_minutes, loss_rule=loss_rule,
                          scale=scale, c3_threshold=c3_threshold)
        if res["skipped"]:
            continue
        out.extend(res["trades"])
    return out


def generate_dvp_trades_full(frames: dict[str, pd.DataFrame], market: str, dates, *,
                            p_ref: float | None, trigger_minutes: int = 5,
                            loss_rule: str | None = "total", scale: float = 1.0,
                            c3_threshold: float = C3_THRESHOLD_DEFAULT) -> dict:
    """Like `generate_dvp_trades`, plus the per-day guardrail counts sec 4
    item 3 asks for ("days stopped by G-loss, days capped by G-four") --
    dvp_runner's --backtest calls this instead of the plain trade-list
    generator so it does not have to re-run every session a second time
    just to get those counts."""
    trades: list[dict] = []
    n_sessions = n_skipped = n_capped = n_stopped = 0
    for date_str in sorted(str(d) for d in dates):
        if date_str not in frames:
            continue
        res = dvp_session(frames[date_str], date_str, market=market, p_ref=p_ref,
                          trigger_minutes=trigger_minutes, loss_rule=loss_rule,
                          scale=scale, c3_threshold=c3_threshold)
        if res["skipped"]:
            n_skipped += 1
            continue
        n_sessions += 1
        trades.extend(res["trades"])
        if res.get("capped_by_four"):
            n_capped += 1
        if res.get("stopped_by_loss"):
            n_stopped += 1
    return {"trades": trades, "n_sessions": n_sessions, "n_skipped": n_skipped,
           "n_days_capped_by_four": n_capped, "n_days_stopped_by_loss": n_stopped}


def generate_dvp_triggers(frames: dict[str, pd.DataFrame], market: str, dates, *,
                          trigger_minutes: int = 5,
                          c3_threshold: float = C3_THRESHOLD_DEFAULT) -> dict[str, dict]:
    """{date_str: dvp_triggers_session(...)} for the G2 pre-flight (no
    P&L) -- see dvp_triggers_session's own docstring."""
    out: dict[str, dict] = {}
    for date_str in sorted(str(d) for d in dates):
        if date_str not in frames:
            continue
        out[date_str] = dvp_triggers_session(frames[date_str], date_str, market=market,
                                             trigger_minutes=trigger_minutes,
                                             c3_threshold=c3_threshold)
    return out


# ---------------------------------------------------------------------
# C-D2 (sec 7.2, reported only): "no pullback" -- enter at the next 5-min
# open the instant the drift state TURNS LONG/SHORT, without waiting for
# an opposite-colour candle. Same fill/scaling/walk/guardrail machinery
# as the registered rule; only the trigger condition differs, so this is
# a second trigger source through the SAME per-trade mechanics
# (`iter_triggers` and `dvp_session`'s own loop are not touched).
# ---------------------------------------------------------------------

def iter_state_turns(df_session_1m: pd.DataFrame, date_str: str, *,
                     trigger_minutes: int = 5, c3_threshold: float = C3_THRESHOLD_DEFAULT):
    """Yield one event per session the FIRST time the drift state, read at
    each trigger-bar close, differs from the state read at the PRIOR
    trigger-bar close and is LONG or SHORT (sec 7.2's C-D2: "enter at the
    next 5-min open after the drift state turns ... without waiting for
    an opposite-colour candle"). Same yield shape as `iter_triggers`."""
    trig = _trigger_frame(df_session_1m, trigger_minutes)
    if len(trig) < 2:
        return
    drift15 = _drift_frame(df_session_1m)
    if drift15.empty:
        return
    session_open = float(df_session_1m.sort_index()["open"].iloc[0])
    states, _ = drift_states(drift15, session_open, c3_threshold=c3_threshold)
    naive15 = _naive_et(drift15)
    close_min15 = _drift_close_minutes(naive15)

    naive_trig = _naive_et(trig)
    trig_start_min = _bar_start_minutes(naive_trig)
    opens = trig["open"].to_numpy()

    open_min = _t2m(dvp_open_time())
    late_min = _t2m(dvp_late_time(date_str))

    prev_state: str | None = None
    for j in range(len(trig) - 1):
        tau_min = trig_start_min[j] + trigger_minutes
        state = _drift_state_at(close_min15, states, tau_min)
        turned = state in ("LONG", "SHORT") and state != prev_state
        prev_state = state
        if not turned:
            continue
        if tau_min < open_min or tau_min > late_min:
            continue
        direction = "long" if state == "LONG" else "short"
        fill_idx = j + 1
        fill_price = float(opens[fill_idx])
        fill_ts = trig.index[fill_idx]
        yield j, direction, fill_idx, fill_price, fill_ts, tau_min


def dvp_session_no_pullback(df_session_1m: pd.DataFrame, date_str: str, *, market: str,
                            p_ref: float | None, trigger_minutes: int = 5,
                            loss_rule: str | None = "total", scale: float = 1.0,
                            c3_threshold: float = C3_THRESHOLD_DEFAULT) -> dict:
    """C-D2 (sec 7.2), reported only: identical fill/scaling/walk/
    guardrail mechanics to `dvp_session`, driven by `iter_state_turns`
    instead of `iter_triggers`. Deliberately NOT sharing a loop body with
    `dvp_session` -- see this module's history: that rule is the
    registered, scored one and is not refactored to share code with a
    reported-only variant."""
    if loss_rule not in LOSS_RULES:
        raise ValueError(f"unknown loss_rule {loss_rule!r}; expected one of {LOSS_RULES}")
    if not has_valid_open(df_session_1m, window_end=dtime(10, 30)):
        return {"skipped": True, "trades": []}

    bars1m = df_session_1m.sort_index()
    naive1m = _naive_et(bars1m)
    minute_of_day = _bar_start_minutes(naive1m)
    opens1 = bars1m["open"].to_numpy(dtype=float)
    highs1 = bars1m["high"].to_numpy(dtype=float)
    lows1 = bars1m["low"].to_numpy(dtype=float)
    held = _held_id(bars1m)
    flat_minute = _t2m(dvp_flat_time(date_str))

    trig = _trigger_frame(df_session_1m, trigger_minutes)
    naive_trig = _naive_et(trig)

    next_eligible_start = None
    n_entries = 0
    n_losses = 0
    consecutive_losses = 0
    stopped_by_loss = False
    guardrails_on = loss_rule is not None
    trades: list[dict] = []

    for j, direction, fill_idx_trig, fill_price, fill_ts, tau_min in iter_state_turns(
            df_session_1m, date_str, trigger_minutes=trigger_minutes, c3_threshold=c3_threshold):
        bar_start = naive_trig[j]
        if next_eligible_start is not None and bar_start < next_eligible_start:
            continue
        if guardrails_on and stopped_by_loss:
            break
        if guardrails_on and n_entries >= 4:
            break

        fill_idx_1m = int(np.searchsorted(minute_of_day, tau_min))
        if fill_idx_1m >= len(bars1m):
            continue

        stop_dist = scaled_distance(STOP_PTS[direction], fill_price, p_ref, scale=scale)
        target_dist = scaled_distance(TARGET_PTS[direction], fill_price, p_ref, scale=scale)
        if direction == "long":
            stop = fill_price - stop_dist
            target = fill_price + target_dist
        else:
            stop = fill_price + stop_dist
            target = fill_price - target_dist

        exit_price, exit_reason, exit_idx, same_bar_tie = fast_walk_stop_target_time_exit(
            minute_of_day, opens1, highs1, lows1, fill_idx_1m, direction, stop, target, flat_minute)

        exit_ts = bars1m.index[exit_idx]
        entry_held = held[fill_idx_1m]
        exit_held = held[exit_idx]
        voided = bool(entry_held != exit_held)
        gross_pts = (exit_price - fill_price) if direction == "long" else (fill_price - exit_price)

        trades.append({
            "date": date_str, "market": market, "baseline": "C-D2",
            "direction": direction, "voided": voided,
            "void_reason": ("roll spans the trade (different instrument_id)" if voided else None),
            "trigger_bar_start": str(bar_start), "fill_time": str(naive_trig[fill_idx_trig]),
            "fill_price": fill_price, "stop": stop, "target": target,
            "stop_dist": stop_dist, "target_dist": target_dist,
            "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
            "entry_fill_kind": "market_or_stop",
            "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop",
            "same_bar_tie": same_bar_tie,
        })

        n_entries += 1
        n_losses, consecutive_losses, stopped_by_loss = _apply_loss_rule(
            loss_rule, gross_pts, n_losses, consecutive_losses)
        next_eligible_start = naive1m[exit_idx]

    return {"skipped": False, "trades": trades}


def generate_dvp_no_pullback_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                                    p_ref: float | None, trigger_minutes: int = 5,
                                    loss_rule: str | None = "total", scale: float = 1.0,
                                    c3_threshold: float = C3_THRESHOLD_DEFAULT) -> list[dict]:
    out: list[dict] = []
    for date_str in sorted(str(d) for d in dates):
        if date_str not in frames:
            continue
        res = dvp_session_no_pullback(frames[date_str], date_str, market=market, p_ref=p_ref,
                                      trigger_minutes=trigger_minutes, loss_rule=loss_rule,
                                      scale=scale, c3_threshold=c3_threshold)
        if res["skipped"]:
            continue
        out.extend(res["trades"])
    return out


# ---------------------------------------------------------------------
# P_ref (sec 3.4) -- computed by the pre-flight, pinned by Amendment A
# ---------------------------------------------------------------------

def compute_p_ref(frames: dict[str, pd.DataFrame], market: str) -> float | None:
    """Median of the 09:30 1-minute open over training sessions
    TRAIN_START_2020 (2020-01-02) -> TRAIN_END_2023 (2023-12-29)
    INCLUSIVE, and no session outside that window, ever -- sec 3.4: "It is
    computed by the G2 pre-flight ... 2024 is our holdout and is not
    read." `frames` is {date_str: that date's RTH-windowed 1-minute bars}
    (strategy.w16.preflight.session_frames' own shape); `market` is
    unused by the computation itself (kept for a call-site's symmetry
    with `P_REF_NQ`/`P_REF_ES` and so a future per-market quirk has
    somewhere to live) but every date outside the window is skipped
    regardless of market, so passing a 2024+ frame here is inert by
    construction, not by a filter that could be gotten wrong -- see
    test_drift_vwap.py's "adding a 2024 session does not move it" test."""
    from strategy.w16.readback import local_naive_et
    opens = []
    for date_str in sorted(frames):
        if date_str < TRAIN_START_2020 or date_str > TRAIN_END_2023:
            continue
        day = frames[date_str]
        if day.empty:
            continue
        naive = local_naive_et(day.index)
        mask = naive.time == dtime(9, 30)
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            continue
        opens.append(float(day["open"].to_numpy()[idx[0]]))
    if not opens:
        return None
    return float(np.median(opens))
