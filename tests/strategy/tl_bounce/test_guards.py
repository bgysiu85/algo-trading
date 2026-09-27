#!/usr/bin/env python3
"""G5 look-ahead guards (REGISTERED_tl_bounce.md sec 5.1): every array this
study reads at bar j must be identical whether or not bars after j exist.
Proven by a CUT test -- the same technique strategy/tl_v0's own hindsight
guard uses (tests/test_tl_v0_hindsight_guard.py): run on the full series and
on a prefix, and require every value up to the cut to agree exactly.

This exercises pivots/lines (lines.entry_lines), touches (lines.touch_signals),
the E0 higher-chart filter (lines.e0_filter) and S2's swing pivots
(strategy.htf.signals.swing_lows/highs, reused verbatim) in one pass, because
a look-ahead in any of them would show up as a divergence before the cut.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf.signals import swing_highs, swing_lows
from strategy.tl_bounce.lines import e0_filter, entry_lines, touch_signals
from strategy.tl_bounce.spec import TRAIL_L, TRAIL_R


def _synthetic_ohlc(n, seed=7):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    trend = np.sin(t / 35) * 15 + t * 0.02
    noise = np.cumsum(rng.normal(0, 0.35, n))
    close = 60 + trend + noise
    high = close + np.abs(rng.normal(0, 0.6, n))
    low = close - np.abs(rng.normal(0, 0.6, n))
    open_ = close + rng.normal(0, 0.25, n)
    return open_, high, low, close


CUTS = [250, 400, 550]


@pytest.mark.parametrize("cut", CUTS)
def test_lines_and_touches_no_lookahead(cut):
    o, h, lo, c = _synthetic_ohlc(700)
    full = entry_lines(o, h, lo, c)
    part = entry_lines(o[:cut], h[:cut], lo[:cut], c[:cut])

    assert np.allclose(full.atr[:cut], part.atr, equal_nan=True)
    assert np.allclose(full.sup[:cut], part.sup, equal_nan=True)
    assert np.array_equal(full.sup_breaks[:cut], part.sup_breaks)
    assert np.allclose(full.res[:cut], part.res, equal_nan=True)
    assert np.array_equal(full.res_breaks[:cut], part.res_breaks)

    tl_full, ts_full = touch_signals(lo, h, c, full)
    tl_part, ts_part = touch_signals(lo[:cut], h[:cut], c[:cut], part)
    assert np.array_equal(tl_full[:cut], tl_part)
    assert np.array_equal(ts_full[:cut], ts_part)


@pytest.mark.parametrize("cut", CUTS)
def test_swing_pivots_no_lookahead(cut):
    _o, h, lo, _c = _synthetic_ohlc(700)
    full_lo = swing_lows(pd.Series(lo), TRAIL_L, TRAIL_R).to_numpy()
    part_lo = swing_lows(pd.Series(lo[:cut]), TRAIL_L, TRAIL_R).to_numpy()
    full_hi = swing_highs(pd.Series(h), TRAIL_L, TRAIL_R).to_numpy()
    part_hi = swing_highs(pd.Series(h[:cut]), TRAIL_L, TRAIL_R).to_numpy()
    assert np.allclose(full_lo[:cut], part_lo, equal_nan=True)
    assert np.allclose(full_hi[:cut], part_hi, equal_nan=True)


def _synthetic_1h_frame(n_sessions, seed=11):
    """A minimal back-adjusted-shaped 1H frame spanning n_sessions CME
    sessions, for e0_filter's higher-chart alignment test (no roll, no real
    calendar -- only t_open spacing and OHLC matter here)."""
    rng = np.random.default_rng(seed)
    n = n_sessions * 23
    start = pd.Timestamp("2019-01-06T23:00:00Z")  # a Sunday 18:00 ET open
    t_open = start + pd.to_timedelta(
        np.concatenate([np.arange(23) + s * 24 for s in range(n_sessions)]), unit="h")
    o, h, lo, c = _synthetic_ohlc(n, seed)
    return pd.DataFrame({"t_open": t_open, "open_adj": o, "high_adj": h,
                         "low_adj": lo, "close_adj": c})


def _resample_to_4h(frame_1h: pd.DataFrame) -> pd.DataFrame:
    d = frame_1h.copy()
    d["bucket"] = (d.index // 4)
    g = d.groupby("bucket")
    out = pd.DataFrame({
        "t_open": g["t_open"].first(),
        "open_adj": g["open_adj"].first(), "high_adj": g["high_adj"].max(),
        "low_adj": g["low_adj"].min(), "close_adj": g["close_adj"].last(),
    }).reset_index(drop=True)
    return out


def test_e0_filter_no_lookahead():
    f1h = _synthetic_1h_frame(30)
    higher = _resample_to_4h(f1h)
    full = e0_filter(f1h, higher, higher_bar_hours=4)
    cut = 300
    f1h_part = f1h.iloc[:cut].reset_index(drop=True)
    # only keep higher bars whose own interval is fully inside the cut
    higher_part = higher[higher["t_open"] + pd.Timedelta(hours=4)
                         <= f1h_part["t_open"].iloc[-1] + pd.Timedelta(hours=1)]
    part = e0_filter(f1h_part, higher_part.reset_index(drop=True), higher_bar_hours=4)
    assert np.array_equal(full[:cut], part)
