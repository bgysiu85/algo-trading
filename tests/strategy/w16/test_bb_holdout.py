"""Tests for strategy.w16.bb_holdout: the G3 gate -- own ledger, six-way
candidate set, mutual refusal by name with every other W16 study's
ledger, --limit refused unconditionally, spent once. Mirrors
test_dvp_holdout.py's own mutation-test pattern. Board W16-0008 subitem 3.
"""
from __future__ import annotations

import json

import pytest

from strategy.w16 import bb_holdout as H
from strategy.w16 import dvp_holdout as DVP_HOLDOUT
from strategy.w16 import holdout as SB_HOLDOUT


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    """Every test gets its own, never-yet-written ledger path -- a test
    that spends the holdout must not leak into a sibling test."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_w16_bb.json")
    yield


def test_lock_boundary():
    assert H.is_locked("2024-01-02")
    assert H.is_locked("2024-06-15")
    assert not H.is_locked("2023-12-29")
    assert not H.is_locked("2024-01-01")


def test_split_dates_training_default():
    dates = ["2023-12-29", "2024-01-01", "2024-01-02", "2024-06-01"]
    keep, n_locked, label = H.split_dates(dates)
    assert keep == ["2023-12-29", "2024-01-01"]
    assert n_locked == 2
    assert "training" in label


def test_split_dates_limit_always_refused():
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(["2023-01-01"], limit=10)
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(["2024-06-01"], spend=True, candidate="ABD-NQ", limit=1)


def test_spend_requires_named_allowed_candidate():
    dates = ["2024-01-02", "2024-06-01"]
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(dates, spend=True)                       # no candidate
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(dates, spend=True, candidate="ABD-ES")   # reported only, sec 9 scores none of ES


def test_spend_only_one_of_six_scored_candidates():
    assert H.ALLOWED_CANDIDATES == {"ABD-NQ", "SSS-NQ", "TMB-NQ", "CRT-NQ", "NRS-ES", "NRS-NQ"}
    dates = ["2024-01-02", "2024-06-01"]
    keep, n_train, label = H.split_dates(dates, spend=True, candidate="NRS-NQ")
    assert keep == dates
    assert "LOCKED" in label
    rec = json.loads(H.LEDGER_PATH.read_text())
    assert rec["candidate"] == "NRS-NQ"


def test_spend_once_only():
    dates = ["2024-01-02", "2024-06-01"]
    H.split_dates(dates, spend=True, candidate="ABD-NQ")
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(dates, spend=True, candidate="SSS-NQ")   # already spent, a DIFFERENT cell cannot take it
    with pytest.raises(H.HoldoutRefused):
        H.split_dates(dates, spend=True, candidate="ABD-NQ")   # not even the SAME cell, twice


def test_mutual_refusal_by_name():
    """BB-v0 refuses every other study's ledger by name, and (the point
    of this whole design) every other study refuses BB-v0's back, without
    a direct edit to dvp_holdout.py -- it derives its own refused set from
    strategy.w16.holdout's, which bb_holdout.py's own build already
    depends on staying in sync."""
    assert H.LEDGER_PATH.name not in H.REFUSED_CUT_NAMES            # BB-v0 never refuses its OWN ledger
    assert SB_HOLDOUT.LEDGER_PATH.name in H.REFUSED_CUT_NAMES        # BB-v0 refuses SB-v0's
    assert DVP_HOLDOUT.LEDGER_PATH.name in H.REFUSED_CUT_NAMES       # BB-v0 refuses DVP's

    with pytest.raises(H.HoldoutRefused):
        H.load_for(SB_HOLDOUT.LEDGER_PATH)
    with pytest.raises(H.HoldoutRefused):
        H.load_for(DVP_HOLDOUT.LEDGER_PATH)
    # and the load_for on BB-v0's OWN path must NOT raise
    H.load_for(H.LEDGER_PATH)

    # the cascade: BB-v0's own ledger name must appear in SB-v0's refused
    # set (added there when this module was built), which is what
    # DVP-v0's own set derives from without a direct edit to dvp_holdout.py
    assert H.LEDGER_PATH.name in SB_HOLDOUT.REFUSED_CUT_NAMES
    assert H.LEDGER_PATH.name in DVP_HOLDOUT.REFUSED_CUT_NAMES
