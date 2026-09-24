#!/usr/bin/env python3
"""A BUY is not sent across a spread this wide, 2026-09-24.

Registered in docs/research/REGISTERED_spread_gate.md before this code:
`SPREAD_GUARD_PCT` = 2.0, on the quoted (ask - bid) / mid, BUY entries only,
AT-the-threshold REFUSED (the opposite direction from the drift guard's own
"at the threshold is admitted"), a missing quote admitted to
marketable_limit's NO_QUOTE rather than refused as a wide spread, one row
per bar. Ben's decision on W03-0002 step 6, in his own words: "let's ship
it". Full-quote backtest result: claude/w03_0002_spread_gate_RESULT_20260924.md.

Mirrors tests/brokers/ibkr/test_drift_guard.py's own parity bar, per
REGISTERED_spread_gate.md's G2 gate.
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
    assert M.SPREAD_GUARD_PCT == 2.0


def test_reads_the_quoted_spread_on_bid_and_ask():
    assert M.quoted_spread_pct(1.98, 2.02) == pytest.approx(2.0)
    assert math.isnan(M.quoted_spread_pct(float("nan"), 5.00))
    assert math.isnan(M.quoted_spread_pct(5.00, float("nan")))
    assert math.isnan(M.quoted_spread_pct(5.00, 0.0))
    assert math.isnan(M.quoted_spread_pct(0.0, 5.00))
    # crossed book (ask < bid) is not a spread reading either
    assert math.isnan(M.quoted_spread_pct(5.05, 5.00))


def test_refuses_at_and_past_two_percent_and_says_the_numbers():
    ok, why = M.spread_guard_ok(1.98, 2.02)            # exactly 2.0%
    assert not ok and "2.00%" in why and "1.9800" in why and "2.0200" in why
    assert "guard 2.0%" in why
    ok, why = M.spread_guard_ok(1.979, 2.021)          # 2.1%
    assert not ok and "2.10%" in why


def test_admits_below_the_threshold():
    assert M.spread_guard_ok(1.981, 2.019) == (True, "")   # 1.9%
    assert M.spread_guard_ok(4.98, 5.02) == (True, "")      # 0.8%
    assert M.spread_guard_ok(5.00, 5.00) == (True, "")      # 0.0%, no spread


def test_a_missing_quote_is_not_a_wide_spread():
    assert M.spread_guard_ok(float("nan"), 5.00) == (True, "")
    assert M.spread_guard_ok(5.00, float("nan")) == (True, "")


def test_the_limit_is_a_parameter_so_a_new_registration_can_change_one_number():
    assert not M.spread_guard_ok(4.90, 5.10, limit_pct=3.0)[0]   # 4.0%
    assert M.spread_guard_ok(4.90, 5.10, limit_pct=5.0)[0]


# --------------------------------------------------------------------------
# 2. the live path
# --------------------------------------------------------------------------

def drive(tag, bid, ask, polls=1):
    """The firing frame's last bar closes at 5.00; the ticker quotes bid/ask
    directly, independent of the drift guard's own derived-bid convention,
    so the spread can be set to an exact percentage regardless of drift."""
    df = retimed(firing_frame(scale_to=5.00), "2026-09-17 06:30")
    tr, st, log, out = one(tag, MCL)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)
    st.ticker.bid, st.ticker.ask = bid, ask

    async def go():
        for i in range(polls):
            await tr.step_symbol(st, at("2026-09-17 06:31:05"))
    asyncio.run(go())
    log.close()
    return st, list(csv.DictReader(out.open(encoding="utf-8")))


def test_a_buy_across_a_wide_spread_is_refused_and_recorded():
    st, rows = drive("wide", bid=4.90, ask=5.10)       # 4.0%, ask +2% (inside drift)
    assert not bought(rows)
    assert st.position is None
    skipped = rows_with(rows, "SKIPPED_SPREAD")
    assert len(skipped) == 1
    assert "4.00%" in skipped[0]["reject_reason"] and "guard 2.0%" in skipped[0]["reject_reason"]
    assert float(skipped[0]["bid"]) == pytest.approx(4.90)
    assert float(skipped[0]["ask"]) == pytest.approx(5.10)


def test_a_buy_at_exactly_the_threshold_is_refused():
    """REGISTERED_spread_gate.md Sec.1: "2.0% or more" -- AT the threshold
    refuses, the opposite of the drift guard's own admit-at-threshold."""
    st, rows = drive("atline", bid=4.95, ask=5.05)     # exactly 2.0%, ask +1%
    assert not bought(rows) and rows_with(rows, "SKIPPED_SPREAD")


def test_a_buy_inside_the_band_goes_through():
    """THE CONTROL: the guard must not stop the trader trading."""
    st, rows = drive("inside", bid=4.98, ask=5.02)     # 0.8%
    assert not rows_with(rows, "SKIPPED_SPREAD")
    assert bought(rows) and st.position is not None


def test_refused_once_per_bar_not_once_per_poll():
    st, rows = drive("repeat", bid=4.90, ask=5.10, polls=4)
    assert len(rows_with(rows, "SKIPPED_SPREAD")) == 1


def test_a_missing_quote_reaches_marketable_limit_as_NO_QUOTE_not_spread():
    st, rows = drive("noquote", bid=float("nan"), ask=float("nan"))
    assert not rows_with(rows, "SKIPPED_SPREAD")
    assert rows_with(rows, "NO_QUOTE")


def test_never_runs_on_a_sell_an_exit_is_never_guarded():
    """A position must be able to leave at any price. The trail fires with
    the quote showing a very wide spread and the SELL still goes out."""
    from tests.brokers.ibkr.test_ghost_position import build, held_position, Trade
    tr, st, ib, log, out = build("exitspread", [Trade(filled=100, avg=2.60, status="Filled")])
    pos = held_position(st, entry=3.82); pos.peak = 3.90
    ib.held["TEST"] = 100
    st.ticker.bid, st.ticker.ask = 2.00, 2.60          # 26% spread -- would refuse an entry
    asyncio.run(tr.manage_position(st, at("2026-09-16 06:17:07"), bar_close=None, detail={}))
    log.close()
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert st.position is None
    assert [r["status"] for r in rows if r["action"] == "SELL"] == ["FILLED"]
    assert not rows_with(rows, "SKIPPED_SPREAD")


def test_drift_and_spread_guards_share_the_same_fresh_quote():
    """Both guards must read one quote() call, not two -- a fresh quote for
    each would let the market move between them. A spread wide enough to
    refuse, with the ask still inside the drift band, isolates that this is
    the spread guard (not the drift guard) doing the refusing here, and
    confirms the same bid/ask pair drives both checks."""
    st, rows = drive("shared", bid=4.90, ask=5.10)
    assert not rows_with(rows, "SKIPPED_DRIFT")
    assert rows_with(rows, "SKIPPED_SPREAD")
