#!/usr/bin/env python3
"""The MEDS ghost, 2026-09-16, and the four rules that make it impossible.

    06:16:04  MC5 MEDS BUY 100 @ 3.82 FILLED
    06:17:07  SELL trailing_stop limit 3.68  NO_FILL_ABANDONED after 0.51s
    06:17:08 -> 09:45   850+ more SELLs, every one NO_FILL
    09:44     IB: MEDS position 0; open order SELL 100 LMT 4.31 PreSubmitted

The first exit filled at IB after the trader had stopped listening. The abandon
path broke out of its poll loop, read `trade.fills` in the same instant, saw
nothing, cancelled, and recorded a no-fill. The trader kept 100 shares on its
books the account no longer held and sent SELL after SELL into a flat account
for three and a half hours -- each one a short sale had it filled -- while the
ghost held one of three concurrency slots and nine real signals were declined.

Four rules, each tested here on the trader's real entry and exit paths:

  D1  An order's outcome is not known until IB says the order is finished.
      After ANY cancel, wait for that; a fill that lands during the cancel is
      a fill; no terminal status within the bound is UNKNOWN, never no-fill.
  D2  Before any exit re-send, ask IB what the account holds. Flat means the
      position is gone -- release it, record it, send nothing. Less than the
      trader thinks means sell IB's number. A long-only book cannot go short.
  D3  After MAX_EXIT_ATTEMPTS with IB confirming the shares held, alert once
      and slow down.
  D4  A released ghost frees its concurrency slot.

Plus D5 (every bar closed during an order wait feeds the peak) and D7
(`show_trades` crashed on the one morning it was needed).
"""
from __future__ import annotations

import asyncio
import csv
import tempfile
import types
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA
from tests.brokers.ibkr.test_dryrun_roundtrip import (FakeEvent, FakeTicker,
                                                      find_firing_series)

ET = M.ET


# --------------------------------------------------------------------------
# a fake IB whose orders can fill AFTER the trader stops listening
# --------------------------------------------------------------------------

class Fill:
    def __init__(self, shares, price=0.0, side="SLD", symbol="TEST", when=None):
        self.execution = types.SimpleNamespace(shares=shares, price=price,
                                               side=side, time=when)
        self.contract = types.SimpleNamespace(symbol=symbol)


class Trade:
    """`late_fill=(shares, px)` lands ONLY when the cancel arrives -- the MEDS
    race. `never_done=True` models IB not answering within the bound."""
    def __init__(self, filled=0, avg=0.0, status="Submitted", late_fill=None,
                 never_done=False, qty=100):
        self.fills = [Fill(filled, avg)] if filled else []
        self.orderStatus = types.SimpleNamespace(status=status, avgFillPrice=avg)
        self.log = []
        self.late_fill = late_fill
        self.never_done = never_done
        self._terminal = status in ("Filled", "Cancelled", "ApiCancelled",
                                    "Inactive") and not (0 < filled < qty)
        self.cancelled = False

    def isDone(self):
        if self.never_done:
            return False
        return self.cancelled or self._terminal

    def on_cancel(self):
        self.cancelled = True
        if self.late_fill:
            sh, px = self.late_fill
            self.fills.append(Fill(sh, px))
            self.orderStatus.status = "Filled"
            self.orderStatus.avgFillPrice = px
        elif not self.never_done:
            # what IB really reports for a cancel the trader sent
            self.orderStatus.status = "Cancelled"


class IB:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.placed, self.trades = [], []
        self.held = {}                       # symbol -> shares, per IB
        self.ib_fills = []                   # what ib.fills() reports
        self.errorEvent = FakeEvent()
        self.positions_raise = False
        self.on_error = None                 # the trader's _on_error, once built

    def placeOrder(self, contract, order):
        order.orderId = len(self.placed) + 1
        self.placed.append(order)
        t = self.outcomes.pop(0) if self.outcomes else Trade()
        self.trades.append(t)
        return t

    def cancelOrder(self, order):
        for t in self.trades:
            t.on_cancel()
        # IB's echo of the cancel: a 202 with nothing after the colon
        if self.on_error is not None:
            self.on_error(order.orderId, 202, "Order Canceled - reason:", None)

    def positions(self):
        if self.positions_raise:
            raise RuntimeError("no connection")
        return [types.SimpleNamespace(contract=types.SimpleNamespace(symbol=s),
                                      position=q) for s, q in self.held.items()]

    def fills(self):
        return list(self.ib_fills)


