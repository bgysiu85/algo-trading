#!/usr/bin/env python3
"""A stop that waits twenty seconds is not a stop.

CRBP, 2026-09-14. The trail fired at 07:02:10 with the bid at 9.08; the order
went out at 9.06 and sat for the full ORDER_TIMEOUT_S while the stock fell to
5.28. The next attempt did not leave until 07:02:31. The position was
unprotected for twenty seconds during a 42% collapse and the round trip cost
$241.37 -- 46% of that week's two-day loss.

The limit was unfillable within about a second of being placed. A marketable
SELL limit fills against the BID; once the bid is below the limit there is no
counterparty at the touch and the remaining wait is pure loss.

So an EXIT abandons and re-prices the moment its own quote says it cannot fill,
and an ENTRY does not -- twenty seconds of patience is how a buy gets a good
fill, and a missed entry costs the signal rather than the position.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brokers.ibkr import trader as T
from common import strategy_adapter as SA

ET = ZoneInfo("America/New_York")


class Trade:
    """ib_async's Trade, as much of it as marketable_limit reads."""

    def __init__(self, fills_after=None):
        self.fills = []
        self.log = []
        self.orderStatus = type("S", (), {"status": "Submitted",
                                          "avgFillPrice": 0.0})()
        self._done_at = fills_after

    def isDone(self):
        # Working until IB confirms the cancel -- the normal case. A trade
        # that never becomes done is the UNKNOWN case, tested separately.
        return getattr(self, "cancelled", False)


class IB:
    """A cancel the trader sends comes back the way IB really answers it:
    status `Cancelled` and a 202 with a blank reason on the error event.
    The fakes used to leave the status at `Submitted`, which is how the
    self-cancel-as-REJECTED defect of 2026-09-17 got past this file."""

    def __init__(self, book=None):
        self.placed = []
        self.cancelled = []
        self.trades = []
        self.book = book

    def placeOrder(self, contract, order):
        order.orderId = len(self.placed) + 1
        self.placed.append(order)
        t = Trade()
        self.trades.append(t)
        return t

    def cancelOrder(self, order):
        self.cancelled.append(order)
        for t in self.trades:
            t.cancelled = True
            t.orderStatus.status = "Cancelled"
        if self.book is not None:
            self.book._on_error(order.orderId, 202, "Order Canceled - reason:", None)


class Log:
    def __init__(self):
        self.rows = []

    def write(self, **kw):
        self.rows.append(kw)


class Book:
    """The trader, reduced to what marketable_limit touches."""

    def __init__(self, quotes):
        self.ib = IB(book=self)
        self.log = Log()
        self.dry_run = False
        self._quotes = list(quotes)      # consumed one per read
        self.reads = 0
        self._errors = {}
        self._self_cancelled = set()

    _on_error = T.MCLPaperTrader._on_error

    # marketable_limit calls this once up front and then once per poll
    def quote(self, st):
        q = self._quotes[min(self.reads, len(self._quotes) - 1)]
        self.reads += 1
        return q

    def _name_of(self, st):
        return "MCL"

    def _trail_for(self, st):
        return 5.0

    def notify_fill(self, *a, **k):
        pass

    # The real settle, so these tests exercise the wait for IB's confirmation
    # rather than a stand-in for it.
    _settle = T.MCLPaperTrader._settle

    async def run(self, action, qty, ref, closing):
        st = T.SymbolState(symbol="CRBP", feed=None,
                           strategy=SA.mcl_adapter())
        st.contract = object()
        st.min_tick = 0.01
        return await T.MCLPaperTrader.marketable_limit(
            self, st, action, qty, ref, "trailing_stop", {},
            closing=closing, ref_kind="trail_level")


def a_position(entry=9.16, qty=100):
    return T.Position(symbol="CRBP", qty=qty, entry_price=entry,
                      entry_time=datetime(2026, 9, 14, 7, 1, tzinfo=ET),
                      peak=9.75, trail_pct=5.0)


COLLAPSE = [(9.08, 9.16)] + [(5.28, 6.87)] * 40      # the CRBP minute
STEADY = [(9.08, 9.16)] * 200


