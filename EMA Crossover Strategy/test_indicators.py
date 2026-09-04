#!/usr/bin/env python3
"""
Unit tests for indicators.py -- verify against independent reference
calculations, matching the project convention set by mcl_paper_trader.py's
RSI/MFI/MACD verification (agreement to <3e-14 against loop implementations).

Run:  pytest test_indicators.py -v
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from indicators import (atr, cum_dollar_volume, ema, resample_bars, rma,
                         session_vwap, true_range)


def _loop_ema(values: list[float], length: int) -> list[float]:
    """Independent reference: Pine/standard EMA recursion, computed by hand
    in a plain Python loop rather than via pandas .ewm()."""
    alpha = 2.0 / (length + 1.0)
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def _loop_rma(values: list[float], length: int) -> list[float]:
    alpha = 1.0 / length
    out = []
    prev = None
    for v in values:
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out.append(prev)
    return out


def _loop_tr(high, low, close) -> list[float]:
    out = []
    prev_close = None
    for h, l, c in zip(high, low, close):
        if prev_close is None:
            out.append(h - l)
        else:
            out.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = c
    return out


class TestEmaRma:
    def test_ema_matches_loop_reference(self):
        vals = [10, 10.5, 11, 10.8, 11.3, 12, 11.7, 12.5, 13, 12.8, 13.4, 14]
        got = ema(pd.Series(vals), 9).tolist()
        want = _loop_ema(vals, 9)
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-9

    def test_rma_matches_loop_reference(self):
        vals = [1, 2, 1.5, 3, 2.8, 4, 3.5, 5, 4.7, 6, 5.9, 7, 6.5, 8]
        got = rma(pd.Series(vals), 14).tolist()
        want = _loop_rma(vals, 14)
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-9

    def test_ema_agrees_with_mcl_strategy_definition(self):
        """indicators.ema must be bit-for-bit the same as
        ../MCL Strategy/mcl_strategy.py's ema() -- both are
        s.ewm(span=length, adjust=False).mean(). Cross-strategy comparisons
        (E15/VW9 vs V7/MC5) are meaningless if these silently diverge."""
        s = pd.Series([5, 5.2, 5.1, 5.4, 5.6, 5.3, 5.8, 6.0, 6.1, 5.9])
        mine = ema(s, 9)
        reference = s.ewm(span=9, adjust=False).mean()
        pd.testing.assert_series_equal(mine, reference)


class TestAtr:
    def test_true_range_matches_loop_reference(self):
        high = [10, 10.5, 10.3, 11, 10.8, 11.2]
        low = [9.5, 9.8, 9.9, 10.2, 10.1, 10.6]
        close = [9.8, 10.2, 10.0, 10.9, 10.3, 11.0]
        got = true_range(pd.Series(high), pd.Series(low), pd.Series(close)).tolist()
        want = _loop_tr(high, low, close)
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-9

    def test_first_bar_tr_is_high_minus_low(self):
        tr = true_range(pd.Series([10.0]), pd.Series([9.0]), pd.Series([9.5]))
        assert tr.iloc[0] == pytest.approx(1.0)

    def test_atr_is_rma_of_true_range(self):
        high = pd.Series([10, 10.5, 10.3, 11, 10.8, 11.2, 11.5, 11.3, 11.7, 12.0,
                          11.9, 12.2, 12.5, 12.3, 12.6])
        low = high - 0.5
        close = high - 0.2
        a = atr(high, low, close, length=14)
        tr = true_range(high, low, close)
        expected = rma(tr, 14)
        pd.testing.assert_series_equal(a, expected)


class TestSessionVwap:
    def test_vwap_on_single_bar_equals_typical_price(self):
        """§2.2: 'with one bar of data VWAP simply equals that bar's typical
        price' -- exact statement from the spec, tested literally."""
        v = session_vwap(pd.Series([10.0]), pd.Series([9.0]), pd.Series([9.6]),
                          pd.Series([1000]))
        typical = (10.0 + 9.0 + 9.6) / 3.0
        assert v.iloc[0] == pytest.approx(typical)

    def test_vwap_matches_hand_computed_reference(self):
        high = pd.Series([10.0, 10.4, 10.2])
        low = pd.Series([9.6, 10.0, 9.9])
        close = pd.Series([9.8, 10.3, 10.0])
        vol = pd.Series([1000, 2000, 1500])
        got = session_vwap(high, low, close, vol)

        typical = [(10.0 + 9.6 + 9.8) / 3.0, (10.4 + 10.0 + 10.3) / 3.0,
                   (10.2 + 9.9 + 10.0) / 3.0]
        cum_pv, cum_v, want = 0.0, 0.0, []
        for tp, v in zip(typical, vol):
            cum_pv += tp * v
            cum_v += v
            want.append(cum_pv / cum_v)
        for g, w in zip(got.tolist(), want):
            assert abs(g - w) < 1e-9

    def test_cum_dollar_volume_matches_hand_computed_reference(self):
        close = pd.Series([10.0, 10.5, 10.2])
        vol = pd.Series([1000, 2000, 500])
        got = cum_dollar_volume(close, vol).tolist()
        want = [10000.0, 10000.0 + 21000.0, 10000.0 + 21000.0 + 5100.0]
        for g, w in zip(got, want):
            assert abs(g - w) < 1e-6