class TG:
    def __init__(self): self.sent = []
    def send(self, text, force=False): self.sent.append(text); return True


def build(tag, outcomes, max_positions=3):
    out = Path(tempfile.gettempdir()) / f"ghost_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    ib = IB(outcomes)
    tr = M.MCLPaperTrader(ib, Path(tempfile.gettempdir()) / "wl.txt", log,
                          dry_run=False, max_positions=max_positions)
    tr.equity = 22290.96
    tr.tg = TG()
    ib.on_error = tr._on_error
    st = M.SymbolState(symbol="TEST", strategy=SA.mcl_adapter())
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states[(st.strategy.name, "TEST")] = st
    return tr, st, ib, log, out


def held_position(st, qty=100, entry=3.82, at=None):
    st.position = M.Position(symbol=st.symbol, qty=qty, entry_price=entry,
                             entry_time=at or datetime(2026, 9, 16, 6, 16, 4,
                                                       tzinfo=ET),
                             peak=entry, trail_pct=5.0)
    return st.position


def rows_of(log, out):
    log.close()
    return list(csv.DictReader(out.open(encoding="utf-8")))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    """The shapes under test, not the seconds. Production waits 20s for an
    order and 3s for a cancel; here both are short and the assertions are
    against the constants, not the numbers."""
    monkeypatch.setattr(M, "ORDER_TIMEOUT_S", 0.6)
    monkeypatch.setattr(M, "CANCEL_CONFIRM_S", 0.5)
    monkeypatch.setattr(M, "EXIT_RETRY_BACKOFF_S", 0.3)


async def trail_exit(tr, st, ask, polls=1):
    """Drive manage_position from the fast loop with the ask below the
    trail, `polls` times, a second apart."""
    st.ticker.bid, st.ticker.ask = ask - 0.01, ask
    now = datetime(2026, 9, 16, 6, 17, 7, tzinfo=ET)
    for i in range(polls):
        await tr.manage_position(st, now + timedelta(seconds=i),
                                 bar_close=None, detail={})


# --------------------------------------------------------------------------
# D1
# --------------------------------------------------------------------------

def test_a_fill_that_lands_during_the_cancel_is_a_fill():
    """THE MEDS RACE, reproduced. The abandon path breaks out, sends the
    cancel, and the fill arrives in that gap. Before: NO_FILL_ABANDONED and a
    ghost. Now: FILLED, position closed, nothing else sent."""
    tr, st, ib, log, out = build("late", [
        Trade(late_fill=(100, 3.69)),          # the first SELL
    ])
    pos = held_position(st)
    pos.peak = 3.90                            # trail 3.705, ask below it
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=3))
    rows = rows_of(log, out)
    sells = [r for r in rows if r["action"] == "SELL"]
    assert st.position is None, "the ghost survived"
    assert [r["status"] for r in sells] == ["FILLED"], [r["status"] for r in sells]
    assert float(sells[0]["fill_price"]) == pytest.approx(3.69)
    assert len(ib.placed) == 1, "a second SELL went into a flat account"


def test_no_terminal_status_within_the_bound_is_UNKNOWN_not_a_no_fill():
    """IB does not answer the cancel. Recording NO_FILL here is the original
    defect with a longer fuse. The row says ORDER_UNKNOWN, the symbol is
    flagged, and the next exit reconciles before it sends."""
    tr, st, ib, log, out = build("unknown", [Trade(never_done=True)])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    rows = rows_of(log, out)
    assert rows[-1]["status"] == "ORDER_UNKNOWN"
    assert st.unknown_order is True
    assert st.position is not None, "an unknown outcome must not close the book"


