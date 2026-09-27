"""sim.py: fills, stops, sizing, and the v0 / v0-rev difference, on hand-built bars.

Each test is written so that breaking the rule it names breaks the test.
"""
from __future__ import annotations

import numpy as np
import pytest

from strategy.tl_v0.sim import SimInput, simulate


def mk(o, h, l, c, up=(), dn=(), htf=1, init_long=None, init_short=None,
       trail_long=None, trail_short=None, **kw):
    n = len(c)
    arr = lambda v: np.asarray(v, dtype=float)
    U = np.zeros(n, bool); U[list(up)] = True
    D = np.zeros(n, bool); D[list(dn)] = True
    fill = lambda v, d: arr(v) if v is not None else np.full(n, d)
    hf = None if htf is None else (arr(htf) if np.ndim(htf) else np.full(n, float(htf)))
    return SimInput(arr(o), arr(h), arr(l), arr(c), U, D, hf,
                    fill(init_long, np.nan), fill(init_short, np.nan),
                    fill(trail_long, np.nan), fill(trail_short, np.nan), **kw)


FLAT = dict(o=[10] * 8, h=[10.5] * 8, l=[9.5] * 8, c=[10] * 8)


def run(x, rule="ignore", risk=100.0, mult=1.0, integer=False):
    return simulate(x, rule=rule, mult=mult, risk_usd=risk, integer=integer)


def test_entry_is_at_the_next_open_with_the_stop_known_at_the_signal_close():
    x = mk([10, 10, 11, 12, 13], [10.5, 10.5, 12, 13, 14], [9.5, 9.5, 10.5, 11.5, 12.5],
           [10, 10.4, 11.5, 12.5, 13.5], up=[1], init_long=[np.nan, 9.0, np.nan, np.nan, np.nan])
    r = run(x)
    t = r.trades[0]
    assert t.entry_j == 2 and t.entry_px == 11 and t.stop_init == 9.0
    assert t.qty == pytest.approx(100 / (11 - 9.0))
    assert t.reason == "data_end" and t.exit_px == 13.5


def test_a_bar_that_gaps_through_the_stop_fills_at_the_open():
    x = mk([10, 10, 10, 8.0, 8], [10.5, 10.5, 10.5, 8.5, 8.5], [9.5, 9.5, 9.6, 7.5, 7.5],
           [10, 10, 10, 8, 8], up=[0], init_long=[9.0] * 5)
    t = run(x).trades[0]
    assert t.exit_j == 3 and t.exit_px == 8.0 and t.reason == "stop_gap" and t.stop_fill
    # mutation: booking it at the stop would be 9.0
    assert t.exit_px != 9.0


def test_an_intrabar_stop_fills_at_the_stop():
    x = mk([10, 10, 10, 9.8, 9.8], [10.5, 10.5, 10.5, 10, 10], [9.5, 9.5, 9.6, 8.5, 9],
           [10, 10, 10, 9.5, 9.5], up=[0], init_long=[9.0] * 5)
    t = run(x).trades[0]
    assert t.exit_px == 9.0 and t.reason == "stop" and t.stop_fill


def test_the_stop_is_live_on_the_entry_bar():
    x = mk([10, 10, 8.5, 8.5], [10.5, 10.5, 9, 9], [9.5, 8.0, 8.4, 8.4], [10, 8.6, 8.6, 8.6],
           up=[0], init_long=[8.1] * 4)
    t = run(x).trades[0]
    assert t.entry_j == 1 and t.exit_j == 1 and t.exit_px == 8.1 and t.reason == "stop"


def test_an_entry_that_opens_beyond_its_stop_is_voided_and_counted():
    x = mk([10, 8.9, 9, 9], [10.5, 9, 9, 9], [9.5, 8.5, 9, 9], [10, 9, 9, 9], up=[0],
           init_long=[9.0] * 4)
    r = run(x)
    assert r.trades == [] and r.counts.voided == 1


def test_integer_sizing_of_zero_is_a_counted_skip():
    x = mk(**FLAT, up=[1], init_long=[1.0] * 8)            # stop 9 points away
    r = run(x, risk=5.0, integer=True)                        # 5 / 9 -> 0 contracts
    assert r.trades == [] and r.counts.skipped_size == 1
    r2 = run(x, risk=5.0, integer=False)
    assert len(r2.trades) == 1 and r2.trades[0].qty == pytest.approx(5 / 9)


def test_integer_sizing_floors():
    x = mk(**FLAT, up=[1], init_long=[8.0] * 8)            # 2 points
    t = run(x, risk=100.0, mult=10.0, integer=True).trades[0]
    assert t.qty == 5.0                                       # 100/(2*10)


def test_the_weekly_filter_blocks_and_counts():
    x = mk(**FLAT, up=[1], htf=-1, init_long=[9.0] * 8)
    r = run(x)
    assert r.trades == [] and r.counts.htf_blocked == 1


def test_no_filter_for_c1():
    x = mk(**FLAT, up=[1], htf=None, init_long=[9.0] * 8)
    assert len(run(x).trades) == 1


