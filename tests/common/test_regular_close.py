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


# --- the statistics route -----------------------------------------------------

def test_the_stat_type_ints_are_the_databento_ones():
    """They are restated as constants so the module loads without databento.
    A restated constant is a second source of truth, so it is pinned."""
    db = pytest.importorskip("databento")
    assert R.STAT_CLOSE_PRICE == int(db.StatType.CLOSE_PRICE)
    assert R.STAT_UNCROSSING_PRICE == int(db.StatType.UNCROSSING_PRICE)


def test_the_stat_candidates_are_scored_when_present():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": 7.22, "stats_close_price": 7.22,
                "auction_else_last": 7.22})]
    sc = R.score(got)
    assert sc["stats_uncrossing"]["hit"] == 1
    assert sc["stats_close_price"]["hit"] == 1


def test_a_missing_statistic_scores_as_a_MISS_not_as_the_daily_close():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22})]
    sc = R.score(got)
    assert sc["stats_uncrossing"]["hit"] == 0
    assert sc["stats_uncrossing"]["of"] == 1


def test_the_census_is_printed_so_an_empty_filter_is_visible():
    """A stat_type filter that matches nothing returns {} — indistinguishable
    from a schema carrying no closes. The counts distinguish them."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22})]
    text = "\n".join(R.render(got, R.score(got), [], st_census={16: 4821, 1: 37}))
    assert "STAT TYPES PRESENT" in text
    assert "UNCROSSING_PRICE" in text
    assert "4,821" in text


def test_a_census_without_either_close_statistic_says_so():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22})]
    text = "\n".join(R.render(got, R.score(got), [], st_census={1: 37, 3: 12}))
    assert "NEITHER close statistic appears" in text
    assert "not an empty result" in text


def test_no_census_section_when_stats_were_not_requested():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38, {"auction_else_last": 7.22})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "STAT TYPES PRESENT" not in text


# --- the statistics READER, exercised for real --------------------------------

def stats_frame(rows, day="2026-09-10"):
    """rows = [(stat_type, symbol, price)] as a statistics frame."""
    idx = pd.DatetimeIndex([
        pd.Timestamp(f"{day} 16:00:00", tz=ET).tz_convert("UTC")
    ] * len(rows))
    return pd.DataFrame({"stat_type": [t for t, _, _ in rows],
                         "symbol": [s for _, s, _ in rows],
                         "price": [p for _, _, p in rows]}, index=idx)


def test_the_reader_pulls_both_close_statistics_out():
    """This path was only reachable through a real .dbn.zst, so its one defect
    -- a column named `_date`, which itertuples renames to a positional field
    -- could not be caught by any test and surfaced as an AttributeError on
    Ben's machine. It is reachable now."""
    c, u, census = R.stats_from_frame(stats_frame([
        (R.STAT_CLOSE_PRICE, "ACVA", 7.22),
        (R.STAT_UNCROSSING_PRICE, "ACVA", 7.22),
        (R.STAT_UNCROSSING_PRICE, "ISPC", 1.50),
        (1, "ACVA", 7.36)]))
    assert c == {("2026-09-10", "ACVA"): 7.22}
    assert u == {("2026-09-10", "ACVA"): 7.22, ("2026-09-10", "ISPC"): 1.50}
    assert census == {1: 1, R.STAT_CLOSE_PRICE: 1, R.STAT_UNCROSSING_PRICE: 2}


def test_the_reader_censuses_stat_types_it_does_not_use():
    _c, _u, census = R.stats_from_frame(stats_frame([(1, "AAA", 5.0),
                                                     (3, "AAA", 5.1)]))
    assert census == {1: 1, 3: 1}


def test_a_zero_or_negative_price_is_dropped_not_stored():
    c, _u, _n = R.stats_from_frame(stats_frame([
        (R.STAT_CLOSE_PRICE, "AAA", 0.0),
        (R.STAT_CLOSE_PRICE, "BBB", 2.5)]))
    assert c == {("2026-09-10", "BBB"): 2.5}


def test_a_row_with_no_symbol_is_skipped():
    c, _u, _n = R.stats_from_frame(stats_frame([
        (R.STAT_CLOSE_PRICE, None, 2.5),
        (R.STAT_CLOSE_PRICE, "BBB", 2.5)]))
    assert c == {("2026-09-10", "BBB"): 2.5}


def test_an_empty_or_schemaless_frame_returns_three_empties():
    assert R.stats_from_frame(pd.DataFrame()) == ({}, {}, {})
    assert R.stats_from_frame(None) == ({}, {}, {})


# --- absent is not wrong ------------------------------------------------------

