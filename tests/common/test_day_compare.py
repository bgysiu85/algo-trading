#!/usr/bin/env python3
"""A day is not a trade, and an absence is not a zero.

Both mistakes produce a full, well-formed spreadsheet. The first prints a price
nobody paid; the second turns a day that could not be tested into a strategy
that broke even. Neither is visible by reading the output.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from common import day_compare as D


TRADE_COLS = ["symbol", "date", "entry_time", "exit_time", "entry_price",
              "exit_price", "qty", "reason", "bars_held", "gross",
              "commission", "net", "cycles", "shares_traded", "adds",
              "max_qty"]


def trade(symbol="AAA", date="2026-03-16", entry=5.0, exit=6.0, qty=100,
          gross=100.0, commission=1.0, net=99.0, cycles=0, adds=0,
          shares_traded=None):
    return {"symbol": symbol, "date": date, "entry_time": "09:31",
            "exit_time": "09:45", "entry_price": entry, "exit_price": exit,
            "qty": qty, "reason": "trail", "bars_held": 14, "gross": gross,
            "commission": commission, "net": net, "cycles": cycles,
            "shares_traded": (2 * qty if shares_traded is None
                              else shares_traded),
            "adds": adds, "max_qty": qty}


def write_trades(tmp_path, name, rows, cols=None):
    p = tmp_path / f"backtest_trades_{name}.csv"
    cols = cols or TRADE_COLS
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


def write_state(tmp_path, name, done):
    p = tmp_path / f"backtest_state_{name}.json"
    p.write_text(json.dumps({"done": done, "trades": []}))
    return p


SUMMARY_COLS = ["symbol", "date", "executions", "shares", "buy_shares",
                "sell_shares", "avg_buy_price", "avg_sell_price",
                "max_position", "gross_pnl", "commission", "net_pnl",
                "in_band"]


def write_summary(tmp_path, rows):
    p = tmp_path / "summary.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


def sday(symbol="AAA", date="2026-03-16", execs=4, buy=1000, sell=1000,
         abp=5.0, asp=6.0, gross=1000.0, commission=-12.0, net=988.0):
    return {"symbol": symbol, "date": date, "executions": execs,
            "shares": buy + sell, "buy_shares": buy, "sell_shares": sell,
            "avg_buy_price": abp, "avg_sell_price": asp,
            "max_position": max(buy, sell), "gross_pnl": gross,
            "commission": commission, "net_pnl": net, "in_band": 1}


# --- the averaging rule -----------------------------------------------------

def test_a_days_average_is_share_weighted_across_its_trades(tmp_path):
    """66% of MCL's symbol-days hold more than one trade -- up to ten -- and
    the entry prices inside one day spread by a median of 18% and a max of 90%.
    The mean of those prices is not the average price paid."""
    write_trades(tmp_path, "mcl", [
        trade(entry=2.0, qty=100),
        trade(entry=9.0, qty=900),
    ])
    b, _ = D.read_trades(tmp_path / "backtest_trades_mcl.csv")
    day = b[("AAA", "2026-03-16")]
    assert day.trades == 2
    assert day.buy_shares == 1000
    assert day.avg_buy_price == pytest.approx(8.30)     # (200 + 8100) / 1000
    assert day.avg_buy_price != pytest.approx(5.50)     # mean of the prices


def test_buy_and_sell_sides_are_averaged_separately(tmp_path):
    write_trades(tmp_path, "mcl", [trade(entry=4.0, exit=7.0, qty=300)])
    day = D.read_trades(tmp_path / "backtest_trades_mcl.csv")[0][("AAA", "2026-03-16")]
    assert (day.buy_shares, day.sell_shares) == (300, 300)
    assert day.avg_buy_price == pytest.approx(4.0)
    assert day.avg_sell_price == pytest.approx(7.0)


def test_pl_and_cost_sum_over_the_days_trades(tmp_path):
    write_trades(tmp_path, "mcl", [
        trade(gross=100.0, commission=1.0, net=99.0),
        trade(gross=-40.0, commission=1.5, net=-41.5),
    ])
    day = D.read_trades(tmp_path / "backtest_trades_mcl.csv")[0][("AAA", "2026-03-16")]
    assert day.gross == pytest.approx(60.0)
    assert day.cost == pytest.approx(2.5)
    assert day.net == pytest.approx(57.5)


# --- entry_price is only the average while a trade is one buy and one sell --

def test_a_scaled_trade_withholds_its_prices_rather_than_averaging(tmp_path):
    """Taking entry_price as the buy price is safe ONLY because scale-out,
    pyramiding and scale-up are off in the engine's default call. Export a
    scaled run and entry_price silently becomes 'the first of several buys'
    while still printing as an average."""
    write_trades(tmp_path, "mcl", [trade(cycles=3, shares_traded=800)])
    blocks, scaled = D.read_trades(tmp_path / "backtest_trades_mcl.csv")
    day = blocks[("AAA", "2026-03-16")]
    assert day.status == "SCALED"
    assert scaled == [("AAA", "2026-03-16")]
    assert D.cells(day) == [""] * len(D.FIELDS)


def test_a_pyramided_trade_is_caught_by_adds_too(tmp_path):
    write_trades(tmp_path, "mcl", [trade(adds=2, shares_traded=500)])
    assert D.read_trades(tmp_path / "backtest_trades_mcl.csv")[1]


def test_shares_traded_disagreeing_with_qty_is_enough_on_its_own():
    """cycles and adds can both be zero on a run whose scaling columns mean
    something else. The share count is the arithmetic check."""
    assert D.single_round_trip(trade(qty=100, shares_traded=200)) is True
    assert D.single_round_trip(trade(qty=100, shares_traded=350)) is False


def test_a_csv_without_scaling_columns_is_treated_as_a_round_trip():
    """MC5 has no scaling mechanic and emits none of these columns. Absence
    means it could not have scaled; a PRESENT column that disagrees is
    believed."""
    assert D.single_round_trip({"symbol": "A", "qty": "100"}) is True


# --- an absence is not a zero ----------------------------------------------

def test_a_declined_session_is_a_real_zero(tmp_path):
    """The strategy saw the bars and took nothing. That IS 0.00 P/L and it
    belongs in a total."""
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK", "trades": 0}})
    blocks, _ = D.strategy_blocks(tmp_path, tmp_path, "mcl")
    b = blocks[("AAA", "2026-03-16")]
    assert b.status == "NO TRADES"
    assert b.has_figures is True
    assert D.cells(b)[-1] == 0.0


def test_a_session_with_no_bars_is_blank_not_zero(tmp_path):
    """Writing 0.00 here makes a day that could not be tested look like a day
    the strategy broke even on, and it then averages into every total."""
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "NO_DATA"}})
    b = D.strategy_blocks(tmp_path, tmp_path, "mcl")[0][("AAA", "2026-03-16")]
    assert b.status == "NO BARS"
    assert D.cells(b) == [""] * len(D.FIELDS)


def test_a_day_with_no_size_to_match_is_blank_too(tmp_path):
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "NO_SIZE"}})
    b = D.strategy_blocks(tmp_path, tmp_path, "mcl")[0][("AAA", "2026-03-16")]
    assert b.status == "NO SIZE"
    assert D.cells(b) == [""] * len(D.FIELDS)


def test_a_pair_absent_from_the_state_file_is_NOT_RUN(tmp_path):
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {})
    s = write_summary(tmp_path, [sday()])
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    assert rows[0]["mcl"].status == "NOT RUN"
    assert D.cells(rows[0]["mcl"]) == [""] * len(D.FIELDS)


def test_an_unknown_engine_status_reads_as_untested_not_as_flat(tmp_path):
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "SOMETHING_NEW"}})
    b = D.strategy_blocks(tmp_path, tmp_path, "mcl")[0][("AAA", "2026-03-16")]
    assert b.status == "NO BARS"


# --- Ben's own side ---------------------------------------------------------

def test_ibkrs_negative_commission_becomes_a_positive_cost(tmp_path):
    """IBKR reports commission as negative-is-paid. Left as-is, 'gross minus
    cost' would be an addition in one column of the sheet and a subtraction in
    every other."""
    s = write_summary(tmp_path, [sday(gross=1000.0, commission=-12.0, net=988.0)])
    b = D.read_summary(s)[("AAA", "2026-03-16")]
    assert b.cost == pytest.approx(12.0)
    assert b.net == pytest.approx(b.gross - b.cost)


def test_an_old_summary_without_the_buy_sell_split_is_refused(tmp_path):
    p = tmp_path / "old.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "date", "executions", "shares", "gross_pnl",
                    "commission", "net_pnl", "in_band"])
        w.writerow(["AAA", "2026-03-16", 4, 2000, 1000, -12, 988, 1])
    with pytest.raises(SystemExit) as e:
        D.read_summary(p)
    assert "buy_shares" in str(e.value)


def test_my_average_prices_survive_the_round_trip(tmp_path):
    s = write_summary(tmp_path, [sday(buy=1000, sell=1000, abp=8.3, asp=9.1)])
    b = D.read_summary(s)[("AAA", "2026-03-16")]
    assert b.avg_buy_price == pytest.approx(8.3)
    assert b.avg_sell_price == pytest.approx(9.1)


# --- the sheet --------------------------------------------------------------

def test_every_traded_day_of_mine_gets_a_row(tmp_path):
    """The row set is Ben's history. A strategy that could not be evaluated
    loses its cells, never the row -- dropping the row would quietly restrict
    the comparison to the days the strategy happened to handle."""
    s = write_summary(tmp_path, [sday(symbol="AAA"), sday(symbol="ZZZ")])
    write_trades(tmp_path, "mcl", [trade(symbol="AAA")])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK"}})
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    assert [r["symbol"] for r in rows] == ["AAA", "ZZZ"]
    assert rows[1]["mcl"].status == "NOT RUN"


def test_the_header_carries_a_status_for_every_source():
    h = D.header(["mcl", "mc5"])
    assert h[:2] == ["symbol", "date"]
    for src in ("mine", "mcl", "mc5"):
        assert f"{src}_status" in h
        assert f"{src}_avg_buy_price" in h


def test_totals_count_only_the_days_a_source_could_be_evaluated_on(tmp_path):
    s = write_summary(tmp_path, [sday(symbol="AAA"), sday(symbol="ZZZ")])
    write_trades(tmp_path, "mcl", [trade(symbol="AAA", net=99.0)])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK"},
                                  "ZZZ|2026-03-16": {"status": "NO_DATA"}})
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    text = "\n".join(D.totals(rows, ["mcl"]))
    assert "NOT like-for-like" in text
    # mine on 2 days, mcl on 1
    assert " mine       " in text and " mcl        " in text


def test_the_coverage_table_names_every_status(tmp_path):
    s = write_summary(tmp_path, [sday()])
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "NO_SIZE"}})
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    text = "\n".join(D.coverage(rows, ["mcl"]))
    for s_ in ("TRADED", "NO TRADES", "NO BARS", "NO SIZE", "NOT RUN"):
        assert s_ in text
    assert "Only NO TRADES is a zero" in text


def test_the_csv_writes_blanks_for_absences(tmp_path):
    s = write_summary(tmp_path, [sday(symbol="ZZZ")])
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"ZZZ|2026-03-16": {"status": "NO_DATA"}})
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    out = tmp_path / "cmp.csv"
    D.write_csv(rows, ["mcl"], out)
    got = list(csv.DictReader(open(out)))[0]
    assert got["mcl_status"] == "NO BARS"
    assert got["mcl_net"] == ""
    assert got["mine_net"] == "988.0"
