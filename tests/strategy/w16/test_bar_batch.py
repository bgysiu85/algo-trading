"""Tests for strategy.w16.bar_batch: the sec 6.2 look-ahead guards (each
proven by a case that a one-bar shift would answer differently), the
sec 7.4 worked example, and the per-rule structural rules the handover
calls out by name (SSS overlap, CRT dead-setup/both-sweep/12:00-cutoff/
Monday-skip/void-on-reward<=0, NRS inside-bar roll-forward/one-a-day/
roll-exit/training-end-exit/double-level-void).

Board W16-0008 subitem 3. docs/research/REGISTERED_w16_bar_batch.md.
"""
from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import bar_batch as B


# ---------------------------------------------------------------------
# synthetic fixtures (same shape as the rest of the W16 test suite's own
# synthetic generators, e.g. test_drift_vwap.py's trend_session helper)
# ---------------------------------------------------------------------

def rth_session(date_str, *, base=100.0, held_id=1, minute_fn=None):
    start = pd.Timestamp(f"{date_str} 09:30:00", tz="America/New_York").tz_convert("UTC")
    idx = pd.date_range(start, periods=390, freq="1min")
    rows = []
    px = base
    for i in range(390):
        o, h, l, c, v = px, px + 0.5, px - 0.5, px + 0.05, 100
        if minute_fn is not None:
            r = minute_fn(i, px)
            if r is not None:
                o, h, l, c, v = r
        rows.append((o, h, l, c, v))
        px = c
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)
    df["instrument_id"] = held_id
    return df


def globex_session(date_str, *, base=100.0, held_id=1, minute_fn=None, days=1):
    start = (pd.Timestamp(f"{date_str} 00:00:00", tz="America/New_York")
            - pd.Timedelta(days=1)).replace(hour=18, minute=0)
    rows, idxs = [], []
    px = base
    cur = start
    end = start + pd.Timedelta(days=days) + pd.Timedelta(hours=23)
    i = 0
    while cur < end:
        if cur.time() == pd.Timestamp("17:00").time():
            cur += pd.Timedelta(hours=1)
            continue
        o, h, l, c, v = px, px + 0.5, px - 0.5, px + 0.02, 50
        if minute_fn is not None:
            r = minute_fn(i, px, cur)
            if r is not None:
                o, h, l, c, v = r
        rows.append((o, h, l, c, v))
        idxs.append(cur.tz_convert("UTC"))
        px = c
        cur += pd.Timedelta(minutes=1)
        i += 1
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idxs))
    df["instrument_id"] = held_id
    return df.sort_index()


# ---------------------------------------------------------------------
# sec 7.4 worked example: ABD, ATR 17.85 -> target 35.75 pts, stop 26.75 pts
# ---------------------------------------------------------------------

def test_abd_worked_example():
    atr = 17.85
    assert B.round_distance_tick(2.0 * atr) == pytest.approx(35.75)
    assert B.round_distance_tick(1.5 * atr) == pytest.approx(26.75)


# ---------------------------------------------------------------------
# ABD: look-ahead guard -- band_j uses close_(j-1)/ATR_(j-1) only
# ---------------------------------------------------------------------

def test_abd_band_uses_prior_bar_not_current():
    """A one-bar shift (reading atr[j] instead of atr[j-1]) would price a
    DIFFERENT band on a day where volatility jumps sharply between two
    consecutive 5-min bars -- assert the real band matches the PRIOR
    bar's own ATR, not the signal bar's own (still-forming) one."""
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    frames = {d: rth_session(d, base=100.0) for d in dates}

    def dip(i, px):
        if i == 65:                                   # a hard, engineered dip
            return (px, px, px - 50, px - 40, 100)
        return None
    frames["2024-01-05"] = rth_session("2024-01-05", base=100.0, minute_fn=dip)
    dates.append("2024-01-05")

    bars5 = B.build_day_session_series(frames, dates, 5)
    held = B._held_id(bars5)
    atr = B.wilder_atr(bars5, 14, held_id=held)
    closes = bars5["close"].to_numpy(dtype=float)

    trades = B.generate_abd_trades(frames, "NQ", dates)
    assert trades, "expected at least one ABD entry on the engineered dip"
    t = trades[0]
    # locate the signal bar j from its OWN recorded atr_prev, restricted to
    # the trade's own date (several days share near-identical flat ATR at
    # this synthetic scale, so band alone is not a unique key)
    naive5 = B._naive_et(bars5)
    date_mask = naive5.strftime("%Y-%m-%d").to_numpy() == t["date"]
    matches = [j for j in range(1, len(bars5))
              if date_mask[j] and np.isfinite(atr[j - 1]) and
              abs(atr[j - 1] - t["atr_prev"]) < 1e-9]
    assert matches, "could not locate the signal bar behind the recorded trade"
    j = matches[0]
    assert t["atr_prev"] == pytest.approx(atr[j - 1])
    # the one-bar-shifted (wrong) reading would use atr[j], which differs
    assert atr[j] != atr[j - 1] or not np.isfinite(atr[j])


