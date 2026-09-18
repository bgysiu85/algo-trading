#!/usr/bin/env python3
"""H-S6: the flat daily stop and the SOLVED threshold that makes it a
comparator rather than a search.

Registered in docs/research/REGISTERED_stop_compare.md. Two things can quietly
turn this into a different test: a flat stop that is secretly peak-relative
(then §1's "genuinely different rules" is false and the comparison is a
tautology), and a threshold that gets chosen rather than solved (then §2's
"no stop is ever selected for performing well" is false). Both are pinned here.
"""
from __future__ import annotations

import pytest

from common import session_stop as S

F = 0.0
DAY = "2026-09-11"


def t(book, date, entry, exit_, net):
    return {"book": book, "date": date, "symbol": "X",
            "entry_et": f"{date} {entry}", "exit_et": f"{date} {exit_}",
            "net": float(net)}


def nets(rows):
    return sorted(float(r["net"]) for r in rows)


# --- the rule ---------------------------------------------------------------

def test_a_drawdown_past_the_stop_refuses_the_next_entry():
    rows = [t("MCL", DAY, "05:00", "05:10", -60),
            t("MCL", DAY, "05:30", "06:10", -50),
            t("MCL", DAY, "07:00", "07:10", -30)]
    res = S.flat_stop(rows, 100.0, f=F)
    assert nets(res["removed"]) == [-30.0]
    assert res["fired"][(DAY,)]["at"] == f"{DAY} 06:10"


def test_the_stop_is_inclusive_at_exactly_the_threshold():
    """`realised <= -STOP`, as §1 writes it. A book exactly at the stop has
    reached it, and `<` here would be a different rule by a cent."""
    rows = [t("MCL", DAY, "05:00", "05:10", -100),
            t("MCL", DAY, "07:00", "07:10", -30)]
    assert nets(S.flat_stop(rows, 100.0, f=F)["removed"]) == [-30.0]
    assert S.flat_stop(rows, 100.01, f=F)["removed"] == []


def test_none_is_bit_identical():
    rows = [t("MCL", DAY, "05:00", "05:10", -500)]
    res = S.flat_stop(rows, None, f=F)
    assert res["kept"] == rows and res["removed"] == [] and res["stop"] is None


def test_a_zero_or_negative_stop_is_refused_rather_than_run():
    """A stop of zero fires on the first cent lost; a negative one fires before
    the session opens. Either would print under this function's name."""
    rows = [t("MCL", DAY, "05:00", "05:10", -10)]
    for bad in (0.0, -50.0):
        with pytest.raises(ValueError, match="positive drawdown"):
            S.flat_stop(rows, bad, f=F)


# --- the two rules are genuinely different (§1) -----------------------------

def test_a_session_that_never_goes_green_trips_the_flat_stop_and_never_the_giveback():
    """Straight to -150 without ever being up: the give-back needs a $40 peak
    first and can never fire. If this case were shared the comparison would be
    a reparametrisation, not a comparison."""
    rows = [t("MCL", DAY, "05:00", "05:10", -150),
            t("MCL", DAY, "07:00", "07:10", -40)]
    assert S.apply_cap(rows, 0.50, f=F)["removed"] == []
    assert nets(S.flat_stop(rows, 100.0, f=F)["removed"]) == [-40.0]


def test_a_session_up_then_half_back_trips_the_giveback_and_never_the_flat_stop():
    """+200 back to +50: realised never goes below zero, so no positive stop
    can fire, and the give-back fires on the retreat. The other half of §1."""
    rows = [t("MCL", DAY, "05:00", "05:10", 200),
            t("MCL", DAY, "05:30", "06:10", -150),
            t("MCL", DAY, "07:00", "07:10", -30)]
    assert nets(S.apply_cap(rows, 0.50, f=F)["removed"]) == [-30.0]
    assert S.flat_stop(rows, 1.0, f=F)["removed"] == []


def test_the_flat_stop_has_no_arm_so_every_key_is_armed():
    """The give-back reports armed keys as those that reached $40. A flat stop
    is live from the first trade, so armed/fired means the same thing in both
    tables rather than silently counting different populations."""
    rows = [t("MCL", DAY, "05:00", "05:10", -5),
            t("MCL", "2026-09-12", "05:00", "05:10", -5)]
    res = S.flat_stop(rows, 100.0, f=F)
    assert len(res["armed"]) == 2 and res["fired"] == {}


