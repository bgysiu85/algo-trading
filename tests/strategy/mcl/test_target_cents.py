#!/usr/bin/env python3
"""The fixed cents target: a resting limit for the whole position."""
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


def test_fills_at_the_target_when_the_high_reaches_it():
    (t,) = run([F, (5.02, 5.10, 5.01, 5.05), (5.05, 5.30, 5.04, 5.20), F, F], target_cents=0.25)
    # entry 5.00 + 1 tick = 5.01; target 5.26; reached on bar 2
    assert t.reason == "target" and t.exit_price == pytest.approx(5.26)
    assert t.bars_held == 2


def test_a_bar_opening_above_the_target_fills_at_the_open():
    (t,) = run([F, (5.40, 5.45, 5.35, 5.42), F], target_cents=0.25)
    assert t.reason == "target" and t.exit_price == pytest.approx(5.40)


def test_the_stop_wins_a_bar_that_reaches_both():
    # peak seeded at 5.01; trail 4.7595. Bar has high 5.30 and low 4.70.
    (t,) = run([F, (5.00, 5.30, 4.70, 4.80), F], target_cents=0.25)
    assert t.reason == "trailing_stop"


def test_none_is_bit_identical_to_the_engine_without_it():
    bars = [F, (5.02, 5.10, 5.01, 5.05), (5.05, 5.30, 5.04, 5.20), (5.2, 5.25, 5.1, 5.15), (5.15, 5.2, 5.1, 5.18)]
    a = run(bars)
    b = run(bars, target_cents=None)
    assert [t.__dict__ for t in a] == [t.__dict__ for t in b]
    assert a[0].reason == "window_close"


def test_a_target_never_reached_leaves_the_other_exits_alone():
    (t,) = run([F, (5.02, 5.10, 5.01, 5.05), F, F], target_cents=0.25)
    assert t.reason == "window_close"
