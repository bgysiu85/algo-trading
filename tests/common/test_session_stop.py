#!/usr/bin/env python3
"""H-S4: the session give-back cap, and the control that decides it.

Registered in docs/research/REGISTERED_giveback_cap.md. The sweep is where
this rule can quietly become a different rule, so these pin the semantics the
registration states rather than the ones that happen to be convenient:
realised-only, the arm, open positions riding their exits, the two scopes,
and the trip moving with friction.
"""
from __future__ import annotations

import pytest

from common import session_stop as S

F = 0.0                      # most cases read cleaner with friction off


def t(book, date, entry, exit_, net):
    return {"book": book, "date": date, "symbol": "X",
            "entry_et": f"{date} {entry}", "exit_et": f"{date} {exit_}",
            "net": float(net)}


def kept_nets(res):
    return sorted(float(r["net"]) for r in res["kept"])


def removed_nets(res):
    return sorted(float(r["net"]) for r in res["removed"])


# --- the control case ------------------------------------------------------

def test_none_is_bit_identical_and_keeps_input_order():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "06:00", "06:10", -80)]
    res = S.apply_cap(rows, None, f=F)
    assert res["kept"] == rows and res["removed"] == []
    assert res["fired"] == {} and res["giveback"] is None


# --- the rule ---------------------------------------------------------------

def test_a_fifty_percent_giveback_stops_the_next_entry():
    """Peak +100 at 05:10, back to +50 at 06:10 -> trips; the 07:00 entry is
    refused. 50 <= 0.5 * 100 exactly, and the registration's `<=` takes it."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -50),
            t("MCL", "2026-09-11", "07:00", "07:10", -30)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert removed_nets(res) == [-30.0]
    assert kept_nets(res) == [-50.0, 100.0]
    assert res["fired"][("2026-09-11",)]["at"] == "2026-09-11 06:10"
    assert res["fired"][("2026-09-11",)]["peak"] == 100.0


def test_a_giveback_just_short_of_the_threshold_does_not_trip():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -49),
            t("MCL", "2026-09-11", "07:00", "07:10", -30)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert res["removed"] == [] and res["fired"] == {}


def test_the_arm_stops_the_rule_firing_on_a_small_peak():
    """A peak of $30 never arms at ARM=$40, however much of it is given back."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 30),
            t("MCL", "2026-09-11", "05:30", "06:10", -30),
            t("MCL", "2026-09-11", "07:00", "07:10", -100)]
    assert S.apply_cap(rows, 0.50, f=F)["removed"] == []
    assert S.apply_cap(rows, 0.50, arm=20.0, f=F)["removed"] != []


def test_the_arm_is_the_registered_forty_dollars():
    assert S.ARM == 40.0 and S.GIVEBACK == 0.50 and S.CUT_DRAWS == 10_000


def test_a_session_that_never_goes_green_never_fires():
    """The rule is a retreat from a PEAK, not a daily loss stop -- the
    registration says so explicitly and the two are different items."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", -200),
            t("MCL", "2026-09-11", "06:00", "06:10", -200),
            t("MCL", "2026-09-11", "07:00", "07:10", -200)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert res["removed"] == [] and res["armed"] == set()


def test_a_day_still_net_green_can_fire():
    """+200 then back to +60: green on the day, and the cap fires anyway."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 200),
            t("MCL", "2026-09-11", "05:30", "06:10", -140),
            t("MCL", "2026-09-11", "07:00", "07:10", 500)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert removed_nets(res) == [500.0], "a green day must still be able to trip"


# --- open positions ride their exits (§1) ----------------------------------

