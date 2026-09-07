#!/usr/bin/env python3
"""What a real trade log has to survive before it can be used as evidence.

The Flex report is the only non-hindsight data in this project, so a parsing
mistake here does not produce a slightly wrong backtest -- it silently corrupts
the one clean out-of-sample set there is. Every test below pins something that
returned a PLAUSIBLE wrong answer during development rather than an error.

The real report is not committed: it carries the account number and per-fill
execution IDs. Fixtures are synthetic and are built to reproduce the exact
shapes that broke things.
"""
from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import pytest

from common import flex

HEADER = ["Symbol", "TradeDate", "DateTime", "Quantity", "TradePrice",
          "IBCommission", "FifoPnlRealized", "Buy/Sell", "AssetClass",
          "LevelOfDetail", "TradeID"]

_ID = itertools.count(1)


def write_csv(path, rows, header=HEADER):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return str(path)


def row(sym="AAA", trade_date="2026-08-04", dt="2026-08-04 18:00:00",
        qty=100, px=5.0, comm=-1.0, pnl=0.0, side="BUY",
        asset="STK", lod="EXECUTION", trade_id=None):
    return [sym, trade_date, dt, qty, px, comm, pnl, side, asset, lod,
            trade_id if trade_id is not None else next(_ID)]


# --- the timezone trap ------------------------------------------------------

def test_pairs_use_tradedate_not_the_datetime_date(tmp_path):
    """The bug this whole module exists to prevent.

    A 10:00 ET fill in a UTC+10 report is stamped 00:01 the NEXT calendar day.
    Pairing on DateTime[:10] dates it to the following session -- a symbol-day
    that does not exist, against which no bars will ever be found, and which
    quietly drops a real trade from the comparison. 109 of 4,692 rows in the
    first real report had this shape.
    """
    p = write_csv(tmp_path / "f.csv", [
        row(sym="CYAB", trade_date="2026-08-28", dt="2026-08-29 00:01:52"),
    ])
    pl = flex.pairs(flex.load(p))
    assert pl == [{"symbol": "CYAB", "date": "2026-08-28"}]
    assert pl[0]["date"] != "2026-08-29"


def test_one_fill_cannot_pin_the_zone_and_the_module_says_so(tmp_path):
    """A single 18:00 stamp on its own TradeDate is consistent with nearly every
    candidate zone -- 04:00 ET from Sydney, 06:00 from Perth, 14:00 from UTC.

    The module must not pretend it resolved something it did not. Reporting
    `ambiguous` lets a caller override; reporting a bare zone name would look
    like an answer.
    """
    p = write_csv(tmp_path / "f.csv", [row(dt="2026-08-04 18:00:00")])
    tz = flex.measure_offsets(flex.load(p))
    assert tz["ambiguous"] is True
    assert len(tz["equally_good"]) > 1
    assert tz["chosen"] in tz["equally_good"]


def test_a_midnight_crossing_row_rules_out_the_report_being_in_et(tmp_path):
    """A DateTime date AHEAD of TradeDate cannot happen if the report is already
    in ET. This is the row shape that carries almost all the information."""
    p = write_csv(tmp_path / "f.csv", [
        row(trade_date="2026-08-28", dt="2026-08-29 00:01:52"),
    ])
    scores = flex.score_offsets(flex.load(p))
    assert scores["America/New_York"] == 0
    assert scores["Australia/Sydney"] == 1       # -> 10:01 ET on the 28th


def test_dst_is_handled_by_the_zone_not_a_constant(tmp_path):
    """The same wall-clock stamp maps to a DIFFERENT ET time either side of a
    changeover. Sydney is +10 in August and +11 in January, while New York is
    -4 then -5, so the gap moves from 14 hours to 16.

    A fixed offset left 86 of 18,482 rows in the full-year report unresolvable,
    all of them near changeovers. This is the test that stops a future edit
    reintroducing a constant.
    """
    execs = flex.load(write_csv(tmp_path / "f.csv", [
        row(sym="SUMMER", trade_date="2026-08-04", dt="2026-08-04 18:00:00"),
        row(sym="WINTER", trade_date="2026-01-06", dt="2026-01-07 01:00:00"),
    ]))
    flex.measure_offsets(execs, force="Australia/Sydney")
    et = {e.symbol: e.et_minute for e in execs}
    assert et["SUMMER"] == 4 * 60                # +10 vs -4  -> 14h
    assert et["WINTER"] == 9 * 60                # +11 vs -5  -> 16h
    assert {e.symbol: e.offset_hours for e in execs} == {"SUMMER": 14, "WINTER": 16}


