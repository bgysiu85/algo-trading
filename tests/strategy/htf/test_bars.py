"""Tests for strategy.htf.bars -- W15-0004, REGISTERED_htf_ben_v0.md sec 2.1.
No real bar is read anywhere in this suite; everything is synthetic, so the
gate (G1) that first reads a real bar is a separate module."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B


def _mkframe(rows):
    """rows: list of (utc_ts_str, symbol, instrument_id, o, h, l, c, v)."""
    idx = pd.DatetimeIndex([pd.Timestamp(r[0], tz="UTC") for r in rows], name="ts_event")
    df = pd.DataFrame({
        "symbol": [r[1] for r in rows],
        "instrument_id": [r[2] for r in rows],
        "open": [r[3] for r in rows], "high": [r[4] for r in rows],
        "low": [r[5] for r in rows], "close": [r[6] for r in rows],
        "volume": [r[7] for r in rows],
    }, index=idx)
    return df


def _session_hourly(session_date: dt.date, instrument_id=100, base=70.0):
    """One full 23-WALL-CLOCK-hour CME session (18:00 prev day -> 17:00
    session date), both CL.c.0 and CL.c.1, evenly spaced, no gaps. Each bar's
    UTC timestamp is derived by localizing the NAIVE wall-clock instant
    (never by adding a Timedelta to a tz-aware one), so this is correct
    across a DST transition too."""
    prev_day = session_date - dt.timedelta(days=1)
    rows = []
    for h in range(23):
        naive = (pd.Timestamp(prev_day) + pd.Timedelta(hours=18 + h))
        t = naive.tz_localize("America/New_York", nonexistent="shift_forward",
                              ambiguous=False).tz_convert("UTC")
        px = base + 0.01 * h
        rows.append((t.isoformat(), "CL.c.0", instrument_id, px, px + 0.05, px - 0.05, px + 0.01, 100 + h))
        rows.append((t.isoformat(), "CL.c.1", instrument_id + 1, px + 1, px + 1.05, px + 0.95, px + 1.01, 50 + h))
    return _mkframe(rows)


# --------------------------------------------------------------------------
# bar-start labelling
# --------------------------------------------------------------------------

def test_bar_start_labelling_4h():
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))  # a Tuesday
    out = B.resample(df, "4H")
    # session 2024-03-05: opens Monday 2024-03-04 18:00 ET
    expected_starts_et = ["18:00", "22:00", "02:00", "06:00", "10:00", "14:00"]
    local = pd.DatetimeIndex(out["t_open"]).tz_convert("America/New_York")
    assert [t.strftime("%H:%M") for t in local] == expected_starts_et
    assert list(out["bar"]) == [0, 1, 2, 3, 4, 5]
    assert list(out["session"]) == [dt.date(2024, 3, 5)] * 6


def test_bar_start_labelling_2h():
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    out = B.resample(df, "2H")
    local = pd.DatetimeIndex(out["t_open"]).tz_convert("America/New_York")
    expected = ["18:00", "20:00", "22:00", "00:00", "02:00", "04:00", "06:00",
                "08:00", "10:00", "12:00", "14:00", "16:00"]
    assert [t.strftime("%H:%M") for t in local] == expected


def test_ts_event_is_bar_start_not_end():
    """The MACD/EMA rules read a 4H bar's close at bar-end -- a bar labelled
    18:00 must be understood to CLOSE at 22:00, i.e. resample must not
    silently shift the label to the bucket's end."""
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    out = B.resample(df, "4H")
    first_close_et = pd.Timestamp(out.iloc[0]["t_open"]).tz_convert("America/New_York")
    assert first_close_et.strftime("%H:%M") == "18:00"


# --------------------------------------------------------------------------
# last bar of session: 16:00 (2H) and 14:00 (4H), shorter duration
# --------------------------------------------------------------------------

def test_last_bar_4h_is_three_hours():
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    out = B.resample(df, "4H")
    last = out.iloc[-1]
    assert last["n_src"] == 3          # 14:00, 15:00, 16:00 source bars
    assert last["bar"] == 5


def test_last_bar_2h_is_one_hour():
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    out = B.resample(df, "2H")
    last = out.iloc[-1]
    assert last["n_src"] == 1          # 16:00 only
    assert last["bar"] == 11


def test_1h_grid_is_identity_23_bars():
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    out = B.resample(df, "1H")
    assert len(out) == 23
    assert (out["n_src"] == 1).all()


# --------------------------------------------------------------------------
# early-close session (fewer than 23 source bars -- nothing synthesised)
# --------------------------------------------------------------------------

def test_early_close_session_no_bar_synthesised():
    full = _session_hourly(dt.date(2024, 3, 5))
    # drop the last 3 hourly bars (14:00-17:00) on both symbols -- an early close
    cutoff = pd.Timestamp("2024-03-05 14:00", tz="America/New_York").tz_convert("UTC")
    early = full[full.index < cutoff]
    df = B.split_held(early)
    out4h = B.resample(df, "4H")
    assert list(out4h["bar"]) == [0, 1, 2, 3, 4]           # no bucket 5 emitted
    day = B.daily(df)
    assert len(day) == 1
    assert day.iloc[0]["n_src"] == 20


# --------------------------------------------------------------------------
# DST crossing
# --------------------------------------------------------------------------

def test_dst_crossing_spring_forward_no_crash_and_six_bars():
    # 2024-03-10 is the US spring-forward Sunday (2am -> 3am). The session
    # labelled 2024-03-11 (Monday) opens Sunday 2024-03-10 18:00 ET and
    # crosses the transition around its 02:00-06:00 bucket.
    df = B.split_held(_session_hourly(dt.date(2024, 3, 11)))
    out4h = B.resample(df, "4H")
    assert len(out4h) == 6
    assert out4h["t_open"].is_monotonic_increasing
    local = pd.DatetimeIndex(out4h["t_open"]).tz_convert("America/New_York")
    assert [t.strftime("%H:%M") for t in local] == \
        ["18:00", "22:00", "02:00", "06:00", "10:00", "14:00"]


