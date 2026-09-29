"""W15-0019 subitem 3: unit tests for common/tl_v1_parity.py's diff/report
logic (not the archive load -- that needs Ben's real data and is exercised
on his machine via the CLI). Synthetic frames only."""
from __future__ import annotations

import numpy as np
import pandas as pd

import sys
import types
from unittest.mock import patch

from common.tl_v1_parity import (
    diff, build_report, load_tv_export, _find_col, _parse_tv_time, python_side,
)


def test_python_side_uses_raw_ohlc_not_the_adjusted_signal_series():
    # REGISTERED_tl_v1.md sec 5.1 G3 says this comparison runs "back-adjustment
    # off" -- python_side must build the line from ro/rh/rl/rc (raw), never
    # the difference-back-adjusted open/high/low/close strategy/tl_v0/bars.py
    # also carries (that series is for the real W15-0020 backtest, not this
    # gate). Regression form: the raw series has two clean high pivots (a
    # valid anchor pair exists); the "adjusted" series is a pure monotonic
    # ramp, which structurally cannot contain an interior pivot at all -- if
    # python_side ever read the adjusted columns instead, the line would be
    # all-NaN throughout.
    n = 20
    dates = pd.bdate_range("2016-01-04", periods=n)
    rh = np.full(n, 100.0)
    rh[4] = 110.0
    rh[12] = 105.0
    frame = pd.DataFrame({
        "date": dates,
        "ro": np.full(n, 97.0), "rh": rh, "rl": np.full(n, 95.0), "rc": np.full(n, 97.0),
        "open": np.linspace(200.0, 300.0, n), "high": np.linspace(201.0, 301.0, n),
        "low": np.linspace(199.0, 299.0, n), "close": np.linspace(200.0, 300.0, n),
    })
    fake_mb = types.SimpleNamespace(frame=frame)

    with patch("strategy.tl_v0.spec.MARKETS", {"TEST": object()}), \
         patch("strategy.tl_v0.bars.load_market", return_value=(fake_mb, None)):
        out = python_side("unused-archive", "TEST", pivlen=2)

    assert out["py_resV"].notna().any(), (
        "no resistance line armed at all -- python_side is reading the "
        "adjusted (monotonic, pivot-free) columns instead of the raw ones")


def _dates(n, start="2016-01-04"):
    return pd.bdate_range(start, periods=n)


def test_matching_bars_all_flagged_match():
    d = _dates(10)
    tv = pd.DataFrame({"date": d, "tv_resV": np.linspace(100, 101, 10), "tv_supV": [np.nan] * 10})
    py = pd.DataFrame({"date": d, "py_resV": np.linspace(100, 101, 10), "py_supV": [np.nan] * 10})
    merged = diff(tv, py, str(d[0].date()), str(d[-1].date()), tol=0.01)
    assert (merged["res_state"] == "match_on").all()
    assert (merged["sup_state"] == "match_off").all()


def test_value_mismatch_beyond_tolerance_is_flagged():
    d = _dates(5)
    tv = pd.DataFrame({"date": d, "tv_resV": [100.0] * 5, "tv_supV": [np.nan] * 5})
    py = pd.DataFrame({"date": d, "py_resV": [100.0, 100.0, 100.5, 100.0, 100.0], "py_supV": [np.nan] * 5})
    merged = diff(tv, py, str(d[0].date()), str(d[-1].date()), tol=0.01)
    assert list(merged["res_state"]) == ["match_on", "match_on", "value_mismatch", "match_on", "match_on"]
    assert merged.loc[2, "res_delta"] == 0.5


def test_state_mismatch_when_one_side_armed_and_other_not():
    d = _dates(3)
    tv = pd.DataFrame({"date": d, "tv_resV": [np.nan, 100.0, 100.0], "tv_supV": [np.nan] * 3})
    py = pd.DataFrame({"date": d, "py_resV": [100.0, 100.0, np.nan], "py_supV": [np.nan] * 3})
    merged = diff(tv, py, str(d[0].date()), str(d[-1].date()), tol=0.01)
    assert list(merged["res_state"]) == ["state_mismatch", "match_on", "state_mismatch"]


