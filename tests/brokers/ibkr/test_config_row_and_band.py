#!/usr/bin/env python3
"""Two things the live sessions asked for, on 2026-09-15.

THE CONFIG ROW. It was written by the UI bridge, so a session with no bridge
left no row at all. The portal chat argued that was complete rather than
ambiguous -- no bridge, no commands, nothing could have changed. Then the
bridge was CONFIGURED and refused to attach (its agent token had just been
deleted by a test run in the portal repo) and the ledger could not tell that
from "no bridge configured". Two states that look the same and are not.

It is written from the TRADER now, unconditionally, and it names the bridge
state so the three cases are distinguishable rather than inferred from the
absence of a row.

THE PRICE BAND. IBKR states the acceptable limit in the text of its own
rejection, and CRBP took three consecutive 202s -- 5.26, 5.52, 6.04 -- while
holding a collapsing position, because nothing read it.
"""
from __future__ import annotations

import pytest

from brokers.ibkr import trader as T
from common import strategy_adapter as SA


class Log:
    def __init__(self):
        self.rows = []

    def write(self, **kw):
        self.rows.append(kw)


class Book:
    def __init__(self, strategies=None, ui=None, paused=False, dry_run=False):
        self.log = Log()
        self.strategies = strategies or [SA.mcl_adapter()]
        self.ui = ui
        self.paused = paused
        self.disabled_strategies = set()
        self.max_positions = 3
        self.dry_run = dry_run

    def bridge_state(self):
        return T.MCLPaperTrader.bridge_state(self)

    def record_config(self, reason="session_open"):
        return T.MCLPaperTrader.record_config(self, reason)


# --- the CONFIG row ------------------------------------------------------------

def test_the_row_is_written_with_no_bridge_at_all(monkeypatch):
    """The whole point. No portal, no commands, and still a record of what the
    session was running with."""
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    b = Book()
    b.record_config()
    row = b.log.rows[0]
    assert row["action"] == "CONFIG" and row["reason"] == "session_open"
    assert "bridge=off" in row["reject_reason"]


def test_configured_but_unattached_is_its_own_state(monkeypatch):
    """2026-09-15 exactly: UI_RELAY_URL set, no token, bridge never attached.
    Indistinguishable from `off` until this existed."""
    monkeypatch.setenv("UI_RELAY_URL", "http://127.0.0.1:8000")
    b = Book(ui=None)
    b.record_config()
    assert "bridge=configured-but-unattached" in b.log.rows[0]["reject_reason"]


def test_attached_is_the_third_state(monkeypatch):
    monkeypatch.setenv("UI_RELAY_URL", "http://127.0.0.1:8000")
    b = Book(ui=object())
    b.record_config()
    assert "bridge=attached" in b.log.rows[0]["reject_reason"]


def test_the_three_states_are_all_different(monkeypatch):
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    off = Book().bridge_state()
    monkeypatch.setenv("UI_RELAY_URL", "http://x")
    unattached = Book().bridge_state()
    attached = Book(ui=object()).bridge_state()
    assert len({off, unattached, attached}) == 3


def test_the_row_carries_the_trail_PER_STRATEGY(monkeypatch):
    """One number would be a claim about both strategies that is only true
    while they happen to agree, and the portal can move one of them."""
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    b = Book(strategies=[mcl, mc5])
    b.record_config()
    cfg = b.log.rows[0]["reject_reason"]
    # the adapter's own name, whatever its case -- reading it off `a.name`
    # rather than hard-coding "mcl" keeps this test from asserting a spelling
    assert f"{mcl.name}:" in cfg and f"{mc5.name}:" in cfg
    assert cfg.count(":") >= 2, "one trail for two strategies is a claim"


def test_the_row_reads_the_cap_off_the_trader_not_a_constant(monkeypatch):
    """`max_positions` can be overridden on the command line. The row exists
    for the session where somebody did."""
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    b = Book()
    b.max_positions = 7
    b.record_config()
    assert "max_positions=7" in b.log.rows[0]["reject_reason"]


def test_paused_and_disabled_reach_the_row(monkeypatch):
    monkeypatch.delenv("UI_RELAY_URL", raising=False)
    b = Book(paused=True)
    b.disabled_strategies = {"mc5"}
    b.record_config()
    cfg = b.log.rows[0]["reject_reason"]
    assert "paused=True" in cfg and "disabled=mc5" in cfg


# --- the price band ------------------------------------------------------------

BAND_MSG = ("Error 202: Order Canceled - reason:We cannot accept an order at "
            "a limit price at or more aggressive than 6.31944. Please submit "
            "your order using <br>a limit price that is closer to the current "
            "market ")


def test_the_band_is_read_out_of_IBs_own_words():
    m = T.BAND_RE.search(BAND_MSG)
    assert m and float(m.group(1)) == pytest.approx(6.31944)


