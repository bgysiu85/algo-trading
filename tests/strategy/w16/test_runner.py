#!/usr/bin/env python3
"""P&L pricing at L1/L2/L3, per-year and both-halves aggregation, and the
sec 9 scoring criteria that need only one cell's own trade list.
REGISTERED_w16_session_baselines.md sec 4 (costs), sec 5 (what every run
must emit) and sec 9 (the bar to clear)."""
from __future__ import annotations

import pytest

import strategy.w16.runner as R
import strategy.w16.costs as C


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
