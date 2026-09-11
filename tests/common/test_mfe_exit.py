#!/usr/bin/env python3
"""The measurement that decides whether the exit queue is worth running.

Two properties carry it:

1. **Every excursion is forward-only.** A ceiling that could see the entry bar's
   own high, or an MFE-after-exit that could see the exit bar's, would
   manufacture a gap that was never available and send the project down an exit
   queue it does not need.
2. **The ceiling is a BOUND.** It must use the same entries, the same size and
   the same commission as the real trade, moving only the exit price. A ceiling
   that changed anything else would be a different strategy, not an upper bound
   on this one.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import mfe_exit as M
from strategy.mcl import mcl as MCL
from tests.common.test_pit_strategy import frame, rec

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)
LIVE = dict(use_apex=False, require_macd_pos=True)


def bars(highs, start=(4, 0)):
    b = pd.Timestamp(datetime.combine(D, dtime(*start), tzinfo=ET))
    idx = pd.DatetimeIndex([(b + timedelta(minutes=i)).tz_convert("UTC")
                            for i in range(len(highs))])
    return pd.DataFrame({"symbol": "AAA", "open": highs, "high": highs,
                         "low": highs, "close": highs,
                         "volume": [1.0] * len(highs)}, index=idx)


def trade(entry_i, exit_i, entry_px, exit_px, qty=100, comm=1.0, net=0.0,
          reason="trailing_stop", held=1):
    b = pd.Timestamp(datetime.combine(D, dtime(4, 0), tzinfo=ET))
    at = lambda i: (b + timedelta(minutes=i)).tz_convert("UTC").isoformat()
    return SimpleNamespace(symbol="AAA", date=D.isoformat(),
                           entry_time=at(entry_i), exit_time=at(exit_i),
                           entry_price=entry_px, exit_price=exit_px, qty=qty,
                           commission=comm, net=net, bars_held=held,
                           reason=reason)


# --- 1. forward-only --------------------------------------------------------

def test_the_ceiling_cannot_see_the_entry_bars_own_high():
    """The entry fills at its own bar's close, so that bar's high has already
    happened. A ceiling that counted it would credit the exit with movement
    that was never available to sell into."""
    b = bars([10.0, 5.0, 6.0, 7.0])          # the high is ON the entry bar
    r = M.excursion(b, trade(0, 3, 10.0, 7.0))
    assert r["ceiling_px"] == 7.0, "ceiling reached back to the entry bar"
    assert r["total_mfe"] == pytest.approx(-3.0)


def test_mfe_after_exit_cannot_see_the_exit_bars_own_high():
    b = bars([5.0, 6.0, 20.0, 7.0])          # the spike is ON the exit bar
    r = M.excursion(b, trade(0, 2, 5.0, 6.0))
    assert r["after_px"] == 7.0
    assert r["left"] == pytest.approx(1.0)


def test_left_on_the_table_is_never_negative():
    """Price falling after the exit is a good exit, not negative opportunity.
    A signed value would net off against real gaps elsewhere in the mean."""
    b = bars([5.0, 9.0, 4.0, 3.0])
    assert M.excursion(b, trade(0, 1, 5.0, 9.0))["left"] == 0.0


def test_an_entry_on_the_last_bar_is_excluded_rather_than_scored_perfect():
    """There was no opportunity and no exit decision to judge. Scoring it would
    silently add a 0/0 capture ratio to the distribution."""
    assert M.excursion(bars([5.0, 6.0]), trade(1, 1, 6.0, 6.0)) is None


# --- 2. the ceiling is a bound ----------------------------------------------

def test_the_ceiling_keeps_the_real_trades_size_commission_and_friction():
    """Only the exit price may move. Anything else makes it a different
    strategy rather than an upper bound on this one."""
    rows = [{"ceiling_px": 12.0, "entry_px": 10.0, "qty": 100,
             "commission": 2.0}]
    assert M.ceiling_nets(rows, 4.26) == pytest.approx([200.0 - 2.0 - 4.26])


def test_the_ceiling_is_never_worse_than_the_real_exit():
    b = bars([5.0, 7.0, 9.0, 6.0])
    r = M.excursion(b, trade(0, 3, 5.0, 6.0, net=100.0 - 1.0))
    assert r["ceiling_px"] >= r["exit_px"]
    assert M.ceiling_nets([r], 0.0)[0] >= r["net"]


# --- 3. R is never reported without its parts -------------------------------

def test_r_stats_always_carries_win_rate_avg_win_avg_loss_and_r():
    s = M.r_stats([10.0, -20.0, 10.0, -20.0])
    assert s["win"] == 0.5 and s["avg_win"] == 10.0 and s["avg_loss"] == 20.0
    assert s["r"] == pytest.approx(0.5)


def test_the_required_r_is_the_break_even_ratio_for_this_win_rate():
    """Derived, not imported. The published 1.05 belongs to a 48.7% win rate on
    the stage-2 universe; this arm wins about 21% of the time."""
    assert M.r_stats([1.0] + [-1.0] * 3)["r_req"] == pytest.approx(3.0)
    assert M.r_stats([1.0] * 487 + [-1.0] * 513)["r_req"] == \
        pytest.approx(1.053, abs=0.01)


# --- 4. the verdict ---------------------------------------------------------

def rows_for(entry, exit_px, ceiling, after, n=200, net=None):
    return [{"symbol": f"S{i}", "date": f"2026-{1 + i % 9:02d}-01", "qty": 100,
             "entry_px": entry, "exit_px": exit_px, "ceiling_px": ceiling,
             "after_px": after, "bars_held": 5 + i % 3,
             "reason": "trailing_stop", "commission": 1.0,
             "net": (exit_px - entry) * 100 - 1.0 if net is None else net,
             "captured": exit_px - entry, "total_mfe": ceiling - entry,
             "left": max(0.0, after - exit_px)} for i in range(n)]


def out(rows):
    return "\n".join(M.render("mcl", rows, "2026-05-01", 546, 1.0))


def mixed(specs, n=200):
    """Rows with an explicit (actual net, ceiling net) per trade.

    Both arms need real winners AND real losers or R has a zero on one side and
    does not exist -- which the report now refuses, and which the first version
    of these fixtures quietly relied on.
    """
    out_rows = []
    for i in range(n):
        net, ceil_net = specs[i % len(specs)]
        # ceiling_net = (ceiling_px - entry) * qty - commission - 4.26
        ceiling_px = 10.0 + (ceil_net + 1.0 + 4.26) / 100.0
        out_rows.append({
            "symbol": f"S{i}", "date": f"2026-{1 + i % 9:02d}-01", "qty": 100,
            "entry_px": 10.0, "exit_px": 10.0 + net / 100.0,
            "ceiling_px": ceiling_px, "after_px": ceiling_px,
            "bars_held": 5 + i % 3, "reason": "trailing_stop",
            "commission": 1.0, "net": net,
            "captured": net / 100.0, "total_mfe": ceiling_px - 10.0,
            "left": max(0.0, ceiling_px - (10.0 + net / 100.0))})
    return out_rows


def test_a_ceiling_that_misses_the_bar_drops_the_exit_queue():
    """25% winners needs R = 3.0 to break even. At the ceiling R is 2.0 -- so
    even perfect foresight cannot reach it, and no rule beats perfect
    foresight."""
    o = out(mixed([(5.0, 10.0), (-20.0, -5.0), (-20.0, -5.0), (-20.0, -5.0)]))
    assert "THE EXIT IS NOT THE PROBLEM" in o
    assert "ENTRY problem" in o
    assert "dropped rather than run" in o


def test_a_ceiling_that_clears_the_bar_and_makes_money_says_attack_the_exit():
    """60% winners needs R = 0.67; at the ceiling R is 4.0 and it earns +$10 a
    trade, so the favourable movement is really there."""
    o = out(mixed([(5.0, 20.0), (5.0, 20.0), (5.0, 20.0), (-20.0, -5.0),
                   (-20.0, -5.0)]))
    assert "THE EXIT IS WORTH ATTACKING" in o
    assert "perfect exit is not available" in o


def test_a_thin_sample_refuses_a_verdict():
    o = out(rows_for(10.0, 10.5, 11.0, 10.8, n=5))
    assert "NO VERDICT" in o


def test_every_figure_is_reported_at_all_three_friction_levels():
    o = out(rows_for(10.0, 10.05, 12.0, 11.0))
    for label, _ in M.FRICTIONS:
        assert label in o


def test_the_report_states_it_has_no_parameters():
    o = out(rows_for(10.0, 10.05, 12.0, 11.0))
    assert "NO PARAMETERS" in o


def test_hold_time_is_split_by_outcome():
    o = out(rows_for(10.0, 10.05, 12.0, 11.0))
    assert "HOLD TIME BY OUTCOME" in o
    assert "winners" in o and "losers" in o


def test_what_is_left_is_broken_out_by_exit_reason():
    o = out(rows_for(10.0, 10.05, 12.0, 11.0))
    assert "BY EXIT REASON" in o and "trailing_stop" in o


def test_the_report_says_the_ceiling_is_a_bound_not_a_strategy():
    o = out(rows_for(10.0, 10.05, 12.0, 11.0))
    assert "perfect foresight" in o and "BOUND, not a rule" in o
    assert "has NOT been spent" in o


# --- 5. the session bound ---------------------------------------------------

def test_session_bars_are_bounded_by_the_engines_own_window():
    """An excursion measured over the warm-up day would count a previous
    session's movement as opportunity this exit missed."""
    df = frame()
    got = M.session_bars(df, D.isoformat(), MCL)
    local = got.index.tz_convert(ET)
    assert set(local.date) == {D}
    assert local.time.min() >= MCL.SESSION_START
    assert local.time.max() < MCL.SESSION_END


