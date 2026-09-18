#!/usr/bin/env python3
"""The "running up" features, and the separation statistic that reads them.

No registration governs these -- the pre-flight has no rule in it. What these
pin is the thing that WOULD make the pre-flight a lie: a feature that reads
bars it could not have seen, a control that is not reproducible, or an AUC
that reports separation a tied feature does not have.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common import running_up as RU

ET = RU.ET


def frame(rows, symbol="X"):
    """rows = [(ts_et, close, volume)] or [(ts_et, o, h, l, c, v)]."""
    idx, recs = [], []
    for r in rows:
        if len(r) == 3:
            ts, c, v = r
            o = h = lo = c
        else:
            ts, o, h, lo, c, v = r
        idx.append(pd.Timestamp(ts, tz=ET))
        recs.append({"open": o, "high": h, "low": lo, "close": c,
                     "volume": v, "symbol": symbol})
    return pd.DataFrame(recs, index=pd.DatetimeIndex(idx)).sort_index()


DAY = "2026-09-11"


def T(hhmm, day=None):
    """A tz-aware ET stamp -- `features` refuses a naive one, by design."""
    return pd.Timestamp(f"{day or DAY} {hhmm}", tz=ET)


# The null control's value for one fixed seed_key. Pinned so a change of
# SEED, of the hash, or a slip back to process-salted hash() fails loudly
# rather than silently reseeding every control in the report.
EXPECTED_RAND = 0.2082409125271617


def ladder(n=10, start=4, px=2.0, vol=1000):
    """n one-minute bars from 04:0start, flat price and volume."""
    return [(f"{DAY} 0{start}:{i:02d}", px, vol) for i in range(n)]


# --- what the features are allowed to see -----------------------------------

def test_a_prior_sessions_bars_are_not_in_the_window():
    """build_frame prepends warm-up sessions. Slicing on the timestamp alone
    would put yesterday's volume in today's baseline -- the three-day-frame
    trap that once moved a detector's signals a median of 245 bars."""
    df = frame([("2026-09-10 05:00", 2.0, 999_999)] + ladder(6))
    hist = RU.session_slice(df, pd.Timestamp(f"{DAY} 04:05", tz=ET))
    assert len(hist) == 6
    assert hist.index[0].tz_convert(ET).date().isoformat() == DAY


def test_no_bar_after_the_entry_is_read():
    df = frame(ladder(10))
    hist = RU.session_slice(df, pd.Timestamp(f"{DAY} 04:03", tz=ET))
    assert len(hist) == 4                      # 04:00..04:03 inclusive
    assert hist.index[-1].tz_convert(ET).strftime("%H:%M") == "04:03"


def test_the_signal_bar_itself_IS_read():
    """The engines enter at the CLOSE of the signal bar, so that bar has
    closed and is knowable. Excluding it would model a different entry."""
    df = frame(ladder(5) + [(f"{DAY} 04:05", 3.0, 5000)])
    f = RU.features(df, T("04:05"))
    assert f["ret_1m"] == pytest.approx(3.0 / 2.0 - 1.0)


def test_bars_before_0400_are_excluded():
    df = frame([(f"{DAY} 03:59", 9.0, 500_000)] + ladder(4))
    hist = RU.session_slice(df, pd.Timestamp(f"{DAY} 04:03", tz=ET))
    assert len(hist) == 4 and float(hist["close"].max()) == 2.0


# --- the arithmetic ---------------------------------------------------------

def test_rvol_5m_is_the_last_five_minutes_against_the_session_median():
    rows = ladder(10, vol=100) + [(f"{DAY} 04:{i}", 2.0, 500) for i in (10, 11, 12, 13, 14)]
    f = RU.features(frame(rows), T("04:14"))
    # 15 bars: ten at 100 and five at 500 -> median 100; last five sum 2,500
    assert f["rvol_5m"] == pytest.approx(2500 / (5 * 100))
    assert f["rvol_1m"] == pytest.approx(5.0)


