"""Tests for strategy/htf/weekly.py -- weekly context (E6, sec 3 item 6).
W15-0004 step 7 checkpoint 9. Small synthetic daily_adj frames (business
days only, close monotonically rising or falling) so the weekly-aggregation
and EMA-warmup logic is exercised deterministically without needing a real
archive."""
from __future__ import annotations

import pandas as pd
import pytest

from strategy.htf import runner as R
from strategy.htf import weekly as W


def _daily_adj(n_days, start="2024-01-01", start_px=100.0, step=1.0):
    """n_days business-day sessions (Mon-Fri), close rising by `step` each
    day; open=high=low=close (flat intrabar, only the close path matters
    for a trend read)."""
    dates = pd.bdate_range(start=start, periods=n_days).date
    closes = [start_px + i * step for i in range(n_days)]
    return pd.DataFrame({"date": dates, "open_adj": closes, "high_adj": closes,
                         "low_adj": closes, "close_adj": closes})


def _trade(entry_t, direction="long", session="d1"):
    return R.Trade(session=session, direction=direction, entry_t=entry_t,
                   fill_adj=100.0, fill_raw=100.0, stop_dist=1.0,
                   initial_stop_adj=99.0, start_pos=0, exit_pos=0,
                   exit_t=entry_t + pd.Timedelta(hours=4), exit_price_adj=101.0,
                   exit_price_raw=101.0, exit_reason="initial_stop",
                   trail_started=False, n_rolls=0)


class TestWeeklyBars:
    def test_groups_business_days_into_iso_weeks_in_order(self):
        # 2024-01-01 is a Monday: 10 business days = exactly 2 full weeks
        daily = _daily_adj(10)
        weekly = W.weekly_bars(daily)
        assert len(weekly) == 2
        assert weekly["week_start"].iloc[0] == daily["date"].iloc[0]
        assert weekly["week_end"].iloc[0] == daily["date"].iloc[4]
        assert weekly["week_end"].iloc[1] == daily["date"].iloc[9]

    def test_ohlc_is_first_open_max_high_min_low_last_close(self):
        daily = _daily_adj(5)   # exactly one week
        weekly = W.weekly_bars(daily)
        assert weekly["open_adj"].iloc[0] == pytest.approx(daily["open_adj"].iloc[0])
        assert weekly["close_adj"].iloc[0] == pytest.approx(daily["close_adj"].iloc[-1])
        assert weekly["high_adj"].iloc[0] == pytest.approx(daily["high_adj"].max())
        assert weekly["low_adj"].iloc[0] == pytest.approx(daily["low_adj"].min())


class TestWeeklyDirection:
    def test_none_before_warmup_then_long_on_a_steady_uptrend(self):
        daily = _daily_adj(40)   # 8 weeks, rising close
        weekly = W.weekly_bars(daily)
        direction = W.weekly_direction(weekly, ema_fast=2, ema_slow=3, warmup_bars=3)
        assert list(direction.iloc[:3]) == ["none", "none", "none"]
        assert direction.iloc[-1] == "long"

    def test_short_on_a_steady_downtrend(self):
        daily = _daily_adj(40, step=-1.0)
        weekly = W.weekly_bars(daily)
        direction = W.weekly_direction(weekly, ema_fast=2, ema_slow=3, warmup_bars=3)
        assert direction.iloc[-1] == "short"


class TestTradeAlignment:
    def test_first_trade_before_any_completed_week_is_none(self):
        daily = _daily_adj(40)
        # entry on the very first session -- no completed week exists yet
        entry = pd.Timestamp(str(daily["date"].iloc[0]) + "T12:00:00", tz="UTC")
        t = _trade(entry, direction="long")
        df = W.trade_alignment([t], daily, ema_fast=2, ema_slow=3, warmup_bars=3)
        assert df.iloc[0]["alignment"] == "none"

    def test_with_and_against_are_read_from_the_last_completed_week_only(self):
        daily = _daily_adj(40)   # steady uptrend -> weekly direction settles "long"
        # entry in week 8 (last session), well after warmup -- last COMPLETED
        # week is week 7, already "long" on this steady uptrend.
        entry_day = daily["date"].iloc[-1]
        entry = pd.Timestamp(str(entry_day) + "T12:00:00", tz="UTC")
        long_trade = _trade(entry, direction="long")
        short_trade = _trade(entry, direction="short")
        df = W.trade_alignment([long_trade, short_trade], daily, ema_fast=2,
                               ema_slow=3, warmup_bars=3)
        assert df.iloc[0]["weekly_direction"] == "long"
        assert df.iloc[0]["alignment"] == "with"
        assert df.iloc[1]["alignment"] == "against"

    def test_does_not_use_the_entry_weeks_own_still_forming_data(self):
        # a sharp reversal happens WITHIN the entry week itself; alignment
        # must still read the PRIOR (completed) week's direction, not the
        # forming one, however the entry week's own data looks so far.
        daily = _daily_adj(35)   # 7 steady-up weeks
        reversal_dates = pd.bdate_range(start="2024-02-26", periods=5).date
        reversal = pd.DataFrame({"date": reversal_dates,
                                 "open_adj": [200, 150, 100, 50, 1],
                                 "high_adj": [200, 150, 100, 50, 1],
                                 "low_adj": [200, 150, 100, 50, 1],
                                 "close_adj": [200, 150, 100, 50, 1]})
        daily_with_reversal = pd.concat([daily, reversal], ignore_index=True)
        entry = pd.Timestamp(str(reversal_dates[0]) + "T12:00:00", tz="UTC")
        t = _trade(entry, direction="long")
        df = W.trade_alignment([t], daily_with_reversal, ema_fast=2, ema_slow=3,
                               warmup_bars=3)
        # last COMPLETED week (week 7, still steady-up) says "long" -- the
        # crashing week-8 data must not have leaked in.
        assert df.iloc[0]["weekly_direction"] == "long"
        assert df.iloc[0]["alignment"] == "with"


class TestNetByAlignment:
    def test_sums_net_pnl_per_alignment_bucket(self):
        daily = _daily_adj(40)
        entry_day = daily["date"].iloc[-1]
        entry = pd.Timestamp(str(entry_day) + "T12:00:00", tz="UTC")
        with_trade = _trade(entry, direction="long")     # aligned "with" the uptrend
        against_trade = _trade(entry, direction="short")  # "against"
        df = W.trade_alignment([with_trade, against_trade], daily, ema_fast=2,
                               ema_slow=3, warmup_bars=3)
        out = W.net_by_alignment(df, "MCL", "mid")
        assert out["with"]["trades"] == 1
        assert out["against"]["trades"] == 1
        assert out["with"]["net"] == pytest.approx(with_trade.net_pnl("MCL", "mid"))
        assert out["against"]["net"] == pytest.approx(against_trade.net_pnl("MCL", "mid"))
        assert out["none"]["trades"] == 0
