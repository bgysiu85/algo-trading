#!/usr/bin/env python3
"""Can the archive cross-check say "clean" — and does it say what that means?

This module exists because three names were checked by hand and all three were
wrong. The risk with a follow-up measurement is the opposite of the usual one:
not that it fails to find the defect, but that it finds it everywhere because
the tolerance is too tight, or nowhere because it is too loose.

The load-bearing tests here are:
  * a clean archive returns nothing AND the report refuses to read that as
    "the data is fine" -- because two files can agree and both be wrong
  * a one-cent overshoot is not a defect
  * the ISPC shape (a print above the day's high) IS a defect
  * a row is counted once, on its worse side, never twice
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import tape_conflict as T


def bars(spec, symbol="AAA"):
    """spec = [(high, low)] -> minute bars for one symbol."""
    idx = pd.date_range("2026-09-08 08:00", periods=len(spec), freq="1min",
                        tz="UTC")
    return pd.DataFrame({"symbol": symbol,
                         "high": [h for h, _ in spec],
                         "low": [l for _, l in spec],
                         "close": [(h + l) / 2 for h, l in spec]}, index=idx)


def daily(high, low, close=None, symbol="AAA"):
    return pd.DataFrame([{"symbol": symbol, "date": "2026-09-08", "high": high,
                          "low": low, "close": close if close is not None
                          else (high + low) / 2}])


# --- the tolerance -----------------------------------------------------------

def test_a_print_inside_the_range_is_clean():
    assert T.conflicts(bars([(1.90, 1.60)]), daily(1.94, 1.55)) == []


def test_one_cent_over_is_not_a_defect():
    """Rounding, not corruption. Counting these would bury the real rows."""
    assert T.conflicts(bars([(1.95, 1.60)]), daily(1.94, 1.55)) == []


def test_the_tolerance_scales_with_the_range_not_the_price():
    """A $200 name with a $40 range gets 20c of slack; a $2 name with a 4c
    range gets the one-cent floor, not 0.02c."""
    assert T.tolerance(200.0, 160.0) == pytest.approx(0.20)
    assert T.tolerance(2.00, 1.96) == pytest.approx(T.TOL_MIN)


# --- the shapes that are defects --------------------------------------------

def test_the_ISPC_shape_is_caught():
    """Premarket printed 2.11 on a day whose own bar tops out at 1.94."""
    out = T.conflicts(bars([(2.11, 2.05)]), daily(1.94, 1.55))
    assert len(out) == 1
    assert out[0]["kind"].startswith("ABOVE")
    assert out[0]["gap"] == pytest.approx(0.17)
    assert out[0]["pct"] == pytest.approx(0.17 / 1.94 * 100)


def test_a_print_below_the_days_low_is_caught_too():
    out = T.conflicts(bars([(1.60, 1.20)]), daily(1.94, 1.55))
    assert len(out) == 1
    assert out[0]["kind"].startswith("BELOW")


def test_a_row_breaching_both_sides_is_counted_ONCE_on_its_worse_side():
    """Otherwise one bad symbol-day inflates the share that drives the verdict."""
    out = T.conflicts(bars([(2.50, 1.00)]), daily(1.94, 1.55))
    assert len(out) == 1
    assert out[0]["kind"].startswith("ABOVE")      # 0.56 over vs 0.55 under
    assert out[0]["gap"] == pytest.approx(0.56)


def test_the_high_is_tested_not_only_the_close():
    """A spike that did not end a minute is still a print, and the screen's
    cumulative volume counted it."""
    b = bars([(2.11, 1.60), (1.80, 1.70)])        # closes are 1.855 / 1.75
    assert T.conflicts(b, daily(1.94, 1.55))


def test_a_symbol_missing_from_either_file_is_not_a_conflict():
    assert T.conflicts(bars([(9.0, 8.0)], "ZZZ"), daily(1.94, 1.55)) == []
    assert T.conflicts(pd.DataFrame(), daily(1.94, 1.55)) == []


# --- the report --------------------------------------------------------------

def test_a_clean_result_REFUSES_to_read_as_the_data_is_fine():
    """The most important test in the file. A zero here bounds one detectable
    class; it does not clear the archive, and the report must say so."""
    text = "\n".join(T.render([], 5000, 550, 0, 0.1))
    assert "DOES NOT CLEAR THE ARCHIVE" in text
    assert "both be wrong" in text


def test_the_bands_are_read_off_symbol_days():
    def band(n, sd):
        rows = [{"symbol": f"S{i}", "date": "2026-09-08", "kind": "ABOVE x",
                 "gap": 1.0, "ref": 2.0, "pct": 50.0, "pm_high": 3.0,
                 "pm_low": 1.0, "daily_high": 2.0, "daily_low": 1.0,
                 "daily_close": 1.5, "bars": 10} for i in range(n)]
        return "\n".join(T.render(rows, sd, 550, 0, 0.1))
    assert "SPORADIC" in band(4, 1000)              # 0.4%
    assert "MATERIAL" in band(50, 1000)             # 5%
    assert "DOES NOT SUPPORT" in band(200, 1000)    # 20%


def test_the_report_refuses_to_name_which_file_is_wrong():
    rows = [{"symbol": "AAA", "date": "2026-09-08", "kind": "ABOVE the day's "
             "high", "gap": 0.17, "ref": 1.94, "pct": 8.8, "pm_high": 2.11,
             "pm_low": 2.05, "daily_high": 1.94, "daily_low": 1.55,
             "daily_close": 1.59, "bars": 10}]
    text = "\n".join(T.render(rows, 1000, 550, 0, 0.1))
    assert "Not a verdict on WHICH file is wrong" in text
    assert "Not a repair" in text


def test_untested_sessions_are_named_rather_than_counted_clean():
    text = "\n".join(T.render([], 100, 540, 10, 0.1))
    assert "10 session(s) had a slice but no daily bars" in text
