#!/usr/bin/env python3
"""Re-entry on a bar that closed during the previous position, 2026-09-17.

    08:24:24  MC5 RETO SELL 100 @ 3.30  trailing_stop
    08:24:25  MC5 RETO BUY  100 @ 3.29  entry_signal   signal close 2.45

Seven re-entries within five seconds of the same strategy's own exit,
(82.62). While a position is open the entry path is never reached, so the
bars closing during it are never marked evaluated; the first poll after the
release evaluates the last closed bar -- one the position was open through --
and buys it at whatever the quote is now. The engine reads each bar once and
in order, so the earliest re-entry it can make is the NEXT bar's own signal.
The live rule that matches it: an entry signal is taken only from a bar
whose close is after this strategy's last exit on the name.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import timedelta

import pandas as pd
import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA
from tests.brokers.ibkr.test_stale_signal_bar import (MCL, at, bought,
                                                      firing_frame, one,
                                                      retimed, rows_with)



# --------------------------------------------------------------------------
# 1. the rule itself
# --------------------------------------------------------------------------

def ts(s: str):
    return pd.Timestamp(s, tz=M.ET).tz_convert("UTC")


def test_no_exit_on_record_means_no_constraint():
    assert M.bar_after_exit(ts("2026-09-17 08:15"), None) == (True, "")


def test_a_bar_that_opened_before_the_exit_is_refused_and_says_why():
    # the RETO bar: 08:15-08:20 bucket, closed 08:20:00; exit 08:24:24
    ok, why = M.bar_after_exit(ts("2026-09-17 08:15"), at("2026-09-17 08:24:24"))
    assert not ok
    assert "08:15" in why and "opened before" in why and "08:24:24" in why


def test_the_bar_the_exit_fired_inside_is_the_exit_bar_and_is_refused():
    """Live, the stop fires on a quote inside a bar; that bar is the engine's
    exit bar and the engine never enters on it. The 08:20-08:25 bucket the
    08:24:24 exit fell inside is refused even though it closes after it."""
    assert not M.bar_after_exit(ts("2026-09-17 08:20"), at("2026-09-17 08:24:24"))[0]
    assert not M.bar_after_exit(ts("2026-09-17 08:24"), at("2026-09-17 08:24:24"))[0]


def test_the_first_bar_to_open_after_the_exit_is_allowed():
    assert M.bar_after_exit(ts("2026-09-17 08:25"), at("2026-09-17 08:24:24"))[0]
    # a bar opening in the same instant as the exit is the next bar, not the exit bar
    assert M.bar_after_exit(ts("2026-09-17 08:25"), at("2026-09-17 08:25:00"))[0]
    assert not M.bar_after_exit(ts("2026-09-17 08:24"), at("2026-09-17 08:25:00"))[0]


def test_the_rule_needs_no_bar_length():
    """The open is the stamp on both strategies, so the same rule serves the
    1-minute and the 5-minute adapter without being told which it is."""
    exit_at = at("2026-09-17 08:23:30")
    for stamp in ("08:20", "08:22", "08:23"):
        assert not M.bar_after_exit(ts(f"2026-09-17 {stamp}"), exit_at)[0]
    for stamp in ("08:24", "08:25"):
        assert M.bar_after_exit(ts(f"2026-09-17 {stamp}"), exit_at)[0]


def test_a_naive_stamp_is_refused_rather_than_guessed():
    ok, why = M.bar_after_exit(pd.Timestamp("2026-09-17 08:20"), at("2026-09-17 08:24:24"))
    assert not ok and "naive" in why


# --------------------------------------------------------------------------
# 2. the live path, through step_symbol
# --------------------------------------------------------------------------

def held(st, entry_et, price=5.00):
    st.position = M.Position(symbol=st.symbol, qty=100, entry_price=price,
                             entry_time=at(entry_et), peak=price, trail_pct=5.0)
    return st.position


def run(tag, df, steps, adapter=MCL):
    """`steps`: (now, action) pairs; action None just polls, 'release' drops
    the position the way an exit on the fast loop does."""
    tr, st, log, out = one(tag, adapter)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)

    async def go():
        for now, action in steps:
            if action == "release":
                st.position = None
                st.last_exit_et = at(now)
            else:
                await tr.step_symbol(st, at(now))
    asyncio.run(go())
    log.close()
    return st, list(csv.DictReader(out.open(encoding="utf-8")))


def test_the_reto_shape_a_signal_bar_the_position_was_open_through_is_refused():
    """Signal on the 08:23 bar (closed 08:24:00) while a position is held;
    the position is released at 08:24:24; the poll at 08:24:25 must NOT buy
    that bar, and must say why once."""
    df = retimed(firing_frame(), "2026-09-17 08:23")
    tr_steps = [("2026-09-17 08:24:05", None),        # position open: managed, not entered
                ("2026-09-17 08:24:24", "release"),
                ("2026-09-17 08:24:25", None),
                ("2026-09-17 08:24:26", None)]
    tr, st, log, out = one("reto", MCL)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    held(st, "2026-09-17 08:10")

    async def go():
        for now, action in tr_steps:
            if action == "release":
                st.position = None
                st.last_exit_et = at(now)
            else:
                await tr.step_symbol(st, at(now))
    asyncio.run(go())
    log.close()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert not bought(rows), "bought a bar that closed during the old position"
    assert st.position is None
    skipped = rows_with(rows, "SKIPPED_BAR_BEFORE_EXIT")
    assert len(skipped) == 1, [r["status"] for r in rows]
    assert "08:24:24" in skipped[0]["reject_reason"]


def test_the_next_bar_after_the_exit_is_taken():
    """THE CONTROL. A bar that opens after the exit is a fresh signal and is
    bought -- the fix must not leave the trader unable to re-enter a name."""
    df = retimed(firing_frame(), "2026-09-17 08:25")     # opens 08:25:00
    st, rows = run("next", df, [("2026-09-17 08:24:24", "release"),
                                ("2026-09-17 08:26:05", None)])
    assert not rows_with(rows, "SKIPPED_BAR_BEFORE_EXIT")
    assert bought(rows)
    assert st.position is not None


def test_the_exit_path_records_the_exit_time():
    """manage_position's close stamps `last_exit_et` from the clock it was
    given, so the gate and the exit read the same clock."""
    from tests.brokers.ibkr.test_ghost_position import build, held_position, Trade
    tr, st, ib, log, out = build("stamp", [Trade(filled=100, avg=3.69, status="Filled")])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    st.ticker.bid, st.ticker.ask = 3.67, 3.68
    now = at("2026-09-16 06:17:07")
    asyncio.run(tr.manage_position(st, now, bar_close=None, detail={}))
    log.close()
    assert st.position is None
    assert st.last_exit_et == now


def test_a_reconciled_release_records_the_exit_time_too():
    from tests.brokers.ibkr.test_ghost_position import (Fill, Trade, build,
                                                        held_position, trail_exit)
    tr, st, ib, log, out = build("recon", [Trade(), Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    ib.held["TEST"] = 0
    ib.ib_fills = [Fill(100, 3.69, when=at("2026-09-16 06:17:08"))]
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    log.close()
    assert st.position is None
    assert st.last_exit_et is not None
    assert st.last_exit_et.date().isoformat() == "2026-09-16", "stamped from the fake clock, not the wall"


def test_a_second_strategy_on_the_same_name_is_not_constrained():
    """The exit is the STRATEGY's: MC5 releasing RETO says nothing about
    MCL's next bar on RETO. States are per (strategy, symbol)."""
    df = retimed(firing_frame(), "2026-09-17 08:23")
    st, rows = run("other", df, [("2026-09-17 08:24:25", None)])   # no exit on THIS state
    assert bought(rows)


