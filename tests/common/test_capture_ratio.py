#!/usr/bin/env python3
"""The confounds that would make this measure the wrong thing convincingly.

Every test here pins a case where a plausible number comes out of a broken
comparison -- which is the failure mode this project keeps hitting, not a
crash.
"""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from common import capture_ratio as C


def stats_frame(rows):
    """rows: (symbol, 'HH:MM' ET, quantity, stat_type)."""
    recs = []
    for sym, hhmm, qty, stype in rows:
        h, m = hhmm.split(":")
        ts = pd.Timestamp(f"2025-04-09 {h}:{m}", tz=C.ET).tz_convert("UTC")
        recs.append({"ts_event": ts, "symbol": sym, "quantity": qty,
                     "stat_type": stype})
    df = pd.DataFrame(recs)
    df.index = pd.DatetimeIndex(df["ts_event"])      # to_df indexes on ts_recv
    return df


# --- the cutoff ------------------------------------------------------------

def test_the_cutoff_separates_rth_from_the_full_session():
    """CLEARED_VOLUME runs 04:00-20:00 while a daily bar may cover only regular
    hours. Comparing a 16-hour figure to a 6.5-hour one measures SESSION
    DEFINITION and calls it tape coverage -- a real-looking number about
    entirely the wrong thing."""
    f = stats_frame([("AAA", "05:00", 100, 6),
                     ("AAA", "12:00", 500, 6),
                     ("AAA", "18:00", 900, 6)])
    assert C.cleared_by_cutoff(f, C.RTH_CLOSE_MIN) == {"AAA": 500}
    assert C.cleared_by_cutoff(f, C.SESSION_END_MIN) == {"AAA": 900}


def test_prints_before_the_session_opens_are_excluded():
    f = stats_frame([("AAA", "03:00", 999, 6), ("AAA", "05:00", 100, 6)])
    assert C.cleared_by_cutoff(f, C.SESSION_END_MIN) == {"AAA": 100}


def test_only_cleared_volume_is_counted():
    """CLOSE_PRICE records carry quantity 2147483647 -- INT32_MAX, the
    'undefined' sentinel. Summing across stat types would put two billion
    shares into every symbol-day."""
    f = stats_frame([("AAA", "12:00", 500, 6),
                     ("AAA", "16:30", 2147483647, 11)])
    assert C.cleared_by_cutoff(f, C.SESSION_END_MIN) == {"AAA": 500}


def test_a_frame_with_no_cleared_volume_yields_nothing_rather_than_zero():
    f = stats_frame([("AAA", "12:00", 2147483647, 11)])
    assert C.cleared_by_cutoff(f, C.SESSION_END_MIN) == {}


def test_the_max_is_taken_not_the_last_row():
    """The series was monotonic on the probe day, but a revision arriving out
    of order would silently lower the total if the last row were trusted."""
    f = stats_frame([("AAA", "12:00", 900, 6), ("AAA", "12:01", 400, 6)])
    assert C.cleared_by_cutoff(f, C.SESSION_END_MIN) == {"AAA": 900}


# --- the session verdict ---------------------------------------------------

def test_a_daily_bar_matching_the_full_minute_sum_is_called_full():
    rows = [{"daily_bar": 1000, "minutes_full": 1000, "minutes_rth": 600}] * 5
    verdict, prose = C.session_verdict(rows)
    assert verdict == "full" and "20:00" in prose


def test_a_daily_bar_matching_only_rth_is_called_rth_and_warns():
    """This is the outcome that would invalidate the 20:00 column, so it has to
    say so rather than quietly preferring the other number."""
    rows = [{"daily_bar": 600, "minutes_full": 1000, "minutes_rth": 600}] * 5
    verdict, prose = C.session_verdict(rows)
    assert verdict == "rth" and "UNDERSTATES" in prose


def test_matching_neither_refuses_to_endorse_any_figure():
    rows = [{"daily_bar": 800, "minutes_full": 1000, "minutes_rth": 600}] * 5
    verdict, prose = C.session_verdict(rows)
    assert verdict == "neither" and "should be quoted" in prose


def test_no_sample_is_unknown_not_an_assumption():
    verdict, prose = C.session_verdict([])
    assert verdict == "unknown" and "UNVERIFIED" in prose


# --- the decomposition -----------------------------------------------------

def test_a_stable_per_symbol_capture_reads_as_between_symbol():
    """If capture is a per-symbol constant it cancels out of RVOL, which is the
    difference between 'the floors need rescaling' and 'the screen is selecting
    on tape coverage'."""
    rows = ([{"symbol": "AAA", "capture_2000": 0.05} for _ in range(5)]
            + [{"symbol": "BBB", "capture_2000": 0.20} for _ in range(5)])
    d = C.decompose(rows)
    assert d["icc"] > 0.95


