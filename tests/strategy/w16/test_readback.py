"""Tests for strategy/w16/readback.py (G1). W16-0003 subitem 2.

Modelled on tests/strategy/htf/test_readback.py, adapted to a 1-minute
09:30-16:00 America/New_York session instead of CL's 18:00-17:00 Globex day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.w16 import readback as R


def _rth_session(date: str, n_minutes: int = 390, instrument_id: int = 1,
                  start_close: float = 4500.0) -> pd.DataFrame:
    """n_minutes of 1-minute ES-like bars covering one RTH session (09:30 ET
    start), UTC-indexed, strictly increasing closes."""
    start = pd.Timestamp(f"{date} 09:30", tz="America/New_York").tz_convert("UTC")
    idx = pd.date_range(start, periods=n_minutes, freq="min", tz="UTC")
    closes = start_close + np.arange(len(idx), dtype=float) * 0.25
    return pd.DataFrame({
        "open": closes - 0.25, "high": closes + 0.25, "low": closes - 0.25,
        "close": closes, "volume": 10.0, "instrument_id": instrument_id,
    }, index=idx)


def _sessions(dates, **kw) -> pd.DataFrame:
    frames = [_rth_session(d, **kw) for d in dates]
    return pd.concat(frames).sort_index()


class TestRthMask:
    def test_keeps_only_0930_to_1600(self):
        df = _rth_session("2024-01-03")
        naive = R.local_naive_et(df.index)
        mask = R.rth_mask(naive)
        assert mask.all(), "a full 390-minute session is entirely inside RTH"

    def test_excludes_premarket_and_afterhours(self):
        start = pd.Timestamp("2024-01-03 08:00", tz="America/New_York").tz_convert("UTC")
        idx = pd.date_range(start, periods=600, freq="min", tz="UTC")
        naive = R.local_naive_et(idx)
        mask = R.rth_mask(naive)
        # 08:00 -> 08:00+600min = 18:00; RTH portion is 09:30..16:00 = 390 min
        assert mask.sum() == 390


class TestBarsPerSession:
    def test_empty_input(self):
        empty = _rth_session("2024-01-03", n_minutes=0)
        out = R.bars_per_session(empty)
        assert out["n_sessions"] == 0
        assert out["total_rth_bars"] == 0

    def test_full_sessions_counted_correctly(self):
        df = _sessions(["2024-01-03", "2024-01-04", "2024-01-05"])
        out = R.bars_per_session(df)
        assert out["n_sessions"] == 3
        assert out["total_rth_bars"] == 3 * 390
        assert out["median"] == 390
        assert out["first_session"] == "2024-01-03"
        assert out["last_session"] == "2024-01-05"

    def test_short_session_shows_in_min(self):
        df = pd.concat([_rth_session("2024-01-03"), _rth_session("2024-01-04", n_minutes=200)])
        out = R.bars_per_session(df.sort_index())
        assert out["min"] == 200
        assert out["max"] == 390


class TestGapsOver:
    def test_no_gap_in_a_contiguous_session(self):
        df = _rth_session("2024-01-03")
        assert R.gaps_over(df) == []

    def test_flags_a_gap_over_five_minutes_inside_the_session(self):
        df = _rth_session("2024-01-03")
        # drop 10 consecutive minutes in the middle -> one gap > 5 min
        df2 = df.drop(df.index[100:110])
        gaps = R.gaps_over(df2)
        assert len(gaps) == 1
        assert gaps[0]["gap_minutes"] == pytest.approx(11.0)
        assert gaps[0]["session"] == "2024-01-03"

    def test_gap_of_exactly_five_minutes_is_not_flagged(self):
        df = _rth_session("2024-01-03")
        df2 = df.drop(df.index[100:104])  # removes 4 bars -> a 5-minute delta
        assert R.gaps_over(df2, minutes=5) == []

    def test_a_thin_minute_is_not_synthesised_into_a_gap_across_sessions(self):
        """A gap between two sessions (overnight) is a session boundary, not
        a gap 'inside' 09:30-16:00, and must not be reported."""
        df = _sessions(["2024-01-03", "2024-01-04"])
        assert R.gaps_over(df) == []


class TestRollSessions:
    def test_no_roll(self):
        df = _sessions(["2024-01-03", "2024-01-04"])
        assert R.roll_sessions(df) == []

    def test_flags_the_session_the_roll_lands_on(self):
        s1 = _rth_session("2024-01-03", instrument_id=1)
        s2 = _rth_session("2024-01-04", instrument_id=2)
        df = pd.concat([s1, s2]).sort_index()
        rolls = R.roll_sessions(df)
        assert len(rolls) == 1
        assert rolls[0]["session"] == "2024-01-04"
        assert rolls[0]["from_id"] == 1 and rolls[0]["to_id"] == 2

    def test_accepts_instrument_id_or_held_id_column(self):
        df = _rth_session("2024-01-03").rename(columns={"instrument_id": "held_id"})
        assert R.roll_sessions(df) == []  # no roll, single id -- just must not raise


class TestRunAgainstOwnedDaily:
    def test_perfect_agreement(self):
        df = _sessions(["2024-01-03", "2024-01-04", "2024-01-05"])
        # Build the "owned" daily close the same way the gate itself would --
        # UTC calendar day, last close of the day -- so a passing run is a
        # real assertion about the wiring, not a tautology against itself.
        d = df.copy()
        d["date"] = d.index.tz_convert("UTC").normalize().date
        owned = d.groupby("date").agg(open=("open", "first"), high=("high", "max"),
                                       low=("low", "min"), close=("close", "last"),
                                       volume=("volume", "sum")).reset_index()
        report = R.run(df, owned)
        assert report["passed"]
        assert report["daily_agreement"]["pct_within_tol"] == 1.0
        assert report["bars_per_session"]["n_sessions"] == 3

    def test_disagreement_fails_the_gate(self):
        df = _sessions(["2024-01-03", "2024-01-04"])
        d = df.copy()
        d["date"] = d.index.tz_convert("UTC").normalize().date
        owned = d.groupby("date").agg(close=("close", "last")).reset_index()
        owned["close"] = owned["close"] + 5.0  # well outside the $0.05 tolerance
        report = R.run(df, owned)
        assert not report["passed"]
        assert len(report["daily_agreement"]["misses"]) == 2