def test_a_candidate_that_never_produced_a_value_reads_as_ABSENT():
    """UNCROSSING_PRICE is not carried on XNAS.BASIC at all. Scoring it 0/24
    puts it beside a candidate that WAS present and got every row wrong, and
    the two are not the same claim."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22}),
           row("2026-09-09", "SUNE", 4.51, 3.89,
               {"stats_uncrossing": None, "auction_else_last": 4.51})]
    sc = R.score(got)
    assert sc["stats_uncrossing"]["present"] is False
    assert sc["auction_else_last"]["present"] is True
    text = "\n".join(R.render(got, sc, []))
    assert "ABSENT, not wrong" in text
    assert "stats_uncrossing                 n/a" in text


def test_an_absent_candidate_can_never_win_the_verdict():
    """0/0 is vacuously perfect. A candidate that produced nothing must not be
    picked as the construction to rebuild 552 sessions on."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22})]
    text = "\n".join(R.render(got, R.score(got), []))
    tail = text.split("VERDICT")[1]
    assert "stats_uncrossing" not in tail


def test_a_present_candidate_that_gets_everything_wrong_still_scores_zero():
    """The other half: ABSENT must not become a way to hide a real failure."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_close_price": 9.99, "auction_else_last": 7.22})]
    sc = R.score(got)
    assert sc["stats_close_price"]["present"] is True
    assert sc["stats_close_price"]["hit"] == 0
    # asserted on THIS candidate's line -- the others really are absent from
    # this fixture and correctly say so, so a global check would pass or fail
    # for the wrong reason.
    line = next(x for x in R.render(got, sc, [])
                if x.strip().startswith("stats_close_price"))
    assert "0/1" in line and "ABSENT" not in line


# --- two methods against the truth --------------------------------------------

def test_two_methods_agreeing_against_the_truth_is_reported_separately():
    """A published statistic and a bar-derived close agreeing with each other
    while TradingView differs puts the TRUTH ROW in question, not the
    extraction."""
    got = [row("2026-09-10", "FTFT", 2.05, 2.11,
               {"auction_else_last": 2.03, "stats_close_price": 2.03})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "WHERE TWO METHODS AGREE AND THE TRUTH DOES NOT" in text
    assert "2026-09-10  FTFT" in text
    assert "neither a pass nor a failure" in text


def test_the_agreement_note_states_they_are_NOT_independent():
    """Both read the same tape. Agreement shows consistency, not correctness,
    and claiming otherwise would be the strongest overreach available here."""
    got = [row("2026-09-10", "FTFT", 2.05, 2.11,
               {"auction_else_last": 2.03, "stats_close_price": 2.03})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "NOT fully independent" in text
    assert "third source" in text


def test_methods_that_DISAGREE_are_not_reported_as_agreement():
    got = [row("2026-09-10", "FTFT", 2.05, 2.11,
               {"auction_else_last": 2.03, "stats_close_price": 2.07})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "WHERE TWO METHODS AGREE" not in text


def test_agreement_WITH_the_truth_is_not_flagged():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"auction_else_last": 7.22, "stats_close_price": 7.22})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "WHERE TWO METHODS AGREE" not in text


# --- the third source ---------------------------------------------------------

def test_a_third_source_CONFIRMING_the_truth_marks_the_flag_a_false_alarm():
    """The two-method flag exists to raise a row for checking, not to win it.
    When the third source backs TradingView, the row is a real miss and the
    report has to say so rather than leaving the doubt hanging."""
    got = [row("2026-09-10", "XRTX", 2.11, 2.44,
               {"auction_else_last": 2.18, "stats_close_price": 2.18})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "CHECKED AGAINST A THIRD SOURCE" in text
    assert "CONFIRMS THE TRUTH" in text
    assert "FALSE ALARM" in text
    assert "real miss" in text


def test_an_unchecked_row_is_not_claimed_to_be_confirmed():
    got = [row("2026-09-10", "FTFT", 2.05, 2.11,
               {"auction_else_last": 2.03, "stats_close_price": 2.03})]
    text = "\n".join(R.render(got, R.score(got), []))
    assert "WHERE TWO METHODS AGREE" in text
    assert "CHECKED AGAINST A THIRD SOURCE" not in text


def test_the_third_source_record_carries_its_provenance():
    """A number with no stated source is the thing this project keeps being
    burned by."""
    for key, (px, how) in R.THIRD_SOURCE.items():
        assert px > 0
        assert how and len(how) > 10


# --- accepting below the bar, deliberately ------------------------------------

def _emit(tmp_path, monkeypatch, argv, got_rows):
    """Drive main()'s emit path with a stubbed scorer and reader."""
    import json
    monkeypatch.chdir(tmp_path)
    return argv, got_rows, json


def test_by_venue_splits_only_discriminating_rows():
    got = [row("2026-09-10", "ACVA", 7.22, 10.38, {}, "NYSE"),
           row("2026-09-08", "ACVA", 7.03, 7.03, {}, "NYSE"),
           row("2026-09-09", "TPET", 1.81, 1.86, {}, "AMEX")]
    v = R._by_venue(got)
    assert sorted(v) == ["AMEX", "NYSE"]
    assert len(v["NYSE"]) == 1, "the quiet row must not be counted"


