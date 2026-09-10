#!/usr/bin/env python3
"""Fixed-cent stops against the percentage trail.

Ben's handover calls this the single largest decision in the Warrior set --
every other parameter scales from the stop. So the guards matter more than the
headline: a pinned primary, a boundary check on the stated range, both halves,
and drop-top-3.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import cent_stop_study as C
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def t(net, entry=5.0, date_="2026-01-01", sym="AAA"):
    return (sym, date_, SimpleNamespace(net=net, entry_price=entry))


# --- the engine change -------------------------------------------------------

def frame(closes, lows=None, start="2026-03-02 04:00"):
    n = len(closes)
    highs = [c * 1.002 for c in closes]
    lows = lows or [c * 0.998 for c in closes]
    vols = [5000.0] * n
    for i in range(60, n, 10):
        vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": vols}, index=idx)


def uptrend(n=160):
    return [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
            for i in range(n)]


def test_the_default_is_still_the_percentage_trail():
    """No cents given must be byte-identical to the shipped rule, or every
    published figure silently moves."""
    df = frame(uptrend())
    a = MCL.backtest_session(df, date(2026, 3, 2), ET, **{"use_apex": False,
                                                          "require_macd_pos": True})
    b = MCL.backtest_session(df, date(2026, 3, 2), ET, trail_cents=None,
                             use_apex=False, require_macd_pos=True)
    assert [(x.entry_price, x.exit_price) for x in a] == \
           [(x.entry_price, x.exit_price) for x in b]


def test_a_cent_stop_is_a_fixed_distance_below_the_peak():
    """The whole point: 15c is 15c whatever the price, where 5% is not."""
    df = frame(uptrend())
    got = MCL.backtest_session(df, date(2026, 3, 2), ET, trail_cents=0.15,
                               use_apex=False, require_macd_pos=True)
    pct = MCL.backtest_session(df, date(2026, 3, 2), ET,
                               use_apex=False, require_macd_pos=True)
    assert got and pct
    # On a $3-5 name, 15c is TIGHTER than 5%, so the cent stop must exit no
    # later than the percentage one.
    assert got[0].bars_held <= pct[0].bars_held


def test_a_cent_stop_can_only_tighten_never_widen():
    """A 'cap' that sometimes widened the stop would be a different change
    wearing the same name."""
    df = frame(uptrend())
    tight = MCL.backtest_session(df, date(2026, 3, 2), ET, trail_cents=0.05,
                                 use_apex=False, require_macd_pos=True)
    wide = MCL.backtest_session(df, date(2026, 3, 2), ET, trail_cents=5.00,
                                use_apex=False, require_macd_pos=True)
    assert tight[0].bars_held <= wide[0].bars_held


# --- the pinned parameters ---------------------------------------------------

def test_the_primary_is_his_stated_most_used_value():
    """Pinned before running. 15c is what he says he uses, not what won."""
    assert C.PRIMARY_CENTS == 0.15
    assert C.BOUNDARY_CENTS == (0.10, 0.20)


def test_the_equivalence_line_states_the_whole_argument():
    line = " ".join(C.equivalent_pct(0.15))
    assert "7.50% at $2" in line and "0.75% at $20" in line


# --- the price-band table ----------------------------------------------------

def test_trades_are_bucketed_by_entry_price():
    """A fixed distance and a percentage diverge across the band by
    construction, so a single total describes nothing."""
    got = dict(C.by_price([t(10, entry=2.5), t(20, entry=15.0),
                           t(-5, entry=15.0)]))
    assert got["$2-4"]["n"] == 1
    assert got["$12-20"]["n"] == 2


def test_an_empty_band_is_omitted_rather_than_shown_as_zero():
    assert [n for n, _ in C.by_price([t(1, entry=3.0)])] == ["$2-4"]


def test_buckets_do_not_double_count():
    rows = [t(1, entry=p) for p in (2.0, 3.9, 4.0, 6.9, 7.0, 11.9, 12.0, 19.9)]
    assert sum(s["n"] for _, s in C.by_price(rows)) == len(rows)


# --- the guards --------------------------------------------------------------

def report(variants):
    return "\n".join(C.render(variants, 373))


def base(net, **kw):
    return [t(net, **kw)]


def test_a_sign_flip_between_halves_is_called_out():
    v = [("5% trail", [t(10, date_="2020-01-01"), t(10, date_="2030-01-01")]),
         ("15c stop", [t(40, date_="2020-01-01"), t(-40, date_="2030-01-01")])]
    assert "SIGN FLIPS" in report(v)


def test_a_win_on_the_total_but_not_drop_top_three_is_not_adoptable():
    v = [("5% trail", [t(1)] * 20),
         ("15c stop", [t(500), t(500), t(500)] + [t(-20)] * 17)]
    text = report(v)
    assert "NOT adoptable" in text or "Not adoptable" in text


def test_the_boundary_check_fires_when_the_best_cell_is_at_an_edge():
    """If the best value sits at the end of his stated range, the range is in
    the wrong place and none of the three should be adopted."""
    v = [("5% trail", [t(1)] * 10), ("10c stop", [t(-5)] * 10),
         ("15c stop", [t(-2)] * 10), ("20c stop", [t(50)] * 10)]
    assert "BOUNDARY CHECK FAILED" in report(v)


def test_the_boundary_check_stays_quiet_when_the_best_is_interior():
    v = [("5% trail", [t(1)] * 10), ("10c stop", [t(-5)] * 10),
         ("15c stop", [t(50)] * 10), ("20c stop", [t(-2)] * 10)]
    assert "BOUNDARY CHECK FAILED" not in report(v)


def test_a_loss_says_what_it_costs_the_rest_of_the_warrior_set():
    """Targets, share count and the 2:1 ratio all scale from the stop. A
    result that killed the cent stop without saying so would leave four
    documents quietly resting on it."""
    v = [("5% trail", [t(100)] * 10), ("15c stop", [t(-100)] * 10)]
    text = report(v)
    assert "WORSE" in text and "2:1 ratio" in text


def test_the_report_says_this_is_not_actually_his_stop():
    """His is min(pullback low, 10-20c) and does not trail. Reading this as a
    test of his rule would reject a strategy that was never run."""
    text = report([("5% trail", [t(1)] * 5), ("15c stop", [t(1)] * 5)])
    assert "It is not his stop" in text
    assert "structure stop with a cents CAP" in text


def test_the_report_says_nothing_here_is_out_of_sample():
    text = report([("5% trail", [t(1)] * 5), ("15c stop", [t(1)] * 5)])
    assert "out of sample" in text


# --- the arithmetic, pinned directly ----------------------------------------
# Three mutations of the inline version survived a synthetic-frame test: the
# cents branch removed entirely, the sign flipped, and `is not None` weakened
# to a truth test. All three change the stop and none changed the exit bar on
# the fixture. The claim is the arithmetic, so assert the arithmetic.

def test_the_percentage_stop_is_a_fraction_of_the_peak():
    assert MCL.stop_level(10.00, 5.0) == pytest.approx(9.50)
    assert MCL.stop_level(3.50, 5.0) == pytest.approx(3.325)


def test_the_cent_stop_is_a_fixed_distance_below_the_peak():
    assert MCL.stop_level(3.50, 5.0, 0.15) == pytest.approx(3.35)
    assert MCL.stop_level(18.00, 5.0, 0.15) == pytest.approx(17.85)


def test_cents_are_subtracted_not_added():
    """A sign flip would put the stop ABOVE the peak and exit every trade on
    its entry bar — which reads as 'the cent stop is catastrophic' rather than
    as a bug."""
    assert MCL.stop_level(5.00, 5.0, 0.15) < 5.00


def test_the_cents_branch_is_taken_at_all():
    """15c at $18 is 0.83%; 5% is 90c. If the cents argument were ignored the
    two would differ by more than a dollar and the study would be comparing
    the percentage trail with itself."""
    assert MCL.stop_level(18.00, 5.0, 0.15) != pytest.approx(
        MCL.stop_level(18.00, 5.0))
    assert MCL.stop_level(18.00, 5.0, 0.15) - MCL.stop_level(18.00, 5.0) \
        == pytest.approx(0.75)


def test_zero_cents_means_a_stop_at_the_peak_not_a_fallback():
    """`is not None`, deliberately. A zero that silently reverted to the
    percentage rule would make the tightest cell in a sweep secretly the
    loosest — and the sweep would report it as a win."""
    assert MCL.stop_level(5.00, 5.0, 0.0) == pytest.approx(5.00)
    assert MCL.stop_level(5.00, 5.0, 0.0) != pytest.approx(
        MCL.stop_level(5.00, 5.0))


def test_a_tighter_cent_value_is_never_a_looser_stop():
    levels = [MCL.stop_level(5.00, 5.0, c) for c in (0.05, 0.10, 0.20)]
    assert levels == sorted(levels, reverse=True)


def uptrend_then_crash(n=150, tail=25):
    """Rises, then collapses. The plain uptrend NEVER stops out — it exits on
    window_close — so a test asserting 'window_close' against it passes
    whatever the walk does. That fixture hid this exact defect once."""
    up = uptrend(n)
    last = up[-1]
    return up + [round(last * (0.97 ** (i + 1)), 4) for i in range(tail)]


def test_the_fixture_actually_stops_out():
    """Guarding the guard. If this ever exits on the window instead, the test
    below stops testing anything and says nothing about it."""
    tr = MCL.backtest_session(frame(uptrend_then_crash()), date(2026, 3, 2),
                              ET, use_apex=False, require_macd_pos=True)
    assert tr and tr[0].reason == "trailing_stop"


def test_the_walk_uses_the_same_function_it_advertises():
    """A shared helper proves nothing if backtest_session stopped calling it.
    Monkeypatch the helper to a level nothing can reach and the trade must
    ride to the window instead of stopping."""
    import unittest.mock as mock

    df = frame(uptrend_then_crash())
    kw = dict(use_apex=False, require_macd_pos=True)
    with mock.patch.object(MCL, "stop_level",
                           lambda peak, pct, cents=None: 0.0):
        never_stops = MCL.backtest_session(df, date(2026, 3, 2), ET, **kw)
    assert never_stops
    assert never_stops[0].reason == "window_close", (
        "a stop at zero can never trigger, so the walk must ride to the "
        "window — if it still stops out, the walk is not calling stop_level")
