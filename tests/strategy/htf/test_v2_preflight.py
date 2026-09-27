"""Tests for strategy/htf/v2_preflight.py (G2). W15-0021.

REGISTERED_htf_ben_v2.md sec 2.1/sec 5.2: v2's entries and q_h/q_e are
inherited from v1, unchanged -- so this gate's own entries/counts must be
IDENTICAL to v1_preflight's own G2 numbers for the same scenario, computed
with the same q_h/q_e. That equality (not just "runs cleanly") is the test
that actually matters here.

run() takes an "archive" identifier for bars.load_1h to resolve (same
convention as preflight.py's/v1_preflight.py's own run(), neither of which
is unit-tested against a raw synthetic frame either -- see either module's
own test file). B.load_1h is monkeypatched to hand back an
already-in-memory synthetic frame directly, the same seam run()'s own
callers (the CLI, v2_report.py) go through for a real archive.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import preflight as P
from strategy.htf import v1_preflight as V1P
from strategy.htf import v2_preflight as V2P


def _synth_1h(n_days=900, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-06-07", periods=24 * n_days, freq="h", tz="UTC")
    steps = rng.normal(loc=0.002, scale=0.35, size=len(idx))
    t = np.arange(len(idx))
    drift = 3.0 * np.sin(t / 800.0)
    close = 50.0 + np.cumsum(steps) * 0.05 + drift
    close = np.clip(close, 5.0, None)
    high = close + np.abs(rng.normal(0.1, 0.05, len(idx)))
    low = close - np.abs(rng.normal(0.1, 0.05, len(idx)))
    open_ = close - rng.normal(0, 0.05, len(idx))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 100.0, "held_id": 1}, index=idx)
    return df


@pytest.fixture(scope="module")
def archive_df_1h():
    return _synth_1h()


@pytest.fixture(autouse=True)
def _load_1h_returns_the_frame_directly(monkeypatch, archive_df_1h):
    """See module docstring: run()'s only job with its `archive_1h` arg is
    to hand it to bars.load_1h -- stub that one seam so run() can be
    exercised against an in-memory synthetic frame, exactly as
    test_v1_runner.py/test_v1_controls.py already do for run_v1/run_c1/etc
    (none of which call bars.load_1h themselves -- only run()/main() do)."""
    monkeypatch.setattr(V2P.B, "load_1h", lambda archive: archive)


def test_v2_g2_entries_are_identical_to_v1s_own_g2_at_the_inherited_q(archive_df_1h):
    """The module's own thesis (docstring): calling detect_v1 with v2's
    inherited q_h/q_e and v1's registered defaults is byte-for-byte v1's
    own G2 call."""
    grids, daily_adj = P.prepare_grids(archive_df_1h)
    entry_adj = grids["4H"]
    four_h_adj = grids["4H"]
    entries_direct, counts_direct = V1P.detect_v1(entry_adj, daily_adj, four_h_adj,
                                                  scenario="B", q_h=V2P.Q_H, q_e=V2P.Q_E)
    report = V2P.run(archive_df_1h)
    assert report["counts_full_history"] == counts_direct
    assert report["totals"]["entries_training"] == len(
        [e for e in entries_direct
         if P.TRAIN_START <= pd.Timestamp(e["session"]).date() <= P.TRAIN_END])


def test_min_entries_threshold_is_150():
    assert V2P.MIN_ENTRIES == 150


def test_run_reports_the_inherited_q_h_q_e_not_recomputed_values(archive_df_1h):
    report = V2P.run(archive_df_1h)
    assert report["q_h"] == V2P.Q_H == pytest.approx(0.190280)
    assert report["q_e"] == V2P.Q_E == pytest.approx(0.501239)


def test_stop_rule_shape(archive_df_1h):
    report = V2P.run(archive_df_1h)
    sr = report["stop_rule"]
    assert sr["min_required"] == 150
    assert sr["underpowered"] == (sr["v2_B_entries_training"] < 150)
