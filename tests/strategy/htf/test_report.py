"""Tests for strategy/htf/report.py -- the step-7 backtest runner that
wires every other module together. W15-0004 step 7 checkpoint 11 (the
last one). This is a WIRING module: the archive-scanning calls
(runner.run_v0/run_c1, controls.run_c2/run_c3, neighbours.run_grid) are
stubbed so these tests run fast and deterministically and check report.py's
OWN logic (training-side filtering, which scenarios get the neighbour
grid, how the final dict is assembled) -- not the underlying modules,
which each have their own dedicated test files already. book.py/account.py/
weekly.py/readback.coverage/holdout.split_dates are all exercised for
real, against a small synthetic archive, since they are cheap."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import holdout as H
from strategy.htf import preflight as P
from strategy.htf import report as REPORT
from strategy.htf import runner as R
from strategy.htf import controls as CT
from strategy.htf import neighbours as NB


def _synth_1h(n_days: int = 30, held_id: int = 1) -> pd.DataFrame:
    """A small, continuous hourly CL.c.0-shaped frame -- same convention
    test_readback.py's own _synth_1h uses (real trading-calendar gaps are
    not needed: bars.resample only needs every timestamp to land in a
    well-defined [0,23) session-elapsed slot, which a continuous hourly
    series always does)."""
    idx = pd.date_range("2015-01-01", periods=24 * n_days, freq="h", tz="UTC")
    closes = 50.0 + np.arange(len(idx), dtype=float) * 0.01
    return pd.DataFrame({
        "open": closes - 0.05, "high": closes + 0.05, "low": closes - 0.05,
        "close": closes, "volume": 100.0, "held_id": held_id,
    }, index=idx)


def _trade(session, direction="long", entry_px=100.0, exit_px=101.0):
    entry_t = pd.Timestamp(str(session) + "T12:00:00", tz="UTC")
    return R.Trade(session=str(session), direction=direction, entry_t=entry_t,
                   fill_adj=entry_px, fill_raw=entry_px, stop_dist=1.0,
                   initial_stop_adj=entry_px - 1.0, start_pos=0, exit_pos=0,
                   exit_t=entry_t + pd.Timedelta(hours=4), exit_price_adj=exit_px,
                   exit_price_raw=exit_px, exit_reason="initial_stop",
                   trail_started=False, n_rolls=0)


class TestTrainingTrades:
    def test_keeps_entries_before_the_lock_date_and_drops_from_it_onward(self):
        before = _trade("2021-12-31")
        on_lock = _trade(H.LOCK_FROM)      # 2022-01-01 itself -- locked, not training
        after = _trade("2023-06-01")
        kept = REPORT.training_trades([before, on_lock, after])
        assert kept == [before]

    def test_empty_input_is_empty_output(self):
        assert REPORT.training_trades([]) == []


@pytest.fixture
def stubbed(monkeypatch):
    """Stubs the four archive-scanning entry points report.py calls, each
    returning a small, fixed, scenario-independent result so the wiring
    logic can be checked without a real archive. v0 has 3 trades: 2 in the
    training window, 1 in the (excluded) holdout."""
    v0_trades = [_trade("2015-03-02", direction="long", exit_px=105.0),
                _trade("2015-08-10", direction="short", entry_px=100.0, exit_px=90.0),
                _trade("2023-01-05", direction="long", exit_px=110.0)]   # holdout -- must be dropped
    c1_trades = [_trade("2015-04-01", exit_px=102.0)]
    c2_trades = [_trade("2015-05-01", exit_px=98.0)]

    def fake_run_v0(df_1h, *, scenario):
        return list(v0_trades), {"triggers": 10, "entries": 3}

    def fake_run_c1(df_1h, *, scenario):
        return list(c1_trades), {"triggers": 5, "entries": 1}

    def fake_run_c2(df_1h, *, scenario, **_):
        return list(c2_trades), {"triggers": 4, "entries": 1}

    def fake_run_c3(df_1h, *, scenario, v0_trades, symbol, level, n_draws, seed_prefix):
        return {"n_draws": n_draws, "pool_size": 100, "n_trades_per_draw": len(v0_trades),
               "p5": -50.0, "p50": 10.0, "p95": 80.0, "nets": np.array([0.0])}

    def fake_run_grid(df_1h, *, scenario, symbol, level, train_start, train_end):
        return {"cells": [], "n_positive": 14, "n_total": 18, "share_positive": 14 / 18}

    monkeypatch.setattr(R, "run_v0", fake_run_v0)
    monkeypatch.setattr(R, "run_c1", fake_run_c1)
    monkeypatch.setattr(CT, "run_c2", fake_run_c2)
    monkeypatch.setattr(CT, "run_c3", fake_run_c3)
    monkeypatch.setattr(NB, "run_grid", fake_run_grid)
    return {"v0": v0_trades, "c1": c1_trades, "c2": c2_trades}


class TestRunScenario:
    def test_v0_is_cut_to_training_before_anything_is_summarised(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        r = REPORT.run_scenario(df_1h, daily_adj, scenario="B")
        assert r["trades_training"]["v0"] == 2      # the 2023 trade is dropped
        assert r["summary"]["mid"].trades == 2

    def test_neighbour_grid_runs_only_when_asked(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        with_nb = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=True)
        without_nb = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=False)
        assert with_nb["neighbour_grid"] is not None
        assert with_nb["neighbour_grid"]["n_positive"] == 14
        assert without_nb["neighbour_grid"] is None
        # criterion 8 must reflect that difference
        crit8_with = next(c for c in with_nb["criteria"] if c.n == 8)
        crit8_without = next(c for c in without_nb["criteria"] if c.n == 8)
        assert crit8_with.passed is True         # 14/18 >= 12
        assert crit8_without.passed is None      # "NOT YET BUILT" (not requested)

    def test_c3_runs_only_when_asked_and_only_if_v0_has_training_trades(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        skipped = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_c3=False)
        assert skipped["controls"]["c3"] is None
        run = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_c3=True)
        assert run["controls"]["c3"]["p95"] == 80.0
        crit6 = next(c for c in run["criteria"] if c.n == 6)
        assert crit6.passed is not None

    def test_account_view_gets_the_session_calendar_only_for_scenario_b(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        b = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=False, run_c3=False)
        a2h = REPORT.run_scenario(df_1h, daily_adj, scenario="A-2H", run_neighbours=False, run_c3=False)
        assert "overnight_margin_breaches" in b["account_view"]["MCL"]["rows"][0]
        assert "overnight_margin_breaches" not in a2h["account_view"]["MCL"]["rows"][0]

    def test_account_view_is_built_for_both_mcl_and_cl(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        r = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=False, run_c3=False)
        assert r["account_view"]["MCL"]["symbol"] == "MCL"
        assert r["account_view"]["CL"]["symbol"] == "CL"
        assert r["account_view"]["CL"]["max_size"] is None   # CL is n=1 only

    def test_weekly_context_has_the_three_alignment_buckets(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        r = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=False, run_c3=False)
        assert set(r["weekly_context"].keys()) == {"with", "against", "none"}

    def test_controls_net_is_computed_from_training_filtered_c1_c2(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        r = REPORT.run_scenario(df_1h, daily_adj, scenario="B", run_neighbours=False, run_c3=False)
        c1_trade = stubbed["c1"][0]
        c2_trade = stubbed["c2"][0]
        assert r["controls"]["c1_net_mid"] == pytest.approx(c1_trade.net_pnl("MCL", "mid"))
        assert r["controls"]["c2_net_mid"] == pytest.approx(c2_trade.net_pnl("MCL", "mid"))

    def test_nine_criteria_are_always_returned(self, stubbed):
        df_1h = _synth_1h()
        _, daily_adj = P.prepare_grids(df_1h)
        r = REPORT.run_scenario(df_1h, daily_adj, scenario="B")
        assert [c.n for c in r["criteria"]] == list(range(1, 10))


class TestRun:
    def test_default_scenarios_are_all_four(self, stubbed, monkeypatch):
        df_1h = _synth_1h()
        monkeypatch.setattr(REPORT.B, "load_1h", lambda archive: df_1h)
        report = REPORT.run("unused-archive", run_c3=False)
        assert set(report["scenarios"].keys()) == set(REPORT.ALL_SCENARIOS)
        # default neighbour_scenarios = SCORED_SCENARIOS only
        assert report["scenarios"]["B"]["neighbour_grid"] is not None
        assert report["scenarios"]["A-2H"]["neighbour_grid"] is not None
        assert report["scenarios"]["A-1H"]["neighbour_grid"] is None
        assert report["scenarios"]["A-4H"]["neighbour_grid"] is None

    def test_scenario_selection_and_neighbour_scoping(self, stubbed, monkeypatch):
        df_1h = _synth_1h()
        monkeypatch.setattr(REPORT.B, "load_1h", lambda archive: df_1h)
        report = REPORT.run("unused-archive", scenarios=("B", "A-2H", "A-1H"),
                            neighbour_scenarios=("B",), run_c3=False)
        assert set(report["scenarios"].keys()) == {"B", "A-2H", "A-1H"}
        assert report["scenarios"]["B"]["neighbour_grid"] is not None
        assert report["scenarios"]["A-2H"]["neighbour_grid"] is None
        assert report["scenarios"]["A-1H"]["neighbour_grid"] is None
        assert "coverage" in report
        assert "holdout_status" in report


class TestJsonable:
    def test_round_trips_through_json_dumps_without_error(self, stubbed, monkeypatch):
        import json
        df_1h = _synth_1h()
        monkeypatch.setattr(REPORT.B, "load_1h", lambda archive: df_1h)
        report = REPORT.run("unused-archive", scenarios=("B",),
                            neighbour_scenarios=("B",), run_c3=True)
        text = json.dumps(REPORT._jsonable(report), indent=2)
        assert '"net"' in text
        parsed = json.loads(text)
        assert parsed["scenarios"]["B"]["summary"]["mid"]["trades"] == 2
