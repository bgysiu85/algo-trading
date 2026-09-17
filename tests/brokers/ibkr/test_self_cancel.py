#!/usr/bin/env python3
"""A cancel the trader sends is not a rejection, 2026-09-17.

    REJECTED -- Error 202: Order Canceled - reason:

Six rows on 09-17: four abandoned exits whose next attempt filled 1-3 s later
and two timed-out entries. After `_settle` waited for the terminal status
(the ghost fix), IB reported the trader's own cancel as `Cancelled` plus the
202 echo above, and the "IB never worked it" branch took it. The no-fill
statuses stopped appearing, so the fill-rate and rejection counts were wrong
from 09-17. Both paths, both directions, tested on the real marketable_limit.
"""
from __future__ import annotations

import asyncio

import pytest

from brokers.ibkr import trader as T
from common import strategy_adapter as SA
from tests.brokers.ibkr.test_exit_abandon import (COLLAPSE, STEADY, Book,
                                                  a_position)

ECHO = "Order Canceled - reason:"
BAND = ("Order Canceled - reason:We cannot accept an order at a limit price at "
        "or more aggressive than 9.20. Please submit your order using a limit "
        "price that is closer to the current market")


@pytest.fixture(autouse=True)
def _short(monkeypatch):
    monkeypatch.setattr(T, "ORDER_TIMEOUT_S", 0.4)
    monkeypatch.setattr(T, "CANCEL_CONFIRM_S", 0.3)


def test_is_cancel_echo_reads_only_a_blank_reason_as_the_echo():
    assert T.is_cancel_echo("Error 202: " + ECHO, "Cancelled")
    assert T.is_cancel_echo("Error 202: Order Cancelled - reason: ", "Cancelled")
    assert T.is_cancel_echo("", "Cancelled")
    assert T.is_cancel_echo("Cancelled", "Cancelled")          # trade.log empty, why == status
    assert not T.is_cancel_echo("Error 202: " + BAND, "Cancelled")
    assert not T.is_cancel_echo("Error 10147: Order to cancel not found", "Cancelled")


def test_an_abandoned_exit_the_trader_cancelled_is_NO_FILL_ABANDONED_not_REJECTED():
    """The four exit rows of 09-17. The abandon path cancels, IB confirms with
    the blank 202, and the row must say what happened: nobody filled it."""
    book = Book(COLLAPSE)
    asyncio.run(book.run("SELL", 100, 9.2625, a_position()))
    row = book.log.rows[-1]
    assert row["status"] == "NO_FILL_ABANDONED", row
    assert "reject_reason" in row and "through the market" in row["reject_reason"]
    assert book.ib.cancelled, "the trader did send the cancel"
    assert book._self_cancelled == set(), "the id is cleared once the outcome is known"
    assert book._errors == {}, "the echo is consumed, not left for the next order"


def test_a_timed_out_entry_the_trader_cancelled_is_NO_FILL_CANCELLED():
    """The two entry rows (DAIC 04:50, 09:27). Entries wait the full timeout
    and are then cancelled by the trader."""
    book = Book(STEADY)
    asyncio.run(book.run("BUY", 100, 9.10, None))
    row = book.log.rows[-1]
    assert row["status"] == "NO_FILL_CANCELLED", row
    assert book._self_cancelled == set()


def test_a_cancel_the_trader_sent_that_ib_attached_a_reason_to_is_still_REJECTED():
    """IB's refusal can land in the settle window. The text carries a reason,
    so it is a rejection whoever sent the cancel -- and the band is consumed
    for the next attempt exactly as before."""
    book = Book(COLLAPSE)
    real_cancel = book.ib.cancelOrder

    def cancel_with_reason(order):
        real_cancel(order)
        book._errors[order.orderId] = "Error 202: " + BAND
    book.ib.cancelOrder = cancel_with_reason
    st_holder = {}
    orig_run = book.run

    async def run_keep(action, qty, ref, closing):
        # keep the SymbolState so the band can be read back
        st = T.SymbolState(symbol="CRBP", feed=None, strategy=SA.mcl_adapter())
        st.contract = object(); st.min_tick = 0.01
        st_holder["st"] = st
        return await T.MCLPaperTrader.marketable_limit(
            book, st, action, qty, ref, "trailing_stop", {}, closing=closing,
            ref_kind="trail_level")
    asyncio.run(run_keep("SELL", 100, 9.2625, a_position()))
    row = book.log.rows[-1]
    assert row["status"] == "REJECTED", row
    assert "more aggressive" in row["reject_reason"]
    assert st_holder["st"].price_band == ("SELL", 9.20)


def test_a_cancel_the_trader_did_not_send_is_REJECTED_even_with_a_blank_reason():
    """The other direction: an order IB cancelled on its own (Read-Only API,
    outside-RTH refused) is done before the trader ever cancels. A blank
    reason on an id the trader never cancelled stays a rejection."""
    book = Book(STEADY)
    placed = book.ib.placeOrder

    def place_dead(contract, order):
        t = placed(contract, order)
        t.cancelled = True                     # isDone() before any cancel
        t.orderStatus.status = "Cancelled"
        book._errors[order.orderId] = "Error 202: " + ECHO
        return t
    book.ib.placeOrder = place_dead
    asyncio.run(book.run("BUY", 100, 9.10, None))
    row = book.log.rows[-1]
    assert row["status"] == "REJECTED", row
    assert book.ib.cancelled == [], "nothing to cancel: it was dead at IB"


def test_the_id_is_remembered_only_between_the_cancel_and_the_outcome():
    """A later order on the same id must not inherit the earlier cancel."""
    book = Book(STEADY)
    asyncio.run(book.run("BUY", 100, 9.10, None))
    assert book._self_cancelled == set()
    # the same id, rejected outright by IB this time
    book.ib.placed.clear()
    placed = book.ib.placeOrder

    def place_dead(contract, order):
        t = placed(contract, order)
        t.cancelled = True
        t.orderStatus.status = "Inactive"
        return t
    book.ib.placeOrder = place_dead
    asyncio.run(book.run("BUY", 100, 9.10, None))
    assert book.log.rows[-1]["status"] == "REJECTED"