def test_a_position_open_when_the_cap_fires_keeps_its_own_exit():
    """Entered 05:30, still open when the 06:10 exit trips the cap. It is not
    removed and its P&L still lands -- force-flattening is a different rule
    and is not registered."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:20", "06:10", -60),
            t("MCL", "2026-09-11", "05:30", "09:00", -400)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert -400.0 in kept_nets(res), "an open position was flattened by the cap"
    assert res["removed"] == []


def test_an_exit_landing_at_the_same_instant_as_an_entry_is_counted_first():
    """The live reading: what is realised when the decision is made includes
    the exit that has just printed."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:20", "06:00", -60),
            t("MCL", "2026-09-11", "06:00", "06:30", -30)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert removed_nets(res) == [-30.0]


def test_pnl_lands_in_exit_order_even_when_a_trade_is_held_across_the_others():
    """A position opened first and closed last must not stall the queue.

    Realised P&L lands when a trade CLOSES, so the sweep walks exits in exit
    order. Walking them in entry order puts the long-held trade at the head of
    the queue, where its far-off exit blocks every trade behind it and the cap
    silently stops firing at all. Every other fixture here enters and exits in
    the same order, so this is the only case that separates the two.

    Here: A is open 05:00-09:00; B books +100 at 05:10 (peak, armed); C books
    -60 at 05:20, which is a give-back past half; D at 06:00 must be refused.
    """
    rows = [t("MCL", "2026-09-11", "05:00", "09:00", -10),
            t("MCL", "2026-09-11", "05:05", "05:10", 100),
            t("MCL", "2026-09-11", "05:15", "05:20", -60),
            t("MCL", "2026-09-11", "06:00", "06:10", -25)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert removed_nets(res) == [-25.0], "the held position stalled the queue"
    assert res["fired"][("2026-09-11",)]["at"] == "2026-09-11 05:20"


# --- the two scopes (amendment A2) -----------------------------------------

def test_session_scope_stops_every_strategy():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -60),
            t("MC5", "2026-09-11", "07:00", "07:10", -25)]
    res = S.apply_cap(rows, 0.50, scope="session", f=F)
    assert removed_nets(res) == [-25.0], "MC5 kept trading after the account tripped"
    assert list(res["fired"]) == [("2026-09-11",)]


def test_strategy_scope_stops_only_the_strategy_that_gave_back():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -60),
            t("MCL", "2026-09-11", "07:00", "07:10", -15),
            t("MC5", "2026-09-11", "07:00", "07:10", -25)]
    res = S.apply_cap(rows, 0.50, scope="strategy", f=F)
    assert removed_nets(res) == [-15.0], "MC5 was stopped by MCL's give-back"
    assert list(res["fired"]) == [("2026-09-11", "MCL")]


def test_one_strategys_profit_can_mask_anothers_giveback_under_session_scope():
    """The scopes are not a sensitivity of each other: on these rows the
    account never gives back 50% while MCL alone does."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -60),
            t("MC5", "2026-09-11", "05:20", "06:00", 300),
            t("MCL", "2026-09-11", "07:00", "07:10", -15)]
    assert S.apply_cap(rows, 0.50, scope="session", f=F)["removed"] == []
    assert removed_nets(S.apply_cap(rows, 0.50, scope="strategy", f=F)) == [-15.0]


def test_an_unknown_scope_is_refused_rather_than_defaulted():
    with pytest.raises(ValueError, match="scope"):
        S.apply_cap([t("MCL", "2026-09-11", "05:00", "05:10", 1)], 0.5, scope="book")


def test_sessions_are_independent():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -60),
            t("MCL", "2026-09-11", "07:00", "07:10", -15),
            t("MCL", "2026-09-12", "07:00", "07:10", -15)]
    res = S.apply_cap(rows, 0.50, f=F)
    assert len(res["removed"]) == 1
    assert res["removed"][0]["date"] == "2026-09-11"


# --- friction moves the trip (amendment A5) --------------------------------

def test_the_trip_point_moves_with_friction():
    """Three +20 winners then a -10: at $0 friction the peak is 60 and the
    book never gives back half. At $8.92 the same trades peak at 33.24 and
    the -18.92 takes it to 14.32, which is under half -- so the cap that is
    inert at one friction level fires at another. A cap computed once and
    re-priced would miss this."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 60),
            t("MCL", "2026-09-11", "06:00", "06:10", -5),
            t("MCL", "2026-09-11", "07:00", "07:10", -5),
            t("MCL", "2026-09-11", "08:00", "08:10", -99)]
    # at $0: peak 60, realised 50 -- above half, inert
    assert S.apply_cap(rows, 0.50, f=0.0)["removed"] == []
    # at $8.92: peak 51.08, realised 23.24 -- under half, fires
    fired = S.apply_cap(rows, 0.50, f=8.92)
    assert removed_nets(fired) == [-99.0]


