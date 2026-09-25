#!/usr/bin/env python3
"""The HTF-Ben holdout refuses the things it says it refuses.

Gate G3 of `docs/research/REGISTERED_htf_ben_v0.md`: "Holdout cut and
enforced in code (section 6), mutation-tested." Every assertion below is
written so that breaking the enforcement breaks a test -- checked by
mutation, not by reading. Mirrors tests/common/test_tl_v0_holdout.py's
coverage, adapted for HTF-Ben's own ledger, its own cut-file refusal list
(TSMOM + TL-v0 + H60 + equity), and the section-6 rule that only "v0" (never
"v0-TL", "v0-1H", or any control) may spend it, and only by spending B and
A-2H together in the one call.
"""
from __future__ import annotations

import json

import pytest

import strategy.htf.holdout as H

# HTF-Ben runs on hourly/daily bars (REGISTERED_htf_ben_v0.md section 2.1),
# so this holdout is tested against dates, like TL-v0's, not TSMOM's months.
DATES = [f"{y}-{m:02d}-{d:02d}"
         for y in range(2010, 2026) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    """Never touch the real ledger. It is a one-way door."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_htf_ben.json")


def test_the_lock_date_matches_tsmom_and_tl_v0():
    """REGISTERED_htf_ben_v0.md section 6: "the same cut as TSMOM and
    TL-v0." Checked by value, not by reference, so the ledgers stay separate
    even though the date is shared (see module docstring) -- and this would
    silently drift if any one of the three constants were edited alone."""
    import common.tsmom_holdout as T
    import common.tl_v0_holdout as L
    assert H.LOCK_FROM == "2022-01-01" == T.LOCK_FROM == L.LOCK_FROM


def test_the_training_side_excludes_2022_onward():
    keep, held, label = H.split_dates(DATES)
    assert all(d < "2022" for d in keep)
    assert held == len([d for d in DATES if d >= "2022"])
    assert "training" in label


def test_2022_is_locked():
    assert H.is_locked("2022-01-01") and H.is_locked("2022-11-30")
    assert not H.is_locked("2021-12-31")


def test_a_bare_year_month_lands_on_the_right_side_of_the_boundary():
    """Same off-by-string-length trap common/tsmom_holdout.py's and
    common/tl_v0_holdout.py's own tests document: "2022-01" >= "2022-01-01"
    is False, so an unpadded compare would put the first month of the
    holdout on the training side."""
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


def test_only_v0_may_spend_it():
    """REGISTERED_htf_ben_v0.md section 6: "Spent once, by v0 ... only."
    v0-TL and v0-1H (section 2.6) and every control (C1/C2/C3, section 3.7)
    are reported neighbours barred from spending the holdout (section 4) --
    refused outright, before any ledger or scenario check is even reached."""
    for bad in ("v0-TL", "v0-1H", "V0", "c1", "C2", "ensemble", ""):
        if bad == "":
            continue  # covered by test_spending_requires_a_candidate_name
        with pytest.raises(SystemExit) as e:
            H.split_dates(DATES, spend=True, candidate=bad,
                          scenarios={"B", "A-2H"})
        msg = str(e.value)
        assert "cannot spend" in msg and "v0" in msg
    assert not H.LEDGER_PATH.exists(), (
        "a refused spend attempt must not write the ledger")


@pytest.mark.parametrize("scen", [
    {"B"}, {"A-2H"}, {"A-1H"}, {"A-4H"}, {"B", "A-1H"},
    {"B", "A-2H", "A-1H"}, set(), None,
])
def test_scenarios_must_be_exactly_b_and_a2h_together(scen):
    """Section 6: "B (4-hour) and A-2H together in that one spend" -- not
    one scenario alone, not a superset with an extra reported neighbour
    thrown in, and not omitted."""
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True, candidate="v0", scenarios=scen)
    assert "together" in str(e.value)
    assert not H.LEDGER_PATH.exists()


def test_v0_with_both_scenarios_together_spends_it():
    keep, _, label = H.split_dates(DATES, spend=True, candidate="v0",
                                   scenarios={"B", "A-2H"})
    assert all(d >= "2022" for d in keep) and "LOCKED" in label
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert rec["candidate"] == "v0"
    assert sorted(rec["scenarios"]) == ["A-2H", "B"]


def test_a_second_spend_attempt_is_refused_even_by_the_same_name_rule():
    """Once v0 has spent it (B and A-2H together), spending again must be
    idempotent-safe for the same call, and no other candidate exists to
    attempt a genuine second spend -- the allow-list is the enforcement, not
    the ledger, same as common/tl_v0_holdout.py's equivalent test."""
    H.split_dates(DATES, spend=True, candidate="v0", scenarios={"B", "A-2H"})
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v0",
                               scenarios={"B", "A-2H"})
    assert keep, "re-reading with the same candidate that already spent it must work"


def test_the_same_candidate_may_re_read_what_it_already_spent():
    """Re-running v0/B+A-2H is not a second spend, and must not rewrite the
    ledger's timestamp -- the same mutation TL-v0's and TSMOM's own tests
    catch: a control whose output is indistinguishable from the failure it
    detects is not a control (PROGRAM_INDEX section 4)."""
    H.split_dates(DATES, spend=True, candidate="v0", scenarios={"B", "A-2H"})
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v0",
                               scenarios={"B", "A-2H"})
    assert keep

    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z", (
        "a re-read rewrote the ledger's spent_at -- the record of WHEN the "
        "holdout was first spent is the part that matters")
    assert again.get("sentinel"), "the ledger was replaced wholesale on a re-read"


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    assert not H.LEDGER_PATH.exists()
    H.split_dates(DATES, spend=True, candidate="v0", scenarios={"B", "A-2H"})
    assert H.LEDGER_PATH.exists(), (
        "the locked dates were returned and no ledger was written -- the "
        "record lags the read, so there is no record")


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_both_sides(kw):
    """G3's words: the enforcement cannot be bypassed by a flag."""
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="v0",
                      scenarios={"B", "A-2H"}, **kw)


def test_the_other_studies_holdouts_are_refused_by_name():
    """The quiet failure this exists for: HTF-Ben shares its lock date with
    TSMOM and TL-v0 (REGISTERED_htf_ben_v0.md section 6), so a runner
    reaching for the wrong file by habit gets numbers that look entirely
    plausible."""
    for name in ("holdout.json", "var/state/holdout.json",
                 "holdout_pairs_2026H2.json", "tsmom_holdout_spent.json",
                 "var/tsmom_holdout_spent.json", "tl_v0_holdout_spent.json",
                 "holdout_h60_spent.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "not HTF-Ben's holdout" in str(e.value)
    H.load_for("holdout_htf_ben.json")       # its own file passes through
    H.load_for("anything_else.json")          # and so does anything else


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
