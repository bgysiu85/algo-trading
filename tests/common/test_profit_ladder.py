#!/usr/bin/env python3
"""The take-profit ladder, and the two strategies it plugs into.

Ben, 2026-09-10: "for every 10% increase, sell 50% of shares until when 20
shares or less, sell them all."

The headline tests are the two INERTNESS ones: with no ladder, both engines
must be bit-identical to what they were. Every published figure in this project
comes from that path, and a mechanic that shifts it by a cent has silently
moved all of them.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import profit_ladder as PL
from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
CFG = PL.LadderConfig()


# --- the rung arithmetic ----------------------------------------------------

def test_rungs_compound_from_the_previous_rung():
    """Ben's choice, 2026-09-10: 'every 10% increase' means 10% above the LAST
    rung, not 10% of entry. Rungs are 1.10x, 1.21x, 1.331x, 1.4641x."""
    got = [round(PL.rung_price(4.0, n), 4) for n in range(1, 5)]
    assert got == [4.4, 4.84, 5.324, 5.8564]


def test_the_linear_control_is_a_different_ladder():
    """If it were not, having it would prove nothing."""
    lin = PL.LadderConfig(linear=True)
    assert [round(PL.rung_price(4.0, n, lin), 4) for n in range(1, 5)] \
        == [4.4, 4.8, 5.2, 5.6]
    assert PL.rung_price(4.0, 4) > PL.rung_price(4.0, 4, lin)


def test_rungs_are_numbered_from_one():
    with pytest.raises(ValueError):
        PL.rung_price(4.0, 0)


# --- the share ladder -------------------------------------------------------

def test_the_hundred_share_ladder_is_the_one_ben_described():
    """50 / 25 / 12 / 13, fully out at +46.4%. The third rung truncates to 12
    and NOT 13 -- rounding up on every rung would eventually oversell."""
    held, done, out = 100, 0, []
    for n in range(1, 8):
        q, used = PL.plan(4.0, PL.rung_price(4.0, n), held, done)
        if q == 0:
            break
        out.append(q)
        held -= q
        done += used
    assert out == [50, 25, 12, 13]
    assert held == 0


def test_the_floor_takes_the_whole_remainder():
    """At or below 20 the next rung closes it. Leaving a 6-then-3 share tail
    pays IBKR's per-order minimum twice for almost no stock."""
    assert PL.sell_qty(20) == 20
    assert PL.sell_qty(13) == 13
    assert PL.sell_qty(21) == 10


def test_it_never_oversells():
    for held in range(0, 205):
        assert 0 <= PL.sell_qty(held) <= held


def test_a_fraction_that_truncates_to_zero_still_advances():
    """A 1% fraction on 40 shares truncates to 0. Returning 0 above the floor
    would stall the ladder forever while the caller kept advancing the rung."""
    assert PL.sell_qty(40, PL.LadderConfig(sell_frac=1.0)) == 1


# --- the bar-level plan -----------------------------------------------------

def test_one_bar_can_clear_two_rungs():
    """A 5-minute bar or a gap can jump two rungs. Counting it as one would
    leave the ladder permanently behind the price, quietly turning the rule
    into 'sell half every bar while rising'."""
    q, used = PL.plan(4.0, 4.9, 100, 0)      # 4.9 clears 4.40 and 4.84
    assert used == 2
    assert q == 50, "two rungs in one bar must still sell ONCE, at one price"


def test_below_the_first_rung_nothing_happens():
    assert PL.plan(4.0, 4.39, 100, 0) == (0, 0)


def test_a_rung_already_taken_does_not_fire_again():
    assert PL.plan(4.0, 4.5, 50, 1) == (0, 0)


@pytest.mark.parametrize("held,entry", [(0, 4.0), (100, 0.0), (-5, 4.0)])
def test_degenerate_inputs_do_nothing(held, entry):
    assert PL.plan(entry, 9.0, held, 0) == (0, 0)


# --- INERTNESS: the tests that protect every published figure ---------------

def frame_mcl(n=160):
    closes = [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
              for i in range(n)]
    vols = [5000.0] * n
    for i in range(60, n, 10):
        vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes], "close": closes,
                         "volume": vols}, index=idx)


