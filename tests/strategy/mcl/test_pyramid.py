#!/usr/bin/env python3
"""The pyramid (add on a recovered pullback, never sell) and entry_shares.

Distinct from the scale-out mechanic in tests/strategy/mcl/test_scale_out.py:
nothing is sold, so there is no sell-low / buy-back-higher cost. What has to
be pinned is that it is inert by default, that it only ever ADDS, that the
caps bind, and that `entry_shares` is a clean size override -- the last
matters because the whole study rests on comparing a pyramid against simply
STARTING at the size it builds to.
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
        t = S.backtest_session(df, DATE, ET, trail_pct=20.0,
                               pyramid_qty=100, pyramid_pullback_pct=2.0)
        if t and t[0].adds >= 3:
            return df
    pytest.skip("no multi-add session found in 200 seeds")


PY = dict(trail_pct=20.0, pyramid_pullback_pct=2.0)


def test_pyramid_is_inert_by_default(choppy):
    off = S.backtest_session(choppy, DATE, ET, trail_pct=20.0)
    assert off
    assert all(t.adds == 0 for t in off)
    assert all(t.max_qty == t.qty for t in off)
    assert all(t.shares_traded == 2 * t.qty for t in off)


def test_pyramid_only_ever_adds(choppy):
    """It must never reduce the position: max_qty is entry + adds x qty, and
    shares transacted is exactly entry + every add + the single final exit."""
    trades = S.backtest_session(choppy, DATE, ET, pyramid_qty=100, **PY)
    assert trades
    for t in trades:
        assert t.max_qty == t.qty + 100 * t.adds
        assert t.shares_traded == t.qty + 100 * t.adds + t.max_qty


@pytest.mark.parametrize("cap", [0, 1, 2, 3])
def test_max_adds_binds(choppy, cap):
    trades = S.backtest_session(choppy, DATE, ET, pyramid_qty=100,
                                max_adds=cap, **PY)
    assert trades
    assert all(t.adds <= cap for t in trades)


def test_max_position_shares_binds(choppy):
    trades = S.backtest_session(choppy, DATE, ET, pyramid_qty=100,
                                max_position_shares=250, **PY)
    assert trades
    assert all(t.max_qty <= 250 for t in trades)


def test_entry_shares_overrides_sizing(choppy):
    """The control the pyramid study is measured against. Without the price
    band's sizing rule in the way, 200 shares must be exactly 200."""
    trades = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                                entry_shares=200)
    assert trades
    assert all(t.qty == 200 for t in trades)


def test_flat_size_is_a_pure_multiplier_at_this_size(choppy):
    """Doubling the size doubles net exactly -- which is WHY the pyramid study
    cannot be judged on P/L alone: any extra size wins by construction.

    Commission scales linearly too, and that is a fact about where MCL sits
    rather than a general one: 100 shares x $0.0035 Tiered is $0.35, exactly
    the per-order minimum. MCL therefore gets no volume discount and pays no
    minimum penalty. A SMALLER order does -- a 50-share partial sell is
    $0.175 of rate against a $0.35 minimum, i.e. double the effective rate,
    which is part of why the scale-out mechanic was expensive."""
    one = S.backtest_session(choppy, DATE, ET, trail_pct=20.0, entry_shares=100)
    two = S.backtest_session(choppy, DATE, ET, trail_pct=20.0, entry_shares=200)
    assert one and two and len(one) == len(two)
    for a, b in zip(one, two):
        assert b.gross == pytest.approx(2 * a.gross, rel=1e-9)
        assert b.commission == pytest.approx(2 * a.commission, abs=0.01)
    # ... and a half-size order pays more than half the commission.
    from common.commissions import order_cost
    assert order_cost(50, 5.0, True, "ibkr_tiered") > \
        0.5 * order_cost(100, 5.0, True, "ibkr_tiered")


def test_a_deeper_dip_requirement_never_adds_more_often(choppy):
    """Monotonicity: requiring a bigger pullback before arming cannot produce
    more adds. A failure here means the arming level is not what it claims."""
    shallow = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                                 pyramid_qty=100, pyramid_pullback_pct=1.0)
    deep = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                              pyramid_qty=100, pyramid_pullback_pct=5.0)
    assert sum(t.adds for t in deep) <= sum(t.adds for t in shallow)
