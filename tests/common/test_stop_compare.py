#!/usr/bin/env python3
"""H-S6's comparator: the cell, the verdict, and the inputs it refuses.

Registered in docs/research/REGISTERED_stop_compare.md §4. The decision rule
is three-valued and the third value exists so the holdout is not spent on a
marginal reading -- an UNDECIDED that quietly renders as a pass would be worse
than no test at all, so each branch is pinned separately.
"""
from __future__ import annotations

import json

import pytest

from common import session_stop as SS
from common import stop_compare as SC

F = 0.0


def t(book, date, entry, exit_, net, symbol="X"):
    return {"book": book, "date": date, "symbol": symbol,
            "entry_et": f"{date} {entry}", "exit_et": f"{date} {exit_}",
            "net": float(net)}


def cellstub(d_give, d_flat, boot_p, valid=True):
    return {"d_give": d_give, "d_flat": d_flat, "boot_p": boot_p,
            "diff": d_give - d_flat, "solved": {"valid": valid}}


def cells(at426, at892, at100=None):
    return {"$1.00": at100 or at426, "$4.26": at426, "$8.92": at892}


# --- the verdict (§4) -------------------------------------------------------

def test_the_shape_survives_when_it_wins_at_both_levels_with_the_bootstrap():
    tag, _ = SC.verdict(cells(cellstub(+0.78, +0.61, 0.97),
                              cellstub(+0.76, +0.60, 0.96)))
    assert tag == "THE SHAPE SURVIVES"


def test_the_shape_adds_nothing_when_the_flat_stop_wins_at_either_level():
    """§4: `D_flat >= D_give` at EITHER level ends it. A rule that survives
    only at the friction level that flatters it has not survived."""
    tag, _ = SC.verdict(cells(cellstub(+0.78, +0.61, 0.99),
                              cellstub(+0.40, +0.55, 0.99)))
    assert tag == "THE SHAPE ADDS NOTHING"
    tag, _ = SC.verdict(cells(cellstub(+0.30, +0.30, 0.99),
                              cellstub(+0.80, +0.10, 0.99)))
    assert tag == "THE SHAPE ADDS NOTHING", "an exact tie is not a win for the shape"


def test_a_positive_difference_with_a_short_bootstrap_is_undecided():
    """The registered prediction is 'survives narrowly, bootstrap marginal',
    so this is the branch most likely to be reached -- and it must not round
    up to a pass."""
    tag, why = SC.verdict(cells(cellstub(+0.20, +0.10, 0.91),
                                cellstub(+0.18, +0.09, 0.97)))
    assert tag == "UNDECIDED"
    assert "$4.26" in " ".join(why)


def test_a_cell_with_no_matched_stop_is_undecided_rather_than_scored():
    tag, _ = SC.verdict(cells(cellstub(0.0, 0.0, 0.0, valid=False),
                              cellstub(+0.5, +0.1, 0.99)))
    assert tag == "UNDECIDED"


def test_the_dollar_one_level_is_not_part_of_the_verdict():
    """§4 names $4.26 and $8.92. $1.00 is printed because the deltas move with
    friction, and a failure there must not decide anything."""
    tag, _ = SC.verdict(cells(cellstub(+0.5, +0.1, 0.99), cellstub(+0.5, +0.1, 0.99),
                              at100=cellstub(+0.1, +0.9, 0.10)))
    assert tag == "THE SHAPE SURVIVES"
    assert SC.SCORED_AT == ("$4.26", "$8.92")


# --- the cell ---------------------------------------------------------------

def rows_that_fire_both_rules():
    """One session per rule, plus a quiet one, on two strategies.

    09-11 gives back from a peak (the give-back's case); 09-12 goes straight
    down without ever being green (the flat stop's case). Both rules therefore
    have something to remove and the two do not fire on the same day.
    """
    return ([t("MCL", "2026-09-11", "05:00", "05:10", 120),
             t("MCL", "2026-09-11", "05:20", "06:10", -90),
             t("MCL", "2026-09-11", "07:00", "07:10", -40),
             t("MCL", "2026-09-11", "08:00", "08:10", -20)]
            + [t("MCL", "2026-09-12", "05:00", "05:10", -150),
               t("MCL", "2026-09-12", "07:00", "07:10", -60),
               t("MCL", "2026-09-12", "08:00", "08:10", -10)]
            + [t("MC5", "2026-09-11", "05:00", "05:10", -5, symbol="Y"),
               t("MC5", "2026-09-12", "05:00", "05:10", -5, symbol="Y")])


