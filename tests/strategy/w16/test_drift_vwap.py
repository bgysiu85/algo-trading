#!/usr/bin/env python3
"""DVP-v0 (Conti drift-VWAP pullback, W16-0006): VWAP/C1-C3, P1h at k=3 vs
k>=4, the drift-state look-ahead guard, trigger colour/doji, fill timing
(10:30 earliest, 15:30 last, 15:55 flat, early closes), price scaling and
tick rounding, literal-points mode, guardrails (G-four, G-loss total vs
consecutive, re-arm), the fast walk's equivalence to
strategy.w16.signals.walk_stop_target_time_exit, and compute_p_ref's
training-window discipline. REGISTERED_w16_drift_vwap.md sec 2/3/6."""
from __future__ import annotations

from datetime import time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

import strategy.w16.drift_vwap as D
import strategy.w16.signals as SIG

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------
# session builders shared by the integration-style tests below
# ---------------------------------------------------------------------

def _clock_add(hh: int, mm: int, n: int = 1) -> tuple[int, int]:
    mm += n
    hh += mm // 60
    mm %= 60
    return hh, mm


def _expand(clock: str, n: int) -> list[str]:
    hh, mm = int(clock[:2]), int(clock[3:])
    out = []
    for _ in range(n):
        out.append(f"{hh:02d}:{mm:02d}")
        hh, mm = _clock_add(hh, mm)
    return out


def _bars_from_rows(date, rows, held_id=1):
    idx, data = [], []
    for hh, mm, o, h, l, c, v in rows:
        ts = pd.Timestamp(f"{date} {hh:02d}:{mm:02d}:00", tz=ET)
        idx.append(ts)
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": v,
                    "held_id": held_id})
    return pd.DataFrame(data, index=pd.DatetimeIndex(idx).tz_convert("UTC"))


def trend_session(date, *, direction="long", slope=1.0, start_price=15000.0,
                  events=(), dip_windows=(), dip_size=6.0, held_id=1,
                  close_time=(16, 0)):
    """A full RTH (or early-close) session, one minute at a time, built
    from a steady per-minute drift (`slope`, signed by `direction`) that
    reliably qualifies C1-C3 LONG/SHORT by 15-min bar 3 (10:30) and stays
    qualified all day, PLUS optional overrides:
    * `dip_windows`: 5-min-window start clocks that become a clean
      AGAINST-the-trend 5-min candle (a red pullback in an uptrend, a
      green one in a downtrend) -- `-dip_size` spread evenly over those 5
      minutes, so the trigger candle's aggregated open/close disagree with
      the trend regardless of `slope` (a single against-trend MINUTE
      inside an otherwise-5-min-bar can still net the "wrong" colour once
      resampled -- this does not).
    * `events`: (start_clock, n_minutes, per_minute_drift) overrides for
      an explicit stretch (a trigger candle, or a sharp reversal to force
      a stop-loss outcome on a specific trade) -- `dip_windows` is sugar
      for a 5-minute against-trend `events` entry.
    """
    sign = 1.0 if direction == "long" else -1.0
    override = {}
    for w in dip_windows:
        for clk in _expand(w, 5):
            override[clk] = -sign * (dip_size / 5.0)
    for start, n, drift in events:
        for clk in _expand(start, n):
            override[clk] = drift
    rows = []
    price = start_price
    hh, mm = 9, 30
    while (hh, mm) < close_time:
        clock = f"{hh:02d}:{mm:02d}"
        o = price
        d = override.get(clock, sign * slope)
        c = o + d
        h = max(o, c) + 0.05
        l = min(o, c) - 0.05
        rows.append((hh, mm, o, h, l, c, 100))
        price = c
        hh, mm = _clock_add(hh, mm)
    return _bars_from_rows(date, rows, held_id=held_id)


DATE = "2024-06-06"                     # an ordinary RTH day
EARLY_CLOSE_DATE = "2018-07-03"         # from sessions.EARLY_CLOSES_2010_2025


def _gross_of(t: dict) -> float:
    return (t["exit_price"] - t["fill_price"]) if t["direction"] == "long" \
        else (t["fill_price"] - t["exit_price"])


# ---------------------------------------------------------------------
# hand-computed VWAP / C1-C3 / P1h
# ---------------------------------------------------------------------

