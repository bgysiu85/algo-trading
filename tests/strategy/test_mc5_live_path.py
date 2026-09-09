#!/usr/bin/env python3
"""MC5 on the live path: the bar it evaluates, and when.

Stage 1 of claude/multi_strategy_trader_spec.md. MC5 trades 5-minute bars and
the trader streams 1-minute ones, so the only thing that matters before any of
this reaches an order is WHICH bar the strategy thinks has closed.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mc5 import mc5 as M
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def bars1m(n: int, start="2026-01-07 04:00", price=5.0, step=0.01):
    """n consecutive 1-minute bars, rising, so indicators are defined."""
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    px = [price + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": px, "high": [p + 0.02 for p in px],
         "low": [p - 0.02 for p in px], "close": px,
         "volume": [10_000.0] * n}, index=idx)


def et(s):
    return pd.Timestamp(s, tz=ET)


# --- the partial bucket -----------------------------------------------------

def test_a_bucket_is_not_complete_until_the_clock_has_passed_it():
    """THE TRAP. At 08:07 the newest bucket is 08:05 and holds two minutes of
    a five-minute bar. Evaluating it enters on a signal that has not formed."""
    df = bars1m(400, start="2026-01-07 04:00")
    df = df[df.index <= et("2026-01-07 08:06").tz_convert("UTC")]
    assert M.last_closed_bucket(df, et("2026-01-07 08:07")) == \
        et("2026-01-07 08:00").tz_convert("UTC"), (
            "08:05 is still forming at 08:07; the newest usable bucket is 08:00")


def test_the_bucket_becomes_available_once_its_five_minutes_are_up():
    df = bars1m(400, start="2026-01-07 04:00")
    df = df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")]
    # 08:05 bucket covers 08:05-08:09. At 08:10 it is closed and we hold 08:09.
    assert M.last_closed_bucket(df, et("2026-01-07 08:10")) == \
        et("2026-01-07 08:05").tz_convert("UTC")


def test_the_clock_alone_does_not_make_a_bucket_complete():
    """IB history can lag. A bucket missing its last two minutes is not
    complete just because a wall clock says so."""
    df = bars1m(400, start="2026-01-07 04:00")
    df = df[df.index <= et("2026-01-07 08:06").tz_convert("UTC")]
    got = M.last_closed_bucket(df, et("2026-01-07 08:20"))
    assert got == et("2026-01-07 08:00").tz_convert("UTC"), (
        "with data only to 08:06 the newest provable bucket is 08:00, "
        "whatever the clock says")


def test_a_minute_with_no_print_does_not_block_the_bucket_forever():
    """A missing minute produces no bar, so 'we hold the 08:09 bar' can never
    be a requirement -- it would stall a thin name permanently."""
    df = bars1m(400, start="2026-01-07 04:00")
    keep = (df.index <= et("2026-01-07 08:08").tz_convert("UTC")) | \
           (df.index >= et("2026-01-07 08:11").tz_convert("UTC"))
    df = df[keep]
    df = df[df.index <= et("2026-01-07 08:12").tz_convert("UTC")]
    assert M.last_closed_bucket(df, et("2026-01-07 08:13")) == \
        et("2026-01-07 08:05").tz_convert("UTC")


def test_evaluate_uses_the_complete_bucket_and_not_the_forming_one():
    """End to end: the close the strategy reports must be the closed bucket's,
    never the partial one's."""
    df = bars1m(400, start="2026-01-07 04:00")
    full = df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")]
    sig = M.evaluate_last_bar(full, et("2026-01-07 08:10"))
    assert sig is not None
    closed = M.to_5m(full)
    assert sig.close == pytest.approx(
        float(closed.loc[et("2026-01-07 08:05").tz_convert("UTC"), "close"]))

    # One minute earlier there is no complete 08:05 bucket, so the answer must
    # come from 08:00 instead -- a DIFFERENT close.
    part = df[df.index <= et("2026-01-07 08:06").tz_convert("UTC")]
    earlier = M.evaluate_last_bar(part, et("2026-01-07 08:07"))
    assert earlier is not None
    assert earlier.close != sig.close


