#!/usr/bin/env python3
"""The hard stop: a fixed level under the position, tested like the trail."""
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


F = (5.00, 5.00, 5.00, 5.00)          # entry 5.01; 5% trail from 5.01 = 4.7595


def test_the_hard_stop_fires_where_the_trail_would_not():
    (t,) = run([F, (5.00, 5.02, 4.89, 4.95), F], hard_stop=4.90)
    assert t.reason == "structure_stop" and t.exit_price == pytest.approx(4.89)


def test_gap_through_pays_the_open():
    (t,) = run([F, (4.80, 4.85, 4.75, 4.82), F], hard_stop=4.90)
    assert t.reason == "structure_stop" and t.exit_price == pytest.approx(4.79)


def test_the_trail_takes_over_once_it_is_higher():
    # peak 5.30 -> trail 5.035 > hard stop 4.90
    (t,) = run([F, (5.05, 5.30, 5.04, 5.28), (5.28, 5.29, 5.02, 5.10), F], hard_stop=4.90)
    assert t.reason == "trailing_stop" and t.exit_price == pytest.approx(5.035 - 0.01)


def test_a_hard_stop_below_the_trail_changes_nothing():
    bars = [F, (5.00, 5.02, 4.95, 4.98), (4.98, 5.00, 4.96, 4.99)]
    a = [t.__dict__ for t in run(bars)]
    b = [t.__dict__ for t in run(bars, hard_stop=4.50)]
    assert a == b


def test_none_is_bit_identical():
    bars = [F, (5.00, 5.02, 4.89, 4.95), (4.95, 5.00, 4.90, 4.99)]
    assert [t.__dict__ for t in run(bars)] == [t.__dict__ for t in run(bars, hard_stop=None)]
