#!/usr/bin/env python3
"""XNYS calendar: closed days, early closes, the RTH window, and the
independently-derived early-close rule cross-checked against the baked,
data-derived table. REGISTERED_w16_session_baselines.md sec 2."""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd
import pytest

import strategy.w16.sessions as S


def test_rule_reproduces_baked_table_exactly_over_its_own_range():
    """See module docstring: the baked table is read off real SPY data, the
    rule is an independent re-derivation. If they disagree, one of them is
    wrong, and this is the test that would catch it."""
    lo, hi = S._BAKED_RANGE
    assert S.early_close_rule(lo, hi) == S.EARLY_CLOSES_2010_2025


def test_black_friday_always_early_close():
    for y in range(2010, 2027):
        days = S.early_close_days(y, y)
        fridays = [d for d in days if pd.Timestamp(d).month == 11]
        assert len(fridays) == 1, f"{y}: expected exactly one November early close"


def test_good_friday_and_columbus_day():
    """XNYS trades through Columbus Day and Veterans Day but is closed on
    Good Friday, which is not a federal holiday at all (sec 2's "NYSE
    trading days (XNYS calendar)")."""
    closed_2024 = S.market_closed_days(2024, 2024)
    assert "2024-03-29" in closed_2024          # Good Friday 2024
    assert "2024-10-14" not in closed_2024      # Columbus Day
    assert "2024-11-11" not in closed_2024      # Veterans Day


def test_known_holidays_closed():
    closed = S.market_closed_days(2023, 2023)
    assert "2023-01-02" in closed               # New Year's observed (Jan 1 = Sunday)
    assert "2023-12-25" in closed
    assert "2023-07-04" in closed
    assert "2023-11-23" in closed                # Thanksgiving


def test_unscheduled_closures_present():
    closed = S.market_closed_days(2012, 2012)
    assert "2012-10-29" in closed and "2012-10-30" in closed   # Hurricane Sandy


def test_is_xnys_trading_day():
    assert S.is_xnys_trading_day("2024-06-06")     # ordinary Thursday
    assert not S.is_xnys_trading_day("2024-06-08")  # Saturday
    assert not S.is_xnys_trading_day("2024-03-29")  # Good Friday


def test_session_close_time_and_orb_time_exit():
    assert S.session_close_time("2024-11-25") == dtime(16, 0)   # ordinary day
    assert S.session_close_time("2024-11-29") == dtime(13, 0)   # day after Thanksgiving
    assert S.orb_time_exit("2024-11-25") == dtime(15, 30)
    assert S.orb_time_exit("2024-11-29") == dtime(12, 30)


def test_session_date_range_excludes_weekends_and_holidays():
    days = S.session_date_range(2024, 2024)
    assert "2024-01-01" not in days              # New Year's Day
    assert "2024-01-06" not in days              # Saturday
    assert "2024-01-02" in days
    assert days == sorted(days)


def _mk_bars(times_et, *, tz="America/New_York"):
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz=tz) for t in times_et]).tz_convert("UTC")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                         "volume": 1.0}, index=idx)


def test_has_valid_open_true_for_clean_session():
    times = [f"2024-06-06 09:{m:02d}:00" for m in range(30, 60)]
    df = _mk_bars(times)
    assert S.has_valid_open(df)


def test_has_valid_open_false_missing_open_bar():
    times = [f"2024-06-06 09:{m:02d}:00" for m in range(35, 60)]   # starts 09:35, not 09:30
    df = _mk_bars(times)
    assert not S.has_valid_open(df)


def test_has_valid_open_false_on_gap_over_5min():
    times = ["2024-06-06 09:30:00", "2024-06-06 09:31:00", "2024-06-06 09:40:00",
            "2024-06-06 09:50:00"]
    df = _mk_bars(times)
    assert not S.has_valid_open(df)


def test_session_window_mask_narrows_to_1300_on_early_close():
    times = ["2024-11-29 09:30:00", "2024-11-29 12:59:00", "2024-11-29 13:05:00",
            "2024-11-29 15:59:00"]
    df = _mk_bars(times)
    mask = S.session_window_mask(df, "2024-11-29")
    assert list(mask) == [True, True, False, False]


def test_split_by_session_groups_by_et_calendar_date():
    times = ["2024-06-06 23:58:00", "2024-06-07 00:02:00", "2024-06-07 09:30:00"]
    df = _mk_bars(times)
    groups = dict(S.split_by_session(df))
    assert set(groups) == {"2024-06-06", "2024-06-07"}
    assert len(groups["2024-06-06"]) == 1
    assert len(groups["2024-06-07"]) == 2
