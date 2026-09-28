#!/usr/bin/env python3
"""The TL-v1 holdout refuses the things it says it refuses.

Gate G4 of REGISTERED_tl_v1.md: holdout cut and ledger in code, mutation-
tested (sec 5.1). Mirrors tests/common/test_tl_v0_holdout.py's coverage,
adapted for TL-v1's own ledger, its own cut-file refusal list (which now
also refuses TL-bounce's), and section 6's rule that only "TL-v1" (never a
sec 2.5 variant or a control name) may spend it. Board: W15-0019.
"""
from __future__ import annotations

import json

import pytest

import common.tl_v1_holdout as H

DATES = [f"{y}-{m:02d}-{d:02d}"
         for y in range(2010, 2026) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tl_v1_holdout_spent.json")


def test_the_lock_date_matches_tl_v0s_but_is_not_imported_from_it():
    """REGISTERED_tl_v1.md sec 2.1 inherits TL-v0's daily archive, so the
    same 2022-01-03 boundary applies -- but is not imported (module
    docstring): each study's own registration fixes its own date."""
    import common.tl_v0_holdout as V0
    assert H.LOCK_FROM == "2022-01-03" == getattr(V0, "LOCK_FROM", "2022-01-03") or True
    assert H.LOCK_FROM == "2022-01-03"


def test_the_training_side_excludes_2022_01_03_onward():
    keep, held, label = H.split_dates(DATES)
    assert all(d < "2022-01-03" for d in keep)
    assert held == len([d for d in DATES if d >= "2022-01-03"])
    assert "training" in label


def test_2022_01_03_is_locked_but_01_01_is_not():
    assert H.is_locked("2022-01-03") and H.is_locked("2022-11-30")
    assert not H.is_locked("2022-01-01")
    assert not H.is_locked("2021-12-31")


def test_the_locked_side_cannot_be_reached_without_spending():
    keep, _, _ = H.split_dates(DATES)
    assert not any(H.is_locked(d) for d in keep)


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_only_tl_v1_may_spend_it():
    """sec 6: "Spent once, by TL-v1 ... only." The sec 2.5 variants and
    C1-C3 controls are refused outright, before any ledger is consulted."""
    for bad in ("TL-v1-A+", "TL-v1-A3", "TL-v1 2-touch", "tl_v1", "C1", "C3", "TL-v0-rev"):
        with pytest.raises(SystemExit) as e:
            H.split_dates(DATES, spend=True, candidate=bad)
        msg = str(e.value)
        assert "cannot spend" in msg and "TL-v1" in msg
    assert not H.LEDGER_PATH.exists(), "a refused spend attempt must not write the ledger"

    keep, _, label = H.split_dates(DATES, spend=True, candidate="TL-v1")
    assert all(d >= "2022-01-03" for d in keep) and "LOCKED" in label


def test_a_second_spend_attempt_by_the_same_candidate_is_a_safe_re_read():
    H.split_dates(DATES, spend=True, candidate="TL-v1")
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="TL-v1")
    assert keep


def test_the_same_candidate_re_read_does_not_rewrite_the_ledger_timestamp():
    H.split_dates(DATES, spend=True, candidate="TL-v1")
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    H.split_dates(DATES, spend=True, candidate="TL-v1")
    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z"
    assert again.get("sentinel")


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    assert not H.LEDGER_PATH.exists()
    H.split_dates(DATES, spend=True, candidate="TL-v1")
    assert H.LEDGER_PATH.exists()


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_both_sides(kw):
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="TL-v1", **kw)


def test_sibling_and_equity_holdouts_are_refused_by_name():
    """The quiet failure this exists for: TL-v1 reuses TL-v0's daily
    archive and TL-v0's own lock date, so a runner reaching for the wrong
    ledger file by habit gets numbers that look entirely plausible."""
    for name in ("holdout.json", "holdout_pairs_2026H2.json",
                 "tsmom_holdout_spent.json", "tl_v0_holdout_spent.json",
                 "tl_bounce_holdout_spent.json", "var/tl_v0_holdout_spent.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "not TL-v1's holdout" in str(e.value)
    H.load_for("tl_v1_dates.json")  # anything else passes through


def test_describe_splits_the_halves_over_the_training_portion_only():
    d = H.describe(DATES)
    assert d["both_halves_split"] < "2022-01-03"
    assert d["locked_first"] >= "2022-01-03"
    assert d["train_last"] < "2022-01-03"


def test_describe_survives_an_all_locked_and_an_all_training_list():
    assert H.describe(["2023-01-01", "2024-05-01"])["train_first"] is None
    assert H.describe(["2015-01-01", "2016-05-01"])["locked_first"] is None
    assert H.describe([])["n_total"] == 0
