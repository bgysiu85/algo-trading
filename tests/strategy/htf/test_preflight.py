"""Tests for strategy/htf/preflight.py (G2). W15-0004 step 4."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import bars as B
from strategy.htf import preflight as P


def _synth_1h(n_days=900, seed=7):
    """Multi-year synthetic CL.c.0 1-hour bars: a random-walk-with-drift
    close, enough sessions (~900 trading days spans well over the 200-bar
    4H warm-up and the 60-bar daily warm-up) to generate real MACD crosses
    on every entry chart. One held_id throughout (no rolls -- roll handling
    is bars.py's/back_adjust's job, already tested there)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-06-07", periods=24 * n_days, freq="h", tz="UTC")
    steps = rng.normal(loc=0.002, scale=0.35, size=len(idx))
    # add a slow sine drift so MACD actually crosses both ways repeatedly
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


class TestPrepareGrids:
    def test_returns_the_three_entry_grids_and_daily(self, grids_and_daily):
        grids, daily_adj = grids_and_daily
        assert set(grids.keys()) == {"1H", "2H", "4H"}
        for g in grids.values():
            assert "close_adj" in g.columns
        assert "close_adj" in daily_adj.columns


class TestDetectV0Invariants:
    """Every trigger must land in exactly one bucket -- no trigger silently
    vanishes and none is double-counted."""

    @pytest.mark.parametrize("scenario", list(P.ALL_SCENARIOS))
    def test_counts_partition_every_trigger(self, grids_and_daily, scenario):
        grids, daily_adj = grids_and_daily
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        entries, counts = P.detect_v0(entry_adj, daily_adj, scenario=scenario)
        accounted = (counts["lapsed"] + counts["blocked_daily_filter"]
                    + counts["blocked_end_of_session"] + counts["voided"]
                    + counts["entries"])
        assert accounted == counts["triggers"]
        assert len(entries) == counts["entries"]

    @pytest.mark.parametrize("scenario", list(P.ALL_SCENARIOS))
    def test_entries_have_positive_stop_distance(self, grids_and_daily, scenario):
        grids, daily_adj = grids_and_daily
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        entries, _ = P.detect_v0(entry_adj, daily_adj, scenario=scenario)
        assert entries, "fixture should produce at least one v0 entry"
        assert all(e["stop_dist"] > 0 for e in entries)

    def test_intraday_scenarios_never_fill_on_the_sessions_last_bar(self, grids_and_daily):
        grids, daily_adj = grids_and_daily
        for scenario in P.INTRADAY_SCENARIOS:
            entry_adj = grids[P.SCENARIO_GRID[scenario]]
            bar_hours = B.GRID_HOURS[P.SCENARIO_GRID[scenario]]
            last_bucket = 22 // bar_hours
            entries, _ = P.detect_v0(entry_adj, daily_adj, scenario=scenario)
            fill_buckets = {pd.Timestamp(e["t_open"]) for e in entries}
            # cross-check: no entry's t_open bucket index equals last_bucket
            bar_of_t_open = dict(zip(entry_adj["t_open"], entry_adj["bar"]))
            assert all(bar_of_t_open[t] != last_bucket for t in fill_buckets)

    def test_b_scenario_allows_holding_into_the_sessions_last_bar(self, grids_and_daily):
        """B is NOT intraday -- it must not apply the end-of-session block."""
        grids, daily_adj = grids_and_daily
        entry_adj = grids["4H"]
        _, counts = P.detect_v0(entry_adj, daily_adj, scenario="B")
        assert counts["blocked_end_of_session"] == 0


class TestDetectC1:
    @pytest.mark.parametrize("scenario", list(P.ALL_SCENARIOS))
    def test_no_confirmation_window_fills_at_trigger_plus_one(self, grids_and_daily, scenario):
        grids, _ = grids_and_daily
        entry_adj = grids[P.SCENARIO_GRID[scenario]]
        close = entry_adj["close_adj"]
        import strategy.htf.signals as SIG
        macd_line, signal_line = SIG.macd_seeded(close)
        up = SIG.macd_cross_up(macd_line, signal_line)
        down = SIG.macd_cross_down(macd_line, signal_line)
        ready = SIG.entry_ready_mask(entry_adj)
        trigger_positions = sorted(np.where(((up | down) & ready).to_numpy())[0].tolist())

        entries, counts = P.detect_c1(entry_adj, scenario=scenario)
        assert counts["triggers"] == len(trigger_positions)
        # C1 has no daily filter at all
        assert counts["blocked_daily_filter"] == 0

    def test_counts_partition_every_trigger(self, grids_and_daily):
        grids, _ = grids_and_daily
        entry_adj = grids["4H"]
        entries, counts = P.detect_c1(entry_adj, scenario="B")
        accounted = (counts["lapsed"] + counts["blocked_daily_filter"]
                    + counts["blocked_end_of_session"] + counts["voided"]
                    + counts["entries"])
        assert accounted == counts["triggers"]