def test_the_volume_baseline_is_the_median_not_the_mean():
    """One 400k print in a thin name would otherwise set the baseline and make
    every later burst read as ordinary."""
    rows = [(f"{DAY} 04:00", 2.0, 400_000)] + [(f"{DAY} 04:{i:02d}", 2.0, 100)
                                               for i in range(1, 11)]
    f = RU.features(frame(rows), T("04:10"))
    assert f["rvol_1m"] == pytest.approx(1.0)      # median is 100, not ~36k


def test_returns_are_positional_over_closed_bars():
    rows = [(f"{DAY} 04:0{i}", 2.0 + 0.1 * i, 100) for i in range(6)]
    f = RU.features(frame(rows), T("04:05"))
    assert f["ret_1m"] == pytest.approx(2.5 / 2.4 - 1)
    assert f["ret_3m"] == pytest.approx(2.5 / 2.2 - 1)
    assert f["ret_5m"] == pytest.approx(2.5 / 2.0 - 1)


def test_a_short_history_gives_nan_rather_than_a_wrong_number():
    f = RU.features(frame(ladder(2)), T("04:01"))
    assert f["ret_1m"] == f["ret_1m"]                    # one bar back exists
    assert f["ret_5m"] != f["ret_5m"]                    # five do not -> NaN
    assert f["up_bars_5"] != f["up_bars_5"]


def test_up_bars_counts_the_last_five_closes():
    """A FLAT bar is not an up bar. Pre-market small caps print flat minutes
    constantly, so `>=` would read a name that has not moved in five minutes
    as five consecutive up bars -- the exact opposite of "running up"."""
    px = [2.0, 2.1, 2.0, 2.2, 2.2, 2.3]
    rows = [(f"{DAY} 04:0{i}", p, 100) for i, p in enumerate(px)]
    f = RU.features(frame(rows), T("04:05"))
    assert f["up_bars_5"] == 3.0                    # up, down, up, FLAT, up


def test_accel_is_positive_when_the_move_is_speeding_up():
    slow = [(f"{DAY} 04:0{i}", 2.0 + 0.01 * i, 100) for i in range(4)]
    fast = slow[:3] + [(f"{DAY} 04:03", 2.5, 100)]
    assert RU.features(frame(slow), T("04:03"))["accel"] == pytest.approx(0.0, abs=2e-4)
    assert RU.features(frame(fast), T("04:03"))["accel"] > 0.05


def test_pos_in_range_and_dist_from_high():
    rows = [(f"{DAY} 04:00", 2.0, 2.0, 2.0, 2.0, 100),
            (f"{DAY} 04:01", 2.0, 3.0, 1.0, 3.0, 100),
            (f"{DAY} 04:02", 3.0, 3.0, 2.0, 2.0, 100)]
    f = RU.features(frame(rows), T("04:02"))
    assert f["pos_in_range"] == pytest.approx((2.0 - 1.0) / (3.0 - 1.0))
    assert f["dist_from_high"] == pytest.approx(2.0 / 3.0 - 1.0)


def test_minutes_since_0400_is_the_clock_not_the_names_first_print():
    """It stands in for TIME OF DAY, which is the closed question. Measuring
    it from the name's first bar would make a 07:00 first-print read as 0."""
    df = frame([(f"{DAY} 07:00", 2.0, 100), (f"{DAY} 07:05", 2.1, 100)])
    assert RU.features(df, T("07:05"))["minutes_since_0400"] == 185.0


def test_duplicate_timestamps_do_not_raise():
    """The 2025-06-09 slice carries duplicate ts_event rows; get_loc returns a
    slice on them and the next comparison raises. Three modules hit it."""
    rows = [(f"{DAY} 04:00", 2.0, 100), (f"{DAY} 04:01", 2.1, 100),
            (f"{DAY} 04:01", 2.2, 100), (f"{DAY} 04:02", 2.3, 100)]
    f = RU.features(frame(rows), T("04:02"))
    assert f["ret_1m"] == pytest.approx(2.3 / 2.2 - 1)


def test_a_naive_timestamp_is_refused_by_name():
    """Read as UTC a naive ET stamp moves every session boundary four or five
    hours and the features still come back looking ordinary. Refused here,
    named, rather than three frames down inside pandas."""
    with pytest.raises(ValueError, match="tz-aware"):
        RU.features(frame(ladder(6)), f"{DAY} 04:05")
    with pytest.raises(ValueError, match="tz-aware"):
        RU.features(frame(ladder(6)), pd.Timestamp(f"{DAY} 04:05"))


