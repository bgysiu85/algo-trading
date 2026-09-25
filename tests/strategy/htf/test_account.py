"""Tests for strategy/htf/account.py -- equity curve, drawdown, ruin, max
size, overnight margin. W15-0004 step 7 checkpoint 8. Exercised against
small hand-built Trade lists (mirrors test_runner.py/test_book.py's own
approach); a real account_view() call over the full archive happens in
report.py, checkpoint 11."""
from __future__ import annotations

import datetime

import pandas as pd
import pytest

from strategy.htf import account as A
from strategy.htf import costs as C
from strategy.htf import runner as R


def _trade(entry_t, exit_t, *, entry_px=100.0, exit_px=101.0, direction="long",
          session="d1"):
    return R.Trade(session=session, direction=direction, entry_t=entry_t,
                   fill_adj=entry_px, fill_raw=entry_px, stop_dist=1.0,
                   initial_stop_adj=entry_px - 1.0, start_pos=0, exit_pos=0,
                   exit_t=exit_t, exit_price_adj=exit_px, exit_price_raw=exit_px,
                   exit_reason="initial_stop", trail_started=False, n_rolls=0)


def _ts(s):
    return pd.Timestamp(s, tz="UTC")


class TestEquityCurve:
    def test_compounds_net_pnl_in_exit_time_order_not_list_order(self):
        later = _trade(_ts("2020-01-05"), _ts("2020-01-06"), exit_px=105.0)
        earlier = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=102.0)
        pts = A.equity_curve([later, earlier], "MCL", "mid", stop_at_ruin=False)
        assert [t for t, _ in pts] == [earlier.exit_t, later.exit_t]
        net1 = earlier.net_pnl("MCL", "mid")
        net2 = later.net_pnl("MCL", "mid")
        assert pts[0][1] == pytest.approx(A.ACCOUNT_START + net1)
        assert pts[1][1] == pytest.approx(A.ACCOUNT_START + net1 + net2)

    def test_qty_scales_net_pnl_linearly(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=90.0)
        pts1 = A.equity_curve([t], "MCL", "mid", qty=1, stop_at_ruin=False)
        pts3 = A.equity_curve([t], "MCL", "mid", qty=3, stop_at_ruin=False)
        net1 = pts1[0][1] - A.ACCOUNT_START
        net3 = pts3[0][1] - A.ACCOUNT_START
        assert net3 == pytest.approx(net1 * 3)


class TestWorstDrawdown:
    def test_measures_from_start_as_the_first_peak(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=95.0)
        pts = A.equity_curve([t], "MCL", "mid", stop_at_ruin=False)
        loss = A.ACCOUNT_START - pts[0][1]
        assert loss > 0
        assert A.worst_drawdown_dollars(pts) == pytest.approx(loss)

    def test_a_later_recovery_does_not_shrink_the_drawdown(self):
        loser = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=90.0)
        winner = _trade(_ts("2020-01-03"), _ts("2020-01-04"), exit_px=120.0)
        pts = A.equity_curve([loser, winner], "MCL", "mid", stop_at_ruin=False)
        loss = A.ACCOUNT_START - pts[0][1]
        assert A.worst_drawdown_dollars(pts) == pytest.approx(loss)


class TestRuin:
    def test_a_breach_stops_the_curve_and_is_reported(self):
        catastrophe = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=0.0)
        afterwards = _trade(_ts("2020-01-03"), _ts("2020-01-04"), exit_px=150.0)
        pts = A.equity_curve([catastrophe, afterwards], "MCL", "mid", stop_at_ruin=True)
        assert len(pts) == 1                         # afterwards never happened
        assert pts[0][1] <= A.RUIN_LEVEL
        assert A.ruin_date(pts) == catastrophe.exit_t

    def test_no_breach_returns_none(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=101.0)
        pts = A.equity_curve([t], "MCL", "mid", stop_at_ruin=True)
        assert A.ruin_date(pts) is None


class TestMaxSize:
    def test_finds_the_largest_n_strictly_under_the_dd_limit(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=95.0)
        per_unit_dd = A.worst_drawdown_dollars(
            A.equity_curve([t], "MCL", "mid", qty=1, stop_at_ruin=False))
        assert per_unit_dd > 0
        limit = per_unit_dd * 6.5   # 6 contracts fit (6x < 6.5x), 7 do not
        assert A.max_size([t], "MCL", "mid", dd_limit=limit) == 6

    def test_zero_when_even_one_contract_breaches(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=50.0)
        per_unit_dd = A.worst_drawdown_dollars(
            A.equity_curve([t], "MCL", "mid", qty=1, stop_at_ruin=False))
        assert A.max_size([t], "MCL", "mid", dd_limit=per_unit_dd * 0.5) == 0

    def test_empty_trade_list_is_zero(self):
        assert A.max_size([], "MCL", "mid") == 0


