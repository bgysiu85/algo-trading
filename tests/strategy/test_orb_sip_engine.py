#!/usr/bin/env python3
"""strategy/orb/sip.py on hand-built bars.

Every case here is a rule from `REGISTERED_orb_sip.md` sections 2 and 3, and
each is written so that removing the rule changes the number. The traps are
the ones ORB already paid for once: a range that includes the bar after it, a
stop that fills at a level the bar gapped past, and a doji treated as a
direction.
"""
from __future__ import annotations

import pytest

from strategy.orb import sip as S

DAY = "2025-03-05"
M0 = S.RTH_OPEN_MIN


def run(rows, atr=1.0, or_minutes=5, **kw):
    """rows: (minute_offset, o, h, l, c) from 09:30."""
    minute = [M0 + r[0] for r in rows]
    return S.trade_symbol_day("AAA", DAY, minute, [r[1] for r in rows],
                              [r[2] for r in rows], [r[3] for r in rows],
                              [r[4] for r in rows], atr, or_minutes, **kw)


UP_RANGE = [(0, 10.0, 10.2, 9.9, 10.1), (1, 10.1, 10.3, 10.0, 10.2),
            (2, 10.2, 10.4, 10.1, 10.3), (3, 10.3, 10.5, 10.2, 10.4),
            (4, 10.4, 10.6, 10.3, 10.5)]          # close 10.5 > open 10.0
DOWN_RANGE = [(0, 10.5, 10.6, 10.3, 10.4), (1, 10.4, 10.5, 10.2, 10.3),
              (2, 10.3, 10.4, 10.1, 10.2), (3, 10.2, 10.3, 10.0, 10.1),
              (4, 10.1, 10.2, 9.9, 10.0)]         # close 10.0 < open 10.5


def test_a_long_enters_at_the_range_high_on_the_first_bar_that_reaches_it():
    t, why = run(UP_RANGE + [(5, 10.5, 10.55, 10.45, 10.5),
                             (6, 10.6, 10.7, 10.6, 10.65),
                             (7, 10.65, 10.8, 10.6, 10.75)])
    assert why == S.OK and t.side == S.LONG
    assert t.or_high == 10.6 and t.entry_px == pytest.approx(10.6)
    assert t.entry_min == M0 + 6, "09:35 could trigger; 09:36 was the first to reach"
    assert t.exit_reason == "session_end" and t.exit_px == pytest.approx(10.75)


def test_a_short_enters_at_the_range_low():
    t, why = run(DOWN_RANGE + [(5, 10.0, 10.05, 9.85, 9.9),
                               (6, 9.9, 9.95, 9.8, 9.85)])
    assert why == S.OK and t.side == S.SHORT
    assert t.or_low == 9.9 and t.entry_px == pytest.approx(9.9)
    assert t.entry_min == M0 + 5


def test_the_range_is_the_first_five_bars_and_the_sixth_can_trigger():
    """`ts_event` is the interval start. If the 09:35 bar were inside the
    range, its high would raise the trigger and this trade would not exist."""
    t, why = run(UP_RANGE + [(5, 10.5, 10.65, 10.45, 10.6)])
    assert why == S.OK and t.or_high == 10.6 and t.entry_min == M0 + 5


def test_a_fifteen_minute_range_uses_fifteen_bars():
    rows = [(i, 10.0 + i * 0.1, 10.2 + i * 0.1, 9.9 + i * 0.1, 10.1 + i * 0.1)
            for i in range(15)] + [(15, 11.5, 12.0, 11.4, 11.9)]
    t, why = run(rows, or_minutes=15)
    assert why == S.OK and t.or_high == pytest.approx(11.6) and t.entry_min == M0 + 15
    t5, _ = run(rows, or_minutes=5)
    assert t5.or_high == pytest.approx(10.6), "the 5-minute range sees five bars"


def test_a_doji_range_places_no_order():
    flat = [(i, 10.0, 10.2, 9.8, 10.0) for i in range(5)]
    t, why = run(flat + [(5, 10.0, 11.0, 9.9, 10.9)])
    assert t is None and why == S.DOJI


def test_an_entry_that_gaps_past_the_trigger_fills_at_the_open():
    """You cannot buy at 10.60 on a bar that opened at 10.90."""
    t, why = run(UP_RANGE + [(5, 10.9, 11.0, 10.85, 10.95)])
    assert why == S.OK and t.entry_px == pytest.approx(10.9)
    assert t.entry_px > t.or_high


def test_the_stop_sits_ten_percent_of_atr_from_the_fill():
    t, _ = run(UP_RANGE + [(5, 10.6, 10.7, 10.6, 10.65)], atr=2.0)
    assert t.stop_px == pytest.approx(10.6 - 0.2)
    assert t.r == pytest.approx(0.2)
    short, _ = run(DOWN_RANGE + [(5, 9.9, 9.95, 9.85, 9.9)], atr=2.0)
    assert short.stop_px == pytest.approx(9.9 + 0.2)


def test_the_protective_stop_gaps_through_too():
    """A bar that opens below the stop fills there, not at the stop price.
    Modelling it the other way flatters every fast reversal."""
    t, _ = run(UP_RANGE + [(5, 10.6, 10.7, 10.55, 10.6),
                           (6, 10.2, 10.25, 10.1, 10.15)], atr=1.0)
    assert t.stop_px == pytest.approx(10.5) and t.exit_reason == "stop"
    assert t.exit_px == pytest.approx(10.2), "the bar opened 30c below the stop"


