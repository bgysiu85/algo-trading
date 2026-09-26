"""Tests for strategy/htf/v1_grid.py (the sec 3 24-cell neighbour grid).
W15-0011. Exercised at integration level against the same synthetic archive
test_v1_runner.py/test_v1_controls.py use -- there is no small hand-built
fixture that meaningfully exercises 4 crossed knobs at once."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import v1_grid as VG
from strategy.htf import v1_preflight as V1P


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


class TestCellId:
    def test_all_24_combinations_produce_distinct_ids(self):
        ids = {VG.cell_id(cw, n, p, x2)
              for cw in VG.CROSS_WINDOWS for n in VG.F1_WINDOWS
              for p in VG.F1_PERCENTILES for x2 in VG.X2_BAR_COUNTS}
        assert len(ids) == VG.N_CELLS == 24


class TestRunCell:
    def test_one_cell_runs_cleanly_and_reports_its_own_knobs(self, archive_df_1h):
        cell = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=9,
                           pctl=25, x2_bars=1)
        assert cell["cross_window"] == 3 and cell["f1_window"] == 9
        assert cell["f1_percentile"] == 25 and cell["x2_bars"] == 1
        assert cell["cell"] == "cw3_n9_p25_x2b1"
        assert isinstance(cell["net"], float)
        assert cell["trades_taken"] == cell["counts"]["trades_taken"]

    def test_the_primary_cell_is_flagged(self, archive_df_1h):
        primary = VG.run_cell(archive_df_1h, scenario="B",
                              cross_window=V1P.CROSS_CONFIRM_WINDOW, f1_window=9,
                              pctl=V1P.F1_PERCENTILE, x2_bars=1)
        assert primary["is_primary"]
        other = VG.run_cell(archive_df_1h, scenario="B", cross_window=2, f1_window=9,
                            pctl=25, x2_bars=1)
        assert not other["is_primary"]

    def test_a_different_f1_window_gives_a_different_q_h_q_e_in_general(self, archive_df_1h):
        """q_h/q_e are recomputed per-cell (module docstring) -- N=9 and
        N=12 are different rolling windows over the same series, so their
        25th percentiles need not (and on real data, essentially never
        will) coincide."""
        c9 = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=9,
                         pctl=25, x2_bars=1)
        c12 = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=12,
                          pctl=25, x2_bars=1)
        assert (c9["q_h"], c9["q_e"]) != (c12["q_h"], c12["q_e"])


class TestTrainingSideFilter:
    def test_train_end_before_the_archive_starts_empties_every_cell(self, archive_df_1h):
        """Same convention as neighbours.py's own run_grid: a train_end
        that predates the whole archive must drop every trade, not silently
        fall back to the unfiltered count."""
        import datetime
        cell = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=9,
                           pctl=25, x2_bars=1, train_end=datetime.date(2000, 1, 1))
        assert cell["trades_taken"] == 0
        assert cell["net"] == 0.0

    def test_a_generous_training_window_matches_the_unfiltered_run(self, archive_df_1h):
        import datetime
        unfiltered = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=9,
                                 pctl=25, x2_bars=1)
        filtered = VG.run_cell(archive_df_1h, scenario="B", cross_window=3, f1_window=9,
                               pctl=25, x2_bars=1, train_start=datetime.date(2000, 1, 1),
                               train_end=datetime.date(2100, 1, 1))
        assert filtered["trades_taken"] == unfiltered["trades_taken"]
        assert filtered["net"] == pytest.approx(unfiltered["net"])


class TestRunGrid:
    def test_produces_exactly_24_cells_with_a_valid_share(self, archive_df_1h):
        result = VG.run_grid(archive_df_1h, scenario="B")
        assert result["n_cells"] == 24
        assert len(result["cells"]) == 24
        assert 0.0 <= result["share_net_positive"] <= 1.0
        assert result["n_net_positive"] == sum(1 for c in result["cells"] if c["net"] > 0)

    def test_cells_are_reported_in_fixed_nested_loop_order_not_sorted_by_net(self, archive_df_1h):
        """Sec 3: 'Nothing is ranked. No best cell table.' -- the order must
        be the declared knob order, not net descending/ascending."""
        result = VG.run_grid(archive_df_1h, scenario="B")
        expected_order = [
            VG.cell_id(cw, n, p, x2)
            for cw in VG.CROSS_WINDOWS for n in VG.F1_WINDOWS
            for p in VG.F1_PERCENTILES for x2 in VG.X2_BAR_COUNTS
        ]
        assert [c["cell"] for c in result["cells"]] == expected_order

    def test_exactly_one_cell_is_flagged_primary(self, archive_df_1h):
        result = VG.run_grid(archive_df_1h, scenario="B")
        primaries = [c for c in result["cells"] if c["is_primary"]]
        assert len(primaries) == 1
        assert primaries[0]["cell"] == VG.cell_id(*VG.PRIMARY_CELL)
