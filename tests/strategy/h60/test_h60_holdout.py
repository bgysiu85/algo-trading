"""Gate G6 -- holdout_h60.json cut and enforced in code, mutation-tested
(REGISTERED_h60_v0.md §8, §9). Every test writes under tmp_path; the real
cut file at the repo root is never touched by the suite."""
from __future__ import annotations

import json
import math

import pytest

from strategy.h60 import holdout as H
from tests.strategy.h60 import _synth as S

SESSIONS = S.sessions(250)
ALL_FALSE = {r: False for r in H.PRIORITY}


def cut(tmp_path, sessions=SESSIONS):
    p = tmp_path / "holdout_h60.json"
    return p, H.cut(sessions, p)


def boundary_is_right(p, sessions=SESSIONS):
    train, n_locked, _ = H.split_sessions(sessions, path=p)
    rec = H.read(p)
    first = S.sessions(1, start=__import__("datetime").date.fromisoformat(rec["first_locked"]))[0]
    assert n_locked == math.ceil(0.2 * len(sessions))
    assert train[-1] < first
    assert first not in train
    assert train[-1].isoformat() == rec["last_training"]
    return True


def test_last_twenty_percent_by_rule(tmp_path):
    p, rec = cut(tmp_path)
    assert rec["n_locked"] == 50 and rec["n_training"] == 200
    assert rec["first_locked"] == SESSIONS[200].isoformat()
    assert rec["last_training"] == SESSIONS[199].isoformat()
    assert boundary_is_right(p)
    assert json.loads(p.read_text(encoding="utf-8"))["first_locked"] == rec["first_locked"]


def test_the_cut_is_computed_not_typed_and_ignores_input_order(tmp_path):
    shuffled = list(reversed(SESSIONS)) + SESSIONS[:3]         # duplicates too
    assert H.compute_cut(shuffled) == H.compute_cut(SESSIONS)


def test_boundary_mutation_is_caught(tmp_path, monkeypatch):
    """Mutation: the lock starts one session late (> instead of >=). The
    boundary check must fail."""
    p, _ = cut(tmp_path)
    real = H.is_locked
    monkeypatch.setattr(H, "is_locked",
                        lambda d, rec: H._d(d) > H._d(rec["first_locked"]))
    with pytest.raises(AssertionError):
        boundary_is_right(p)
    monkeypatch.setattr(H, "is_locked", real)
    assert boundary_is_right(p)


def test_recut_is_refused_whatever_it_says(tmp_path):
    p, _ = cut(tmp_path)
    with pytest.raises(H.HoldoutRefused, match="cut ONCE"):
        H.cut(SESSIONS[:200], p)
    with pytest.raises(H.HoldoutRefused):
        H.cut(SESSIONS, p)


def test_limit_is_refused_on_both_sides(tmp_path):
    p, _ = cut(tmp_path)
    with pytest.raises(H.HoldoutRefused, match="limit"):
        H.split_sessions(SESSIONS, path=p, limit=10)
    with pytest.raises(H.HoldoutRefused, match="limit"):
        H.split_sessions(SESSIONS, path=p, spend=True, candidate="DON-60",
                         verdicts=ALL_FALSE, limit=10)


def test_no_cut_no_numbers(tmp_path):
    with pytest.raises(H.HoldoutRefused, match="gate G6"):
        H.split_sessions(SESSIONS, path=tmp_path / "holdout_h60.json")


def test_other_studies_holdouts_are_refused_by_name(tmp_path):
    for name in ("holdout.json", "holdout_spy.json", "holdout_swing.json"):
        with pytest.raises(H.HoldoutRefused, match="another study"):
            H.cut(SESSIONS, tmp_path / name)


def test_sessions_after_the_pulled_sample_are_locked_too(tmp_path):
    p, rec = cut(tmp_path)
    later = S.sessions(10, start=SESSIONS[-1])[1:]
    train, _, _ = H.split_sessions(SESSIONS + later, path=p)
    assert not set(later) & set(train)


def test_the_spender_is_the_first_passing_rule_in_section_8_order():
    v = dict(ALL_FALSE, **{"ORB-60": True, "MCL-60": True})
    assert H.spend_candidate(v) == "ORB-60"
    v["DON-60"] = True
    assert H.spend_candidate(v) == "DON-60"
    with pytest.raises(H.HoldoutRefused, match="nothing may spend"):
        H.spend_candidate(ALL_FALSE)
    with pytest.raises(H.HoldoutRefused, match="all seven"):
        H.spend_candidate({"DON-60": True})


def test_spend_once_by_the_allowed_rule_only(tmp_path):
    p, rec = cut(tmp_path)
    ledger = tmp_path / "spent.json"
    v = dict(ALL_FALSE, **{"VW9-60": True, "MC5-60": True})
    with pytest.raises(H.HoldoutRefused, match="cannot spend"):
        H.split_sessions(SESSIONS, path=p, spend=True, candidate="MC5-60",
                         verdicts=v, ledger=ledger)
    assert not ledger.exists()
    locked, n_train, side = H.split_sessions(SESSIONS, path=p, spend=True,
                                             candidate="VW9-60", verdicts=v,
                                             ledger=ledger)
    assert len(locked) == 50 and n_train == 200 and side.startswith("LOCKED")
    led = json.loads(ledger.read_text(encoding="utf-8"))
    assert led["candidate"] == "VW9-60" and led["verdicts"]["VW9-60"] is True
    with pytest.raises(H.HoldoutRefused, match="already spent"):
        H.split_sessions(SESSIONS, path=p, spend=True, candidate="VW9-60",
                         verdicts=v, ledger=ledger)


def test_priority_matches_the_rule_registry():
    from strategy.h60.rules import PRIORITY
    assert H.PRIORITY == PRIORITY
