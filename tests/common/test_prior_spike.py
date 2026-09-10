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
    assert P.label(None, closes([1.0] * 40)) == "no prior spike"


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
    assert P.label(got, closes([1.0] * 40)) == "former runner"


def test_a_fully_retraced_run_retains_nothing():
    """His own example: up 300% two weeks earlier, fully retraced."""
    got = P.prior_spike(closes([1.0, 4.0, 1.0]))
    assert got["retained"] == pytest.approx(0.0)
    assert P.label(got, closes([1.0] * 40)) == "pump and dump"


def test_half_held_is_neither_category():
    got = P.prior_spike(closes([1.0, 3.0, 2.0]))
    assert got["retained"] == pytest.approx(0.5)
    assert P.label(got, closes([1.0] * 40)) == "former runner"   # >= 0.50 is the boundary
    assert P.label({"retained": 0.35}, closes([1.0] * 40)) == "partial hold"


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


def both(n, per):
    """Half the trades either side of the split. Several fixtures here were
    single-sided, which trips the inert-control guard for the same reason the
    2026-09-10 screened run did — a half-comparison against an empty half."""
    return g(n // 2, per, "2020-01-01") + g(n - n // 2, per, "2030-01-01")


def report(groups, split="2026-03-20"):
    return "\n".join(P.render(groups, 100, 373, "all", 0, split,
                              "fixed, for the test"))


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
                               + g(15, -1.0, "2020-01-01")
                               + g(30, -1.0, "2030-01-01"),
              "pump and dump": g(30, -0.5, "2020-01-01") + g(30, -0.5, "2030-01-01")}
    text = report(groups)
    assert "NOT SUPPORTED" in text and "drop-top-3" in text


def test_the_inverted_case_says_what_it_costs_the_warrior_docs():
    """Three rules across two documents rest on the opposite. A null that did
    not say so would leave them quoted as live candidates."""
    groups = {"former runner": both(20, -5.0), "pump and dump": both(20, 5.0)}
    text = report(groups)
    assert "INVERTED" in text
    assert "§7.1" in text and "rubric" in text


def test_an_empty_group_stops_the_comparison_rather_than_faking_one():
    text = report({"former runner": both(20, 5.0)})
    assert "nothing to" in text and "change nothing" in text


def test_the_no_spike_population_is_reported_not_dropped():
    """It may well be the majority here, and a filter that silently discards
    most of the universe is a different filter from the one described."""
    text = report({"former runner": both(5, 1.0), "pump and dump": both(5, -1.0),
                   "no prior spike": both(300, 0.1)})
    assert "no prior spike" in text and "300" in text


def test_the_report_warns_about_split_adjustment():
    """A reverse split follows a price collapse — exactly these names — and an
    adjusted history can turn a collapse into a flat line."""
    text = report({"former runner": both(5, 1.0), "pump and dump": both(5, -1.0)})
    assert "SPLIT-ADJUSTED" in text


# --- corrections after the first run, 2026-09-10 -----------------------------

def test_a_name_with_almost_no_history_is_not_called_quiet():
    """"We found no spike" and "we could not look" are different answers, and
    the first version collapsed them. On this universe recent listings and
    reverse splits are a large slice, so that bucket was carrying names that
    had never had a chance to run."""
    short = closes([1.0] * 5)
    assert P.label(None, short) == "too new to judge"
    assert P.label(None, closes([1.0] * 40)) == "no prior spike"


def test_a_real_spike_is_still_labelled_even_with_long_history():
    got = P.prior_spike(closes([1.0] * 30 + [3.0] * 30))
    assert P.label(got, closes([1.0] * 60)) == "former runner"


def test_halves_are_compared_per_trade_not_on_totals():
    """THE BUG THE FIRST RUN EXPOSED. The groups differed 137 to 30, so
    comparing their half TOTALS compared how many trades each had. Here the
    small group wins per trade in both halves and loses on both totals."""
    # The small group wins PER TRADE in both halves (+1.00 vs +0.50), but the
    # early-half TOTALS run the other way (10 vs 30) because the other group
    # has six times the trades there. Compared on totals the sign flips and
    # the verdict inverts; compared per trade it does not. A fixture where
    # both halves agree either way cannot tell the two apart -- the first
    # version of this test could not, and the mutation survived it.
    groups = {
        "former runner": g(10, 1.0, "2020-01-01") + g(10, 1.0, "2030-01-01"),
        "pump and dump": g(60, 0.5, "2020-01-01") + g(5, 0.5, "2030-01-01"),
    }
    text = report(groups)
    assert "SUPPORTED" in text and "NOT SUPPORTED" not in text