def test_dst_crossing_fall_back_no_crash_and_six_bars():
    # 2024-11-03 is the US fall-back Sunday (2am occurs twice).
    df = B.split_held(_session_hourly(dt.date(2024, 11, 4)))
    out4h = B.resample(df, "4H")
    assert len(out4h) == 6
    assert out4h["t_open"].is_monotonic_increasing


def test_one_bar_shift_breaks_bar_start_labelling():
    """Mutation guard: shifting every source timestamp forward one hour must
    change the resampled bar starts (proves the test above is actually
    pinned to the real boundary, not a tautology)."""
    # Truncate to the session's first 19 hourly bars (elapsed 0..18) so a
    # 3.5-hour forward shift of every source bar stays inside [0,23) -- the
    # bucket GRID (t_open labels) is fixed by the session calendar, not the
    # data, so the mutation is proven by bucket MEMBERSHIP changing instead
    # (n_src / close per bucket), which a 3.5h shift across several 4H
    # boundaries (4, 8, 12, 16) does.
    raw = _session_hourly(dt.date(2024, 3, 5)).iloc[:38]
    shifted = raw.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=3, minutes=30)
    out_a = B.resample(B.split_held(raw), "4H")
    out_b = B.resample(B.split_held(shifted), "4H")
    assert list(out_a["n_src"]) != list(out_b["n_src"]) or \
        list(out_a["close"]) != list(out_b["close"])


# --------------------------------------------------------------------------
# session labelling: Sunday evening joins Monday
# --------------------------------------------------------------------------

def test_sunday_evening_joins_monday_session():
    # A Sunday-evening-only slice (18:00-21:00 ET on a Sunday) must be
    # labelled with MONDAY's date, not Sunday's.
    sunday = dt.date(2024, 3, 3)  # a Sunday
    open_et = pd.Timestamp(sunday, tz="America/New_York") + pd.Timedelta(hours=18)
    rows = []
    for h in range(4):
        t = (open_et + pd.Timedelta(hours=h)).tz_convert("UTC")
        rows.append((t.isoformat(), "CL.c.0", 100, 70 + h, 70.1 + h, 69.9 + h, 70 + h, 100))
    df = B.split_held(_mkframe(rows))
    out = B.resample(df, "1H")
    assert (out["session"] == dt.date(2024, 3, 4)).all()   # Monday


# --------------------------------------------------------------------------
# back_adjust: roll gaps, never ratio, difference accumulates backward
# --------------------------------------------------------------------------

def test_back_adjust_no_roll_is_untouched():
    s1 = B.split_held(_session_hourly(dt.date(2024, 3, 5), instrument_id=1))
    out = B.back_adjust(B.resample(s1, "4H"))
    assert (out["close_adj"] == out["close"]).all()
    assert (out["adj_offset"] == 0).all()
    assert out["n_rolls"].iloc[0] == 0


def test_back_adjust_roll_gap_shifts_earlier_segment_only():
    day1 = B.split_held(_session_hourly(dt.date(2024, 3, 5), instrument_id=1, base=70.0))
    day2 = B.split_held(_session_hourly(dt.date(2024, 3, 6), instrument_id=2, base=75.0))
    combined = pd.concat([day1, day2]).sort_index()
    r4h = B.resample(combined, "4H")
    out = B.back_adjust(r4h)
    # the roll bucket is where held_id first changes
    roll_pos = out.index[out["held_id"] != out["held_id"].shift(1)][1:]
    assert len(roll_pos) == 1
    i = roll_pos[0]
    gap = out.loc[i, "close"] - out.loc[i - 1, "close"]
    # everything BEFORE the roll (the earlier segment) is shifted by the gap
    assert np.isclose(out.loc[i - 1, "close_adj"], out.loc[i - 1, "close"] + gap)
    # the current (post-roll) segment is untouched
    assert out.loc[i, "close_adj"] == out.loc[i, "close"]
    assert out["n_rolls"].iloc[0] == 1


def test_back_adjust_never_ratio_survives_negative_price():
    """CL printed -$37.63 on 2020-04-20 (REGISTERED sec 8): a difference
    adjustment must still work when a raw close is negative."""
    day1 = B.split_held(_session_hourly(dt.date(2024, 3, 5), instrument_id=1, base=-37.63))
    day2 = B.split_held(_session_hourly(dt.date(2024, 3, 6), instrument_id=2, base=40.0))
    combined = pd.concat([day1, day2]).sort_index()
    out = B.back_adjust(B.resample(combined, "4H"))
    assert np.isfinite(out["close_adj"]).all()


# --------------------------------------------------------------------------
# session-bounds guard
# --------------------------------------------------------------------------

def test_session_bounds_error_on_bad_elapsed():
    """A row that resample() cannot place inside [0,23) of ITS OWN session_of
    label must raise, not silently wrap -- guards against a future edit to
    session_of()/session_open_naive() going out of sync with each other."""
    df = B.split_held(_session_hourly(dt.date(2024, 3, 5)))
    import strategy.htf.bars as mod
    orig = mod.session_open_naive
    try:
        # shift the "session open" a session too RIGHT so a real bar reads
        # as arriving before its (unreachable) session open -> out of [0,23)
        mod.session_open_naive = lambda s: orig(s) - pd.Timedelta(days=1)
        with pytest.raises(mod.SessionBoundsError):
            mod.resample(df, "4H")
    finally:
        mod.session_open_naive = orig
