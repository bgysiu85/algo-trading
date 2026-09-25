"""Tests for strategy/htf/neighbours.py (the neighbour grid). W15-0004 step
7 checkpoint 7. run_grid's own archive-level wiring (each cell is a real
runner.run_v0 call) is exercised for real on Ben's machine, same convention
as run_v0/run_c1/run_c3 -- here it is tested against a stubbed run_v0 so the
grid's own bookkeeping (18 cells, correct params threaded, net-positive
count) is verified fast and deterministically."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.htf import neighbours as NB
from strategy.htf import runner as R


def _trade(net_sign):
    """A single fake trade whose net_pnl has the sign requested (via a
    trivially large/negative raw price gap), enough to drive run_grid's
    n_positive count without needing a real archive."""
    px = 101.0 if net_sign > 0 else 99.0
    return R.Trade(session="2015-01-01", direction="long", entry_t=pd.Timestamp("2015-01-01", tz="UTC"),
                   fill_adj=100.0, fill_raw=100.0, stop_dist=1.0, initial_stop_adj=99.0,
                   start_pos=0, exit_pos=0, exit_t=pd.Timestamp("2015-01-01T04:00", tz="UTC"),
                   exit_price_adj=px, exit_price_raw=px, exit_reason="initial_stop",
                   trail_started=False, n_rolls=0)


class TestCells:
    def test_eighteen_combinations_covering_the_registered_ranges(self):
        c = NB.cells()
        assert len(c) == 18
        assert set(x[0] for x in c) == {0.10, 0.20, 0.40}
        assert set(x[1] for x in c) == {1, 2, 3}
        assert set(x[2] for x in c) == {2, 3}
        assert len(set(c)) == 18   # every combination distinct


class TestRunGrid:
    def test_calls_run_v0_once_per_cell_with_the_right_params(self, monkeypatch):
        seen = []

        def fake_run_v0(df_1h, *, scenario, trail_trigger, confirm_window, swing_LR):
            seen.append((trail_trigger, confirm_window, swing_LR))
            return [_trade(1)], {}

        monkeypatch.setattr(R, "run_v0", fake_run_v0)
        result = NB.run_grid(pd.DataFrame(), scenario="B")
        assert len(seen) == 18
        assert set(seen) == set(NB.cells())
        assert result["n_total"] == 18

    def test_counts_net_positive_cells_correctly(self, monkeypatch):
        # first 12 cells net-positive, last 6 net-negative (order follows
        # cells()'s own product order)
        signs = iter([1] * 12 + [-1] * 6)

        def fake_run_v0(df_1h, *, scenario, trail_trigger, confirm_window, swing_LR):
            return [_trade(next(signs))], {}

        monkeypatch.setattr(R, "run_v0", fake_run_v0)
        result = NB.run_grid(pd.DataFrame(), scenario="B")
        assert result["n_positive"] == 12
        assert result["share_positive"] == pytest.approx(12 / 18)

    def test_training_window_filters_trades_by_session_date(self, monkeypatch):
        def fake_run_v0(df_1h, *, scenario, trail_trigger, confirm_window, swing_LR):
            in_window = R.Trade(session="2015-06-01", direction="long",
                                entry_t=pd.Timestamp("2015-06-01", tz="UTC"), fill_adj=100.0,
                                fill_raw=100.0, stop_dist=1.0, initial_stop_adj=99.0, start_pos=0,
                                exit_pos=0, exit_t=pd.Timestamp("2015-06-01T04:00", tz="UTC"),
                                exit_price_adj=101.0, exit_price_raw=101.0, exit_reason="initial_stop",
                                trail_started=False, n_rolls=0)
            out_of_window = R.Trade(session="2023-06-01", direction="long",
                                    entry_t=pd.Timestamp("2023-06-01", tz="UTC"), fill_adj=100.0,
                                    fill_raw=100.0, stop_dist=1.0, initial_stop_adj=99.0, start_pos=0,
                                    exit_pos=0, exit_t=pd.Timestamp("2023-06-01T04:00", tz="UTC"),
                                    exit_price_adj=101.0, exit_price_raw=101.0, exit_reason="initial_stop",
                                    trail_started=False, n_rolls=0)
            return [in_window, out_of_window], {}

        monkeypatch.setattr(R, "run_v0", fake_run_v0)
        import datetime
        result = NB.run_grid(pd.DataFrame(), scenario="B",
                             train_start=datetime.date(2010, 1, 1), train_end=datetime.date(2021, 12, 31))
        assert all(c["trades"] == 1 for c in result["cells"])   # only in_window counted