def test_a_rejection_without_a_band_yields_nothing():
    """Most 202s say something else. Inventing a band from a message that has
    none would clamp the next order to a price nobody quoted."""
    assert T.BAND_RE.search("Error 201: No Trading Permission") is None
    assert T.BAND_RE.search("Error 110: price does not conform to the minimum "
                            "price variation") is None


def _clamp(action, limit, band, tick=0.01):
    """THE MODULE'S OWN CLAMP.

    This used to be a reimplementation of the arithmetic sitting beside the
    code it was checking, and three mutations of the real thing survived a
    green suite: the band never recorded, never applied, and not one-shot. A
    guard tested by a copy of itself is not tested.
    """
    return T.clamp_to_band(limit, action, band, tick)


def test_a_SELL_is_clamped_UP_past_the_stated_edge():
    """"More aggressive" is LOWER for a sell, and the quoted number is itself
    refused -- so the limit has to land on the acceptable side of it, not on
    it. CRBP sent 5.26 against a band of 6.31944."""
    out = _clamp("SELL", 5.26, 6.31944)
    assert out > 6.31944, f"{out} would be rejected again"


def test_a_BUY_is_clamped_DOWN_past_the_stated_edge():
    out = _clamp("BUY", 9.99, 9.50)
    assert out < 9.50


def test_a_limit_already_inside_the_band_is_left_alone():
    """The clamp must never make an acceptable order worse."""
    assert _clamp("SELL", 7.00, 6.31944) == 7.00
    assert _clamp("BUY", 9.00, 9.50) == 9.00


def test_the_band_lives_on_the_feed_so_both_strategies_see_it():
    """IB refusing a price is a fact about the contract, not about one
    strategy. Two states over one feed must not each have to spend a rejected
    order to learn it."""
    assert "price_band" in T._FEED_FIELDS
    feed = T.SymbolFeed(symbol="CRBP")
    a = T.SymbolState(symbol="CRBP", feed=feed, strategy=SA.mcl_adapter())
    c = T.SymbolState(symbol="CRBP", feed=feed, strategy=SA.mc5_adapter())
    a.price_band = ("SELL", 6.31944)
    assert c.price_band == ("SELL", 6.31944)


def test_the_band_starts_empty():
    assert T.SymbolFeed(symbol="X").price_band is None


# --- and the band driven through the real order path ---------------------------
#
# The clamp tests above call clamp_to_band. These drive marketable_limit, so
# "recorded", "applied" and "one-shot" are checked where they happen rather
# than beside them.

class _Trade:
    def __init__(self):
        self.fills = []
        self.log = []
        self.orderStatus = type("S", (), {"status": "Submitted",
                                          "avgFillPrice": 0.0})()

    def isDone(self):
        return True                      # end the wait immediately


class _IB:
    def __init__(self):
        self.placed = []
        self.cancelled = []

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return _Trade()

    def cancelOrder(self, order):
        self.cancelled.append(order)


class Sender:
    def __init__(self, bid=9.08, ask=9.16):
        self.ib = _IB()
        self.log = Log()
        self.dry_run = False
        self._q = (bid, ask)
        self._errors = {}
        self._self_cancelled = set()

    def quote(self, st):
        return self._q

    def _name_of(self, st):
        return "MCL"

    def _trail_for(self, st):
        return 5.0

    def notify_fill(self, *a, **k):
        pass

    async def send(self, st, action="SELL"):
        return await T.MCLPaperTrader.marketable_limit(
            self, st, action, 100, 9.2625, "trailing_stop", {},
            closing=None, ref_kind="trail_level")


def _state():
    st = T.SymbolState(symbol="CRBP", feed=None, strategy=SA.mcl_adapter())
    st.contract = object()
    st.min_tick = 0.01
    return st


def test_a_recorded_band_actually_changes_the_limit_that_is_sent():
    import asyncio
    st = _state()
    st.price_band = ("SELL", 9.20)       # our natural limit ~9.06 is below it
    s = Sender()
    asyncio.run(s.send(st))
    assert s.ib.placed[0].lmtPrice > 9.20, \
        "the order went out at a price IB has already refused"


def test_the_band_is_spent_once_and_not_reapplied():
    import asyncio
    st = _state()
    st.price_band = ("SELL", 9.20)
    s = Sender()
    asyncio.run(s.send(st))
    first = s.ib.placed[0].lmtPrice
    assert st.price_band is None, "a band is a fact about a moment, not a setting"
    asyncio.run(s.send(st))
    assert s.ib.placed[1].lmtPrice < first, \
        "the second order must be priced off the quote again"


def test_a_band_for_the_OTHER_action_is_ignored():
    """A buy band says nothing about where a sell may be priced."""
    import asyncio
    st = _state()
    st.price_band = ("BUY", 9.20)
    s = Sender()
    asyncio.run(s.send(st, "SELL"))
    assert s.ib.placed[0].lmtPrice < 9.20


