#!/usr/bin/env python3
"""Prior-spike retention: has this name run before, and did it hold?

One computation answering three separate rules — warrior_0 §7.1's daily-chart
trust check and both history rows of warrior_3's Gap-and-Go rubric. The tests
concentrate on the two ways it could produce a confident wrong answer: seeing
the move it is supposed to be history for, and calling an absent spike a zero.
"""
from __future__ import annotations

import pandas as pd
import pytest

from common import prior_spike as P


def closes(vals):
    return pd.Series([float(v) for v in vals])


def daily(rows):
    """rows = [(symbol, 'YYYY-MM-DD', close)]"""
    return pd.DataFrame(
        [{"symbol": s, "date": d, "close": c} for s, d, c in rows])


# --- finding the spike -------------------------------------------------------

def test_a_run_that_doubles_is_a_spike():
    got = P.prior_spike(closes([1.0, 1.0, 2.0, 2.0]))
    assert got is not None
    assert got["base"] == pytest.approx(1.0)
    assert got["peak"] == pytest.approx(2.0)
    assert got["run_pct"] == pytest.approx(1.0)


def test_a_gentle_drift_is_not_a_spike():
    assert P.prior_spike(closes([1.0, 1.1, 1.2, 1.3])) is None


def test_no_spike_is_None_rather_than_a_zero():
    """THE DISTINCTION THAT MATTERS. 'This name has never run' is one of the
    rubric's own categories, not a retention of 0.0 — and scoring it as one
    would file every quiet name with the pump-and-dumps."""
    assert P.prior_spike(closes([5.0] * 40)) is None
    assert P.label(None) == "no prior spike"


def test_the_base_must_precede_the_peak():
    """A low AFTER the high is a collapse, not a run. Taking the window
    minimum without regard to order would score every crash as a spike.

    The series matters: [2, 2, 3, 1] has a 3 that only clears +100% against
    the 1 that comes AFTER it. A shorter fixture cannot tell the two
    implementations apart, because the running minimum starts at the first
    value either way."""
    assert P.prior_spike(closes([2.0, 2.0, 3.0, 1.0])) is None
    # And the same shape with the low FIRST is a real spike.
    assert P.prior_spike(closes([1.0, 2.0, 3.0])) is not None


def test_the_largest_run_in_the_window_wins():
    got = P.prior_spike(closes([1.0, 2.5, 1.0, 1.0, 2.2]))
    assert got["run_pct"] == pytest.approx(1.5)


# --- retention ---------------------------------------------------------------

def test_a_fully_held_run_retains_everything():
    got = P.prior_spike(closes([1.0, 3.0, 3.0]))
    assert got["retained"] == pytest.approx(1.0)
    assert P.label(got) == "former runner"


def test_a_fully_retraced_run_retains_nothing():
    """His own example: up 300% two weeks earlier, fully retraced."""
    got = P.prior_spike(closes([1.0, 4.0, 1.0]))
    assert got["retained"] == pytest.approx(0.0)
    assert P.label(got) == "pump and dump"


def test_half_held_is_neither_category():
    got = P.prior_spike(closes([1.0, 3.0, 2.0]))
    assert got["retained"] == pytest.approx(0.5)
    assert P.label(got) == "former runner"     # >= 0.50 is the boundary
    assert P.label({"retained": 0.35}) == "partial hold"


def test_retention_below_the_base_is_floored_at_zero():
    """A name now trading BELOW where the run started has retained none of it,
    not a negative share of it. Unclipped, [2, 6, 1] scores -0.25 — and a
    negative dragging a bucket average is one name deciding a verdict."""
    got = P.prior_spike(closes([2.0, 6.0, 1.0]))
    assert got["retained"] == pytest.approx(0.0)
    raw = (1.0 - got["base"]) / (got["peak"] - got["base"])
    assert raw < 0, "unclipped this is negative, which is what the floor is for"


def test_retention_is_capped_at_the_whole_run():
    got = P.prior_spike(closes([1.0, 3.0, 5.0]))
    assert got["retained"] == pytest.approx(1.0)


# --- the window, and the trap it exists for ---------------------------------

def test_the_quiet_gap_hides_the_move_being_traded():
    """THE ERROR THIS PREVENTS. Without the gap the search runs right up to
    the trade and finds the move being traded as its own 'prior' spike —
    scoring every winner a former runner by construction and producing a
    beautiful, meaningless result."""
    rows = [("AAA", f"2026-01-{i:02d}", 1.0) for i in range(1, 21)]
    rows += [("AAA", f"2026-02-{i:02d}", 10.0) for i in range(1, 6)]
    got = P.history_for(daily(rows), "AAA", "2026-02-06")
    assert got is not None
    assert max(got) == pytest.approx(1.0), "the 10.0 spike is inside the gap"
    assert P.prior_spike(got) is None