def test_forcing_a_zone_overrides_the_measurement(tmp_path):
    p = write_csv(tmp_path / "f.csv", [row(dt="2026-08-04 18:00:00")])
    execs = flex.load(p)
    tz = flex.measure_offsets(execs, force="Australia/Perth")
    assert tz["chosen"] == "Australia/Perth" and tz["forced"] is True
    assert execs[0].et_minute == 6 * 60          # +8 vs -4 -> 12h -> 06:00 ET


def test_a_row_the_offset_cannot_explain_is_left_unresolved(tmp_path):
    """Never guess a block for a row that does not fit. UNKNOWN is a real
    answer; silently bucketing it into PRE is not."""
    p = write_csv(tmp_path / "f.csv", [
        row(dt="2026-08-04 18:00:00"),
        row(sym="BBB", trade_date="2026-08-04", dt="2026-08-04 03:00:00"),
    ])
    execs = flex.load(p)
    tz = flex.measure_offsets(execs)
    assert tz["unresolved"] >= 1
    bad = [e for e in execs if e.et_minute is None]
    assert bad and flex.block(bad[0].et_minute) == "UNKNOWN"


def test_block_boundaries(tmp_path):
    assert flex.block(4 * 60) == "PRE"
    assert flex.block(9 * 60 + 29) == "PRE"
    assert flex.block(9 * 60 + 30) == "RTH"      # the open belongs to RTH
    assert flex.block(15 * 60 + 59) == "RTH"
    assert flex.block(16 * 60) == "POST"
    assert flex.block(None) == "UNKNOWN"


# --- aggregation ------------------------------------------------------------

def test_commission_sign_is_ibkrs_not_flipped(tmp_path):
    """IBKR reports commission as NEGATIVE (money left the account). Adding it
    is correct; subtracting it doubles the cost and makes every strategy
    comparison look better than it is."""
    p = write_csv(tmp_path / "f.csv", [
        row(pnl=100.0, comm=-1.50),
    ])
    sd = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert sd.gross_pnl == 100.0
    assert sd.commission == -1.50
    assert sd.net_pnl == 98.50


def test_symbol_day_aggregates_every_execution(tmp_path):
    """176 symbol-days came from 4,692 executions -- a median of 14 each. If
    aggregation dropped fills the P/L would still look plausible."""
    p = write_csv(tmp_path / "f.csv", [
        row(pnl=10.0, comm=-1.0, qty=100),
        row(pnl=-4.0, comm=-1.0, qty=-100, side="SELL"),
        row(pnl=2.0, comm=-1.0, qty=50),
    ])
    sd = flex.symbol_days(flex.load(p))
    assert len(sd) == 1
    s = sd[("AAA", "2026-08-04")]
    assert s.executions == 3
    assert s.shares == 250                       # absolute, both directions
    assert s.gross_pnl == 8.0
    assert s.net_pnl == 5.0


def test_pairs_are_deduped_and_sorted(tmp_path):
    p = write_csv(tmp_path / "f.csv", [
        row(sym="ZZZ", trade_date="2026-08-04"),
        row(sym="AAA", trade_date="2026-08-05"),
        row(sym="AAA", trade_date="2026-08-05"),
        row(sym="AAA", trade_date="2026-08-04"),
    ])
    pl = flex.pairs(flex.load(p))
    assert pl == [
        {"symbol": "AAA", "date": "2026-08-04"},
        {"symbol": "AAA", "date": "2026-08-05"},
        {"symbol": "ZZZ", "date": "2026-08-04"},
    ]