def test_the_any_spike_split_is_reported():
    groups = {"former runner": g(20, 5.0, "2020-01-01") + g(20, 5.0, "2030-01-01"),
              "pump and dump": g(5, 1.0, "2020-01-01") + g(5, 1.0, "2030-01-01"),
              "no prior spike": g(30, -5.0, "2020-01-01") + g(30, -5.0, "2030-01-01")}
    text = report(groups)
    assert "HAS THIS NAME EVER RUN AT ALL" in text
    assert "SEPARATES" in text
    assert "spend the holdout on THIS" in text


def test_the_any_spike_split_respects_both_halves():
    groups = {"former runner": g(20, 9.0, "2020-01-01") + g(20, -1.0, "2030-01-01"),
              "no prior spike": g(20, 1.0, "2020-01-01") + g(20, 1.0, "2030-01-01")}
    text = report(groups)
    assert "SEPARATES" not in text
    assert "sign flips between halves" in text


def test_no_separation_is_said_plainly():
    groups = {"former runner": both(20, -5.0), "pump and dump": both(20, -5.0),
              "no prior spike": both(30, 5.0)}
    assert "No separation" in report(groups)


def test_a_group_too_small_for_drop_top_three_gets_no_verdict():
    """On 4 trades, dropping the top 3 removes 75% of the group and the
    control decides the answer by itself."""
    groups = {"former runner": both(40, 5.0), "pump and dump": both(4, -5.0)}
    text = report(groups)
    assert "FEWER THAN" in text and "no verdict drawn" in text
    assert "SUPPORTED" not in text


# --- the holdout, which is clean for this filter exactly once ---------------

def sess(dates):
    return [("AAA", d, None) for d in dates]


def test_the_default_side_is_training_and_the_locked_slice_is_set_aside():
    """A holdout that can be read casually is not a holdout. holdout.json was
    cut 2026-09-07 over the screened universe; this filter was invented on
    09-10, so the locked slice is genuinely clean for it -- and worth exactly
    one read."""
    keep, aside, side = P.split_sessions(
        sess(["2025-06-01", "2026-01-11", "2026-01-12", "2026-06-01"]), False)
    assert [d for _, d, _ in keep] == ["2025-06-01", "2026-01-11"]
    assert aside == 2
    assert side.startswith("training")


def test_spending_the_holdout_takes_only_the_locked_side():
    keep, aside, side = P.split_sessions(
        sess(["2025-06-01", "2026-01-11", "2026-01-12", "2026-06-01"]), True)
    assert [d for _, d, _ in keep] == ["2026-01-12", "2026-06-01"]
    assert aside == 2
    assert side.startswith("LOCKED")


def test_the_cut_date_is_read_from_the_committed_file():
    """Not a constant here. The cut is committed at the repo root precisely so
    it cannot quietly differ between a tool and the file of record."""
    assert P.lock_from() == "2026-01-12"


def test_the_two_sides_never_overlap():
    dates = ["2025-06-01", "2026-01-11", "2026-01-12", "2026-06-01"]
    a = {d for _, d, _ in P.split_sessions(sess(dates), False)[0]}
    b = {d for _, d, _ in P.split_sessions(sess(dates), True)[0]}
    assert not (a & b)
    assert a | b == set(dates)


def test_reading_the_holdout_is_announced_in_the_report():
    """A locked read that looked like any other run is how a holdout gets
    spent twice without anyone noticing."""
    text = "\n".join(P.render({"former runner": g(20, 1.0)}, 20, 100,
                              "LOCKED, from 2026-01-12", 300, "2026-03-20", "x"))
    assert "THIS READ THE LOCKED HOLDOUT" in text
    assert "spent for this filter" in text


def test_an_ordinary_run_carries_no_such_banner():
    text = "\n".join(P.render({"former runner": g(20, 1.0)}, 20, 100,
                              "training, before 2026-01-12", 164, "2026-03-20", "x"))
    assert "LOCKED HOLDOUT" not in text