def test_the_trail_never_loosens_and_needs_the_right_side_of_the_close():
    n = 8
    x = mk([10] * n, [10.5] * n, [9.6] * n, [10] * n, up=[0], init_long=[9.0] * n,
           trail_long=[np.nan, 9.5, 9.2, 10.5, np.nan, np.nan, np.nan, np.nan])
    r = run(x)
    t = r.trades[0]
    # 9.5 applied from bar 2 (low 9.6 does not reach it); 9.2 is looser -> ignored;
    # 10.5 is above the close -> ignored; so no stop is hit
    assert t.reason == "data_end"
    x2 = mk([10] * n, [10.5] * n, [9.6, 9.6, 9.6, 9.4, 9.6, 9.6, 9.6, 9.6], [10] * n,
            up=[0], init_long=[9.0] * n, trail_long=[np.nan, 9.5, 9.2] + [np.nan] * 5)
    t2 = run(x2).trades[0]
    assert t2.exit_j == 3 and t2.exit_px == 9.5              # the ratcheted level held


def test_v0_ignores_an_opposite_break_and_v0_rev_reverses_at_the_next_open():
    n = 8
    o = [10, 10, 10.2, 10.1, 9.9, 9.8, 9.7, 9.6]
    x = mk(o, [v + 0.3 for v in o], [v - 0.3 for v in o], o, up=[0], dn=[3],
           htf=[1, 1, 1, -1, -1, -1, -1, -1], init_long=[8.0] * n, init_short=[12.0] * n)
    v0 = run(x, rule="ignore")
    assert len(v0.trades) == 1 and v0.trades[0].reason == "data_end"
    assert v0.counts.ignored_in_position == 1
    rev = run(x, rule="reverse")
    a, b = rev.trades
    assert a.reason == "reverse" and a.exit_j == 4 and a.exit_px == o[4] and not a.stop_fill
    assert b.direction == -1 and b.entry_j == 4 and b.entry_px == o[4] and b.stop_init == 12.0
    assert rev.counts.reversals == 1


def test_v0_rev_goes_flat_when_the_filter_blocks_the_reversal():
    n = 8
    o = [10, 10, 10.2, 10.1, 9.9, 9.8, 9.7, 9.6]
    x = mk(o, [v + 0.3 for v in o], [v - 0.3 for v in o], o, up=[0], dn=[3], htf=1,
           init_long=[8.0] * n, init_short=[12.0] * n)
    r = run(x, rule="reverse")
    assert len(r.trades) == 1 and r.trades[0].reason == "flat_blocked" and r.trades[0].exit_j == 4
    assert r.counts.reversal_blocked_flat == 1


def test_a_pending_exit_whose_open_is_through_the_stop_is_a_stop_fill():
    n = 6
    x = mk([10, 10, 10, 10, 7.0, 7], [10.3] * 4 + [7.2, 7.2], [9.7] * 4 + [6.8, 6.8],
           [10, 10, 10, 10, 7, 7], up=[0], dn=[3], htf=[1, 1, 1, -1, -1, -1],
           init_long=[8.0] * n, init_short=[12.0] * n)
    a = run(x, rule="reverse").trades[0]
    assert a.reason == "stop_gap" and a.stop_fill and a.exit_px == 7.0


def test_same_side_breaks_in_a_position_are_ignored_by_both():
    x = mk(**FLAT, up=[0, 3], init_long=[9.0] * 8)
    for rule in ("ignore", "reverse"):
        r = run(x, rule=rule)
        assert len(r.trades) == 1 and r.counts.ignored_in_position == 1


def test_a_signal_on_the_last_bar_is_counted_unfilled():
    x = mk(**FLAT, up=[7], init_long=[9.0] * 8)
    r = run(x)
    assert r.trades == [] and r.counts.unfilled_at_end == 1


def test_a_stop_on_the_wrong_side_of_the_close_is_no_order():
    x = mk(**FLAT, up=[1], init_long=[11.0] * 8)
    r = run(x)
    assert r.trades == [] and r.counts.no_stop == 1


def test_chandelier_ratchets_from_the_highest_high():
    n = 8
    h = [10.5, 10.5, 11, 12, 13, 12.5, 12, 11]
    lo = [9.5, 9.5, 10, 11, 12, 11.5, 11, 9.9]
    c = [10, 10, 10.8, 11.8, 12.8, 12, 11.5, 10]
    o = [10, 10, 10.2, 11.2, 12.2, 12.5, 11.8, 11.4]
    x = mk(o, h, lo, c, up=[1], atr=np.full(n, 0.5), chandelier_k=3.0)
    t = run(x).trades[0]
    # hh reaches 13 at bar 4 -> stop 13 - 1.5 = 11.5 from bar 5; bar 5 opens 12.5
    # and trades down to 11.5 -> filled at the stop
    assert t.exit_j == 5 and t.exit_px == 11.5 and t.stop_init == pytest.approx(10.5 - 1.5)
