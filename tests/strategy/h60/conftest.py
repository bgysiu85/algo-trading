"""Every H60 test runs with the holdout's cut file and spend ledger pointed
into tmp_path. holdout_h60.json lives at the repo root, which tests/conftest.py
does not protect (it guards var/ and the bar caches), and a test that wrote
the real cut would fix the study's holdout from synthetic sessions -- the
first draft of test_h60_run.py did exactly that in a scratch copy."""
from __future__ import annotations

import pytest

from strategy.h60 import holdout as H


@pytest.fixture(autouse=True)
def _h60_holdout_paths_are_temporary(tmp_path, monkeypatch):
    real_cut, real_ledger = H.CUT_PATH, H.LEDGER_PATH
    existed = (real_cut.exists(), real_ledger.exists())
    monkeypatch.setattr(H, "CUT_PATH", tmp_path / "_guard_cut" / "holdout_h60.json")
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "_guard_cut" / "holdout_h60_spent.json")
    (tmp_path / "_guard_cut").mkdir()
    yield
    assert (real_cut.exists(), real_ledger.exists()) == existed, (
        "an H60 test created or removed the REAL holdout file at the repo root")