def test_vwap_15m_hand_computed():
    """5 bars, all typical == close (H=L=C), so VWAP is a plain volume-
    weighted average of the closes -- hand-checkable directly."""
    bars15 = pd.DataFrame({
        "open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "high": [100.0, 101.0, 102.0, 103.0, 104.0],
        "low": [100.0, 101.0, 102.0, 103.0, 104.0],
        "close": [100.0, 101.0, 102.0, 103.0, 104.0],
        "volume": [100.0, 100.0, 100.0, 200.0, 100.0],
    })
    vwap = D._vwap_15m(bars15)
    # VWAP_2 = (100*100 + 101*100 + 102*100) / 300 = 101.0
    assert vwap[2] == pytest.approx(101.0)
    # VWAP_3 = (10000+10100+10200 + 103*200) / 500 = (30300+20600)/500 = 101.8
    assert vwap[3] == pytest.approx(101.8)


def test_c1_c2_c3_on_a_hand_computed_bar():
    """sec 3.1's V/C1/C2/C3 evaluated on one concrete 15-min bar 3, against
    hand-computed VWAP_2/VWAP_3 and P1h_3 = the session open."""
    bars15 = pd.DataFrame({
        "open": [100.0, 100.5, 101.0, 102.0],
        "high": [100.5, 101.0, 102.0, 103.0],
        "low": [100.0, 100.5, 101.0, 102.0],
        "close": [100.5, 101.0, 102.0, 103.0],
        "volume": [150.0, 150.0, 150.0, 150.0],
    })
    session_open = 100.0
    states, closes = D.drift_states(bars15, session_open)
    vwap = D._vwap_15m(bars15)
    # typical == close for every bar here (H=L=C given by construction
    # above is not quite true -- H/L differ from C -- so recompute by hand
    # via the same formula the function itself uses, and just check C1/C2
    # against that, plus C3 against the KNOWN P1h=session_open):
    assert D._p1h_at(3, session_open, closes) == pytest.approx(100.0)
    c3 = closes[3] / 100.0 - 1.0
    assert c3 == pytest.approx(0.03)                    # 103/100 - 1
    assert closes[3] > vwap[3]                          # C1
    assert vwap[3] > vwap[2]                             # C2
    assert states[3] == "LONG"                           # all three hold


def test_p1h_uses_session_open_at_k3_and_bar_close_at_k_ge_4():
    closes = np.array([100.5, 101.0, 102.0, 103.0, 104.0, 105.0])
    session_open = 99.0
    assert D._p1h_at(3, session_open, closes) == pytest.approx(99.0)        # session open, NOT close_(-1)
    assert D._p1h_at(4, session_open, closes) == pytest.approx(closes[0])   # close_(4-4)
    assert D._p1h_at(5, session_open, closes) == pytest.approx(closes[1])   # close_(5-4)
    assert D._p1h_at(2, session_open, closes) is None
    assert D._p1h_at(0, session_open, closes) is None


def test_drift_state_undefined_below_k3():
    bars15 = pd.DataFrame({
        "open": [100.0] * 4, "high": [101.0] * 4, "low": [99.0] * 4,
        "close": [100.5, 101.0, 101.5, 110.0], "volume": [100.0] * 4,
    })
    states, _ = D.drift_states(bars15, session_open=100.0)
    assert states[0] is None and states[1] is None and states[2] is None


# ---------------------------------------------------------------------
# look-ahead guard (sec 6.2): a one-minute shift in a bar's close time
# must change the drift state read at a fixed tau.
# ---------------------------------------------------------------------

def test_drift_state_lookahead_guard_one_minute_shift_breaks_it():
    close_minutes = np.array([945, 960, 975, 990])       # bar k's CLOSE times
    states = [None, None, None, "LONG"]
    tau = 990
    assert D._drift_state_at(close_minutes, states, tau) == "LONG"
    # shift bar 3's close ONE MINUTE past tau -- it must no longer be visible
    shifted = close_minutes.copy()
    shifted[3] = 991
    assert D._drift_state_at(shifted, states, tau) is None


def test_drift_state_at_never_reads_a_bar_before_its_own_close():
    close_minutes = np.array([945, 960, 975, 990, 1005])
    states = [None, None, None, "LONG", "SHORT"]
    assert D._drift_state_at(close_minutes, states, 989) is None   # bar 3 not yet closed
    assert D._drift_state_at(close_minutes, states, 990) == "LONG"  # closes exactly at tau
    assert D._drift_state_at(close_minutes, states, 1004) == "LONG"
    assert D._drift_state_at(close_minutes, states, 1005) == "SHORT"