def key(trades):
    return [(t.entry_time, t.exit_time, t.entry_price, t.exit_price,
             t.qty, t.reason, t.gross, t.commission, t.net) for t in trades]


def test_mcl_with_no_ladder_is_bit_identical():
    df = frame_mcl()
    a = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                             use_apex=False, require_macd_pos=True)
    b = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                             use_apex=False, require_macd_pos=True, ladder=None)
    assert key(a) == key(b)
    assert a, "the fixture produced no trades; this would pass vacuously"


def test_mc5_with_no_ladder_is_bit_identical():
    """MC5's exit accounting was REWRITTEN to support partial sells -- it now
    accumulates realised P/L and commission rather than computing both at the
    exit. With no ladder those accumulators must reproduce the old arithmetic
    exactly, and this is the only thing standing between that refactor and
    every MC5 figure moving underneath us."""
    df = frame_mcl(400)
    a = MC5.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100)
    b = MC5.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                             ladder=None)
    assert key(a) == key(b)
    assert a, "the fixture produced no trades; this would pass vacuously"


def test_the_ladder_default_is_none_on_both():
    import inspect
    for mod in (MCL, MC5):
        assert inspect.signature(mod.backtest_session).parameters["ladder"].default is None


# --- the ladder actually firing, on a fixture built to reach the rungs ------

def ramp(entry_bars=90, n=60, step=0.02):
    """Flat warm-up, then a clean climb, so the rungs are certain to be hit."""
    base = [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
            for i in range(entry_bars)]
    last = base[-1]
    closes = base + [round(last * (1 + step) ** k, 4) for k in range(1, n + 1)]
    m = len(closes)
    vols = [5000.0] * m
    for i in range(60, m, 10):
        vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(m)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes], "close": closes,
                         "volume": vols}, index=idx)


def test_a_runner_exits_through_the_ladder_not_the_trail():
    df = ramp()
    out = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                               use_apex=False, require_macd_pos=True,
                               ladder=CFG)
    laddered = [t for t in out if t.reason == "profit_ladder"]
    assert laddered, "the ramp never completed a ladder; fixture is too short"
    t = laddered[0]
    assert t.qty == 100, "qty must report the ORIGINAL size, not the last slice"
    assert t.net > 0


def test_the_trailing_stop_still_wins_on_a_shared_bar():
    """A bar that both clears a rung and trips the stop is the STOP. A ladder
    that outranked it would book part of the position at a rung and the rest at
    a stop the trade had already hit -- two better fills than it got."""
    df = ramp()
    px = list(df["close"])
    # Run up past two rungs, then collapse through the trail on one bar.
    cut = 100
    for i in range(cut, len(px)):
        px[i] = px[cut - 1] * 0.80
    df2 = df.copy()
    df2["close"] = px
    df2["open"] = px
    df2["low"] = [p * 0.998 for p in px]
    df2["high"] = [p * 1.002 for p in px]
    out = MCL.backtest_session(df2, date(2026, 3, 2), ET, entry_shares=100,
                               use_apex=False, require_macd_pos=True,
                               ladder=CFG)
    assert out and out[0].reason == "trailing_stop"


def test_shares_traded_counts_every_slice():
    """Commission is charged per ORDER, so a four-rung exit pays four minimums.
    A ladder whose accounting lost the slices would understate its own cost."""
    df = ramp()
    out = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                               use_apex=False, require_macd_pos=True,
                               ladder=CFG)
    t = [x for x in out if x.reason == "profit_ladder"][0]
    assert t.shares_traded >= 100


def test_the_ladder_costs_more_commission_than_holding():
    """Four exit orders against one. If this were not true the ladder would be
    free, and a free option is a sign the model is wrong."""
    df = ramp()
    plain = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                                 use_apex=False, require_macd_pos=True)
    lad = MCL.backtest_session(df, date(2026, 3, 2), ET, entry_shares=100,
                               use_apex=False, require_macd_pos=True,
                               ladder=CFG)
    assert lad[0].commission > plain[0].commission