class TestResampleBars:
    def _minute_frame(self, start, n, price_start=10.0, gap_at=None):
        """n consecutive 1-minute bars from `start`. gap_at, if given, is a
        set of offsets to OMIT -- simulating a minute with no print, exactly
        as IB does not return a bar for a minute nobody traded."""
        gap_at = gap_at or set()
        idx, rows = [], []
        for i in range(n):
            if i in gap_at:
                continue
            ts = start + pd.Timedelta(minutes=i)
            px = price_start + i * 0.01
            idx.append(ts)
            rows.append({"open": px, "high": px + 0.02, "low": px - 0.02,
                        "close": px + 0.01, "volume": 100 + i})
        return pd.DataFrame(rows, index=pd.DatetimeIndex(idx, tz="America/New_York"))

    def test_5m_bucket_aggregates_correctly(self):
        start = pd.Timestamp("2026-09-04 04:00", tz="America/New_York")
        df = self._minute_frame(start, 5)
        out = resample_bars(df, 5)
        assert len(out) == 1
        row = out.iloc[0]
        assert row["open"] == pytest.approx(df.iloc[0]["open"])
        assert row["close"] == pytest.approx(df.iloc[-1]["close"])
        assert row["high"] == pytest.approx(df["high"].max())
        assert row["low"] == pytest.approx(df["low"].min())
        assert row["volume"] == pytest.approx(df["volume"].sum())

    def test_bucket_with_zero_source_bars_is_dropped_not_synthesised(self):
        """The core E15/VW9 rule: a 15m interval with no trades produces NO
        row -- not a flat O=H=L=C=prior_close bar. Build 30 minutes where
        minutes 15-29 (the third 15m bucket) are entirely missing."""
        start = pd.Timestamp("2026-09-04 04:00", tz="America/New_York")
        gap = set(range(15, 30))
        df = self._minute_frame(start, 45, gap_at=gap)
        out = resample_bars(df, 15)
        # Bucket 04:00 (minutes 0-14, present) and 04:30 (minutes 30-44,
        # present) should exist. The 04:15 bucket (minutes 15-29, entirely
        # gapped) must be absent -- not present as a synthesised flat bar.
        assert len(out) == 2
        assert out.index[0] == start
        assert out.index[1] == start + pd.Timedelta(minutes=30)

    def test_requires_tz_aware_index(self):
        df = pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1],
                           "volume": [1]},
                          index=pd.DatetimeIndex([pd.Timestamp("2026-09-04")]))
        with pytest.raises(ValueError):
            resample_bars(df, 5)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