class Rejecter(Sender):
    """A Sender whose order comes back cancelled, with IB's 202 on the error
    event -- which is where the real reason arrives."""

    def __init__(self, message=BAND_MSG):
        super().__init__()
        self.message = message
        self._errors = {}
        self._self_cancelled = set()      # IB's cancel, not the trader's
        self.blocked = []

        class Trade:
            def __init__(self):
                self.fills = []
                self.log = []
                self.orderStatus = type("S", (), {"status": "Cancelled",
                                                  "avgFillPrice": 0.0})()

            def isDone(self):
                return True

        def place(contract, order):
            order.orderId = 42
            self._errors[42] = self.message
            return Trade()
        self.ib.placeOrder = place

    def block_symbol(self, st, why):
        st.blocked = True
        self.blocked.append((st.symbol, why))


def test_the_band_is_recorded_FROM_a_real_rejection():
    """The parse has to run where the rejection is handled, not in a test's
    own call to BAND_RE. A mutation that dropped the assignment survived a
    green suite until this existed."""
    import asyncio
    st = _state()
    r = Rejecter()
    asyncio.run(r.send(st))
    assert st.price_band == ("SELL", pytest.approx(6.31944))
    assert r.log.rows[-1]["status"] == "REJECTED"


def test_a_rejection_with_no_band_leaves_the_field_alone():
    import asyncio
    st = _state()
    st.price_band = None
    r = Rejecter("Error 201: Order rejected - No Trading Permission")
    asyncio.run(r.send(st))
    assert st.price_band is None


def test_the_band_is_spent_by_the_next_order_and_not_the_one_after():
    """One-shot, driven end to end: reject (records a band), send (consumes
    it), send again (prices off the quote)."""
    import asyncio
    st = _state()
    # a band that BINDS: the natural limit off bid 9.08 is ~9.06, so the edge
    # has to sit above it or the clamp correctly does nothing and the test
    # measures nothing.
    binding = BAND_MSG.replace("6.31944", "9.20")
    asyncio.run(Rejecter(binding).send(st))
    assert st.price_band == ("SELL", pytest.approx(9.20))
    s = Sender()
    asyncio.run(s.send(st))
    assert st.price_band is None
    first = s.ib.placed[0].lmtPrice
    assert first > 9.20, "the first order should have been clamped"
    asyncio.run(s.send(st))
    assert s.ib.placed[1].lmtPrice < first, \
        "the second is priced off the quote again, not off a spent band"


# --- prepare() writes the row before anything can change it --------------------

def test_prepare_writes_the_config_row_before_the_watchlist(monkeypatch):
    """Driven through prepare(), not asserted from its source. A session that
    dies in sync_watchlist still has to leave a row saying what it was about
    to run with."""
    import asyncio
    monkeypatch.delenv("UI_RELAY_URL", raising=False)

    order = []

    class Prep(Book):
        async def sync_watchlist(self, first=False):
            order.append("watchlist")

        async def refresh_equity(self):
            order.append("equity")

        def record_config(self, reason="session_open"):
            order.append("config")
            return Book.record_config(self, reason)

    async def nosleep(_):
        return None
    monkeypatch.setattr(T.asyncio, "sleep", nosleep)

    p = Prep()
    asyncio.run(T.MCLPaperTrader.prepare(p))
    assert order[0] == "config", f"config must come first, got {order}"
    assert p.log.rows[0]["action"] == "CONFIG"


# --- drift ---------------------------------------------------------------------

def test_drift_is_NaN_not_zero_when_a_side_of_the_book_is_missing():
    """Zero drift is a strong, specific claim -- "the market is exactly where
    the decision was priced". It is not the same statement as "there was no
    quote", and writing 0.0 here would be the shape this column exists to
    fix."""
    nan = float("nan")
    assert T.ref_drift(nan, 9.16, 9.75) != T.ref_drift(nan, 9.16, 9.75)
    assert T.ref_drift(9.08, nan, 9.75) != T.ref_drift(9.08, nan, 9.75)
    assert T.ref_drift(9.08, 9.16, 0.0) != T.ref_drift(9.08, 9.16, 0.0)


def test_drift_measures_the_CRBP_entry_as_the_warning_it_was():
    """ref 9.75, bid 9.11, ask 9.35 -- the market was 5.3% below the price the
    decision was made at, and slippage_vs_ref called the fill favourable."""
    d = T.ref_drift(9.11, 9.35, 9.75)
    assert d == pytest.approx(-5.33, abs=0.02)


def test_the_band_pattern_can_only_match_a_parseable_number():
    """There is no try/except around the float() and there must not need to
    be: the pattern is the guard. A mutation pass showed the handler that used
    to sit there was unreachable."""
    for text in ("more aggressive than 6.31944", "more aggressive than .5",
                 "more aggressive than 12", "more aggressive than   9.0"):
        m = T.BAND_RE.search(text)
        assert m and float(m.group(1)) >= 0
    for text in ("more aggressive than abc", "more aggressive than 1.2.3 x",
                 "more aggressive than -"):
        m = T.BAND_RE.search(text)
        if m:
            float(m.group(1))            # whatever it matched must still parse
