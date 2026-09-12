#!/usr/bin/env python3
"""Can the close-construction test say "I cannot tell"?

The whole point of this module is to stop a 552-session pull being spent on a
guess. It is therefore worth more as a refusal than as an answer, and the
failure mode that would defeat it is subtle:

    On a day with no after-hours activity, the extended close and the regular
    close are the SAME NUMBER. Every candidate matches. A scorer that counted
    those rows reports a near-perfect result for whichever construction it
    tried first, and the pull goes ahead on nothing.

So the tests below spend most of their effort on rows that must NOT count.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import regular_close as R

ET = ZoneInfo("America/New_York")


def minutes(spec, day="2026-09-10", symbol="AAA"):
    """spec = [(HH, MM, close)] as ET bar STARTS."""
    idx = pd.DatetimeIndex([
        pd.Timestamp(datetime.combine(pd.Timestamp(day).date(),
                                      dtime(h, m), tzinfo=ET)).tz_convert("UTC")
        for h, m, _ in spec])
    return pd.DataFrame({"symbol": symbol,
                         "close": [c for _, _, c in spec]}, index=idx)


# --- the constructions -------------------------------------------------------

def test_the_three_candidates_are_distinguished():
    """15:59 continuous at 7.30, the 16:00 auction at 7.22."""
    c = R.candidates(minutes([(15, 58, 7.31), (15, 59, 7.30), (16, 0, 7.22)]))
    assert c["last_bar_before_1600"] == pytest.approx(7.30)
    assert c["bar_at_1600"] == pytest.approx(7.22)
    assert c["last_bar_at_or_before_1600"] == pytest.approx(7.22)


def test_a_missing_1600_bar_leaves_that_candidate_None_not_zero():
    c = R.candidates(minutes([(15, 58, 7.31), (15, 59, 7.30)]))
    assert c["bar_at_1600"] is None
    assert c["last_bar_at_or_before_1600"] == pytest.approx(7.30)


def test_bars_after_1600_are_never_used():
    c = R.candidates(minutes([(15, 59, 7.30), (16, 0, 7.22), (16, 3, 9.80)]))
    assert c["last_bar_at_or_before_1600"] == pytest.approx(7.22)
    assert all(v != pytest.approx(9.80) for v in c.values() if v is not None)


def test_an_empty_frame_yields_no_candidates():
    assert R.candidates(pd.DataFrame()) == {}


# --- what must not count -----------------------------------------------------

def row(date, sym, truth, daily, cand, exchange="NASDAQ"):
    return {"date": date, "symbol": sym, "truth": truth, "daily": daily,
            "exchange": exchange, "cand": cand,
            "discriminating": abs(daily - truth) > R.TOL}


def test_a_quiet_day_is_NOT_discriminating():
    """ACVA 09-08: our daily close and the market's agree, so the row cannot
    tell the candidates apart."""
    r = row("2026-09-08", "ACVA", 7.03, 7.03,
            {"last_bar_before_1600": 7.03, "bar_at_1600": 7.03,
             "last_bar_at_or_before_1600": 7.03})
    assert r["discriminating"] is False


def test_a_run_after_hours_IS_discriminating():
    r = row("2026-09-10", "ACVA", 7.22, 10.38,
            {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
             "last_bar_at_or_before_1600": 7.22})
    assert r["discriminating"] is True


def test_only_discriminating_rows_are_scored():
    got = [row("2026-09-08", "ACVA", 7.03, 7.03,
               {"last_bar_before_1600": 7.03, "bar_at_1600": 7.03,
                "last_bar_at_or_before_1600": 7.03}),
           row("2026-09-10", "ACVA", 7.22, 10.38,
               {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
                "last_bar_at_or_before_1600": 7.22})]
    sc = R.score(got)
    assert sc["bar_at_1600"]["of"] == 1, "the quiet row must not inflate the n"
    assert sc["bar_at_1600"]["hit"] == 1
    assert sc["last_bar_before_1600"]["hit"] == 0


def test_no_discriminating_row_is_reported_as_such_not_as_a_pass():
    """The trap. All quiet rows -> every candidate is 0/0, and a verdict of
    "perfect" would authorise the pull on nothing."""
    got = [row("2026-09-08", "ACVA", 7.03, 7.03,
               {"last_bar_before_1600": 7.03, "bar_at_1600": 7.03,
                "last_bar_at_or_before_1600": 7.03})]
    sc = R.score(got)
    text = "\n".join(R.render(got, sc, []))
    assert "NO DISCRIMINATING ROW" in text
    assert "NOT evidence" in text


# --- the verdict -------------------------------------------------------------

def two_rows(cand_a, cand_b):
    return [row("2026-09-10", "ACVA", 7.22, 10.38, cand_a, "NYSE"),
            row("2026-09-09", "TPET", 1.81, 1.86, cand_b, "AMEX")]


def test_a_single_perfect_construction_wins():
    """Separating the two 16:00 readings needs a THIN name -- one that did not
    print in the closing minute, so `bar_at_1600` is absent and only the
    fallback can answer. Without such a row they are identical."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
                "last_bar_at_or_before_1600": 7.22}),
           row("2026-09-09", "TPET", 1.81, 1.86,
               {"last_bar_before_1600": 1.81, "bar_at_1600": None,
                "last_bar_at_or_before_1600": 1.81})]
    text = "\n".join(R.render(got, R.score(got), []))
    tail = text.split("VERDICT")[1]
    assert "last_bar_at_or_before_1600" in tail
    assert "AMBIGUOUS" not in text