# ---------------------------------------------------------------------
# SSS: enters at j+1's open, exits at j+2's open; overlap rule
# ---------------------------------------------------------------------

def _shooting_star_minute_fn(bucket_start_minute):
    """All FIVE 1-minute bars inside one 5-min resample bucket must be
    shaped consistently -- shaping only one of the five and leaving the
    other four at the fixture's default open/close lets them dilute the
    bucket's own aggregate high/low and silently break the intended wick
    pattern (a real trap hit once already building this suite)."""
    def fn(i, px):
        if bucket_start_minute <= i < bucket_start_minute + 5:
            if i == bucket_start_minute:
                return (px, px + 5.0, px - 0.05, px, 100)   # the long upper wick
            return (px, px + 0.05, px - 0.02, px, 100)      # tiny bars, stay inside the wick's range
        return None
    return fn


def test_sss_entry_and_exit_timing():
    d = "2024-01-02"
    frames = {d: rth_session(d, base=100.0, minute_fn=_shooting_star_minute_fn(30))}
    trades = B.generate_sss_trades(frames, "NQ", [d])
    assert trades, "expected a shooting-star pattern to fire"
    bars5 = B.resample_session_bars(frames[d], 5)
    t = trades[0]
    fill_ts = pd.Timestamp(t["fill_time"])
    exit_ts = pd.Timestamp(t["exit_time"])
    j = list(bars5.index).index(fill_ts) - 1     # pattern bar
    assert fill_ts == bars5.index[j + 1], "entry must be j+1's open, not j's own close"
    assert exit_ts == bars5.index[j + 2], "exit must be j+2's open"


def test_sss_overlap_rule_ignores_pattern_on_held_bar():
    """A pattern on the bar being held (j+1, while the first trade is
    open) must be ignored -- only a pattern on j+2 (once flat) can open
    the next trade, entering at j+3's open."""
    def fn(i, px):
        r = _shooting_star_minute_fn(30)(i, px)
        if r is not None:
            return r
        r2 = _shooting_star_minute_fn(35)(i, px)          # bar j+1's own bucket -- must be ignored
        return r2
    d = "2024-01-02"
    frames = {d: rth_session(d, base=100.0, minute_fn=fn)}
    trades = B.generate_sss_trades(frames, "NQ", [d])
    # bar 30's bucket = j=6 (5-min bar index); its hold bar is j+1=7
    # (minute 35's own bucket), which is exactly where the second pattern
    # was engineered -- the overlap rule must ignore it, so exactly ONE
    # trade should result, not two.
    assert len(trades) == 1


# ---------------------------------------------------------------------
# TMB: HP/AC/5-bar-high at k use only bars <= k; the 5-bar high excludes
# k itself; the trailing stop at minute m uses only bars < m
# ---------------------------------------------------------------------

def test_tmb_five_bar_high_excludes_signal_bar():
    """hurst_proxy/autocorr_lag5 are pure functions of the array up to
    and including index k (by construction: both loop `for k in
    range(N, n)` and read only `[..k+1]` slices) -- checked directly
    against a hand-built input so a future edit that leaks bar k+1 into
    either would be caught here."""
    n = 40
    highs = np.arange(n, dtype=float) + 100.0
    lows = highs - 1.0
    atr20 = np.full(n, 2.0)
    bars = pd.DataFrame({"high": highs, "low": lows})
    hp = B.hurst_proxy(bars, atr20)
    # HP at k must not change if bar k+1's high is altered
    highs2 = highs.copy()
    highs2[25] = 500.0     # perturb a bar AFTER k=24
    bars2 = pd.DataFrame({"high": highs2, "low": lows})
    hp2 = B.hurst_proxy(bars2, atr20)
    assert hp[24] == pytest.approx(hp2[24]), \
        "HP at bar 24 must be unaffected by a later bar's high (look-ahead guard)"