class TestInitialStop:
    def test_uses_confirmed_swing_low_minus_a_tick_when_valid(self):
        import strategy.htf.signals as SIG
        low = pd.Series([10, 9, 8, 5, 8, 9, 10, 11, 12], dtype=float)
        swing_low = SIG.swing_lows(low, L=2, R=2).ffill()
        swing_high = SIG.swing_highs(pd.Series([10] * 9, dtype=float), L=2, R=2).ffill()
        stop = P._initial_stop("long", fill_idx=6, fill_price=20.0,
                               swing_low=swing_low, swing_high=swing_high,
                               low_adj=low.to_numpy(), high_adj=np.full(9, 10.0))
        assert stop == pytest.approx(5.0 - 0.01)

    def test_falls_back_to_5_bar_low_when_swing_is_at_or_above_fill(self):
        import strategy.htf.signals as SIG
        # confirmed swing low at index3 (value 5, known from index5 on); a
        # deeper, NOT-YET-CONFIRMED low at index9 (value 2) sits inside the
        # last-5-bars fallback window at fill_idx=10 but isn't reflected in
        # swing_low yet (confirmation needs 2 more bars) -- so the swing
        # (4.99) is invalid against a fill of 3.0, and the fallback (which
        # reads raw lows, not confirmed pivots) correctly finds the 2.0 low.
        low = pd.Series([10, 9, 8, 5, 8, 9, 10, 11, 12, 2, 9, 9], dtype=float)
        swing_low = SIG.swing_lows(low, L=2, R=2).ffill()
        swing_high = SIG.swing_highs(pd.Series([10] * 12, dtype=float), L=2, R=2).ffill()
        assert swing_low.iloc[10] == pytest.approx(5.0)  # sanity: not yet updated to 2
        stop = P._initial_stop("long", fill_idx=10, fill_price=3.0,
                               swing_low=swing_low, swing_high=swing_high,
                               low_adj=low.to_numpy(), high_adj=np.full(12, 10.0))
        expected = low.to_numpy()[5:10].min() - 0.01  # window low_adj[5:10] -> includes index9=2
        assert stop == pytest.approx(expected)

    def test_voided_when_even_the_fallback_is_at_or_above_fill(self):
        low = pd.Series([10.0] * 9)
        empty_swing = pd.Series([np.nan] * 9)
        stop = P._initial_stop("long", fill_idx=6, fill_price=1.0,
                               swing_low=empty_swing, swing_high=empty_swing,
                               low_adj=low.to_numpy(), high_adj=np.full(9, 10.0))
        assert stop is None

    def test_short_mirrors_long(self):
        import strategy.htf.signals as SIG
        high = pd.Series([10, 11, 12, 15, 12, 11, 10, 9, 8], dtype=float)
        swing_high = SIG.swing_highs(high, L=2, R=2).ffill()
        swing_low = SIG.swing_lows(pd.Series([10] * 9, dtype=float), L=2, R=2).ffill()
        stop = P._initial_stop("short", fill_idx=5, fill_price=0.0,
                               swing_low=swing_low, swing_high=swing_high,
                               low_adj=np.full(9, 10.0), high_adj=high.to_numpy())
        assert stop == pytest.approx(15.0 + 0.01)


class TestSummarize:
    def test_slices_to_training_window_only(self):
        entries = [
            {"session": "2015-06-01", "year": 2015, "stop_dist": 1.0, "hours_left": None},
            {"session": "2022-01-05", "year": 2022, "stop_dist": 1.0, "hours_left": None},  # outside training
        ]
        counts = {"triggers": 2, "lapsed": 0, "blocked_daily_filter": 0,
                 "blocked_end_of_session": 0, "voided": 0, "entries": 2}
        out = P.summarize(entries, counts, scenario="B")
        assert out["totals"]["entries_training"] == 1
        assert 2015 in out["per_year"] and 2022 not in out["per_year"]

    def test_underpowered_flag(self):
        entries = [{"session": "2015-06-01", "year": 2015, "stop_dist": 1.0, "hours_left": None}]
        counts = {"triggers": 1, "lapsed": 0, "blocked_daily_filter": 0,
                 "blocked_end_of_session": 0, "voided": 0, "entries": 1}
        out = P.summarize(entries, counts, scenario="B")
        assert out["totals"]["underpowered"] is True

    def test_not_underpowered_above_the_threshold(self):
        entries = [{"session": "2015-06-01", "year": 2015, "stop_dist": 1.0, "hours_left": None}] * 150
        counts = {"triggers": 150, "lapsed": 0, "blocked_daily_filter": 0,
                 "blocked_end_of_session": 0, "voided": 0, "entries": 150}
        out = P.summarize(entries, counts, scenario="B")
        assert out["totals"]["underpowered"] is False
        assert out["totals"]["entries_training"] == 150
