"""strategy.h60.bars -- the 60-minute grid (REGISTERED_h60_v0.md §2.2)."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from strategy.h60 import bars as B


def one_minute(day: dt.date, symbols=("AAA",), start="09:30", end="16:00",
               skip=()):
    """Every minute in [start, end) ET, price = minute number, volume 1."""
    t0 = pd.Timestamp(f"{day} {start}", tz=B.ET)
    t1 = pd.Timestamp(f"{day} {end}", tz=B.ET)
    idx = pd.date_range(t0, t1, freq="1min", inclusive="left")
    rows = []
    for s in symbols:
        for k, t in enumerate(idx):
            if t.strftime("%H:%M") in skip:
                continue
            rows.append((t.tz_convert("UTC"), s, 100 + k, 100.5 + k, 99.5 + k, 100.2 + k, 1.0))
    df = pd.DataFrame(rows, columns=["ts", "symbol", "open", "high", "low", "close", "volume"])
    return df.set_index("ts")


def test_primary_grid_slots_and_the_short_last_bar():
    assert list(B.bucket_of(np.array([570, 629, 630, 929, 930, 959]), "primary")) == [0, 0, 1, 5, 6, 6]
    assert [B.slot_start_min(s, "primary") for s in range(7)] == [570, 630, 690, 750, 810, 870, 930]
    assert B.slot_end_min(6, "primary") == 960
    assert B.half_hours(6, "primary") == [930]
    assert B.half_hours(0, "primary") == [570, 600]


def test_fallback_grid_is_a_half_hour_then_clock_hours():
    assert list(B.bucket_of(np.array([570, 599, 600, 659, 660, 959]), "fallback")) == [0, 0, 1, 1, 2, 6]
    assert [B.slot_start_min(s, "fallback") for s in range(7)] == [570, 600, 660, 720, 780, 840, 900]
    assert B.half_hours(0, "fallback") == [570]
    assert B.half_hours(6, "fallback") == [900, 930]


def test_resample_day_primary():
    day = dt.date(2021, 3, 3)
    out = B.resample_day(one_minute(day, ("AAA", "BBB")), "primary")
    a = out[out.symbol == "AAA"].reset_index(drop=True)
    assert list(a["bar"]) == list(range(7))
    assert list(a["n_min"]) == [60, 60, 60, 60, 60, 60, 30]
    # first minute's open, last minute's close, extremes over the bucket
    assert a.loc[0, "open"] == 100 and a.loc[0, "close"] == 100.2 + 59
    assert a.loc[0, "high"] == 100.5 + 59 and a.loc[0, "low"] == 99.5
    assert a.loc[6, "close"] == 100.2 + 389
    assert a.loc[1, "t_open"] == pd.Timestamp(f"{day} 10:30", tz=B.ET).tz_convert("UTC")
    assert (out["session"] == day).all()


def test_resample_day_fallback_first_bar_is_thirty_minutes():
    day = dt.date(2021, 3, 3)
    a = B.resample_day(one_minute(day), "fallback")
    assert list(a["n_min"]) == [30, 60, 60, 60, 60, 60, 60]
    assert a.loc[1, "t_open"] == pd.Timestamp(f"{day} 10:00", tz=B.ET).tz_convert("UTC")


def test_dst_is_handled_in_et_not_utc():
    # 2021-03-12 is EST (UTC-5), 2021-03-15 is EDT (UTC-4): 09:30 ET moves by
    # an hour in UTC and must still land in slot 0.
    for day in (dt.date(2021, 3, 12), dt.date(2021, 3, 15)):
        a = B.resample_day(one_minute(day), "primary")
        assert a.loc[0, "n_min"] == 60
        assert a.loc[0, "t_open"].tz_convert(B.ET).strftime("%H:%M") == "09:30"


def test_minutes_outside_rth_are_dropped_and_empty_buckets_vanish():
    day = dt.date(2021, 3, 3)
    pre = one_minute(day, start="08:00", end="09:30")
    rth = one_minute(day, skip=tuple(f"11:{m:02d}" for m in range(30, 60))
                     + tuple(f"12:{m:02d}" for m in range(0, 30)))
    a = B.resample_day(pd.concat([pre, rth]), "primary")
    assert list(a["bar"]) == [0, 1, 3, 4, 5, 6]      # 11:30 bucket had no minute


def test_half_day_ends_at_one():
    day = dt.date(2021, 11, 26)
    a = B.resample_day(one_minute(day, end="13:00"), "primary")
    assert list(a["bar"]) == [0, 1, 2, 3]
    assert list(a["n_min"]) == [60, 60, 60, 30]


def test_one_session_at_a_time():
    x = pd.concat([one_minute(dt.date(2021, 3, 3)), one_minute(dt.date(2021, 3, 4))])
    with pytest.raises(ValueError, match="one at a time"):
        B.resample_day(x, "primary")


def test_no_grid_recorded_refuses_before_any_bar_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "GRID", None)
    calls = []
    with pytest.raises(B.GridNotChosen, match="amendment B"):
        B.build_cache(tmp_path, tmp_path, read=lambda p: calls.append(p))
    with pytest.raises(B.GridNotChosen):
        B.load_cache(tmp_path)
    assert calls == []


def test_the_committed_grid_is_still_unrecorded_until_amendment_b():
    """Flip this test in the amendment-B commit, not before: a grid set in
    code without the amendment text is exactly what §2.2 forbids."""
    assert B.GRID is None


def test_build_and_load_cache_roundtrip(tmp_path):
    rth = tmp_path / "rth"
    rth.mkdir()
    days = [dt.date(2021, 3, 3), dt.date(2021, 3, 4), dt.date(2022, 1, 5)]
    frames = {d: one_minute(d, ("AAA", "BBB")) for d in days}
    for d in days:
        (rth / f"{d}.dbn.zst").write_bytes(b"x")
    (rth / "2021-03-05.dbn.zst").write_bytes(b"x")          # a holiday: empty

    def read(p):
        d = dt.date.fromisoformat(p.name[:10])
        return frames.get(d, pd.DataFrame())

    res = B.build_cache(rth, tmp_path / "root", "primary", read=read)
    assert res["empty_days"] == 1
    assert res["rows_by_year"] == {2021: 28, 2022: 14}
    df = B.load_cache(tmp_path / "root", "primary")
    assert len(df) == 42
    assert df["t_open"].dt.tz is not None
    assert list(df.columns[:4]) == ["symbol", "session", "bar", "t_open"]
