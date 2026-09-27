"""Tests for strategy/htf/v2_grid.py (sec 4 criterion 8 / sec 5.3's 6-cell
exit-side neighbour grid). W15-0021. Exercised at integration level against
the same synthetic archive test_v2_runner.py uses."""
from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest

from strategy.htf import preflight as P
from strategy.htf import v1_preflight as V1P
from strategy.htf import v2_grid as V2G


def _synth_1h(n_days=500, seed=11):
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


@pytest.fixture(scope="module")
def q_h_q_e(archive_df_1h):
    grids, _ = P.prepare_grids(archive_df_1h)
    q_h, q_e, _, _, _ = V1P.compute_percentiles(grids["4H"])
    return q_h, q_e


class TestCellId:
    def test_all_6_combinations_produce_distinct_ids(self):
        ids = {V2G.cell_id(sw, tt) for sw in V2G.SWING_SIZES for tt in V2G.TRAIL_TRIGGERS}
        assert len(ids) == V2G.N_CELLS == 6


class TestRunCell:
    def test_one_cell_runs_cleanly_and_reports_its_own_knobs(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        cell = V2G.run_cell(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e,
                            swing_LR=2, trail_trigger=0.20)
        assert cell["swing_LR"] == 2 and cell["trail_trigger"] == 0.20
        assert cell["cell"] == "swing2_trail0.20"
        assert isinstance(cell["net"], float)
        assert cell["trades_taken"] == cell["counts"]["trades_taken"]


class TestTrainingSideFilter:
    def test_train_end_before_the_archive_starts_empties_every_cell(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        cell = V2G.run_cell(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, swing_LR=2,
                            trail_trigger=0.20, train_end=datetime.date(2000, 1, 1))
        assert cell["trades_taken"] == 0
        assert cell["net"] == 0.0

    def test_a_generous_training_window_matches_the_unfiltered_run(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        unfiltered = V2G.run_cell(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, swing_LR=2,
                                  trail_trigger=0.20)
        filtered = V2G.run_cell(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e, swing_LR=2,
                                trail_trigger=0.20, train_start=datetime.date(2000, 1, 1),
                                train_end=datetime.date(2100, 1, 1))
        assert filtered["trades_taken"] == unfiltered["trades_taken"]
        assert filtered["net"] == pytest.approx(unfiltered["net"])


class TestRunGrid:
    def test_produces_exactly_6_cells_with_a_valid_share(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        result = V2G.run_grid(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        assert result["n_cells"] == 6
        assert len(result["cells"]) == 6
        assert 0.0 <= result["share_net_positive"] <= 1.0
        assert result["n_net_positive"] == sum(1 for c in result["cells"] if c["net"] > 0)

    def test_cells_are_reported_in_fixed_nested_loop_order_not_sorted_by_net(self, archive_df_1h, q_h_q_e):
        q_h, q_e = q_h_q_e
        result = V2G.run_grid(archive_df_1h, scenario="B", q_h=q_h, q_e=q_e)
        expected_order = [V2G.cell_id(sw, tt) for sw in V2G.SWING_SIZES for tt in V2G.TRAIL_TRIGGERS]
        assert [c["cell"] for c in result["cells"]] == expected_order
