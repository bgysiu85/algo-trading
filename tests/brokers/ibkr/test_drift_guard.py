#!/usr/bin/env python3
"""A BUY is not sent into a quote that has left its reference, 2026-09-17.

Registered in docs/research/REGISTERED_drift_guard.md before this code:
`DRIFT_GUARD_PCT` = 6.0, absolute, on the ASK against the signal close, BUY
entries only, at-the-threshold admitted, a missing quote admitted to
marketable_limit's NO_QUOTE rather than refused as drift, one row per bar.
"""
from __future__ import annotations

import asyncio
import csv
import math

import pytest

from brokers.ibkr import trader as M
from tests.brokers.ibkr.test_stale_signal_bar import (MCL, at, bought,
                                                      firing_frame, one,
                                                      retimed, rows_with)


# --------------------------------------------------------------------------
# 1. the rule
# --------------------------------------------------------------------------

def test_the_threshold_is_the_registered_one():
    assert M.DRIFT_GUARD_PCT == 6.0


def test_reads_the_ask_not_the_mid():
    assert M.ask_drift_pct(5.30, 5.00) == pytest.approx(6.0)
    assert math.isnan(M.ask_drift_pct(float("nan"), 5.00))
    assert math.isnan(M.ask_drift_pct(5.30, 0.0))
    assert math.isnan(M.ask_drift_pct(0.0, 5.00))


def test_refuses_past_six_percent_either_side_and_says_the_numbers():
    ok, why = M.drift_guard_ok(3.29, 2.45)            # RETO, +34.3%
    assert not ok and "+34.3%" in why and "3.2900" in why and "2.4500" in why
    ok, why = M.drift_guard_ok(9.11, 9.75)            # CRBP, -6.6%
    assert not ok and "-6.6%" in why
    assert not M.drift_guard_ok(5.301, 5.00)[0]
    assert not M.drift_guard_ok(4.699, 5.00)[0]


def test_admits_at_and_inside_the_threshold():
    assert M.drift_guard_ok(5.30, 5.00) == (True, "")   # exactly 6.0% in float
    assert M.drift_guard_ok(4.70, 5.00) == (True, "")
    assert M.drift_guard_ok(5.01, 5.00) == (True, "")
    assert M.drift_guard_ok(5.00, 5.00) == (True, "")


def test_a_missing_quote_is_not_drift():
    assert M.drift_guard_ok(float("nan"), 5.00) == (True, "")


def test_the_limit_is_a_parameter_so_a_new_registration_can_change_one_number():
    assert not M.drift_guard_ok(5.20, 5.00, limit_pct=3.0)[0]
    assert M.drift_guard_ok(5.20, 5.00, limit_pct=6.0)[0]


# --------------------------------------------------------------------------
# 2. the live path
# --------------------------------------------------------------------------

def drive(tag, ask, polls=1):
    """The firing frame's last bar closes at 5.00; the ticker asks `ask`."""
    df = retimed(firing_frame(scale_to=5.00), "2026-09-17 06:30")
    tr, st, log, out = one(tag, MCL)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    st.ticker.bid, st.ticker.ask = (ask - 0.01 if ask == ask else ask), ask

    async def go():
        for i in range(polls):
            await tr.step_symbol(st, at("2026-09-17 06:31:05"))
    asyncio.run(go())
    log.close()
    return st, list(csv.DictReader(out.open(encoding="utf-8")))


def test_a_buy_into_a_quote_far_above_the_signal_close_is_refused_and_recorded():
    st, rows = drive("above", ask=6.80)                # +36%
    assert not bought(rows)
    assert st.position is None
    skipped = rows_with(rows, "SKIPPED_DRIFT")
    assert len(skipped) == 1
    assert "+36.0%" in skipped[0]["reject_reason"] and "guard 6.0%" in skipped[0]["reject_reason"]
    assert float(skipped[0]["ask"]) == pytest.approx(6.80)


def test_a_buy_into_a_collapse_is_refused_too():
    st, rows = drive("below", ask=4.60)                # -8%
    assert not bought(rows) and rows_with(rows, "SKIPPED_DRIFT")


def test_a_buy_inside_the_band_goes_through():
    """THE CONTROL: the guard must not stop the trader trading."""
    st, rows = drive("inside", ask=5.20)               # +4%
    assert not rows_with(rows, "SKIPPED_DRIFT")
    assert bought(rows) and st.position is not None


def test_refused_once_per_bar_not_once_per_poll():
    st, rows = drive("repeat", ask=6.80, polls=4)
    assert len(rows_with(rows, "SKIPPED_DRIFT")) == 1


def test_a_missing_quote_reaches_marketable_limit_as_NO_QUOTE_not_drift():
    st, rows = drive("noquote", ask=float("nan"))
    assert not rows_with(rows, "SKIPPED_DRIFT")
    assert rows_with(rows, "NO_QUOTE")


def test_an_exit_is_never_guarded():
    """A position must be able to leave at any price. The trail fires with
    the quote 30% below the reference and the SELL still goes out."""
    from tests.brokers.ibkr.test_ghost_position import build, held_position, Trade
    tr, st, ib, log, out = build("exit", [Trade(filled=100, avg=2.60, status="Filled")])
    pos = held_position(st, entry=3.82); pos.peak = 3.90
    ib.held["TEST"] = 100
    st.ticker.bid, st.ticker.ask = 2.59, 2.60          # 33% under the peak
    asyncio.run(tr.manage_position(st, at("2026-09-16 06:17:07"), bar_close=None, detail={}))
    log.close()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert st.position is None
    assert [r["status"] for r in rows if r["action"] == "SELL"] == ["FILLED"]
    assert not rows_with(rows, "SKIPPED_DRIFT")