@pytest.fixture(autouse=True)
def _short_timeout(monkeypatch):
    """ORDER_TIMEOUT_S is 20 seconds in production and these tests would spend
    it, literally, four times over. The behaviour under test is the SHAPE --
    abandon early, or wait out whatever the timeout is -- so the tests assert
    against T.ORDER_TIMEOUT_S rather than against 20, and shrinking it here
    changes nothing they check."""
    monkeypatch.setattr(T, "ORDER_TIMEOUT_S", 2.0)


def test_an_exit_abandons_as_soon_as_its_limit_is_through_the_market():
    b = Book(COLLAPSE)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    row = b.log.rows[-1]
    assert row["status"] == "NO_FILL_ABANDONED"
    assert row["seconds_to_fill"] < T.ORDER_TIMEOUT_S / 2, \
        "it must not wait out the timeout -- that is the whole defect"
    assert b.ib.cancelled, "the working order has to be pulled"


def test_the_abandoned_row_says_why_in_numbers():
    """Pooled with the plain timeout these become one figure and the change is
    unmeasurable. 'Waited 20s and nobody came' and 'was unfillable after half a
    second' are different facts."""
    b = Book(COLLAPSE)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    row = b.log.rows[-1]
    assert "through the market" in row["reject_reason"]
    assert "5.28" in row["reject_reason"]


def test_a_steady_quote_still_waits_the_full_timeout():
    """The other half. A stop that bails on every tick would churn the book and
    take a worse price than the one it already had."""
    b = Book(STEADY)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    row = b.log.rows[-1]
    assert row["status"] == "NO_FILL_CANCELLED"
    assert row["seconds_to_fill"] >= T.ORDER_TIMEOUT_S * 0.9


def test_an_ENTRY_never_abandons_however_far_the_quote_runs():
    """Twenty seconds of patience is how a buy gets a good fill, and a missed
    entry costs the signal, not the position. `closing is None` is the whole
    distinction."""
    b = Book([(9.08, 9.16)] + [(20.0, 21.0)] * 200)      # ask runs away
    asyncio.run(b.run("BUY", 100, 9.75, None))
    row = b.log.rows[-1]
    assert row["status"] == "NO_FILL_CANCELLED"
    assert row["seconds_to_fill"] >= T.ORDER_TIMEOUT_S * 0.9


def test_a_missing_quote_is_not_evidence_that_the_limit_is_dead():
    """NaN is absence, not a price through the limit. Treating it as one would
    abandon every exit the moment the feed hiccups."""
    nan = float("nan")
    b = Book([(9.08, 9.16)] + [(nan, nan)] * 200)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    assert b.log.rows[-1]["status"] == "NO_FILL_CANCELLED"


def test_one_bad_read_does_not_abandon_the_order():
    """EXIT_ABANDON_POLLS is a debounce on the feed. A single stale or crossed
    print must not pull a working order."""
    assert T.EXIT_ABANDON_POLLS >= 2
    flicker = [(9.08, 9.16)] + [(5.00, 6.00), (9.08, 9.16)] * 100
    b = Book(flicker)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    assert b.log.rows[-1]["status"] == "NO_FILL_CANCELLED"


def test_the_plain_timeout_row_now_carries_its_wait_too():
    """Both no-fill rows record how long they waited, or the two cannot be
    compared against each other."""
    b = Book(STEADY)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    assert "seconds_to_fill" in b.log.rows[-1]


def test_a_SELL_watches_the_BID_and_a_BUY_watches_the_ASK():
    """A marketable SELL limit fills against the bid. Watching the ask instead
    would keep a dead order working through exactly the move that killed CRBP
    -- and the collapse fixture above cannot tell the two apart, because there
    both sides fell. Here only the bid goes through the limit."""
    # limit is bid * (1 - LIMIT_CROSS_BPS/1e4) rounded, so ~9.06 from bid 9.08
    one_side = [(9.08, 9.16)] + [(9.00, 9.50)] * 200   # bid < limit, ask > limit
    b = Book(one_side)
    asyncio.run(b.run("SELL", 100, 9.2625, a_position()))
    assert b.log.rows[-1]["status"] == "NO_FILL_ABANDONED", \
        "the SELL must read the BID"