def test_the_cell_matches_the_budget_and_reads_both_rules_on_the_same_base():
    c = SC.cell(rows_that_fire_both_rules(), "MCL", "strategy", F)
    assert c["target"] > 0 and c["solved"]["valid"]
    # §2's whole design: both rules spend the same abstention budget
    assert c["solved"]["removed"] == c["target"]
    assert c["diff"] == pytest.approx(c["d_give"] - c["d_flat"])
    # and the two rules fire on different days here, so the comparison is not
    # a reparametrisation of one rule
    assert c["days"]["give_only"] and c["days"]["flat_only"]


def test_the_cell_reads_only_the_strategy_it_names_under_session_scope():
    """Under session scope both rules act on the pooled book. The delta read
    must still be MCL's, or the cell silently scores MC5's trades too."""
    rows = rows_that_fire_both_rules()
    c = SC.cell(rows, "MCL", "session", F)
    assert c["n_base"] == sum(1 for r in rows if r["book"] == "MCL")
    assert all(r["book"] == "MCL" for r in c["g_kept"])
    assert all(r["book"] == "MCL" for r in c["f_kept"])


def test_under_session_scope_the_budget_matched_is_the_strategys_not_the_pool():
    """One pooled stop removes from both strategies at once. The registered
    cell is (strategy, scope, friction), so the count solved for is MCL's --
    matching the pooled total would leave the strategy actually being read
    unmatched, and the two rules would then be spending different budgets on
    it, which is the one thing §2 rules out.
    """
    rows = rows_that_fire_both_rules() + [
        t("MC5", "2026-09-11", "07:30", "07:40", -30, symbol="Y"),
        t("MC5", "2026-09-11", "08:30", "08:40", -30, symbol="Y"),
        t("MC5", "2026-09-12", "07:30", "07:40", -30, symbol="Y")]
    c = SC.cell(rows, "MCL", "session", F)
    assert c["solved"]["removed"] == c["target"], "the pooled count was matched"
    # and the stop really does remove MC5 trades too -- otherwise the pooled
    # and per-strategy counts coincide and this proves nothing
    pooled = SS.flat_stop(rows, c["solved"]["stop"], scope="session", f=F)["removed"]
    assert len(pooled) > c["target"]


def test_the_bootstrap_reads_the_giveback_minus_the_flat_stop():
    """Signed the way §4 words it: the difference is `D_give - D_flat`, so a
    book where the give-back is the better rule has to bootstrap ABOVE zero.
    Backwards, every verdict in the report inverts and still looks ordinary.
    """
    c = SC.cell(rows_that_fire_both_rules(), "MCL", "strategy", F)
    # On this book the FLAT stop is the better rule: it removes the 09-12
    # pair worth (35.00) a trade while the give-back removes the 09-11 pair
    # worth (30.00), so `D_give - D_flat` is negative and the bootstrap has to
    # land below a half. Backwards, it reads 0.751 and every verdict in the
    # report inverts while still looking ordinary.
    assert c["removed_pt"]["flat"] < c["removed_pt"]["give"]
    assert c["diff"] < 0 and c["total_diff"] < 0
    assert c["boot_p"] < 0.5, "the difference is signed the wrong way round"


def test_a_cell_the_giveback_never_fired_on_is_reported_not_scored():
    """No budget to match means nothing to compare. Solving a stop for a
    target of zero would produce a rule and a number, which is worse."""
    rows = [t("MCL", "2026-09-11", "05:00", "05:10", -10),
            t("MCL", "2026-09-11", "07:00", "07:10", -10)]
    c = SC.cell(rows, "MCL", "strategy", F)
    assert c["target"] == 0 and c["solved"]["valid"] is False
    assert "nothing to compare" in " ".join(SC.cell_lines(c))