def test_the_stop_is_live_on_the_entry_bar_under_the_registered_primary():
    """Amendment A. The entry bar's low can stop the trade out; the
    alternative is reported as a sensitivity and must differ here."""
    rows = UP_RANGE + [(5, 10.6, 10.75, 10.4, 10.7), (6, 10.7, 10.8, 10.65, 10.75)]
    strict, _ = run(rows, atr=1.0, stop_on_entry_bar=True)
    loose, _ = run(rows, atr=1.0, stop_on_entry_bar=False)
    assert strict.exit_reason == "stop" and strict.exit_px == pytest.approx(10.5)
    assert loose.exit_reason == "session_end" and loose.exit_px == pytest.approx(10.75)


def test_no_trigger_no_trade_and_the_reason_is_named():
    t, why = run(UP_RANGE + [(5, 10.4, 10.5, 10.3, 10.45),
                             (6, 10.45, 10.55, 10.4, 10.5)])
    assert t is None and why == S.NO_TRIGGER
    t2, why2 = run(UP_RANGE)
    assert t2 is None and why2 == S.NO_BARS_AFTER
    t3, why3 = run(UP_RANGE + [(5, 10.6, 10.7, 10.5, 10.6)], atr=float("nan"))
    assert t3 is None and why3 == S.NO_ATR


def test_a_missing_0930_bar_still_builds_the_range_it_has():
    """No bar exists for a minute with no trade; the range is what printed."""
    t, why = run([(2, 10.0, 10.3, 9.9, 10.2), (4, 10.2, 10.4, 10.1, 10.3),
                  (5, 10.3, 10.5, 10.3, 10.45)])
    assert why == S.OK and t.or_high == 10.4


# --------------------------------------------------------------------------
# friction: section 3.3
# --------------------------------------------------------------------------

def a_trade(reason="session_end", entry=10.0, exit_=10.20, side=S.LONG):
    return S.Trade("AAA", DAY, side, M0 + 5, entry, M0 + 200, exit_, reason,
                   entry - side * 0.05, 0.05, 195, 10.0, 9.5)


def test_paper_friction_charges_only_the_papers_commission():
    t = a_trade()
    assert S.net(t, 100, S.PAPER) == pytest.approx(20.0 - 0.35 * 2, abs=1e-9)


def test_base_friction_charges_slippage_on_both_legs_and_more_on_a_stop():
    t = a_trade()
    close_exit = S.net(t, 100, S.BASE)
    stopped = S.net(a_trade(reason="stop", exit_=9.95), 100, S.BASE)
    # entry 1c worse, close exit 1c worse -> 2c of the 20c move
    assert close_exit < 20.0 - 2.0
    # the same move stopped out pays 1c + 2c
    assert stopped < S.net(a_trade(reason="stop", exit_=9.95), 100, S.PAPER) - 2.9


def test_harsh_is_worse_than_base_is_worse_than_paper_on_the_same_trade():
    t = a_trade()
    vals = [S.net(t, 100, f) for f in (S.PAPER, S.BASE, S.HARSH)]
    assert vals[0] > vals[1] > vals[2]


def test_slippage_hurts_a_short_in_the_other_direction():
    """A short sells at entry and buys back at exit, so the signs flip. A
    model that charged the same arithmetic both ways would pay a short to be
    slipped."""
    long_t = a_trade(side=S.LONG, entry=10.0, exit_=10.2)
    short_t = a_trade(side=S.SHORT, entry=10.2, exit_=10.0)
    assert S.net(long_t, 100, S.PAPER) == pytest.approx(S.net(short_t, 100, S.PAPER))
    assert S.net(short_t, 100, S.BASE) < S.net(short_t, 100, S.PAPER)


def test_the_net_of_a_flat_trade_is_the_cost_of_trading_it():
    t = a_trade(entry=10.0, exit_=10.0)
    assert S.net(t, 100, S.BASE) < 0 and S.net(t, 100, S.PAPER) == pytest.approx(-0.7)


def test_the_entry_bars_open_cannot_be_the_stops_fill():
    """Amendment D. The entry bar opened at 10.30, broke 10.60 (the trigger)
    and traded down to 10.45. The stop is 10.50. The position was opened
    inside that bar at 10.60, so 10.30 is a price from before the order
    existed: filling the stop there books a loss the trade could not have
    taken. On the entry bar the stop fills AT the stop."""
    rows = UP_RANGE + [(5, 10.30, 10.75, 10.45, 10.55),
                       (6, 10.55, 10.6, 10.5, 10.55)]
    t, why = run(rows, atr=1.0)
    assert why == S.OK and t.entry_px == pytest.approx(10.6)
    assert t.exit_reason == "stop" and t.exit_min == M0 + 5
    assert t.exit_px == pytest.approx(10.5), "not 10.30, the pre-entry open"


def test_a_later_bar_still_gaps_through_the_stop():
    """The rule narrows to the entry bar only: on any later bar the open is
    after the entry, so a gap through the stop is real."""
    rows = UP_RANGE + [(5, 10.6, 10.7, 10.58, 10.65),
                       (6, 10.20, 10.25, 10.1, 10.15)]
    t, _ = run(rows, atr=1.0)
    assert t.exit_reason == "stop" and t.exit_px == pytest.approx(10.2)


def test_a_short_on_the_entry_bar_fills_at_its_stop_too():
    rows = DOWN_RANGE + [(5, 10.05, 10.15, 9.85, 9.95)]
    t, why = run(rows, atr=1.0)
    assert why == S.OK and t.entry_px == pytest.approx(9.9)
    assert t.stop_px == pytest.approx(10.0)
    assert t.exit_reason == "stop" and t.exit_px == pytest.approx(10.0)