def test_p_ref_lookahead_guard_2024_session_never_moves_it():
    frames = {}
    for i, day in enumerate(("2020-01-02", "2021-06-01", "2023-12-29")):
        idx = pd.date_range(f"{day} 09:30", periods=3, freq="1min", tz=ET).tz_convert("UTC")
        frames[day] = pd.DataFrame({"open": [15000.0 + i, 0, 0], "high": [0.0] * 3,
                                    "low": [0.0] * 3, "close": [0.0] * 3,
                                    "volume": [1.0] * 3}, index=idx)
    before = D.compute_p_ref(frames, "NQ")
    idx2024 = pd.date_range("2024-03-04 09:30", periods=3, freq="1min", tz=ET).tz_convert("UTC")
    frames["2024-03-04"] = pd.DataFrame({"open": [999999.0, 0, 0], "high": [0.0] * 3,
                                         "low": [0.0] * 3, "close": [0.0] * 3,
                                         "volume": [1.0] * 3}, index=idx2024)
    after = D.compute_p_ref(frames, "NQ")
    assert before == after
    assert before == pytest.approx(np.median([15000.0, 15001.0, 15002.0]))


def test_p_ref_excludes_2019_session_too():
    frames = {}
    idx19 = pd.date_range("2019-12-31 09:30", periods=1, freq="1min", tz=ET).tz_convert("UTC")
    frames["2019-12-31"] = pd.DataFrame({"open": [1.0], "high": [0.0], "low": [0.0],
                                         "close": [0.0], "volume": [1.0]}, index=idx19)
    idx20 = pd.date_range("2020-01-02 09:30", periods=1, freq="1min", tz=ET).tz_convert("UTC")
    frames["2020-01-02"] = pd.DataFrame({"open": [5000.0], "high": [0.0], "low": [0.0],
                                         "close": [0.0], "volume": [1.0]}, index=idx20)
    assert D.compute_p_ref(frames, "NQ") == pytest.approx(5000.0)


# ---------------------------------------------------------------------
# tick rounding / price scaling (sec 3.4) and literal mode (sec 3.6/7.3)
# ---------------------------------------------------------------------

def test_scaled_distance_price_scaled_mode():
    # fill == p_ref -> distance == raw points, tick-exact
    assert D.scaled_distance(80.0, 15000.0, 15000.0) == pytest.approx(80.0)
    assert D.scaled_distance(40.0, 15000.0, 15000.0) == pytest.approx(40.0)


def test_scaled_distance_rounds_to_nearest_tick_with_one_tick_minimum():
    # 80 * 100/15000 = 0.5333... -> nearest 0.25 tick = 0.5
    assert D.scaled_distance(80.0, 100.0, 15000.0) == pytest.approx(0.5)
    # a distance that rounds to 0 ticks is floored up to the 1-tick minimum
    assert D.scaled_distance(80.0, 1.0, 15000.0) == pytest.approx(D.TICK)


def test_scaled_distance_literal_mode_ignores_fill_price():
    assert D.scaled_distance(80.0, 9999.0, None) == pytest.approx(80.0)
    assert D.scaled_distance(50.0, 1.0, None) == pytest.approx(50.0)


def test_scaled_distance_grid_multiplier_applies_before_scaling():
    assert D.scaled_distance(40.0, 15000.0, 15000.0, scale=0.75) == pytest.approx(30.0)
    assert D.scaled_distance(40.0, 15000.0, 15000.0, scale=1.25) == pytest.approx(50.0)


# ---------------------------------------------------------------------
# fast vectorised walk == strategy.w16.signals.walk_stop_target_time_exit
# ---------------------------------------------------------------------

