#!/usr/bin/env python3
"""strategy/orb/sip_summary.py -- the one row per symbol-day everything reads.

The failures worth catching here are the silent ones: an opening range that is
one bar too long, a summary that includes pre- or post-market bars because the
day file happened to carry them, and a coverage figure that hides a halt.
"""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.orb import sip_summary as S

ET = "America/New_York"


def bars(day, rows):
    """rows: (HH:MM, o, h, l, c, v). Index is UTC, as read_dbn returns."""
    idx = pd.to_datetime([f"{day} {t}" for t, *_ in rows]).tz_localize(ET).tz_convert("UTC")
    return pd.DataFrame(
        {"open": [r[1] for r in rows], "high": [r[2] for r in rows],
         "low": [r[3] for r in rows], "close": [r[4] for r in rows],
         "volume": [float(r[5]) for r in rows],
         "symbol": [r[6] if len(r) > 6 else "AAA" for r in rows]}, index=idx)


DAY = "2025-03-05"


def test_the_five_minute_range_is_0930_to_0934_and_0935_is_outside_it():
    """`ts_event` is the interval START, so the bar stamped 09:34 is the last
    minute of a 5-minute range and 09:35 is the first bar that can trigger."""
    df = bars(DAY, [("09:30", 10, 11, 9.5, 10.5, 100),
                    ("09:31", 10.5, 10.9, 10.4, 10.6, 50),
                    ("09:34", 10.6, 12.0, 10.5, 11.0, 70),
                    ("09:35", 11.0, 20.0, 1.0, 12.0, 900)])
    r = S.summarise(df, DAY).iloc[0]
    assert (r.or5_open, r.or5_close) == (10.0, 11.0)
    assert (r.or5_high, r.or5_low) == (12.0, 9.5)
    assert r.or5_volume == 220, "the 09:35 bar is not in the range"
    assert r.rth_high == 20.0 and r.rth_close == 12.0


def test_the_fifteen_minute_range_is_the_same_rule_at_0944():
    df = bars(DAY, [("09:30", 10, 11, 9.5, 10.5, 100),
                    ("09:44", 10.5, 13.0, 10.0, 12.0, 60),
                    ("09:45", 12.0, 14.0, 11.0, 13.0, 80)])
    r = S.summarise(df, DAY).iloc[0]
    assert r.or15_high == 13.0 and r.or15_volume == 160
    assert r.or5_high == 11.0, "the 5-minute range must not see the 09:44 bar"


def test_bars_outside_rth_or_from_another_date_never_reach_a_row():
    """The 09:30-16:00 pull is clean today. A future window pull, or a file
    whose lookback spills a neighbouring session, must not change a summary."""
    df = pd.concat([
        bars(DAY, [("08:00", 5, 99, 5, 90, 5000)]),
        bars(DAY, [("09:30", 10, 11, 9.5, 10.5, 100), ("15:59", 10.5, 10.6, 10.4, 10.55, 200)]),
        bars(DAY, [("16:00", 10.55, 50, 1, 40, 9000)]),
        bars("2025-03-06", [("09:30", 1, 2, 0.5, 1.5, 77)]),
    ])
    out = S.summarise(df, DAY)
    assert len(out) == 1
    r = out.iloc[0]
    assert r.rth_high == 11.0 and r.rth_close == 10.55 and r.rth_volume == 300
    assert r.rth_bars == 2


def test_a_missing_0930_bar_is_visible_rather_than_invented():
    """No bar is written for a minute with no trade, so a name that starts at
    09:47 must say so -- the registration's $5 open reads `open`, and a row
    that quietly reported the 09:47 open as the session open would put a name
    in the universe on a price from seventeen minutes later."""
    df = bars(DAY, [("09:47", 7.0, 7.2, 6.9, 7.1, 300)])
    r = S.summarise(df, DAY).iloc[0]
    assert r.first_bar == 9 * 60 + 47
    assert pd.isna(r.or5_open) and pd.isna(r.or5_volume)


def test_the_halt_proxy_counts_the_largest_gap():
    """Section 3.6: a halt is not modelled, it is counted."""
    df = bars(DAY, [("09:30", 10, 11, 9.5, 10.5, 100),
                    ("09:31", 10.5, 10.6, 10.4, 10.5, 10),
                    ("10:00", 10.5, 10.6, 10.4, 10.5, 10),
                    ("10:01", 10.5, 10.6, 10.4, 10.5, 10)])
    r = S.summarise(df, DAY).iloc[0]
    assert r.max_gap_min == 28
    assert S.summarise(bars(DAY, [("09:30", 1, 1, 1, 1, 1)]), DAY).iloc[0].max_gap_min == 0


def test_symbols_are_kept_apart():
    df = pd.concat([
        bars(DAY, [("09:30", 10, 11, 9.5, 10.5, 100, "AAA"),
                   ("09:31", 10.5, 10.6, 10.4, 10.5, 10, "AAA")]),
        bars(DAY, [("09:30", 50, 55, 49, 54, 900, "BBB")]),
    ])
    out = S.summarise(df, DAY).set_index("symbol")
    assert out.loc["AAA"].rth_volume == 110 and out.loc["BBB"].rth_volume == 900
    assert out.loc["BBB"].or5_high == 55


def test_an_empty_session_returns_the_columns_and_no_rows():
    out = S.summarise(pd.DataFrame(columns=["open", "high", "low", "close", "volume", "symbol"],
                                   index=pd.DatetimeIndex([], tz="UTC")), DAY)
    assert list(out.columns) == S.COLUMNS and out.empty


def test_the_day_file_name_matches_the_archive_layout(tmp_path):
    p = S.day_file(tmp_path, "XNAS.BASIC", "2025-03-05")
    assert p.name == "2025-03-05_0930_1600.dbn.zst"
    assert p.parent.name == "ohlcv-1m"


def test_build_skips_what_is_already_written_and_force_rewrites(tmp_path, monkeypatch):
    out = tmp_path / "summary"; out.mkdir()
    (out / "2025-03-05.csv.gz").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(S, "_one", lambda a: (calls.append(a[2]), (a[2], 1, ""))[1])
    st = S.build(tmp_path, "XNAS.BASIC", ["2025-03-05", "2025-03-06"], out, 1, False)
    assert calls == ["2025-03-06"] and st["already"] == 1 and st["written"] == 1
    calls.clear()
    S.build(tmp_path, "XNAS.BASIC", ["2025-03-05", "2025-03-06"], out, 1, True)
    assert calls == ["2025-03-05", "2025-03-06"]


def test_a_failed_session_is_reported_and_does_not_stop_the_rest(tmp_path, monkeypatch):
    out = tmp_path / "s"
    monkeypatch.setattr(S, "_one",
                        lambda a: (a[2], 0, "boom") if a[2].endswith("06") else (a[2], 5, ""))
    st = S.build(tmp_path, "XNAS.BASIC", ["2025-03-05", "2025-03-06"], out, 1, False)
    assert st["written"] == 1 and st["failed"] == [("2025-03-06", "boom")]