# --- the control -----------------------------------------------------------

def test_random_cut_removes_a_tail_from_the_fired_sessions_only():
    rows = ([t("MCL", "2026-09-11", f"0{5+i}:00", f"0{5+i}:30", -10) for i in range(4)]
            + [t("MCL", "2026-09-12", f"0{5+i}:00", f"0{5+i}:30", -10) for i in range(4)])
    out = S.random_cut(rows, [("2026-09-11",)], "session", 0.0, draws=200)
    assert out["valid"] and out["keys"] == 1
    # a 4-trade session cuts at 1..3, so 1 to 3 trades go, never 0 and never 4
    assert 1.0 <= out["removed"]["p05"] and out["removed"]["p95"] <= 3.0
    assert out["removed"]["mean"] == pytest.approx(2.0, abs=0.3)


def test_random_cut_is_seeded_and_reproducible():
    rows = [t("MCL", "2026-09-11", f"0{5+i}:00", f"0{5+i}:30", -10 * i) for i in range(5)]
    a = S.random_cut(rows, [("2026-09-11",)], "session", 0.0, draws=500)
    b = S.random_cut(rows, [("2026-09-11",)], "session", 0.0, draws=500)
    assert a["per_trade"] == b["per_trade"]


def test_random_cut_on_a_losing_book_is_centred_above_zero_per_trade_only_if_the_tail_is_worse():
    """The control's whole job: on a book whose trades all lose the SAME,
    truncating anywhere moves per trade by nothing. A cap that reads +0 here
    has found nothing, and the band says so."""
    rows = [t("MCL", "2026-09-11", f"0{5+i}:00", f"0{5+i}:30", -10) for i in range(6)]
    out = S.random_cut(rows, [("2026-09-11",)], "session", 0.0, draws=500)
    assert out["per_trade"]["p50"] == pytest.approx(0.0, abs=1e-9)
    assert out["per_trade"]["p95"] == pytest.approx(0.0, abs=1e-9)


def test_random_cut_refuses_a_single_trade_session_rather_than_removing_nothing():
    rows = [t("MCL", "2026-09-11", "05:00", "05:30", -10)]
    assert S.random_cut(rows, [("2026-09-11",)], "session", 0.0, draws=10)["valid"] is False


# --- reporting --------------------------------------------------------------

def test_fire_clock_buckets_by_et_hour():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 100),
            t("MCL", "2026-09-11", "05:30", "06:10", -60),
            t("MCL", "2026-09-11", "07:00", "07:10", -15)]
    res = S.apply_cap(rows, 0.50, f=F)
    # The trip is the 06:10 exit. Slicing the timestamp from the left would
    # read "20" out of the year and print a 20:00 bucket that looks like a
    # late-session fire -- which is exactly the row §4 asks us to read.
    assert S.fire_clock(res) == {"06:00": 1}


def test_per_trade_and_total_carry_friction():
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", 10),
            t("MCL", "2026-09-11", "06:00", "06:10", 20)]
    assert S.per_trade(rows, 4.26) == pytest.approx(15 - 4.26)
    assert S.total(rows, 4.26) == pytest.approx(30 - 8.52)
    assert S.per_trade([], 4.26) == 0.0
