"""OWA-v0 pre-flight, pricing, criteria, grid, report, command line and the
one-time holdout run. REGISTERED_w16_open_window.md sec 5-12.
Board W16-0040 sub 4. All bars here are made up."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import open_window as OW
from strategy.w16 import owa_holdout as H
from strategy.w16 import owa_preflight as PF
from strategy.w16 import owa_runner as RUN
from tests.strategy.w16 import owa_fixtures as F


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "LEDGER_PATH", tmp_path / "holdout_w16_owa.json")


@pytest.fixture(scope="module")
def bars():
    return F.random_bars(F.weekdays(45))


@pytest.fixture(scope="module")
def market(bars):
    mk = OW.prepare(bars)
    return mk, [d.date for d in mk.days]


@pytest.fixture(scope="module")
def spanning_bars():
    """30 days either side of the lock date."""
    dates = F.weekdays(30, "2023-11-13") + F.weekdays(30, "2024-01-02")
    assert dates[29] < "2024-01-01" < dates[30]
    return F.random_bars(dates, seed=11)


def _trade(**kw):
    t = {"date": "2015-03-09", "direction": "long", "trigger": "A", "fill_price": 100.0,
         "exit_price": 110.0, "voided": False, "hold_minutes": 5.0, "pre_open": False,
         "exit_reason": "time"}
    t.update(kw)
    return t


# ---------------------------------------------------------------------
# costs and statistics
# ---------------------------------------------------------------------

@pytest.mark.parametrize("vehicle,level,cost", [
    ("MNQ", "L0", 0.0), ("MNQ", "L1", 1.24), ("MNQ", "L2", 2.24), ("MNQ", "L3", 3.24),
    ("NQ", "L2", 14.52)])
def test_price_uses_the_ibkr_table(vehicle, level, cost):
    p = RUN.price([_trade()], level, vehicle)[0]
    gross = 10 * (2.0 if vehicle == "MNQ" else 20.0)
    assert (p["gross"], p["cost"], p["net"]) == pytest.approx((gross, cost, gross - cost))


def test_voided_trades_are_not_priced():
    assert RUN.price([_trade(voided=True)], "L2") == []


def test_runs_and_drawdown():
    nets = [-5.0, 10.0, -1.0, -2.0, -3.0, 4.0, -7.0]
    assert RUN.worst_runs(nets) == {"longest_losing_run": 3, "worst_losing_run_usd": -7.0}
    assert RUN.max_drawdown([-5.0, 2.0]) == -5.0            # the start is a peak
    assert RUN.max_drawdown([10.0, -4.0, -4.0, 20.0]) == -8.0
    assert RUN.max_drawdown([]) == 0.0


def test_stats_worst_day_and_month():
    priced = RUN.price([_trade(date="2015-03-09", exit_price=90.0),
                        _trade(date="2015-03-09", exit_price=95.0),
                        _trade(date="2015-04-01", exit_price=96.0)], "L2")
    s = RUN.stats(priced)
    assert s["worst_day"] == ("2015-03-09", pytest.approx(-34.48))
    assert s["worst_month"][0] == "2015-03" and s["win_rate"] == 0.0
    assert RUN.stats([])["n_trades"] == 0 and RUN.stats([])["worst_day"] is None


def test_money_puts_negatives_in_brackets():
    assert RUN.money(-1234.4) == "($1,234)" and RUN.money(5) == "$5" and RUN.money(None) == "-"


# ---------------------------------------------------------------------
# grid and verdict
# ---------------------------------------------------------------------

@pytest.mark.parametrize("trigger,knob,values", [
    ("A", "big_mult", {1.25, 1.5, 1.75}), ("B", "big_mult", {1.25, 1.5, 1.75}),
    ("C", "macd_k", {2, 3, 4})])
def test_grid_cells(trigger, knob, values):
    cells = RUN.grid_cells(trigger)
    assert len(cells) == 9
    assert {c[0][knob] for c in cells} == values
    assert {c[0]["trail"] for c in cells} == {2.0, 2.5, 3.0}
    assert [p == OW.REGISTERED for _, p in cells] == [False] * 4 + [True] + [False] * 4


def test_grid_registered_cell_equals_the_primary_book(market):
    mk, dates = market
    grid = RUN.run_grid(mk, "C", "15", dates)
    book = OW.simulate_book(mk, OW.compute_signals(mk, "15"), "C", dates)
    middle = next(r for r in grid["cells"] if r["is_registered_cell"])
    assert middle["n_trades"] == len(book["trades"]) > 0
    assert middle["net"] == pytest.approx(sum(t["net"] for t in RUN.price(book["trades"], "L2")))
    assert len({r["net"] for r in grid["cells"]}) > 1


def test_verdict():
    good = {k: True for k in RUN.CRITERIA_TEXT}
    assert RUN.verdict(good, 300, True) == "PASS"
    assert RUN.verdict(dict(good, **{"5_beats_control": False, "1_net_positive": False}),
                       400, True) == "FAIL (criteria 1, 5)"
    assert RUN.verdict(dict(good, **{"9_min_trades": False}), 299, True).startswith("NOT READ")
    assert RUN.verdict(good, 400, False).startswith("INCOMPLETE")


def test_a_full_cell_report(market):
    mk, dates = market
    cell = RUN.run_cell(mk, "C", "15", dates, n_draws=40)
    assert cell["verdict"].startswith("INCOMPLETE")         # 40 draws is a quick look
    assert set(cell["criteria"]) >= set(RUN.CRITERIA_TEXT)
    assert cell["criteria"]["5_beats_control"] == (
        cell["levels"]["MNQ"]["L2"]["net"] > cell["controls"]["C1"]["p95"])
    assert set(cell["reported_books"]) == {"long_only", "short_only", "signal_close_fills",
                                           "no_daily_cap"}
    net = [cell["levels"]["MNQ"][lvl]["net"] for lvl in ("L0", "L1", "L2", "L3")]
    assert net == sorted(net, reverse=True)
    assert sum(s["n_trades"] for s in cell["by_year"].values()) == cell["n_trades"]
    assert len(cell["sample_trades"]) == min(20, cell["n_trades"])
    text = "\n".join(RUN.cell_text(cell))
    text.encode("ascii")                                    # Windows console safe
    for piece in ("CELL C-15", "C-1 random later timing", "neighbour grid", "20 sample trades"):
        assert piece in text


def test_run_backtest_covers_six_cells_in_table_order(market):
    mk, dates = market
    report = RUN.run_backtest(mk, dates, "training", controls=False, grid=False)
    assert list(report["cells"]) == ["A-1H", "B-1H", "C-1H", "A-15", "B-15", "C-15"]
    assert list(report["all_books"]) == ["All-1H", "All-15"]
    assert report["passing_cells"] == [] and report["complete"] is False
    assert all(c["criteria"]["5_beats_control"] is None for c in report["cells"].values())
    RUN.backtest_text(report).encode("ascii")
    json.dumps(report, default=str)


# ---------------------------------------------------------------------
# pre-flight (G2)
# ---------------------------------------------------------------------

def test_preflight_reads_no_exit_and_no_pnl(market, monkeypatch):
    mk, dates = market
    monkeypatch.setattr(OW, "walk_exit", lambda *a, **k: pytest.fail("pre-flight read an exit"))
    report = PF.run_preflight(mk, dates, "training")
    assert list(report["cells"]) == ["A-1H", "B-1H", "C-1H", "A-15", "B-15", "C-15"]
    assert not hasattr(PF, "pnl_dollars") and not hasattr(PF, "ibkr_round_trip")
    flat = json.dumps(report)
    for word in ('"net"', '"gross"', "exit_price", "win_rate"):
        assert word not in flat
    PF.text_report(report).encode("ascii")


def test_preflight_counts_agree_with_the_book(market):
    mk, dates = market
    report = PF.run_preflight(mk, dates, "training")
    tradable = sum(d.status == "tradable" for d in mk.days)
    year = report["common_by_year"]["2015"]
    assert year["tradable"] == tradable and year["trading_days"] == len(mk.days)
    assert year["trading_days"] == year["tradable"] + year["skipped"] + year["warmup"]
    for name, cell in report["cells"].items():
        trigger, filt = name.split("-")
        book = OW.simulate_book(mk, OW.compute_signals(mk, filt), trigger, dates)
        first_days = {t["date"] for t in book["trades"]}
        assert cell["trades_lower_bound"] == len(first_days)
        assert len(book["trades"]) <= cell["trades_upper_bound"]
        t = cell["totals"]
        assert t["first_fills_long"] + t["first_fills_short"] == len(first_days)
        assert t["first_fills_pre_open"] + t["first_fills_rth"] == len(first_days)
        assert cell["read_status"].startswith("NOT READ") == (cell["trades_upper_bound"] < 300)


# ---------------------------------------------------------------------
# the training cut and the command line
# ---------------------------------------------------------------------

def test_training_cut_drops_every_bar_from_2024(spanning_bars):
    cut = RUN.training_cut(spanning_bars)
    local = cut.index.tz_convert(OW.ET)
    assert local.max() < pd.Timestamp("2024-01-01", tz=OW.ET)
    assert 0 < len(cut) < len(spanning_bars)
    edge = pd.DataFrame({"x": [1, 2]}, index=pd.DatetimeIndex(
        [pd.Timestamp("2023-12-31 23:59", tz=OW.ET), pd.Timestamp("2024-01-01 00:00", tz=OW.ET)]
    ).tz_convert("UTC"))
    assert RUN.training_cut(edge)["x"].tolist() == [1]


@pytest.fixture
def cli(monkeypatch, spanning_bars):
    monkeypatch.setattr(RUN, "load_nq", lambda archive: spanning_bars)
    seen = []
    real = OW.prepare

    def spy(df):
        seen.append(df.index.tz_convert(OW.ET).max())
        return real(df)

    monkeypatch.setattr(OW, "prepare", spy)
    return seen


def test_cli_preflight_never_sees_a_locked_bar(cli, tmp_path):
    out = tmp_path / "pre.json"
    assert RUN.main(["--preflight", "--archive", str(tmp_path), "--out", str(out)]) == 0
    assert max(cli).year == 2023
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["last_date"] < "2024-01-01"
    assert "NO P&L" in out.with_suffix(".txt").read_text(encoding="utf-8")
    assert not H.LEDGER_PATH.exists()


def test_cli_backtest_never_sees_a_locked_bar(cli, tmp_path):
    out = tmp_path / "bt.json"
    assert RUN.main(["--backtest", "--archive", str(tmp_path), "--out", str(out),
                     "--skip-controls", "--skip-grid"]) == 0
    assert max(cli).year == 2023
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["last_date"] < "2024-01-01" and report["complete"] is False
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("argv", [
    ["--spend-holdout", "A-1H", "--skip-controls"],
    ["--spend-holdout", "A-1H", "--skip-grid"],
    ["--spend-holdout", "A-1H", "--n-control-draws", "10"],
    ["--spend-holdout", "A-1H", "--limit", "5"],
    ["--spend-holdout", "A-1H"],                              # no --out
    ["--preflight", "--skip-grid"],
    ["--backtest", "--limit", "5"],
    ["--backtest", "--spend-holdout", "A-1H"],
    ["--backtest", "--n-control-draws", "0"],
    ["--spend", "A-1H"],
])
def test_cli_refuses_narrowing_the_holdout(argv, monkeypatch, tmp_path):
    monkeypatch.setattr(RUN, "load_nq", lambda archive: pytest.fail("data was loaded"))
    if argv != ["--spend-holdout", "A-1H"]:
        argv = argv + ["--out", str(tmp_path / "o.json")]
    with pytest.raises(SystemExit) as stop:
        RUN.main(argv)
    assert stop.value.code != 0
    assert not H.LEDGER_PATH.exists()


# ---------------------------------------------------------------------
# the holdout run (sec 9)
# ---------------------------------------------------------------------

def _fake_training(passing, per_trade=1.0):
    def fake(mk, dates, label, **kwargs):
        assert max(dates) < "2024-01-01" and mk.days[-1].date < "2024-01-01"
        assert kwargs.keys() <= {"log"}, "the holdout's training run must not be narrowed"
        cells = {n: {"levels": {"MNQ": {"L2": {"avg_net_per_trade": per_trade}}}} for n in passing}
        return {"passing_cells": list(passing), "cells": cells}
    return fake


def test_no_passing_cell_leaves_the_holdout_unspent(spanning_bars, monkeypatch):
    monkeypatch.setattr(RUN, "run_backtest", _fake_training([]))
    with pytest.raises(H.HoldoutRefused):
        RUN.run_holdout(spanning_bars, ["C-15"])
    assert not H.LEDGER_PATH.exists()


@pytest.mark.parametrize("named", [["C-15"], ["C-15", "B-15", "A-15"], ["A-1H"]])
def test_naming_anything_but_every_passing_cell_spends_nothing(spanning_bars, monkeypatch, named):
    monkeypatch.setattr(RUN, "run_backtest", _fake_training(["C-15", "B-15"]))
    with pytest.raises(H.HoldoutRefused):
        RUN.run_holdout(spanning_bars, named)
    assert not H.LEDGER_PATH.exists()


def test_holdout_runs_once_for_every_passing_cell(spanning_bars, monkeypatch):
    monkeypatch.setattr(RUN, "run_backtest", _fake_training(["C-15", "B-15"]))
    real = OW.prepare

    def spy(df):
        if df.index.tz_convert(OW.ET).max().year >= 2024:
            assert H.LEDGER_PATH.exists(), "locked bars read before the ledger was written"
        return real(df)

    monkeypatch.setattr(OW, "prepare", spy)
    report = RUN.run_holdout(spanning_bars, ["B-15", "C-15"])
    assert json.loads(H.LEDGER_PATH.read_text(encoding="utf-8"))["cells"] == ["C-15", "B-15"]
    assert list(report["cells"]) == ["C-15", "B-15"]
    assert report["first_date"] >= "2024-01-02"
    for cell in report["cells"].values():
        for absent in ("verdict", "criteria", "grid", "reported_books"):
            assert absent not in cell
        assert cell["controls"]["C1"]["n_draws"] == 1000
        assert min(cell["by_year"]) >= "2024"
        assert set(cell["holdout_bar"]["checks"]) == {
            "net_positive", "per_trade_at_least_a_third_of_training", "beats_c1_p95",
            "net_positive_at_l3"}
    RUN.holdout_text(report).encode("ascii")
    with pytest.raises(H.HoldoutRefused):
        RUN.run_holdout(spanning_bars, ["B-15", "C-15"])


@pytest.mark.parametrize("net,per_trade,p95,l3,cleared", [
    (100.0, 1.0, 50.0, 10.0, True),
    (-1.0, 1.0, -50.0, 10.0, False),
    (100.0, 0.9, 50.0, 10.0, False),        # under a third of training's $3
    (100.0, 1.0, 100.0, 10.0, False),       # must beat p95, not tie it
    (100.0, 1.0, 50.0, 0.0, False)])
def test_holdout_bar(net, per_trade, p95, l3, cleared):
    cell = {"levels": {"MNQ": {"L2": {"net": net, "avg_net_per_trade": per_trade},
                               "L3": {"net": l3}}}, "controls": {"C1": {"p95": p95}}}
    train = {"levels": {"MNQ": {"L2": {"avg_net_per_trade": 3.0}}}}
    assert RUN.holdout_bar(cell, train)["cleared"] is cleared