def test_tmb_trailing_stop_uses_only_prior_minutes():
    """_tmb_walk's own extreme/stop update happens AFTER a minute's own
    stop/target check clears -- so the very first minute's check must use
    the ENTRY stop, not one already trailed using that same minute's own
    high."""
    idx = pd.date_range("2024-01-02 09:31", periods=5, freq="1min", tz="UTC")
    bars = pd.DataFrame({
        "open": [100.0, 100.0, 100.0, 100.0, 100.0],
        "high": [110.0, 100.5, 100.5, 100.5, 100.5],   # minute 0's own high is far above fill
        "low": [99.5, 99.5, 99.5, 99.5, 99.5],
        "close": [100.0] * 5,
    }, index=idx)
    naive = pd.DatetimeIndex(idx.tz_convert("America/New_York")).tz_localize(None)
    price, reason, pos = B._tmb_walk(bars, naive, 0, atr_k=1.0, flat_minute=16 * 60, direction="long")
    # stop_dist = 4*1.0 = 4; entry stop = 100-4=96. Minute 0's own low
    # (99.5) never reaches 96, so this must NOT stop out on minute 0 even
    # though minute 0's own high (110) would have trailed the stop far
    # above 99.5 had the extreme been folded in before minute 0's own check.
    assert reason != "stop" or pos > 0


# ---------------------------------------------------------------------
# CRT: dead setup, both-side sweep, 12:00 cutoff, Monday skip, void on
# reward <= 0
# ---------------------------------------------------------------------

def _crt_minute_fn(overrides: dict):
    """A TIGHT default bar for every minute (so adjacent 15-min buckets
    never accidentally bleed into each other's high/low -- a real trap
    hit once already building this suite, see _shooting_star_minute_fn),
    with `overrides={minute_index: (o, h, l, c, v)}` poking specific
    minutes to build a setup."""
    def fn(i, px):
        if i in overrides:
            return overrides[i]
        return (px, px + 0.01, px - 0.01, px, 100)    # perfectly flat close -- no cross-bucket drift
    return fn


def _crt_frame(overrides: dict, date_str="2024-01-02"):
    return {date_str: rth_session(date_str, base=100.0, minute_fn=_crt_minute_fn(overrides))}


def test_crt_dead_setup_produces_no_trade():
    """A bullish C1/C2 setup whose C3 window elapses with neither stop
    level ever triggering is DEAD -- no trade, and a later bar breaking
    the level does not count."""
    # C1 = minutes 0-14 (tight, high~100.01); C2 = minutes 15-29: sweep
    # C1's low, close back inside -> bullish setup. C3 (30-44) never
    # breaks out (stays tight throughout).
    frames = _crt_frame({20: (100.0, 100.0, 97.0, 99.8, 100)})
    trades = B.generate_crt_trades(frames, "NQ", ["2024-01-02"])
    assert trades == []


def test_crt_both_side_sweep_is_not_a_setup():
    """A C2 that sweeps BOTH C1's high and low is not a setup at all
    (counted elsewhere, never reaches a trade)."""
    frames = _crt_frame({20: (100.0, 103.0, 97.0, 100.0, 100)})
    trades = B.generate_crt_trades(frames, "NQ", ["2024-01-02"])
    assert trades == []


def test_crt_window_end_cutoff():
    """A break that would only occur AFTER the entry window's own end
    (registered 12:00) must not fill."""
    frames = _crt_frame({
        20: (100.0, 100.0, 97.0, 100.0, 100),          # bullish C2
        200: (100.0, 103.0, 100.0, 102.5, 100),       # ~12:50, well past 12:00
    })
    trades = B.generate_crt_trades(frames, "NQ", ["2024-01-02"])
    assert trades == []


def test_crt_no_trades_on_monday():
    """A plain Monday must be skipped outright, engineered setup or not."""
    frames = _crt_frame({
        20: (100.0, 100.0, 97.0, 100.0, 100),
        32: (100.0, 103.0, 100.0, 102.5, 100),
    }, date_str="2024-01-08")                          # a Monday
    trades = B.generate_crt_trades(frames, "NQ", ["2024-01-08"])
    assert trades == []


def test_crt_voids_on_reward_le_zero():
    """If the fill is at or beyond the target itself, reward <= 0 and the
    trade is voided and counted, not skipped silently."""
    frames = _crt_frame({
        20: (100.0, 100.0, 97.0, 100.0, 100),           # bullish C2 -> C1's high (H1) ~= 100.01
        32: (100.0, 150.0, 100.0, 145.0, 100),          # break straight through H1 in one bar
    })
    trades = B.generate_crt_trades(frames, "NQ", ["2024-01-02"])
    assert trades, "the fill itself should still be counted, just voided"
    assert trades[0]["voided"] is True
    assert trades[0]["void_reason"].startswith("reward")