def test_a_partial_whose_remainder_fills_during_the_cancel_counts_both():
    """The partial-fill path had the same race for the remainder."""
    tr, st, ib, log, out = build("partial", [
        Trade(filled=40, avg=3.69, status="Submitted", late_fill=(60, 3.685)),
    ])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    rows = rows_of(log, out)
    sell = [r for r in rows if r["action"] == "SELL"][0]
    assert sell["status"] == "FILLED"
    assert int(sell["filled_qty"]) == 100
    assert st.position is None


def test_a_confirmed_cancel_with_no_fill_is_still_a_no_fill():
    """The control: D1 must not turn every abandon into a fill or an unknown.
    IB confirms the cancel, nothing filled -- the row is the same abandon row
    as before, and the position is still held."""
    tr, st, ib, log, out = build("clean", [Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    rows = rows_of(log, out)
    assert rows[-1]["status"] in ("NO_FILL_ABANDONED", "NO_FILL_CANCELLED")
    assert st.unknown_order is False
    assert st.position is not None


# --------------------------------------------------------------------------
# D2
# --------------------------------------------------------------------------

def test_ib_flat_on_a_retry_releases_the_position_and_sends_nothing():
    """The rule that would have ended MEDS at 06:17:08 instead of 09:45. IB's
    fill list shows the sell, so it is booked as an ordinary late fill."""
    tr, st, ib, log, out = build("flat", [Trade(), Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))       # attempt 1: no fill
    assert st.position is not None
    ib.held["TEST"] = 0                                        # IB is flat now
    ib.ib_fills = [Fill(100, 3.69, when=datetime(2026, 9, 16, 6, 17, 8,
                                                  tzinfo=ET))]
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=5))       # would be 5 re-sends
    rows = rows_of(log, out)
    assert st.position is None
    assert len(ib.placed) == 1, f"{len(ib.placed)} orders sent into a flat account"
    rec = [r for r in rows if r["reason"] == "reconciled_flat"]
    assert len(rec) == 1
    assert rec[0]["status"] == "FILLED"
    assert float(rec[0]["exit_price"]) == pytest.approx(3.69)
    assert rec[0]["trade_pnl"] != ""


