"""Smoke tests for strategy/htf/v2_report.py (sec 3 + sec 4 wiring).
W15-0021. Not a numeric validation of any real backtest result -- just
confirms the whole pipeline (v2_runner + v2_controls + v2_grid +
v2_holdout + book/account/weekly/readback) wires together and produces the
shape sec 3/sec 4 require, on a small synthetic archive with cheap
draw/grid counts.

run()'s `archive_1h` arg is only ever handed to bars.load_1h (same
convention as v1_report.py's own run()) -- monkeypatched here to return an
in-memory synthetic frame directly, same seam test_v2_preflight.py uses.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import v2_report as V2REP


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
    monkeypatch.setattr(V2REP.B, "load_1h", lambda archive: archive)


class TestRunShape:
    def test_run_produces_scenario_b_only_with_nine_criteria(self, archive_df_1h):
        report = V2REP.run(archive_df_1h, run_neighbours=True, run_c3=True, n_draws=10)
        assert set(report["scenarios"].keys()) == {"B"}
        r = report["scenarios"]["B"]
        assert len(r["criteria"]) == 9
        assert r["neighbour_grid"]["n_cells"] == 6
        assert r["controls"]["c3"]["n_draws"] == 10

    def test_skip_neighbours_and_c3_leaves_those_fields_none(self, archive_df_1h):
        report = V2REP.run(archive_df_1h, run_neighbours=False, run_c3=False)
        r = report["scenarios"]["B"]
        assert r["neighbour_grid"] is None
        assert r["controls"]["c3"] is None
        # criterion 8 must be reported as NOT scored, not silently passed
        crit8 = next(c for c in r["criteria"] if c.n == 8)
        assert crit8.passed is None

    def test_verdict_closes_on_criterion_5_iff_c1_or_c2_beats_v2(self, archive_df_1h):
        report = V2REP.run(archive_df_1h, run_neighbours=False, run_c3=False)
        r = report["scenarios"]["B"]
        v = r["verdict"]
        c5 = next(c for c in r["criteria"] if c.n == 5)
        assert v["closed_on_criterion_5"] == (c5.passed is False)

    def test_originating_trade_count_check_is_present_and_shaped(self, archive_df_1h):
        report = V2REP.run(archive_df_1h, run_neighbours=False, run_c3=False)
        r = report["scenarios"]["B"]
        occ = r["originating_trade_count_check"]
        assert occ["originating_trade_count"] == 286
        assert occ["trades_taken"] == r["summary"]["mid"].trades
        assert isinstance(occ["flag"], (bool, np.bool_))

    def test_never_touches_the_holdout(self, archive_df_1h, tmp_path, monkeypatch):
        from strategy.htf import v2_holdout as VH
        monkeypatch.setattr(VH, "LEDGER_PATH", tmp_path / "holdout_htf_ben_v2.json")
        V2REP.run(archive_df_1h, run_neighbours=False, run_c3=False)
        assert not VH.LEDGER_PATH.exists(), (
            "v2_report.run() must never spend the holdout (module docstring)")