# --- what it shares with the give-back --------------------------------------

def test_an_open_position_rides_its_exit():
    rows = [t("MCL", DAY, "05:00", "05:10", -120),
            t("MCL", DAY, "05:05", "09:00", -400),
            t("MCL", DAY, "07:00", "07:10", -30)]
    res = S.flat_stop(rows, 100.0, f=F)
    assert -400.0 in nets(res["kept"])
    assert nets(res["removed"]) == [-30.0]


def test_the_trip_point_moves_with_friction():
    """Three -30s: at $0 the book is at -90 and a $100 stop is inert; at $8.92
    it is at -116.76 and the same stop fires. Amendment A5's point, and it
    applies to the comparator or the two rules are priced differently."""
    rows = [t("MCL", DAY, "05:00", "05:10", -30),
            t("MCL", DAY, "05:20", "05:30", -30),
            t("MCL", DAY, "05:40", "05:50", -30),
            t("MCL", DAY, "07:00", "07:10", -25)]
    assert S.flat_stop(rows, 100.0, f=0.0)["removed"] == []
    assert nets(S.flat_stop(rows, 100.0, f=8.92)["removed"]) == [-25.0]


def test_scope_session_stops_every_strategy_and_scope_strategy_does_not():
    rows = [t("MCL", DAY, "05:00", "05:10", -120),
            t("MCL", DAY, "07:00", "07:10", -15),
            t("MC5", DAY, "07:00", "07:10", -25)]
    assert nets(S.flat_stop(rows, 100.0, scope="session", f=F)["removed"]) == [-25.0, -15.0]
    assert nets(S.flat_stop(rows, 100.0, scope="strategy", f=F)["removed"]) == [-15.0]


def test_sessions_are_independent():
    rows = [t("MCL", DAY, "05:00", "05:10", -120),
            t("MCL", DAY, "07:00", "07:10", -15),
            t("MCL", "2026-09-12", "07:00", "07:10", -15)]
    res = S.flat_stop(rows, 100.0, f=F)
    assert len(res["removed"]) == 1 and res["removed"][0]["date"] == DAY


# --- the solve (§2) ---------------------------------------------------------

def test_the_solved_stop_matches_the_target_count():
    rows = [t("MCL", DAY, f"{5 + i:02d}:00", f"{5 + i:02d}:30", -40) for i in range(6)]
    sol = S.solve_stop(rows, 3, f=F)
    assert sol["valid"] and sol["removed"] == 3
    # -40 each: after three exits the book is at -120, so the stop that leaves
    # exactly three entries refused is $120 and not $80 or $160.
    assert sol["stop"] == pytest.approx(120.0)


def test_removal_count_is_non_increasing_in_the_stop():
    """The solve bisects, which is only valid if a deeper stop never removes
    more. Checked on the shape the solve actually searches."""
    rows = [t("MCL", DAY, f"{5 + i:02d}:00", f"{5 + i:02d}:30", -13 * (i % 4 - 1))
            for i in range(12)]
    counts = [len(S.flat_stop(rows, s, f=F)["removed"])
              for s in S.stop_candidates(rows, scope="session", f=F)]
    assert counts == sorted(counts, reverse=True)


def test_the_candidates_are_the_depths_the_book_actually_reaches():
    """Nothing between two achievable depths changes which trades go, so the
    solve enumerates them rather than sweeping a grid that can land between
    two counts and report a threshold no session ever hit."""
    rows = [t("MCL", DAY, "05:00", "05:10", -30),
            t("MCL", DAY, "06:00", "06:10", 10),
            t("MCL", DAY, "07:00", "07:10", -50)]
    # running realised: -30, -20, -70  ->  depths 30, 20, 70
    assert S.stop_candidates(rows, scope="session", f=F) == [20.0, 30.0, 70.0]


def test_a_target_below_every_achievable_count_takes_the_deepest_stop():
    """Four -50s: the achievable counts are 3, 2, 1 and nothing smaller. A
    target of 0 is refused elsewhere; a target of 1 is reachable exactly, and
    the assertion is that the stop returned is the one producing it rather
    than a number picked for its P&L."""
    rows = [t("MCL", DAY, f"{5 + i:02d}:00", f"{5 + i:02d}:30", -50) for i in range(4)]
    sol = S.solve_stop(rows, 1, f=F)
    assert sol["removed"] == 1 and sol["stop"] == pytest.approx(150.0)


