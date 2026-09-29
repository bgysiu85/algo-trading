"""W15-0019 subitem 3: unit tests for common/tl_v1_parity.py's diff/report
logic (not the archive load -- that needs Ben's real data and is exercised
on his machine via the CLI). Synthetic frames only."""
from __future__ import annotations

import numpy as np
import pandas as pd

from common.tl_v1_parity import diff, build_report, load_tv_export, _find_col


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
