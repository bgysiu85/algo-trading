#!/usr/bin/env python3
"""Unit tests for the 1-hour exit walk (exits.py), W15-0016.
REGISTERED_tl_bounce.md sec 2.3."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.tl_bounce import exits as EX
from strategy.tl_bounce.signals import Signals
from strategy.tl_bounce.sim import simulate as g2_simulate
from strategy.tl_bounce.spec import STOP_BUF


def _sig(n, sup=None, res=None, sup_breaks=None, res_breaks=None, swing_low=None,
        swing_high=None, atr=None):
    nan = np.full(n, np.nan)
    zero = np.zeros(n, bool)
    return Signals(
        o=np.zeros(n), h=np.zeros(n), l=np.zeros(n), c=np.zeros(n),
        atr=(np.ones(n) if atr is None else np.asarray(atr, float)),
        sup=(nan.copy() if sup is None else np.asarray(sup, float)),
        sup_breaks=(zero.copy() if sup_breaks is None else np.asarray(sup_breaks, bool)),
        res=(nan.copy() if res is None else np.asarray(res, float)),
        res_breaks=(zero.copy() if res_breaks is None else np.asarray(res_breaks, bool)),
        touch_long=zero.copy(), touch_short=zero.copy(),
        swing_low=(nan.copy() if swing_low is None else np.asarray(swing_low, float)),
        swing_high=(nan.copy() if swing_high is None else np.asarray(swing_high, float)),
        e0=None,
    )


def _hourly(opens, highs, lows, closes, bar_hours=4, per_bucket=4):
    """`per_bucket` 1H rows per entry-chart bucket; opens/highs/lows/closes
    are per-HOURLY-ROW arrays (len = n_buckets * per_bucket)."""
    n = len(opens)
    t = pd.date_range("2020-01-06 18:00", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "t_open": t, "open_adj": opens, "high_adj": highs, "low_adj": lows,
        "close_adj": closes, "adj_offset": np.zeros(n), "held_id": np.ones(n, dtype=int),
    })


def _entry_t_open(n_buckets, bar_hours=4):
    return pd.Series(pd.date_range("2020-01-06 18:00", periods=n_buckets, freq=f"{bar_hours}h", tz="UTC"))


def test_stop_hit_within_the_fill_bucket_itself():
    # entry-chart bucket 1 (fill bucket) has 4 hourly bars; price dips to
    # the stop on the 3rd hour of that same bucket -- must exit there, not
    # wait for the bucket to close (an entry-chart-granularity walk like
    # sim.py's G2 approximation cannot see this).
    per_bucket = 4
    opens =  [10, 10, 10, 10,   11, 11, 11, 11]
    highs =  [10.2]*4 +          [11.2]*4
    lows =   [9.9]*4  +          [10.5, 9.0, 10.5, 10.5]   # hour 5 (idx 5) dips through
    closes = [10]*4   +          [11]*4
    hourly = _hourly(opens, highs, lows, closes)
    entry_t = _entry_t_open(2)
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t)
    sig = _sig(2, swing_low=[9.5, 9.5])
    start_pos = EX.find_start_pos(hourly["t_open"], entry_t.iloc[1])
    assert start_pos == 4
    outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=1, start_pos=4,
                                     direction="long", initial_stop=9.5, x1_on=True)
    assert outcome.exit_pos == 5
    assert outcome.exit_bucket_j == 1        # still inside the fill's own bucket
    assert outcome.reason == EX.R_INITIAL_STOP
    assert outcome.exit_price == pytest.approx(9.5)   # stop level, not the open (not gapped)


def test_trail_only_takes_effect_from_the_next_bucket():
    # 3 buckets x 4 hours. Bucket 1 (fill) never threatens the stop. Its
    # own close (last hour of bucket 1) has swing_low that WOULD raise the
    # stop above bucket 2's low -- but that new level must not apply until
    # bucket 2 starts, matching S3 ("a new stop takes effect from the next
    # bar").
    opens =  [10]*4 + [10]*4 + [10]*4
    highs =  [10.2]*12
    lows =   [9.9]*4 + [9.6, 9.6, 9.6, 9.6] + [9.9]*4
    closes = [10]*12
    hourly = _hourly(opens, highs, lows, closes)
    entry_t = _entry_t_open(3)
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t)
    # swing_low[0] (fill bucket's own close) = 9.7 -> candidate stop = 9.7 - 0.25*1 = 9.45,
    # ABOVE the initial stop (9.0), so it should raise the stop once bucket 1 closes.
    sig = _sig(3, swing_low=[9.7, 9.7, 9.7])
    outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=0, start_pos=0,
                                     direction="long", initial_stop=9.0, x1_on=True)
    # bucket 1's hours (lows=9.6) never touch 9.0 (initial) NOR 9.45 (candidate,
    # not yet applied) -- so no exit until bucket 2, where the now-applied 9.45
    # stop is never actually tested either (bucket 2's lows are 9.9) -> data_end.
    assert outcome.reason == EX.R_DATA_END
    assert outcome.trail_started is True     # the candidate did exceed the initial stop


def test_x1_exit_fires_at_next_buckets_open():
    opens =  [10]*4 + [10.5]*4
    highs =  [10.2]*4 + [10.7]*4
    lows =   [9.9]*4 + [10.3]*4
    closes = [10]*4 + [10.5]*4
    hourly = _hourly(opens, highs, lows, closes)
    entry_t = _entry_t_open(2)
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t)
    sig = _sig(2, sup_breaks=[True, False], swing_low=[9.0, 9.0])
    outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=0, start_pos=0,
                                     direction="long", initial_stop=9.0, x1_on=True)
    assert outcome.reason == EX.R_X1
    assert outcome.exit_bucket_j == 1
    assert outcome.exit_pos == 4
    assert outcome.exit_price == pytest.approx(10.5)   # next bucket's own open


def test_x1_off_variant_ignores_the_break():
    opens =  [10]*4 + [10.5]*4
    highs =  [10.2]*4 + [10.7]*4
    lows =   [9.9]*4 + [10.3]*4
    closes = [10]*4 + [10.5]*4
    hourly = _hourly(opens, highs, lows, closes)
    entry_t = _entry_t_open(2)
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t)
    sig = _sig(2, sup_breaks=[True, False], swing_low=[9.0, 9.0])
    outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=0, start_pos=0,
                                     direction="long", initial_stop=9.0, x1_on=False)
    assert outcome.reason == EX.R_DATA_END


def test_short_direction_mirrors_long():
    # swing_high held far away so the trail candidate never tightens below
    # the initial stop -- isolates the mirrored stop-hit path from S2.
    opens =  [10]*4 + [10]*4
    highs =  [10.1]*4 + [11.5, 10.1, 10.1, 10.1]
    lows =   [9.9]*4 + [9.9]*4
    closes = [10]*4 + [10]*4
    hourly = _hourly(opens, highs, lows, closes)
    entry_t = _entry_t_open(2)
    bucket_idx = EX.hourly_bucket_index(hourly["t_open"], entry_t)
    sig = _sig(2, swing_high=[20.0, 20.0])
    outcome = EX.simulate_trade_exit(hourly, bucket_idx, sig, fill_j=0, start_pos=0,
                                     direction="short", initial_stop=11.0, x1_on=True)
    assert outcome.reason == EX.R_INITIAL_STOP
    assert outcome.exit_pos == 4
    assert outcome.exit_price == pytest.approx(11.0)
    assert outcome.trail_started is False


def test_trail_candidate_matches_sim_formula_bar_for_bar():
    """Cross-check exits.trail_candidate against sim.py's own inline step-4
    formula (sim.py is frozen for G2; this proves this module's
    reimplementation has not drifted from it) on a synthetic multi-bar
    walk with both an active line and an active swing on each side."""
    rng = np.random.default_rng(7)
    n = 40
    sup = np.where(rng.random(n) > 0.3, rng.uniform(8, 9, n), np.nan)
    res = np.where(rng.random(n) > 0.3, rng.uniform(11, 12, n), np.nan)
    swing_low = rng.uniform(8.5, 9.5, n)
    swing_high = rng.uniform(10.5, 11.5, n)
    atr = rng.uniform(0.5, 1.5, n)
    for direction in ("long", "short"):
        stop_sim = 9.0 if direction == "long" else 11.0
        stop_ex = stop_sim
        for j in range(n):
            if direction == "long":
                line_ref = sup[j] if not np.isnan(sup[j]) else np.inf
                cand = min(swing_low[j], line_ref) - STOP_BUF * atr[j]
                stop_sim = max(stop_sim, cand) if np.isfinite(cand) and cand < 100 else stop_sim
            else:
                line_ref = res[j] if not np.isnan(res[j]) else -np.inf
                cand = max(swing_high[j], line_ref) + STOP_BUF * atr[j]
                stop_sim = min(stop_sim, cand) if np.isfinite(cand) else stop_sim
            cand_ex = EX.trail_candidate(sup[j], res[j], swing_low[j], swing_high[j], atr[j], direction)
            if np.isfinite(cand_ex):
                stop_ex = max(stop_ex, cand_ex) if direction == "long" else min(stop_ex, cand_ex)
            assert stop_ex == pytest.approx(stop_sim)


def test_hourly_bucket_index_maps_each_hour_to_its_own_entry_bar():
    entry_t = _entry_t_open(3)
    hourly_t = pd.Series(pd.date_range("2020-01-06 18:00", periods=12, freq="1h", tz="UTC"))
    idx = EX.hourly_bucket_index(hourly_t, entry_t)
    assert list(idx[:4]) == [0, 0, 0, 0]
    assert list(idx[4:8]) == [1, 1, 1, 1]
    assert list(idx[8:12]) == [2, 2, 2, 2]


def test_find_start_pos_falls_back_across_a_real_gap():
    hourly_t = pd.Series(pd.to_datetime(
        ["2020-01-06 18:00", "2020-01-06 19:00", "2020-01-06 21:00"], utc=True))
    pos = EX.find_start_pos(hourly_t, pd.Timestamp("2020-01-06 20:00", tz="UTC"))
    assert pos == 2   # the missing 20:00 hour has no print; first real hour at/after it
