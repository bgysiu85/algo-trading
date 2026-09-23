#!/usr/bin/env python3
"""strategy/orb/tensec_engine.py on hand-built 1-second bars.

W05-0003, `docs/research/REGISTERED_10sec.md` G3: every case here is a rule
from section 3, and each is written so that reverting the rule changes the
number or the verdict. B0's cases mirror `test_orb_sip_engine.py` one
resolution down (the point of G2); T1's cases are new to this study --
the completed-close trigger, the next-second fill, the fill-second stop
convention, and the 15:59:00 cutoff.

Seconds are given as offsets from 09:35:00 (`T0`, the end of the 5-minute
opening range) unless a test needs a specific clock time (the 15:59:00
boundary cases).
"""
from __future__ import annotations

import pytest

from strategy.orb import tensec_engine as E

T0 = E.RANGE_END_SEC          # 09:35:00
LONG, SHORT = E.LONG, E.SHORT


def run_b0(rows, side=LONG, or_high=10.6, or_low=9.9, r=0.2):
    """rows: (second_offset_from_T0, o, h, l, c)."""
    sod = [T0 + row[0] for row in rows]
    return E.b0_trade(sod, [r_[1] for r_ in rows], [r_[2] for r_ in rows],
                      [r_[3] for r_ in rows], [r_[4] for r_ in rows],
                      side, or_high, or_low, r)


def run_t1(rows, side=LONG, or_high=10.6, or_low=9.9, r=0.2, base=T0):
    """rows: (second_offset_from `base`, o, h, l, c). `base` lets the
    15:59:00-boundary tests place seconds at an absolute clock time."""
    sod = [base + row[0] for row in rows]
    return E.t1_trade(sod, [r_[1] for r_ in rows], [r_[2] for r_ in rows],
                      [r_[3] for r_ in rows], [r_[4] for r_ in rows],
                      side, or_high, or_low, r)


# ---------------------------------------------------------------------------
# B0 -- the baseline, one resolution down. Mirrors sip.py's own tests.
# ---------------------------------------------------------------------------

def test_b0_long_enters_the_first_printed_second_that_reaches_the_level():
    t, why = run_b0([(0, 10.50, 10.55, 10.48, 10.52),
                     (1, 10.55, 10.62, 10.50, 10.58),
                     (2, 10.65, 10.70, 10.60, 10.68)])
    assert why == E.OK and t.side == LONG
    assert t.entry_sec == T0 + 1 and t.entry_px == pytest.approx(10.6)
    assert t.exit_reason == "session_end" and t.exit_px == pytest.approx(10.68)


def test_b0_an_entry_that_gaps_past_the_level_fills_at_the_open():
    t, why = run_b0([(0, 10.90, 11.00, 10.85, 10.95)])
    assert why == E.OK
    assert t.entry_px == pytest.approx(10.9) and t.entry_px > 10.6
    assert t.stop_px == pytest.approx(10.9 - 0.2), \
        "the stop is off the EXECUTED fill, not the level"


def test_b0_stop_on_the_entry_second_fills_at_the_stop_price_not_the_open():
    """Amendment D, one resolution down. The entry second's own low reaches
    the stop; the fill is the stop price, never that second's own open
    (10.30, well below the stop) and never the low it reached (10.45)."""
    t, why = run_b0([(0, 10.30, 10.65, 10.45, 10.55)], r=0.1)
    assert why == E.OK
    assert t.entry_px == pytest.approx(10.6), "the level, not that second's open"
    assert t.stop_px == pytest.approx(10.5)
    assert t.exit_reason == "stop" and t.exit_sec == T0
    assert t.exit_px == pytest.approx(10.5), \
        "not 10.45 (the low) and not 10.30 (that second's open)"


def test_b0_a_later_second_gaps_through_the_stop():
    t, why = run_b0([(0, 10.60, 10.65, 10.55, 10.60),
                     (1, 10.30, 10.35, 10.20, 10.25)], r=0.1)
    assert why == E.OK
    assert t.stop_px == pytest.approx(10.5) and t.exit_reason == "stop"
    assert t.exit_px == pytest.approx(10.3), "the second opened 20c below the stop"


def test_b0_short_side_mirrors_long():
    t, why = run_b0([(0, 9.95, 9.97, 9.85, 9.90),
                     (1, 9.90, 9.95, 9.85, 9.88)], side=SHORT, r=0.1)
    assert why == E.OK and t.side == SHORT
    assert t.entry_px == pytest.approx(9.9) and t.stop_px == pytest.approx(10.0)
    assert t.exit_reason == "session_end" and t.exit_px == pytest.approx(9.88)


def test_b0_no_trigger_no_trade():
    t, why = run_b0([(0, 10.40, 10.50, 10.30, 10.45),
                     (1, 10.45, 10.55, 10.40, 10.50)])
    assert t is None and why == E.NO_TRIGGER


def test_b0_one_entry_per_symbol_day_the_first_stop_wins():
    """A bug that kept scanning after the stop would find the later
    recross and misreport it. The function returns on the first exit."""
    t, why = run_b0([(0, 10.60, 10.65, 10.58, 10.60),   # entry
                     (1, 10.30, 10.35, 10.20, 10.25),   # stop, gapped
                     (2, 10.90, 11.20, 10.85, 11.10)],  # a later recross -- ignored
                     r=0.1)
    assert why == E.OK
    assert t.exit_reason == "stop" and t.exit_sec == T0 + 1
    assert t.exit_px == pytest.approx(10.3)


