"""Tests for strategy/swing/report_layer.py (W07-0012 subitem 6).
Offline: synthetic universe/prices/intraday store, no network, no real
var/swing_pit needed."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from strategy.swing import fill_engine as F
from strategy.swing import pit_universe as P
from strategy.swing import reversal_v0 as R
from strategy.swing import report_layer as L

D = dt.date


def test_self_test_passes():
    lines = L.self_test()
    assert lines and "passed" in lines[0]


# --------------------------------------------------------------------------
# friction / financing
# --------------------------------------------------------------------------

def test_friction_measured_is_flat_and_index_independent():
    assert L.friction_bps("measured", "open", "sp500") == L.MEASURED_BPS
    assert L.friction_bps("measured", "close", "sp400") == L.MEASURED_BPS
    assert L.friction_bps("measured", "midday", None) == L.MEASURED_BPS


def test_friction_bucket_adds_commission_by_index():
    assert L.friction_bps("bucket", "open", "sp500") == pytest.approx(7.98 + 1.7)
    assert L.friction_bps("bucket", "close", "sp400") == pytest.approx(2.96 + 3.3)
    # unknown/missing index falls back to the conservative (mid-cap) figure
    assert L.friction_bps("bucket", "midday", None) == pytest.approx(3.61 + 3.3)


def test_friction_stress_is_2x_the_bucket_total():
    bucket_total = L.friction_bps("bucket", "midday", "sp500")
    assert L.friction_bps("stress", "midday", "sp500") == pytest.approx(2 * bucket_total)


def test_friction_rejects_unknown_level():
    with pytest.raises(ValueError):
        L.friction_bps("wrong", "open", "sp500")


def test_financing_bps_linear_in_trading_days():
    assert L.financing_bps(2) == pytest.approx(1.98)
    assert L.financing_bps(10) == pytest.approx(9.9)
    assert L.financing_bps(20) == pytest.approx(19.8)


def test_commission_bps_for_unknown_index_uses_conservative_fallback():
    assert L.commission_bps_for(None) == L.DEFAULT_COMMISSION_BPS
    assert L.commission_bps_for("nope") == L.DEFAULT_COMMISSION_BPS
    assert L.DEFAULT_COMMISSION_BPS == max(L.COMMISSION_BPS_BY_INDEX.values())


# --------------------------------------------------------------------------
# code_index_on
# --------------------------------------------------------------------------

def make_universe():
    cal = [D(2026, 1, 5) + dt.timedelta(days=i) for i in range(14)]
    spells = (
        P.Spell("sp500", "AAA", "Alpha", cal[0], cal[-1], True, False),
        P.Spell("sp500", "BBB", "Beta", cal[0], cal[-1], True, False),
        P.Spell("sp400", "CCC", "Gamma", cal[0], cal[-1], True, False),
    )
    return R.Universe(spells=spells, n_suspects_excluded=0), cal


def test_code_index_on():
    universe, cal = make_universe()
    assert L.code_index_on(universe, "AAA", cal[3]) == "sp500"
    assert L.code_index_on(universe, "CCC", cal[3]) == "sp400"
    assert L.code_index_on(universe, "ZZZ", cal[3]) is None


# --------------------------------------------------------------------------
# universe_eligible_bucket_return: pick-independent, cached
# --------------------------------------------------------------------------

def test_benchmark_is_equal_weight_over_priced_eligible_codes_only():
    universe, cal = make_universe()
    store = {
        "AAA": {(cal[3], "midday"): (10.0, "HIT"), (cal[5], "midday"): (11.0, "HIT")},
        "BBB": {(cal[3], "midday"): (20.0, "HIT"), (cal[5], "midday"): (19.0, "HIT")},
        # CCC: no file -- excluded, not treated as zero
    }
    bench = L.universe_eligible_bucket_return(universe, store, cal[3], cal[5], "midday")
    expected = ((11.0 / 10.0 - 1.0) + (19.0 / 20.0 - 1.0)) / 2
    assert bench == pytest.approx(expected)


def test_benchmark_none_when_nothing_priced():
    universe, cal = make_universe()
    assert L.universe_eligible_bucket_return(universe, {}, cal[3], cal[5], "midday") is None


def test_benchmark_cache_is_pick_independent_and_hit_on_second_call():
    universe, cal = make_universe()
    store = {"AAA": {(cal[3], "midday"): (10.0, "HIT"), (cal[5], "midday"): (11.0, "HIT")}}
    cache: dict = {}
    b1 = L.universe_eligible_bucket_return(universe, store, cal[3], cal[5], "midday", cache=cache)
    assert len(cache) == 1
    b2 = L.universe_eligible_bucket_return(universe, store, cal[3], cal[5], "midday", cache=cache)
    assert b1 == b2 and len(cache) == 1  # second call reused the cache, did not grow it


# --------------------------------------------------------------------------
# score_trades
# --------------------------------------------------------------------------

def build_scored():
    universe, cal = make_universe()
    store = {
        "AAA": {(cal[3], "midday"): (10.0, "HIT"), (cal[5], "midday"): (11.0, "HIT")},
        "BBB": {(cal[3], "midday"): (20.0, "HIT"), (cal[5], "midday"): (19.0, "HIT")},
    }
    picks = {cal[2]: ["AAA", "BBB"]}
    trades, unfilled = F.build_trades(picks, cal, store, "midday", n=2)
    rows, n_no_bench = L.score_trades(trades, universe, store)
    return universe, cal, store, trades, rows, n_no_bench


def test_score_trades_net_and_market_relative_cash_funded():
    universe, cal, store, trades, rows, n_no_bench = build_scored()
    assert n_no_bench == 0
    aaa = next(r for r in rows if r["code"] == "AAA")
    assert aaa["index"] == "sp500"
    expected_net = 0.1 - L.friction_bps("bucket", "midday", "sp500") / 10000.0
    assert aaa["net_bucket"] == pytest.approx(expected_net)
    bench = L.universe_eligible_bucket_return(universe, store, cal[3], cal[5], "midday")
    assert aaa["mr_bucket"] == pytest.approx(expected_net - bench)


def test_score_trades_levered_doubles_gross_and_cost_adds_financing_once():
    universe, cal, store, trades, rows, _ = build_scored()
    aaa = next(r for r in rows if r["code"] == "AAA")
    expected_levered = (2 * 0.1
                        - 2 * L.friction_bps("bucket", "midday", "sp500") / 10000.0
                        - L.financing_bps(2) / 10000.0)
    assert aaa["levered_net_bucket"] == pytest.approx(expected_levered)


def test_score_trades_no_benchmark_counted_not_dropped():
    universe, cal = make_universe()
    store = {"AAA": {(cal[3], "midday"): (10.0, "HIT"), (cal[5], "midday"): (11.0, "HIT")}}
    picks = {cal[2]: ["AAA"]}
    trades, _ = F.build_trades(picks, cal, store, "midday", n=2)
    # entry/exit both eligible on cal[3]/cal[5], but ONLY AAA has a price at
    # all -- so the "universe" benchmark still resolves from AAA itself here;
    # force a no-benchmark case by asking about dates nothing is priced at
    rows, n_no_bench = L.score_trades(trades, universe, {})
    assert len(rows) == 1
    assert rows[0]["mr_bucket"] is None and rows[0]["net_bucket"] is not None
    assert n_no_bench == 1


# --------------------------------------------------------------------------
# weighted aggregation helpers
# --------------------------------------------------------------------------

def test_aggregate_weighted_mean_and_total():
    rows = [{"f": 0.02, "weight": 1.0}, {"f": 0.04, "weight": 0.5}, {"f": None, "weight": 1.0}]
    agg = L.aggregate(rows, "f")
    assert agg["n"] == 2
    assert agg["total"] == pytest.approx(0.02 * 1.0 + 0.04 * 0.5)
    assert agg["mean"] == pytest.approx(agg["total"] / 1.5)


def test_aggregate_empty_is_none():
    assert L.aggregate([], "f") == {"n": 0, "mean": None, "total": None}


def test_by_half_splits_at_median_entry_date():
    cal = [D(2026, 1, 5) + dt.timedelta(days=i) for i in range(10)]
    rows = [{"entry_date": cal[i], "code": "AAA", "f": 0.01, "weight": 1.0}
           for i in range(10)]
    result = L.by_half(rows, "f")
    assert result["first_half"]["n"] + result["second_half"]["n"] == 10
    assert result["median_date"] == cal[5].isoformat()


def test_by_half_falls_back_to_index_split_when_all_same_date():
    cal = [D(2026, 1, 5)]
    rows = [{"entry_date": cal[0], "code": f"C{i}", "f": 0.01, "weight": 1.0}
           for i in range(4)]
    result = L.by_half(rows, "f")
    assert result["first_half"]["n"] + result["second_half"]["n"] == 4
    assert result["second_half"]["n"] > 0


def test_by_year_groups_correctly():
    rows = [{"entry_date": D(2020, 6, 1), "f": 0.01, "weight": 1.0},
           {"entry_date": D(2021, 6, 1), "f": -0.02, "weight": 1.0}]
    result = L.by_year(rows, "f")
    assert set(result) == {2020, 2021}
    assert result[2020]["mean"] == pytest.approx(0.01)


# --------------------------------------------------------------------------
# drop_top_n
# --------------------------------------------------------------------------

def test_drop_top_n_returns_na_when_too_few_codes():
    rows = [{"code": "AAA", "f": 0.05, "weight": 1.0},
           {"code": "BBB", "f": 0.02, "weight": 1.0}]
    assert L.drop_top_n(rows, "f", 5) == "n/a"
    assert L.drop_top_n(rows, "f", 2) == "n/a"


def test_drop_top_n_drops_the_biggest_weighted_contributor():
    rows = [{"code": "AAA", "f": 0.10, "weight": 1.0},
           {"code": "BBB", "f": 0.01, "weight": 1.0},
           {"code": "CCC", "f": -0.02, "weight": 1.0}]
    dropped = L.drop_top_n(rows, "f", 1)
    assert dropped != "n/a"
    assert dropped["n"] == 2  # AAA removed
    assert dropped["mean"] == pytest.approx((0.01 + -0.02) / 2)


# --------------------------------------------------------------------------
# cluster_bootstrap_by_month
# --------------------------------------------------------------------------

def test_cluster_bootstrap_all_positive_is_100_pct():
    rows = [{"entry_date": D(2026, 1, 10), "f": 0.01, "weight": 1.0},
           {"entry_date": D(2026, 2, 10), "f": 0.02, "weight": 1.0}]
    result = L.cluster_bootstrap_by_month(rows, "f", resamples=100, seed=5)
    assert result["pct_positive"] == 100.0
    assert result["months"] == 2


def test_cluster_bootstrap_reproducible_with_same_seed():
    rows = [{"entry_date": D(2026, 1, 10), "f": 0.01, "weight": 1.0},
           {"entry_date": D(2026, 2, 10), "f": -0.03, "weight": 1.0},
           {"entry_date": D(2026, 3, 10), "f": 0.02, "weight": 1.0}]
    a = L.cluster_bootstrap_by_month(rows, "f", resamples=200, seed=42)
    b = L.cluster_bootstrap_by_month(rows, "f", resamples=200, seed=42)
    assert a == b


def test_cluster_bootstrap_empty_is_none():
    result = L.cluster_bootstrap_by_month([], "f", resamples=10, seed=1)
    assert result["pct_positive"] is None and result["months"] == 0


# --------------------------------------------------------------------------
# random_decile_picks / random_decile_control
# --------------------------------------------------------------------------

def test_random_decile_picks_matches_actual_decile_size():
    universe, cal = make_universe()
    picks = {cal[2]: ["AAA"], cal[3]: []}
    rnd = L.random_decile_picks(universe, cal, picks, None, seed=3)
    assert len(rnd[cal[2]]) == 1
    assert rnd[cal[2]][0] in {"AAA", "BBB", "CCC"}
    assert rnd[cal[3]] == []


def test_random_decile_control_reproducible_and_shaped():
    universe, cal = make_universe()
    store = {
        "AAA": {(cal[i], "midday"): (100 + i, "HIT") for i in range(len(cal))},
        "BBB": {(cal[i], "midday"): (50 - i * 0.1, "HIT") for i in range(len(cal))},
        "CCC": {(cal[i], "midday"): (30 + i * 0.05, "HIT") for i in range(len(cal))},
    }
    picks = {cal[2]: ["AAA"]}
    rc1 = L.random_decile_control(universe, cal, store, picks, "midday", 2,
                                  draws=8, seed=9)
    rc2 = L.random_decile_control(universe, cal, store, picks, "midday", 2,
                                  draws=8, seed=9)
    assert rc1 == rc2
    assert rc1["draws"] == 8


def test_random_decile_control_no_result_when_nothing_priced():
    universe, cal = make_universe()
    picks = {cal[2]: ["AAA"]}
    rc = L.random_decile_control(universe, cal, {}, picks, "midday", 2, draws=4, seed=1)
    assert rc["draws_with_a_result"] == 0
    assert rc["mean_of_draw_means"] is None


# --------------------------------------------------------------------------
# run_cell / ensemble_cell / run_grid
# --------------------------------------------------------------------------

def make_full_pit():
    universe, cal = make_universe()
    prices = {
        "AAA": {cal[i]: 100 + i for i in range(len(cal))},
        "BBB": {cal[i]: 50 - i * 0.2 for i in range(len(cal))},
        "CCC": {cal[i]: 30 + i * 0.1 for i in range(len(cal))},
    }
    store = {
        code: {(cal[i], b): (px[cal[i]], "HIT") for i in range(len(cal)) for b in R.BUCKETS}
        for code, px in prices.items()
    }
    return universe, cal, prices, store


def test_run_cell_shape():
    universe, cal, prices, store = make_full_pit()
    cell = L.run_cell(universe, prices, cal, store, k=5, n=2, bucket="midday")
    assert cell["k"] == 5 and cell["n"] == 2 and cell["bucket"] == "midday"
    assert "cash_funded" in cell and "levered_2x1" in cell
    for lvl in L.FRICTION_LEVELS:
        assert lvl in cell["cash_funded"]["by_level"]


def test_ensemble_cell_pools_sleeves_at_one_third_weight():
    universe, cal, prices, store = make_full_pit()
    sleeves = [L.run_cell(universe, prices, cal, store, k=5, n=n, bucket="midday")
              for n in R.N_VALUES]
    ens = L.ensemble_cell(sleeves)
    assert ens["n_values"] == sorted(R.N_VALUES)
    total_rows = sum(len(s["rows"]) for s in sleeves)
    assert len(ens["rows"]) == total_rows
    if ens["rows"]:
        assert all(abs(r["weight"] - 1.0 / 3.0) < 1e-9 for r in ens["rows"])


def test_run_grid_has_every_cell_and_ensemble():
    universe, cal, prices, store = make_full_pit()
    grid = L.run_grid(universe, prices, cal, store)
    assert len(grid["cells"]) == len(R.K_VALUES) * len(R.BUCKETS) * len(R.N_VALUES)
    assert len(grid["ensembles"]) == len(R.K_VALUES) * len(R.BUCKETS)
    assert (5, "midday", 5) in grid["cells"]
    assert (5, "midday") in grid["ensembles"]


# --------------------------------------------------------------------------
# coverage_report
# --------------------------------------------------------------------------

def write_suspects(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                   "verdict", "in_window_rows", "expected_rows"])


def test_coverage_report_guards_and_shape(tmp_path: Path):
    universe, cal, prices, store = make_full_pit()
    picks_by_k = {k: R.daily_picks(universe, prices, cal, k) for k in R.K_VALUES}
    suspects_path = tmp_path / R.SUSPECTS_NAME
    write_suspects(suspects_path)
    cov = L.coverage_report(universe, prices, cal, picks_by_k, suspects_path, tmp_path)
    assert cov["hindsight_guard_rejections"] == 0
    assert cov["n_codes_covered"] == 3
    assert set(cov["by_k"]) == set(R.K_VALUES)
    assert cov["first_last_date_by_code"]["AAA"] == (cal[0].isoformat(), cal[-1].isoformat())


# --------------------------------------------------------------------------
# to_json_safe / write_scored_rows_csv / format_report
# --------------------------------------------------------------------------

def test_to_json_safe_strips_rows_and_is_json_dumpable(tmp_path: Path):
    import json
    universe, cal, prices, store = make_full_pit()
    grid = L.run_grid(universe, prices, cal, store)
    result = {"pit_dir": str(tmp_path), "index": None,
             "window": [cal[0].isoformat(), cal[-1].isoformat()],
             "grid": grid, "coverage": {"caveat": "n/a"},
             "random_decile_control": {(5, "midday", 5):
                                       {"draws": 1, "draws_with_a_result": 0,
                                        "mean_of_draw_means": None,
                                        "pct_draws_positive": None}}}
    safe = L.to_json_safe(result)
    text = json.dumps(safe)  # must not raise
    assert "K5_midday_N5" in safe["grid"]["cells"]
    assert "rows" not in safe["grid"]["cells"]["K5_midday_N5"]
    assert "n_trades" in safe["grid"]["cells"]["K5_midday_N5"]


def test_write_scored_rows_csv_roundtrip(tmp_path: Path):
    universe, cal, store, trades, rows, _ = build_scored()
    out = tmp_path / "scored.csv"
    L.write_scored_rows_csv(out, rows)
    read_rows = list(csv.DictReader(out.open(newline="", encoding="utf-8")))
    assert len(read_rows) == 2
    assert {r["code"] for r in read_rows} == {"AAA", "BBB"}
    assert read_rows[0]["index"] in ("sp500", "sp400")


def test_format_report_mentions_key_sections():
    universe, cal, prices, store = make_full_pit()
    grid = L.run_grid(universe, prices, cal, store)
    result = {
        "window": [cal[0].isoformat(), cal[-1].isoformat()],
        "grid": grid,
        "random_decile_control": {},
        "coverage": {"hindsight_guard_rejections": 0, "hindsight_guard_pairs_checked": 0,
                    "suspect_leak_guard_spells_confirmed_absent": 0, "n_codes_covered": 3,
                    "by_k": {}, "caveat": "n/a"},
    }
    text = L.format_report(result, index="sp500")
    assert "DEPLOYED CELL" in text
    assert "FULL K x N x BUCKET GRID" in text
    assert "COVERAGE / COUNTS" in text
    assert "index=sp500" in text


# --------------------------------------------------------------------------
# CLI gate
# --------------------------------------------------------------------------

def test_main_missing_membership_exits(tmp_path: Path):
    rc = L.main(["run", "--pit-dir", str(tmp_path / "nope")])
    assert rc == 2


def test_main_without_stage_requires_run():
    with pytest.raises(SystemExit):
        L.main([])
