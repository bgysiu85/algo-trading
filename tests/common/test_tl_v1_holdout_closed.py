"""W15-0030 / REGISTERED_tl_v2.md G3: TL-v1's ledger is CLOSED-UNSPENT, so the 2022-2025 window cannot be
spent twice. The committed marker is read for real; the refusal paths run against a temp copy."""
from __future__ import annotations

import json

import pytest

import common.tl_v1_holdout as H

DATES = [f"{y}-{m:02d}-15" for y in range(2019, 2026) for m in range(1, 13)]


def test_the_committed_marker_says_closed_unspent_and_names_its_item():
    rec = json.loads((H.ROOT / "tl_v1_holdout_spent.json").read_text(encoding="utf-8"))
    assert rec["closed_unspent"] is True and rec["closed_by"] == "W15-0030" and rec["candidate"] is None


def test_tl_v1_can_no_longer_spend_and_the_refusal_names_the_reason(tmp_path, monkeypatch):
    p = tmp_path / "tl_v1_holdout_spent.json"
    p.write_text((H.ROOT / "tl_v1_holdout_spent.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(H, "LEDGER_PATH", p)
    with pytest.raises(SystemExit) as e:
        H.split_dates(DATES, spend=True, candidate="TL-v1")
    assert "CLOSED-UNSPENT" in str(e.value) and "holdout_tl_v2.json" in str(e.value)
    keep, _, _ = H.split_dates(DATES)                       # the training side is unaffected
    assert keep and all(d < "2022-01-03" for d in keep)


def test_the_cli_refuses_to_spend_a_closed_ledger_and_status_reads_it(tmp_path, monkeypatch, capsys):
    p = tmp_path / "tl_v1_holdout_spent.json"
    p.write_text((H.ROOT / "tl_v1_holdout_spent.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(H, "LEDGER_PATH", p)
    assert H.main(["--status"]) == 0
    assert "CLOSED-UNSPENT" in capsys.readouterr().out
    assert H.main(["--spend", "TL-v1"]) == 2
    assert json.loads(p.read_text(encoding="utf-8"))["candidate"] is None      # nothing was written


def test_without_the_marker_tl_v1_behaves_exactly_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "tl_v1_holdout_spent.json")
    keep, _, label = H.split_dates(DATES, spend=True, candidate="TL-v1")
    assert keep and "LOCKED" in label