def test_ib_flat_with_no_visible_execution_releases_with_an_unknown_price():
    """Still released -- a position IB does not hold is not a position -- but
    the row says the P/L is unknown rather than inventing one."""
    tr, st, ib, log, out = build("flatnofill", [Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    ib.held["TEST"] = 0
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    rows = rows_of(log, out)
    assert st.position is None
    assert rows[-1]["status"] == "RECONCILED_FLAT"
    assert rows[-1]["fill_price"] in ("", "nan")


def test_ib_holding_less_than_the_trader_thinks_sizes_the_sell_to_ib():
    tr, st, ib, log, out = build("less", [Trade(), Trade(filled=60, avg=3.69,
                                                        status="Filled", qty=60)])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    ib.held["TEST"] = 60
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    rows = rows_of(log, out)
    assert any(r["status"] == "RECONCILED_QTY" for r in rows)
    assert ib.placed[-1].totalQuantity == 60
    assert st.position is None


def test_a_sell_never_exceeds_what_ib_holds():
    """The property MEDS violated 850 times. Across a spread of local and IB
    quantities, every order sent on a retry is bounded by IB's number."""
    for local, ib_qty in ((100, 100), (100, 40), (100, 0), (250, 100)):
        tr, st, ib, log, out = build(f"prop{local}_{ib_qty}",
                                     [Trade(), Trade()])
        pos = held_position(st, qty=local); pos.peak = 3.90
        ib.held["TEST"] = local
        asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
        ib.held["TEST"] = ib_qty
        asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
        log.close()
        for o in ib.placed[1:]:
            assert o.totalQuantity <= ib_qty, (local, ib_qty, o.totalQuantity)


def test_an_unreadable_position_means_no_send():
    """A long-only book that cannot verify what it holds must not risk going
    short. The exit is skipped this poll, not sent blind."""
    tr, st, ib, log, out = build("unreadable", [Trade(), Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    ib.positions_raise = True
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=3))
    assert len(ib.placed) == 1
    assert st.position is not None


def test_the_first_attempt_trusts_local_state():
    """The other direction. IB's position push can lag a fill by a moment;
    refusing a legitimate FIRST exit because IB has not caught up would leave
    a real position unmanaged. Only retries reconcile.

    Since W02-0014 the exemption is bounded to POSITION_PUSH_LAG_S after the
    entry, which is where the lag lives: this entry is 2s old. The same exit
    on a position a minute old is refused -- see test_double_sell_short."""
    tr, st, ib, log, out = build("first", [Trade(filled=100, avg=3.69,
                                                status="Filled")])
    pos = held_position(st, at=datetime(2026, 9, 16, 6, 17, 5, tzinfo=ET))
    pos.peak = 3.90
    ib.held = {}                                   # IB has not caught up
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    assert len(ib.placed) == 1
    assert st.position is None


def test_an_unknown_order_forces_a_reconcile_even_on_the_next_first_attempt():
    tr, st, ib, log, out = build("unk2", [Trade(never_done=True), Trade()])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    assert st.unknown_order
    ib.held["TEST"] = 0
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    assert st.position is None
    assert len(ib.placed) == 1


# --------------------------------------------------------------------------
# D3
# --------------------------------------------------------------------------

def test_past_the_cap_it_alerts_once_and_slows_down(monkeypatch):
    """IB confirms the shares every time, and nothing fills. 850 orders a
    morning is not management. One alert, then a retry every
    EXIT_RETRY_BACKOFF_S, and the position stays open and counted.

    The backoff is left at its real value here: each poll spends about a
    second of wall clock in the order and cancel waits, so with a 30 s backoff
    every poll past the cap is throttled and the count is exact."""
    monkeypatch.setattr(M, "EXIT_RETRY_BACKOFF_S", 30.0)
    tr, st, ib, log, out = build("cap", [Trade() for _ in range(40)])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=M.MAX_EXIT_ATTEMPTS + 6))
    assert pos.needs_attention is True
    assert len(tr.tg.sent) == 1, tr.tg.sent
    assert "NEEDS ATTENTION" in tr.tg.sent[0]
    assert len(ib.placed) == M.MAX_EXIT_ATTEMPTS, len(ib.placed)
    assert st.position is not None, "a real, held position was dropped"
    log.close()


def test_after_the_backoff_the_retry_resumes(monkeypatch):
    """Slowed down, not stopped. A real held position still gets its exit."""
    monkeypatch.setattr(M, "EXIT_RETRY_BACKOFF_S", 0.0)
    tr, st, ib, log, out = build("resume", [Trade() for _ in range(40)])
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=M.MAX_EXIT_ATTEMPTS + 3))
    assert len(ib.placed) == M.MAX_EXIT_ATTEMPTS + 3
    assert len(tr.tg.sent) == 1, "the alert must fire once, not per retry"
    log.close()


# --------------------------------------------------------------------------
# D4
# --------------------------------------------------------------------------

def test_a_released_ghost_frees_its_concurrency_slot():
    """MEDS held one of three slots for three hours and nine entries were
    declined SKIPPED_CONCURRENCY_CAP. After the reconcile the slot is free."""
    tr, st, ib, log, out = build("slot", [Trade()], max_positions=1)
    pos = held_position(st); pos.peak = 3.90
    ib.held["TEST"] = 100
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    open_before = sum(1 for s in tr.states.values() if s.position is not None)
    ib.held["TEST"] = 0
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    open_after = sum(1 for s in tr.states.values() if s.position is not None)
    assert (open_before, open_after) == (1, 0)
    log.close()


# --------------------------------------------------------------------------
# D5
# --------------------------------------------------------------------------