def test_an_empty_frame_returns_all_nan_but_still_a_control():
    f = RU.features(frame([]), T("04:05"))
    assert all(f[k] != f[k] for k in RU.FEATURES if k != "rand")
    assert 0.0 <= f["rand"] <= 1.0


# --- the null control -------------------------------------------------------

def test_rand_is_reproducible_and_not_process_salted():
    """`hash()` on a str is salted per process, so a control seeded on it
    differs in every worker and on every run. A control that cannot be
    reproduced is not a control."""
    a = RU.features(frame(ladder(6)), T("04:05"), seed_key="AAPL2026-09-1104:05")
    b = RU.features(frame(ladder(6)), T("04:05"), seed_key="AAPL2026-09-1104:05")
    assert a["rand"] == b["rand"]
    c = RU.features(frame(ladder(6)), T("04:05"), seed_key="MSFT2026-09-1104:05")
    assert c["rand"] != a["rand"]
    # the exact value, so a change of seed or of the hash cannot pass silently
    assert a["rand"] == pytest.approx(EXPECTED_RAND, abs=1e-12)


def test_rand_is_spread_over_the_unit_interval():
    vals = [RU.features(frame([]), T("04:05"), seed_key=f"S{i}")["rand"]
            for i in range(300)]
    assert 0.35 < float(np.mean(vals)) < 0.65
    assert min(vals) < 0.1 and max(vals) > 0.9


# --- the separation statistic ----------------------------------------------

def test_auc_of_a_useless_feature_is_a_half():
    rng = np.random.default_rng(0)
    a, b = rng.random(4000), rng.random(4000)
    assert RU.auc(a, b) == pytest.approx(0.5, abs=0.02)


def test_auc_of_perfect_separation_is_one_and_zero():
    a = np.array([5.0, 6.0, 7.0])
    b = np.array([1.0, 2.0, 3.0])
    assert RU.auc(a, b) == 1.0
    assert RU.auc(b, a) == 0.0


def test_ties_count_as_half_rather_than_as_separation():
    """up_bars_5 takes six values, so most pairs tie. Without average ranks a
    wholly tied feature reads as separation it does not have."""
    a = np.array([1.0, 1.0, 1.0, 1.0])
    b = np.array([1.0, 1.0, 1.0, 1.0])
    assert RU.auc(a, b) == pytest.approx(0.5)
    # half tied, half clearly above
    assert RU.auc(np.array([1.0, 2.0]), np.array([1.0, 1.0])) == pytest.approx(0.75)


def test_auc_ignores_nans_rather_than_ranking_them():
    a = np.array([5.0, np.nan, 6.0])
    b = np.array([1.0, 2.0, np.nan])
    assert RU.auc(a, b) == 1.0


def test_auc_is_nan_when_a_group_is_empty():
    assert RU.auc(np.array([]), np.array([1.0])) != RU.auc(np.array([]), np.array([1.0]))


# --- the binding table ------------------------------------------------------

def test_bind_table_reports_the_share_each_group_keeps():
    hot = np.array([1.0, 2.0, 3.0, 4.0])
    cold = np.array([3.0, 4.0, 5.0, 6.0])
    out = RU.bind_table(hot, cold, [3.0])
    cut, kh, kc = out[0]
    assert (kh, kc) == (0.5, 1.0)


def test_bind_table_on_an_identical_pair_reports_no_difference():
    """A useless feature keeps the same share of both groups at every cut --
    the last column of the printed table is zero all the way down."""
    v = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    for cut, kh, kc in RU.bind_table(v, v.copy(), [1.0, 3.0, 5.0]):
        assert kh == kc


def test_deciles_are_nine_numbers_and_skip_nans():
    d = RU.deciles(np.array([1.0, np.nan, 2.0, 3.0, 4.0, 5.0]))
    assert len(d) == 9 and d[0] <= d[-1]
    assert RU.deciles(np.array([np.nan, np.nan])) == []