def test_two_perfect_constructions_are_AMBIGUOUS_not_a_pick():
    got = two_rows(
        {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
         "last_bar_at_or_before_1600": 7.22},
        {"last_bar_before_1600": 1.81, "bar_at_1600": 1.81,
         "last_bar_at_or_before_1600": 1.81})
    text = "\n".join(R.render(got, R.score(got), []))
    assert "AMBIGUOUS" in text
    assert "Do" in text and "NOT pick one" in text


def test_the_ambiguity_message_names_WHY_those_two_tie():
    """They are identical by construction when a 16:00 bar exists. A report
    that just said "ambiguous" would send someone hunting for a data problem
    that is not there."""
    got = two_rows(
        {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
         "last_bar_at_or_before_1600": 7.22},
        {"last_bar_before_1600": 1.81, "bar_at_1600": 1.81,
         "last_bar_at_or_before_1600": 1.81})
    text = "\n".join(R.render(got, R.score(got), []))
    assert "IDENTICAL BY CONSTRUCTION" in text
    assert "THIN name" in text


def test_no_candidate_matching_refuses_the_pull():
    got = two_rows(
        {"last_bar_before_1600": 9.9, "bar_at_1600": 9.8,
         "last_bar_at_or_before_1600": 9.8},
        {"last_bar_before_1600": 9.9, "bar_at_1600": 9.8,
         "last_bar_at_or_before_1600": 9.8})
    text = "\n".join(R.render(got, R.score(got), []))
    assert "NONE of the candidates" in text
    assert "does not authorise" in text


# --- reporting ---------------------------------------------------------------

def test_untested_rows_are_named_not_silently_dropped():
    got = two_rows(
        {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
         "last_bar_at_or_before_1600": 7.22},
        {"last_bar_before_1600": 1.83, "bar_at_1600": 1.81,
         "last_bar_at_or_before_1600": 1.81})
    text = "\n".join(R.render(got, R.score(got),
                              ["2026-09-11 ISPC: not on this tape"]))
    assert "NOT TESTED" in text
    assert "2026-09-11 ISPC" in text


def test_the_report_flags_the_cross_listed_question():
    got = two_rows(
        {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
         "last_bar_at_or_before_1600": 7.22},
        {"last_bar_before_1600": 1.83, "bar_at_1600": 1.81,
         "last_bar_at_or_before_1600": 1.81})
    text = "\n".join(R.render(got, R.score(got), []))
    assert "ACVA is NYSE and TPET is" in text
    assert "Not out of sample" in text


