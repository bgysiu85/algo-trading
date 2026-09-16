#!/usr/bin/env python3
"""The green-hold exit: in profit at bar N -> out at that close; not in profit -> hold."""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)


def run(bars, **kw):
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000
    take = pd.Series(False, index=idx)
    take.iloc[0] = True
    return MCL.backtest_session(df, DAY, ET, entry_bars=take, entry_shares=100,
                                use_apex=False, **kw)


F = (5.00, 5.00, 5.00, 5.00)
UP = (5.05, 5.08, 5.04, 5.06)      # green against an entry at 5.01
DN = (4.99, 5.00, 4.98, 4.99)      # red against it, above the trail


def test_in_profit_at_bar_n_exits_at_that_close():
    (t,) = run([F, UP, UP, UP, UP, UP, UP], green_hold_bars=3)
    assert t.reason == "green_hold" and t.bars_held == 3
    assert t.exit_price == pytest.approx(5.06 - 0.01)


def test_not_in_profit_at_bar_n_keeps_holding():
    (t,) = run([F, DN, DN, DN, DN, UP, UP, UP], green_hold_bars=3)
    # red at bars 3 and 4, green from bar 5 -> exits at bar 5
    assert t.reason == "green_hold" and t.bars_held == 5


def test_the_trail_wins_the_same_bar():
    (t,) = run([F, UP, UP, (5.06, 5.20, 4.70, 5.10), F], green_hold_bars=3)
    assert t.reason == "trailing_stop"


def test_the_window_close_is_not_relabelled():
    (t,) = run([F, UP, UP, UP], green_hold_bars=3)
    assert t.reason == "window_close"


def test_none_is_bit_identical():
    bars = [F, UP, UP, UP, UP, DN, UP]
    a = [t.__dict__ for t in run(bars)]
    b = [t.__dict__ for t in run(bars, green_hold_bars=None)]
    assert a == b and a[0]["reason"] == "window_close"


def test_zero_bars_is_the_tightest_setting_not_off():
    (t,) = run([F, UP, UP, UP], green_hold_bars=0)
    # the entry bar itself is never managed; bar 1 is >= 0 bars after and green
    assert t.reason == "green_hold" and t.bars_held == 1