def test_fast_walk_matches_shared_walk_on_randomised_sessions():
    rng = np.random.default_rng(42)
    mismatches = 0
    for _ in range(300):
        n = int(rng.integers(5, 60))
        idx = pd.date_range(f"{DATE} 09:30", periods=n, freq="1min", tz=ET).tz_convert("UTC")
        walk = np.cumsum(rng.normal(0, 0.3, n))
        close = 100 + walk
        open_ = np.concatenate([[100.0], close[:-1]])
        high = np.maximum(open_, close) + rng.uniform(0, 0.6, n)
        low = np.minimum(open_, close) - rng.uniform(0, 0.6, n)
        df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                          "volume": 100, "held_id": 1}, index=idx)
        naive = SIG._naive_et(df)
        minute_of_day = (naive.hour * 60 + naive.minute).to_numpy()
        fill_idx = int(rng.integers(0, n))
        direction = "long" if rng.random() < 0.5 else "short"
        fill_price = float(open_[fill_idx])
        stop_dist = float(rng.uniform(0.2, 2.0))
        target_dist = float(rng.uniform(0.2, 2.0))
        if direction == "long":
            stop, target = fill_price - stop_dist, fill_price + target_dist
        else:
            stop, target = fill_price + stop_dist, fill_price - target_dist
        exit_minute = 9 * 60 + 30 + int(n // 2)

        slow_price, slow_reason = SIG.walk_stop_target_time_exit(
            df, naive, fill_idx, direction, stop, target, dtime(exit_minute // 60, exit_minute % 60))
        fast_price, fast_reason, _, _ = D.fast_walk_stop_target_time_exit(
            minute_of_day, open_, high, low, fill_idx, direction, stop, target, exit_minute)
        if not (abs(slow_price - fast_price) < 1e-9 and slow_reason == fast_reason):
            mismatches += 1
    assert mismatches == 0


def test_fast_walk_reports_same_bar_tie_when_stop_and_target_both_hit():
    minute_of_day = np.array([600, 601])
    opens = np.array([100.0, 100.0])
    highs = np.array([100.0, 106.0])                   # bar 1 spans stop and target
    lows = np.array([100.0, 94.0])
    price, reason, idx, tie = D.fast_walk_stop_target_time_exit(
        minute_of_day, opens, highs, lows, 0, "long", stop=95.0, target=105.0, exit_minute=1000)
    assert reason == "stop"                              # sec 3.4: stop wins the tie
    assert tie is True


def test_fast_walk_no_tie_when_only_target_hit():
    minute_of_day = np.array([600, 601])
    opens = np.array([100.0, 100.0])
    highs = np.array([100.0, 106.0])
    lows = np.array([100.0, 101.0])
    price, reason, idx, tie = D.fast_walk_stop_target_time_exit(
        minute_of_day, opens, highs, lows, 0, "long", stop=95.0, target=105.0, exit_minute=1000)
    assert reason == "target" and tie is False


# ---------------------------------------------------------------------
# G-loss helper (sec 3.3): total vs consecutive, the loss-win-loss day
# ---------------------------------------------------------------------

def test_apply_loss_rule_total_stops_on_two_losses_anywhere():
    n, c = 0, 0
    for gross in (-5.0, 5.0, -5.0):                       # loss, win, loss
        n, c, stopped = D._apply_loss_rule("total", gross, n, c)
    assert (n, c, stopped) == (2, 1, True)


def test_apply_loss_rule_consecutive_needs_two_in_a_row():
    n, c = 0, 0
    for gross in (-5.0, 5.0, -5.0):                       # loss, win, loss -- never consecutive
        n, c, stopped = D._apply_loss_rule("consecutive", gross, n, c)
    assert stopped is False
    n2, c2, stopped2 = D._apply_loss_rule("consecutive", -1.0, n, c)  # a genuine 2nd in a row
    assert stopped2 is True


def test_apply_loss_rule_none_never_stops():
    n, c = 0, 0
    for gross in (-5.0, -5.0, -5.0, -5.0):
        n, c, stopped = D._apply_loss_rule(None, gross, n, c)
    assert stopped is False


# ---------------------------------------------------------------------
# trigger colour, doji, fill timing
# ---------------------------------------------------------------------

def test_long_trigger_fires_on_red_candle_and_fills_at_next_bar_open():
    df = trend_session(DATE, direction="long", dip_windows=["10:35"])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["direction"] == "long"
    assert t["fill_time"] == "2024-06-06 10:40:00"       # next 5-min bar's open


def test_short_trigger_fires_on_green_candle_in_a_downtrend():
    df = trend_session(DATE, direction="short", dip_windows=["10:35"])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["direction"] == "short"


def test_doji_is_never_a_trigger():
    """The would-be trigger window has open == close (a doji) -- LONG
    drift is otherwise qualified, and must NOT fire."""
    df = trend_session(DATE, direction="long", events=[("10:35", 5, 0.0)])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert res["trades"] == []


def test_earliest_fill_is_1030_using_bar_3s_own_close():
    df = trend_session(DATE, direction="long", dip_windows=["10:25"])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["fill_time"] == "2024-06-06 10:30:00"


def test_last_allowed_fill_is_1530_and_1535_is_refused():
    included = trend_session(DATE, direction="long", dip_windows=["15:25"])
    res_in = D.dvp_session(included, DATE, market="NQ", p_ref=15000.0)
    assert any(t["fill_time"] == "2024-06-06 15:30:00" for t in res_in["trades"])

    excluded = trend_session(DATE, direction="long", dip_windows=["15:30"])
    res_out = D.dvp_session(excluded, DATE, market="NQ", p_ref=15000.0)
    assert all(t["fill_time"] != "2024-06-06 15:35:00" for t in res_out["trades"])


def test_flat_at_1555_when_neither_stop_nor_target_hit():
    """A trade whose price goes flat right after fill (never reaches the
    80/40-point stop/target) must time-exit at 15:55."""
    df = trend_session(DATE, direction="long", slope=1.0,
                       dip_windows=["10:35"],
                       events=[("10:40", 315, 0.0)])       # flat 10:40 -> 15:55
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["exit_reason"] == "time_exit"
    assert t["exit_time"].endswith("19:55:00+00:00")     # 15:55 ET == 19:55 UTC in June (EDT)


def test_early_close_flat_time_is_1255_and_late_time_is_1230():
    assert D.dvp_flat_time(EARLY_CLOSE_DATE) == dtime(12, 55)
    assert D.dvp_late_time(EARLY_CLOSE_DATE) == dtime(12, 30)
    assert D.dvp_open_time() == dtime(10, 30)


def test_early_close_session_flat_at_1255(monkeypatch=None):
    df = trend_session(EARLY_CLOSE_DATE, direction="long", slope=1.0,
                       dip_windows=["10:35"],
                       events=[("10:40", 135, 0.0)],        # flat 10:40 -> 12:55
                       close_time=(13, 0))
    res = D.dvp_session(df, EARLY_CLOSE_DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["exit_reason"] == "time_exit"
    assert t["exit_time"].endswith("16:55:00+00:00")     # 12:55 ET == 16:55 UTC in July (EDT)


# ---------------------------------------------------------------------
# re-arm (sec 3.2 "First"): the next trigger must START at/after the exit
# ---------------------------------------------------------------------

def test_rearm_skips_a_trigger_bar_starting_before_the_prior_exit():
    """Two back-to-back trigger candles, but the first trade's exit
    (flat, via a long flat stretch) lands AFTER the second candle's own
    start time -- the second must be skipped (not re-armed yet); only one
    trade results."""
    df = trend_session(DATE, direction="long", slope=1.0,
                       dip_windows=["10:35", "10:45"],
                       events=[("10:40", 60, 0.0)])         # flat well past 10:45
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1


# ---------------------------------------------------------------------
# guardrails: G-four cap, G-loss on/off, "no guardrails" lifts both
# ---------------------------------------------------------------------

def test_five_winning_triggers_capped_at_four_with_guardrails_on():
    df = trend_session(DATE, direction="long", slope=1.0,
                       dip_windows=["10:35", "11:35", "12:35", "13:35", "14:35"])
    capped = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule="total")
    assert len(capped["trades"]) == 4
    uncapped = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule=None)
    assert len(uncapped["trades"]) == 5                    # "no guardrails": all triggers taken
    consecutive_capped = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule="consecutive")
    assert len(consecutive_capped["trades"]) == 4           # G-four still applies under "consecutive"


def test_guardrail_wiring_matches_apply_loss_rule_replay():
    """dvp_session's own stop/cap decisions, under each loss_rule, must
    equal replaying `_apply_loss_rule` (+ the 4-trade cap) over the SAME
    trades that a guardrail-free run (`loss_rule=None`) actually produced
    -- proof the guardrail state is folded in once per completed trade,
    not recomputed from something else."""
    df = trend_session(DATE, direction="long", events=[
        ("10:35", 5, -1.2), ("10:40", 15, -7.0),            # trigger + forced stop-loss
        ("12:35", 5, -1.2),                                  # a clean trigger (natural outcome)
        ("14:35", 5, -1.2), ("14:40", 15, -7.0),             # trigger + forced stop-loss
    ])
    natural = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule=None)["trades"]
    assert len(natural) >= 2

    for rule in ("total", "consecutive"):
        n_losses = consecutive = 0
        predicted = []
        for t in natural:
            if len(predicted) >= 4:
                break
            predicted.append(t)
            n_losses, consecutive, stopped = D._apply_loss_rule(
                rule, _gross_of(t), n_losses, consecutive)
            if stopped:
                break
        actual = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule=rule)["trades"]
        assert [t["fill_time"] for t in actual] == [t["fill_time"] for t in predicted]


