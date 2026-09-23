#!/usr/bin/env python3
"""The CRML short, 2026-09-21 (W02-0014), and the three rules that close it.

    07:12:02  MCL CRML BUY 100 @ 8.57 FILLED
    08:40:02  MC5 CRML BUY 100 @ 8.67 FILLED         account now holds 200
    09:30:02  MCL SELL window_close  ORDER_UNKNOWN   (it filled after the wait)
    09:30:06  MCL SELL re-send       FILLED 100      IB said 100 -- MC5's
    09:30:07  MC5 SELL window_close  FILLED 100      first attempt, unchecked
    next day  startup refuses: IBKR holds CRML -100

The re-send guard (the MEDS rules, test_ghost_position) asked IB what the
ACCOUNT held. With two strategies in one name the account always holds
"something" until the last sell, so the guard could not see the double sell.

  S1  An ORDER_UNKNOWN order is remembered and its own fills are read before
      anything is re-sent. A fill there IS the exit.
  S2  A re-send is checked against what IB holds FOR THIS STRATEGY: the
      account less every other strategy's booked shares in the name.
  S3  No SELL -- first attempt or re-send -- for more than the account holds
      less SELLs still working, except a first attempt inside
      POSITION_PUSH_LAG_S of its entry.

Each rule is tested alone on the trader's real exit path, and the replay is
run once with all three switched off to prove it reproduces the short.
"""
from __future__ import annotations

import asyncio
import csv
import tempfile
import types
from datetime import datetime
from pathlib import Path

import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA
from tests.brokers.ibkr.test_dryrun_roundtrip import FakeEvent, FakeTicker

ET = M.ET
SYM = "CRML"


def at(h, m, s):
    return datetime(2026, 9, 21, h, m, s, tzinfo=ET)


# --------------------------------------------------------------------------
# a fake IB that keeps the ACCOUNT position honest
# --------------------------------------------------------------------------

class Fill:
    def __init__(self, shares, price, side="SLD", when=None):
        self.execution = types.SimpleNamespace(shares=shares, price=price,
                                               side=side, time=when)
        self.contract = types.SimpleNamespace(symbol=SYM)


class Trade:
    """`fill_now=px` fills the whole order on placement. `hang=True` models
    MCL's 09:30:02 order: no terminal status, even after the cancel."""
    def __init__(self, fill_now=None, hang=False):
        self.fill_now, self.hang = fill_now, hang
        self.order = self.contract = None
        self.fills = []
        self.orderStatus = types.SimpleNamespace(status="Submitted",
                                                 avgFillPrice=0.0,
                                                 remaining=0)
        self.log = []
        self._done = False

    def isDone(self):
        return self._done


class IB:
    def __init__(self, outcomes, held):
        self.outcomes = list(outcomes)
        self.placed, self.trades = [], []
        self.held = {SYM: held}
        self.low = held                       # lowest the account ever went
        self.ib_fills = []
        self.errorEvent = FakeEvent()
        self.on_error = None

    def _fill(self, t, px, qty):
        t.fills.append(Fill(qty, px))
        t.orderStatus.status = "Filled"
        t.orderStatus.avgFillPrice = px
        t.orderStatus.remaining = 0
        t._done = True
        sign = -1 if t.order.action == "SELL" else 1
        self.held[SYM] += sign * qty
        self.low = min(self.low, self.held[SYM])
        self.ib_fills.append(Fill(qty, px,
                                  "SLD" if sign < 0 else "BOT"))

    def placeOrder(self, contract, order):
        order.orderId = len(self.placed) + 1
        self.placed.append(order)
        t = self.outcomes.pop(0) if self.outcomes else Trade()
        t.order, t.contract = order, contract
        t.orderStatus.remaining = order.totalQuantity
        self.trades.append(t)
        if t.fill_now is not None:
            self._fill(t, t.fill_now, order.totalQuantity)
        return t

    def cancelOrder(self, order):
        for t in self.trades:
            if t.order is order and not t._done and not t.hang:
                t.orderStatus.status = "Cancelled"
                t._done = True
        if self.on_error is not None:
            self.on_error(order.orderId, 202, "Order Canceled - reason:", None)

    def late_fill(self, t, px):
        """IB fills the hung order after the trader stopped listening."""
        self._fill(t, px, t.order.totalQuantity)

    def openTrades(self):
        return [t for t in self.trades if not t._done]

    def positions(self):
        return [types.SimpleNamespace(contract=types.SimpleNamespace(symbol=s),
                                      position=q, avgCost=8.62)
                for s, q in self.held.items() if q]

    def fills(self):
        return list(self.ib_fills)


class TG:
    def __init__(self): self.sent = []
    def send(self, text, force=False): self.sent.append(text); return True


