"""Gate G3: the OWA-v0 holdout ledger -- training by default, spent once for
the list of passing cells, no narrowing, refused by name both ways.
REGISTERED_w16_open_window.md sec 9. Board W16-0040 sub 4."""
from __future__ import annotations

import json

import pytest

from strategy.w16 import bb_holdout as BB
from strategy.w16 import dvp_holdout as DVP
from strategy.w16 import holdout as SB
from strategy.w16 import owa_holdout as H

DATES = ["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03", "2026-10-27"]


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_w16_owa.json")


def test_registered_dates_and_cells():
    assert H.LOCK_FROM == "2024-01-02" and H.TRAINING_DATA_BEFORE == "2024-01-01"
    assert H.CELLS == ("A-1H", "B-1H", "C-1H", "A-15", "B-15", "C-15")
    assert H.is_locked("2024-01-02") and not H.is_locked("2023-12-29")


def test_training_is_the_default():
    keep, aside, label = H.split_dates(DATES)
    assert keep == DATES[:2] and aside == 3 and "training" in label
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("kwargs", [{}, {"spend": True, "cells": ["A-1H"]}])
def test_limit_is_refused_on_either_side(kwargs):
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(DATES, limit=10, **kwargs)
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("cells", [None, [], "A-1H", ["A-1H", "A-1H"], ["All-1H"],
                                   ["A-1H", "C-2"], ["B-15-long"]])
def test_only_a_list_of_scored_cells_can_spend(cells):
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(DATES, spend=True, cells=cells)
    assert not H.LEDGER_PATH.exists()


def test_spent_once_by_every_cell_named_together():
    keep, aside, label = H.split_dates(DATES, spend=True, cells=["B-1H", "C-15"])
    assert keep == DATES[2:] and "LOCKED" in label
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert rec["cells"] == ["B-1H", "C-15"] and rec["n_locked_days"] == 3
    for cells in (["B-1H"], ["A-1H"], ["B-1H", "C-15"]):
        with pytest.raises(H.HoldoutRefused):
            H.split_dates(DATES, spend=True, cells=cells)


def test_nothing_is_spent_without_locked_dates():
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(DATES[:2], spend=True, cells=["A-1H"])
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("other", [SB, DVP, BB])
def test_refused_by_name_both_ways(other):
    assert other.LEDGER_PATH.name in H.REFUSED_CUT_NAMES
    assert "holdout_w16_owa.json" in other.REFUSED_CUT_NAMES
    with pytest.raises(H.HoldoutRefused):
        H.load_for(f"/some/path/{other.LEDGER_PATH.name}")
    with pytest.raises(other.HoldoutRefused):
        other.load_for("/some/path/holdout_w16_owa.json")


def test_own_name_is_accepted_and_the_cli_cannot_spend(capsys):
    H.load_for("/some/path/holdout_w16_owa.json")
    assert H.main(["--status"]) == 0
    assert "UNSPENT" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        H.main(["--spend", "A-1H"])
    assert not H.LEDGER_PATH.exists()