# --- warm-up ----------------------------------------------------------------

def test_min_bars_required_is_counted_in_five_minute_bars():
    """40 five-minute bars is 3h20m of clock, against MCL's 40 minutes. The
    numbers being equal is what makes this easy to misread."""
    assert M.MIN_BARS_REQUIRED == MCL.MIN_BARS_REQUIRED == 40
    assert M.MIN_BARS_REQUIRED * M.BAR_MINUTES == 200


def test_a_cold_frame_returns_none_rather_than_a_signal():
    df = bars1m(60, start="2026-01-07 04:00")        # 12 five-minute buckets
    assert M.evaluate_last_bar(df, et("2026-01-07 05:01")) is None


def test_it_stays_none_until_the_indicators_are_actually_warm():
    """Boundary, not vibes: 39 buckets is None, 40 is a signal."""
    def buckets(n):
        df = bars1m(n * M.BAR_MINUTES + 1, start="2026-01-07 04:00")
        end = et("2026-01-07 04:00") + timedelta(minutes=n * M.BAR_MINUTES)
        return M.evaluate_last_bar(
            df[df.index < end.tz_convert("UTC")], end)
    assert buckets(M.MIN_BARS_REQUIRED - 1) is None
    assert buckets(M.MIN_BARS_REQUIRED) is not None


# --- interchangeability with MCL -------------------------------------------

def test_the_two_signals_types_stay_interchangeable():
    """The trader consumes whichever the active strategy returns. Separate
    classes are fine; separate FIELDS are not."""
    a = [f.name for f in dataclasses.fields(M.Signals)]
    b = [f.name for f in dataclasses.fields(MCL.Signals)]
    assert a == b


def test_five_minute_input_is_accepted_as_already_closed():
    """backtest_session hands 5-minute frames around; evaluate must take one
    without pretending to re-derive which bucket has closed."""
    df = bars1m(400, start="2026-01-07 04:00")
    df5 = M.to_5m(df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")])
    sig = M.evaluate_last_bar(df5, et("2026-01-07 08:10"))
    assert sig is not None
    assert sig.close == pytest.approx(float(df5["close"].iloc[-1]))


# --- agreement with the backtest -------------------------------------------

def test_the_live_evaluation_agrees_with_backtest_session_on_the_same_bar():
    """THE CONTROL FOR STAGE 1. If the live path and the backtest disagree
    about the last bar, nothing built on top of this is worth testing.

    backtest_session is driven by signals() over the whole frame; so is
    evaluate_last_bar. Running both and comparing the entry flag on the final
    closed bucket is the direct check that the live path reads the same rule.
    """
    df = bars1m(400, start="2026-01-07 04:00")
    cut = df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")]
    live = M.evaluate_last_bar(cut, et("2026-01-07 08:10"))
    assert live is not None

    ref = M.signals(M.to_5m(cut))
    last = ref.loc[et("2026-01-07 08:05").tz_convert("UTC")]
    assert live.long_entry == bool(last["entry"])
    assert live.exit_signal == bool(last["exit_sig"])
    assert live.close == pytest.approx(float(last["close"]))


def test_the_detail_dict_carries_every_condition_the_entry_depends_on():
    """The fill log stores these. A rejected or accepted entry has to be
    reconstructable from the row three hours later."""
    df = bars1m(400, start="2026-01-07 04:00")
    sig = M.evaluate_last_bar(
        df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")],
        et("2026-01-07 08:10"))
    assert {"c_rsi", "c_ema", "c_macd"} <= set(sig.detail)
    assert sig.long_entry == (sig.detail["c_rsi"] and sig.detail["c_ema"]
                              and sig.detail["c_macd"])
