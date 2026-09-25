"""Tests for strategy/htf/book.py -- aggregation and sec.4 scoring. W15-0004
step 7 checkpoint 6."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategy.htf import book as BK
from strategy.htf import runner as R


def _trade(session, direction, entry_t, exit_t, fill_raw, exit_raw, reason="initial_stop",
          trail=False, n_rolls=0):
    return R.Trade(session=session, direction=direction, entry_t=pd.Timestamp(entry_t, tz="UTC"),
                   fill_adj=fill_raw, fill_raw=fill_raw, stop_dist=1.0, initial_stop_adj=fill_raw - 1.0,
                   start_pos=0, exit_pos=0, exit_t=pd.Timestamp(exit_t, tz="UTC"),
                   exit_price_adj=exit_raw, exit_price_raw=exit_raw, exit_reason=reason,
                   trail_started=trail, n_rolls=n_rolls)


class TestNetTable:
    def test_columns_and_year_from_session(self):
        trades = [_trade("2015-03-01", "long", "2015-03-01T10:00", "2015-03-01T14:00", 100.0, 101.0)]
        df = BK.net_table(trades, "MCL", "mid")
        assert df.loc[0, "year"] == 2015
        assert df.loc[0, "gross"] == pytest.approx(100.0)   # (101-100)*100
        assert df.loc[0, "hold_hours"] == pytest.approx(4.0)


class TestSummarize:
    def test_empty_book(self):
        s = BK.summarize(BK.net_table([], "MCL", "mid"))
        assert s.trades == 0 and s.net == 0.0 and s.worst_loss_streak == 0

    def test_wins_losses_and_worst_streak(self):
        trades = [
            _trade("d1", "long", "2015-01-01", "2015-01-01T04:00", 100.0, 101.0),   # win
            _trade("d1", "long", "2015-01-02", "2015-01-02T04:00", 100.0, 99.0),    # loss
            _trade("d1", "long", "2015-01-03", "2015-01-03T04:00", 100.0, 98.0),    # loss
            _trade("d1", "long", "2015-01-04", "2015-01-04T04:00", 100.0, 102.0),   # win
        ]
        df = BK.net_table(trades, "MCL", "low")
        s = BK.summarize(df)
        assert s.trades == 4
        assert s.wins == 2 and s.losses == 2
        assert s.worst_loss_streak == 2
        assert s.largest_loss == pytest.approx(df["net"].min())

    def test_a_break_in_losses_resets_the_streak(self):
        net = np.array([-1.0, -1.0, 1.0, -1.0])
        assert BK.worst_loss_streak(net) == 2


class TestYearTable:
    def test_fills_years_with_no_trades_as_zero(self):
        trades = [
            _trade("d1", "long", "2015-01-01", "2015-01-01T04:00", 100.0, 101.0),
            _trade("d1", "long", "2017-06-01", "2017-06-01T04:00", 100.0, 101.0),
        ]
        df = BK.net_table(trades, "MCL", "low")
        yt = BK.year_table(df)
        assert set(yt.keys()) == {2015, 2016, 2017}
        assert yt[2016] == 0.0
        assert yt[2015] > 0 and yt[2017] > 0

    def test_empty_book_gives_empty_table(self):
        assert BK.year_table(BK.net_table([], "MCL", "low")) == {}


class TestSplitHalves:
    def test_splits_at_the_median_trade_date(self):
        trades = [
            _trade("d1", "long", "2015-01-01", "2015-01-01T04:00", 100.0, 101.0),  # win, before median
            _trade("d1", "long", "2015-02-01", "2015-02-01T04:00", 100.0, 101.0),  # win, at/after median
            _trade("d1", "long", "2015-03-01", "2015-03-01T04:00", 100.0, 99.0),   # loss, at/after median
        ]
        df = BK.net_table(trades, "MCL", "low")
        first, second = BK.split_halves(df)
        # median entry_t is trade 2 (2015-02-01): first half = strictly before it (trade 1's win),
        # second half = trade 2 + trade 3 (win + loss)
        assert first == pytest.approx(df["net"].iloc[0])
        assert second == pytest.approx(df["net"].iloc[1] + df["net"].iloc[2])


class TestTopYearShare:
    def test_identifies_the_dominant_year(self):
        yt = {2014: 100.0, 2015: 900.0, 2016: 0.0}
        year, share = BK.top_year_share(yt)
        assert year == 2015
        assert share == pytest.approx(0.9)

    def test_empty_returns_none(self):
        assert BK.top_year_share({}) == (None, 0.0)


class TestBootstrapByYear:
    def test_all_positive_years_bootstraps_near_100_percent(self):
        yt = {y: 100.0 for y in range(2010, 2020)}
        share = BK.bootstrap_by_year(yt, n=500, seed=1)
        assert share > 0.99

    def test_all_negative_years_bootstraps_near_zero(self):
        yt = {y: -100.0 for y in range(2010, 2020)}
        share = BK.bootstrap_by_year(yt, n=500, seed=1)
        assert share < 0.01

    def test_fewer_than_two_years_returns_nan(self):
        assert np.isnan(BK.bootstrap_by_year({2015: 100.0}))
        assert np.isnan(BK.bootstrap_by_year({}))

    def test_deterministic_for_a_fixed_seed(self):
        yt = {2010: 50.0, 2011: -30.0, 2012: 20.0}
        assert BK.bootstrap_by_year(yt, n=200, seed=3) == BK.bootstrap_by_year(yt, n=200, seed=3)


class TestSampleTrades:
    def test_takes_every_nth_trade_in_order(self):
        trades = [_trade("d1", "long", f"2015-01-{i+1:02d}", f"2015-01-{i+1:02d}T04:00", 100.0, 101.0)
                 for i in range(5)]
        out = BK.sample_trades(trades, "MCL", "low", every=2)
        assert len(out) == 3   # indices 0, 2, 4
        assert out[0]["entry_t"] == str(trades[0].entry_t)
        assert out[1]["entry_t"] == str(trades[2].entry_t)


class TestScore:
    def _mid_book(self, net_per_trade, years):
        trades = []
        for i, (net, yr) in enumerate(zip(net_per_trade, years)):
            fill = 100.0
            exit_px = fill + net / 100.0   # MCL multiplier 100, ignoring cost for simplicity of the fixture
            trades.append(_trade(f"d{i}", "long", f"{yr}-01-01T00:00", f"{yr}-01-01T04:00", fill, exit_px))
        return BK.net_table(trades, "MCL", "low")

    def test_all_nine_criteria_present_and_dependency_gaps_are_none_not_false(self):
        df_mid = self._mid_book([500.0] * 200, [2015] * 200)
        df_high = df_mid.copy()
        year_net = BK.year_table(df_mid)
        crit = BK.score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net,
                        net_c1=None, net_c2=None, c3_p95=None)
        assert len(crit) == 9
        by_n = {c.n: c for c in crit}
        assert by_n[5].passed is None and by_n[5].detail == "NOT SUPPLIED"
        assert by_n[6].passed is None
        assert by_n[8].passed is None and by_n[8].detail == "NOT YET BUILT"

    def test_criterion_1_and_9_fail_on_a_losing_thin_book(self):
        df_mid = self._mid_book([-10.0] * 5, [2015] * 5)
        df_high = df_mid.copy()
        year_net = BK.year_table(df_mid)
        crit = BK.score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net,
                        net_c1=None, net_c2=None, c3_p95=None)
        by_n = {c.n: c for c in crit}
        assert by_n[1].passed is False
        assert by_n[9].passed is False

    def test_criterion_5_and_6_evaluate_when_supplied(self):
        df_mid = self._mid_book([500.0] * 200, [2015] * 200)
        df_high = df_mid.copy()
        year_net = BK.year_table(df_mid)
        crit = BK.score(df_mid=df_mid, df_high=df_high, year_net_mid=year_net,
                        net_c1=1_000_000.0, net_c2=1_000_000.0, c3_p95=1_000_000.0)
        by_n = {c.n: c for c in crit}
        assert by_n[5].passed is False    # v0's net doesn't beat the inflated C1/C2 figures
        assert by_n[6].passed is False
