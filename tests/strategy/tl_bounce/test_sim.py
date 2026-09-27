#!/usr/bin/env python3
"""Unit tests for the TL-bounce walk (sim.py) against hand-built cases,
REGISTERED_tl_bounce.md sec 2.2-2.3."""
from __future__ import annotations

import numpy as np
import pytest

from strategy.tl_bounce.sim import Counts, Entry, TICK, simulate
from strategy.tl_bounce.signals import Signals
from strategy.tl_bounce.spec import STOP_BUF


def _sig(o, h, lo, c, atr, sup=None, res=None, sup_breaks=None, res_breaks=None,
        swing_low=None, swing_high=None, e0=None):
    n = len(c)
    nan = np.full(n, np.nan)
    zero = np.zeros(n, bool)
    return Signals(
        np.asarray(o, float), np.asarray(h, float), np.asarray(lo, float),
        np.asarray(c, float), np.asarray(atr, float),
        nan.copy() if sup is None else np.asarray(sup, float),
        zero.copy() if sup_breaks is None else np.asarray(sup_breaks, bool),
        nan.copy() if res is None else np.asarray(res, float),
        zero.copy() if res_breaks is None else np.asarray(res_breaks, bool),
        zero.copy(), zero.copy(),
        (np.asarray(lo, float) - 1 if swing_low is None else np.asarray(swing_low, float)),
        (np.asarray(h, float) + 1 if swing_high is None else np.asarray(swing_high, float)),
        e0,
    )


def test_touch_leads_to_entry_next_open_long():
    n = 6
    c = [10, 10, 10, 10, 10, 10]
    o = [10, 10, 10, 11, 10, 10]
    h = [10.2] * n
    lo = [9.9, 9.9, 9.9, 9.9, 9.9, 9.9]
    atr = [1.0] * n
    sup = [np.nan, np.nan, 9.8, 9.8, 9.8, 9.8]
    s = _sig(o, h, lo, c, atr, sup=sup)
    s.touch_long[2] = True   # bar 2: low(9.9) <= sup(9.8)+0.25*1=10.05, close(10)>=9.8
    entries, k = simulate(s)
    assert k.held == 1
    assert k.entries == 1
    assert len(entries) == 1
    e = entries[0]
    assert e.direction == 1
    assert e.entry_j == 3          # filled at the open of the bar AFTER the touch
    assert e.stop_init == pytest.approx(min(9.8 - STOP_BUF * 1.0, 9.9 - TICK))


def test_e2_void_when_open_gaps_through_stop():
    n = 5
    c = [10] * n
    o = [10, 10, 10, 9.0, 10]   # bar 3's open gaps below the stop
    h = [10.2] * n
    lo = [9.9] * n
    atr = [1.0] * n
    sup = [np.nan, np.nan, 9.8, 9.8, 9.8]
    s = _sig(o, h, lo, c, atr, sup=sup)
    s.touch_long[2] = True
    entries, k = simulate(s)
    assert k.voided == 1
    assert k.entries == 0
    assert len(entries) == 0


def test_touch_ignored_while_in_position():
    n = 6
    c = [10] * n
    o = [10] * n
    h = [10.2] * n
    lo = [9.9] * n
    atr = [1.0] * n
    sup = [np.nan, 9.8, 9.8, 9.8, 9.8, 9.8]
    s = _sig(o, h, lo, c, atr, sup=sup)
    s.touch_long[1] = True    # opens a position (filled bar 2)
    s.touch_long[3] = True    # while still in position -> ignored, not a 2nd entry
    entries, k = simulate(s)
    assert k.held == 1
    assert k.ignored_in_position == 1
    assert k.entries == 1


def test_x1_exit_at_next_open_when_line_breaks():
    n = 6
    c = [10] * n
    o = [10] * n
    h = [10.2] * n
    lo = [9.9] * n
    atr = [1.0] * n
    sup = [np.nan, 9.8, 9.8, 9.8, np.nan, np.nan]
    sup_breaks = [False, False, False, True, False, False]   # line breaks at bar 3's close
    s = _sig(o, h, lo, c, atr, sup=sup, sup_breaks=sup_breaks)
    s.touch_long[1] = True
    entries, k = simulate(s)
    assert len(entries) == 1
    e = entries[0]
    assert e.exit_reason == "X1"
    assert e.exit_j == 4          # exits at the open AFTER the break fires
    assert k.exit_x1 == 1


def test_stop_hit_exits_same_bar_as_entry_fill():
    n = 4
    c = [10, 10, 10, 10]
    o = [10, 10, 10, 10]
    h = [10.2] * n
    lo = [9.9, 9.4, 9.9, 9.9]   # bar 1 (the fill bar) pierces the stop intrabar
    atr = [1.0] * n
    sup = [9.8, 9.8, 9.8, 9.8]
    s = _sig(o, h, lo, c, atr, sup=sup)
    s.touch_long[0] = True     # fills at bar 1's open
    entries, k = simulate(s)
    assert len(entries) == 1
    assert entries[0].entry_j == 1
    assert entries[0].exit_reason == "stop"
    assert entries[0].exit_j == 1
    assert k.exit_stop == 1


def test_no_reentry_bar_after_exit_bounce_once():
    """sec 2.5 bounce-once: this walk's narrower reading (module docstring)
    is 'no re-entry at all' after the first entry."""
    n = 8
    c = [10] * n
    o = [10] * n
    h = [10.2] * n
    lo = [9.9] * n
    atr = [1.0] * n
    sup = [np.nan, 9.8, 9.8, 9.8, np.nan, 9.8, 9.8, 9.8]
    sup_breaks = [False, False, False, True, False, False, False, False]
    s = _sig(o, h, lo, c, atr, sup=sup, sup_breaks=sup_breaks)
    s.touch_long[1] = True   # first entry
    s.touch_long[5] = True   # would be a 2nd touch after the X1 exit
    entries, k = simulate(s, allow_reentry=False)
    assert k.entries == 1
    assert k.held == 1


def test_e0_blocks_entry_when_direction_disagrees():
    n = 4
    c = [10] * n
    o = [10] * n
    h = [10.2] * n
    lo = [9.9] * n
    atr = [1.0] * n
    sup = [np.nan, 9.8, 9.8, 9.8]
    e0 = np.array([0, -1, -1, -1], dtype=float)   # higher chart says short only
    s = _sig(o, h, lo, c, atr, sup=sup, e0=e0)
    s.touch_long[1] = True
    entries, k = simulate(s, e0_on=True)
    assert k.e0_blocked == 1
    assert k.entries == 0