class TestNightsHeld:
    def test_a_same_session_trade_is_zero_nights(self):
        t = _trade(_ts("2024-01-04T12:00:00"), _ts("2024-01-04T16:00:00"))
        calendar = [datetime.date(2024, 1, 4)]
        assert A.nights_held(t, calendar) == 0

    def test_a_thursday_to_monday_hold_is_two_nights_not_four_calendar_nights(self):
        # 2024-01-04 = Thursday, 2024-01-08 = Monday; Fri-close -> Sun-evening
        # is a single margin-relevant gap, not three separate calendar nights.
        t = _trade(_ts("2024-01-04T12:00:00"), _ts("2024-01-08T12:00:00"))
        calendar = [datetime.date(2024, 1, 2), datetime.date(2024, 1, 3),
                   datetime.date(2024, 1, 4), datetime.date(2024, 1, 5),
                   datetime.date(2024, 1, 8), datetime.date(2024, 1, 9)]
        assert A.nights_held(t, calendar) == 2


class TestOvernightMarginBreaches:
    def test_only_held_nights_are_checked_and_only_when_margin_exceeds_equity(self):
        calendar = [datetime.date(2024, 1, 2), datetime.date(2024, 1, 3),
                   datetime.date(2024, 1, 4), datetime.date(2024, 1, 5),
                   datetime.date(2024, 1, 8), datetime.date(2024, 1, 9)]
        # same-session trade, catastrophic loss -> equity well below the
        # $884.53 MCL initial margin, but 0 nights held so it never counts.
        same_session = _trade(_ts("2024-01-02T12:00:00"), _ts("2024-01-02T16:00:00"),
                              exit_px=0.0)
        # held Thursday -> Monday (2 nights) entered AFTER the wipeout above,
        # so equity is now deeply negative -> both held nights breach.
        held = _trade(_ts("2024-01-04T12:00:00"), _ts("2024-01-08T12:00:00"),
                      exit_px=101.0)
        n = A.overnight_margin_breaches([same_session, held], calendar,
                                        symbol="MCL", level="mid", qty=1)
        assert n == 2

    def test_ample_equity_never_breaches(self):
        calendar = [datetime.date(2024, 1, 4), datetime.date(2024, 1, 5),
                   datetime.date(2024, 1, 8)]
        held = _trade(_ts("2024-01-04T12:00:00"), _ts("2024-01-08T12:00:00"),
                      exit_px=100.5)   # small, equity stays near $10,000
        n = A.overnight_margin_breaches([held], calendar, symbol="MCL",
                                        level="mid", qty=1)
        assert n == 0


class TestAccountView:
    def test_mcl_steps_n_from_one_to_max_size_plus_one(self):
        # a big enough single-contract loss (~$5,004) that the breach point
        # (n=2, ~$10,008) falls well inside N_CAP, not up against it.
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=50.0)
        view = A.account_view([t], "MCL", "mid")
        m = view["max_size"]
        assert m == 1
        assert [r["n"] for r in view["rows"]] == list(range(1, m + 2))
        # the last row (max_size+1) is the one that breaches the dd test
        assert view["rows"][-1]["worst_drawdown"] >= A.DD_LIMIT

    def test_cl_reports_a_single_row_and_no_max_size(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=101.0)
        view = A.account_view([t], "CL", "mid")
        assert view["max_size"] is None
        assert len(view["rows"]) == 1
        assert view["rows"][0]["n"] == 1

    def test_session_calendar_adds_the_margin_count_only_when_given(self):
        t = _trade(_ts("2020-01-01"), _ts("2020-01-02"), exit_px=101.0)
        without = A.account_view([t], "MCL", "mid")
        assert "overnight_margin_breaches" not in without["rows"][0]
        with_cal = A.account_view([t], "MCL", "mid",
                                  session_calendar=[datetime.date(2020, 1, 1),
                                                    datetime.date(2020, 1, 2)])
        assert "overnight_margin_breaches" in with_cal["rows"][0]
