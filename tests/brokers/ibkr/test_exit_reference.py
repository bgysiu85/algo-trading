#!/usr/bin/env python3
"""What an exit's slippage is measured against.

Found on the 2026-09-08 paper session: both trailing-stop exits logged a
`slippage_vs_ref` that was the trade's whole per-share P/L. manage_position
took one `ref_close` doing two unrelated jobs -- a fallback price when the ask
is NaN, and the fill log's measurement reference -- and the fast loop, which
has no bar, passed the position's ENTRY price for the first and so supplied it
as the second.

It is not cosmetic: common/friction.py reads these rows to produce the
$/round-trip figure the whole project turns on.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from brokers.ibkr import trader as T
from common import friction as F

ET = ZoneInfo("America/New_York")


def pos(entry=5.82, peak=6.00, qty=100):
    return T.Position(symbol="WYHG", qty=qty, entry_price=entry,
                      entry_time=datetime(2026, 9, 8, 8, 11, tzinfo=ET),
                      peak=peak)


# --- which price an exit is judged against ---------------------------------

def test_a_trailing_stop_is_measured_against_the_level_that_fired_it():
    """The question friction needs answered is 'how far below the trigger did
    we get out'. The trigger is the trail level, not the entry price."""
    p = pos(entry=5.82, peak=6.00)
    ref, kind = T.MCLPaperTrader._exit_reference(p, "trailing_stop",
                                                 bar_close=None,
                                                 last_price=5.43)
    assert kind == "trail_level"
    assert ref == pytest.approx(p.trail_level())
    assert ref != p.entry_price, "THE BUG: the entry price is not a reference"


def test_the_entry_price_is_never_the_reference_for_any_exit():
    """Regression, stated as the general rule rather than the one case. With
    entry as the reference, 'slippage' is (exit - entry) -- the P/L."""
    p = pos(entry=5.82, peak=6.00)
    for reason, bar_close in (("trailing_stop", None),
                              ("trailing_stop", 5.90),
                              ("window_close", 5.90),
                              ("apex_reversal", 5.90)):
        ref, _kind = T.MCLPaperTrader._exit_reference(p, reason, bar_close,
                                                      last_price=5.43)
        assert ref != p.entry_price


def test_a_bar_triggered_exit_is_measured_against_the_bar():
    for reason in ("window_close", "apex_reversal"):
        ref, kind = T.MCLPaperTrader._exit_reference(pos(), reason,
                                                     bar_close=5.90,
                                                     last_price=5.43)
        assert (ref, kind) == (5.90, "bar_close")


def test_a_bar_exit_retried_from_the_fast_loop_says_it_used_a_quote():
    """Reachable when a bar-triggered exit did not fill and is retried where
    there is no bar. Naming it stops a quote-referenced row being averaged in
    as though it were bar-referenced."""
    ref, kind = T.MCLPaperTrader._exit_reference(pos(), "window_close",
                                                 bar_close=None,
                                                 last_price=5.43)
    assert (ref, kind) == (5.43, "quote")


def test_the_trail_level_moves_with_the_peak_not_the_entry():
    """If the reference tracked entry, a position that ran up before stopping
    out would report its whole gain-then-loss as execution slippage."""
    low = T.MCLPaperTrader._exit_reference(pos(peak=6.00), "trailing_stop",
                                           None, 5.43)[0]
    high = T.MCLPaperTrader._exit_reference(pos(peak=9.00), "trailing_stop",
                                            None, 5.43)[0]
    assert high > low


# --- the fill log says which reference it used -----------------------------

def test_ref_kind_is_a_column_so_a_row_describes_itself():
    assert "ref_kind" in T.FIELDS
    assert T.FIELDS.index("ref_kind") == T.FIELDS.index("ref_close") + 1


# --- friction.py must not average the old rows in --------------------------

def test_friction_drops_pre_fix_trailing_stop_sells():
    """Rows with no ref_kind and reason=trailing_stop are the broken ones."""
    assert not F.usable_reference(
        {"action": "SELL", "reason": "trailing_stop"})


def test_friction_keeps_everything_the_bug_did_not_touch():
    """Buys were always measured against the signal close, and pre-fix bar-path
    exits had a real bar close -- which is what keeps the published $4.26,
    measured when 84% of exits were apex, standing."""
    assert F.usable_reference({"action": "BUY", "reason": "entry_signal"})
    assert F.usable_reference({"action": "SELL", "reason": "apex_reversal"})
    assert F.usable_reference({"action": "SELL", "reason": "window_close"})


def test_a_row_that_names_its_reference_is_always_kept():
    assert F.usable_reference({"action": "SELL", "reason": "trailing_stop",
                               "ref_kind": "trail_level"})


def test_the_20260908_rows_would_have_been_excluded():
    """The two exits from that session, as written. Both are the trade's P/L
    dressed as slippage: -0.39 = 5.43 - 5.82 and -0.22 = 5.36 - 5.58."""
    rows = [{"action": "SELL", "reason": "trailing_stop",
             "slippage_vs_ref": "-0.39"},
            {"action": "SELL", "reason": "trailing_stop",
             "slippage_vs_ref": "-0.22"}]
    assert [F.usable_reference(r) for r in rows] == [False, False]
