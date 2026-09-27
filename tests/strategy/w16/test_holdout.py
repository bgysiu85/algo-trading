#!/usr/bin/env python3
"""The W16 holdout refuses the things it says it refuses. Gate G3:
"Holdout cut and enforced in code (sec 8), mutation-tested." Mirrors
tests/strategy/htf/test_holdout.py's coverage, adapted for W16's own
ledger, its own refused-cut-file list, and sec 8's "spent once, by ONE
CELL" rule (a (baseline, market) pair, not a fixed candidate name)."""
from __future__ import annotations

import pytest

import strategy.w16.holdout as H

DATES = [f"{y}-{m:02d}-{d:02d}" for y in range(2010, 2027) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_w16_sb.json")


def test_lock_date_matches_registered_sec8():
    assert H.LOCK_FROM == "2024-01-02"


def test_training_side_excludes_2024_onward():
    keep, held, label = H.split_dates(DATES)
    assert all(d < "2024-01-02" for d in keep)
    assert held == len([d for d in DATES if d >= "2024-01-02"])
    assert "training" in label


def test_2024_01_02_is_locked_but_01_01_is_not():
    assert H.is_locked("2024-01-02")
    assert not H.is_locked("2024-01-01")


def test_bare_year_month_lands_on_the_right_side():
    """LOCK_FROM is 2024-01-02, not the 1st -- so a bare "2024-01" (padded
    to "2024-01-01") is one day EARLIER than the lock and must NOT be
    locked; "2024-02" (padded to "2024-02-01") is unambiguously after it."""
    assert not H.is_locked("2024-01")
    assert H.is_locked("2024-02")
    assert not H.is_locked("2023-12")


def test_locked_side_unreachable_without_spending():
    keep, _, _ = H.split_dates(DATES)
    assert not any(H.is_locked(d) for d in keep)


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_only_the_six_cells_may_spend_it():
    assert H.ALLOWED_CANDIDATES == {"B1-ES", "B1-NQ", "B2-ES", "B2-NQ", "B3-ES", "B3-NQ"}
    for bad in ("B1", "ES", "b1-es", "C-B1-ES", "B4-ES", ""):
        if bad == "":
            continue
        with pytest.raises(SystemExit):
            H.split_dates(DATES, spend=True, candidate=bad)


def test_spending_returns_only_locked_dates():
    keep, held, label = H.split_dates(DATES, spend=True, candidate="B2-ES")
    assert all(H.is_locked(d) for d in keep)
    assert "LOCKED" in label
    assert held == len(DATES) - len(keep)


def test_spending_writes_a_ledger_and_refuses_a_second_spend():
    H.split_dates(DATES, spend=True, candidate="B1-NQ")
    assert H.LEDGER_PATH.exists()
    rec = H.read_ledger()
    assert rec["candidate"] == "B1-NQ"
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True, candidate="B2-ES")   # even a DIFFERENT cell
    assert "already spent" in str(e.value)


def test_limit_is_refused_on_either_side():
    with pytest.raises(SystemExit):
        H.split_dates(DATES, limit=5)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="B1-ES", limit=5)


def test_refuses_every_other_lines_cut_file_by_name():
    for name in H.REFUSED_CUT_NAMES:
        with pytest.raises(H.HoldoutRefused):
            H.load_for(f"/some/path/{name}")


def test_does_not_refuse_its_own_file():
    H.load_for("/some/path/holdout_w16_sb.json")   # must not raise


def test_describe_reports_both_halves_split_on_training_only():
    desc = H.describe(DATES)
    assert desc["lock_from"] == "2024-01-02"
    assert desc["both_halves_split"] < "2024-01-02"
    assert desc["n_train"] + desc["n_locked"] == desc["n_total"]