# ---------------------------------------------------------------------
# pre-flight: no P&L capability, counts triggers not guardrail-limited entries
# ---------------------------------------------------------------------

def test_preflight_module_never_imports_pnl_functions():
    assert not hasattr(D, "pnl_dollars")
    assert not hasattr(D, "trade_cost")


def test_dvp_triggers_session_counts_without_walking_exits():
    df = trend_session(DATE, direction="long",
                       dip_windows=["10:35", "11:35", "12:35", "13:35", "14:35"])
    res = D.dvp_triggers_session(df, DATE, market="NQ")
    assert res["n_triggers"] == 5
    assert res["n_entries_upper_bound"] == 4                # capped, sec 6.1
    assert res["first_direction"] == "long"


def test_dvp_triggers_session_skips_invalid_open():
    df = trend_session(DATE, direction="long", dip_windows=["10:35"])
    df = df.iloc[3:]                                        # drop the 09:30 bar
    res = D.dvp_triggers_session(df, DATE, market="NQ")
    assert res["skipped"] is True and res["n_triggers"] == 0


# ---------------------------------------------------------------------
# day-skip rule (sec 2): missing 09:30, or a >5-min gap inside 09:30-10:30
# ---------------------------------------------------------------------

def test_session_skipped_when_0930_bar_missing():
    df = trend_session(DATE, direction="long", dip_windows=["10:35"]).iloc[1:]
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert res["skipped"] is True


