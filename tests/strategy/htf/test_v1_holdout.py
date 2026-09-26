#!/usr/bin/env python3
"""The HTF-Ben v1 holdout refuses the things it says it refuses.

Gate G3 of `docs/research/REGISTERED_htf_ben_v1.md`: "Holdout cut and
enforced in code (section 6), mutation-tested." Every assertion below is
written so that breaking the enforcement breaks a test -- checked by
mutation, not by reading. Mirrors tests/strategy/htf/test_holdout.py's own
coverage, adapted for v1's THREE-way split (training/holdout/seen instead
of v0's training/locked), v1's own ledger and cut-file refusal list (v0's
own ledger added to the cross-study set), and the section-6 rule that only
"v1" (never an ablation or a control) may spend it, and only on B alone (not
B and A-2H together like v0).
"""
from __future__ import annotations

import json

import pytest

import strategy.htf.v1_holdout as H

# v1 runs on hourly/daily bars (REGISTERED_htf_ben_v1.md section 2.1), so
# this holdout is tested against dates, like v0's own, not TSMOM's months.
# Spans training, holdout AND seen so every test below can see all three
# buckets in one list.
DATES = [f"{y}-{m:02d}-{d:02d}"
         for y in range(2010, 2027) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    """Never touch the real ledger. It is a one-way door."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_htf_ben_v1.json")


def test_the_training_start_matches_v0s():
    """REGISTERED_htf_ben_v1.md section 6: "Training: 2010-06-06 ->
    2021-12-31 (as v0)." v1 does not re-cut the training side -- only the
    holdout/seen boundaries are new. Checked by value against v0's own
    module, not by reference, since the two studies keep separate ledgers
    even though this one date is shared."""
    import strategy.htf.holdout as H0
    assert H.HOLDOUT_START == "2022-01-03"
    assert H0.LOCK_FROM == "2022-01-01"  # v0's own boundary, unchanged, for contrast


def test_the_three_buckets_are_mutually_exclusive_and_exhaustive():
    for d in DATES:
        buckets = [H.is_training(d), H.is_holdout(d), H.is_seen(d)]
        assert sum(buckets) == 1, (d, buckets)


def test_the_training_side_excludes_holdout_and_seen():
    keep, held, label = H.split_dates(DATES)
    assert all(H.is_training(d) for d in keep)
    assert not any(H.is_holdout(d) or H.is_seen(d) for d in keep)
    assert held == len([d for d in DATES if not H.is_training(d)])
    assert "training" in label


def test_is_locked_covers_holdout_and_seen_alike():
    """The default (non-spend) path relies on is_locked excluding BOTH
    off-limits buckets with the one check -- a caller that forgets the seen
    window exists must still never get it back labelled 'training'."""
    assert H.is_locked("2022-01-03") and H.is_locked("2025-09-23")
    assert H.is_locked("2026-01-01")
    assert not H.is_locked("2022-01-02")


def test_the_boundaries_are_exact():
    assert H.is_training("2022-01-02") and not H.is_training("2022-01-03")
    assert H.is_holdout("2022-01-03") and H.is_holdout("2025-09-22")
    assert not H.is_holdout("2022-01-02") and not H.is_holdout("2025-09-23")
    assert H.is_seen("2025-09-23") and not H.is_seen("2025-09-22")


def test_a_bare_year_month_lands_on_the_right_side_of_each_boundary():
    """Same off-by-string-length trap v0's own holdout.py's tests document:
    "2022-01" >= "2022-01-03" is False, so an unpadded compare could put the
    first month of the holdout on the training side."""
    for m in ("2021-12", "2022-01", "2025-09", "2025-10"):
        assert H.is_training(m) == H.is_training(m + "-01"), m
        assert H.is_holdout(m) == H.is_holdout(m + "-01"), m
        assert H.is_seen(m) == H.is_seen(m + "-01"), m


def test_the_holdout_and_seen_sides_cannot_be_reached_as_training():
    keep, _, _ = H.split_dates(DATES)
    assert not any(H.is_holdout(d) or H.is_seen(d) for d in keep), (
        "the default path returned holdout or seen dates -- the holdout is "
        "readable casually as training, which means it is not a holdout")


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_only_v1_may_spend_it():
    """REGISTERED_htf_ben_v1.md section 6: "Spent once, by v1 ... only."
    The ablations (section 2.4: v1-curl/v1-F1/v1-F2/v1-X) and every control
    (C1/C2/C3, section 3) are reported neighbours barred from spending the
    holdout (section 4) -- refused outright, before any ledger or scenario
    check is even reached."""
    for bad in ("v1-curl", "v1-F1", "v1-F2", "v1-X", "v0", "V1", "c1", "C2",
                "ensemble"):
        with pytest.raises(SystemExit) as e:
            H.split_dates(DATES, spend=True, candidate=bad, scenarios={"B"})
        msg = str(e.value)
        assert "cannot spend" in msg and "v1" in msg
    assert not H.LEDGER_PATH.exists(), (
        "a refused spend attempt must not write the ledger")


@pytest.mark.parametrize("scen", [
    {"A-2H"}, {"A-1H"}, {"A-4H"}, {"B", "A-2H"}, {"B", "A-1H"},
    {"B", "A-2H", "A-1H"}, set(), None,
])
def test_scenarios_must_be_exactly_b_alone(scen):
    """Section 6: "by v1 on B" -- not A-2H alone (reported, never scored,
    section 4), not B and A-2H together like v0, and not omitted."""
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True, candidate="v1", scenarios=scen)
    assert "alone" in str(e.value)
    assert not H.LEDGER_PATH.exists()


def test_v1_with_b_alone_spends_it():
    keep, _, label = H.split_dates(DATES, spend=True, candidate="v1",
                                   scenarios={"B"})
    assert all(H.is_holdout(d) for d in keep) and "HOLDOUT" in label
    assert not any(H.is_seen(d) for d in keep), (
        "spending the holdout must not also hand over the seen window")
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert rec["candidate"] == "v1"
    assert rec["scenarios"] == ["B"]


def test_a_second_spend_attempt_is_refused_even_by_the_same_name_rule():
    """Once v1 has spent it (B alone), spending again must be idempotent-
    safe for the same call, and no other candidate exists to attempt a
    genuine second spend -- the allow-list is the enforcement, not the
    ledger, same as v0's own equivalent test."""
    H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    assert keep, "re-reading with the same candidate that already spent it must work"


def test_the_same_candidate_may_re_read_what_it_already_spent():
    """Re-running v1/B is not a second spend, and must not rewrite the
    ledger's timestamp -- same mutation v0's own test catches: a control
    whose output is indistinguishable from the failure it detects is not a
    control (PROGRAM_INDEX section 4)."""
    H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    assert keep

    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z", (
        "a re-read rewrote the ledger's spent_at -- the record of WHEN the "
        "holdout was first spent is the part that matters")
    assert again.get("sentinel"), "the ledger was replaced wholesale on a re-read"


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    assert not H.LEDGER_PATH.exists()
    H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    assert H.LEDGER_PATH.exists(), (
        "the holdout dates were returned and no ledger was written -- the "
        "record lags the read, so there is no record")


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_every_side(kw):
    """G3's words: the enforcement cannot be bypassed by a flag."""
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"}, **kw)
    with pytest.raises(SystemExit):
        H.seen_dates(DATES, **kw)


