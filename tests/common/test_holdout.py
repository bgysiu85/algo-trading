#!/usr/bin/env python3
"""The holdout has to be committed, reproducible, and hard to re-cut.

The previous holdout lived under var/, which is gitignored, so it never
travelled: the invariant test SKIPPED on the machine doing the real work and
reported green. That is the worst possible place for a control to be absent.

This one is a split of the rule-generated screened universe, contains nothing
private, and is committed at the repo root. These tests pin the three
properties that make it worth having: it exists in the tree, the boundaries
reproduce from the same inputs, and re-cutting requires an explicit --force
that shows up in a diff.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from common import holdout as H

REPO = Path(__file__).resolve().parents[2]


# --- it has to actually be in the repo --------------------------------------

def test_the_cut_exists():
    assert H.CUT_PATH.exists(), (
        "no holdout.json -- six strategies are about to be scored against one "
        "universe and nothing is being held back. Run: python -m "
        "common.holdout --cut var/state/screen_pairs_consolidated.json "
        "var/state/screen_rejects.json")


def test_the_cut_is_tracked_by_git_unlike_the_last_one():
    """The failure this replaces: the old holdout was gitignored, so the test
    guarding it skipped everywhere except the machine that made it."""
    r = subprocess.run(["git", "check-ignore", "-q", str(H.CUT_PATH)],
                       cwd=REPO, capture_output=True)
    assert r.returncode != 0, (
        f"{H.CUT_PATH.name} is gitignored -- it will not travel, and the "
        "control silently disappears on every other machine")
    r = subprocess.run(["git", "ls-files", "--error-unmatch",
                        str(H.CUT_PATH.relative_to(REPO))],
                       cwd=REPO, capture_output=True)
    assert r.returncode == 0, (
        f"{H.CUT_PATH.name} exists but is untracked -- commit it, or it is a "
        "holdout only on this machine")


def test_the_cut_is_well_formed():
    rec = H.load()
    for k in ("lock_from", "both_halves_split", "n_sessions", "n_train",
              "n_locked", "universe_fingerprint", "cut_at", "lock_fraction"):
        assert k in rec, f"holdout.json is missing {k!r}"
    assert rec["n_train"] + rec["n_locked"] == rec["n_sessions"]
    assert rec["train_last"] < rec["lock_from"]
    assert rec["train_first"] < rec["both_halves_split"] < rec["lock_from"]
    assert rec["n_early"] + rec["n_late"] == rec["n_train"]


def test_the_locked_portion_is_big_enough_to_mean_something():
    """A drop-top-5 check on a handful of sessions is not a check."""
    rec = H.load()
    assert rec["n_locked"] >= 100, (
        f"only {rec['n_locked']} locked sessions -- removing the best 5 "
        "symbols from that is removing the sample, not testing concentration")


# --- the split is a rule, not a choice --------------------------------------

DAYS = [f"2026-{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 15)]


def test_the_split_reproduces_from_the_same_inputs():
    a = H.split(DAYS)
    b = H.split(DAYS)
    assert a == b


def test_the_boundaries_are_fractions_of_the_session_count():
    """Not calendar dates: the halves must carry comparable numbers of TRADING
    days, and trading days are not evenly spread across the calendar."""
    rec = H.split(DAYS, lock_fraction=0.25)
    assert rec["n_locked"] == len(DAYS) - int(len(DAYS) * 0.75)
    assert abs(rec["n_early"] - rec["n_late"]) <= 1


def test_locking_more_does_not_move_the_both_halves_split_arbitrarily():
    """The both-halves boundary is the median of the TRAINING portion, so it is
    a property of the training data rather than of the lock fraction. It does
    move when the training set changes -- but predictably, and earlier."""
    a = H.split(DAYS, lock_fraction=0.20)
    b = H.split(DAYS, lock_fraction=0.40)
    assert b["both_halves_split"] <= a["both_halves_split"]


def test_too_few_sessions_is_refused_rather_than_split():
    with pytest.raises(ValueError, match="too few"):
        H.split(["2026-01-01", "2026-01-02"])


# --- partitioning ------------------------------------------------------------

def test_a_pair_lands_in_exactly_one_set():
    rec = H.split(DAYS)
    pairs = [{"symbol": "AAA", "date": d} for d in DAYS]
    got = H.partition(rec, pairs)
    assert sum(len(v) for v in got.values()) == len(pairs)
    assert not (set(map(str, got["early"])) & set(map(str, got["locked"])))


def test_everything_on_or_after_the_lock_date_is_locked():
    rec = H.split(DAYS)
    assert H.is_locked(rec, rec["lock_from"])
    assert not H.is_locked(rec, DAYS[0])


def test_partition_accepts_tuples_as_well_as_dicts():
    rec = H.split(DAYS)
    got = H.partition(rec, [("AAA", DAYS[0]), ("BBB", DAYS[-1])])
    assert len(got["early"]) == 1 and len(got["locked"]) == 1


# --- the fingerprint ---------------------------------------------------------

def test_the_fingerprint_is_of_the_universe_not_of_the_files(tmp_path):
    """Re-running the screen and getting the same pairs must NOT invalidate the
    cut -- otherwise every regeneration looks like tampering and the signal
    becomes noise."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    rows = [{"symbol": "BBB", "date": "2026-01-02"},
            {"symbol": "AAA", "date": "2026-01-01"}]
    a.write_text(json.dumps(rows))
    b.write_text(json.dumps(list(reversed(rows))))     # same pairs, new order
    assert H.fingerprint([a]) == H.fingerprint([b])


