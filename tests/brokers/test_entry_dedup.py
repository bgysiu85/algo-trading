#!/usr/bin/env python3
"""One signal must not open more than one position.

THE BUG THIS PINS
------------------
`trader.py` deduped entries with `st.last_bar_ts == last_ts`, where `last_ts`
is the last 1-MINUTE row of the frame. For MCL the signal bar IS that row and
the guard worked. For MC5 the frame advances every minute while the signal only
changes every five, so the guard never fired inside a bucket and the SAME
signal entered up to five times, each at whatever the market had moved to.

Live, 2026-09-11: 40% of entries reused an already-traded bucket. One TNON
bucket with close 7.51 bought at 7.22, 7.04, 6.94, 6.98 and 6.96 on five
consecutive minutes -- buying a falling market five times on one stale signal.

The guard's key was not the thing it guarded. These tests are about that
distinction, so the MC5 case -- where the signal bar and the frame's last row
DIFFER -- is the one that carries the weight.
"""
from __future__ import annotations

from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common.strategy_adapter import BUILDERS, build
from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def frame(n: int, start=dtime(4, 0), day="2026-09-11", base=7.0, step=0.01):
    """n 1-minute bars, gently rising so indicators are defined."""
    t0 = pd.Timestamp(datetime.combine(
        pd.Timestamp(day).date(), start, tzinfo=ET))
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)])
    close = [base + i * step for i in range(n)]
    return pd.DataFrame({"open": close, "high": [c * 1.002 for c in close],
                         "low": [c * 0.998 for c in close], "close": close,
                         "volume": [50_000.0] * n}, index=idx)


# --- the contract ------------------------------------------------------------

def test_every_registered_strategy_supplies_the_bar_it_used():
    """The fallback in trader.py is for a strategy that omits `bar_ts`. No
    SHIPPED strategy may rely on it -- that is what let MC5 through."""
    df = frame(200)
    now = df.index[-1].to_pydatetime() + timedelta(minutes=6)
    for name in BUILDERS:
        a = build(name)
        sig = a.evaluate(df, now)
        assert sig is not None, f"{name} returned no signal on 200 bars"
        assert getattr(sig, "bar_ts", None) is not None, (
            f"{name} does not report which bar it used; the trader would fall "
            "back to the frame's last row, which is the MC5 bug")


def test_mcl_bar_ts_is_the_frames_last_row():
    df = frame(200)
    sig = MCL.evaluate_last_bar(df)
    assert sig.bar_ts == df.index[-1]


def test_mc5_bar_ts_is_the_BUCKET_not_the_frames_last_row():
    """The whole defect in one assertion."""
    df = frame(200)
    now = df.index[-1].to_pydatetime() + timedelta(minutes=6)
    sig = MC5.evaluate_last_bar(df, now)
    assert sig.bar_ts is not None
    assert sig.bar_ts != df.index[-1], (
        "MC5's signal bar must not equal the 1-minute frame's last row -- if "
        "it does, this test is not exercising the case that broke")
    assert sig.bar_ts.minute % 5 == 0


def test_mc5_bar_ts_is_STABLE_across_minutes_inside_one_bucket():
    """The reason the guard failed: the frame's last row changes every minute
    and the signal's bar does not. Five successive frames, one bucket, one
    bar_ts -- so a guard keyed on bar_ts fires and one keyed on the frame's
    last row does not."""
    full = frame(210)
    seen_signal, seen_frame = set(), set()
    for extra in range(5):
        df = full.iloc[:200 + extra]
        now = df.index[-1].to_pydatetime() + timedelta(minutes=1)
        sig = MC5.evaluate_last_bar(df, now)
        if sig is None:
            continue
        seen_signal.add(sig.bar_ts)
        seen_frame.add(df.index[-1])
    assert len(seen_frame) > 1, "frames did not advance; test is vacuous"
    assert len(seen_signal) == 1, (
        f"expected one signal bucket across these minutes, got {seen_signal}")


# --- the guard itself --------------------------------------------------------

class _St:
    """Only the fields the guard touches."""
    def __init__(self):
        self.last_bar_ts = None


def guard(st, sig, last_ts) -> bool:
    """trader.py's entry dedupe, isolated. Returns True when the entry is
    ALLOWED through. Kept in step with the trader by
    test_the_guard_matches_the_traders_source below."""
    signal_ts = getattr(sig, "bar_ts", None) or last_ts
    if st.last_bar_ts == signal_ts:
        return False
    st.last_bar_ts = signal_ts
    return True


def test_the_guard_blocks_a_second_entry_on_one_mc5_bucket():
    full = frame(210)
    st = _St()
    allowed = 0
    for extra in range(5):
        df = full.iloc[:200 + extra]
        now = df.index[-1].to_pydatetime() + timedelta(minutes=1)
        sig = MC5.evaluate_last_bar(df, now)
        if sig is None:
            continue
        if guard(st, sig, df.index[-1]):
            allowed += 1
    assert allowed == 1, f"one bucket let {allowed} entries through"


def test_the_OLD_key_would_have_let_all_five_through():
    """Vacuous-guard. If the old key also blocked them, the fix is not the fix
    and this whole file proves nothing."""
    full = frame(210)
    st = _St()
    allowed = 0
    for extra in range(5):
        df = full.iloc[:200 + extra]
        now = df.index[-1].to_pydatetime() + timedelta(minutes=1)
        if MC5.evaluate_last_bar(df, now) is None:
            continue
        last_ts = df.index[-1]
        if st.last_bar_ts != last_ts:       # the OLD guard
            st.last_bar_ts = last_ts
            allowed += 1
    assert allowed > 1, ("the old key did not admit duplicates on this "
                         "fixture, so the new one proves nothing")


def test_a_new_bucket_is_allowed_through():
    """The guard must not be a one-entry-per-symbol lock."""
    full = frame(215)
    st = _St()
    allowed = 0
    for extra in range(0, 15):
        df = full.iloc[:200 + extra]
        now = df.index[-1].to_pydatetime() + timedelta(minutes=1)
        sig = MC5.evaluate_last_bar(df, now)
        if sig is None:
            continue
        if guard(st, sig, df.index[-1]):
            allowed += 1
    assert allowed >= 2, "a genuinely new bucket must be admitted"


def test_a_strategy_without_bar_ts_falls_back_to_the_frame():
    class Bare:
        bar_ts = None
    st = _St()
    t = pd.Timestamp("2026-09-11 09:00", tz=ET)
    assert guard(st, Bare(), t) is True
    assert guard(st, Bare(), t) is False


def test_the_guard_matches_the_traders_source():
    """This file's `guard` is a copy. A copy that drifts from the original is
    the defect this project keeps finding, so the shape is pinned here."""
    import inspect
    from pathlib import Path
    src = Path(inspect.getsourcefile(__import__(
        "brokers.ibkr.trader", fromlist=["x"]))).read_text(encoding="utf-8")
    assert 'signal_ts = getattr(sig, "bar_ts", None) or last_ts' in src
    assert "if st.last_bar_ts == signal_ts:" in src
    assert "st.last_bar_ts = signal_ts" in src
