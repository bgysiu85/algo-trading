"""Tests for strategy/swing/pit_validate.py (G8 step 4, W07-0002).

Offline throughout: everything this module reads is a local file it is
handed directly, same as pit_universe's own report stage. No network."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from strategy.swing import pit_universe as P
from strategy.swing import pit_validate as V

D = dt.date


# --------------------------------------------------------------- name matching

def test_norm_name_strips_suffixes_and_punctuation():
    assert V.norm_name("Marsh & McLennan Companies, Inc.") == "marsh mclennan"
    assert V.norm_name("The Bank of New York Mellon Corporation") == \
        "bank of new york mellon"


def test_rename_candidate_exact_match_only():
    active = {V.norm_name("The Bank of New York Mellon Corporation"): "BNY"}
    assert V.find_rename_candidate(
        "The Bank of New York Mellon Corporation", active) == "BNY"


def test_rename_candidate_does_not_false_positive_on_short_suffix_stripped_names():
    # Regression: "IES Holdings Inc" normalizes to "ies", which is a
    # substring of "technologies" -- a loose containment match used to claim
    # this was a rename of "Lumen Technologies Inc". It must not.
    active = {V.norm_name("IES Holdings Inc"): "IESC"}
    assert V.find_rename_candidate("Lumen Technologies Inc", active) is None
    # Same shape: "Cabot Corporation" -> "cabot" is a substring of
    # "Cabot Oil & Gas Corporation" -> "cabot oil gas", but they are two
    # different companies.
    active2 = {V.norm_name("Cabot Corporation"): "CBT"}
    assert V.find_rename_candidate("Cabot Oil & Gas Corporation", active2) is None


def test_rename_candidate_no_match_returns_none():
    assert V.find_rename_candidate("Nobody Here Inc", {"somebody": "X"}) is None
    assert V.find_rename_candidate("", {"somebody": "X"}) is None


# ------------------------------------------------------------------ coverage

WINDOW = (D(2016, 1, 1), D(2018, 12, 31))


def business_days_csv(path: Path, start: D, end: D) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(P.PRICE_FIELDS)
        d = start
        while d <= end:
            if d.weekday() < 5:
                w.writerow([d.isoformat(), 1, 1, 1, 1, 1, 100])
            d += dt.timedelta(days=1)


def test_true_coverage_full_when_rows_span_the_whole_spell(tmp_path):
    spell = P.Spell("sp500", "GOOD", "Good Co", D(2016, 1, 1), None, True, False)
    csvp = tmp_path / "GOOD.csv"
    business_days_csv(csvp, D(2015, 6, 1), D(2019, 6, 1))
    verdict, in_win, expected = V.true_coverage(spell, V.price_dates(csvp), WINDOW)
    assert verdict == "full"
    assert in_win > 0


def test_true_coverage_none_when_no_price_file(tmp_path):
    spell = P.Spell("sp500", "GONE", "Gone Co", D(2016, 1, 1), D(2017, 1, 1), False, True)
    verdict, in_win, expected = V.true_coverage(spell, [], WINDOW)
    assert verdict == "none"
    assert in_win == 0


def test_true_coverage_suspect_reuse_when_data_exists_but_outside_spell_window(tmp_path):
    # The reused-ticker shape: a spell that ended in 2016, but the only price
    # data on file starts in 2021 -- pit_universe's own first/last check would
    # still call the LAST date "covered" (data runs to today), which is
    # exactly the blind spot this module exists to close.
    spell = P.Spell("sp500", "REUSE", "Old Co", D(2016, 1, 1), D(2016, 6, 1), False, True)
    csvp = tmp_path / "REUSE.csv"
    business_days_csv(csvp, D(2021, 1, 1), D(2026, 1, 1))
    verdict, in_win, expected = V.true_coverage(spell, V.price_dates(csvp), WINDOW)
    assert verdict == "suspect_reuse"
    assert in_win == 0


def test_true_coverage_outside_window_entirely(tmp_path):
    spell = P.Spell("sp500", "LATER", "Later Co", D(2025, 1, 1), None, True, False)
    verdict, in_win, expected = V.true_coverage(spell, [], WINDOW)
    assert verdict == "outside"


def test_true_coverage_partial_when_density_is_low_but_nonzero(tmp_path):
    spell = P.Spell("sp500", "THIN", "Thin Co", D(2016, 1, 1), D(2018, 12, 31), False, True)
    csvp = tmp_path / "THIN.csv"
    # Only a handful of rows scattered across the window -- real overlap,
    # but nowhere near enough to call it full coverage.
    with csvp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(P.PRICE_FIELDS)
        for d in ("2016-02-01", "2017-02-01", "2018-02-01"):
            w.writerow([d, 1, 1, 1, 1, 1, 100])
    verdict, in_win, expected = V.true_coverage(spell, V.price_dates(csvp), WINDOW)
    assert verdict in ("partial", "suspect_reuse")
    assert in_win == 3


# --------------------------------------------------------------------- end to end

def build_repo(out: Path) -> None:
    (out / "eod").mkdir(parents=True)
    (out / "raw").mkdir(parents=True)
    P.write_membership(out / "membership.csv", [
        P.Spell("sp500", "GONE", "Real Old Co", D(2016, 1, 1), D(2016, 6, 1), False, True),
        P.Spell("sp500", "REUSE", "Real Acquired Co", D(2016, 1, 1), D(2016, 6, 1), False, True),
        P.Spell("sp500", "GOOD", "Still Here Inc", D(2016, 1, 1), None, True, False),
    ])
    business_days_csv(out / "eod" / "GOOD.csv", D(2016, 1, 1), D(2018, 12, 31))
    business_days_csv(out / "eod" / "REUSE.csv", D(2021, 1, 1), D(2026, 1, 1))


def test_stage_validate_end_to_end(tmp_path):
    build_repo(tmp_path)
    lines = V.stage_validate(tmp_path, WINDOW, None, ["GOOD", "REUSE", "GONE"])
    text = "\n".join(lines)
    assert "suspect_reuse" in text
    assert "REUSE" in text
    assert "GOOD" not in text.split("WATCH-LIST")[0].split("SUSPECT_REUSE")[1].split("NO-START-DATE")[0]


def test_write_suspects_csv_only_lists_the_true_hole(tmp_path):
    build_repo(tmp_path)
    V.write_suspects_csv(tmp_path / "suspects.csv", tmp_path, WINDOW)
    rows = list(csv.DictReader((tmp_path / "suspects.csv").open()))
    codes = {r["code"] for r in rows}
    assert codes == {"GONE", "REUSE"}
    assert "GOOD" not in codes


def test_undated_spells_split_by_active_status(tmp_path):
    (tmp_path / "eod").mkdir(parents=True)
    (tmp_path / "raw").mkdir(parents=True)
    P.write_membership(tmp_path / "membership.csv", [
        P.Spell("sp500", "STILLIN", "Still In Co", None, None, True, False),
        P.Spell("sp500", "LEFTLONGAGO", "Left Co", None, D(2017, 1, 1), False, True),
    ])
    lines = V.stage_validate(tmp_path, WINDOW, None, [])
    text = "\n".join(lines)
    assert "1 are still active today" in text
    assert "1 have ALREADY left the index" in text


def test_self_test_passes():
    assert V.self_test()