def test_session_skipped_on_gap_inside_first_hour_but_not_after():
    df = trend_session(DATE, direction="long", dip_windows=["11:35"])
    naive = SIG._naive_et(df)
    keep = ~((naive.time >= dtime(10, 0)) & (naive.time < dtime(10, 10)))
    gapped = df[keep]
    assert D.dvp_session(gapped, DATE, market="NQ", p_ref=15000.0)["skipped"] is True

    naive2 = SIG._naive_et(df)
    keep2 = ~((naive2.time >= dtime(13, 0)) & (naive2.time < dtime(13, 20)))
    late_gap = df[keep2]
    assert D.dvp_session(late_gap, DATE, market="NQ", p_ref=15000.0)["skipped"] is False


# ---------------------------------------------------------------------
# voided flag: entry/exit instrument_id differ
# ---------------------------------------------------------------------

def test_trade_voided_when_entry_and_exit_held_ids_differ():
    df = trend_session(DATE, direction="long", slope=1.0,
                       dip_windows=["10:35"],
                       events=[("10:40", 315, 0.0)])         # flat -> forces the 15:55 time exit
    naive = SIG._naive_et(df)
    df = df.copy()
    df.loc[naive.time >= dtime(15, 0), "held_id"] = 2         # a "roll" late in the day
    res = D.dvp_session(df, DATE, market="NQ", p_ref=15000.0)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["voided"] is True
    assert res["trades"][0]["void_reason"] is not None


# ---------------------------------------------------------------------
# literal-points mode end to end (sec 3.6/7.3)
# ---------------------------------------------------------------------

def test_literal_points_mode_distances_are_unscaled():
    df = trend_session(DATE, direction="long", dip_windows=["10:35"])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=None)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["stop_dist"] == pytest.approx(80.0)
    assert t["target_dist"] == pytest.approx(40.0)


def test_short_target_distance_is_50_points():
    df = trend_session(DATE, direction="short", dip_windows=["10:35"])
    res = D.dvp_session(df, DATE, market="NQ", p_ref=None)
    assert len(res["trades"]) == 1
    assert res["trades"][0]["target_dist"] == pytest.approx(50.0)
    assert res["trades"][0]["stop_dist"] == pytest.approx(80.0)


def test_loss_rule_rejects_unknown_value():
    df = trend_session(DATE, direction="long", dip_windows=["10:35"])
    with pytest.raises(ValueError):
        D.dvp_session(df, DATE, market="NQ", p_ref=15000.0, loss_rule="nope")