def test_the_fixed_stops_are_computed_and_labelled_never_scored():
    c = SC.cell(rows_that_fire_both_rules(), "MCL", "strategy", F)
    assert [x["stop"] for x in c["fixed"]] == list(SC.FIXED)
    text = " ".join(SC.cell_lines(c))
    assert "REPORTED, NEVER SCORED" in text and "is not adoptable" in text


def test_the_cell_moves_with_friction():
    """Amendment A5 applies to the comparator: `realised` is net of friction,
    so both trip points move and the cell must be recomputed per level rather
    than priced once."""
    rows = rows_that_fire_both_rules()
    a = SC.cell(rows, "MCL", "strategy", 0.0)
    b = SC.cell(rows, "MCL", "strategy", 8.92)
    assert (a["target"], a["solved"]["stop"]) != (b["target"], b["solved"]["stop"])


# --- the inputs -------------------------------------------------------------

def write_inputs(tmp_path, meta_extra=None, books=("MCL", "MC5")):
    import csv
    p = tmp_path / "trades.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["book", "symbol", "date", "entry_et",
                                           "exit_et", "net"])
        w.writeheader()
        for b in books:
            w.writerow(t(b, "2026-09-11", "05:00", "05:10", -10))
    meta = {"pairs": "var/state/screen_pairs_pit_itch_v2.json", "dataset": "XNAS.ITCH",
            "sessions": ["2026-09-11"], "symbol_days": 1,
            "giveback": SS.GIVEBACK, "arm": SS.ARM}
    meta.update(meta_extra or {})
    (tmp_path / "trades_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_a_matching_csv_is_accepted(tmp_path):
    p = write_inputs(tmp_path)
    assert SC.input_refusal(SC.load_meta(p), SC.load_books(p)) is None


def test_a_csv_written_with_another_giveback_is_refused(tmp_path):
    """The incumbent has to be the rule H-S4 passed on. A CSV written at 40%
    describes a different rule, and the report would still print 'the
    give-back' at the top of the table."""
    p = write_inputs(tmp_path, {"giveback": 0.40})
    why = SC.input_refusal(SC.load_meta(p), SC.load_books(p))
    assert why and "different incumbent" in why


def test_a_csv_written_with_another_arm_is_refused(tmp_path):
    p = write_inputs(tmp_path, {"arm": 20.0})
    assert "arm" in (SC.input_refusal(SC.load_meta(p), SC.load_books(p)) or "")


def test_a_meta_that_records_neither_is_refused_rather_than_defaulted(tmp_path):
    p = write_inputs(tmp_path)
    meta = SC.load_meta(p)
    del meta["giveback"]
    why = SC.input_refusal(meta, SC.load_books(p))
    assert why and "cannot be identified" in why


def test_a_csv_missing_a_book_is_refused(tmp_path):
    p = write_inputs(tmp_path, books=("MCL",))
    assert "MC5" in (SC.input_refusal(SC.load_meta(p), SC.load_books(p)) or "")


# --- the report -------------------------------------------------------------

def test_the_report_names_the_registration_the_source_and_every_cell(tmp_path):
    rows = rows_that_fire_both_rules()
    books = {"MCL": [r for r in rows if r["book"] == "MCL"],
             "MC5": [r for r in rows if r["book"] == "MC5"]}
    text = "\n".join(SC.render(books, {"pairs": "p.json", "dataset": "XNAS.ITCH",
                                       "sessions": ["2026-09-11", "2026-09-12"],
                                       "symbol_days": 4}, "t.csv"))
    assert SC.REGISTERED in text
    assert "the SAME book H-S4 passed on" in text
    for label, _ in SC.FRICTIONS:
        assert f"AT {label} A ROUND TRIP" in text
    for scope in SS.SCOPES:
        for strat in SC.PLAIN:
            assert f"{strat}  scope {scope}" in text
    assert "holdout.json stays shut" in text
