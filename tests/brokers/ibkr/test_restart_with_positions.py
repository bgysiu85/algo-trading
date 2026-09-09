#!/usr/bin/env python3
"""Restarting into an account that is not flat.

Found 2026-09-09, when Ben asked whether he should restart a live session that
was holding two positions. The honest answer was no, and the reason was worse
than "you would lose a few minutes":

  * the trailing stop is software-managed IN THIS PROCESS -- outside RTH there
    is no broker-side stop -- so killing it leaves the shares with no stop;
  * the trader never called ib.positions(), so the new process could not see
    them: the concurrency cap would read 0 open rather than 2;
  * and with st.position None for those names, the entry path was free to BUY
    THEM AGAIN.

The module docstring already warned that a crash with a position open leaves
it unprotected. The restart case -- where it silently doubles down -- was
covered nowhere.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA

ET = ZoneInfo("America/New_York")


class FakeContract:
    def __init__(self, symbol):
        self.symbol = symbol


class FakePosition:
    def __init__(self, symbol, qty, avg=5.0):
        self.contract = FakeContract(symbol)
        self.position = qty
        self.avgCost = avg


class FakeIB:
    def __init__(self, positions):
        self._positions = positions

    def positions(self):
        return list(self._positions)


def trader_with(positions, log_path, strategies=("mcl",)):
    tr = M.MCLPaperTrader.__new__(M.MCLPaperTrader)
    tr.ib = FakeIB(positions)
    tr.strategies = SA.build_all(list(strategies))
    tr.states = {}
    tr.feeds = {}
    tr.log = type("L", (), {"path": Path(log_path)})()
    return tr


def write_log(path: Path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=M.FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in M.FIELDS})


def buy_row(symbol="WYHG", strategy="MCL", price=5.82,
            ts="2026-09-09 08:11:03", status="FILLED"):
    return {"ts_et": ts, "strategy": strategy, "symbol": symbol,
            "action": "BUY", "status": status, "fill_price": price,
            "filled_qty": 100, "reason": "entry_signal"}


# --- seeing them at all ------------------------------------------------------

def test_the_trader_now_asks_the_broker_what_it_is_holding(tmp_path):
    tr = trader_with([FakePosition("WYHG", 100)], tmp_path / "f.csv")
    assert [p.contract.symbol for p in tr.open_at_broker()] == ["WYHG"]


def test_a_zero_size_row_is_not_an_open_position(tmp_path):
    """IB reports closed positions as size 0 rather than dropping them."""
    tr = trader_with([FakePosition("WYHG", 0), FakePosition("BNC", 100)],
                     tmp_path / "f.csv")
    assert [p.contract.symbol for p in tr.open_at_broker()] == ["BNC"]


# --- adoption ----------------------------------------------------------------

def bars_to(now, high=6.40, start="2026-09-09 08:00", n=40):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    return pd.DataFrame({"open": 5.8, "high": high, "low": 5.7, "close": 5.9,
                         "volume": 1000.0}, index=idx)


def adopting(tr, held, bars=None):
    async def sub(symbol):
        a = tr.strategies[0]
        tr.states[(a.name, symbol)] = M.SymbolState(
            symbol=symbol, feed=tr.feed_for(symbol), strategy=a)
        return True
    tr._subscribe = sub
    tr.bars = lambda _st: asyncio.sleep(
        0, result=bars if bars is not None else bars_to(None))
    return asyncio.run(tr.adopt_open_positions(held))


def test_an_adopted_position_carries_its_real_entry_and_strategy(tmp_path):
    log = tmp_path / "f.csv"
    write_log(log, [buy_row()])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    assert adopting(tr, tr.open_at_broker()) == []

    pos = tr.states[("MCL", "WYHG")].position
    assert pos is not None
    assert pos.qty == 100
    assert pos.entry_price == pytest.approx(5.82)
    assert pos.entry_time.hour == 8 and pos.entry_time.minute == 11
    assert pos.trail_pct == SA.mcl_adapter().trail_pct


def test_the_peak_is_read_from_the_bars_not_guessed(tmp_path):
    """THE DANGEROUS FIELD. The trail is measured from the highest price since
    entry, and that is recorded nowhere. Too low and the position stops out
    instantly; too high and it gives back more than the rule allows."""
    log = tmp_path / "f.csv"
    write_log(log, [buy_row(price=5.82)])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    adopting(tr, tr.open_at_broker(), bars=bars_to(None, high=7.10))
    pos = tr.states[("MCL", "WYHG")].position
    assert pos.peak == pytest.approx(7.10)
    assert pos.trail_level() == pytest.approx(7.10 * 0.95)


def test_the_peak_is_never_below_the_entry(tmp_path):
    """A name that only ever fell would otherwise get a trail under its own
    entry, which is not the rule the backtest measured."""
    log = tmp_path / "f.csv"
    write_log(log, [buy_row(price=5.82)])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    adopting(tr, tr.open_at_broker(), bars=bars_to(None, high=5.00))
    assert tr.states[("MCL", "WYHG")].position.peak == pytest.approx(5.82)


def test_only_bars_after_the_entry_count_towards_the_peak(tmp_path):
    """A high made BEFORE the entry is not a high since entry. Including it
    would put the trail above the market, which is the 2026-09-05 fill-model
    correction being reintroduced through a different door."""
    log = tmp_path / "f.csv"
    write_log(log, [buy_row(price=5.82, ts="2026-09-09 08:20:00")])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    early = bars_to(None, start="2026-09-09 08:00", n=10, high=9.99)
    adopting(tr, tr.open_at_broker(), bars=early)
    assert tr.states[("MCL", "WYHG")].position.peak == pytest.approx(5.82)


# --- refusing ----------------------------------------------------------------

def test_adoption_is_all_or_nothing(tmp_path):
    """A half-managed account is worse than an unmanaged one: some positions
    would have a trailing stop and others would not, and nothing on screen
    would say which."""
    log = tmp_path / "f.csv"
    write_log(log, [buy_row("WYHG")])        # BNC has no BUY row
    tr = trader_with([FakePosition("WYHG", 100), FakePosition("BNC", 100)], log)
    problems = adopting(tr, tr.open_at_broker())
    assert problems and any("BNC" in p for p in problems)
    assert all(s.position is None for s in tr.states.values()), (
        "nothing may be adopted when anything cannot be")


def test_a_position_with_no_fill_row_is_refused(tmp_path):
    log = tmp_path / "f.csv"
    write_log(log, [])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    problems = adopting(tr, tr.open_at_broker())
    assert any("no BUY row" in p for p in problems)


def test_a_position_opened_by_a_strategy_that_is_not_running_is_refused(tmp_path):
    """Adopting it under MCL's rules would size, band and trail it against a
    strategy that never agreed to them."""
    log = tmp_path / "f.csv"
    write_log(log, [buy_row(strategy="MC5")])
    tr = trader_with([FakePosition("WYHG", 100)], log, strategies=("mcl",))
    problems = adopting(tr, tr.open_at_broker())
    assert any("MC5" in p and "not running" in p for p in problems)


def test_a_short_is_refused_outright(tmp_path):
    log = tmp_path / "f.csv"
    write_log(log, [buy_row()])
    tr = trader_with([FakePosition("WYHG", -100)], log)
    problems = adopting(tr, tr.open_at_broker())
    assert any("SHORT" in p for p in problems)


def test_a_symbol_with_no_bars_is_refused_rather_than_given_a_guessed_trail(
        tmp_path):
    log = tmp_path / "f.csv"
    write_log(log, [buy_row()])
    tr = trader_with([FakePosition("WYHG", 100)], log)
    problems = adopting(tr, tr.open_at_broker(), bars=bars_to(None).iloc[0:0])
    assert any("peak" in p for p in problems)


# --- the default -------------------------------------------------------------

def test_refuse_is_the_default_not_adopt():
    """Adoption reconstructs a trailing stop from a log and some bars. That is
    the right escape hatch and the wrong default.

    Read off the TRADER's own parser: a test that builds its own and asserts on
    that is asserting about itself.
    """
    args = M.build_parser().parse_args([])
    assert args.on_open_positions == "refuse"
    assert M.build_parser().parse_args(
        ["--on-open-positions", "adopt"]).on_open_positions == "adopt"


def test_adopt_is_the_only_other_choice():
    """An unrecognised value must be rejected by argparse rather than falling
    through to a branch that treats anything-but-adopt as refuse -- which is
    safe here, but silently ignoring a typed option is how a flag stops
    meaning anything."""
    with pytest.raises(SystemExit):
        M.build_parser().parse_args(["--on-open-positions", "ignore"])