def test_the_truth_table_carries_an_exchange_for_every_row():
    """The cross-listing caveat is only checkable if the listing is recorded."""
    for day, sym, exch, px in R.TRUTH:
        assert exch in {"NYSE", "NASDAQ", "AMEX"}, (sym, exch)
        assert px > 0


# --- the dataset question ----------------------------------------------------

def test_the_report_names_which_dataset_the_minutes_CAME_FROM():
    """Two datasets are scored against one truth table. A report that did not
    say which tape it read would be two indistinguishable files."""
    got = two_rows(
        {"last_bar_before_1600": 7.30, "bar_at_1600": 7.22,
         "last_bar_at_or_before_1600": 7.22},
        {"last_bar_before_1600": 1.83, "bar_at_1600": 1.81,
         "last_bar_at_or_before_1600": 1.81})
    text = "\n".join(R.render(got, R.score(got), [], "EQUS.MINI", "XNAS.BASIC"))
    assert "minute bars from EQUS.MINI" in text
    assert "currently in use is XNAS.BASIC" in text


def test_a_failure_does_not_blame_the_construction_by_default():
    """On a Nasdaq-only tape a NYSE name's official close is absent entirely,
    so "no candidate matched" may be a statement about the DATASET. The report
    must offer that reading rather than only the construction one."""
    got = two_rows(
        {"last_bar_before_1600": 9.9, "bar_at_1600": 9.8,
         "last_bar_at_or_before_1600": 9.8},
        {"last_bar_before_1600": 9.9, "bar_at_1600": 9.8,
         "last_bar_at_or_before_1600": 9.8})
    text = "\n".join(R.render(got, R.score(got), []))
    assert "NONE of the candidates" in text
    assert "cannot answer the question" in text
    assert "before blaming the construction" in text


# --- the candidate the FIRST run forced ---------------------------------------

def minutes_oc(spec, day="2026-09-10", symbol="AAA"):
    """spec = [(HH, MM, open, close)] as ET bar STARTS."""
    idx = pd.DatetimeIndex([
        pd.Timestamp(datetime.combine(pd.Timestamp(day).date(),
                                      dtime(h, m), tzinfo=ET)).tz_convert("UTC")
        for h, m, _, _ in spec])
    return pd.DataFrame({"symbol": symbol,
                         "open": [o for _, _, o, _ in spec],
                         "close": [c for _, _, _, c in spec]}, index=idx)


def test_the_1600_bar_CLOSE_is_not_the_auction():
    """ACVA 2026-09-10, from the real tape: the market closed at 7.22 and the
    16:00-16:01 bar closed at 10.45, because that minute also holds the first
    EXTENDED-hours prints and the name was already away. The auction is the
    FIRST trade in that minute."""
    c = R.candidates(minutes_oc([(15, 59, 7.25, 7.24),
                                 (16, 0, 7.22, 10.45)]))
    assert c["bar_at_1600"] == pytest.approx(10.45)
    assert c["open_at_1600"] == pytest.approx(7.22)
    assert c["auction_else_last"] == pytest.approx(7.22)


def test_auction_else_last_falls_back_when_there_is_no_1600_print():
    """A thin name that did not trade in the closing minute has no cross, and
    its official close is the last continuous trade."""
    c = R.candidates(minutes_oc([(15, 58, 1.82, 1.81), (15, 59, 1.81, 1.80)]))
    assert c["open_at_1600"] is None
    assert c["auction_else_last"] == pytest.approx(1.80)


def test_a_frame_without_an_open_column_yields_None_not_a_close():
    """Silently substituting the close would make the auction candidate a
    duplicate of one that already failed."""
    c = R.candidates(minutes([(15, 59, 7.30), (16, 0, 10.45)]))
    assert c["open_at_1600"] is None
    assert c["auction_else_last"] == pytest.approx(7.30)