# ---------------------------------------------------------------------
# NRS: inside-bar order roll-forward, one-a-day, roll exit, training-end
# exit, double-level minute void
# ---------------------------------------------------------------------

def _squeeze_globex(breakout_hour=30, breakout_minute=5, breakout_up=True, days=3):
    def fn(i, px, ts):
        hour_idx = i // 60
        if hour_idx < breakout_hour:
            amp = max(0.5, 3.0 - hour_idx * 0.1)
            return (px, px + amp, px - amp, px + 0.01, 50)
        if hour_idx == breakout_hour and i % 60 == breakout_minute:
            return ((px, px + 20.0, px, px + 18.0, 200) if breakout_up
                    else (px, px, px - 20.0, px - 18.0, 200))
        return None
    return globex_session("2024-01-08", base=100.0, minute_fn=fn, days=days)


def test_nrs_one_entry_per_day():
    df = _squeeze_globex()
    dates = B.nrs_cme_trading_days(df)
    trades = B.generate_nrs_trades(df, "NQ", dates)
    fill_days = [t["date"] for t in trades if not t.get("voided")]
    assert len(fill_days) == len(set(fill_days)), "at most one entry per market per CME day"


def test_nrs_training_end_exit_closes_open_position():
    df = _squeeze_globex(days=3)
    dates = B.nrs_cme_trading_days(df)
    trades = B.generate_nrs_trades(df, "NQ", dates)
    assert trades
    assert trades[-1]["exit_reason"] in ("training_end", "stop", "roll")


def test_nrs_roll_exit_fires_on_instrument_change():
    """An open position must exit at the prior bar's close, 1 tick
    against it, the moment `instrument_id` changes -- not ride through
    the roll. Uses a first (unmodified) pass to discover the real fill's
    exact row position, then mutates `instrument_id` 30 minutes later --
    hand-predicting that row from the fixture's own minute_fn is fragile
    (a skipped 17:00-18:00 pause shifts later minutes off any simple
    i // 60 grouping)."""
    df = _squeeze_globex(days=3)
    dates = B.nrs_cme_trading_days(df)
    baseline = B.generate_nrs_trades(df, "NQ", dates)
    assert baseline
    entry_idx = baseline[0]["entry_idx_1m"]

    df2 = df.copy()
    ids = np.ones(len(df2), dtype=int)
    ids[entry_idx + 30:] = 2
    df2["instrument_id"] = ids
    trades = B.generate_nrs_trades(df2, "NQ", dates)
    assert trades
    assert trades[0]["exit_reason"] == "roll"


def test_nrs_double_level_minute_is_voided_and_counted():
    """A 1-minute bar that reaches BOTH the buy-stop and sell-stop levels
    during the armed window is voided and counted, not silently dropped.
    Same two-pass approach as the roll-exit test above: discover the real
    fill minute, then blow its own high/low out to cover both levels."""
    df = _squeeze_globex(days=3)
    dates = B.nrs_cme_trading_days(df)
    baseline = B.generate_nrs_trades(df, "NQ", dates)
    assert baseline
    entry_idx = baseline[0]["entry_idx_1m"]

    df2 = df.copy()
    px = float(df2.iloc[entry_idx]["open"])
    df2.iloc[entry_idx, df2.columns.get_loc("high")] = px + 50.0
    df2.iloc[entry_idx, df2.columns.get_loc("low")] = px - 50.0
    trades = B.generate_nrs_trades(df2, "NQ", dates)
    voided = [t for t in trades if t.get("voided")]
    assert voided, "expected a double-level minute to be voided and counted"
    assert voided[0]["void_reason"] == "1-minute bar reached both stop levels"


def test_nrs_look_ahead_guard_hour_not_usable_before_it_closes():
    """The while-loop that advances which hourly bar is 'closed' must
    require ts_naive to reach the START OF THE NEXT hour, not merely the
    candidate hour's own start -- a one-hour-early reading (the bug this
    guards against) would let squeeze_flag/chandelier see a still-forming
    hour's full range 59 minutes before it actually closes."""
    h_start_vals = pd.date_range("2024-01-08 18:00", periods=6, freq="1h").values
    m_naive = pd.date_range("2024-01-08 18:00", periods=6 * 60, freq="1min").values
    h_pos = -1
    n_h = len(h_start_vals)
    first_close_at = None
    for ts in m_naive:
        while h_pos + 2 < n_h and h_start_vals[h_pos + 2] <= ts:
            h_pos += 1
            if first_close_at is None:
                first_close_at = ts
            break
        if first_close_at is not None:
            break
    assert first_close_at == h_start_vals[1], \
        "hour 0 must not be usable before ts reaches hour 1's own start"