# --------------------------------------------------------------------------
# 3. parity: the engine's own re-entry rule, which the live gate copies
# --------------------------------------------------------------------------

def test_the_engine_never_enters_on_a_bar_it_held_through_or_exited_on():
    """Signals on EVERY bar. Entry at bar 0; the stop bar exits at bar 1;
    the signals on bars 0 (held) and 1 (exit bar) are consumed, and the next
    trade opens on bar 2 -- the first bar to CLOSE after the exit, which is
    exactly what bar_after_exit allows live."""
    from tests.strategy.test_skip_entries import F, STOP, entries, mcl_run
    bars = [F, STOP, F, STOP, F, F]
    trades = mcl_run(bars, [0, 1, 2, 3, 4, 5])
    assert entries(trades)[:2] == ["07:00", "07:02"]
    for a, b in zip(trades, trades[1:]):
        assert pd.Timestamp(b.entry_time) > pd.Timestamp(a.exit_time)
        # and the live rule agrees on the same stamps: the exit bar's own
        # stamp is refused, the next bar's is allowed
        # live, the exit fires INSIDE the exit bar (stamp + 30 s here)
        live_exit = pd.Timestamp(a.exit_time) + timedelta(seconds=30)
        assert not M.bar_after_exit(pd.Timestamp(a.exit_time), live_exit)[0]
        assert M.bar_after_exit(pd.Timestamp(b.entry_time), live_exit)[0]
