"""The HTF-Ben v2 holdout refuses the things it says it refuses.

Gate G3 of `docs/research/REGISTERED_htf_ben_v2.md` (sec 5.1): "v2 holdout
cut and ledger (sec 6), mutation-tested, new file name." Mirrors
tests/strategy/htf/test_v1_holdout.py's own coverage almost line for line
-- v2 keeps the same three-way training/holdout/seen split and the same
two boundary dates v1 registered (sec 6: "same window convention as v1's"),
just its own ledger file and candidate name, and REFUSED_CUT_NAMES gains
v1's own ledger on top of everything v1's module already refused.
"""
from __future__ import annotations

import json

import pytest

import strategy.htf.v2_holdout as H

DATES = [f"{y}-{m:02d}-{d:02d}"
         for y in range(2010, 2027) for m in range(1, 13) for d in (1, 15)]


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    """Never touch the real ledger. It is a one-way door."""
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_htf_ben_v2.json")


def test_the_boundaries_match_v1s():
    """REGISTERED_htf_ben_v2.md sec 6: "same window convention as v1's."
    Checked by value, not by reference -- v2 keeps its own ledger even
    though these two dates are shared with v1."""
    import strategy.htf.v1_holdout as H1
    assert H.HOLDOUT_START == H1.HOLDOUT_START == "2022-01-03"
    assert H.SEEN_START == H1.SEEN_START == "2025-09-23"


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
    assert H.is_locked("2022-01-03") and H.is_locked("2025-09-23")
    assert H.is_locked("2026-01-01")
    assert not H.is_locked("2022-01-02")


def test_the_boundaries_are_exact():
    assert H.is_training("2022-01-02") and not H.is_training("2022-01-03")
    assert H.is_holdout("2022-01-03") and H.is_holdout("2025-09-22")
    assert not H.is_holdout("2022-01-02") and not H.is_holdout("2025-09-23")
    assert H.is_seen("2025-09-23") and not H.is_seen("2025-09-22")


def test_a_bare_year_month_lands_on_the_right_side_of_each_boundary():
    for m in ("2021-12", "2022-01", "2025-09", "2025-10"):
        assert H.is_training(m) == H.is_training(m + "-01"), m
        assert H.is_holdout(m) == H.is_holdout(m + "-01"), m
        assert H.is_seen(m) == H.is_seen(m + "-01"), m


def test_spending_requires_a_candidate_name():
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True)
    assert "candidate name" in str(e.value)


def test_only_v2_may_spend_it():
    """sec 6: "Spent once, by v2 on B ... only." v2 has no registered
    ablations (sec 2.4: "None"), so the bad-candidate list here is the
    OTHER lines' names (v0, v1 and v1's own ablations/controls) rather
    than any v2-specific variant."""
    for bad in ("v1", "v0", "v1-curl", "v1-F1", "v1-F2", "v1-X", "V2", "c1",
               "C2", "ensemble"):
        with pytest.raises(SystemExit) as e:
            H.split_dates(DATES, spend=True, candidate=bad, scenarios={"B"})
        msg = str(e.value)
        assert "cannot spend" in msg and "v2" in msg
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("scen", [
    {"A-2H"}, {"A-1H"}, {"A-4H"}, {"B", "A-2H"}, {"B", "A-1H"},
    {"B", "A-2H", "A-1H"}, set(), None,
])
def test_scenarios_must_be_exactly_b_alone(scen):
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True, candidate="v2", scenarios=scen)
    assert "alone" in str(e.value)
    assert not H.LEDGER_PATH.exists()


def test_v2_with_b_alone_spends_it():
    keep, _, label = H.split_dates(DATES, spend=True, candidate="v2",
                                   scenarios={"B"})
    assert all(H.is_holdout(d) for d in keep) and "HOLDOUT" in label
    assert not any(H.is_seen(d) for d in keep)
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert rec["candidate"] == "v2"
    assert rec["scenarios"] == ["B"]


def test_a_second_spend_attempt_is_refused_even_by_the_same_name_rule():
    H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    assert keep


def test_the_same_candidate_may_re_read_what_it_already_spent():
    H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    rec = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    rec["spent_at"] = "2020-01-01T00:00:00Z"
    rec["sentinel"] = "written by the first spend"
    H.LEDGER_PATH.write_text(json.dumps(rec, indent=2), encoding="utf-8")

    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    assert keep

    again = json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))
    assert again["spent_at"] == "2020-01-01T00:00:00Z"
    assert again.get("sentinel")


def test_the_ledger_is_written_in_the_same_call_that_hands_over_the_data():
    assert not H.LEDGER_PATH.exists()
    H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    assert H.LEDGER_PATH.exists()


@pytest.mark.parametrize("kw", [{"limit": 10}, {"limit": 1}, {"limit": 0}])
def test_limit_is_refused_on_every_side(kw):
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, **kw)
    assert "limit is refused" in str(e.value)
    with pytest.raises(SystemExit):
        H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"}, **kw)
    with pytest.raises(SystemExit):
        H.seen_dates(DATES, **kw)


def test_the_seen_window_is_never_spendable():
    keep, _, _ = H.split_dates(DATES, spend=True, candidate="v2", scenarios={"B"})
    assert not any(H.is_seen(d) for d in keep)


def test_seen_dates_is_ungated_but_still_only_the_seen_window():
    got = H.seen_dates(DATES)
    assert got
    assert all(H.is_seen(d) for d in got)
    assert not any(H.is_training(d) or H.is_holdout(d) for d in got)
    assert not H.LEDGER_PATH.exists()


def test_the_other_studies_holdouts_are_refused_by_name():
    """The quiet failure this exists for -- and, per REGISTERED sec 6, this
    is the one place v2's own list differs in SHAPE from v1's: v1's own
    ledger is refused here too, on top of everything v0's/TSMOM's/TL-v0's/
    H60's own modules already refused."""
    for name in ("holdout.json", "var/state/holdout.json",
                "holdout_pairs_2026H2.json", "tsmom_holdout_spent.json",
                "var/tsmom_holdout_spent.json", "tl_v0_holdout_spent.json",
                "holdout_h60_spent.json", "holdout_htf_ben.json",
                "var/holdout_htf_ben.json", "holdout_htf_ben_v1.json",
                "var/holdout_htf_ben_v1.json"):
        with pytest.raises(SystemExit) as e:
            H.load_for(name)
        assert "not v2's holdout" in str(e.value)
    H.load_for("holdout_htf_ben_v2.json")
    H.load_for("anything_else.json")


def test_describe_splits_the_halves_over_the_training_portion_only():
    d = H.describe(DATES)
    assert d["both_halves_split"] < "2022-01-03"
    assert d["holdout_first"].startswith("2022-01")
    assert d["seen_first"] >= "2025-09-23"
    assert d["train_last"] < "2022-01-03"
    train = [dd for dd in DATES if H.is_training(dd)]
    assert d["both_halves_split"] == train[len(train) // 2]


def test_describe_survives_a_missing_bucket():
    only_train = H.describe(["2015-01-01", "2016-05-01"])
    assert only_train["holdout_first"] is None and only_train["seen_first"] is None
    only_seen = H.describe(["2026-01-01", "2026-05-01"])
    assert only_seen["train_first"] is None and only_seen["holdout_first"] is None
    assert H.describe([])["n_total"] == 0
