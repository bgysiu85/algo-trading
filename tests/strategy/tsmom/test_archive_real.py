#!/usr/bin/env python3
"""Checks against the REAL archive -- skipped wherever it is not mounted.

The engine's tests never need the archive (handover section 2). These do, and
are kept separate so the suite still runs on a machine without E:\\. Point
TSMOM_ARCHIVE at another copy to run them elsewhere.

Nothing here computes a return: it checks the calendar, the contract mapping,
the point values and the held contract's bars on the TRAINING side.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ARCHIVE = Path(os.environ.get("TSMOM_ARCHIVE", r"E:\Databento\GLBX.MDP3"))
pytestmark = pytest.mark.skipif(not (ARCHIVE / "manifest_tsmom.json").exists(),
                                reason=f"TSMOM archive not mounted at {ARCHIVE}")


@pytest.fixture(scope="module")
def loaded():
    pytest.importorskip("databento")
    from strategy.tsmom import archive as A
    return A.load_all(ARCHIVE)


def test_manifest_is_the_registered_dataset():
    from strategy.tsmom import archive as A
    assert A.read_manifest(ARCHIVE)["dataset"] == "GLBX.MDP3"


def test_every_bar_maps_and_point_values_agree(loaded):
    for root, (_inp, _c0, note) in loaded.items():
        assert note["unmapped_rows"] == 0, root
        assert note["point_value_mismatch"] == [], note["point_value_mismatch"]
        assert note["saturday_rows_dropped"] == 0, root


def test_the_roll_calendar_passes_at41(loaded):
    from strategy.tsmom import rollcheck as RC
    for root, (inp, c0, _) in loaded.items():
        assert RC.verdict(RC.compare(c0, inp.contracts))["result"] == "PASS", root


def test_training_side_held_contracts_have_bars_and_roots_enter_on_time(loaded):
    from strategy.tsmom.engine import coverage
    cov = coverage({r: v[0] for r, v in loaded.items()})
    assert (cov["held_stale_sessions"] <= 5).all(), cov["held_stale_sessions"]
    assert str(cov.loc["RTY", "enters"]).startswith("2018")
    assert str(cov.loc["TN", "enters"]).startswith("2017")
    assert all(str(v) < "2022-01-01" for v in cov["last"])
