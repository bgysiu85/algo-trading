#!/usr/bin/env python3
"""The TSMOM holdout refuses the things it says it refuses.

Gate G4 of `docs/research/REGISTERED_tsmom.md`: the holdout is cut and enforced
in code BEFORE the first run, "with a test that the enforcement cannot be
bypassed by a flag". Every assertion below is written so that breaking the
enforcement breaks a test -- checked by mutation, not by reading.
"""
from __future__ import annotations

import json

import pytest

import common.tsmom_holdout as H

MONTHS = [f"{y}-{m:02d}" for y in range(2011, 2026) for m in range(1, 13)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    """Never touch the real ledger. It is a one-way door."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tsmom_holdout_spent.json")


def test_the_lock_date_is_the_registered_one():
    assert H.LOCK_FROM == "2022-01-01", (
        "the lock date is registered in REGISTERED_tsmom section 6, before any "
        "data was bought. Changing it is a new registration, not an edit.")


def test_the_training_side_excludes_2022_onward():
    keep, held, label = H.split_months(MONTHS)
    assert all(m < "2022" for m in keep)
    assert held == len([m for m in MONTHS if m >= "2022"])
    assert "training" in label


def test_2022_is_locked_because_it_is_the_best_year():
    """The whole point of the cut. If 2022 leaks in, criterion 7 is toothless."""
    assert H.is_locked("2022-01-01") and H.is_locked("2022-11-30")
    assert not H.is_locked("2021-12-31")


def test_a_bare_year_month_lands_on_the_right_side_of_the_boundary():
    """The boundary month is where naive string comparison gets it wrong.

    "2022-01" >= "2022-01-01" is False -- the shorter string sorts first -- so
    an unpadded compare put the FIRST MONTH OF THE HOLDOUT in the training set,
    labelled "training". A monthly runner passes exactly this form.
    """
    assert H.is_locked("2022-01"), "the first locked month read as training"
    assert not H.is_locked("2021-12")
    assert H.is_locked("2022-12") and H.is_locked("2025-06")
    # and the padded and unpadded forms must agree with each other
    for m in ("2021-11", "2021-12", "2022-01", "2022-02"):
        assert H.is_locked(m) == H.is_locked(m + "-01"), m


def test_the_locked_side_cannot_be_reached_without_spending():
    keep, _, _ = H.split_months(MONTHS)
    assert not any(H.is_locked(m) for m in keep), (
        "the default path returned locked months -- the holdout is readable "
        "casually, which means it is not a holdout")


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_months(MONTHS, spend=True)
    assert "candidate name" in str(e.value)


def test_a_second_candidate_is_refused():
    keep, _, label = H.split_months(MONTHS, spend=True, candidate="ensemble_k3_6_9_12")
    assert all(m >= "2022" for m in keep) and "LOCKED" in label
    with pytest.raises(SystemExit) as e:
        H.split_months(MONTHS, spend=True, candidate="k12_alone")
    msg = str(e.value)
    assert "already spent" in msg and "ensemble_k3_6_9_12" in msg


def test_the_same_candidate_may_re_read_what_it_already_spent():
    """Re-running one candidate is not a second spend, and must not be refused.

    A rule that fails on a re-run gets worked around, and the workaround is
    deleting the ledger -- which is exactly the thing the ledger exists to make
    visible.
    """
    H.split_months(MONTHS, spend=True, candidate="ensemble_k3_6_9_12")

    # Backdate the record and leave a sentinel. Comparing the two timestamps
    # directly CANNOT FAIL -- both spends land in the same second, so a
    # rewritten ledger is byte-identical and the assertion passes for the wrong
    # reason. Mutation-testing caught exactly that: "rewrite the ledger on every
    # re-read" survived the first version of this test. A control whose output
    # is indistinguishable from the failure it detects is not a control
    # (PROGRAM_INDEX section 4).
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    keep, _, _ = H.split_months(MONTHS, spend=True, candidate="ensemble_k3_6_9_12")
    assert keep

    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z", (
        "a re-read rewrote the ledger -- the record of WHEN the holdout was "
        "first spent is the part that matters, and it has been overwritten "
        "with today")
    assert again.get("sentinel"), "the ledger was replaced wholesale on a re-read"


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    """Not afterwards, by a caller who might not.

    common/holdout.py's docstring records the precedent: a promised counter
    that nothing incremented, removed rather than shipped as decoration.
    """
    assert not H.LEDGER_PATH.exists()
    H.split_months(MONTHS, spend=True, candidate="ensemble_k3_6_9_12")
    assert H.LEDGER_PATH.exists(), (
        "the locked months were returned and no ledger was written -- the "
        "record lags the read, so there is no record")


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_both_sides(kw):
    """G4's words: the enforcement cannot be bypassed by a flag."""
    with pytest.raises(SystemExit) as e:
        H.split_months(MONTHS, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_months(MONTHS, spend=True, candidate="x", **kw)


def test_the_equity_holdout_is_refused_by_name():
    """The quiet failure this exists for.

    holdout.json is a cut over screened equity symbol-days. Handed to
    holdout.split_sessions, a futures date list matches nothing, so it returns
    EVERYTHING with the label "all (no committed cut)" -- the locked years read,
    and the label reading like a reassurance.
    """
    for name in ("holdout.json", "var/state/holdout.json",
                 "holdout_pairs_2026H2.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "EQUITY" in str(e.value)
    H.load_for("tsmom_months.json")          # anything else passes through


def test_describe_splits_the_halves_over_the_training_portion_only():
    """Locking the holdout must not move the both-halves boundary.

    If the median were taken over the whole sample, extending the archive or
    changing the lock date would move criterion 2's split point -- a swept
    split by accident.
    """
    d = H.describe(MONTHS)
    assert d["both_halves_split"] < "2022"
    assert d["locked_first"] == "2022-01"
    assert d["train_last"] == "2021-12"
    # and it is the median of the training portion, not of everything
    train = [m for m in MONTHS if m < "2022"]
    assert d["both_halves_split"] == train[len(train) // 2]


def test_describe_survives_an_all_locked_and_an_all_training_list():
    """An empty half is not a sign flip (PROGRAM_INDEX section 4).

    describe() must report None rather than raise, so a coverage table can
    print the emptiness instead of the run dying and the emptiness going
    unnoticed.
    """
    assert H.describe(["2023-01", "2024-05"])["train_first"] is None
    assert H.describe(["2015-01", "2016-05"])["locked_first"] is None
    assert H.describe([])["n_total"] == 0
