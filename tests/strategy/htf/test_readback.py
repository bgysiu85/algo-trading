"""Tests for strategy/htf/readback.py (G1). W15-0004 step 2, Amendment B."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import readback as R


def _synth_1h(n_days: int = 12, held_id: int = 1) -> pd.DataFrame:
    """n_days of hourly CL.c.0 bars, UTC index, strictly increasing closes so
    a one-hour bucketing shift changes which bar lands last in each UTC day
    (and therefore changes the day's close)."""
    idx = pd.date_range("2015-03-01", periods=24 * n_days, freq="h", tz="UTC")
    closes = 50.0 + np.arange(len(idx), dtype=float) * 0.1
    return pd.DataFrame({
        "open": closes - 0.05, "high": closes + 0.05, "low": closes - 0.05,
        "close": closes, "volume": 100.0, "held_id": held_id,
    }, index=idx)


def _synth_1h_with_roll(n_days: int = 6) -> pd.DataFrame:
    """Like _synth_1h, but held_id changes to 2 on the first bar of day 3."""
    df = _synth_1h(n_days=n_days)
    roll_at = df.index[df.index.normalize() == df.index.normalize()[24 * 2]][0]
    df.loc[df.index >= roll_at, "held_id"] = 2
    return df


class TestUtcDaily:
    def test_empty_input(self):
        empty = _synth_1h(n_days=0)
        out = R.utc_daily(empty)
        assert list(out.columns) == ["date", "open", "high", "low", "close",
                                      "volume", "held_id"]
        assert out.empty

    def test_one_row_per_utc_calendar_day(self):
        df_1h = _synth_1h(n_days=5)
        out = R.utc_daily(df_1h)
        assert len(out) == 5
        assert list(out["date"]) == sorted(out["date"])

    def test_close_is_last_bar_of_the_utc_day(self):
        df_1h = _synth_1h(n_days=3)
        out = R.utc_daily(df_1h)
        day0 = df_1h[df_1h.index.normalize() == df_1h.index.normalize()[0]]
        assert out.iloc[0]["close"] == pytest.approx(day0["close"].iloc[-1])

    def test_ohlc_aggregation(self):
        df_1h = _synth_1h(n_days=2)
        out = R.utc_daily(df_1h)
        day0 = df_1h[df_1h.index.normalize() == df_1h.index.normalize()[0]]
        row = out.iloc[0]
        assert row["open"] == pytest.approx(day0["open"].iloc[0])
        assert row["high"] == pytest.approx(day0["high"].max())
        assert row["low"] == pytest.approx(day0["low"].min())
        assert row["volume"] == pytest.approx(day0["volume"].sum())

    def test_held_id_is_last_bar_of_day_across_a_roll(self):
        df_1h = _synth_1h_with_roll(n_days=6)
        out = R.utc_daily(df_1h)
        # roll lands on day index 2 (0-based) -- that day's held_id is the
        # NEW id (last bar of the day), not the old one
        assert out.iloc[1]["held_id"] == 1
        assert out.iloc[2]["held_id"] == 2


class TestUtcRollDays:
    def test_no_roll(self):
        assert R.utc_roll_days(_synth_1h(n_days=3)) == set()

    def test_flags_the_day_the_roll_lands_on(self):
        df_1h = _synth_1h_with_roll(n_days=6)
        roll_days = R.utc_roll_days(df_1h)
        assert len(roll_days) == 1
        expected = df_1h.index.normalize()[24 * 2].date()
        assert roll_days == {expected}


class TestDailyAgreement:
    def test_perfect_agreement_when_owned_matches_utc_rebuild(self):
        df_1h = _synth_1h(n_days=10)
        utc = R.utc_daily(df_1h)
        owned = utc.rename(columns={}).copy()  # same OHLCV, "independently pulled"
        agree = R.daily_agreement(utc, owned)
        assert agree["pct_within_tol"] == 1.0
        assert agree["misses"] == []

    def test_miss_flagged_as_roll_day_when_it_is_one(self):
        df_1h = _synth_1h_with_roll(n_days=6)
        utc = R.utc_daily(df_1h)
        owned = utc.copy()
        # perturb only the roll day's close beyond tolerance
        roll_day = sorted(R.utc_roll_days(df_1h))[0]
        owned.loc[owned["date"] == roll_day, "close"] += 1.0
        agree = R.daily_agreement(utc, owned, roll_days=R.utc_roll_days(df_1h))
        assert len(agree["misses"]) == 1
        assert agree["misses"][0]["is_roll_day"] is True

    def test_close_only_frames_still_work(self):
        df_1h = _synth_1h(n_days=4)
        utc = R.utc_daily(df_1h)[["date", "close"]]
        owned = utc.copy()
        agree = R.daily_agreement(utc, owned)
        assert agree["pct_within_tol"] == 1.0
        assert "high_1h" not in (agree["misses"][0] if agree["misses"] else {})


class TestShiftedBucketingBreaksTheMatch:
    """The guard this gate exists to enforce: a one-hour bucketing error must
    fail G1, not slip through as a rounding difference. Amendment B, step 2:
    'Add a test that shifting the bucketing by one hour breaks the match.'"""

    def test_one_hour_shift_drops_agreement_below_the_pass_threshold(self):
        df_1h = _synth_1h(n_days=30)
        correct = R.utc_daily(df_1h)
        owned = correct[["date", "close"]].copy()  # the "independently owned" truth

        shifted_1h = df_1h.copy()
        shifted_1h.index = shifted_1h.index + pd.Timedelta(hours=1)
        shifted = R.utc_daily(shifted_1h)

        agree = R.daily_agreement(shifted, owned)
        assert agree["pct_within_tol"] < R.PASS_PCT

    def test_one_hour_shift_does_not_affect_correct_bucketing(self):
        """Sanity check on the fixture itself: with NO shift, agreement is
        perfect, so the failure above is caused by the shift alone."""
        df_1h = _synth_1h(n_days=30)
        correct = R.utc_daily(df_1h)
        owned = correct[["date", "close"]].copy()
        agree = R.daily_agreement(correct, owned)
        assert agree["pct_within_tol"] == 1.0


class TestRunPassFailGating:
    """run()'s "passed" must be decided by the UTC-day comparison, not the
    ET session-grid one (Amendment B) -- a mutation check: swap which
    comparison gates and this test catches it."""

    def test_passed_key_matches_utc_agreement_not_session_grid(self, monkeypatch):
        df_1h = _synth_1h(n_days=20)
        utc = R.utc_daily(df_1h)
        owned = utc[["date", "close"]].copy()

        # session-grid rebuild deliberately disagrees with owned (simulates
        # the pre-Amendment-B 45.58% result) while the UTC one agrees fully
        bad_session_grid = owned.copy()
        bad_session_grid["close"] = bad_session_grid["close"] + 5.0

        import strategy.htf.bars as B
        monkeypatch.setattr(B, "load_1h", lambda archive: df_1h)
        monkeypatch.setattr(B, "daily", lambda d: bad_session_grid.assign(
            open=bad_session_grid["close"], high=bad_session_grid["close"],
            low=bad_session_grid["close"], volume=0.0))
        monkeypatch.setattr(B, "settlement_bar_mask",
                            lambda d: np.zeros(len(d), dtype=bool))
        monkeypatch.setattr(R, "owned_daily", lambda path: owned.assign(
            open=owned["close"], high=owned["close"], low=owned["close"], volume=0.0))

        report = R.run(archive_1h="unused", ohlcv1d_path="unused")
        assert report["passed"] is True
        assert report["daily_agreement"]["pct_within_tol"] == 1.0
        assert report["daily_agreement_session_grid_reported_only"]["pct_within_tol"] < 1.0
