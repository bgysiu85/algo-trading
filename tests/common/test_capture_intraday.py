#!/usr/bin/env python3
"""Capture measured at intraday cutoffs, where both legs must mean the same
window or the ratio is nonsense that still prints.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

from common import capture_intraday as I

ET = ZoneInfo("America/New_York")


def minute_frame(rows):
    """rows: (symbol, 'HH:MM' ET, volume) on 2025-04-09."""
    idx, recs = [], []
    for sym, hhmm, vol in rows:
        ts = pd.Timestamp(f"2025-04-09 {hhmm}", tz=ET).tz_convert("UTC")
        idx.append(ts)
        recs.append({"symbol": sym, "volume": vol})
    df = pd.DataFrame(recs, index=pd.DatetimeIndex(idx))
    et = df.index.tz_convert(ET)
    return df.assign(_day=et.strftime("%Y-%m-%d"),
                     _min=et.hour * 60 + et.minute)


def test_each_cutoff_accumulates_from_the_session_open():
    """Both legs must be cumulative from 04:00 or the ratio compares a window
    on one tape against a different window on the other -- a number that looks
    like capture and is not."""
    f = minute_frame([("AAA", "05:00", 100), ("AAA", "08:00", 200),
                      ("AAA", "10:30", 400), ("AAA", "17:00", 800)])
    out = I.minute_cumulative(f, "2025-04-09", {"AAA"})
    assert out["AAA"]["07:00"] == 100            # 05:00 only
    assert out["AAA"]["09:30"] == 300            # + 08:00
    assert out["AAA"]["11:00"] == 700            # + 10:30
    assert out["AAA"]["20:00"] == 1500           # + 17:00


def test_bars_before_the_session_are_never_counted():
    f = minute_frame([("AAA", "03:00", 999), ("AAA", "05:00", 100)])
    out = I.minute_cumulative(f, "2025-04-09", {"AAA"})
    assert out["AAA"]["20:00"] == 100


def test_a_cutoff_with_no_bars_yet_is_absent_not_zero():
    """A symbol with no pre-market prints has NO capture ratio at 07:00. Zero
    would drag every early-session percentile towards a value that means
    'nothing traded', not 'the tape missed it'."""
    f = minute_frame([("AAA", "10:00", 500)])
    out = I.minute_cumulative(f, "2025-04-09", {"AAA"})
    assert "07:00" not in out["AAA"]
    assert "09:30" not in out["AAA"]
    assert out["AAA"]["11:00"] == 500


def test_other_days_and_other_symbols_are_excluded():
    f = minute_frame([("AAA", "10:00", 100), ("BBB", "10:00", 900)])
    out = I.minute_cumulative(f, "2025-04-09", {"AAA"})
    assert set(out) == {"AAA"}
    assert I.minute_cumulative(f, "2025-04-10", {"AAA"}) == {}


# --- the report -------------------------------------------------------------

def rows_at(open_ratio, close_ratio, n=50):
    return [{"symbol": f"S{i}", "date": "2025-04-09",
             "09:30": open_ratio, "20:00": close_ratio} for i in range(n)]


def test_worse_capture_early_is_called_out_as_the_binding_case():
    """This is the outcome that would mean the daily 4.7% UNDERSTATES the error
    where the screen actually reads."""
    out = I.render(rows_at(0.02, 0.05), 0, 1.0)
    assert "CAPTURE IS WORSE EARLY" in out


def test_better_capture_early_is_reported_too():
    out = I.render(rows_at(0.09, 0.05), 0, 1.0)
    assert "CAPTURE IS BETTER EARLY" in out


def test_a_flat_profile_says_the_daily_figure_carries_over():
    out = I.render(rows_at(0.047, 0.047), 0, 1.0)
    assert "ROUGHLY FLAT" in out


def test_an_empty_result_says_so_rather_than_printing_empty_quantiles():
    assert "NO ROWS MATCHED" in I.render([], 100, 1.0)


def test_a_cutoff_with_no_observations_is_labelled_rather_than_blank():
    rows = [{"symbol": "A", "date": "2025-04-09", "20:00": 0.05}]
    out = I.render(rows, 0, 1.0)
    assert "(no data)" in out


def test_a_thinly_covered_cutoff_is_flagged_as_a_selection_effect():
    """At 09:30 only 135 of 182 symbol-days had data on both sides. The
    excluded ones are those EQUS.MINI saw LEAST, so dropping them biases the
    early medians upward -- the figure is conditional, and a reader comparing
    it against the 20:00 column needs to know that."""
    rows = ([{"symbol": f"S{i}", "date": "2025-04-09",
              "09:30": 0.02, "20:00": 0.05} for i in range(50)]
            + [{"symbol": f"T{i}", "date": "2025-04-09", "20:00": 0.05}
               for i in range(50)])
    out = I.render(rows, 0, 1.0)
    assert "selection effect" in out
    assert "09:30" in out and "50% of symbol-days" in out


def test_full_coverage_says_no_cutoff_is_conditioned():
    rows = [{"symbol": f"S{i}", "date": "2025-04-09",
             **{lab: 0.05 for _, lab in I.CUTOFFS}} for i in range(20)]
    assert "no cutoff below is materially conditioned" in I.render(rows, 0, 1.0)


def test_the_premarket_ladder_covers_the_hours_before_the_open():
    """07:00 alone came back with n=0 on the first pass, leaving the whole
    pre-market as one unlit gap between 04:00 and 09:30."""
    labels = [lab for _, lab in I.CUTOFFS]
    assert ["07:00", "08:00", "09:00", "09:30"] == labels[:4]
