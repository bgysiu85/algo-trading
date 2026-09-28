"""Tests for strategy/w16/readback_trades.py (W16-0009 subitem 4).

Pins the pure comparison functions on synthetic frames -- no real archive
is touched. Modelled on tests/strategy/w16/test_readback.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import readback_trades as R


def _trades(minute_sizes: dict[str, list[int]], sides=None) -> pd.DataFrame:
    """A trades-shaped frame: one row per print, `minute_sizes` maps a
    'YYYY-MM-DD HH:MM' minute string to the list of print sizes inside it
    (spread evenly across the minute's 60 seconds)."""
    rows = []
    for minute, sizes in minute_sizes.items():
        base = pd.Timestamp(minute, tz="UTC")
        for i, sz in enumerate(sizes):
            rows.append({"ts": base + pd.Timedelta(seconds=i), "size": sz,
                        "side": (sides or {}).get(minute, ["B"] * len(sizes))[i]
                        if sides else "B"})
    if not rows:
        return pd.DataFrame(columns=["size", "side"]).set_index(
            pd.DatetimeIndex([], tz="UTC"))
    df = pd.DataFrame(rows).set_index("ts")
    return df


def _bar_volume(minute_volumes: dict[str, int]) -> pd.Series:
    idx = pd.DatetimeIndex([pd.Timestamp(m, tz="UTC") for m in minute_volumes], name="ts")
    return pd.Series(list(minute_volumes.values()), index=idx, name="volume")


class TestMinuteVolumeFromTrades:
    def test_empty_is_empty(self):
        out = R.minute_volume_from_trades(_trades({}))
        assert out.empty

    def test_sums_prints_within_a_minute(self):
        df = _trades({"2026-09-08 14:30": [3, 5, 2]})
        out = R.minute_volume_from_trades(df)
        assert out.iloc[0] == 10

    def test_seconds_floor_into_their_own_minute(self):
        df = _trades({"2026-09-08 14:30": [4], "2026-09-08 14:31": [6]})
        out = R.minute_volume_from_trades(df)
        assert len(out) == 2
        assert out[pd.Timestamp("2026-09-08 14:30", tz="UTC")] == 4
        assert out[pd.Timestamp("2026-09-08 14:31", tz="UTC")] == 6


class TestAggressorSideStats:
    def test_empty(self):
        out = R.aggressor_side_stats(_trades({}))
        assert out["n"] == 0 and out["pct_sided"] == 0.0

    def test_all_sided(self):
        df = _trades({"2026-09-08 14:30": [1, 1, 1]},
                     sides={"2026-09-08 14:30": ["B", "A", "B"]})
        out = R.aggressor_side_stats(df)
        assert out["n"] == 3 and out["n_sided"] == 3
        assert out["pct_sided"] == 1.0
        assert out["values"] == {"B": 2, "A": 1}

    def test_unresolved_prints_excluded_from_sided_count(self):
        df = _trades({"2026-09-08 14:30": [1, 1, 1, 1]},
                     sides={"2026-09-08 14:30": ["B", "A", "N", "N"]})
        out = R.aggressor_side_stats(df)
        assert out["n"] == 4 and out["n_sided"] == 2
        assert out["pct_sided"] == 0.5


class TestMinuteAgreement:
    def test_exact_match_all_pass(self):
        tv = R.minute_volume_from_trades(_trades({
            "2026-09-08 14:30": [10], "2026-09-08 14:31": [20]}))
        bv = _bar_volume({"2026-09-08 14:30": 10, "2026-09-08 14:31": 20})
        out = R.minute_agreement(tv, bv)
        assert out["n_compared"] == 2
        assert out["n_within_tol"] == 2
        assert out["pct_within_tol"] == 1.0
        assert out["passed"]

    def test_bar_anchored_ignores_minutes_the_bar_doesnt_have(self):
        """A minute with trades but no bar is not this check's problem
        (it's G1's, on the ohlcv-1m side) -- comparison is over the bar's
        own index only."""
        tv = R.minute_volume_from_trades(_trades({
            "2026-09-08 14:30": [10], "2026-09-08 14:35": [999]}))
        bv = _bar_volume({"2026-09-08 14:30": 10})
        out = R.minute_agreement(tv, bv)
        assert out["n_compared"] == 1
        assert out["pct_within_tol"] == 1.0

    def test_bar_minute_with_zero_trades_counts_as_a_full_miss(self):
        tv = R.minute_volume_from_trades(_trades({}))
        bv = _bar_volume({"2026-09-08 14:30": 10})
        out = R.minute_agreement(tv, bv)
        assert out["n_within_tol"] == 0
        assert out["misses"][0]["trades_volume"] == 0
        assert out["misses"][0]["bar_volume"] == 10

    def test_small_relative_drift_within_tolerance(self):
        # bar volume 10,000 -> tol = max(1, round(10000*0.001)) = 10
        tv = R.minute_volume_from_trades(_trades({"2026-09-08 14:30": [9995]}))
        bv = _bar_volume({"2026-09-08 14:30": 10000})
        out = R.minute_agreement(tv, bv)
        assert out["n_within_tol"] == 1

    def test_drift_beyond_tolerance_fails_that_minute(self):
        tv = R.minute_volume_from_trades(_trades({"2026-09-08 14:30": [9900]}))
        bv = _bar_volume({"2026-09-08 14:30": 10000})
        out = R.minute_agreement(tv, bv)
        assert out["n_within_tol"] == 0
        assert out["n_misses_total"] == 1

    def test_below_99pct_marks_the_check_failed(self):
        minutes = {f"2026-09-08 14:{m:02d}": 10 for m in range(30, 59)}  # 29 minutes
        bv = _bar_volume(minutes)
        # Only 27/29 (~93%) match -- two minutes get zero trades
        trade_minutes = {k: [10] for k in list(minutes)[:27]}
        tv = R.minute_volume_from_trades(_trades(trade_minutes))
        out = R.minute_agreement(tv, bv)
        assert out["n_compared"] == 29
        assert out["n_within_tol"] == 27
        assert out["pct_within_tol"] < 0.99
        assert not out["passed"]

    def test_empty_bar_index_is_zero_compared_not_a_crash(self):
        out = R.minute_agreement(pd.Series(dtype="int64"),
                                 pd.Series(dtype="int64"))
        assert out["n_compared"] == 0
        assert out["misses"] == []


class TestDayCoverage:
    def test_all_pulled_days_readable_and_nonempty_passes(self):
        out = R.day_coverage(["2026-09-08", "2026-09-09"],
                             ["2026-09-08", "2026-09-09"], [])
        assert out["passed"]
        assert out["n_missing"] == 0 and out["n_empty"] == 0

    def test_a_pulled_day_with_no_readable_file_is_missing(self):
        out = R.day_coverage(["2026-09-08", "2026-09-09"], ["2026-09-08"], [])
        assert not out["passed"]
        assert out["missing_days"] == ["2026-09-09"]

    def test_an_empty_file_is_reported_separately_from_missing(self):
        out = R.day_coverage(["2026-09-08", "2026-09-09"],
                             ["2026-09-08", "2026-09-09"], ["2026-09-09"])
        assert not out["passed"]
        assert out["empty_days"] == ["2026-09-09"]
        assert out["missing_days"] == []


class TestRunRoot:
    def test_all_checks_passing_gives_an_overall_pass(self):
        day_frames = {"2026-09-08": _trades(
            {"2026-09-08 14:30": [10]}, sides={"2026-09-08 14:30": ["B"]})}
        owned_1m = pd.DataFrame(
            {"volume": [10]},
            index=pd.DatetimeIndex([pd.Timestamp("2026-09-08 14:30", tz="UTC")]))
        out = R.run_root(day_frames, owned_1m, "ES", ["2026-09-08"])
        assert out["passed"]
        assert out["coverage"]["passed"]
        assert out["minute_volume_agreement"]["passed"]

    def test_missing_day_fails_the_whole_root(self):
        day_frames = {"2026-09-08": None}
        owned_1m = pd.DataFrame({"volume": []}, index=pd.DatetimeIndex([]))
        out = R.run_root(day_frames, owned_1m, "ES", ["2026-09-08", "2026-09-09"])
        assert not out["passed"]
        assert not out["coverage"]["passed"]
