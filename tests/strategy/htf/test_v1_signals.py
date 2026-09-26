"""Tests for strategy/htf/v1_signals.py. W15-0011."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import preflight as P
from strategy.htf import v1_signals as V1S


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


class TestCurlTriggerSeries:
    def test_hand_built_curl_up_fires(self):
        idx = pd.date_range("2020-01-01", periods=10, freq="4h", tz="UTC")
        hist = pd.Series([1, 1, -3, -2, -1, 1, 1, 1, 1, 1], index=idx, dtype=float)
        curl_long, curl_short = V1S.curl_trigger_series(hist)
        # bar 4: hist[2]=-3 < hist[3]=-2 < hist[4]=-1, and hist[4] < 0 -> curl up
        assert bool(curl_long.iloc[4])
        assert not bool(curl_short.iloc[4])

    def test_hand_built_curl_down_fires(self):
        idx = pd.date_range("2020-01-01", periods=10, freq="4h", tz="UTC")
        hist = pd.Series([-1, -1, 3, 2, 1, -1, -1, -1, -1, -1], index=idx, dtype=float)
        curl_long, curl_short = V1S.curl_trigger_series(hist)
        assert bool(curl_short.iloc[4])
        assert not bool(curl_long.iloc[4])

    def test_no_curl_when_hist_already_positive_for_long(self):
        """hist[t] must be < 0 for a long curl (still below the signal
        line) -- a rising histogram that is already positive is not a curl
        trigger (it would already have crossed)."""
        idx = pd.date_range("2020-01-01", periods=10, freq="4h", tz="UTC")
        hist = pd.Series([1, 1, 1, 2, 3, 1, 1, 1, 1, 1], index=idx, dtype=float)
        curl_long, _ = V1S.curl_trigger_series(hist)
        assert not bool(curl_long.iloc[4])

    def test_flat_or_falling_hist_does_not_curl_up(self):
        idx = pd.date_range("2020-01-01", periods=10, freq="4h", tz="UTC")
        hist = pd.Series([-1, -1, -1, -1, -1, -1, -1, -1, -1, -1], index=idx, dtype=float)
        curl_long, curl_short = V1S.curl_trigger_series(hist)
        assert not curl_long.any()
        assert not curl_short.any()


class TestE2Confirms:
    def test_ema9_and_spread_both_rising_confirms_long(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        ema9 = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
        spread = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
        confirms_long, confirms_short = V1S.e2_confirms(ema9, spread)
        assert confirms_long.iloc[1:].all()
        assert not confirms_short.any()

    def test_ema9_and_spread_both_falling_confirms_short(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        ema9 = pd.Series([5, 4, 3, 2, 1], index=idx, dtype=float)
        spread = pd.Series([5, 4, 3, 2, 1], index=idx, dtype=float)
        confirms_long, confirms_short = V1S.e2_confirms(ema9, spread)
        assert confirms_short.iloc[1:].all()
        assert not confirms_long.any()

    def test_ema9_rising_but_spread_falling_confirms_neither(self):
        """Sec 2.1 E2 requires BOTH conditions -- EMA9 rising while the
        gap itself narrows (spread falling, for a long) must not confirm."""
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        ema9 = pd.Series([1, 2, 3, 4, 5], index=idx, dtype=float)
        spread = pd.Series([5, 4, 3, 2, 1], index=idx, dtype=float)
        confirms_long, confirms_short = V1S.e2_confirms(ema9, spread)
        assert not confirms_long.any()
        assert not confirms_short.any()


class TestF1RatioSeries:
    def test_ratio_is_max_abs_over_window_divided_by_atr(self):
        n = 20
        hist_4h = np.zeros(n)
        spread_4h = np.zeros(n)
        atr_4h = np.full(n, 2.0)
        hist_4h[12] = 6.0  # within the 9-bar window ending at 15
        ratio_h, ratio_e = V1S.f1_ratio_series(hist_4h, spread_4h, atr_4h, window=9)
        assert ratio_h[15] == pytest.approx(3.0)   # 6.0 / 2.0
        assert ratio_e[15] == pytest.approx(0.0)

    def test_value_outside_window_does_not_count(self):
        n = 30
        hist_4h = np.zeros(n)
        spread_4h = np.zeros(n)
        atr_4h = np.full(n, 2.0)
        hist_4h[5] = 100.0  # far before bar 25's 9-bar window [17, 25]
        ratio_h, _ = V1S.f1_ratio_series(hist_4h, spread_4h, atr_4h, window=9)
        assert ratio_h[25] == pytest.approx(0.0)

    def test_nan_atr_gives_nan_ratio(self):
        n = 10
        hist_4h = np.ones(n)
        spread_4h = np.ones(n)
        atr_4h = np.full(n, np.nan)
        ratio_h, ratio_e = V1S.f1_ratio_series(hist_4h, spread_4h, atr_4h)
        assert np.isnan(ratio_h).all()
        assert np.isnan(ratio_e).all()


class TestF1BlockedAt:
    def test_below_both_thresholds_blocks(self):
        ratio_h = np.array([0.1, 0.2, 0.3])
        ratio_e = np.array([0.1, 0.2, 0.3])
        assert V1S.f1_blocked_at(1, ratio_h, ratio_e, q_h=0.5, q_e=0.5)

    def test_above_either_threshold_does_not_block(self):
        ratio_h = np.array([0.1, 0.9, 0.3])
        ratio_e = np.array([0.1, 0.2, 0.3])
        assert not V1S.f1_blocked_at(1, ratio_h, ratio_e, q_h=0.5, q_e=0.5)

    def test_out_of_range_or_nan_does_not_block(self):
        ratio_h = np.array([np.nan, 0.2, 0.3])
        ratio_e = np.array([np.nan, 0.2, 0.3])
        assert not V1S.f1_blocked_at(0, ratio_h, ratio_e, q_h=0.5, q_e=0.5)
        assert not V1S.f1_blocked_at(-1, ratio_h, ratio_e, q_h=0.5, q_e=0.5)
        assert not V1S.f1_blocked_at(99, ratio_h, ratio_e, q_h=0.5, q_e=0.5)


class TestOnRealGrids:
    """Sanity checks against the module's real inputs (not hand-built),
    same spirit as test_tl_variant.py's grids_and_daily fixture use."""

    def test_entry_chart_indicators_shapes_and_some_triggers(self, grids_and_daily):
        grids, _ = grids_and_daily
        entry_adj = grids["4H"]
        macd_line, signal_line, hist, ema9, ema21, spread = V1S.entry_chart_indicators(entry_adj)
        n = len(entry_adj)
        assert len(hist) == n
        curl_long, curl_short = V1S.curl_trigger_series(hist)
        confirms_long, confirms_short = V1S.e2_confirms(ema9, spread)
        # on 900 days of synthetic data with real drift, expect at least
        # some bars of each -- otherwise the wiring itself is broken
        assert curl_long.any() or curl_short.any()
        assert confirms_long.any() or confirms_short.any()

    def test_four_h_indicators_align_with_build_4h_lines_atr(self, grids_and_daily):
        from strategy.htf import v1_lines as V1L
        grids, _ = grids_and_daily
        four_h_adj = grids["4H"]
        hist_4h, spread_4h = V1S.four_h_indicators(four_h_adj)
        _, _, atr = V1L.build_4h_lines(four_h_adj)
        assert len(hist_4h) == len(atr)
        ratio_h, ratio_e = V1S.f1_ratio_series(hist_4h, spread_4h, atr)
        assert len(ratio_h) == len(atr)
        assert np.isfinite(ratio_h).any()
