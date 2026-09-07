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


SUMMARY_COLS = ["symbol", "date", "executions", "round_trips", "shares",
                "buy_shares",
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
         abp=5.0, asp=6.0, gross=1000.0, commission=-12.0, net=988.0,
         round_trips=2):
    return {"symbol": symbol, "date": date, "executions": execs,
            "round_trips": round_trips,
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


def test_my_trade_count_is_round_trips_and_the_fills_sit_beside_it(tmp_path):
    """A strategy's 'trades' are round trips. If mine were executions, the
    column would compare how finely orders were sliced against how many
    decisions a strategy made -- and mine would always look larger."""
    s = write_summary(tmp_path, [sday(execs=31, round_trips=3)])
    b = D.read_summary(s)[("AAA", "2026-03-16")]
    assert b.trades == 3
    assert b.fills == 31
    rows, _ = D.build(s, tmp_path, tmp_path, [])
    out = tmp_path / "cmp.csv"
    D.write_csv(rows, [], out)
    got = list(csv.DictReader(open(out)))[0]
    assert got["mine_trades"] == "3" and got["mine_fills"] == "31"


def test_a_summary_without_round_trips_is_refused(tmp_path):
    p = tmp_path / "old.csv"
    cols = [c for c in SUMMARY_COLS if c != "round_trips"]
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerow(sday())
    with pytest.raises(SystemExit) as e:
        D.read_summary(p)
    assert "round_trips" in str(e.value)


# --- the summary sheets -----------------------------------------------------

def test_utc_entry_times_are_converted_to_ET_before_bucketing(tmp_path):
    """THE bug this would otherwise ship with. The engine writes entry_time in
    UTC ('2026-06-01 08:22:00+00:00'). Bucketed as-is, an 04:22 ET pre-market
    entry lands in the 08:00 block and every bucket shifts four or five hours
    -- and the sheet looks entirely reasonable, just describing a market that
    opens at 13:30."""
    assert D._et_minute("2026-06-01 08:22:00+00:00") == 4 * 60 + 22
    assert D._et_minute("2026-01-15 14:35:00+00:00") == 9 * 60 + 35   # EST
    assert D._et_minute("2026-06-15 13:35:00+00:00") == 9 * 60 + 35   # EDT


def test_a_naive_or_unparseable_timestamp_is_not_guessed():
    """A stamp with no zone could be anything. Assuming UTC would be a four or
    five hour error dressed as a measurement."""
    assert D._et_minute("2026-06-01 08:22:00") is None
    assert D._et_minute("") is None
    assert D._et_minute("not a time") is None


def test_blocks_are_half_open_half_hours():
    assert D.block_label(4 * 60) == "04:00-04:30"
    assert D.block_label(4 * 60 + 29) == "04:00-04:30"
    assert D.block_label(4 * 60 + 30) == "04:30-05:00"
    assert D.block_label(9 * 60 + 31) == "09:30-10:00"


def unit(minute, gross=100.0, cost=1.0, net=99.0, date="2026-03-16"):
    return {"symbol": "AAA", "date": date, "minute": minute,
            "gross": gross, "cost": cost, "net": net}


def test_the_clock_sheet_counts_trades_and_keys_on_entry(tmp_path):
    got = D.by_entry_block({"mine": [unit(9 * 60 + 31), unit(9 * 60 + 45)],
                            "mcl": [unit(4 * 60 + 5)]}, ["mine", "mcl"])
    assert list(got) == ["04:00-04:30", "09:30-10:00"]
    assert got["09:30-10:00"]["mine"].trades == 2
    assert got["09:30-10:00"]["mine"].gross == pytest.approx(200.0)
    assert got["09:30-10:00"]["mcl"].trades == 0
    assert got["04:00-04:30"]["mcl"].trades == 1


def test_units_with_no_resolved_time_sort_last_under_their_own_label():
    got = D.by_entry_block({"mine": [unit(None), unit(9 * 60)]}, ["mine"])
    assert list(got)[-1] == "NO TIME"
    assert got["NO TIME"]["mine"].trades == 1


def test_a_declined_day_counts_in_the_month_but_in_no_time_block(tmp_path):
    """It is a real zero -- a day the strategy was given and did nothing with
    -- so it belongs in the monthly day count. It has no entry, so it belongs
    in no clock bucket. Putting it in one would invent a time."""
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "OK"}})
    s = write_summary(tmp_path, [sday()])
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    months = D.by_month(rows, ["mine", "mcl"])
    assert months["2026-03"]["mcl"].days == 1
    assert months["2026-03"]["mcl"].net == 0.0
    assert D.by_entry_block({"mcl": D.strategy_units(
        tmp_path / "backtest_trades_mcl.csv")}, ["mcl"]) == {}