def test_price_band_flags_but_never_drops(tmp_path):
    """A real trade log's job is to show what was ACTUALLY traded, including
    the 54 of 176 symbol-days the strategies would have refused. Dropping them
    here would hide the gap between the live universe and the modelled one --
    which is exactly the parity failure PROGRAM_INDEX section 4 warns about."""
    p = write_csv(tmp_path / "f.csv", [
        row(sym="CHEAP", px=0.42),
        row(sym="DEAR", px=42.0),
        row(sym="OK", px=5.0),
    ])
    sd = flex.symbol_days(flex.load(p))
    assert len(sd) == 3                          # nothing dropped
    assert sd[("CHEAP", "2026-08-04")].in_band is False
    assert sd[("DEAR", "2026-08-04")].in_band is False
    assert sd[("OK", "2026-08-04")].in_band is True


# --- loading ----------------------------------------------------------------

def test_order_level_rows_are_excluded(tmp_path):
    """Flex can emit ORDER and EXECUTION rows in one file. Summing both
    double-counts the P/L and every total looks twice as large."""
    p = write_csv(tmp_path / "f.csv", [
        row(pnl=10.0, lod="EXECUTION"),
        row(pnl=10.0, lod="ORDER"),
    ])
    execs = flex.load(p)
    assert len(execs) == 1
    assert sum(e.fifo_pnl for e in execs) == 10.0


def test_non_stock_rows_are_excluded_by_default(tmp_path):
    p = write_csv(tmp_path / "f.csv", [
        row(asset="STK"), row(sym="SPY   260904C00500000", asset="OPT"),
    ])
    assert len(flex.load(p)) == 1
    assert len(flex.load(p, stocks_only=False)) == 2


def test_a_non_flex_csv_fails_loudly(tmp_path):
    """The failure mode to avoid is a partial parse that returns a smaller,
    plausible answer. VW9's first Setup B run did exactly that with the wrong
    loader and produced 176 trades instead of 407 with no error at all."""
    p = write_csv(tmp_path / "f.csv", [["AAA", "2026-08-04"]],
                  header=["symbol", "date"])
    with pytest.raises(ValueError, match="not an IBKR Flex trade report"):
        flex.load(p)


def test_new_against_finds_only_genuinely_new_pairs(tmp_path):
    existing = tmp_path / "existing.json"
    json.dump([{"symbol": "AAA", "date": "2026-08-04"}], open(existing, "w"))
    p = write_csv(tmp_path / "f.csv", [
        row(sym="AAA", trade_date="2026-08-04"),
        row(sym="BBB", trade_date="2026-08-04"),
    ])
    new = flex.new_against(flex.pairs(flex.load(p)), existing)
    assert new == [{"symbol": "BBB", "date": "2026-08-04"}]


# --- the shipped artefact ---------------------------------------------------

def test_the_committed_holdout_list_is_well_formed():
    """The holdout list must stay DISJOINT from the training pairs. If a future
    edit merges them, the project loses its only out-of-sample set and no test
    anywhere else would notice."""
    root = Path(__file__).resolve().parents[2]
    holdout = root / "var/state/holdout_pairs_2026H2.json"
    train = root / "var/state/traded_pairs.json"
    if not holdout.exists():
        pytest.skip("holdout list not present")

    h = json.load(open(holdout))
    assert len(h) == 176
    assert all(set(p) == {"symbol", "date"} for p in h)
    assert len({(p["symbol"], p["date"]) for p in h}) == len(h)
    assert min(p["date"] for p in h) >= "2026-07-01"

    if train.exists():
        t = json.load(open(train))
        overlap = ({(p["symbol"], p["date"]) for p in h}
                   & {(p["symbol"], p["date"]) for p in t})
        assert not overlap, f"holdout contaminated by {len(overlap)} training pairs"
        # And it must stay strictly LATER in time than the training set.
        assert min(p["date"] for p in h) > max(p["date"] for p in t)


# --- combining exports ------------------------------------------------------

def test_identical_child_fills_are_not_treated_as_duplicates(tmp_path):
    """The bug that cost $3,360 and raised nothing.

    A large order routed as several identical child fills -- same symbol, same
    second, same size, same price, same commission -- is ordinary. A de-dup key
    built from those field values collapsed 1,314 real executions out of a
    single 18,482-row report. The total just got smaller and stayed plausible.
    TradeID is what distinguishes them.
    """
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, px=5.0, comm=-1.0, pnl=25.0, trade_id="A1"),
        row(qty=100, px=5.0, comm=-1.0, pnl=25.0, trade_id="A2"),
        row(qty=100, px=5.0, comm=-1.0, pnl=25.0, trade_id="A3"),
    ])
    execs = flex.load_many([p])
    assert len(execs) == 3
    assert sum(e.fifo_pnl for e in execs) == 75.0


