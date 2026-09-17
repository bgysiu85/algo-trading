#!/usr/bin/env python3
"""The five scenarios, wired: which book each one reads and what it composes.

The arithmetic of the cap is `test_session_stop`; the floor's is
`tests/strategy/test_price_floor`. This is the wiring between them, which is
where a scenario can quietly end up reading the wrong book -- scenario 4 is
the cap applied to the FLOORED books, and a fall-through default that returned
the plain ones would still produce a plausible table.
"""
from __future__ import annotations

import pytest

from common import session_scenarios as M
from common import session_stop as SS

F = 0.0
DAY = "2026-09-11"


def r(book, entry, exit_, net, px=6.0):
    return {"book": book, "symbol": f"S{entry[:2]}", "date": DAY, "ordinal": 1,
            "entry_et": f"{DAY} {entry}", "exit_et": f"{DAY} {exit_}",
            "entry_px": px, "exit_px": px, "reason": "t", "bars_held": 1,
            "net": float(net)}


def four_books():
    """MCL gives back past half; MC5 does not. The floored books hold only the
    winner, so a cap applied to them has nothing left to trip on."""
    return {
        "MCL": [r("MCL", "05:00", "05:10", 100), r("MCL", "05:30", "06:10", -60),
                r("MCL", "07:00", "07:10", -25)],
        "MCL-pf5": [r("MCL-pf5", "05:00", "05:10", 100)],
        "MC5": [r("MC5", "07:00", "07:10", -40)],
        "MC5-pf5": [r("MC5-pf5", "07:00", "07:10", -40)],
    }


def test_scenario_1_is_the_floored_books_untouched():
    sc = M.scenario_books(four_books(), F)
    assert sc["1"]["MCL"] == four_books()["MCL-pf5"]
    assert sc["1"]["MC5"] == four_books()["MC5-pf5"]


def test_scenario_2_stops_every_strategy_and_3_stops_only_the_one():
    sc = M.scenario_books(four_books(), F)
    assert len(sc["2"]["MCL"]) == 2 and len(sc["2"]["MC5"]) == 0
    assert len(sc["3"]["MCL"]) == 2 and len(sc["3"]["MC5"]) == 1


def test_scenarios_4_and_5_read_the_FLOORED_books_not_the_plain_ones():
    """The wiring this file exists for. The floored MCL book holds one winner
    and never gives back, so 4 and 5 must equal scenario 1 here. Reading the
    plain books instead would remove trades and print a different, plausible
    number."""
    sc = M.scenario_books(four_books(), F)
    assert sc["4"]["MCL"] == sc["1"]["MCL"]
    assert sc["5"]["MCL"] == sc["1"]["MCL"]
    assert sc["4"]["MC5"] == sc["1"]["MC5"]
    assert sc["4"]["MCL"] != sc["2"]["MCL"], "scenario 4 is reading the plain book"


def test_a_book_the_cap_empties_is_not_confused_with_a_book_never_in_scope():
    """MC5 is stopped entirely under session scope. Its scenario-2 book is
    empty because the cap removed it, and that must not be reached through a
    default that would also fire if the book were simply absent."""
    sc = M.scenario_books(four_books(), F)
    assert sc["2"]["MC5"] == []
    assert sc["caps"]["2"]["removed"], "nothing was removed, so the case is vacuous"


def test_the_trip_is_recomputed_at_each_friction_level():
    """Amendment A5. Same books, two frictions, different kept counts."""
    books = {"MCL": [r("MCL", "05:00", "05:10", 60), r("MCL", "06:00", "06:10", -5),
                     r("MCL", "07:00", "07:10", -5), r("MCL", "08:00", "08:10", -99)],
             "MCL-pf5": [], "MC5": [], "MC5-pf5": []}
    assert len(M.scenario_books(books, 0.0)["2"]["MCL"]) == 4
    assert len(M.scenario_books(books, 8.92)["2"]["MCL"]) == 3


def test_the_registered_constants_are_the_ones_the_runner_uses():
    assert M.PRICE_FLOOR == 5.00
    assert SS.GIVEBACK == 0.50 and SS.ARM == 40.0
    assert M.PAIRS.endswith("screen_pairs_pit_itch_v2.json"), "the v2 book is the deciding file"
    assert M.build_parser().parse_args([]).dataset == "XNAS.ITCH"


def test_the_four_engine_books_are_two_strategies_at_two_floors():
    assert [b[0] for b in M.BOOKS] == ["MCL", "MCL-pf5", "MC5", "MC5-pf5"]
    assert [b[2] for b in M.BOOKS] == [None, 5.00, None, 5.00]


def test_render_names_both_registrations_and_every_scenario():
    books = four_books()
    text = "\n".join(M.render(books, 24, 0, [DAY, "2026-09-12"], 1.0, 1, [],
                              universe=M.PAIRS, dataset="XNAS.ITCH"))
    for tag in ("SCENARIO 1", "SCENARIO 2", "SCENARIO 3", "SCENARIO 4", "SCENARIO 5"):
        assert tag in text
    assert "REGISTERED_price_floor.md" in text and "REGISTERED_giveback_cap.md" in text
    assert "$1.00" in text and "$4.26" in text and "$8.92" in text
    # A6: the margin is shown beside reading 1 and labelled as not scored
    assert "not scored: the project's $4.26 margin" in text
    # A7: the composition is read against scenario 1 as well as the baseline
    assert "ON TOP OF the floor" in text
    assert "NOT A CAP MODEL" in text and "holdout.json has not been touched" in text
    # scenario 1's registered verdict is read ONCE, at the measured friction,
    # because gate_study.verdict is defined at $4.26 -- printing it under all
    # three friction headings would be one verdict shown over three books.
    assert text.count("THE REGISTERED VERDICT") == 1
    assert text.count("SCENARIO 2:") == 3, "the cap's verdict IS friction-dependent (A5)"


def test_cap_verdict_reports_which_way_the_control_biases_the_test():
    """Amendment A4: the count mismatch is stated, not left to the reader."""
    books = {"MCL": [r("MCL", f"0{5+i}:00", f"0{5+i}:30", 60 if i == 0 else -20)
                     for i in range(6)],
             "MCL-pf5": [], "MC5": [], "MC5-pf5": []}
    sc = M.scenario_books(books, F)
    tag, lines = M.cap_verdict(books["MCL"], sc["2"]["MCL"], DAY, 10,
                               sc["caps"]["2"], "session", F)
    text = "\n".join(lines)
    assert "trades removed: the cap" in text
    assert ("conservative" in text)
    assert tag in ("PASSES", "NOTHING")
