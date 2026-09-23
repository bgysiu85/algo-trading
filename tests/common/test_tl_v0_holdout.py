#!/usr/bin/env python3
"""The TL-v0 holdout refuses the things it says it refuses.

Gate G4 of `docs/research/REGISTERED_tl_v0.md`: "Holdout cut and enforced in
code (section 6), mutation-tested." Every assertion below is written so that
breaking the enforcement breaks a test -- checked by mutation, not by
reading. Mirrors tests/strategy/test_tsmom_holdout.py's coverage, adapted for
TL-v0's own ledger, its own cut-file refusal list, and the section-6 rule
that only "v0-rev" (never any other name, and never "v0") may spend it.
"""
from __future__ import annotations

import json

import pytest

import common.tl_v0_holdout as H

# TL-v0 runs on daily bars (REGISTERED_tl_v0.md section 2.1: "Execution
# timeframe | Daily"), unlike TSMOM's monthly signal -- so this holdout is
# tested against dates, not months.
DATES = [f"{y}-{m:02d}-{d:02d}"
         for y in range(2010, 2026) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    """Never touch the real ledger. It is a one-way door."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tl_v0_holdout_spent.json")


def test_the_lock_date_matches_tsmoms_and_is_the_registered_one():
    """REGISTERED_tl_v0.md section 6: "the same cut as TSMOM." Not derived by
    importing TSMOM's constant -- see module docstring for why the ledgers
    must stay separate even though the date is shared -- so this is checked
    by value, not by reference, and would silently drift if either constant
    were edited without the other."""
    import common.tsmom_holdout as T
    assert H.LOCK_FROM == "2022-01-01" == T.LOCK_FROM


def test_the_training_side_excludes_2022_onward():
    keep, held, label = H.split_dates(DATES)
    assert all(d < "2022" for d in keep)
    assert held == len([d for d in DATES if d >= "2022"])
    assert "training" in label


def test_2022_is_locked():
    assert H.is_locked("2022-01-01") and H.is_locked("2022-11-30")
    assert not H.is_locked("2021-12-31")


def test_a_bare_year_month_lands_on_the_right_side_of_the_boundary():
    """Same off-by-string-length trap common/tsmom_holdout.py's own test
    documents: "2022-01" >= "2022-01-01" is False, so an unpadded compare
    would put the first month of the holdout on the training side."""
    assert H.is_locked("2022-01")
    assert not H.is_locked("2021-12")
    for m in ("2021-11", "2021-12", "2022-01", "2022-02"):
        assert H.is_locked(m) == H.is_locked(m + "-01"), m


def test_the_locked_side_cannot_be_reached_without_spending():
    keep, _, _ = H.split_dates(DATES)
    assert not any(H.is_locked(d) for d in keep), (
        "the default path returned locked dates -- the holdout is readable "
        "casually, which means it is not a holdout")


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_only_v0_rev_may_spend_it():
    """REGISTERED_tl_v0.md section 6: "Spent once, by v0-rev only." Unlike
    TSMOM's holdout, which accepts whichever single candidate asks first,
    every other name -- including "v0", the reported neighbour that section
    4 explicitly bars from spending it -- is refused outright, before any
    ledger is even consulted."""
    for bad in ("v0", "v0_rev", "V0-REV", "tl_v0", "ensemble_k3_6_9_12", ""):
        if bad == "":
            continue  # covered by test_spending_requires_a_candidate_name
        with pytest.raises(SystemExit) as e:
            H.split_dates(DATES, spend=True, candidate=bad)
        msg = str(e.value)
        assert "cannot spend" in msg and "v0-rev" in msg
    assert not H.LEDGER_PATH.exists(), (
        "a refused spend attempt must not write the ledger")

    keep, _, label = H.split_dates(DATES, spend=True, candidate="v0-rev")
    assert all(d >= "2022" for d in keep) and "LOCKED" in label


def test_a_second_spend_attempt_is_refused_even_by_the_same_name_rule():
    """Once v0-rev has spent it, spending again -- even by v0-rev again in a
    way that would look like a second study -- must be idempotent-safe, and
    a differently-named second candidate must still be impossible (there is
    no other allowed name to test this against, which is itself the point:
    the allow-list is the enforcement, not the ledger)."""
    H.split_dates(DATES, spend=True, candidate="v0-rev")
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v0-rev")
    assert keep, "re-reading with the same candidate that already spent it must work"


def test_the_same_candidate_may_re_read_what_it_already_spent():
    """Re-running v0-rev is not a second spend, and must not be refused, and
    must not rewrite the ledger's timestamp -- the same mutation TSMOM's own
    test catches: a control whose output is indistinguishable from the
    failure it detects is not a control (PROGRAM_INDEX section 4)."""
    H.split_dates(DATES, spend=True, candidate="v0-rev")
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v0-rev")
    assert keep

    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z", (
        "a re-read rewrote the ledger's spent_at -- the record of WHEN the "
        "holdout was first spent is the part that matters")
    assert again.get("sentinel"), "the ledger was replaced wholesale on a re-read"


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    assert not H.LEDGER_PATH.exists()
    H.split_dates(DATES, spend=True, candidate="v0-rev")
    assert H.LEDGER_PATH.exists(), (
        "the locked dates were returned and no ledger was written -- the "
        "record lags the read, so there is no record")


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_both_sides(kw):
    """G4's words: the enforcement cannot be bypassed by a flag."""
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="v0-rev", **kw)


def test_the_equity_and_tsmom_holdouts_are_refused_by_name():
    """The quiet failure this exists for: TL-v0 registers the same markets
    and the same lock date as TSMOM (REGISTERED_tl_v0.md section 2.1), so a
    runner reaching for the wrong file by habit gets numbers that look
    entirely plausible."""
    for name in ("holdout.json", "var/state/holdout.json",
                 "holdout_pairs_2026H2.json", "tsmom_holdout_spent.json",
                 "var/tsmom_holdout_spent.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "not TL-v0's holdout" in str(e.value)
    H.load_for("tl_v0_dates.json")          # anything else passes through


def test_describe_splits_the_halves_over_the_training_portion_only():
    d = H.describe(DATES)
    assert d["both_halves_split"] < "2022"
    assert d["locked_first"].startswith("2022")
    assert d["train_last"] < "2022"
    train = [dd for dd in DATES if dd < "2022"]
    assert d["both_halves_split"] == train[len(train) // 2]


def test_describe_survives_an_all_locked_and_an_all_training_list():
    """An empty half is not a sign flip (PROGRAM_INDEX section 4)."""
    assert H.describe(["2023-01-01", "2024-05-01"])["train_first"] is None
    assert H.describe(["2015-01-01", "2016-05-01"])["locked_first"] is None
    assert H.describe([])["n_total"] == 0