def test_bars_closed_while_an_order_waited_still_feed_the_peak():
    """Ben saw 4.96; the trader's peak read 4.79. Three bars closed during one
    twenty-second order wait and only the newest was read."""
    full, _, _ = find_firing_series(140)
    tr, st, ib, log, out = build("peak", [])
    entry_time = full.index[100].to_pydatetime()
    pos = held_position(st, entry=float(full["close"].iloc[100]), at=entry_time)
    pos.peak = pos.entry_price
    # bars 101..104 closed while an order was waiting; bar 103 printed a spike
    df = full.iloc[:105].copy()
    spike = float(df["high"].iloc[103]) * 1.10
    df.iloc[103, df.columns.get_loc("high")] = spike
    st.ticker.bid, st.ticker.ask = pos.entry_price, pos.entry_price + 0.02
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    asyncio.run(tr.step_symbol(st, df.index[-1].to_pydatetime()
                               + timedelta(minutes=1)))
    assert pos.peak == pytest.approx(spike), (pos.peak, spike)
    assert pos.last_bar_seen == df.index[-1]
    log.close()


# --------------------------------------------------------------------------
# D7
# --------------------------------------------------------------------------

def test_show_trades_renders_a_real_fill_shape_without_crashing(capsys):
    """`Execution` has no `contract`; the Fill does. The crash hid the MEDS
    executions on the one morning they were needed."""
    from common import report_trades as R

    fill = types.SimpleNamespace(
        contract=types.SimpleNamespace(symbol="MEDS"),
        execution=types.SimpleNamespace(time=datetime(2026, 9, 16, 6, 17, 8),
                                        side="SLD", shares=100.0, price=3.69),
        commissionReport=types.SimpleNamespace(commission=0.35,
                                               realizedPNL=-13.35))

    class ViewerIB:
        async def accountSummaryAsync(self): return []
        async def reqPositionsAsync(self): return []
        async def reqAllOpenOrdersAsync(self): return []
        async def reqExecutionsAsync(self, _f): return [fill]

    asyncio.run(R.snapshot(ViewerIB()))
    out = capsys.readouterr().out
    assert "MEDS" in out and "SLD" in out and "3.6900" in out


# --------------------------------------------------------------------------
# the reverse ghost: an entry IB filled that the trader never saw
# --------------------------------------------------------------------------

def test_an_unknown_BUY_adopts_what_ib_holds_and_its_first_exit_reconciles():
    """The mirror of MEDS. A BUY whose cancel IB never confirmed can leave
    100 shares in the account with no position on the book -- unmanaged and
    free to be bought again. The trader adopts IB's shares at IB's cost, and
    because the flag stays set, the FIRST exit attempt reconciles rather than
    trusting local state -- the one case where `unknown_order` decides."""
    full, _, _ = find_firing_series(140)
    fires = [i for i, e in enumerate(__import__("strategy.mcl.mcl",
                                                 fromlist=["signals"])
                                     .signals(full)["entry"]) if e]
    df = full.iloc[: fires[0] + 1]
    tr, st, ib, log, out = build("reverse", [Trade(never_done=True), Trade()])
    ib.held["TEST"] = 100
    ib.positions_avg = 3.82
    orig_positions = ib.positions
    ib.positions = lambda: [types.SimpleNamespace(
        contract=types.SimpleNamespace(symbol=s), position=q, avgCost=3.82)
        for s, q in ib.held.items()]
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    now = df.index[-1].to_pydatetime() + timedelta(minutes=1)
    asyncio.run(tr.step_symbol(st, now))
    assert st.position is not None, "IB's shares were left orphaned"
    assert st.position.qty == 100 and st.position.entry_price == pytest.approx(3.82)
    assert st.unknown_order is True

    # IB goes flat before the first exit: reconciled, nothing sent.
    ib.held["TEST"] = 0
    st.position.peak = 3.90
    asyncio.run(trail_exit(tr, st, ask=3.68, polls=1))
    assert st.position is None
    assert len(ib.placed) == 1, "a SELL went out on the first attempt unverified"
    rows = rows_of(log, out)
    assert any(r["reason"] == "adopted_unknown_entry" for r in rows)
