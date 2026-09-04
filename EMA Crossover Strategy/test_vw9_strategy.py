#!/usr/bin/env python3
"""
Unit tests for vw9_strategy.py's regime gate and Setup A/B detection, on
hand-built bar sequences -- exactly the practice vw9_strategy_spec.md §12
step 5 calls for before running against real data: "a clean reclaim; a
reclaim that closes back below VWAP next bar [not applicable to counting,
see note below]; a pullback that breaches VWAP mid-pullback; an uncontrolled
pullback; ... a session where VWAP is degenerate for the first four bars."

WHY THERE IS NO "FAILED RECLAIM" TEST
--------------------------------------
The spec's Setup A trigger is unconditional the instant a bar closes above
both VWAP and the 9 EMA after a qualifying bearish stretch (§4.1) -- what
happens on the NEXT bar (price falling back below VWAP) is a §5.3 hard EXIT,
not something that un-fires the entry. Since this module only counts
triggers (§8.3, "before gates" -- and before exits, which don't exist yet),
a reclaim that immediately fails still counts as one Setup A. The failure
mode worth testing for Setup A instead is an INSUFFICIENT bearish streak
(< MIN_BELOW_BARS), which is what test_setup_a_needs_min_below_bars checks.

Every numeric scenario below was verified interactively (regime/atr printed
bar by bar) before being pinned into an assertion -- not hand-derived from
the EMA/VWAP formulas, which would be impractical past a handful of bars.
"""

from __future__ import annotations

import pandas as pd
import pytest

from vw9_strategy import (IMPULSE_LOOKBACK, MAX_PULLBACK_BARS,
                           MIN_BELOW_BARS, REGIME_BEARISH,
                           REGIME_STRONG, REGIME_WEAK_BULL, apply_indicators,
                           find_setups)

VOL = 100_000  # generous, so MIN_VWAP_DOLLAR_VOL matures on bar count alone


def make_bars(rows, start="2026-09-04 04:00", freq_min=15):
    """rows: list of (open, high, low, close, volume) tuples."""
    idx = pd.date_range(start, periods=len(rows), freq=f"{freq_min}min",
                        tz="America/New_York")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=idx)


def warmup(n=8, price=10.0, rng=0.3, vol=VOL):
    """Flat bars so neither EMA9 nor VWAP has moved by the time regime
    matures (bar 9, since EMA_FAST=9). Regime is None throughout -- there
    aren't yet 9 completed bars."""
    return [(price, price + rng, price - rng, price, vol)] * n


def impulse(start_close=10.0, step=0.15, n=20, rng=0.25, vol=VOL):
    """A gentle, steady climb. Gentle on purpose: EMA9 needs to track close
    enough to price that a pullback BELOW it doesn't also trip the
    PULLBACK_CTRL_ATR check by construction -- a steep climb leaves EMA9 far
    behind price, so crossing it requires a drop several ATRs wide before
    ATR itself has caught up to the trend's volatility. Verified interactively:
    at step=0.15/bar over 20 bars, EMA9 sits ~0.6 below price and ATR14 is
    ~0.64, so a ~0.8 pullback comfortably crosses EMA9 while staying inside
    1.5x ATR."""
    rows = []
    c = start_close
    for _ in range(n):
        o = c
        c = round(c + step, 2)
        h = round(max(o, c) + rng, 2)
        l = round(min(o, c) - rng, 2)
        rows.append((o, h, l, c, vol))
    return rows


# --- regime / maturity ------------------------------------------------

class TestRegimeMaturity:
    def test_regime_is_none_before_nine_bars(self):
        df = make_bars(warmup(8))
        sig = apply_indicators(df)
        assert sig["regime"].isna().all()

    def test_vwap_never_matures_on_starved_dollar_volume(self):
        """15 bars, well past MIN_VWAP_BARS(3) and EMA_FAST(9) bar counts,
        but at volume=10/bar and price=10 the cumulative dollar volume never
        reaches MIN_VWAP_DOLLAR_VOL($50,000) -- regime must stay None
        throughout, and find_setups must find nothing."""
        df = make_bars(warmup(15, vol=10))
        sig = apply_indicators(df)
        assert sig["regime"].isna().all()
        assert find_setups(df) == []

    def test_regime_classifies_bearish_and_strong_correctly(self):
        rows = warmup(8) + [(10.0, 8.1, 7.9, 8.0, VOL), (8.0, 8.1, 7.9, 8.0, VOL),
                            (8.0, 15.1, 7.9, 15.0, VOL)]
        df = make_bars(rows)
        sig = apply_indicators(df)
        assert sig["regime"].iloc[8] == REGIME_BEARISH
        assert sig["regime"].iloc[9] == REGIME_BEARISH
        assert sig["regime"].iloc[10] == REGIME_STRONG


# --- Setup A: VWAP reclaim ---------------------------------------------

