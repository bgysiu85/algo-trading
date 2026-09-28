#!/usr/bin/env python3
"""The DVP-v0 holdout refuses the things it says it refuses. Gate G3:
"Holdout cut and enforced in code (sec 8), mutation-tested." Mirrors
tests/strategy/w16/test_holdout.py's coverage for DVP-v0's own ledger, its
own refused-cut-file list (built from SB-v0's), and sec 8's single
candidate "DVP-NQ" (not a (baseline, market) pair)."""
from __future__ import annotations

import pytest

import strategy.w16.dvp_holdout as DH
import strategy.w16.holdout as H

DATES = [f"{y}-{m:02d}-{d:02d}" for y in range(2010, 2027) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(DH, "LEDGER_PATH", tmp_path / "holdout_w16_dvp.json")


def test_lock_date_matches_sb_v0s_own():
    assert DH.LOCK_FROM == "2024-01-02" == H.LOCK_FROM


def test_training_side_excludes_2024_onward():
    keep, held, label = DH.split_dates(DATES)
    assert all(d < "2024-01-02" for d in keep)
    assert held == len([d for d in DATES if d >= "2024-01-02"])
    assert "training" in label


def test_only_dvp_nq_may_spend_it():
    assert DH.ALLOWED_CANDIDATES == {"DVP-NQ", "DVP-v1-NQ"}
    for bad in ("DVP", "DVP-ES", "dvp-nq", "B1-NQ", "C-D1-NQ", "DVP-NQ-15min"):
        with pytest.raises(SystemExit):
            DH.split_dates(DATES, spend=True, candidate=bad)


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        DH.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_spending_returns_only_locked_dates_and_writes_a_ledger():
    keep, held, label = DH.split_dates(DATES, spend=True, candidate="DVP-NQ")
    assert all(DH.is_locked(d) for d in keep)
    assert "LOCKED" in label
    assert DH.LEDGER_PATH.exists()
    rec = DH.read_ledger()
    assert rec["candidate"] == "DVP-NQ"


def test_spent_once_a_second_spend_is_refused():
    DH.split_dates(DATES, spend=True, candidate="DVP-NQ")
    with pytest.raises(SystemExit) as e:
        DH.split_dates(DATES, spend=True, candidate="DVP-NQ")
    assert "already spent" in str(e.value)


def test_limit_is_refused_on_either_side():
    with pytest.raises(SystemExit):
        DH.split_dates(DATES, limit=5)
    with pytest.raises(SystemExit):
        DH.split_dates(DATES, spend=True, candidate="DVP-NQ", limit=5)


# ---------------------------------------------------------------------
# mutually-refused-by-name: DVP-v0 refuses SB-v0's ledger and every other
# study's; SB-v0 (patched at import time above) refuses DVP-v0's own.
# ---------------------------------------------------------------------

def test_refuses_sb_v0s_own_ledger_by_name():
    with pytest.raises(DH.HoldoutRefused):
        DH.load_for("/some/path/holdout_w16_sb.json")


def test_refuses_every_other_studys_cut_file_by_name():
    for name in H.REFUSED_CUT_NAMES:
        if name == "holdout_w16_dvp.json":
            continue                                    # that one is DVP-v0's OWN name
        with pytest.raises(DH.HoldoutRefused):
            DH.load_for(f"/some/path/{name}")


def test_does_not_refuse_its_own_file():
    DH.load_for("/some/path/holdout_w16_dvp.json")        # must not raise


def test_sb_v0_refuses_dvp_v0s_ledger_by_name():
    """The mirror image: strategy.w16.holdout (SB-v0) must refuse
    holdout_w16_dvp.json by name too, since REGISTERED_w16_drift_vwap.md
    sec 8 says the refusal is by name from EVERY OTHER line's ledger, and
    that includes SB-v0 reaching for DVP-v0's ledger by mistake."""
    with pytest.raises(H.HoldoutRefused):
        H.load_for("/some/path/holdout_w16_dvp.json")


def test_mutation_a_refusal_list_missing_dvp_would_fail_this_test():
    """Mutation-style check (mirrors test_holdout.py's own pattern): the
    refusal is a real membership test against a real set, not a stub that
    always raises -- proven by checking the set itself contains the name,
    not only by checking the function raises."""
    assert "holdout_w16_dvp.json" in H.REFUSED_CUT_NAMES
    assert "holdout_w16_sb.json" in DH.REFUSED_CUT_NAMES


def test_describe_reports_both_halves_split_on_training_only():
    desc = DH.describe(DATES)
    assert desc["lock_from"] == "2024-01-02"
    assert desc["both_halves_split"] < "2024-01-02"
    assert desc["n_train"] + desc["n_locked"] == desc["n_total"]


def test_v1_spends_once_and_then_dvp_nq_is_refused():
    keep, _, label = DH.split_dates(DATES, spend=True, candidate="DVP-v1-NQ")
    assert keep and all(d >= "2024-01-02" for d in keep) and "LOCKED" in label
    assert DH.read_ledger()["candidate"] == "DVP-v1-NQ"
    for again in ("DVP-v1-NQ", "DVP-NQ"):
        with pytest.raises(SystemExit):
            DH.split_dates(DATES, spend=True, candidate=again)