def test_the_seen_window_is_never_spendable():
    """Section 6: "Never scored; reported only." There is no spend path
    that returns it -- split_dates's spend branch only ever returns the
    holdout bucket, whatever candidate/scenario combination is tried."""
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v1", scenarios={"B"})
    assert not any(H.is_seen(d) for d in keep)


def test_seen_dates_is_ungated_but_still_only_the_seen_window():
    got = H.seen_dates(DATES)
    assert got, "the DATES fixture must include seen-window dates"
    assert all(H.is_seen(d) for d in got)
    assert not any(H.is_training(d) or H.is_holdout(d) for d in got)
    assert not H.LEDGER_PATH.exists(), "reading the seen window must never write a ledger"


def test_the_other_studies_holdouts_are_refused_by_name():
    """The quiet failure this exists for: a runner reaching for the wrong
    file by habit (including v0's own, closed-unspent per section 6) gets
    numbers that look entirely plausible."""
    for name in ("holdout.json", "var/state/holdout.json",
                 "holdout_pairs_2026H2.json", "tsmom_holdout_spent.json",
                 "var/tsmom_holdout_spent.json", "tl_v0_holdout_spent.json",
                 "holdout_h60_spent.json", "holdout_htf_ben.json",
                 "var/holdout_htf_ben.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "not v1's holdout" in str(e.value)
    H.load_for("holdout_htf_ben_v1.json")     # its own file passes through
    H.load_for("anything_else.json")           # and so does anything else


def test_describe_splits_the_halves_over_the_training_portion_only():
    d = H.describe(DATES)
    assert d["both_halves_split"] < "2022-01-03"
    assert d["holdout_first"].startswith("2022-01")
    assert d["seen_first"] >= "2025-09-23"
    assert d["train_last"] < "2022-01-03"
    train = [dd for dd in DATES if H.is_training(dd)]
    assert d["both_halves_split"] == train[len(train) // 2]


def test_describe_survives_a_missing_bucket():
    """An empty bucket is not a sign flip (PROGRAM_INDEX section 4)."""
    only_train = H.describe(["2015-01-01", "2016-05-01"])
    assert only_train["holdout_first"] is None and only_train["seen_first"] is None
    only_seen = H.describe(["2026-01-01", "2026-05-01"])
    assert only_seen["train_first"] is None and only_seen["holdout_first"] is None
    assert H.describe([])["n_total"] == 0
