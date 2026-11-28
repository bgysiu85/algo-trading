"""WICK-REV bar building (W15-0063 sec 2): session grid, 4H boundaries, short 14:00 bar, cut-first."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.wick_rev import bars as B
from tests.strategy.wick_rev.synth import raw_bars


def _hourly_session(day_open_et="2020-01-06 18:00", hours=24):
    idx = pd.date_range(day_open_et, periods=hours, freq="h", tz="America/New_York").tz_convert("UTC")
    return idx


def test_4h_grid_boundaries_and_short_last_bar():
    idx = _hourly_session()                       # 18:00 .. 17:00 next day (24 hourly stamps)
    v = np.arange(len(idx), dtype=float)
    df = raw_bars(idx, v, v + 1, v - 1, v + 0.5)
    out = B.build_bars(df, 240)
    assert len(out) == 6                           # 17:00 bar is not traded
    starts = pd.DatetimeIndex(out["t_open"]).tz_convert("America/New_York").strftime("%H:%M").tolist()
    assert starts == ["18:00", "22:00", "02:00", "06:00", "10:00", "14:00"]
    assert out["n_src"].tolist() == [4, 4, 4, 4, 4, 3]            # the 14:00 bar holds 14, 15, 16
    assert out["short"].tolist() == [False] * 5 + [True]
    last_end = pd.Timestamp(out["t_end"].iloc[-1]).tz_convert("America/New_York")
    assert last_end.strftime("%H:%M") == "17:00"
    assert out["open"].iloc[0] == 0 and out["close"].iloc[0] == 3.5       # first open, last close
    assert out["high"].iloc[0] == 4 and out["low"].iloc[0] == -1


def test_30m_from_1m_and_no_bar_made_up():
    idx = pd.date_range("2020-01-06 18:00", periods=95, freq="min", tz="America/New_York").tz_convert("UTC")
    idx = idx.delete(np.arange(40, 50))                           # a hole inside the 2nd half hour
    n = len(idx)
    df = raw_bars(idx, np.ones(n), np.ones(n) * 2, np.ones(n) * 0.5, np.ones(n))
    out = B.build_bars(df, 30)
    assert out["n_src"].tolist() == [30, 20, 30, 5]               # 18:00, 18:30 (10 missing), 19:00, 19:30
    assert pd.DatetimeIndex(out["t_open"]).tz_convert("America/New_York").strftime("%H:%M").tolist() == \
        ["18:00", "18:30", "19:00", "19:30"]


def test_wall_clock_bucketing_holds_across_daylight_saving():
    winter = B.build_bars(raw_bars(_hourly_session("2020-01-06 18:00", 4), [1] * 4, [2] * 4, [0] * 4, [1] * 4), 240)
    summer = B.build_bars(raw_bars(_hourly_session("2020-07-06 18:00", 4), [1] * 4, [2] * 4, [0] * 4, [1] * 4), 240)
    assert pd.Timestamp(winter["t_open"].iloc[0]).hour == 23      # 18:00 EST = 23:00 UTC
    assert pd.Timestamp(summer["t_open"].iloc[0]).hour == 22      # 18:00 EDT = 22:00 UTC
    assert len(winter) == len(summer) == 1


def test_cut_by_session_date_is_inclusive_and_uses_the_18_00_open():
    # the 18:00 bar of 2021-12-31 (ET) belongs to the 2022-01-03 session? No: Friday evening is closed; use Thursday.
    idx = pd.DatetimeIndex(["2021-12-30 17:30", "2021-12-30 18:00", "2021-12-31 16:30"],
                           tz="America/New_York").tz_convert("UTC")
    df = raw_bars(idx, [1, 1, 1], [2, 2, 2], [0, 0, 0], [1, 1, 1])
    assert len(B.cut_sessions(df, "2021-12-30", "2021-12-30")) == 1      # only the 17:30 bar is session 12-30
    assert len(B.cut_sessions(df, "2021-12-31", "2021-12-31")) == 2      # 18:00 12-30 joins the 12-31 session
    assert len(B.cut_sessions(df, "2010-06-06", "2021-12-31")) == 3


def test_back_adjust_removes_the_roll_gap():
    idx = _hourly_session(hours=8)
    held = np.array([1, 1, 1, 1, 2, 2, 2, 2])
    c = np.array([100, 100, 100, 100, 110, 110, 110, 110], float)
    df = raw_bars(idx, c, c + 1, c - 1, c, held=held)
    adj = B.back_adjust_bars(B.build_bars(df, 60))
    assert adj["close_adj"].iloc[0] == 110 and adj["close_adj"].iloc[-1] == 110     # old segment lifted by the gap
