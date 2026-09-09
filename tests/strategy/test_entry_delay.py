#!/usr/bin/env python3
"""Pricing the minute between a signal bar closing and the order going out.

Measured live on 2026-09-09: three signals out of three left SIXTY SECONDS
after their bar closed, so the price paid belongs to the next bar. The backtest
had always assumed a fill at the signal bar's close. entry_delay_bars makes
that assumption a parameter instead of a silent one.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def frame(closes, highs=None, lows=None, vols=None,
          start="2026-03-02 04:00"):
    n = len(closes)
    highs = highs or [c * 1.002 for c in closes]
    lows = lows or [c * 0.998 for c in closes]
    if vols is None:
        # MCL needs a 3x surge on the entry bar over a live trailing average,
        # so a flat volume series produces no trades and every assertion below
        # would pass vacuously.
        vols = [5000.0] * n
        for i in range(60, n, 10):
            vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": highs, "low": lows,
                         "close": closes, "volume": vols}, index=idx)


def run(df, delay):
    return MCL.backtest_session(df, date(2026, 3, 2), ET,
                                entry_delay_bars=delay,
                                use_apex=False, require_macd_pos=True)


def uptrend(n=160):
    """A frame that reliably produces MCL entries.

    NOT a straight line: on a monotone rise RSI and MFI saturate at 100 and
    stop RISING, so c_mfi and c_rsi never fire and the frame yields no trades
    at all. The wobble is what makes the fixture exercise anything.
    """
    return [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
            for i in range(n)]


def test_the_default_is_the_rule_as_backtested():
    """Zero delay must be byte-identical to the old behaviour, or every
    figure this project has published silently moves."""
    df = frame(uptrend())
    a = run(df, 0)
    b = MCL.backtest_session(df, date(2026, 3, 2), ET, use_apex=False,
                             require_macd_pos=True)
    assert [(t.entry_time, t.entry_price, t.exit_price) for t in a] == \
           [(t.entry_time, t.entry_price, t.exit_price) for t in b]


def test_a_delayed_entry_pays_the_next_bars_price():
    df = frame(uptrend())
    base, late = run(df, 0), run(df, 1)
    assert base and late
    assert late[0].entry_price > base[0].entry_price, (
        "on a rising frame the next bar costs more")
    assert pd.Timestamp(late[0].entry_time) - pd.Timestamp(
        base[0].entry_time) == timedelta(minutes=1)


def test_the_signal_is_not_re_tested_at_the_delayed_bar():
    """A live order already sent is not withdrawn because the next bar looked
    worse. Re-testing would measure a different and flattering strategy."""
    closes = uptrend()
    df = frame(closes)
    base = run(df, 0)
    assert base
    # Blow the signal away on the bar AFTER the entry: the trade must survive.
    i = df.index.get_loc(pd.Timestamp(base[0].entry_time).tz_convert("UTC"))
    wrecked = closes[:]
    wrecked[i + 1] = closes[i] * 0.80
    late = run(frame(wrecked, lows=[c * 0.999 for c in closes]), 1)
    assert late, "the delayed entry must still be taken"


def test_the_entry_bar_is_never_managed():
    """THE LOOKAHEAD THIS AVOIDS. The delayed entry is taken at a bar the loop
    has not reached, so without a guard the trail would be tested against the
    very bar we bought on and stop trades out at the instant of entry."""
    closes = uptrend()
    df = frame(closes)
    base = run(df, 0)
    assert base
    i = df.index.get_loc(pd.Timestamp(base[0].entry_time).tz_convert("UTC"))
    # A deep wick on the delayed entry bar, well through a 5% trail.
    lows = [c * 0.999 for c in closes]
    lows[i + 1] = closes[i + 1] * 0.50
    late = run(frame(closes, lows=lows), 1)
    assert late, "a wick on the entry bar must not close the trade"
    assert late[0].bars_held >= 1


def test_an_entry_that_would_land_on_the_last_bar_is_refused():
    """It could never be exited, so the trade would vanish from the results --
    the same silent-drop failure the trail_confirm_bars comment records."""
    closes = uptrend()
    df = frame(closes)
    base = run(df, 0)
    assert base
    huge = run(df, 10_000)
    assert huge == [], "no trade may be opened with nothing left to manage it"


def test_delay_never_invents_trades():
    df = frame(uptrend())
    assert len(run(df, 1)) <= len(run(df, 0))