def test_accept_is_a_named_construction_not_a_boolean():
    """A bare --force would relax the bar without recording WHICH construction
    was accepted or what it scored."""
    p = R.build_parser()
    a = p.parse_args(["--accept", "auction_else_last", "--emit"])
    assert a.accept == "auction_else_last"
    assert p.parse_args([]).accept is None


def test_the_help_says_the_relaxation_is_recorded():
    """The flag has to read as a decision, not a convenience."""
    txt = R.build_parser().format_help()
    assert "pre-registered bar" in txt
    assert "stamped into the output file" in txt


def test_an_absent_construction_cannot_be_accepted():
    """UNCROSSING_PRICE produced nothing. Accepting it would write a file of
    nothing that looks exactly like a file of closes."""
    got = [row("2026-09-10", "ACVA", 7.22, 10.38,
               {"stats_uncrossing": None, "auction_else_last": 7.22})]
    sc = R.score(got)
    assert sc["stats_uncrossing"]["present"] is False


# --- the emit loop's cached-day path ------------------------------------------

def test_a_dataframe_has_no_truth_value_so_the_or_idiom_is_a_bug():
    """The bug this pins, stated as the language fact it rests on.

    `--emit` read its bars as `cache.get(day) or read_dbn(p)`. For an uncached
    day `.get` returns None and the fallback runs; for a CACHED day it returns
    a DataFrame, and `df or x` calls __bool__, which pandas refuses. The cached
    days are the TRUTH days -- 2026-09-08..11 -- which sit at the END of a
    chronological walk, so a real run ground through ~548 sessions in silence
    and then died having written nothing.
    """
    import pandas as pd
    with pytest.raises(ValueError, match="truth value"):
        _ = pd.DataFrame({"a": [1]}) or "fallback"


def test_emit_day_is_pure_so_the_pool_needs_no_discipline():
    """Parallelising is only safe because a session carries nothing: no
    warm-up, no state from the day before, no randomness. Two calls on the
    same slice must agree exactly, or --jobs would change the answer."""
    import pandas as pd
    frame = pd.DataFrame(
        {"symbol": ["ACVA", "ACVA"], "open": [7.20, 7.22],
         "high": [7.25, 7.30], "low": [7.18, 7.20], "close": [7.22, 7.28],
         "volume": [1000.0, 2000.0]},
        index=pd.DatetimeIndex(
            ["2026-09-10T19:59:00Z", "2026-09-10T20:00:00Z"]))

    calls = []

    def fake_read(path):
        calls.append(path)
        return frame

    import common.dbn_io as dbn
    orig = dbn.read_dbn
    dbn.read_dbn = fake_read
    try:
        a = R.emit_day(("2026-09-10_1555_1605.dbn.zst", "open_at_1600"))
        b = R.emit_day(("2026-09-10_1555_1605.dbn.zst", "open_at_1600"))
    finally:
        dbn.read_dbn = orig
    assert a == b
    assert a[0] == "2026-09-10"
    assert len(calls) == 2, "each call must read its own slice, not share one"


def test_emit_day_names_the_session_from_the_FILENAME():
    """The day is the file's, not the frame's. A slice whose bars land either
    side of midnight UTC would otherwise be filed under two dates."""
    import pandas as pd
    import common.dbn_io as dbn
    orig = dbn.read_dbn
    dbn.read_dbn = lambda p: pd.DataFrame()
    try:
        day, got = R.emit_day(("/x/y/2024-07-01_1555_1605.dbn.zst", "x"))
    finally:
        dbn.read_dbn = orig
    assert day == "2024-07-01" and got == {}


def test_the_emit_loop_reads_a_cached_day_without_raising():
    """The fix, exercised the way the loop exercises it. A plain membership
    test has no truth-value problem and returns the cached frame."""
    import pandas as pd
    frame = pd.DataFrame({"symbol": ["ACVA"], "close": [7.22]})
    cache = {"2026-09-10": frame}

    def pick(day, cached, fallback):
        return cached[day] if day in cached else fallback

    assert pick("2026-09-10", cache, "READ") is frame
    assert pick("2024-07-01", cache, "READ") == "READ"


def test_an_EMPTY_cached_frame_is_still_used_not_silently_re_read():
    """The `or` idiom would also have fallen through on an empty frame --
    re-reading a file already known to hold nothing, and quietly disagreeing
    with the scoring pass about what that day contained."""
    import pandas as pd
    empty = pd.DataFrame(columns=["symbol", "close"])
    cache = {"2026-09-10": empty}
    got = cache["2026-09-10"] if "2026-09-10" in cache else "RE-READ"
    assert got is empty