def test_overlapping_exports_are_deduplicated_by_trade_id(tmp_path):
    """Flex caps a query at ~12 months, so a longer history arrives as
    overlapping files. Concatenating them double-counts the overlap, and the
    overlap is invisible in the totals -- they are simply larger."""
    a = write_csv(tmp_path / "a.csv", [
        row(pnl=10.0, trade_id="X1"), row(pnl=20.0, trade_id="X2")])
    b = write_csv(tmp_path / "b.csv", [
        row(pnl=20.0, trade_id="X2"), row(pnl=30.0, trade_id="X3")])
    execs = flex.load_many([a, b])
    assert len(execs) == 3
    assert sum(e.fifo_pnl for e in execs) == 60.0


def test_a_missing_trade_id_fails_loudly_rather_than_guessing(tmp_path):
    p = write_csv(tmp_path / "f.csv", [row(trade_id="")])
    with pytest.raises(ValueError, match="no TradeID"):
        flex.load_many([p])


# --- buy and sell sides, kept apart -----------------------------------------

def test_average_prices_are_share_weighted_not_an_average_of_averages(tmp_path):
    """The fills are wildly unequal -- a day can be 31 executions running from
    100 to 5,000 shares. Averaging the fill prices gives 5.50 here; weighting
    by shares gives 8.00, and only one of them is what the account paid. The
    wrong one is not detectably wrong: it is always a plausible price."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, px=2.0),
        row(qty=900, px=9.0),
    ])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert s.buy_shares == 1000
    assert s.avg_buy_price == pytest.approx(8.30)   # (200 + 8100) / 1000
    assert s.avg_buy_price != pytest.approx(5.50)   # the mean of the prices


def test_buys_and_sells_are_separated_by_the_sign_not_the_side_string(tmp_path):
    """Every other figure here -- shares, max_position -- is derived from the
    sign of qty. Deriving this one from the Buy/Sell string instead would let
    the two drift apart on a row where they disagree, silently."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=200, px=4.0, side="BUY"),
        row(qty=-200, px=6.0, side="SELL"),
    ])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert (s.buy_shares, s.sell_shares) == (200, 200)
    assert s.avg_buy_price == pytest.approx(4.0)
    assert s.avg_sell_price == pytest.approx(6.0)
    assert s.shares == 400          # unchanged: total transacted, both sides


def test_a_day_with_no_sells_has_no_average_sell_price(tmp_path):
    """None, not 0.0. A zero in an average-price column reads as a real price
    and averages into any summary as one."""
    p = write_csv(tmp_path / "f.csv", [row(qty=100, px=5.0)])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert s.avg_sell_price is None
    assert s.avg_buy_price == pytest.approx(5.0)


def test_the_new_columns_do_not_disturb_the_old_totals(tmp_path):
    """Strictly additive. If gross, commission or net moved, every conclusion
    already drawn from this aggregation moved with them."""
    p = write_csv(tmp_path / "f.csv", [
        row(pnl=10.0, comm=-1.0, qty=100),
        row(pnl=-4.0, comm=-1.0, qty=-100, side="SELL"),
        row(pnl=2.0, comm=-1.0, qty=50),
    ])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert (s.executions, s.shares, s.gross_pnl, s.net_pnl) == (3, 250, 8.0, 5.0)


def test_a_missing_average_price_is_written_empty_not_zero():
    assert flex._px(None) == ""
    assert flex._px(4.5) == "4.5000"


# --- fills are not trades ---------------------------------------------------