def test_a_changed_universe_changes_the_fingerprint(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps([{"symbol": "AAA", "date": "2026-01-01"}]))
    one = H.fingerprint([a])
    a.write_text(json.dumps([{"symbol": "AAA", "date": "2026-01-01"},
                             {"symbol": "AAA", "date": "2026-01-02"}]))
    assert H.fingerprint([a]) != one


# --- re-cutting has to be deliberate ----------------------------------------

def test_recutting_over_an_existing_cut_is_refused(tmp_path, monkeypatch,
                                                   capsys):
    """A holdout you can re-cut after seeing a result is not a holdout."""
    p = tmp_path / "holdout.json"
    src = tmp_path / "s.json"
    src.write_text(json.dumps([{"symbol": "A", "date": d} for d in DAYS]))
    monkeypatch.setattr(H, "CUT_PATH", p)
    assert H.main(["--cut", str(src)]) == 0
    first = p.read_text()
    assert H.main(["--cut", str(src)]) == 1          # refused
    assert p.read_text() == first                    # and unchanged
    out = capsys.readouterr().out
    assert "DESTROYS THE" in out and "--force" in out


def test_force_re_cuts_and_is_the_only_way(tmp_path, monkeypatch):
    p = tmp_path / "holdout.json"
    src = tmp_path / "s.json"
    src.write_text(json.dumps([{"symbol": "A", "date": d} for d in DAYS]))
    monkeypatch.setattr(H, "CUT_PATH", p)
    H.main(["--cut", str(src)])
    assert H.main(["--cut", str(src), "--force"]) == 0


def test_check_reports_a_universe_that_has_moved(tmp_path, monkeypatch, capsys):
    p = tmp_path / "holdout.json"
    src = tmp_path / "s.json"
    src.write_text(json.dumps([{"symbol": "A", "date": d} for d in DAYS]))
    monkeypatch.setattr(H, "CUT_PATH", p)
    H.main(["--cut", str(src)])
    assert H.main(["--check", str(src)]) == 0
    src.write_text(json.dumps([{"symbol": "A", "date": d} for d in DAYS]
                              + [{"symbol": "ZZZ", "date": DAYS[0]}]))
    assert H.main(["--check", str(src)]) == 1
    assert "DIFFERS" in capsys.readouterr().out


# --- the honesty note has to survive ----------------------------------------

def test_the_cut_records_that_it_does_not_cover_the_existing_strategies():
    """MC5 was scored over the whole period on 2026-09-07, these sessions
    included. The temptation later is to quote its locked-set figure as
    out-of-sample. It is not, and the file says so."""
    rec = H.load()
    note = rec.get("note", "")
    assert "MC5" in note and "NOT out of sample" in note


def test_the_sources_are_machine_neutral():
    """The cut is committed and read on other machines. Recording the absolute
    path it happened to be cut from (a cloud sandbox, in this case) would be a
    statement about nothing."""
    rec = H.load()
    for s in rec["sources"]:
        assert "/" not in s and "\\" not in s, (
            f"{s!r} is a path, not a name -- it will be wrong everywhere "
            "except the machine that cut it")
    assert set(rec["sources"]) == {"screen_pairs_consolidated.json",
                                   "screen_rejects.json"}


def test_no_read_counter_is_advertised():
    """An earlier draft documented a counter of reads against the locked set
    and never incremented it. A control that does not work is worse than an
    absent one, because it is believed."""
    import inspect
    assert "reads" not in H.load()
    src = inspect.getsource(H)
    assert 'rec.get("reads"' not in src
