"""Tests for strategy/htf/v1_exits.py (X1/X2 layered on S1/S2). W15-0011."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import v1_exits as V1E


def _hourly_frame(n_buckets: int, bar_hours: int = 4, price: float = 100.0):
    """A single-session hourly frame with n_buckets entry-chart buckets of
    bar_hours hours each, flat OHLC at `price` unless a test overrides a
    row. 'bar' runs 0..n_buckets*bar_hours-1 (elapsed hours), matching
    bars.resample's own convention so bar // bar_hours reproduces the
    entry-chart bucket index exactly."""
    n = n_buckets * bar_hours
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    session = pd.Series(["2020-01-02"] * n)
    bar = np.arange(n)
    df = pd.DataFrame({
        "session": session, "bar": bar, "t_open": idx,
        "open_adj": price, "high_adj": price + 0.01, "low_adj": price - 0.01,
        "close_adj": price,
    })
    return df


def _entry_adj_frame(n_buckets: int):
    """The matching entry-chart frame: one row per bucket, bar = bucket
    index (bars.resample's own convention)."""
    idx = pd.date_range("2020-01-01", periods=n_buckets, freq="4h", tz="UTC")
    return pd.DataFrame({"session": ["2020-01-02"] * n_buckets,
                        "bar": np.arange(n_buckets), "t_open": idx})


class TestXSignalSeries:
    def test_x1_long_fires_on_hist_crossing_to_le_zero(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([1.0, 0.5, 0.1, -0.2, -1.0], index=idx)
        ema9 = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0], index=idx)
        x1_long, x1_short, x2_long, x2_short = V1E.x_signal_series(hist, ema9)
        assert bool(x1_long.iloc[3])   # 0.1 -> -0.2: crosses to <= 0
        assert not bool(x1_long.iloc[4])  # already <=0 the bar before -- no NEW cross
        assert not x1_short.any()

    def test_x1_short_fires_on_hist_crossing_to_ge_zero(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([-1.0, -0.5, -0.1, 0.2, 1.0], index=idx)
        ema9 = pd.Series([1.0] * 5, index=idx)
        x1_long, x1_short, _, _ = V1E.x_signal_series(hist, ema9)
        assert bool(x1_short.iloc[3])
        assert not x1_long.any()

    def test_x2_long_fires_when_ema9_turns_down(self):
        """x2_long/x2_short are evaluated bar-by-bar (rising vs falling
        that specific bar), not as a single whole-series 'the turn' event
        -- so EMA9's earlier rise (bars 1, 2) correctly flags x2_short
        there; only bar 3, where it falls, must flag x2_long, and the two
        must be mutually exclusive AT THAT BAR."""
        idx = pd.date_range("2020-01-01", periods=4, freq="4h", tz="UTC")
        hist = pd.Series([1.0] * 4, index=idx)
        ema9 = pd.Series([1.0, 2.0, 3.0, 2.5], index=idx)
        _, _, x2_long, x2_short = V1E.x_signal_series(hist, ema9)
        assert bool(x2_long.iloc[3])
        assert not bool(x2_short.iloc[3])
        assert not x2_long.iloc[:3].any()

    def test_x2_short_fires_when_ema9_turns_up(self):
        idx = pd.date_range("2020-01-01", periods=4, freq="4h", tz="UTC")
        hist = pd.Series([-1.0] * 4, index=idx)
        ema9 = pd.Series([3.0, 2.0, 1.0, 1.5], index=idx)
        _, _, x2_long, x2_short = V1E.x_signal_series(hist, ema9)
        assert bool(x2_short.iloc[3])
        assert not bool(x2_long.iloc[3])
        assert not x2_short.iloc[:3].any()


class TestXSignalSeriesX2Bars:
    """The sec 3 neighbour-grid X2 axis: x2_bars=1 (primary, tested above
    via the default) vs x2_bars=2 ('2 bars in a row' -- two consecutive
    down-moves for long, up-moves for short)."""

    def test_rejects_anything_other_than_1_or_2(self):
        idx = pd.date_range("2020-01-01", periods=3, freq="4h", tz="UTC")
        hist = pd.Series([1.0] * 3, index=idx)
        ema9 = pd.Series([1.0, 2.0, 3.0], index=idx)
        with pytest.raises(ValueError):
            V1E.x_signal_series(hist, ema9, x2_bars=3)

    def test_x2_bars_2_needs_two_consecutive_down_moves_for_long(self):
        # bars:      0     1     2     3     4
        # ema9:    1.0   2.0   3.0   2.5   2.0   (rises, rises, falls, falls)
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([1.0] * 5, index=idx)
        ema9 = pd.Series([1.0, 2.0, 3.0, 2.5, 2.0], index=idx)
        _, _, x2_long, _ = V1E.x_signal_series(hist, ema9, x2_bars=2)
        assert not bool(x2_long.iloc[3]), "only ONE down-move so far (bar 2->3)"
        assert bool(x2_long.iloc[4]), "TWO down-moves in a row (bar 2->3->4)"

    def test_x2_bars_1_fires_on_the_first_down_move_alone(self):
        """Same series as above: x2_bars=1 must already fire at bar 3,
        unlike x2_bars=2 which needs to wait one more bar."""
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([1.0] * 5, index=idx)
        ema9 = pd.Series([1.0, 2.0, 3.0, 2.5, 2.0], index=idx)
        _, _, x2_long, _ = V1E.x_signal_series(hist, ema9, x2_bars=1)
        assert bool(x2_long.iloc[3])
        assert bool(x2_long.iloc[4])

    def test_x2_bars_2_short_needs_two_consecutive_up_moves(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([-1.0] * 5, index=idx)
        ema9 = pd.Series([3.0, 2.0, 1.0, 1.5, 2.0], index=idx)
        _, _, _, x2_short = V1E.x_signal_series(hist, ema9, x2_bars=2)
        assert not bool(x2_short.iloc[3])
        assert bool(x2_short.iloc[4])

    def test_x2_bars_2_long_and_short_are_still_mutually_exclusive_at_a_bar(self):
        idx = pd.date_range("2020-01-01", periods=5, freq="4h", tz="UTC")
        hist = pd.Series([1.0] * 5, index=idx)
        ema9 = pd.Series([1.0, 2.0, 3.0, 2.5, 2.0], index=idx)
        _, _, x2_long, x2_short = V1E.x_signal_series(hist, ema9, x2_bars=2)
        assert not (bool(x2_long.iloc[4]) and bool(x2_short.iloc[4]))


class TestEntryBarLookup:
    def test_lookup_matches_bucket_to_row(self):
        entry_adj = _entry_adj_frame(5)
        lookup = V1E.entry_bar_lookup(entry_adj)
        assert lookup[("2020-01-02", 0)] == 0
        assert lookup[("2020-01-02", 4)] == 4
        assert len(lookup) == 5


class TestSimulateExitV1:
    def _flags(self, n_buckets, x1_bucket=None, x1_dir="long", x2_bucket=None, x2_dir="long"):
        x1_long = np.zeros(n_buckets, dtype=bool)
        x1_short = np.zeros(n_buckets, dtype=bool)
        x2_long = np.zeros(n_buckets, dtype=bool)
        x2_short = np.zeros(n_buckets, dtype=bool)
        if x1_bucket is not None:
            (x1_long if x1_dir == "long" else x1_short)[x1_bucket] = True
        if x2_bucket is not None:
            (x2_long if x2_dir == "long" else x2_short)[x2_bucket] = True
        return x1_long, x1_short, x2_long, x2_short

    def test_x1_exits_at_the_open_of_the_bucket_after_the_signal_bucket(self):
        n_buckets = 6
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        # signal fires at bucket 2 (fill at bucket 0) -> exit at bucket 3's
        # first hour (pos = 3*4 = 12)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets, x1_bucket=2, x1_dir="long")
        # give bucket 3's open a distinct price so we can confirm it's used
        hourly.loc[12, "open_adj"] = 123.45
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason == V1E.R_X1
        assert outcome.exit_pos == 12
        assert outcome.exit_price == pytest.approx(123.45)

    def test_x2_exits_at_the_open_of_the_bucket_after_the_signal_bucket(self):
        n_buckets = 6
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets, x2_bucket=1, x2_dir="short")
        hourly.loc[8, "open_adj"] = 88.0
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="short",
            fill_price=100.0, initial_stop=110.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason == V1E.R_X2
        assert outcome.exit_pos == 8
        assert outcome.exit_price == pytest.approx(88.0)

    def test_signal_on_the_fill_bar_itself_is_ignored(self):
        """X1/X2 only count for entry-chart bars strictly after the fill
        bar (sec 2.2: 'any entry-chart bar after the fill bar') -- a signal
        flagged on bucket 0 itself (the fill bucket) must not fire an
        exit."""
        n_buckets = 4
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets, x1_bucket=0, x1_dir="long")
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason == V1E.R_DATA_END

    def test_stop_hit_before_the_signal_bucket_closes_takes_precedence(self):
        """A stop hit strictly inside the bar that would have produced an
        X1 signal must win -- the walk never reaches the bucket-transition
        check for that bar because it already returned on the stop test."""
        n_buckets = 6
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        # signal flagged at bucket 2 (hours 8-11), but the stop is hit at
        # hour 9 (inside bucket 2, before it closes)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets, x1_bucket=2, x1_dir="long")
        hourly.loc[9, "low_adj"] = 80.0   # stop = 90.0, this hour's low breaches it
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason in (V1E.R_INITIAL_STOP, V1E.R_TRAILED_STOP)
        assert outcome.exit_pos == 9

    def test_x1_preferred_over_x2_when_both_fire_same_bucket(self):
        n_buckets = 4
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        x1_long = np.array([False, True, False, False])
        x2_long = np.array([False, True, False, False])
        x1_short = np.zeros(n_buckets, dtype=bool)
        x2_short = np.zeros(n_buckets, dtype=bool)
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason == V1E.R_X1

    def test_no_signal_falls_through_to_data_end(self):
        n_buckets = 3
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets)
        outcome = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome.reason == V1E.R_DATA_END

    def test_no_lookahead_a_bucket_far_after_the_exit_does_not_change_it(self):
        """G4-style guard: an X1/X2 flag set on a bucket far past where the
        walk already exited must not change that exit."""
        n_buckets = 8
        hourly = _hourly_frame(n_buckets)
        entry_adj = _entry_adj_frame(n_buckets)
        lookup = V1E.entry_bar_lookup(entry_adj)
        x1_long, x1_short, x2_long, x2_short = self._flags(n_buckets, x1_bucket=1, x1_dir="long")
        outcome_before = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        x1_long_mut = x1_long.copy()
        x1_long_mut[6] = True  # far after the bucket-1 signal already exits
        outcome_after = V1E.simulate_exit_v1(
            hourly, lookup, start_pos=0, fill_entry_idx=0, direction="long",
            fill_price=100.0, initial_stop=90.0, bar_hours=4, session_flatten=False,
            x1_long=x1_long_mut, x1_short=x1_short, x2_long=x2_long, x2_short=x2_short)
        assert outcome_before == outcome_after