def test_run_day_floors_every_entry_and_skips_names_with_no_first_seen():
    df = frame()
    assert M.run_day(df, D.isoformat(),
                     [{"symbol": "AAA", "date": D.isoformat(),
                       "first_seen": None}], mod=MCL, extra=LIVE) == []
    got = M.run_day(df, D.isoformat(), [rec(h=6, m=0)], mod=MCL, extra=LIVE)
    assert got
    for r in got:
        assert r["total_mfe"] == r["ceiling_px"] - r["entry_px"]


def test_an_arm_with_no_losers_refuses_the_r_verdict():
    """R with a zero on one side reads 0.00 against a requirement that also
    reads 0.00, and the comparison resolves to 'worth attacking' on an arm
    where R does not exist."""
    o = out(rows_for(10.0, 10.50, 12.0, 11.0, n=200))   # every trade a winner
    assert "R does not exist" in o
    assert "THE EXIT IS WORTH ATTACKING" not in o
    assert "Read the per-trade column instead" in o


def test_an_arm_with_no_winners_also_refuses():
    r = rows_for(10.0, 9.90, 12.0, 11.0, n=200)
    o = out(r)
    assert "R does not exist" in o


def test_a_healthy_mix_still_gets_a_verdict():
    o = out(mixed([(5.0, 20.0), (-20.0, -5.0)]))
    assert "R does not exist" not in o
    assert ("THE EXIT IS WORTH ATTACKING" in o
            or "THE EXIT IS NOT THE PROBLEM" in o)