def state(tr, adapter, qty, entry, when):
    st = M.SymbolState(symbol=SYM, strategy=adapter)
    st.contract = types.SimpleNamespace(symbol=SYM)
    st.ticker = FakeTicker()
    st.ticker.bid, st.ticker.ask = 8.69, 8.77      # 09:30:02 quote
    if qty:
        st.position = M.Position(symbol=SYM, qty=qty, entry_price=entry,
                                 entry_time=when, peak=entry, trail_pct=5.0)
    tr.states[(adapter.name, SYM)] = st
    return st


def build(tag, outcomes, held, mcl_qty=100, mc5_qty=100):
    out = Path(tempfile.gettempdir()) / f"dblsell_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    ib = IB(outcomes, held)
    tr = M.MCLPaperTrader(ib, Path(tempfile.gettempdir()) / "wl.txt", log,
                          dry_run=False, max_positions=3)
    tr.equity = 22290.96
    tr.tg = TG()
    ib.on_error = tr._on_error
    mcl = state(tr, SA.mcl_adapter(), mcl_qty, 8.57, at(7, 12, 2))
    mc5 = state(tr, SA.mc5_adapter(), mc5_qty, 8.67, at(8, 40, 2))
    return tr, mcl, mc5, ib, log, out


def rows_of(log, out):
    log.close()
    return list(csv.DictReader(out.open(encoding="utf-8")))


def close(tr, st, when):
    asyncio.run(tr.manage_position(st, when, bar_close=None, detail={}))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(M, "ORDER_TIMEOUT_S", 0.4)
    monkeypatch.setattr(M, "CANCEL_CONFIRM_S", 0.3)


def replay_0921(tr, mcl, mc5, ib):
    """09:30:02 MCL sell hangs, fills late; 09:30:06 MCL again; 09:30:07 MC5."""
    close(tr, mcl, at(9, 30, 2))
    assert mcl.unknown_order, "setup: the first MCL sell must go UNKNOWN"
    ib.late_fill(ib.trades[0], 8.73)
    close(tr, mcl, at(9, 30, 6))
    close(tr, mc5, at(9, 30, 7))
    # and a couple more polls, as the real loop would make
    for s in (mcl, mc5):
        if s.position is not None:
            close(tr, s, at(9, 30, 8))


# --------------------------------------------------------------------------
# the replay
# --------------------------------------------------------------------------

def test_the_0921_replay_ends_flat_not_short():
    tr, mcl, mc5, ib, log, out = build("replay", [
        Trade(hang=True),            # MCL 09:30:02 -- fills after the wait
        Trade(fill_now=8.75),        # MC5 09:30:07
    ], held=200)
    replay_0921(tr, mcl, mc5, ib)
    rows = rows_of(log, out)
    assert ib.held[SYM] == 0, f"account ended at {ib.held[SYM]}, not flat"
    assert ib.low >= 0, f"account went short: {ib.low}"
    assert len(ib.placed) == 2, "MCL re-sent a SELL its first order had filled"
    assert mcl.position is None and mc5.position is None
    late = [r for r in rows if r["ref_kind"] == "late_fill"]
    assert len(late) == 1 and late[0]["strategy"] == "MCL"
    assert late[0]["status"] == "FILLED" and late[0]["filled_qty"] == "100"
    assert float(late[0]["exit_price"]) == 8.73      # the late fill's price
    assert float(late[0]["trade_pnl"]) > 0            # 8.57 -> 8.73, 100 sh
    assert tr.session_trades == 2


def test_control_without_the_fix_the_replay_goes_short(monkeypatch):
    """The replay must reproduce the defect, or it tests nothing. All three
    rules off -- the account-level check, no late-fill read, no no-short
    guard -- is the code as it ran on 2026-09-21."""
    monkeypatch.setattr(M.MCLPaperTrader, "_ib_held_for",
                        lambda self, st: self._ib_held(st))
    monkeypatch.setattr(M.MCLPaperTrader, "_resolve_unknown_exit",
                        lambda self, *a, **k: False)
    monkeypatch.setattr(M.MCLPaperTrader, "_sell_room",
                        lambda self, st: 10 ** 9)
    tr, mcl, mc5, ib, log, out = build("control", [
        Trade(hang=True), Trade(fill_now=8.74), Trade(fill_now=8.75),
    ], held=200)
    replay_0921(tr, mcl, mc5, ib)
    rows_of(log, out)
    assert ib.held[SYM] == -100, "control no longer reproduces 09-21"


# --------------------------------------------------------------------------
# each rule on its own
# --------------------------------------------------------------------------

