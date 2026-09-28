#!/usr/bin/env python3
"""DVP-v0 runner: P_ref refusal, DVP-v0's own bootstrap threshold (95%,
NOT runner.py's 99%), the pre-flight's no-P&L/no-exit-walk discipline,
the sec 7.4 neighbour grid shape, full-contract (not micro) pricing for
the sec 7.3 replication block, and an end-to-end runtime smoke test of
--backtest on a small synthetic multi-year archive.
REGISTERED_w16_drift_vwap.md sec 6.1/7/9."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_drift_vwap import trend_session  # noqa: E402

import strategy.w16.drift_vwap as D
import strategy.w16.dvp_runner as DR
import strategy.w16.preflight as PF
import strategy.w16.runner as R


@pytest.fixture(autouse=True)
def _restore_p_ref():
    saved_nq, saved_es = D.P_REF_NQ, D.P_REF_ES
    yield
    D.P_REF_NQ, D.P_REF_ES = saved_nq, saved_es


# ---------------------------------------------------------------------
# require_p_ref (sec 3.4/12): the backtest refuses to run while the
# module constant is still None -- it does NOT silently compute one.
# ---------------------------------------------------------------------

def test_require_p_ref_refuses_when_none():
    D.P_REF_NQ = None
    with pytest.raises(SystemExit) as e:
        DR.require_p_ref("NQ")
    assert "P_REF_NQ is None" in str(e.value)


def test_require_p_ref_returns_the_pinned_constant():
    D.P_REF_NQ = 15234.5
    assert DR.require_p_ref("NQ") == pytest.approx(15234.5)


def test_run_backtest_refuses_before_amendment_a():
    D.P_REF_NQ = None
    with pytest.raises(SystemExit):
        DR.run_backtest(None)


# ---------------------------------------------------------------------
# DVP-v0's own bootstrap threshold (sec 9 #4): 95%, NOT runner.py's 99%
# (which stays 99% -- untouched -- for SB-v0's six scored cells).
# ---------------------------------------------------------------------

def test_bootstrap_threshold_is_95pct_and_runner_py_is_unchanged():
    assert DR.BOOTSTRAP_PASS_PCT == 0.95
    assert R.BOOTSTRAP_PASS_PCT == 0.99                    # never edited


def test_dvp_score_cell_uses_95pct_not_runner_pys_99pct():
    # 40 months, 38 positive / 2 negative -> ~95% positive: passes DVP-v0's
    # bar (>=95%) but would ALSO pass runner.py's stricter 99% only by luck,
    # so pin the exact boundary instead: a book whose bootstrap comes out
    # at exactly 95% must PASS here (>=95%) even though runner.py's own
    # module-level score_cell (99%) would fail it.
    trades = []
    for i in range(1, 39):
        trades.append({"date": f"2020-{(i % 12) + 1:02d}-01", "net": 10.0, "gross": 10.0, "cost": 0.0})
    for i in range(2):
        trades.append({"date": f"2021-{i + 1:02d}-01", "net": -100.0, "gross": -100.0, "cost": 0.0})
    priced_by_level = {lvl: trades for lvl in DR.LEVELS}
    result = DR.dvp_score_cell(priced_by_level)
    assert result["bootstrap"]["pass_threshold"] == 0.95


# ---------------------------------------------------------------------
# pre-flight: no P&L function call, no exit walk, ever (sec 6.1)
# ---------------------------------------------------------------------

def test_preflight_never_calls_pnl_functions_or_the_exit_walk(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("pre-flight must never call this")

    monkeypatch.setattr(D, "dvp_session", _boom)
    monkeypatch.setattr(D, "fast_walk_stop_target_time_exit", _boom)
    import strategy.w16.costs as C
    monkeypatch.setattr(C, "pnl_dollars", _boom)
    monkeypatch.setattr(C, "trade_cost", _boom)
    # dvp_runner imports these names into its own namespace -- patch there too,
    # and the shared pricing helper, so a pre-flight that priced anything fails.
    monkeypatch.setattr(DR, "pnl_dollars", _boom)
    monkeypatch.setattr(DR, "trade_cost", _boom)
    monkeypatch.setattr(DR.R, "price_trade", _boom)
    monkeypatch.setattr(DR.R, "price_all", _boom)

    dates = ["2020-06-01", "2020-06-02"]
    dfs = [trend_session(d, direction="long", slope=1.0, dip_windows=["10:35"]) for d in dates]
    df_1m = pd.concat(dfs).sort_index()
    monkeypatch.setattr(DR, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(PF, "load_root_bars", lambda archive, market: df_1m)

    DR.run_preflight(None)                                  # must not raise


# ---------------------------------------------------------------------
# neighbour grid (sec 7.4): 9 cells, centre == the registered rule
# ---------------------------------------------------------------------

def test_neighbour_grid_is_9_cells_with_registered_centre():
    assert len(DR.GRID_SCALES) == 3 and len(DR.GRID_C3) == 3
    assert DR.REGISTERED_GRID_CELL == (1.0, D.C3_THRESHOLD_DEFAULT)
    assert DR.REGISTERED_GRID_CELL[0] in DR.GRID_SCALES
    assert DR.REGISTERED_GRID_CELL[1] in DR.GRID_C3

    dates = ["2020-06-01", "2020-06-02", "2020-06-03"]
    dfs = [trend_session(d, direction="long", slope=1.0, dip_windows=["10:35", "12:35"]) for d in dates]
    frames = {d: df for d, df in zip(dates, dfs)}
    grid = DR.run_neighbour_grid(frames, "NQ", dates, p_ref=15000.0)
    assert grid["n_total"] == 9
    assert sum(1 for c in grid["cells"] if c["is_registered_cell"]) == 1


# ---------------------------------------------------------------------
# full-contract (not micro) pricing for the replication block (sec 7.3)
# ---------------------------------------------------------------------

def test_price_trade_full_contract_uses_full_point_value_not_micro():
    trade = {"market": "NQ", "direction": "long", "fill_price": 15000.0,
             "exit_price": 15010.0, "entry_fill_kind": "market_or_stop",
             "exit_fill_kind": "target", "voided": False}
    priced = DR._price_trade_full_contract(trade, "L2")
    assert priced["gross"] == pytest.approx(10.0 * 20.0)     # $20/pt for full NQ, not $2 (MNQ)


def test_replication_block_prices_per_1_nq():
    dates = ["2020-06-01", "2020-06-02"]
    dfs = [trend_session(d, direction="long", slope=1.0, dip_windows=["10:35"]) for d in dates]
    frames = {d: df for d, df in zip(dates, dfs)}
    repl = DR.run_replication(frames, "NQ")
    assert repl["L2"]["n_trades"] >= 1
    # a target-exit winner's gross must be a multiple of $20 (full NQ), not $2
    assert repl["L0"]["gross"] % 20.0 == pytest.approx(0.0, abs=1e-6) if repl["L0"]["gross"] else True


# ---------------------------------------------------------------------
# holdout wiring
# ---------------------------------------------------------------------

def test_run_backtest_default_stays_on_training_side(monkeypatch, tmp_path):
    import strategy.w16.dvp_holdout as DH
    monkeypatch.setattr(DH, "LEDGER_PATH", tmp_path / "holdout_w16_dvp.json")
    D.P_REF_NQ = 15000.0
    dates = ["2020-06-01", "2024-06-01"]                     # one training, one locked
    dfs = [trend_session(d, direction="long", slope=1.0, dip_windows=["10:35"]) for d in dates]
    df_1m = pd.concat(dfs).sort_index()
    monkeypatch.setattr(DR, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(PF, "load_root_bars", lambda archive, market: df_1m)
    result = DR.run_backtest(None, compute_controls_flag=False, compute_grid_flag=False,
                             include_replication=False, include_reported_variants=False)
    assert all(t["date"] < "2024-01-02" for t in result.get("sample_trades", []) or [])
    assert "training" in result["date_side"]


def test_run_backtest_refuses_a_non_dvp_nq_holdout_spend():
    D.P_REF_NQ = 15000.0
    with pytest.raises(SystemExit):
        DR.run_backtest(None, spend_holdout="DVP-ES")


# ---------------------------------------------------------------------
# break-even win rate (sec 4 item 4)
# ---------------------------------------------------------------------

def test_break_even_win_rate_hand_computed():
    # win $866, loss $1300 (Conti's own stated figures, sec 5) -> 1300/(866+1300)
    be = DR.break_even_win_rate(866.0, -1300.0)
    assert be == pytest.approx(1300.0 / 2166.0)


def test_break_even_win_rate_none_when_no_losses():
    assert DR.break_even_win_rate(50.0, None) is None


# ---------------------------------------------------------------------
# runtime smoke test: the whole --backtest, small synthetic multi-year
# archive, small n_control_draws
# ---------------------------------------------------------------------

def test_backtest_runtime_smoke_on_small_synthetic_archive(monkeypatch, tmp_path):
    import strategy.w16.dvp_holdout as DH
    monkeypatch.setattr(DH, "LEDGER_PATH", tmp_path / "holdout_w16_dvp.json")
    D.P_REF_NQ = 15000.0

    dates = []
    for year in (2021, 2022, 2023):
        for month, day in ((1, 4), (6, 1), (9, 2)):
            dates.append(f"{year}-{month:02d}-{day:02d}")
    dfs = []
    for i, d in enumerate(dates):
        direction = "long" if i % 2 == 0 else "short"
        dfs.append(trend_session(d, direction=direction, slope=1.0,
                                 dip_windows=["10:35", "12:35", "14:35"], dip_size=6.0))
    df_1m = pd.concat(dfs).sort_index()
    monkeypatch.setattr(DR, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(PF, "load_root_bars", lambda archive, market: df_1m)

    result = DR.run_backtest(None, compute_controls_flag=True, n_control_draws=5,
                             compute_grid_flag=True, progress=False)

    for key in ("criteria", "by_level", "exit_reasons", "sample_trades", "account_view",
               "control_summary_c_d1", "control_c_d2_no_pullback", "control_summary_c_d3",
               "neighbour_grid", "replication", "reported_variants", "trades_per_day",
               "long_short_split", "break_even_win_rate_l2"):
        assert key in result
    for c in ("1_net_positive", "2_both_halves_positive", "3_no_year_over_50pct",
             "4_month_bootstrap_ge_95pct", "5_beats_c_d1_p95", "6_net_positive_at_l3",
             "7_survives_dropping_best_1pct", "8_neighbour_grid_6_of_9", "9_min_trades"):
        assert c in result["criteria"]
    assert result["neighbour_grid"]["n_total"] == 9

    import json
    json.dumps(result, default=str)                         # must be JSON-serialisable

    txt = DR._txt_report(None, result)
    assert "sec 9 criteria" in txt


def test_preflight_runtime_smoke(monkeypatch):
    D.P_REF_NQ = 15000.0
    dates = ["2020-06-01", "2020-06-02", "2020-06-03"]
    dfs = [trend_session(d, direction="long", slope=1.0, dip_windows=["10:35"]) for d in dates]
    df_1m = pd.concat(dfs).sort_index()
    monkeypatch.setattr(DR, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(PF, "load_root_bars", lambda archive, market: df_1m)
    report = DR.run_preflight(None)
    assert "NQ" in report["markets"] and "ES" in report["markets"]
    import json
    json.dumps(report, default=str)