# ---------------------------------------------------------------------------
# T1 -- H-X1, the 10-second confirmation trigger. New to this study.
# ---------------------------------------------------------------------------

def test_t1_needs_a_completed_close_not_a_wick():
    """The first 10-second bucket wicks to 10.80 but closes at 10.55 --
    below the level -- and must not trigger. The second bucket closes at
    10.70, above the level, and triggers there."""
    t, why = run_t1([
        (0, 10.50, 10.55, 10.45, 10.50), (5, 10.50, 10.80, 10.50, 10.55),
        (10, 10.60, 10.75, 10.60, 10.70),
        (20, 10.72, 10.80, 10.65, 10.75),
    ])
    assert why == E.OK
    assert t.trigger_sec == T0 + 10, "the wicking bucket at T0 must not have triggered"


def test_t1_an_exact_equal_close_does_not_trigger():
    """'Strictly beyond' -- a close AT the level is not a trigger, in either
    of two separate 10-second buckets."""
    t, why = run_t1([(0, 10.50, 10.65, 10.45, 10.60),   # bucket 1: closes exactly AT 10.6
                     (10, 10.60, 10.61, 10.59, 10.60)])  # bucket 2: still exactly at it
    assert t is None and why == E.NO_TRIGGER


def test_t1_fill_is_the_next_printed_seconds_open_never_the_trigger_bars_own_price():
    t, why = run_t1([
        (0, 10.60, 10.75, 10.60, 10.70),      # trigger bucket, closes 10.70
        (10, 10.72, 10.80, 10.65, 10.75),     # first print at/after the bucket ends
    ])
    assert why == E.OK
    assert t.entry_px == pytest.approx(10.72), \
        "must be the next second's open -- not 10.6 (level), 10.7 (trigger close) or 10.75 (its close)"


def test_t1_stop_is_off_the_executed_fill_not_the_level():
    t, why = run_t1([
        (0, 10.60, 10.75, 10.60, 10.70),
        (10, 10.72, 10.80, 10.65, 10.75),
    ], r=0.2)
    assert why == E.OK
    assert t.stop_px == pytest.approx(10.52), "10.72 - 0.2, not 10.6 - 0.2"


def test_t1_fill_second_stop_fills_at_the_stop_price_not_the_open():
    """The fill second's own low reaches the stop; the exit is the stop
    price, not that second's open and not its low."""
    t, why = run_t1([
        (0, 10.60, 10.75, 10.60, 10.70),
        (10, 10.72, 10.80, 10.40, 10.60),   # low 10.40 reaches the r=0.2 stop
    ], r=0.2)
    assert why == E.OK
    assert t.stop_px == pytest.approx(10.52)
    assert t.exit_reason == "stop" and t.exit_sec == t.entry_sec
    assert t.exit_px == pytest.approx(10.52), "not 10.40 (the low), not 10.72 (the open)"


def test_t1_stops_gap_through_after_the_fill_second():
    t, why = run_t1([
        (0, 10.60, 10.75, 10.60, 10.70),
        (10, 10.72, 10.80, 10.60, 10.70),   # fill second: no stop hit
        (11, 10.30, 10.35, 10.20, 10.25),   # next second gaps below the stop
    ], r=0.2)
    assert why == E.OK
    assert t.stop_px == pytest.approx(10.52) and t.exit_reason == "stop"
    assert t.exit_px == pytest.approx(10.3), "gapped, not the 10.52 stop price"


def test_t1_short_side_mirrors_long():
    t, why = run_t1([
        (0, 9.90, 9.90, 9.75, 9.80),          # closes 9.80, below 9.9 -> triggers
        (10, 9.78, 9.85, 9.70, 9.75),
    ], side=SHORT, or_high=10.6, or_low=9.9, r=0.2)
    assert why == E.OK
    assert t.entry_px == pytest.approx(9.78) and t.stop_px == pytest.approx(9.98)


def test_t1_no_entry_when_the_trigger_bar_ends_after_15_59_00():
    """The bucket [15:59:00, 15:59:10) ends after 15:59:00 -- rejected
    outright, before the engine even looks for a second to fill on."""
    fifteen_59_01 = 15 * 3600 + 59 * 60 + 1
    t, why = E.t1_trade([fifteen_59_01], [10.60], [10.65], [10.55], [10.70],
                        LONG, 10.6, 9.9, 0.2)
    assert t is None and why == E.TOO_LATE


def test_t1_a_trigger_bar_ending_exactly_at_15_59_00_is_still_allowed():
    """The bucket [15:58:50, 15:59:00) ends AT 15:59:00, not after it."""
    fifteen_58_51 = 15 * 3600 + 58 * 60 + 51            # bucket start 15:58:50
    fifteen_59_00 = 15 * 3600 + 59 * 60                 # the fill second
    t, why = E.t1_trade([fifteen_58_51, fifteen_59_00],
                        [10.60, 10.72], [10.65, 10.80], [10.55, 10.65],
                        [10.70, 10.75], LONG, 10.6, 9.9, 0.2)
    assert why == E.OK, "the trigger bucket ends AT 15:59:00, not after it"
    assert t.entry_sec == fifteen_59_00


def test_t1_no_bar_after_the_trigger_returns_no_trade():
    """The trigger bucket is the last printed second of the day -- there is
    no next second to fill on."""
    t, why = run_t1([(0, 10.60, 10.75, 10.60, 10.70)])
    assert t is None and why == E.NO_BAR_AFTER_TRIGGER