class TestSetupA:
    def test_clean_reclaim_after_two_bearish_bars_fires(self):
        rows = warmup(8) + [(10.0, 8.1, 7.9, 8.0, VOL), (8.0, 8.1, 7.9, 8.0, VOL),
                            (8.0, 15.1, 7.9, 15.0, VOL)]
        df = make_bars(rows)
        setups = find_setups(df)
        assert len(setups) == 1
        assert setups[0].kind == "A"
        assert setups[0].bar_index == 10
        assert setups[0].entry_ref == pytest.approx(15.0)
        # structure_low = lowest low over the bearish stretch (both bars low 7.9)
        assert setups[0].structure_low == pytest.approx(7.9)

    def test_setup_a_needs_min_below_bars(self):
        """Only ONE bearish bar (MIN_BELOW_BARS=2 required) before the
        reclaim -- must not fire."""
        assert MIN_BELOW_BARS == 2, "test assumes the spec default of 2"
        rows = warmup(8) + [(10.0, 8.1, 7.9, 8.0, VOL), (8.0, 15.1, 7.9, 15.0, VOL)]
        df = make_bars(rows)
        assert find_setups(df) == []

    def test_reclaim_lookback_caps_structure_low(self):
        """A bearish stretch longer than RECLAIM_LOOKBACK(6) bars must only
        use the most recent 6 lows for structure_low, not the whole stretch
        -- an earlier, deeper low outside the window must not be picked up."""
        bearish_stretch = [(10.0, 8.1, 3.0, 8.0, VOL)]  # low=3.0, outside the window
        bearish_stretch += [(8.0, 8.1, 7.9, 8.0, VOL)] * 6  # 6 more bearish bars, low=7.9
        rows = warmup(8) + bearish_stretch + [(8.0, 15.1, 7.9, 15.0, VOL)]
        df = make_bars(rows)
        setups = find_setups(df)
        assert len(setups) == 1
        assert setups[0].structure_low == pytest.approx(7.9)  # NOT 3.0


# --- Setup B: 9 EMA retest ----------------------------------------------

class TestSetupB:
    def test_clean_retest_fires(self):
        rows = warmup() + impulse() + [
            (13.0, 13.0, 12.1, 12.2, VOL),   # pullback: below ema9, above vwap
            (12.2, 12.6, 12.15, 12.5, VOL),  # reclaim: closes back above ema9
        ]
        df = make_bars(rows)
        sig = apply_indicators(df)
        assert sig["regime"].iloc[28] == REGIME_WEAK_BULL   # the pullback bar
        assert sig["regime"].iloc[29] == REGIME_STRONG       # the reclaim bar
        setups = find_setups(df)
        assert len(setups) == 1
        assert setups[0].kind == "B"
        assert setups[0].bar_index == 29
        assert setups[0].entry_ref == pytest.approx(12.5)
        assert setups[0].structure_low == pytest.approx(12.1)

    def test_pullback_breaching_vwap_abandons_no_trigger(self):
        rows = warmup() + impulse() + [
            (13.0, 13.0, 10.5, 10.8, VOL),   # closes THROUGH vwap -> BEARISH
            (10.8, 12.6, 10.7, 12.5, VOL),   # would-be reclaim
        ]
        df = make_bars(rows)
        sig = apply_indicators(df)
        assert sig["regime"].iloc[28] == REGIME_BEARISH
        assert find_setups(df) == []

    def test_uncontrolled_pullback_abandons_no_trigger(self):
        """A single bar dropping more than PULLBACK_CTRL_ATR x atr14 kills
        the setup even though it lands in WEAK_BULL, not BEARISH."""
        rows = warmup() + impulse() + [
            (13.0, 13.0, 11.0, 11.2, VOL),   # drop 1.8 vs ~0.96 threshold
            (11.2, 12.6, 11.15, 12.5, VOL),
        ]
        df = make_bars(rows)
        sig = apply_indicators(df)
        assert sig["regime"].iloc[28] == REGIME_WEAK_BULL  # not bearish...
        assert find_setups(df) == []                        # ...but still abandoned

    def test_pullback_exceeding_max_bars_abandons_no_trigger(self):
        """Seven WEAK_BULL bars (MAX_PULLBACK_BARS=6) before the reclaim --
        one bar too many, so the eventual reclaim must not count."""
        assert MAX_PULLBACK_BARS == 6, "test assumes the spec default of 6"
        pullback = [(13.0, 13.0, 12.1, 12.2, VOL)]
        pc = 12.2
        for _ in range(6):
            nc = round(pc - 0.02, 2)
            pullback.append((pc, pc + 0.1, nc - 0.05, nc, VOL))
            pc = nc
        pullback.append((pc, pc + 0.6, pc - 0.05, pc + 0.5, VOL))  # 8th bar: reclaim attempt
        df = make_bars(warmup() + impulse() + pullback)
        assert find_setups(df) == []

    def test_pullback_blocked_without_recent_session_high(self):
        """The impulse's last new high is 12 bars before the pullback starts
        -- past IMPULSE_LOOKBACK(10) -- so the pullback must never arm, even
        though the price pattern is structurally identical to the clean-fire
        case above."""
        assert IMPULSE_LOOKBACK == 10, "test assumes the spec default of 10"
        stale = [(13.0, 13.05, 12.95, 13.0, VOL)] * 12
        pullback = [(13.0, 13.0, 12.1, 12.2, VOL), (12.2, 12.6, 12.15, 12.5, VOL)]
        df = make_bars(warmup() + impulse() + stale + pullback)
        assert find_setups(df) == []


# --- combined: a session producing both kinds ---------------------------

class TestCombined:
    def test_setup_a_then_setup_b_in_one_session_both_count(self):
        """A reclaim (Setup A) followed later by an impulse-and-retest
        (Setup B) in the same session: both must be counted, independently,
        which is exactly what §8.3 needs the totals to reflect."""
        reclaim = [(10.0, 8.1, 7.9, 8.0, VOL), (8.0, 8.1, 7.9, 8.0, VOL),
                   (8.0, 15.1, 7.9, 15.0, VOL)]
        rows = warmup() + reclaim + impulse(start_close=15.0) + [
            (18.0, 18.0, 17.1, 17.2, VOL), (17.2, 17.6, 17.15, 17.5, VOL),
        ]
        df = make_bars(rows)
        setups = find_setups(df)
        kinds = [s.kind for s in setups]
        assert "A" in kinds
        assert "B" in kinds


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