def test_a_genuinely_old_spike_is_still_found():
    rows = [("AAA", f"2026-01-{i:02d}", 1.0) for i in range(1, 6)]
    rows += [("AAA", f"2026-01-{i:02d}", 4.0) for i in range(6, 11)]
    rows += [("AAA", f"2026-01-{i:02d}", 3.8) for i in range(11, 26)]
    got = P.prior_spike(P.history_for(daily(rows), "AAA", "2026-02-01"))
    assert got is not None and got["run_pct"] >= 1.0


def test_only_this_symbols_history_is_read():
    rows = [("AAA", f"2026-01-{i:02d}", 1.0) for i in range(1, 26)]
    rows += [("BBB", f"2026-01-{i:02d}", 9.0) for i in range(1, 26)]
    assert P.prior_spike(P.history_for(daily(rows), "AAA", "2026-02-01")) is None


def test_days_at_or_after_the_trade_are_never_read(monkeypatch):
    """Tested with the quiet gap TURNED OFF. With the gap on, the trade day
    falls inside it and is dropped for the wrong reason — so the boundary
    itself goes untested and a `<=` slips through looking correct."""
    monkeypatch.setattr(P, "QUIET_SESSIONS", 0)
    rows = [("AAA", f"2026-01-{i:02d}", 1.0) for i in range(1, 26)]
    rows += [("AAA", "2026-02-01", 99.0)]
    got = P.history_for(daily(rows), "AAA", "2026-02-01")
    assert 99.0 not in list(got), "the trade's own day is not history"


def test_a_symbol_with_no_history_yields_nothing():
    assert P.history_for(daily([("BBB", "2026-01-01", 1.0)]),
                         "AAA", "2026-02-01") is None


def test_a_history_shorter_than_the_gap_yields_nothing():
    rows = [("AAA", f"2026-01-{i:02d}", 1.0) for i in range(1, 4)]
    assert P.history_for(daily(rows), "AAA", "2026-02-01") is None


# --- the pinned parameters ---------------------------------------------------

def test_the_thresholds_are_the_pinned_ones():
    assert (P.LOOKBACK_SESSIONS, P.QUIET_SESSIONS) == (60, 5)
    assert P.SPIKE_MIN == 1.00
    assert (P.RETAINED_HIGH, P.RETAINED_LOW) == (0.50, 0.20)


# --- the report --------------------------------------------------------------

def g(n, per, date_="2026-01-01"):
    return [{"symbol": "X", "date": date_, "real": per} for _ in range(n)]


def report(groups):
    return "\n".join(P.render(groups, 100, 373))


def test_a_clean_pass_is_called_supported_but_not_adoptable():
    groups = {"former runner": g(20, 5.0, "2020-01-01") + g(20, 5.0, "2030-01-01"),
              "pump and dump": g(20, -5.0, "2020-01-01") + g(20, -5.0, "2030-01-01")}
    text = report(groups)
    assert "SUPPORTED" in text
    assert "NOT enough to turn it on" in text


def test_a_sign_flip_between_halves_is_not_supported():
    # Former runners win overall (+1.00/trade vs +0.50) but only because the
    # early half carries it; the late half runs the other way.
    groups = {"former runner": g(10, 3.0, "2020-01-01") + g(10, -1.0, "2030-01-01"),
              "pump and dump": g(10, 1.0, "2020-01-01") + g(10, 0.0, "2030-01-01")}
    text = report(groups)
    assert "NOT SUPPORTED" in text
    assert "sign flips between halves" in text


def test_a_result_carried_by_three_trades_is_not_supported():
    groups = {"former runner": [{"symbol": "X", "date": "2020-01-01",
                                 "real": v} for v in (500, 500, 500)]
                               + g(30, -1.0, "2030-01-01"),
              "pump and dump": g(30, -0.5, "2020-01-01") + g(30, -0.5, "2030-01-01")}
    text = report(groups)
    assert "NOT SUPPORTED" in text and "drop-top-3" in text


def test_the_inverted_case_says_what_it_costs_the_warrior_docs():
    """Three rules across two documents rest on the opposite. A null that did
    not say so would leave them quoted as live candidates."""
    groups = {"former runner": g(20, -5.0), "pump and dump": g(20, 5.0)}
    text = report(groups)
    assert "INVERTED" in text
    assert "§7.1" in text and "rubric" in text


def test_an_empty_group_stops_the_comparison_rather_than_faking_one():
    text = report({"former runner": g(20, 5.0)})
    assert "nothing to" in text and "change nothing" in text


def test_the_no_spike_population_is_reported_not_dropped():
    """It may well be the majority here, and a filter that silently discards
    most of the universe is a different filter from the one described."""
    text = report({"former runner": g(5, 1.0), "pump and dump": g(5, -1.0),
                   "no prior spike": g(300, 0.1)})
    assert "no prior spike" in text and "300" in text


def test_the_report_warns_about_split_adjustment():
    """A reverse split follows a price collapse — exactly these names — and an
    adjusted history can turn a collapse into a flat line."""
    text = report({"former runner": g(5, 1.0), "pump and dump": g(5, -1.0)})
    assert "SPLIT-ADJUSTED" in text
