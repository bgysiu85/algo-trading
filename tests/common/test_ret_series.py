#!/usr/bin/env python3
"""`ret_series` must equal `ret_at`, bar for bar, NaNs included.

H-P1's gate reads the five-minute return at every bar of every symbol-day, and
calling `ret_at` per bar is minutes rather than seconds over 6,411 symbol-days.
So there are two implementations of one number, and this file is what makes
that safe rather than a second source of truth: the cheapest control in this
project is pulling the same figure down two independent routes and requiring
agreement, which is how the SPY caches caught a data-path defect.

The case that matters most is the warm-up frame. `build_frame` prepends
previous sessions, and `back` is POSITIONAL within a session -- a shift across
the whole frame computes the 04:00 bar's return against yesterday's last bars
and returns a perfectly ordinary-looking number.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from common import running_up as RU


def frame(days=("2026-09-10", "2026-09-11"), bars=40, start_hour=4):
    idx, closes = [], []
    px = 3.0
    for d in days:
        t0 = pd.Timestamp(f"{d} {start_hour:02d}:00", tz=RU.ET)
        for i in range(bars):
            idx.append(t0 + timedelta(minutes=i))
            px = round(px * (1.0 + 0.004 * np.sin(i / 3.0) + 0.001), 4)
            closes.append(px)
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": 10_000},
                        index=pd.DatetimeIndex(idx))


def test_it_agrees_with_ret_at_on_every_bar():
    df = frame()
    got = RU.ret_series(df, back=5)
    for ts in df.index:
        one = RU.ret_at(df, ts, back=5)
        many = got.loc[ts]
        if np.isnan(one):
            assert np.isnan(many), f"{ts}: ret_at NaN, ret_series {many}"
        else:
            assert many == pytest.approx(one, abs=1e-12), ts


@pytest.mark.parametrize("back", [1, 3, 5, 9])
def test_it_agrees_at_other_lookbacks(back):
    df = frame()
    got = RU.ret_series(df, back=back)
    for ts in df.index[::3]:
        one, many = RU.ret_at(df, ts, back=back), got.loc[ts]
        assert (np.isnan(one) and np.isnan(many)) or many == pytest.approx(one, abs=1e-12)


def test_the_first_bars_of_EACH_session_are_NaN_not_yesterdays_return():
    """THE WARM-UP TRAP. A shift over the whole frame makes the 04:00 bar's
    five-minute return a comparison against yesterday's 09:2x bars -- a real
    number, wrong, and invisible."""
    df = frame()
    got = RU.ret_series(df, back=5)
    local = df.index.tz_convert(RU.ET)
    for day in pd.unique(local.date):
        first5 = df.index[local.date == day][:5]
        assert got.loc[first5].isna().all(), f"{day}: a session's first bars carried a value"


def test_a_zero_previous_close_is_NaN_and_not_an_infinite_return():
    df = frame(days=("2026-09-11",))
    df.loc[df.index[3], "close"] = 0.0
    got = RU.ret_series(df, back=5)
    assert np.isnan(got.iloc[8]), got.iloc[8]
    assert np.isfinite(got.dropna()).all()


def test_an_empty_frame_returns_an_empty_series_rather_than_raising():
    out = RU.ret_series(pd.DataFrame(columns=["close"],
                                     index=pd.DatetimeIndex([], tz=RU.ET)))
    assert out.empty


def test_bars_before_0400_are_excluded_from_the_session_window():
    """`session_slice` starts the session at 04:00 ET, so a 03:55 bar is not
    part of it and must not become the denominator of the 04:00 bar."""
    df = frame(days=("2026-09-11",), bars=12, start_hour=3)
    got = RU.ret_series(df, back=5)
    local = df.index.tz_convert(RU.ET)
    assert got[local.time < RU.SESSION_START].isna().all()


def test_the_index_is_preserved_exactly():
    """The gate reindexes this onto the engine's bar index; a reordered or
    partial index would silently become False everywhere it did not align."""
    df = frame()
    got = RU.ret_series(df)
    assert got.index.equals(df.index)


# --- dist_from_high, the same arrangement ------------------------------------

def test_dist_series_agrees_with_the_feature_on_every_bar():
    df = frame()
    got = RU.dist_series(df)
    for ts in df.index:
        one = RU.features(df, ts).get("dist_from_high", float("nan"))
        many = got.loc[ts]
        if one != one:
            assert np.isnan(many), ts
        else:
            assert many == pytest.approx(one, abs=1e-12), ts


def test_dist_is_zero_at_a_new_session_high_and_negative_below_it():
    df = frame(days=("2026-09-11",), bars=20)
    got = RU.dist_series(df)
    assert (got.dropna() <= 1e-12).all()
    rising = df.copy()
    rising["high"] = rising["close"] = np.arange(1.0, 1.0 + len(rising))
    assert RU.dist_series(rising).dropna().abs().max() < 1e-12


def test_dist_does_not_measure_today_against_yesterdays_high():
    """The warm-up trap again: a cummax over the whole frame would carry
    yesterday's high into this morning and read every bar as far below it."""
    df = frame()
    local = df.index.tz_convert(RU.ET)
    days = list(pd.unique(local.date))
    df.loc[local.date == days[0], "high"] *= 100.0    # a huge high, yesterday
    got = RU.dist_series(df)
    today = got[local.date == days[-1]].dropna()
    assert today.min() > -0.5, "yesterday's high leaked into today"
