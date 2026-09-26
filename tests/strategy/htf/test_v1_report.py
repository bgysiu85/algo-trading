"""Tests for strategy/htf/v1_report.py. W15-0011.

training_trades/seen_trades/v1_score/verdict are unit-tested directly
(fabricated Trade lists / plain dicts -- no need for a real archive: they
only look at t.session strings and pandas frames). run_scenario/run are
exercised at integration level against the same short synthetic archive
test_v1_runner.py/test_v1_controls.py/test_v1_grid.py already use; that
archive never reaches 2022, so every trade it produces is training-side by
construction -- these integration tests check the WIRING (shapes, which
scenario gets scored, q_h/q_e shared across scenarios), not real holdout/
seen-window filtering, which is covered by the direct unit tests below and
by v1_holdout's own 29 tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import book as BK
from strategy.htf import preflight as P
from strategy.htf import runner as R
from strategy.htf import v1_report as VR


def _trade(session, net_hint=0.0):
    """A minimal runner.Trade -- only `session`/`entry_t`/`exit_t` and the
    fields net_pnl/gross_pnl/cost need are populated; net_hint is baked in
    via fill/exit so net_pnl comes out signed as intended without reaching
    into costs.py."""
    entry_t = pd.Timestamp(f"{session}T10:00:00Z")
    exit_t = pd.Timestamp(f"{session}T14:00:00Z")
    fill = 100.0
    exit_price = fill + net_hint / 100.0   # MCL: $100/point-ish scale is irrelevant here
    return R.Trade(session=session, direction="long", fill_adj=fill, fill_raw=fill,
                   stop_dist=1.0, initial_stop_adj=fill - 1.0, start_pos=0, exit_pos=1,
                   entry_t=entry_t, exit_t=exit_t, exit_price_adj=exit_price,
                   exit_price_raw=exit_price, exit_reason="data_end", trail_started=False,
                   n_rolls=0)


class TestTrainingTrades:
    def test_empty_list_returns_empty(self):
        assert VR.training_trades([]) == []

    def test_keeps_only_pre_2022_01_03_sessions(self):
        trades = [_trade("2021-12-31"), _trade("2022-01-02"), _trade("2022-01-03"),
                 _trade("2025-01-01")]
        kept = VR.training_trades(trades)
        assert {t.session for t in kept} == {"2021-12-31", "2022-01-02"}


class TestSeenTrades:
    def test_empty_list_returns_empty(self):
        assert VR.seen_trades([]) == []

    def test_keeps_only_2025_09_23_onward(self):
        trades = [_trade("2025-09-22"), _trade("2025-09-23"), _trade("2026-01-01")]
        kept = VR.seen_trades(trades)
        assert {t.session for t in kept} == {"2025-09-23", "2026-01-01"}

    def test_training_and_seen_trades_never_overlap(self):
        trades = [_trade("2021-12-31"), _trade("2023-06-15"), _trade("2025-09-23")]
        train = {t.session for t in VR.training_trades(trades)}
        seen = {t.session for t in VR.seen_trades(trades)}
        assert not (train & seen)


class TestV1Score:
    def _mid_frame(self, nets, years):
        return pd.DataFrame({
            "net": nets, "year": years,
            "entry_t": pd.date_range("2015-01-01", periods=len(nets), freq="30D"),
        })

    def test_nine_criteria_in_order_with_the_v1_specific_threshold_wording(self):
        df_mid = self._mid_frame([100.0] * 160, [2015] * 80 + [2016] * 80)
        year_net = {2015: 8000.0, 2016: 8000.0}
        crit = VR.v1_score(df_mid=df_mid, df_high=df_mid, year_net_mid=year_net,
                           net_c1=1000.0, net_c2=1000.0, c3_p95=1000.0,
                           neighbour_positive=17, neighbour_total=24)
        assert [c.n for c in crit] == list(range(1, 10))
        eight = crit[7]
        assert "16 of 24" in eight.label
        assert eight.passed is True and eight.detail == "17/24"

    def test_criterion_8_reports_not_yet_built_without_neighbour_data(self):
        df_mid = self._mid_frame([100.0] * 160, [2015] * 160)
        crit = VR.v1_score(df_mid=df_mid, df_high=df_mid, year_net_mid={2015: 16000.0},
                           net_c1=1000.0, net_c2=1000.0, c3_p95=1000.0)
        eight = crit[7]
        assert eight.passed is None and eight.detail == "NOT YET BUILT"

    def test_criterion_9_uses_150_by_default(self):
        df_mid = self._mid_frame([10.0] * 149, [2015] * 149)
        crit = VR.v1_score(df_mid=df_mid, df_high=df_mid, year_net_mid={2015: 1490.0},
                           net_c1=None, net_c2=None, c3_p95=None)
        nine = crit[8]
        assert nine.passed is False and "150" in nine.label


class TestVerdict:
    def test_all_pass_is_flagged(self):
        crit = [BK.Criterion(n, f"c{n}", True, "") for n in range(1, 10)]
        v = VR.verdict(crit)
        assert v["all_nine_pass"] and not v["closed_on_criterion_5"]
        assert v["failing"] == [] and v["not_evaluated"] == []

    def test_failing_criterion_5_is_flagged_even_if_only_failure(self):
        crit = [BK.Criterion(n, f"c{n}", n != 5, "") for n in range(1, 10)]
        v = VR.verdict(crit)
        assert v["closed_on_criterion_5"]
        assert not v["all_nine_pass"]
        assert v["failing"] == [5]

    def test_failing_a_different_criterion_does_not_flag_criterion_5_closure(self):
        crit = [BK.Criterion(n, f"c{n}", n != 3, "") for n in range(1, 10)]
        v = VR.verdict(crit)
        assert not v["closed_on_criterion_5"]
        assert v["failing"] == [3]

    def test_not_evaluated_criteria_are_reported_separately_from_failures(self):
        crit = [BK.Criterion(n, f"c{n}", True if n != 8 else None, "") for n in range(1, 10)]
        v = VR.verdict(crit)
        assert v["not_evaluated"] == [8]
        assert v["failing"] == []
        assert not v["all_nine_pass"]


def _synth_1h(n_days=350, seed=13):
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


class TestRunScenarioIntegration:
    def test_b_is_scored_with_a_full_criteria_list_and_a_neighbour_grid(self, archive_df_1h):
        grids, daily_adj = P.prepare_grids(archive_df_1h)
        from strategy.htf import v1_preflight as V1P
        q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])
        r = VR.run_scenario(archive_df_1h, daily_adj, scenario="B", q_h=q_h, q_e=q_e,
                            run_c3=True, n_draws=15)
        assert r["scored"] is True
        assert r["criteria"] is not None and len(r["criteria"]) == 9
        assert r["verdict"] is not None
        assert r["neighbour_grid"] is not None
        assert r["neighbour_grid"]["n_cells"] == 24

    def test_a2h_is_reported_but_not_scored_and_skips_the_grid(self, archive_df_1h):
        grids, daily_adj = P.prepare_grids(archive_df_1h)
        from strategy.htf import v1_preflight as V1P
        q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])
        r = VR.run_scenario(archive_df_1h, daily_adj, scenario="A-2H", q_h=q_h, q_e=q_e,
                            run_neighbours=False, run_c3=True, n_draws=15)
        assert r["scored"] is False
        assert r["criteria"] is None and r["verdict"] is None
        assert r["neighbour_grid"] is None

    def test_ablations_are_reported_never_scored(self, archive_df_1h):
        grids, daily_adj = P.prepare_grids(archive_df_1h)
        from strategy.htf import v1_preflight as V1P
        q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])
        r = VR.run_scenario(archive_df_1h, daily_adj, scenario="B", q_h=q_h, q_e=q_e,
                            run_neighbours=False, run_c3=False)
        for key in ("v1-curl", "v1-F1", "v1-F2", "v1-X"):
            assert key in r["ablations"]
            assert "summary_mid" in r["ablations"][key]


class TestRunIntegration:
    """run()'s own job is loading the archive (B.load_1h) then handing off
    to run_scenario per scenario -- same convention as v0's own
    test_report.py: stub load_1h with the already-in-memory synthetic
    frame so these tests don't need a real archive path, and still
    exercise run()'s own wiring (shared q_h/q_e, _jsonable) for real."""

    def test_both_scenarios_share_the_same_q_h_q_e(self, archive_df_1h, monkeypatch):
        monkeypatch.setattr(VR.B, "load_1h", lambda archive: archive_df_1h)
        report = VR.run(archive_df_1h, scenarios=("B", "A-2H"),
                        neighbour_scenarios=(), run_c3=False)
        assert report["scenarios"]["B"]["q_h"] == report["scenarios"]["A-2H"]["q_h"]
        assert report["scenarios"]["B"]["q_e"] == report["scenarios"]["A-2H"]["q_e"]
        assert report["q_h"] == report["scenarios"]["B"]["q_h"]

    def test_jsonable_round_trips_through_json_dumps(self, archive_df_1h, monkeypatch):
        import json
        monkeypatch.setattr(VR.B, "load_1h", lambda archive: archive_df_1h)
        report = VR.run(archive_df_1h, scenarios=("B",), neighbour_scenarios=(),
                        run_c3=False)
        text = json.dumps(VR._jsonable(report))
        assert isinstance(text, str) and len(text) > 0
