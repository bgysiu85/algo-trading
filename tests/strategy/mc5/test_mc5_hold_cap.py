#!/usr/bin/env python3
"""MC5's time cap (`max_hold_bars`, W03-0004, REGISTERED_time_cap.md).

Same contract as MCL's parameter (tests/common/test_hold_cap.py), in
five-minute bars. Tested on constructed sessions: the cap's job is to fire on
the right bar at the right price, and to change nothing when it is off.
"""
from __future__ import annotations

import inspect
from datetime import date
from zoneinfo import ZoneInfo

import pytest

from strategy.mc5 import mc5 as M
from tests.strategy.mc5.test_mc5_strategy import frame_1m, momentum_series

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 2)


def session(seed: int):
    return frame_1m(momentum_series(seed=seed), start="00:00")


def run(df, **kw):
    return M.backtest_session(df, DAY, ET, **kw)


def _key(t):
    return (t.entry_time, t.exit_time, t.entry_price, t.exit_price,
            t.reason, t.bars_held, t.net)


@pytest.fixture(scope="module")
def sessions():
    """Seeds whose uncapped book has at least one trade held 3+ bars, so the
    assertions below cannot pass vacuously."""
    out = []
    for seed in range(1, 40):
        df = session(seed)
        tr = run(df)
        if any(t.bars_held >= 3 for t in tr):
            out.append((df, tr))
        if len(out) >= 4:
            break
    assert len(out) >= 2, "fixture produced no multi-bar MC5 holds"
    return out


def test_default_is_none():
    assert inspect.signature(M.backtest_session).parameters["max_hold_bars"].default is None


def test_none_is_identical_to_not_passing_it(sessions):
    for df, base in sessions:
        assert [_key(t) for t in run(df, max_hold_bars=None)] == [_key(t) for t in base]


def test_no_trade_outlives_the_cap(sessions):
    for df, _ in sessions:
        for cap in (1, 2, 3, 6):
            for t in run(df, max_hold_bars=cap):
                assert t.bars_held <= cap, (cap, t)


def test_hold_cap_fires_exactly_at_the_cap_at_the_close_less_a_tick(sessions):
    fired = 0
    for df, _ in sessions:
        d5 = M.to_5m(df)
        for t in run(df, max_hold_bars=2):
            if t.reason != "hold_cap":
                continue
            fired += 1
            assert t.bars_held == 2
            import pandas as pd
            close = float(d5.loc[pd.Timestamp(t.exit_time), "close"])
            assert t.exit_price == pytest.approx(round(close - M.SLIPPAGE_TICKS * M.TICK, 4))
    assert fired > 0, "the cap never fired -- the test proved nothing"


def test_a_trade_that_ends_before_the_cap_is_untouched(sessions):
    """The first trade of the day is the same trade under both rules until the
    cap could act. If it ended by its own rule before the cap, it must be
    byte-identical."""
    checked = 0
    for df, base in sessions:
        first = base[0]
        cap = first.bars_held + 1
        assert _key(run(df, max_hold_bars=cap)[0]) == _key(first)
        checked += 1
    assert checked


def test_trail_wins_a_tie_with_the_cap(sessions):
    """A trade the trail closed on bar k keeps the trail's label under a cap of
    k: the cap is last in the exit order."""
    checked = 0
    for df, base in sessions:
        first = base[0]
        if first.reason == "trailing_stop" and first.bars_held >= 1:
            got = run(df, max_hold_bars=first.bars_held)[0]
            assert got.reason == "trailing_stop"
            assert _key(got) == _key(first)
            checked += 1
    if not checked:
        pytest.skip("no trailing-stop first trade in the fixture seeds")


def test_zero_is_the_tightest_cap_not_off(sessions):
    df, base = sessions[0]
    capped = run(df, max_hold_bars=0)
    assert capped, "cap 0 removed every trade"
    assert all(t.bars_held <= 1 for t in capped)
    assert [_key(t) for t in capped] != [_key(t) for t in base]


def test_negative_cap_is_refused():
    with pytest.raises(ValueError):
        run(session(1), max_hold_bars=-1)
