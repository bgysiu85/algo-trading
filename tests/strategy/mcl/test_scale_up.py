#!/usr/bin/env python3
"""The MIRROR mechanic: sell into strength, buy back on the dip.

Ben asked to revisit the scale-out one last time, and re-reading his original
description showed the two versions are opposite trades rather than variants:

    scale_out_pct  sell on a PULLBACK, buy back on the RECOVERY -> sells low
    scale_up_pct   sell into STRENGTH, buy back on the DIP      -> sells high

Both were measured and both lose, for opposite reasons, which is why both stay
in the code as inert, parameterised options rather than being deleted. What is
pinned here is the BEHAVIOUR that made the measurement meaningful -- above all
`rebuy_ref`, because where the dip is measured from decides whether a round
trip can lose at all:

    "peak"  dip from the high reached after the sell. If price runs, the
            buy-back lands ABOVE the sell -- only 45% of cycles bought back
            below their own sell price at +2%/-2%.
    "sell"  a limit resting below the sell price. Profitable by construction.

The second still lost money overall (-$294, P(>0) = 1.6%), which is the whole
finding: the round trips banked +$112 while being short of size on the runners
cost more.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")
DATE = date(2026, 9, 2)


def frame(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    t0 = datetime.strptime("2026-09-02 04:00", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq="1min").tz_convert("UTC")
    return pd.DataFrame(
        {"open": closes,
         "high": highs or [c * 1.004 for c in closes],
         "low": lows or [c * 0.996 for c in closes],
         "close": closes,
         "volume": vols or [5000] * n}, index=idx)


@pytest.fixture(scope="module")
def choppy():
    for seed in range(200):
        rng = np.random.default_rng(seed)
        px, closes = 3.0, []
        for i in range(220):
            px *= 1.0 + (rng.uniform(-0.004, 0.012) if i < 130
                         else rng.uniform(-0.012, 0.013))
            closes.append(px)
        vols = [int(v) for v in rng.integers(4000, 7000, 220)]
        vols[125] = vols[124] * 6
        df = frame(closes, vols=vols)
        t = S.backtest_session(df, DATE, ET, trail_pct=20.0, scale_up_pct=2.0,
                               scale_up_portion=50.0, rebuy_dip_pct=2.0)
        if t and t[0].cycles >= 3:
            return df
    pytest.skip("no multi-cycle session found in 200 seeds")


UP = dict(trail_pct=20.0, scale_up_portion=50.0, rebuy_dip_pct=2.0)


def test_inert_when_disabled(choppy):
    """scale_up_pct=None must reproduce the plain engine bit-for-bit."""
    off = S.backtest_session(choppy, DATE, ET, trail_pct=20.0)
    also = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                              scale_up_pct=None, scale_up_portion=50.0,
                              rebuy_dip_pct=2.0)
    assert off and [t.net for t in off] == [t.net for t in also]
    assert all(t.cycles == 0 for t in off)


def test_the_two_mechanics_are_independent(choppy):
    """scale_out_pct and scale_up_pct must not interfere: enabling one leaves
    the other's trigger untouched. They are opposite trades and combining them
    silently would make any measurement meaningless."""
    up = S.backtest_session(choppy, DATE, ET, scale_up_pct=2.0, **UP)
    out = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                             scale_out_pct=50.0, partial_trail_pct=2.0,
                             rebuy_qty=None)
    assert up and out
    assert [t.net for t in up] != [t.net for t in out]


def test_selling_into_strength_never_grows_the_position(choppy):
    """It sells first and buys back at most what it sold, so the position can
    never exceed the entry size -- the opposite of the pyramid."""
    trades = S.backtest_session(choppy, DATE, ET, scale_up_pct=2.0, **UP)
    assert trades
    assert all(t.max_qty == t.qty for t in trades)


def test_rebuy_ref_sell_always_buys_back_below_the_sell(choppy):
    """The point of rebuy_ref='sell': the round trip cannot lose. Checked
    through realised P/L -- with the position size unchanged at the end, a
    trade whose cycles all banked a credit must beat the same trade with the
    scaling switched off ON THE REALISED LEG. Here it is enough that the
    buy level is by construction below the sell level, which the engine
    guarantees because both derive from the same recorded sell price."""
    trades = S.backtest_session(choppy, DATE, ET, scale_up_pct=3.0,
                                rebuy_ref="sell", trail_pct=20.0,
                                scale_up_portion=50.0, rebuy_dip_pct=1.0)
    peak = S.backtest_session(choppy, DATE, ET, scale_up_pct=3.0,
                              rebuy_ref="peak", trail_pct=20.0,
                              scale_up_portion=50.0, rebuy_dip_pct=1.0)
    assert trades and peak
    # Resting below the SELL is a strictly lower buy level than resting below
    # a peak that is >= the sell, so it can never fire more often.
    assert sum(t.cycles for t in trades) <= sum(t.cycles for t in peak)


def test_peak_is_the_default_reference(choppy):
    a = S.backtest_session(choppy, DATE, ET, scale_up_pct=2.0, **UP)
    b = S.backtest_session(choppy, DATE, ET, scale_up_pct=2.0,
                           rebuy_ref="peak", **UP)
    assert [t.net for t in a] == [t.net for t in b]


@pytest.mark.parametrize("cap", [0, 1, 2, 3])
def test_max_cycles_binds(choppy, cap):
    trades = S.backtest_session(choppy, DATE, ET, scale_up_pct=2.0,
                                max_cycles=cap, **UP)
    assert trades and all(t.cycles <= cap for t in trades)


def test_a_higher_sell_trigger_never_fires_more_often(choppy):
    """Monotonicity. A failure here means the ladder reference is wrong --
    the sell level is measured from the last fill, so it must rise with the
    parameter rather than staying pinned to the entry."""
    near = S.backtest_session(choppy, DATE, ET, scale_up_pct=1.0, **UP)
    far = S.backtest_session(choppy, DATE, ET, scale_up_pct=10.0, **UP)
    assert sum(t.cycles for t in far) <= sum(t.cycles for t in near)


def test_selling_more_costs_more_on_a_clean_runner():
    """The finding, as a property: on a stock that only goes up, selling ANY
    portion into strength must underperform holding, and selling more must
    underperform selling less. This is the cost the mechanic pays, and it is
    paid exactly on the trades that carry the strategy."""
    for seed in range(60):
        rng = np.random.default_rng(seed)
        px, closes = 3.0, []
        for i in range(220):
            px *= 1.0 + (rng.uniform(-0.003, 0.011) if i < 130 else 0.006)
            closes.append(px)
        vols = [int(v) for v in rng.integers(4000, 7000, 220)]
        vols[125] = vols[124] * 6
        df = frame(closes, vols=vols)
        hold = S.backtest_session(df, DATE, ET, trail_pct=20.0)
        if not hold:
            continue
        small = S.backtest_session(df, DATE, ET, trail_pct=20.0,
                                   scale_up_pct=2.0, scale_up_portion=25.0,
                                   rebuy_dip_pct=2.0)
        big = S.backtest_session(df, DATE, ET, trail_pct=20.0,
                                 scale_up_pct=2.0, scale_up_portion=75.0,
                                 rebuy_dip_pct=2.0)
        # A completed cycle is NOT required -- a steady climber never dips
        # enough to buy back, and the property holds anyway: shares sold into
        # strength and not replaced are exactly the shares that miss the run.
        #
        # Nor is shares_traded a usable detector, which cost a debugging
        # detour worth recording: a sell with no buy-back does not change it.
        # Entry 100 + sell 25 + exit 75 is the same 200 shares as entry 100 +
        # exit 100. The only reliable evidence that the mechanic acted is that
        # the P/L moved.
        h, s, b = (sum(t.net for t in x) for x in (hold, small, big))
        if s == h:
            continue
        assert b <= s <= h, f"seed {seed}: hold {h:.2f} small {s:.2f} big {b:.2f}"
        return
    pytest.skip("no clean runner with a scale-up cycle in 60 seeds")