def test_an_untestable_day_is_in_no_month_total_either(tmp_path):
    """NO BARS is not a zero, so it must not add a day to the count OR a 0.00
    to the sum -- both would understate the strategy's average."""
    write_trades(tmp_path, "mcl", [])
    write_state(tmp_path, "mcl", {"AAA|2026-03-16": {"status": "NO_DATA"}})
    s = write_summary(tmp_path, [sday()])
    rows, _ = D.build(s, tmp_path, tmp_path, ["mcl"])
    m = D.by_month(rows, ["mine", "mcl"])["2026-03"]
    assert m["mcl"].days == 0
    assert m["mine"].days == 1


def test_weekday_buckets_are_named_not_numbered(tmp_path):
    s = write_summary(tmp_path, [sday(date="2026-03-16"),      # Monday
                                 sday(date="2026-03-20")])     # Friday
    rows, _ = D.build(s, tmp_path, tmp_path, [])
    got = D.by_weekday(rows, ["mine"])
    assert set(got) == {"Monday", "Friday"}
    assert got["Monday"]["mine"].days == 1


def test_my_round_trip_costs_are_flipped_to_positive(tmp_path):
    """Same convention as everywhere else in the sheet, so 'gross minus cost'
    is one subtraction in every column."""
    p = tmp_path / "rt.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "date", "entry_et", "exit_et", "fills", "shares",
                    "max_position", "gross_pnl", "commission", "net_pnl",
                    "open_at_end"])
        w.writerow(["AAA", "2026-03-16", "09:31", "09:45", 2, 200, 100,
                    100.0, -2.0, 98.0, 0])
    u = D.my_units(p)[0]
    assert u["minute"] == 9 * 60 + 31
    assert u["cost"] == pytest.approx(2.0)
    assert u["net"] == pytest.approx(u["gross"] - u["cost"])


def test_a_round_trip_with_no_entry_time_survives_as_NO_TIME(tmp_path):
    p = tmp_path / "rt.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "date", "entry_et", "gross_pnl", "commission",
                    "net_pnl"])
        w.writerow(["AAA", "2026-03-16", "", 10.0, -1.0, 9.0])
    assert D.my_units(p)[0]["minute"] is None


def test_trades_on_days_i_never_traded_are_dropped_and_counted(tmp_path):
    """The row set is the spine: a strategy trade on a day Ben did not trade
    has nothing to compare against. But a strategy's artefacts outlive a pair
    list -- the shipped MCL run held 6 trades on 3 symbol-days absent from the
    flex summary. Left in, they sat in the clock sheet and not the monthly one,
    and the two totals disagreed by $102.67 on a workbook whose every
    individual cell was correct."""
    s = write_summary(tmp_path, [sday(symbol="AAA")])
    rows, _ = D.build(s, tmp_path, tmp_path, [])
    units = {"mcl": [unit(9 * 60), {**unit(10 * 60), "symbol": "GONE"}]}
    kept, dropped = D.restrict_units(units, rows)
    assert [u["symbol"] for u in kept["mcl"]] == ["AAA"]
    assert [u["symbol"] for u in dropped["mcl"]] == ["GONE"]


def test_nothing_is_dropped_when_every_trade_has_a_row(tmp_path):
    s = write_summary(tmp_path, [sday(symbol="AAA")])
    rows, _ = D.build(s, tmp_path, tmp_path, [])
    kept, dropped = D.restrict_units({"mcl": [unit(9 * 60)]}, rows)
    assert dropped == {}
    assert len(kept["mcl"]) == 1


def test_raw_cells_keep_full_precision_but_still_blank_an_absence(tmp_path):
    """A spreadsheet stores exact and rounds in the format. Its monthly totals
    are SUMIFS over the day cells, so rounding them to the cent first puts the
    month a few cents off the rows it is summing -- on a sheet showing both."""
    b = D.Block(status="TRADED", trades=1, buy_shares=100, sell_shares=100,
                buy_notional=100 * 5.123456, sell_notional=100 * 6.987654,
                cost=1.234567, gross=186.4198, net=185.185233)
    raw, shown = D.cells(b, raw=True), D.cells(b)
    assert raw[-1] == pytest.approx(185.185233)
    assert shown[-1] == pytest.approx(185.19)
    assert D.cells(D.Block(status="NO BARS"), raw=True) == [""] * len(D.FIELDS)