def test_all_five_candidates_are_scored():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"last_bar_before_1600": 7.22, "open_at_1600": 7.22,
                "bar_at_1600": 10.45, "last_bar_at_or_before_1600": 10.45,
                "auction_else_last": 7.22})]
    sc = R.score(got)
    assert set(sc) == {"last_bar_before_1600", "open_at_1600", "bar_at_1600",
                       "last_bar_at_or_before_1600", "auction_else_last"}
    assert sc["bar_at_1600"]["hit"] == 0
    assert sc["auction_else_last"]["hit"] == 1


# --- the venue split ---------------------------------------------------------

def test_the_score_is_split_by_listing_venue_when_venues_differ():
    """An official close is set by the LISTING venue's cross. A construction
    that is perfect on NASDAQ and imperfect elsewhere is a partial TAPE, not a
    broken construction, and pooling the two hides exactly that."""
    got = [row("2026-09-10", "ISPC", 1.50, 1.43,
               {"auction_else_last": 1.50}, "NASDAQ"),
           row("2026-09-09", "TPET", 1.81, 1.86,
               {"auction_else_last": 1.82}, "AMEX")]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "SPLIT BY LISTING VENUE" in text
    assert "NASDAQ" in text and "AMEX" in text
    assert "1/1" in text and "0/1" in text
    assert "partial" in text


def test_no_split_is_printed_when_every_row_lists_on_one_venue():
    got = [row("2026-09-10", "ISPC", 1.50, 1.43,
               {"auction_else_last": 1.50}, "NASDAQ")]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "SPLIT BY LISTING VENUE" not in text


def test_the_truth_table_spans_both_venues_and_a_thin_nasdaq_name():
    """The second batch exists to separate "wrong venue" from "thin tape". If
    every added row were a liquid NASDAQ name it could not do that."""
    ex = {sym: e for _d, sym, e, _p in R.TRUTH}
    assert {"NASDAQ", "NYSE", "AMEX"} <= set(ex.values())
    assert "XRTX" in ex and ex["XRTX"] == "NASDAQ"


# --- the end-of-day candidate -------------------------------------------------

def test_the_eod_candidate_is_scored_when_present():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"ohlcv_eod_close": 7.22, "auction_else_last": 7.22})]
    sc = R.score(got)
    assert "ohlcv_eod_close" in sc
    assert sc["ohlcv_eod_close"]["hit"] == 1


def test_the_eod_candidate_is_absent_when_it_was_not_asked_for():
    """It must not appear as 0/n and read as a failed candidate when the bars
    were simply never pulled."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"auction_else_last": 7.22})]
    assert "ohlcv_eod_close" not in R.score(got)


def test_a_missing_eod_bar_scores_as_a_MISS_not_as_the_daily_close():
    """Falling back to ohlcv-1d for an absent eod bar would make the new
    candidate score exactly as well as the thing it is replacing -- a control
    indistinguishable from the failure it detects."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"ohlcv_eod_close": None, "auction_else_last": 7.22})]
    sc = R.score(got)
    assert sc["ohlcv_eod_close"]["hit"] == 0
    assert sc["ohlcv_eod_close"]["of"] == 1


def test_an_eod_bar_that_is_just_the_extended_close_scores_ZERO():
    """The whole risk of this route: a schema named `ohlcv-eod` may aggregate
    the extended session too, which is exactly what ohlcv-1d does. Availability
    is not validation, and the scorer must be able to say so."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"ohlcv_eod_close": 10.38, "auction_else_last": 7.22}),
           row("2026-09-09", "SUNE", 4.51, 3.89,
               {"ohlcv_eod_close": 3.89, "auction_else_last": 4.51})]
    sc = R.score(got)
    assert sc["ohlcv_eod_close"]["hit"] == 0
    assert sc["auction_else_last"]["hit"] == 2