def test_a_tie_goes_to_the_larger_stop():
    """The registered tie-break, on a book whose counts straddle the target.

    Two entries sit between the first and second exits, so the achievable
    counts jump 4 -> 2 with nothing between. A target of 3 is equidistant, and
    §2 fixes the winner as the LARGER stop -- the rule that removes fewer
    trades -- so the tie-break can never become a choice made on results.
    """
    rows = [t("MCL", DAY, "05:00", "05:10", -100),
            t("MCL", DAY, "05:15", "05:16", 0),
            t("MCL", DAY, "05:20", "05:30", -100),
            t("MCL", DAY, "06:00", "06:10", 0),
            t("MCL", DAY, "06:20", "06:30", 0)]
    counts = {s: len(S.flat_stop(rows, s, f=F)["removed"]) for s in (100.0, 200.0)}
    assert counts == {100.0: 4, 200.0: 2}, counts
    sol = S.solve_stop(rows, 3, f=F)
    assert sol["stop"] == pytest.approx(200.0), "the tie went to the smaller stop"
    assert sol["removed"] == 2


def test_a_stop_that_never_fires_is_not_a_candidate():
    """The candidate set is the depths the book REACHES, so "deep enough never
    to fire" is never solved to.

    It would otherwise be available whenever the target is small, and a
    comparator that removes nothing scores D_flat = 0 -- which would hand the
    give-back a win by default on exactly the cells where the comparison
    matters most. Excluding it is the choice against the incumbent.
    """
    rows = [t("MCL", DAY, "05:00", "05:10", -100),
            t("MCL", DAY, "06:00", "06:10", 0),
            t("MCL", DAY, "07:00", "07:10", 0)]
    assert S.stop_candidates(rows, scope="session", f=F) == [100.0]
    sol = S.solve_stop(rows, 1, f=F)
    assert sol["stop"] == pytest.approx(100.0) and sol["removed"] == 2


def test_of_book_matches_the_count_on_the_strategy_being_read():
    """Under SESSION scope one pooled stop removes from both strategies. The
    registered cell is (strategy, scope, friction), so the count that must be
    matched is the one for the strategy being read -- matching the pooled
    total would leave that strategy unmatched, which is the one thing §2 says
    must not happen."""
    rows = [t("MCL", DAY, "05:00", "05:10", -120),
            t("MCL", DAY, "07:00", "07:10", -10),
            t("MC5", DAY, "07:30", "07:40", -10),
            t("MC5", DAY, "08:00", "08:10", -10)]
    sol = S.solve_stop(rows, 1, scope="session", f=F, of_book="MCL")
    assert sol["removed"] == 1 and sol["of_book"] == "MCL"
    # the same stop removes three trades in total, and two of them are MC5's
    total = S.flat_stop(rows, sol["stop"], scope="session", f=F)["removed"]
    assert len(total) == 3


def test_a_zero_target_is_refused_rather_than_solved_for_nothing():
    rows = [t("MCL", DAY, "05:00", "05:10", -50)]
    assert S.solve_stop(rows, 0, f=F)["valid"] is False


def test_a_book_that_never_goes_negative_has_no_candidates():
    rows = [t("MCL", DAY, "05:00", "05:10", 50),
            t("MCL", DAY, "06:00", "06:10", 50)]
    assert S.stop_candidates(rows, scope="session", f=F) == []
    assert S.solve_stop(rows, 1, f=F)["valid"] is False


def test_the_solve_is_cheaper_than_sweeping_every_candidate():
    """Bisection, not a sweep: 200 achievable depths must not cost 200 sweeps.
    A linear scan would still be correct and would make the full run minutes
    of nothing."""
    rows = [t("MCL", DAY, f"{5 + i // 60:02d}:{i % 60:02d}:00",
              f"{5 + i // 60:02d}:{i % 60:02d}:30", -7) for i in range(200)]
    sol = S.solve_stop(rows, 50, f=F)
    assert sol["valid"] and sol["candidates"] == 200
    assert sol["evaluations"] <= 12, sol["evaluations"]
