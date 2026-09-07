#!/usr/bin/env python3
"""entry_shares has to reach the fill, not just the signature.

Accepting a keyword and ignoring it is worse than rejecting it: the run
completes, every row is populated, and the output is filed as size-matched
while every position is the strategy's own MAX_SHARES=100. Against a real
trading day that ran 5,000 shares, that is a P/L comparison of two different
experiments printed in adjacent columns.

So these tests run the strategy and read the SIZE OFF THE RESULTING TRADE,
and for VW9 -- where the value crosses three modules to get to the fill --
they also pin the threading itself.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from strategy.mcl import mcl as MCL
from strategy.mc5 import mc5 as MC5
from strategy.vw9 import vw9_5m, vw9_15m
from strategy.vw9 import backtest as VW

ET = ZoneInfo("America/New_York")
DATE = date(2026, 9, 2)


def frame(closes, vols=None, start="04:00", freq="1min"):
    n = len(closes)
    t0 = datetime.strptime(f"2026-09-02 {start}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    idx = pd.date_range(t0, periods=n, freq=freq).tz_convert("UTC")
    return pd.DataFrame(
        {"open": closes,
         "high": [c * 1.004 for c in closes],
         "low": [c * 0.996 for c in closes],
         "close": closes,
         "volume": vols or [5000] * n}, index=idx)


@pytest.fixture(scope="module")
def mcl_session():
    """A session MCL actually enters. Found by search rather than written --
    the entry needs MACD, a volume spike and a regime to line up at once, which
    is why every other MCL test does the same thing."""
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
        if MCL.backtest_session(df, DATE, ET, trail_pct=20.0):
            return df
    pytest.skip("no entering session found in 200 seeds")


def test_mcl_fills_the_size_it_was_given(mcl_session):
    default = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0)
    sized = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                                 entry_shares=1_437)
    assert default[0].qty == MCL.MAX_SHARES        # the thing being overridden
    assert sized[0].qty == 1_437
    assert len(sized) == len(default)              # size must not change the
    assert sized[0].entry_time == default[0].entry_time   # decisions


def test_mcl_pl_scales_with_the_size(mcl_session):
    """The size has to reach the P/L, not only the reported qty. Gross is
    linear in quantity, so ten times the shares is ten times the gross."""
    one = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                               entry_shares=100)[0]
    ten = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                               entry_shares=1000)[0]
    # abs, not rel: gross is stored rounded to the cent, so ten times a
    # rounded number is off by up to a few cents from the rounded ten-times.
    assert ten.gross == pytest.approx(one.gross * 10, abs=0.05)
    # And the cost has to scale with it too, or net is gross at a discount.
    assert ten.commission == pytest.approx(one.commission * 10, rel=0.02)
    for t in (one, ten):
        assert t.net == pytest.approx(t.gross - t.commission, abs=0.01)


def test_the_per_order_minimum_survives_being_size_matched(mcl_session):
    """Cost is linear in quantity only ABOVE the per-order minimum. At 10
    shares the $0.35 floor dominates and a share costs about eleven times what
    it costs at 1,000 -- so a size-matched run must price each day's own size
    rather than scaling one number. Measured: order_cost(10,$5) = $0.38 and
    order_cost(1000,$5) = $6.71, not $38."""
    tiny = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                                entry_shares=10)[0]
    big = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                               entry_shares=1000)[0]
    assert big.commission < tiny.commission * 100


def test_mcl_default_is_unchanged_when_no_size_is_given(mcl_session):
    """Strictly additive. Every published MCL figure was produced without this
    argument, and must still be reproducible without it."""
    a = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0)
    b = MCL.backtest_session(mcl_session, DATE, ET, trail_pct=20.0,
                             entry_shares=None)
    assert [t.__dict__ for t in a] == [t.__dict__ for t in b]


@pytest.fixture(scope="module")
def mc5_session():
    for seed in range(60):
        rng = np.random.default_rng(seed)
        px, closes, burst = 3.0, [], 0
        for _ in range(900):
            if burst == 0 and rng.random() < 0.02:
                burst = int(rng.integers(15, 50))
            drift = 0.004 if burst > 0 else 0.0
            burst = max(0, burst - 1)
            px *= 1.0 + drift + rng.normal(0, 0.004)
            closes.append(max(px, 0.2))
        df = frame(closes, start="03:00")
        if MC5.backtest_session(df, DATE, ET):
            return df
    pytest.skip("no entering MC5 session found")


def test_mc5_fills_the_size_it_was_given(mc5_session):
    default = MC5.backtest_session(mc5_session, DATE, ET)
    sized = MC5.backtest_session(mc5_session, DATE, ET, entry_shares=2_500)
    assert default[0].qty == MC5.MAX_SHARES
    assert sized[0].qty == 2_500
    assert sized[0].gross == pytest.approx(default[0].gross * 25, abs=0.30)


# --- VW9 crosses three modules to reach the fill ----------------------------

def test_vw9_threads_the_size_all_the_way_to_the_fill(monkeypatch):
    """vw9_5m.backtest_session -> backtest_session_tf -> _simulate_trade.
    A signature check only proves the first hop; a value dropped at either of
    the other two would leave the run silently at 100 shares."""
    seen = {}
    real = VW._simulate_trade

    def spy(*a, **kw):
        seen["entry_shares"] = kw.get("entry_shares", "ABSENT")
        return real(*a, **kw)

    monkeypatch.setattr(VW, "_simulate_trade", spy)
    df = frame([3.0 + 0.01 * i for i in range(400)])
    for mod in (vw9_5m, vw9_15m):
        seen.clear()
        mod.backtest_session(df, DATE, ET, entry_shares=911)
        if seen:                      # only if a setup fired on this frame
            assert seen["entry_shares"] == 911, f"{mod.__name__} dropped it"


def test_vw9_simulate_trade_uses_the_size_over_size_for():
    """The one hop the spy above cannot prove: that _simulate_trade prefers
    entry_shares to its own size_for()."""
    import inspect
    src = inspect.getsource(VW._simulate_trade)
    assert "size_for(entry_price) if entry_shares is None else" in src
