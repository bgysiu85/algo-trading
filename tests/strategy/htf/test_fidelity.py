"""Tests for strategy/htf/fidelity.py (W15-0005, sec 6.1)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import fidelity as F
from strategy.htf import preflight as P


def _synth_1h(n_days=900, seed=11):
    """Same generator as test_preflight.py's _synth_1h (kept local rather
    than imported, since that one is module-private there): enough sessions
    to clear both warm-ups and produce real v0 entries to test the window
    filter and the matcher against."""
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
def entry_daily():
    from strategy.htf import bars as B
    df_1h = _synth_1h()
    entry_adj = B.back_adjust(B.resample(df_1h, "4H"))
    daily_adj = B.back_adjust(B.daily(df_1h))
    return entry_adj, daily_adj


@pytest.fixture(scope="module")
def all_v0_entries(entry_daily):
    entry_adj, daily_adj = entry_daily
    entries, _ = P.detect_v0(entry_adj, daily_adj, scenario="B")
    assert entries, "fixture should produce at least one v0 entry"
    return entries


class TestWindowFilter:
    def test_keeps_only_entries_inside_the_window(self, entry_daily, all_v0_entries):
        entry_adj, daily_adj = entry_daily
        mid = pd.Timestamp(all_v0_entries[len(all_v0_entries) // 2]["t_open"])
        start = mid - pd.Timedelta(days=2)
        end = mid + pd.Timedelta(days=2)
        windowed = F.v0_entries_in_window(entry_adj, daily_adj, start, end)
        assert windowed
        assert all(start <= pd.Timestamp(e["t_open"]) < end for e in windowed)
        # and it's not just "everything" -- the full-series count is larger
        assert len(windowed) < len(all_v0_entries)

    def test_empty_window_returns_nothing(self, entry_daily):
        entry_adj, daily_adj = entry_daily
        # a window entirely before the warm-up period ends
        start = pd.Timestamp("2010-06-07", tz="UTC")
        end = pd.Timestamp("2010-06-08", tz="UTC")
        assert F.v0_entries_in_window(entry_adj, daily_adj, start, end) == []


class TestBarsInWindow:
    def test_counts_bars_actually_in_the_window(self, entry_daily):
        entry_adj, _daily_adj = entry_daily
        t = pd.to_datetime(entry_adj["t_open"], utc=True)
        mid = t.iloc[len(t) // 2]
        start, end = mid - pd.Timedelta(days=2), mid + pd.Timedelta(days=2)
        n = F.bars_in_window(entry_adj, start, end)
        assert n == int(((t >= start) & (t < end)).sum())
        assert n > 0

    def test_zero_for_a_window_outside_the_archive(self, entry_daily):
        entry_adj, _daily_adj = entry_daily
        far_future = pd.Timestamp("2099-01-01", tz="UTC")
        assert F.bars_in_window(entry_adj, far_future,
                                far_future + pd.Timedelta(days=7)) == 0


class TestMatchTrade:
    def test_matches_a_trade_on_the_same_side_and_bar(self, all_v0_entries):
        e = all_v0_entries[0]
        trade = {"trade_id": 1, "side": e["direction"],
                 "entry_time": e["t_open"], "entry_price": e["fill_price"]}
        m = F.match_trade(trade, all_v0_entries)
        assert m is not None
        assert m["t_open"] == e["t_open"]

    def test_no_match_on_the_opposite_side(self, all_v0_entries):
        e = all_v0_entries[0]
        opposite = "short" if e["direction"] == "long" else "long"
        trade = {"trade_id": 1, "side": opposite,
                 "entry_time": e["t_open"], "entry_price": e["fill_price"]}
        # only a same-side v0 entry may match, even at the identical time
        same_side_at_t = [x for x in all_v0_entries
                          if x["t_open"] == e["t_open"] and x["direction"] == opposite]
        m = F.match_trade(trade, all_v0_entries)
        if not same_side_at_t:
            assert m is None

    def test_no_match_far_outside_the_tolerance(self, all_v0_entries):
        e = all_v0_entries[0]
        far = pd.Timestamp(e["t_open"]) + pd.Timedelta(days=30)
        trade = {"trade_id": 1, "side": e["direction"],
                 "entry_time": str(far), "entry_price": e["fill_price"]}
        assert F.match_trade(trade, all_v0_entries) is None


class TestReplay:
    def test_a_trade_built_from_a_real_v0_entry_is_flagged_as_found(self, all_v0_entries):
        e = all_v0_entries[0]
        trade = {"trade_id": 1, "side": e["direction"],
                 "ben_entry_time": e["t_open"] if False else e["t_open"],
                 "entry_time": e["t_open"], "entry_price": e["fill_price"],
                 "exit_time": e["t_open"], "exit_price": e["fill_price"]}
        results = F.replay([trade], all_v0_entries)
        assert results[0]["v0_signal_found"] is True
        assert results[0]["same_bar"] is True

    def test_a_trade_with_no_nearby_v0_entry_is_flagged_as_mismatch(self, all_v0_entries):
        last = pd.Timestamp(all_v0_entries[-1]["t_open"])
        far = last + pd.Timedelta(days=60)
        trade = {"trade_id": 1, "side": "long", "entry_time": str(far),
                 "entry_price": 50.0, "exit_time": str(far), "exit_price": 51.0}
        results = F.replay([trade], all_v0_entries)
        assert results[0]["v0_signal_found"] is False
        assert "v0_fill_t_open" not in results[0]

    def test_no_p_and_l_field_anywhere_in_a_result_row(self, all_v0_entries):
        """Sec 6.1: 'computes no P&L for the window' -- a result row must
        never carry a P&L-shaped field, whatever else it reports."""
        e = all_v0_entries[0]
        trade = {"trade_id": 1, "side": e["direction"], "entry_time": e["t_open"],
                 "entry_price": e["fill_price"], "exit_time": e["t_open"],
                 "exit_price": e["fill_price"]}
        results = F.replay([trade], all_v0_entries)
        banned = {"pnl", "realized_pnl", "net", "p&l", "profit"}
        assert not (banned & set(results[0].keys()))