def test_the_side_is_stated_on_every_report():
    text = "\n".join(P.render({"former runner": g(20, 1.0)}, 20, 100,
                              "training, before 2026-01-12", 164, "2026-03-20", "x"))
    assert "SIDE: training" in text and "164 session(s) set aside" in text


def test_main_actually_applies_the_split(monkeypatch, tmp_path):
    """Reading the cut correctly and then not applying it would run every
    session including the locked ones — and the report would say 'training'
    while having read the holdout. The only symptom is a number that is
    quietly not out of sample."""
    import common.dbn_io as dbn
    from common import prior_spike as M

    seen = {}

    def fake_load(_root):
        return [("AAA", "2025-06-01", None), ("AAA", "2026-06-01", None)]

    def fake_backtest(df, d, tz, **kw):
        seen.setdefault("dates", []).append(str(d))
        return []

    monkeypatch.setattr(M, "load_sessions", fake_load)
    monkeypatch.setattr(M.MCL, "backtest_session", fake_backtest)
    monkeypatch.setattr(dbn, "daily_frame",
                        lambda root, ds: daily([("AAA", "2025-01-01", 1.0)]))
    monkeypatch.setattr(M, "emit",
                        lambda text, out, header="": seen.update(text=text))

    M.main(["--archive", str(tmp_path)])
    assert seen["dates"] == ["2025-06-01"], (
        "the 2026-06-01 session is past lock_from and must not be read")
    assert "SIDE: training" in seen["text"]
    # And the split reaches the report. Deriving it correctly and then not
    # passing it leaves the old constant in place — which is exactly the
    # 2026-09-10 defect, and its only symptom is a control that silently
    # stops dividing.
    assert "halves split at 2025-06-01" in seen["text"], seen["text"][:400]


# --- the control that did not control, 2026-09-10 ---------------------------

def test_a_split_outside_the_data_is_announced_not_silently_failed():
    """THE DEFECT THIS CATCHES. On the screened universe the split was
    hard-coded to bar_cache's midpoint, which sat AFTER the whole training
    side. Every 'late' figure was 0.00, so (early_a - early_b) * (0 - 0) was
    zero — not > 0 — and the report announced 'the sign flips between halves'
    about a control that had divided nothing. Two confident verdicts came out
    of it."""
    groups = {"former runner": g(40, 5.0, "2020-01-01"),
              "pump and dump": g(40, -5.0, "2020-01-01")}
    text = report(groups, split="2030-01-01")
    assert "DID NOT DIVIDE THIS RUN" in text
    assert "NO" in text and "VERDICT" in text
    assert "sign flips" not in text
    assert "SUPPORTED" not in text


def test_a_group_averaging_exactly_zero_is_not_mistaken_for_an_empty_half():
    """The guard counts trades rather than reading the mean, because a mean of
    0.0 is ambiguous between 'no trades' and 'trades that netted zero' — and a
    real group can produce the latter."""
    groups = {"former runner": g(20, 1.0, "2020-01-01") + g(20, 1.0, "2030-01-01"),
              "pump and dump": g(20, 0.0, "2020-01-01") + g(20, 0.0, "2030-01-01")}
    text = report(groups)
    assert "DID NOT DIVIDE" not in text


def test_the_split_is_derived_from_the_run_not_hard_coded():
    """A constant chosen for one cache is wrong for every other one."""
    inside = ["2024-08-01", "2025-06-01", "2026-01-05"]
    got, how = P.halves_split(inside)
    assert got == "2025-04-08" and "holdout" in how

    late_only = ["2026-05-01", "2026-06-01", "2026-07-01"]
    got, how = P.halves_split(late_only)
    assert late_only[0] < got <= late_only[-1]
    assert "midpoint" in how


def test_the_registered_split_is_not_used_when_it_divides_nothing():
    """holdout.json's split is right for the screened universe and wrong for a
    cache that starts after it."""
    got, how = P.halves_split(["2026-05-01", "2026-06-01"])
    assert got != "2025-04-08"


def test_the_report_states_which_split_it_used_and_why():
    text = report({"former runner": both(20, 1.0), "pump and dump": both(20, -1.0)})
    assert "halves split at 2026-03-20" in text
