#!/usr/bin/env python3
"""Regression net for the scale-out / scale-back-in exit (Ross Cameron style).

Two real bugs were shipped into this mechanic and both were invisible to the
P/L -- the backtest simply reported a different, plausible-looking number. So
the tests here pin BEHAVIOUR, not returns:

  1. Re-entry fired on the previous BAR's high rather than the peak the
     pullback started from. Measured over 4,359 re-entries, that bought back
     below its own sell price 82% of the time: it was averaging down into a
     slide while claiming to buy strength.
  2. Hitting max_cycles stopped the buy-back but NOT the partial sell, so a
     capped trade kept selling half its position on every subsequent pullback
     and never bought any of it back, bleeding to nothing on a trade that was
     never stopped out.

The invariants below would have failed on both.
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


def frame(closes, highs=None, lows=None, vols=None, start="04:00"):
    n = len(closes)
    t0 = datetime.strptime(f"2026-09-02 {start}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq="1min").tz_convert("UTC")
    return pd.DataFrame(
        {"open": closes,
         "high": highs or [c * 1.004 for c in closes],
         "low": lows or [c * 0.996 for c in closes],
         "close": closes,
         "volume": vols or [5000] * n}, index=idx)


@pytest.fixture(scope="module")
def choppy():
    """A session that enters and then saws up and down enough to exercise many
    scale-out cycles. Found by search rather than construction, for the same
    reason test_backtest_engine.py does it: MCL's entry needs MACD, a volume
    spike and a regime to line up, which is not practical to hand-write."""
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
        # A wide trail so the position survives long enough to cycle.
        t = S.backtest_session(df, DATE, ET, trail_pct=20.0,
                               scale_out_pct=50.0, partial_trail_pct=1.0,
                               rebuy_qty=None)
        if t and t[0].cycles >= 3:
            return df
    pytest.skip("no multi-cycle session found in 200 seeds")


KW = dict(trail_pct=20.0, partial_trail_pct=1.0, scale_out_pct=50.0)


def test_mechanic_is_inert_when_disabled(choppy):
    """scale_out_pct=None must reproduce the plain engine bit-for-bit --
    otherwise every published result in claude/*.md silently changed."""
    off = S.backtest_session(choppy, DATE, ET, trail_pct=20.0)
    also_off = S.backtest_session(choppy, DATE, ET, trail_pct=20.0,
                                  scale_out_pct=None, partial_trail_pct=1.0,
                                  rebuy_qty=100, max_cycles=3)
    assert [t.net for t in off] == [t.net for t in also_off]
    assert all(t.cycles == 0 for t in off)
    assert all(t.shares_traded == 2 * t.qty for t in off)


def test_peak_trigger_re_enters_higher_than_prev_bar_trigger(choppy):
    """The fix, stated as a property: reclaiming the PEAK is a strictly harder
    condition than tagging the previous bar's high, so it can never fire more
    often. The old trigger's extra 're-entries' were the averaging-down ones."""
    peak = S.backtest_session(choppy, DATE, ET, rebuy_qty=None,
                              rebuy_trigger="peak", **KW)
    prev = S.backtest_session(choppy, DATE, ET, rebuy_qty=None,
                              rebuy_trigger="prev_bar_high", **KW)
    assert peak and prev
    assert sum(t.cycles for t in peak) < sum(t.cycles for t in prev)


def test_peak_trigger_is_the_default(choppy):
    explicit = S.backtest_session(choppy, DATE, ET, rebuy_qty=None,
                                  rebuy_trigger="peak", **KW)
    default = S.backtest_session(choppy, DATE, ET, rebuy_qty=None, **KW)
    assert [t.net for t in default] == [t.net for t in explicit]


@pytest.mark.parametrize("cap", [0, 1, 2, 3])
def test_max_cycles_is_never_exceeded(choppy, cap):
    trades = S.backtest_session(choppy, DATE, ET, rebuy_qty=None,
                                max_cycles=cap, **KW)
    assert trades
    assert all(t.cycles <= cap for t in trades)


def test_capped_trade_stops_selling_too(choppy):
    """Bug 2. A capped trade must not keep shedding shares it will never buy
    back. Shares transacted at cap=1 has a hard ceiling: entry + one partial
    sell + one buy-back + the final exit, all of at most the entry size."""
    capped = S.backtest_session(choppy, DATE, ET, rebuy_qty=None,
                                max_cycles=1, **KW)
    assert capped
    for t in capped:
        assert t.shares_traded <= 4 * t.qty, (
            f"{t.shares_traded} shares on a 1-cycle cap of {t.qty}: the "
            f"mechanic kept selling after the cap")


def test_size_neutral_rebuy_never_grows_the_position(choppy):
    """rebuy_qty=None means 'restore exactly what was sold', so at a 50%
    portion every cycle transacts exactly 2 x 50 shares on a 100-share
    position -- never more. The entry and the final exit add 2 x qty, and a
    scale-out still open when the trade ends adds one more sell."""
    trades = S.backtest_session(choppy, DATE, ET, rebuy_qty=None, **KW)
    assert trades
    for t in trades:
        sold = t.qty // 2                       # scale_out_pct=50
        lo = 2 * t.qty + 2 * t.cycles * sold
        assert lo <= t.shares_traded <= lo + sold, (
            f"{t.shares_traded} shares over {t.cycles} cycles on {t.qty}: "
            f"size did not stay constant")


def test_max_position_shares_caps_a_growing_position(choppy):
    """rebuy_qty=150 on a 100-share entry grows the position; the cap must
    bind. Checked through commission, which is charged per order on the real
    IBKR schedule and so rises with the shares actually transacted."""
    uncapped = S.backtest_session(choppy, DATE, ET, rebuy_qty=150, **KW)
    capped = S.backtest_session(choppy, DATE, ET, rebuy_qty=150,
                                max_position_shares=120, **KW)
    assert uncapped and capped
    assert sum(t.shares_traded for t in capped) \
        < sum(t.shares_traded for t in uncapped)


def test_scaling_costs_money_on_a_clean_runner():
    """The mechanic's cost, stated as a property rather than a P/L number: on
    a stock that only goes up, selling into a dip and buying back higher can
    never beat holding. If this ever passes the other way, the fill model has
    started paying to trade."""
    hold = scaled = None
    for seed in range(60):
        rng = np.random.default_rng(seed)
        px, closes = 3.0, []
        for i in range(220):
            px *= 1.0 + (rng.uniform(-0.003, 0.011) if i < 130 else 0.004)
            closes.append(px)
        lows = [c * 0.996 for c in closes]
        lows[170] = closes[170] * 0.985       # one 1.5% dip that recovers
        vols = [int(v) for v in rng.integers(4000, 7000, 220)]
        vols[125] = vols[124] * 6
        df = frame(closes, lows=lows, vols=vols)
        hold = S.backtest_session(df, DATE, ET, trail_pct=20.0)
        if hold:
            scaled = S.backtest_session(df, DATE, ET, trail_pct=20.0,
                                        partial_trail_pct=1.0,
                                        scale_out_pct=50.0, rebuy_qty=None,
                                        rebuy_slip_bps=40.0)
            if any(t.cycles for t in scaled):
                break
    else:
        pytest.skip("no clean runner with a recovered dip in 60 seeds")
    assert sum(t.net for t in scaled) < sum(t.net for t in hold)
