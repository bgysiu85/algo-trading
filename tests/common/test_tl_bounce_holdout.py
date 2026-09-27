#!/usr/bin/env python3
"""common/tl_bounce_holdout.py: the TL-bounce holdout ledger.
REGISTERED_tl_bounce.md sec 6. Mirrors tests/common/test_tl_v0_holdout.py's
own coverage for the sibling study."""
from __future__ import annotations

import importlib

import pytest

MODULE = "common.tl_bounce_holdout"


@pytest.fixture()
def mod(tmp_path, monkeypatch):
    m = importlib.import_module(MODULE)
    m = importlib.reload(m)
    monkeypatch.setattr(m, "LEDGER_PATH", tmp_path / "tl_bounce_holdout_spent.json")
    yield m
    importlib.reload(m)   # restore the real ROOT-relative LEDGER_PATH for other tests


def test_lock_boundary_is_2022_01_03(mod):
    assert mod.LOCK_FROM == "2022-01-03"
    assert not mod.is_locked("2022-01-02")
    assert mod.is_locked("2022-01-03")
    assert mod.is_locked("2025-09-22")


def test_default_split_is_training_only(mod):
    dates = ["2019-01-01", "2021-12-31", "2022-01-03", "2024-06-01"]
    keep, n_locked, label = mod.split_dates(dates)
    assert keep == ["2019-01-01", "2021-12-31"]
    assert n_locked == 2
    assert "training" in label


def test_limit_is_refused(mod):
    with pytest.raises(mod.HoldoutRefused):
        mod.split_dates(["2019-01-01"], limit=10)


def test_spend_requires_the_named_candidate(mod):
    dates = ["2022-01-03", "2023-01-01"]
    with pytest.raises(mod.HoldoutRefused):
        mod.split_dates(dates, spend=True, candidate="TL-bounce-variant")
    with pytest.raises(mod.HoldoutRefused):
        mod.split_dates(dates, spend=True)   # no candidate at all


def test_spend_writes_ledger_once(mod):
    dates = ["2022-01-03", "2023-01-01", "2019-01-01"]
    keep, n_train, label = mod.split_dates(dates, spend=True, candidate="TL-bounce")
    assert set(keep) == {"2022-01-03", "2023-01-01"}
    assert n_train == 1
    assert "LOCKED" in label
    spent_at = mod.read_ledger()["spent_at"]

    # a repeat spend by the SAME (only-allowed) candidate is idempotent --
    # it does not re-write the ledger or refuse (mirrors tl_v0_holdout.py)
    keep2, _, _ = mod.split_dates(dates, spend=True, candidate="TL-bounce")
    assert set(keep2) == set(keep)
    assert mod.read_ledger()["spent_at"] == spent_at

    # only a genuinely different recorded candidate would be refused -- not
    # reachable while ALLOWED_CANDIDATE is a single fixed name, so this
    # exercises the backstop directly rather than through split_dates
    mod._write_ledger("someone-else", 0)
    with pytest.raises(mod.HoldoutRefused):
        mod.split_dates(dates, spend=True, candidate="TL-bounce")


def test_refuses_sibling_and_equity_cut_files(mod):
    for name in ("holdout.json", "tsmom_holdout_spent.json", "tl_v0_holdout_spent.json"):
        with pytest.raises(mod.HoldoutRefused):
            mod.load_for(name)
