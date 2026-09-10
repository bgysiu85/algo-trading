#!/usr/bin/env python3
"""Cameron's exit — half at a target, breakeven stop on the rest.

warrior_0 §5.3 calls this the largest untested gap in the spec set. The tests
that matter are the inertness one (no target_exit must be bit-identical) and
the two that pin the mechanic's counter-intuitive shape: a breakeven stop is
LOOSER than a 5% trail on any trade up more than ~5.3%, so it holds longer, and
the cell that takes 0% still arms it.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import target_exit as TE
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
ENTRY_I = 80


def frame(closes):
    n = len(closes)
    vols = [5000.0] * n
    for i in range(60, n, 10):
        vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes], "close": closes,
                         "volume": vols}, index=idx)


def base(n=90):
    return [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
            for i in range(n)]


def run(px, **kw):
    return MCL.backtest_session(frame(px), date(2026, 3, 2), ET,
                                entry_shares=100, use_apex=False,
                                require_macd_pos=True, **kw)


def fade():
    """Up 16%, then a GRADUAL 0.5%/bar fade. Gradual matters: a collapse gaps
    through both the trail and breakeven on one bar and the two are then
    indistinguishable, which is how an earlier draft of this fixture reported
    the mechanic as inert when it was working."""
    b = base()
    up = [round(b[-1] * (1 + 0.012) ** k, 4) for k in range(1, 15)]
    down = [round(up[-1] * (1 - 0.005) ** k, 4) for k in range(1, 60)]
    return b + up + down


# --- the parameter ----------------------------------------------------------

def test_none_is_the_default_and_is_bit_identical():
    px = fade()
    a = run(px)
    b = run(px, target_exit=None)
    k = lambda ts: [(t.entry_time, t.exit_time, t.net, t.reason, t.qty)
                    for t in ts]
    assert k(a) == k(b)
    assert a, "the fixture produced no trades; this would pass vacuously"


def test_the_target_is_2R_against_the_five_percent_trail():
    """Derived per warrior_0 §5.2 -- his stated 2:1 re-posed against a
    percentage stop -- and NOT chosen because it wins."""
    assert TE.TARGET_PCT == 10.0
    assert MCL.TRAIL_PCT == 5.0
    assert TE.TARGET_PCT == 2 * MCL.TRAIL_PCT


def test_the_target_price_and_partial_size():
    te = TE.TargetExit()
    assert te.target_price(4.0) == pytest.approx(4.4)
    assert te.qty_at_target(100) == 50
    assert te.qty_at_target(25) == 12


def test_the_partial_never_takes_the_whole_position():
    """Taking 100% at the target is a fixed profit target, a different rule --
    and it would make the breakeven stop unreachable, so the two would be
    indistinguishable in the output."""
    te = TE.TargetExit(take_frac=100.0)
    for held in (2, 5, 100):
        assert te.qty_at_target(held) == held - 1
    assert te.qty_at_target(1) == 0


def test_take_frac_zero_is_a_real_cell_not_a_disabled_one():
    """It arms the breakeven WITHOUT selling, which is the cell that isolates
    the stop change from the partial. If it silently did nothing the 2x2 would
    have three cells and one duplicate."""
    px = fade()
    plain = run(px)[0]
    stop_only = run(px, target_exit=TE.TargetExit(take_frac=0.0))[0]
    assert TE.TargetExit(take_frac=0.0).qty_at_target(100) == 0
    assert stop_only.exit_price != plain.exit_price, (
        "take_frac=0 changed nothing, so the stop never moved")


# --- the shape that inverts the naive reading -------------------------------

def test_breakeven_is_LOOSER_than_the_trail_on_a_winner():
    """The finding that reframes the mechanic. Once a trade is up more than
    ~5.3%, the entry price sits BELOW a 5% trail from the peak, so moving the
    stop to breakeven gives the remainder MORE room, not less. It is not risk
    reduction; it is a very wide stop plus a certain half."""
    px = fade()
    trailed = run(px, target_exit=TE.TargetExit(breakeven=False))[0]
    be = run(px, target_exit=TE.TargetExit())[0]
    assert be.bars_held > trailed.bars_held, "breakeven should hold LONGER"
    assert be.exit_price < trailed.exit_price, "and exit LOWER on a fade"


def test_the_partial_is_what_saves_the_trade_not_the_stop():
    """On the same fade: breakeven alone gives the whole move back; breakeven
    plus the partial keeps the target gain. This is the attribution the 2x2
    exists to make, pinned on one trade."""
    px = fade()
    stop_only = run(px, target_exit=TE.TargetExit(take_frac=0.0))[0]
    cameron = run(px, target_exit=TE.TargetExit())[0]
    assert stop_only.net < 0 < cameron.net


def test_the_target_is_tested_against_the_close_not_the_high():
    """A target tagged only by a bar's high is one the strategy could not have
    acted on. More sensitive here than for the trail, because a target is a
    level price runs THROUGH rather than one it settles below."""
    import inspect
    src = inspect.getsource(MCL.backtest_session)
    i = src.index("target_exit.target_price")
    assert 'row["close"]' in src[max(0, i - 200):i], (
        "the target must be compared against the close")


def test_the_trailing_stop_still_wins_on_a_shared_bar():
    """A bar that reaches the target AND trips the stop resolves as the stop."""
    b = base()
    px = b + [round(b[-1] * 1.15, 4)] + [round(b[-1] * 0.70, 4)] * 40
    t = run(px, target_exit=TE.TargetExit())[0]
    assert t.reason == "trailing_stop"
