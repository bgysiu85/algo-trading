#!/usr/bin/env python3
"""P&L pricing at L1/L2/L3, per-year and both-halves aggregation, and the
sec 9 scoring criteria that need only one cell's own trade list.
REGISTERED_w16_session_baselines.md sec 4 (costs), sec 5 (what every run
must emit) and sec 9 (the bar to clear)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import strategy.w16.runner as R
import strategy.w16.costs as C
import strategy.w16.signals as SIG


def _trade(date, direction, entry, exit_, entry_kind="market_or_stop",
          exit_kind="market_or_stop", market="ES", voided=False):
    return {"date": date, "market": market, "baseline": "B1", "direction": direction,
           "fill_price": entry, "exit_price": exit_, "entry_fill_kind": entry_kind,
           "exit_fill_kind": exit_kind, "voided": voided}


def test_price_trade_long_winner_at_l2():
    t = _trade("2024-06-06", "long", 5000.0, 5010.0, exit_kind="target")
    priced = R.price_trade(t, "L2")
    assert priced["gross"] == pytest.approx(10.0 * C.POINT_VALUE["MES"])
    expected_cost = C.trade_cost("MES", "L2", entry_kind="market_or_stop", exit_kind="target")
    assert priced["cost"] == pytest.approx(expected_cost)
    assert priced["net"] == pytest.approx(priced["gross"] - expected_cost)


def test_price_trade_short_loser_at_l3():
    t = _trade("2024-06-06", "short", 5000.0, 5010.0)   # short loses when price rises
    priced = R.price_trade(t, "L3")
    assert priced["gross"] == pytest.approx(-10.0 * C.POINT_VALUE["MES"])
    assert priced["net"] < priced["gross"]               # costs only ever reduce net


def test_voided_trade_prices_to_zero():
    t = _trade("2024-06-06", "long", 5000.0, 5010.0, voided=True)
    priced = R.price_trade(t, "L2")
    assert priced["gross"] == 0.0 and priced["cost"] == 0.0 and priced["net"] == 0.0


def test_price_all_excludes_voided():
    trades = [_trade("2024-06-06", "long", 100.0, 101.0),
             _trade("2024-06-07", "long", 100.0, 101.0, voided=True)]
    priced = R.price_all(trades, "L2")
    assert len(priced) == 1


def test_summarize_wins_losses_and_drawdown():
    priced = [{"net": 10.0, "gross": 12.0, "cost": 2.0},
             {"net": -5.0, "gross": -3.0, "cost": 2.0},
             {"net": 8.0, "gross": 10.0, "cost": 2.0},
             {"net": -20.0, "gross": -18.0, "cost": 2.0}]
    s = R.summarize(priced)
    assert s["n_trades"] == 4 and s["wins"] == 2 and s["losses"] == 2
    assert s["net"] == pytest.approx(-7.0)
    assert s["largest_loss"] == pytest.approx(-20.0)
    assert s["avg_win"] == pytest.approx(9.0)
    assert s["avg_loss"] == pytest.approx(-12.5)
    # equity path: 10, 5, 13, -7 -> running max 10,10,13,13 -> dd 0,-5,0,-20
    assert s["max_drawdown"] == pytest.approx(-20.0)


def test_both_halves_split_at_median_date():
    priced = [{"date": "2020-01-01", "net": 10.0, "gross": 10.0, "cost": 0.0},
             {"date": "2021-01-01", "net": 10.0, "gross": 10.0, "cost": 0.0},
             {"date": "2022-01-01", "net": -30.0, "gross": -30.0, "cost": 0.0}]
    halves = R.both_halves(priced)
    assert halves["split_date"] == "2021-01-01"
    assert halves["early"]["n_trades"] == 1
    assert halves["late"]["n_trades"] == 2


def test_drop_best_1pct_removes_the_single_best_trade_of_100():
    priced = [{"date": "2024-01-01", "net": 1.0, "gross": 1.0, "cost": 0.0} for _ in range(99)]
    priced.append({"date": "2024-01-01", "net": 1000.0, "gross": 1000.0, "cost": 0.0})
    kept = R.drop_best_pct(priced, pct=0.01)
    assert kept["n_trades"] == 99
    assert kept["net"] == pytest.approx(99.0)


def test_bootstrap_by_month_all_positive_months_always_passes():
    priced = [{"date": f"2020-{m:02d}-01", "net": 5.0} for m in range(1, 13)]
    result = R.bootstrap_by_month(priced, n_draws=200, seed=1)
    assert result["pct_net_positive"] == 1.0
    assert result["pass"] is True


def test_bootstrap_by_month_all_negative_months_never_passes():
    priced = [{"date": f"2020-{m:02d}-01", "net": -5.0} for m in range(1, 13)]
    result = R.bootstrap_by_month(priced, n_draws=200, seed=1)
    assert result["pct_net_positive"] == 0.0
    assert result["pass"] is False


def test_bootstrap_by_month_is_reproducible_given_a_seed():
    priced = [{"date": f"2020-{m:02d}-{d:02d}", "net": (5.0 if (m + d) % 2 else -4.0)}
             for m in range(1, 13) for d in (1, 15)]
    a = R.bootstrap_by_month(priced, n_draws=500, seed=42)
    b = R.bootstrap_by_month(priced, n_draws=500, seed=42)
    assert a == b


def test_score_cell_reports_none_for_uncomputed_criteria():
    priced_by_level = {lvl: [] for lvl in R.LEVELS}
    result = R.score_cell(priced_by_level)
    assert result["criteria"]["5_beats_control"] is None
    assert result["criteria"]["8_neighbour_grid_6_of_9"] is None
    assert result["criteria"]["passes_all_computed"] is False   # empty book can't pass


def test_score_cell_all_positive_book_passes_computed_criteria():
    trades = []
    for y in (2020, 2021, 2022, 2023):
        for i in range(100):
            trades.append({"date": f"{y}-{(i % 12) + 1:02d}-01", "net": 10.0,
                          "gross": 10.0, "cost": 0.0})
    priced_by_level = {lvl: trades for lvl in R.LEVELS}
    result = R.score_cell(priced_by_level)
    c = result["criteria"]
    assert c["1_net_positive"] is True
    assert c["2_both_halves_positive"] is True
    assert c["9_min_trades"] is True
    assert c["7_survives_dropping_best_1pct"] is True


# ---------------------------------------------------------------------
# sec 9 #5 -- control_deterministic (B2's AND-condition: > C-O2 AND > C-O3 p95)
# ---------------------------------------------------------------------

def test_score_cell_control_nets_only_uses_p95():
    trades = [{"date": f"2020-01-{d:02d}", "net": 10.0, "gross": 10.0, "cost": 0.0}
             for d in range(1, 21)]
    priced_by_level = {lvl: trades for lvl in R.LEVELS}
    passing = R.score_cell(priced_by_level, control_nets=[1.0] * 94 + [50.0] * 6)
    failing = R.score_cell(priced_by_level, control_nets=[1.0] * 6 + [500.0] * 94)
    assert passing["criteria"]["5_beats_control"] is True     # net 200 > p95 of that mix
    assert failing["criteria"]["5_beats_control"] is False    # p95 is 500, net is 200


def test_score_cell_control_deterministic_adds_and_condition_for_b2():
    trades = [{"date": f"2020-01-{d:02d}", "net": 10.0, "gross": 10.0, "cost": 0.0}
             for d in range(1, 21)]
    priced_by_level = {lvl: trades for lvl in R.LEVELS}
    # net (200) beats the p95 (100) but NOT the deterministic C-O2 comparator (250)
    result = R.score_cell(priced_by_level, control_nets=[100.0] * 100,
                          control_deterministic=250.0)
    assert result["criteria"]["5_beats_control"] is False
    # now the deterministic comparator is below net -- both conditions hold
    result2 = R.score_cell(priced_by_level, control_nets=[100.0] * 100,
                           control_deterministic=50.0)
    assert result2["criteria"]["5_beats_control"] is True


# ---------------------------------------------------------------------
# sec 5 reporting: exit reasons, sample trades, account view
# ---------------------------------------------------------------------

def test_exit_reason_counts_tallies_by_reason_and_ignores_reasonless_trades():
    priced = [{"exit_reason": "stop"}, {"exit_reason": "stop"}, {"exit_reason": "target"},
             {"no_reason_here": True}]
    counts = R.exit_reason_counts(priced)
    assert counts == {"stop": 2, "target": 1}


def test_sample_trades_returns_all_when_fewer_than_n():
    priced = [{"date": f"2020-01-{d:02d}", "net": 1.0} for d in range(1, 6)]
    out = R.sample_trades(priced, n=20)
    assert len(out) == 5


def test_sample_trades_spreads_evenly_across_a_long_list():
    priced = [{"date": f"2020-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}", "net": float(i)}
             for i in range(200)]
    out = R.sample_trades(priced, n=20)
    assert len(out) == 20
    # evenly spread means the first and last dated trades both appear
    dates = [t["date"] for t in out]
    assert dates == sorted(dates)


def test_account_view_empty_book():
    v = R.account_view([], "B1", "ES")
    assert v["equity_final"] == 0.0 and v["max_drawdown_usd"] == 0.0


def test_account_view_reports_overnight_margin_only_for_b2():
    priced = [{"date": "2020-01-01", "net": 10.0}]
    v_b1 = R.account_view(priced, "B1", "ES")
    v_b2 = R.account_view(priced, "B2", "MES".replace("MES", "ES"))
    assert "overnight_margin" not in v_b1
    assert "overnight_margin" in v_b2
    assert v_b2["overnight_margin"]["initial"] == pytest.approx(2881.37)   # MES, Amendment A


def test_account_view_drawdown_pct_of_account():
    # a winning trade first establishes the peak (1000), then a loss draws the
    # equity down by exactly $2,212.90 = 10% of the $22,129 account
    priced = [{"date": "2020-01-01", "net": 1000.0},
             {"date": "2020-01-02", "net": -2212.9}]
    v = R.account_view(priced, "B1", "ES")
    assert v["max_drawdown_usd"] == pytest.approx(-2212.9)
    assert v["max_drawdown_pct_of_account"] == pytest.approx(10.0, rel=1e-3)


# ---------------------------------------------------------------------
# controls actually run (sec 9 #5) -- small n_draws, synthetic bars
# ---------------------------------------------------------------------

def _synthetic_session(date_str, seed, n=60, base=5000.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{date_str} 09:30", periods=n, freq="1min", tz="America/New_York").tz_convert("UTC")
    walk = np.cumsum(rng.normal(0, 0.5, n))
    close = base + walk
    open_ = np.concatenate([[base], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 0.5, n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.5, n)
    vol = rng.integers(50, 500, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                        "volume": vol, "held_id": 1}, index=idx)


@pytest.fixture
def synthetic_frames():
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2020-01-06", periods=10)]
    return {d: _synthetic_session(d, seed=i) for i, d in enumerate(dates)}


def test_compute_controls_b1_returns_n_draws_nets(synthetic_frames):
    date_list = sorted(synthetic_frames.keys())
    trades = R.generate_b1_trades(synthetic_frames, "ES", date_list)
    ctrl = R.compute_controls("B1", "ES", frames=synthetic_frames, trades=trades,
                              n_draws=5, progress=False)
    assert len(ctrl["random_nets"]) == 5
    assert ctrl["deterministic_net"] is None
    assert all(isinstance(v, float) for v in ctrl["random_nets"])


def test_compute_controls_b2_returns_deterministic_and_random(synthetic_frames):
    date_list = sorted(synthetic_frames.keys())
    trades = R.generate_b2_trades(synthetic_frames, "ES", date_list)
    df_1m = pd.concat([synthetic_frames[d] for d in date_list]).sort_index()
    full_index, price_at = R.training_full_index_price(df_1m, set(date_list))
    ctrl = R.compute_controls("B2", "ES", frames=synthetic_frames, trades=trades,
                              full_index=full_index, price_at=price_at,
                              n_draws=5, progress=False)
    assert len(ctrl["random_nets"]) == 5
    assert isinstance(ctrl["deterministic_net"], float)


def test_compute_controls_b3_returns_n_draws_nets(synthetic_frames):
    date_list = sorted(synthetic_frames.keys())
    flip_counts = R.b3_flip_counts(synthetic_frames, "ES", date_list)
    ctrl = R.compute_controls("B3", "ES", frames=synthetic_frames, flip_counts=flip_counts,
                              n_draws=5, progress=False)
    assert len(ctrl["random_nets"]) == 5
    assert ctrl["deterministic_net"] is None


def test_training_full_index_price_filters_to_given_dates(synthetic_frames):
    date_list = sorted(synthetic_frames.keys())
    df_1m = pd.concat([synthetic_frames[d] for d in date_list]).sort_index()
    keep = set(date_list[:5])
    full_index, price_at = R.training_full_index_price(df_1m, keep)
    from strategy.w16.readback import local_naive_et
    seen_dates = set(local_naive_et(full_index).strftime("%Y-%m-%d"))
    assert seen_dates == keep
    assert len(full_index) == len(price_at)


def test_b3_flip_counts_matches_signal_module(synthetic_frames):
    date_list = sorted(synthetic_frames.keys())
    counts = R.b3_flip_counts(synthetic_frames, "ES", date_list)
    d0 = date_list[0]
    expected = SIG.vwap_flip_session(synthetic_frames[d0], d0, market="ES")["n_flips"]
    assert counts[d0] == expected


def test_run_cell_wires_controls_and_reporting_end_to_end(monkeypatch, synthetic_frames):
    """Regression test: run_cell() itself must build the control inputs and
    thread compute_controls_flag/n_control_draws through to compute_controls
    and score_cell (helper-level unit tests above don't catch a run_cell
    that forgets to call them -- this caught exactly that bug once)."""
    date_list = sorted(synthetic_frames.keys())
    df_1m = pd.concat([synthetic_frames[d] for d in date_list]).sort_index()
    monkeypatch.setattr(R, "load_root_bars", lambda archive, market: df_1m)
    monkeypatch.setattr(R, "session_frames", lambda df: synthetic_frames)

    for baseline in ("B1", "B2", "B3"):
        result = R.run_cell(baseline, "ES", None, n_control_draws=3)
        assert result["baseline"] == baseline
        assert result["control_summary"] is not None
        assert result["control_summary"]["n_draws"] == 3
        assert isinstance(result["exit_reasons"], dict)
        assert isinstance(result["sample_trades"], list)
        assert "equity_final" in result["account_view"]
        assert result["criteria"]["5_beats_control"] in (True, False)

    result = R.run_cell("B1", "ES", None, compute_controls_flag=False)
    assert result["control_summary"] is None
    assert result["criteria"]["5_beats_control"] is None