def test_S1_alone_a_late_fill_on_the_unknown_order_is_the_exit(monkeypatch):
    monkeypatch.setattr(M.MCLPaperTrader, "_ib_held_for",
                        lambda self, st: self._ib_held(st))
    monkeypatch.setattr(M.MCLPaperTrader, "_sell_room",
                        lambda self, st: 10 ** 9)
    tr, mcl, mc5, ib, log, out = build("s1", [
        Trade(hang=True), Trade(fill_now=8.75)], held=200)
    replay_0921(tr, mcl, mc5, ib)
    rows_of(log, out)
    assert ib.held[SYM] == 0 and len(ib.placed) == 2


def test_S2_alone_the_other_strategys_shares_do_not_vouch(monkeypatch):
    """The late fill is NOT visible on the order (only in IB's position).
    The re-send asks IB for MCL's share: 100 held less MC5's 100 = 0, so
    MCL's position is released and nothing is sent."""
    monkeypatch.setattr(M.MCLPaperTrader, "_resolve_unknown_exit",
                        lambda self, *a, **k: False)
    monkeypatch.setattr(M.MCLPaperTrader, "_sell_room",
                        lambda self, st: 10 ** 9)
    tr, mcl, mc5, ib, log, out = build("s2", [
        Trade(hang=True), Trade(fill_now=8.75)], held=200)
    replay_0921(tr, mcl, mc5, ib)
    rows = rows_of(log, out)
    assert ib.held[SYM] == 0 and len(ib.placed) == 2
    rec = [r for r in rows if r["reason"] == "reconciled_flat"]
    assert len(rec) == 1 and rec[0]["strategy"] == "MCL"
    # IB's SLD list since MCL's entry holds only MCL's own 100 here, but the
    # row must never claim more than the position it closes
    assert int(rec[0]["filled_qty"] or 0) <= 100


def test_S3_alone_a_first_attempt_into_a_flat_account_is_refused():
    """MC5 at 09:30:07 with the account already flat: its book says 100,
    the account says 0. Refused, then released on the next poll."""
    tr, mcl, mc5, ib, log, out = build("s3", [Trade(fill_now=8.75)],
                                       held=0, mcl_qty=0)
    close(tr, mc5, at(9, 30, 7))
    assert ib.placed == [], "a SELL left for shares the account does not hold"
    close(tr, mc5, at(9, 30, 8))
    rows = rows_of(log, out)
    assert ib.placed == [] and mc5.position is None
    assert [r["status"] for r in rows][:1] == ["REFUSED_WOULD_SHORT"]
    assert ib.low == 0


def test_S3_counts_sells_still_working():
    """Account holds 100, a SELL for 100 of it is still working at IB: a
    second SELL for 100 would be short the moment both fill."""
    tr, mcl, mc5, ib, log, out = build("working", [Trade(hang=True)],
                                       held=100, mcl_qty=0)
    working = Trade(hang=True)
    working.order = types.SimpleNamespace(action="SELL", totalQuantity=100)
    working.contract = types.SimpleNamespace(symbol=SYM)
    working.orderStatus.remaining = 100
    ib.trades.append(working)
    close(tr, mc5, at(9, 30, 7))
    rows_of(log, out)
    assert ib.placed == []


def test_S3_exempts_only_a_fresh_entry():
    """Inside POSITION_PUSH_LAG_S of the entry, IB may simply not have caught
    up; the first attempt trusts local state as it always did."""
    tr, mcl, mc5, ib, log, out = build("fresh", [Trade(fill_now=8.75)],
                                       held=0, mcl_qty=0)
    mc5.position.entry_time = at(9, 30, 5)
    close(tr, mc5, at(9, 30, 7))
    rows_of(log, out)
    assert len(ib.placed) == 1


# --------------------------------------------------------------------------
# the entry side, and the end of the session
# --------------------------------------------------------------------------

def test_an_unknown_entry_adopts_only_this_strategys_share():
    """MC5 already holds 100; MCL's BUY went UNKNOWN and filled, so the
    account holds 200. MCL adopts 100 -- not MC5's shares as well."""
    tr, mcl, mc5, ib, log, out = build("adopt", [], held=200, mcl_qty=0)
    mcl.unknown_order = True
    tr._adopt_unknown_entry(mcl, at(8, 45, 0), {})
    rows_of(log, out)
    assert mcl.position is not None and mcl.position.qty == 100


def test_a_short_at_session_end_is_reported_and_alerted():
    tr, mcl, mc5, ib, log, out = build("eod", [], held=-100,
                                       mcl_qty=0, mc5_qty=0)
    shorts = tr.shorts_at_broker()
    rows_of(log, out)
    assert shorts == [f"{SYM} -100"]
    assert any("SHORT AT SESSION END" in m for m in tr.tg.sent)


def test_a_flat_account_at_session_end_says_nothing():
    tr, mcl, mc5, ib, log, out = build("eod_flat", [], held=0,
                                       mcl_qty=0, mc5_qty=0)
    assert tr.shorts_at_broker() == [] and tr.tg.sent == []
    rows_of(log, out)
