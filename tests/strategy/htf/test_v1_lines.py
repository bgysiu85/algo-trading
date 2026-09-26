"""Tests for strategy/htf/v1_lines.py (v1's T route and F2 filter). W15-0011."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B
from strategy.htf import preflight as P
from strategy.htf import tl_variant as TLV
from strategy.htf import v1_lines as V1L


def _synth_1h(n_days=900, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-06-07", periods=24 * n_days, freq="h", tz="UTC")
    steps = rng.normal(loc=0.002, scale=0.35, size=len(idx))
    t = np.arange(len(idx))
    drift = 3.0 * np.sin(t / 800.0)
    close = 50.0 + np.cumsum(steps) * 0.05 + drift
    close = np.clip(close, 5.0, None)
    high = close + np.abs(rng.normal(0.1, 0.05, len(idx)))
    low = close - np.abs(rng.normal(0.1, 0.05, len(idx)))
    open_ = close - rng.normal(0, 0.05, len(idx))
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": 100.0, "held_id": 1}, index=idx)
    return df


@pytest.fixture(scope="module")
def grids_and_daily():
    df_1h = _synth_1h()
    return P.prepare_grids(df_1h)


@pytest.fixture(scope="module")
def four_h_lines(grids_and_daily):
    grids, _ = grids_and_daily
    four_h_adj = grids["4H"]
    line_low, line_high, atr = V1L.build_4h_lines(four_h_adj)
    return four_h_adj, line_low, line_high, atr


class TestBuild4hLines:
    def test_shapes_match_frame(self, four_h_lines):
        four_h_adj, line_low, line_high, atr = four_h_lines
        n = len(four_h_adj)
        assert line_low.shape == (n,)
        assert line_high.shape == (n,)
        assert atr.shape == (n,)

    def test_some_bars_have_an_active_line(self, four_h_lines):
        """On 900 days of synthetic data with real swings, at least some
        bars must have an active rising or falling line -- otherwise the
        pivot/walk wiring itself is broken, not just quiet."""
        _, line_low, line_high, _ = four_h_lines
        assert np.isfinite(line_low).any()
        assert np.isfinite(line_high).any()


class TestTCondition:
    def test_touch_and_close_beyond_fires_for_long(self):
        n = 60
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        low[10] = 95.0
        low[30] = 98.0
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        line_low, line_high, atr = V1L.build_4h_lines(four_h)
        t4 = 40
        assert not np.isnan(line_low[t4]), "expected an active rising line by bar 40"
        # slope of rising line: (98-95)/20 = 0.15 per bar, ref at idx 29 (value 98)
        for off in V1L.T_OFFSETS:
            k = t4 - off
            lv = line_low[k]
            low[k] = lv + 0.01
            close[k] = lv + 0.5
            four_h.loc[four_h.index[k], "low_adj"] = low[k]
            four_h.loc[four_h.index[k], "close_adj"] = close[k]
        # every close from k..t4 must stay beyond the line
        for j in range(t4 - max(V1L.T_OFFSETS), t4 + 1):
            if not np.isnan(line_low[j]) and close[j] <= line_low[j]:
                close[j] = line_low[j] + 0.5
                four_h.loc[four_h.index[j], "close_adj"] = close[j]
        assert V1L.t_condition("long", t4, four_h, line_low, line_high, atr)

    def test_no_touch_means_no_signal(self, four_h_lines):
        four_h_adj, line_low, line_high, atr = four_h_lines
        # pick an early bar before any line could be active
        assert not V1L.t_condition("long", 1, four_h_adj, line_low, line_high, atr)
        assert not V1L.t_condition("short", 1, four_h_adj, line_low, line_high, atr)

    def test_out_of_range_t4_is_false(self, four_h_lines):
        four_h_adj, line_low, line_high, atr = four_h_lines
        assert not V1L.t_condition("long", -1, four_h_adj, line_low, line_high, atr)
        assert not V1L.t_condition("long", len(four_h_adj) + 5, four_h_adj, line_low, line_high, atr)


class TestF2DirectionBlock:
    def test_no_touched_line_in_window_means_no_block(self):
        n = 20
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        line_low = np.full(n, np.nan)
        line_high = np.full(n, np.nan)
        atr = np.full(n, 1.0)
        assert not V1L.f2_direction_block("long", 15, four_h, line_low, line_high, atr)
        assert not V1L.f2_direction_block("short", 15, four_h, line_low, line_high, atr)

    def test_falling_line_touch_blocks_longs_only(self):
        n = 20
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        atr = np.full(n, 1.0)
        line_low = np.full(n, np.nan)
        line_high = np.full(n, np.nan)
        touch_bar = 12
        line_high[touch_bar] = high[touch_bar] - 0.1  # within 0.25*ATR
        assert V1L.f2_direction_block("long", 15, four_h, line_low, line_high, atr)
        assert not V1L.f2_direction_block("short", 15, four_h, line_low, line_high, atr)

    def test_rising_line_touch_blocks_shorts_only(self):
        n = 20
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        atr = np.full(n, 1.0)
        line_low = np.full(n, np.nan)
        line_high = np.full(n, np.nan)
        touch_bar = 12
        line_low[touch_bar] = low[touch_bar] + 0.1  # within 0.25*ATR
        assert V1L.f2_direction_block("short", 15, four_h, line_low, line_high, atr)
        assert not V1L.f2_direction_block("long", 15, four_h, line_low, line_high, atr)

    def test_most_recent_touch_wins_over_an_earlier_one(self):
        n = 20
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        atr = np.full(n, 1.0)
        line_low = np.full(n, np.nan)
        line_high = np.full(n, np.nan)
        # earlier touch on the rising line, later touch on the falling line
        line_low[8] = low[8] + 0.1
        line_high[12] = high[12] - 0.1
        assert V1L.f2_direction_block("long", 15, four_h, line_low, line_high, atr)
        assert not V1L.f2_direction_block("short", 15, four_h, line_low, line_high, atr)

    def test_touch_outside_lookback_window_is_ignored(self):
        n = 50
        idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
        close = 100.0 + np.arange(n) * 0.0001
        high = close + 0.5
        low = close - 0.5
        four_h = pd.DataFrame({"t_open": idx, "high_adj": high, "low_adj": low,
                              "close_adj": close})
        atr = np.full(n, 1.0)
        line_low = np.full(n, np.nan)
        line_high = np.full(n, np.nan)
        t4 = 45
        touch_bar = t4 - V1L.F2_LOOKBACK_4H - 5  # well before the window
        line_high[touch_bar] = high[touch_bar] - 0.1
        assert not V1L.f2_direction_block("long", t4, four_h, line_low, line_high, atr)