def test_diff_no_overlap_reports_both_sides_actual_ranges():
    tv_dates = _dates(5, start="2023-01-02")
    py_dates = _dates(5, start="2016-01-04")
    tv = pd.DataFrame({"date": tv_dates, "tv_resV": [100.0] * 5, "tv_supV": [np.nan] * 5})
    py = pd.DataFrame({"date": py_dates, "py_resV": [100.0] * 5, "py_supV": [np.nan] * 5})
    try:
        diff(tv, py, "2015-01-01", "2019-12-31", tol=0.01)
        assert False, "expected SystemExit"
    except SystemExit as e:
        msg = str(e)
        assert "tv-csv covers" in msg and "2023-01-02" in msg
        assert "python side covers" in msg and "2016-01-04" in msg
        assert "Scroll/drag the chart back" in msg


def test_diff_restricts_to_requested_window():
    d = _dates(10)
    tv = pd.DataFrame({"date": d, "tv_resV": [100.0] * 10, "tv_supV": [np.nan] * 10})
    py = pd.DataFrame({"date": d, "py_resV": [100.0] * 10, "py_supV": [np.nan] * 10})
    merged = diff(tv, py, str(d[2].date()), str(d[4].date()), tol=0.01)
    assert len(merged) == 3


def test_report_flags_no_mismatch_case_cleanly():
    d = _dates(5)
    tv = pd.DataFrame({"date": d, "tv_resV": [100.0] * 5, "tv_supV": [np.nan] * 5})
    py = pd.DataFrame({"date": d, "py_resV": [100.0] * 5, "py_supV": [np.nan] * 5})
    merged = diff(tv, py, str(d[0].date()), str(d[-1].date()), tol=0.01)
    text = build_report(merged, "CL", 5, str(d[0].date()), str(d[-1].date()), 0.01, "fake.csv")
    assert "No mismatches on either line" in text
    assert "Zero mismatches" in text


def test_report_lists_mismatch_dates_by_month_when_present():
    d = _dates(5)
    tv = pd.DataFrame({"date": d, "tv_resV": [100.0, 100.0, 105.0, 100.0, 100.0], "tv_supV": [np.nan] * 5})
    py = pd.DataFrame({"date": d, "py_resV": [100.0] * 5, "py_supV": [np.nan] * 5})
    merged = diff(tv, py, str(d[0].date()), str(d[-1].date()), tol=0.01)
    text = build_report(merged, "CL", 5, str(d[0].date()), str(d[-1].date()), 0.01, "fake.csv")
    assert "mismatched bars, by month" in text
    assert "2016-01" in text


def test_find_col_matches_loosely_on_title_words():
    cols = ["time", "open", "high", "low", "close", "Resistance (her line)", "Support (her line)"]
    assert _find_col(cols, "resistance") == "Resistance (her line)"
    assert _find_col(cols, "support") == "Support (her line)"
    assert _find_col(cols, "time") == "time"


def test_parse_tv_time_unix_seconds_lands_on_the_right_year_not_1970():
    # 2015-01-01T00:00:00Z and 2019-12-31T00:00:00Z as UNIX SECONDS, exactly
    # what TradingView's "Time format (UTC): UNIX timestamp" export option
    # gives -- the regression this guards is pandas silently reading a bare
    # integer column as NANOSECONDS since epoch (landing on 1970-01-01).
    raw = pd.Series([1420070400, 1577750400])
    ts = _parse_tv_time(raw)
    assert ts.dt.year.tolist() == [2015, 2019]


def test_load_tv_export_handles_unix_seconds_csv(tmp_path):
    csv_path = tmp_path / "tv_unix.csv"
    csv_path.write_text(
        "time,open,high,low,close,Resistance (her line),Support (her line)\n"
        "1420070400,50,51,49,50.5,,48.0\n"
        "1420156800,50.5,52,50,51.5,55.0,\n"
    )
    df = load_tv_export(str(csv_path))
    assert df["date"].dt.year.tolist() == [2015, 2015]
    assert df.loc[0, "tv_supV"] == 48.0 and df.loc[1, "tv_resV"] == 55.0


def test_load_tv_export_accepts_iso_time_and_loose_headers(tmp_path):
    csv_path = tmp_path / "tv.csv"
    csv_path.write_text(
        "time,open,high,low,close,Resistance (her line),Support (her line)\n"
        "2016-01-04,50,51,49,50.5,,48.0\n"
        "2016-01-05,50.5,52,50,51.5,55.0,\n"
    )
    df = load_tv_export(str(csv_path))
    assert list(df.columns) == ["date", "tv_resV", "tv_supV"]
    assert len(df) == 2
    assert np.isnan(df.loc[0, "tv_resV"]) and df.loc[0, "tv_supV"] == 48.0
    assert df.loc[1, "tv_resV"] == 55.0 and np.isnan(df.loc[1, "tv_supV"])