def test_capture_that_wanders_within_a_symbol_reads_as_within_symbol():
    rows = []
    for sym in ("AAA", "BBB"):
        for v in (0.05, 0.10, 0.20, 0.40):
            rows.append({"symbol": sym, "capture_2000": v})
    d = C.decompose(rows)
    assert d["icc"] < 0.2


def test_the_decomposition_is_on_logs_because_these_are_ratios():
    """5%->20% and 20%->80% are the same factor. An arithmetic variance calls
    the second pair sixteen times more spread out, which would make every
    high-capture symbol look unstable purely for being high."""
    rows = [{"symbol": "AAA", "capture_2000": 0.05},
            {"symbol": "AAA", "capture_2000": 0.20},
            {"symbol": "BBB", "capture_2000": 0.20},
            {"symbol": "BBB", "capture_2000": 0.80}]
    d = C.decompose(rows)
    per = [math.log(0.20) - math.log(0.05), math.log(0.80) - math.log(0.20)]
    assert per[0] == pytest.approx(per[1])       # the premise
    assert d["within_var"] == pytest.approx(     # both symbols contribute equally
        pd_var([math.log(0.05), math.log(0.20)]), rel=1e-9)


def pd_var(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def test_singletons_cannot_produce_a_within_symbol_variance():
    """One observation per symbol says nothing about day-to-day stability, and
    reporting 0.0 would read as 'perfectly stable' rather than 'unmeasured'."""
    rows = [{"symbol": s, "capture_2000": 0.1} for s in "ABCDE"]
    d = C.decompose(rows)
    assert d["icc"] is None and d["within_var"] is None


# --- the report ------------------------------------------------------------

def test_an_empty_result_says_so_rather_than_printing_a_table_of_nans():
    out = C.render([], [], 0, 100, 1.0)
    assert "NO ROWS MATCHED" in out


def test_the_report_names_the_primary_column_from_the_session_check():
    rows = [{"symbol": "AAA", "date": "2025-04-09",
             "capture_1600": 0.30, "capture_2000": 0.10}]
    rth = [{"daily_bar": 600, "minutes_full": 1000, "minutes_rth": 600}] * 3
    assert "Primary column, per the session check: capture_1600" in \
        C.render(rows, rth, 0, 0, 1.0)


def test_impossible_rows_are_counted_in_the_report():
    out = C.render([{"symbol": "A", "date": "2025-04-09", "capture_2000": 0.1}],
                   [], 7, 0, 1.0)
    assert "IMPOSSIBLE (capture>1)  7" in out


# --- pair loading ----------------------------------------------------------

def test_pairs_group_by_date_and_dedupe(tmp_path):
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": "AAA", "date": "2025-04-09"},
               {"symbol": "AAA", "date": "2025-04-09"},
               {"symbol": "BBB", "date": "2025-04-09"},
               {"symbol": "CCC", "date": "2025-04-10"}], open(p, "w"))
    assert C.load_pairs(p) == {"2025-04-09": ["AAA", "BBB"],
                               "2025-04-10": ["CCC"]}


def test_a_read_dbn_shaped_frame_uses_the_index_and_gets_the_same_answer():
    """dbn_io.read_dbn re-indexes on ts_event, which CONSUMES the column -- so
    its frames carry the right times in the index and no ts_event column at
    all, while a raw store.to_df() is indexed on ts_recv with ts_event as a
    column. Both reach this function. On the real probe file ts_recv runs up to
    4.67s behind ts_event, which is nothing except exactly at a cutoff.
    """
    f = stats_frame([("AAA", "15:59", 500, 6), ("AAA", "16:01", 900, 6)])
    as_read_dbn = f.drop(columns=["ts_event"])       # index already ts_event
    assert C.cleared_by_cutoff(as_read_dbn, C.RTH_CLOSE_MIN) == {"AAA": 500}
    assert C.cleared_by_cutoff(f, C.RTH_CLOSE_MIN) == {"AAA": 500}


def test_the_two_framings_disagree_only_when_they_should():
    """If a record's ts_recv lands after a cutoff its ts_event precedes, the
    column and the index give different answers -- and the column is right."""
    f = stats_frame([("AAA", "15:59", 500, 6)])
    f.index = pd.DatetimeIndex(                       # ts_recv, 2 minutes late
        [f["ts_event"].iloc[0] + pd.Timedelta(minutes=2)])
    assert C.cleared_by_cutoff(f, C.RTH_CLOSE_MIN) == {"AAA": 500}
    assert C.cleared_by_cutoff(f.drop(columns=["ts_event"]),
                               C.RTH_CLOSE_MIN) == {}
