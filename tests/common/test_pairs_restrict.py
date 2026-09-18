#!/usr/bin/env python3
"""The restricted universe is a SUBSET, unchanged row for row."""
from __future__ import annotations

import json

import pytest

from common import pairs_restrict as R

ROWS = [{"symbol": "A", "date": "2026-01-02", "first_seen": "x", "best_rank": 1},
        {"symbol": "B", "date": "2026-01-02", "first_seen": "y", "best_rank": 2},
        {"symbol": "C", "date": "2026-01-03", "first_seen": "z", "best_rank": 3}]


def test_it_only_removes_and_never_edits():
    out = R.restrict(ROWS, ["2026-01-02"])
    assert out == ROWS[:2]
    assert all(any(r is o for o in ROWS) for r in out)      # the same objects


def test_a_date_the_pairs_file_does_not_have_is_simply_absent():
    assert R.restrict(ROWS, ["2026-01-02", "2026-06-01"]) == ROWS[:2]


def test_dates_come_from_a_studys_meta_sessions(tmp_path):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({"sessions": ["2026-01-03"], "qty": 100}), encoding="utf-8")
    assert R.dates_from(p) == ["2026-01-03"]


def test_an_empty_sessions_list_is_refused(tmp_path):
    p = tmp_path / "meta.json"
    p.write_text(json.dumps({"sessions": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        R.dates_from(p)


def test_the_published_file_cannot_be_overwritten(tmp_path):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(ROWS), encoding="utf-8")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"sessions": ["2026-01-02"]}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        R.main(["--pairs", str(p), "--dates-from", str(m), "--out", str(p)])
    assert "not overwritten" in str(e.value)


def test_a_restriction_that_keeps_nothing_is_refused(tmp_path):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(ROWS), encoding="utf-8")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"sessions": ["2030-01-01"]}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        R.main(["--pairs", str(p), "--dates-from", str(m), "--out", str(tmp_path / "o.json")])
    assert "kept nothing" in str(e.value)


def test_the_file_written_round_trips(tmp_path):
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps(ROWS), encoding="utf-8")
    m = tmp_path / "meta.json"
    m.write_text(json.dumps({"sessions": ["2026-01-02"]}), encoding="utf-8")
    out = tmp_path / "o.json"
    R.main(["--pairs", str(p), "--dates-from", str(m), "--out", str(out)])
    assert json.loads(out.read_text(encoding="utf-8")) == ROWS[:2]