def test_round_trips_count_returns_to_flat_not_fills(tmp_path):
    """'Number of trades' has to mean the same thing in every column of a
    comparison. A strategy's count is round trips; `executions` is fills, and a
    day of 31 fills can be three decisions. Putting one beside the other
    compares an order-slicing habit against a decision count."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, dt="2026-08-04 14:00:00"),
        row(qty=100, dt="2026-08-04 14:01:00"),          # scaling in
        row(qty=-200, dt="2026-08-04 14:05:00", side="SELL"),   # flat: 1
        row(qty=300, dt="2026-08-04 15:00:00"),
        row(qty=-300, dt="2026-08-04 15:30:00", side="SELL"),   # flat: 2
    ])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert s.executions == 5
    assert s.round_trips == 2


def test_a_position_left_open_at_the_close_is_not_a_round_trip(tmp_path):
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, dt="2026-08-04 14:00:00"),
        row(qty=-50, dt="2026-08-04 15:00:00", side="SELL"),
    ])
    s = flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")]
    assert s.round_trips == 0


def test_a_day_that_never_trades_has_no_round_trip(tmp_path):
    """Counted on the CROSSING to flat, not on being flat -- otherwise the
    first fill of every day would score one before anything closed."""
    p = write_csv(tmp_path / "f.csv", [row(qty=100)])
    assert flex.symbol_days(flex.load(p))[("AAA", "2026-08-04")].round_trips == 0


# --- positions, not fills ---------------------------------------------------

def test_a_round_trip_holds_its_gross_cost_and_time_together(tmp_path):
    """IBKR books realised P/L on the CLOSING fill. Bucketing FILLS by time
    would put a day's gross in its exits and its commission at both ends, and
    no time bucket would satisfy net = gross - cost."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, px=5.0, comm=-1.0, pnl=0.0, dt="2026-08-04 14:00:00"),
        row(qty=-100, px=6.0, comm=-1.0, pnl=100.0, side="SELL",
            dt="2026-08-04 14:20:00"),
    ])
    ex = flex.load(p)
    flex.measure_offsets(ex)
    rt = flex.round_trips(ex)
    assert len(rt) == 1
    assert rt[0].fills == 2
    assert rt[0].gross_pnl == 100.0
    assert rt[0].commission == -2.0
    assert rt[0].net_pnl == 98.0
    assert rt[0].entry_minute is not None
    assert rt[0].entry_minute < rt[0].exit_minute


def test_round_trips_reconcile_with_the_day_totals(tmp_path):
    """Every fill belongs to exactly one unit, so the units must sum to the day.
    If they ever stop doing so, a time-of-day sheet and a monthly sheet built
    from the same trades will disagree and neither will look wrong."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=100, comm=-1.0, pnl=0.0, dt="2026-08-04 14:00:00"),
        row(qty=-100, comm=-1.0, pnl=40.0, side="SELL", dt="2026-08-04 14:10:00"),
        row(qty=200, comm=-2.0, pnl=0.0, dt="2026-08-04 15:00:00"),
        row(qty=-200, comm=-2.0, pnl=-15.0, side="SELL", dt="2026-08-04 15:30:00"),
    ])
    ex = flex.load(p)
    flex.measure_offsets(ex)
    rt = flex.round_trips(ex)
    day = flex.symbol_days(ex)[("AAA", "2026-08-04")]
    assert len(rt) == 2
    assert sum(r.gross_pnl for r in rt) == pytest.approx(day.gross_pnl)
    assert sum(r.commission for r in rt) == pytest.approx(day.commission)
    assert sum(r.fills for r in rt) == day.executions


def test_a_position_left_open_is_kept_and_flagged(tmp_path):
    """Its realised P/L is real -- partial closes inside it booked FIFO.
    Dropping it would remove that money from every time-keyed total while
    leaving it in the day totals, so the two would silently disagree."""
    p = write_csv(tmp_path / "f.csv", [
        row(qty=200, comm=-2.0, dt="2026-08-04 14:00:00"),
        row(qty=-100, comm=-1.0, pnl=30.0, side="SELL", dt="2026-08-04 15:00:00"),
    ])
    ex = flex.load(p)
    flex.measure_offsets(ex)
    rt = flex.round_trips(ex)
    assert len(rt) == 1
    assert rt[0].open_at_end is True
    assert rt[0].exit_minute is None
    assert rt[0].gross_pnl == 30.0


def test_an_unresolved_time_is_blank_not_midnight():
    """00:00 would drop every unresolved fill into one 30-minute bucket -- and
    the most conspicuous one on the sheet."""
    assert flex._hhmm(None) == ""
    assert flex._hhmm(4 * 60) == "04:00"
    assert flex._hhmm(9 * 60 + 31) == "09:31"
