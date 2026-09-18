#!/usr/bin/env python3
"""H-C2's profit floor, on hand-built bars, for both engines.

docs/research/REGISTERED_profit_floor.md §1: once a bar AFTER the entry bar
reaches entry + 15 ticks, the stop is max(5% trail, entry + 10 ticks) from the
NEXT bar on; same gap-through and tick as the trail; labelled by the level
that did the work; None is bit-identical.

Every case below is written so that the WRONG implementation produces a
different trade, not merely the same trade for a different reason -- a floor
that never arms, arms on the entry bar, or acts on its own arming bar each
fails at least one assertion here on the exit price or the exit bar.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
DAY = date(2026, 9, 11)
PF = (15, 10)

F = (5.00, 5.00, 5.00, 5.00)          # signal close 5.00 -> entry 5.01; floor 5.11; arm 5.16


def mcl_run(bars, **kw):
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000
    take = pd.Series(False, index=idx)
    take.iloc[0] = True
    return MCL.backtest_session(df, DAY, ET, entry_bars=take, entry_shares=100,
                                use_apex=False, **kw)


def mc5_run(bars, monkeypatch, **kw):
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=5 * i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000

    def fake_signals(df5, **kwargs):
        # **kwargs mirrors the real signals(): a fake whose signature has
        # drifted from the function it replaces stops testing that function.
        out = df5.copy()
        out["entry"] = False
        out.iloc[0, out.columns.get_loc("entry")] = True
        out["exit_sig"] = False
        return out

    monkeypatch.setattr(MC5, "signals", fake_signals)
    return MC5.backtest_session(df, DAY, ET, entry_shares=100, use_apex=False, **kw)


@pytest.fixture(params=["mcl", "mc5"])
def run(request, monkeypatch):
    if request.param == "mcl":
        return lambda bars, **kw: mcl_run(bars, **kw)
    return lambda bars, **kw: mc5_run(bars, monkeypatch, **kw)


def only(trades):
    assert len(trades) == 1, trades
    return trades[0]


def bar_no(t):
    """Index of the exit bar, independent of 1- or 5-minute spacing."""
    return t.bars_held


# --- the rule ------------------------------------------------------------------

def test_none_is_bit_identical(run):
    bars = [F, (5.02, 5.20, 5.12, 5.15), (5.14, 5.15, 5.05, 5.06), (5.06, 5.07, 4.70, 4.80), F]
    a = [t.__dict__ for t in run(bars)]
    b = [t.__dict__ for t in run(bars, profit_floor=None)]
    assert a == b and a


def test_arms_on_the_next_bar_and_exits_at_the_floor(run):
    # bar1 high 5.16 arms (low 5.12 is above the floor anyway); bar2 low 5.05
    # crosses the floor 5.11 with the trail at 5.16 * 0.95 = 4.902.
    bars = [F, (5.02, 5.16, 5.12, 5.15), (5.14, 5.15, 5.05, 5.06), F]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "profit_floor"
    assert t.exit_price == pytest.approx(5.10)          # 5.11 - one tick
    assert bar_no(t) == 2


def test_without_the_floor_the_same_bars_ride_to_the_close(run):
    bars = [F, (5.02, 5.16, 5.12, 5.15), (5.14, 5.15, 5.05, 5.06), F]
    t = only(run(bars))
    assert t.reason == "window_close"


def test_the_entry_bars_own_high_cannot_arm(run):
    # The entry bar trades to 5.30 BEFORE the 5.00 close we bought at. If it
    # armed, bar1's low 5.08 would exit on the floor.
    bars = [(5.00, 5.30, 5.00, 5.00), (5.02, 5.10, 5.08, 5.09), (5.09, 5.10, 5.08, 5.09)]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "window_close"


def test_the_floor_does_not_act_on_its_own_arming_bar(run):
    # bar1 reaches 5.16 AND trades down to 5.05 inside the same bar. The order
    # of high and low inside a bar is unknown, so the floor may not use it.
    bars = [F, (5.02, 5.16, 5.05, 5.10), (5.12, 5.14, 5.12, 5.13), (5.13, 5.14, 5.12, 5.13)]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "window_close"
    assert bar_no(t) == 3


def test_a_gap_below_the_floor_fills_at_the_open(run):
    bars = [F, (5.10, 5.16, 5.12, 5.15), (5.08, 5.09, 5.00, 5.02), F]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "profit_floor"
    assert t.exit_price == pytest.approx(5.07)          # open 5.08 - one tick


def test_a_gap_below_entry_is_still_possible_and_is_booked_as_one(run):
    bars = [F, (5.10, 5.16, 5.12, 5.15), (4.95, 4.98, 4.90, 4.92), F]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "profit_floor"
    assert t.exit_price == pytest.approx(4.94)
    assert t.exit_price < t.entry_price


def test_the_trail_wins_once_it_is_the_higher_level(run):
    # peak 5.60 -> trail 5.32 > floor 5.11
    bars = [F, (5.10, 5.60, 5.40, 5.55), (5.50, 5.52, 5.30, 5.31), F]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "trailing_stop"
    assert t.exit_price == pytest.approx(5.32 - 0.01)


def test_a_trade_that_never_reaches_fifteen_ticks_is_untouched(run):
    # best high 5.15 is 14 ticks; the trail then takes it out at 4.7595.
    bars = [F, (5.00, 5.15, 5.12, 5.14), (5.10, 5.12, 4.70, 4.80), F]
    a = [t.__dict__ for t in run(bars)]
    b = [t.__dict__ for t in run(bars, profit_floor=PF)]
    assert a == b and a[0]["reason"] == "trailing_stop"


def test_exactly_fifteen_ticks_arms_despite_binary_residue(run):
    # 2.69 + 0.15 is 2.8400000000000003; a high of exactly 2.84 must arm.
    base = (2.68, 2.68, 2.68, 2.68)                     # entry 2.69, floor 2.79
    bars = [base, (2.70, 2.84, 2.80, 2.83), (2.82, 2.83, 2.75, 2.76), base]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "profit_floor"
    assert t.exit_price == pytest.approx(2.78)


def test_the_floor_sits_on_the_fill_not_the_signal_close(run):
    # Signal close 5.00, fill 5.01. A floor built on the close would be 5.10
    # and a low of 5.105 would not touch it; the fill-based floor 5.11 does.
    bars = [F, (5.02, 5.16, 5.12, 5.15), (5.14, 5.15, 5.105, 5.12), F]
    t = only(run(bars, profit_floor=PF))
    assert t.reason == "profit_floor" and bar_no(t) == 2


def test_after_a_floor_exit_the_name_can_trade_again(monkeypatch):
    # MCL, entry signals on bars 0 and 3: the floor exit on bar 2 frees the
    # engine, so bar 3's signal is a new entry.
    t0 = datetime.combine(DAY, dtime(7, 0), tzinfo=ET)
    bars = [F, (5.02, 5.16, 5.12, 5.15), (5.14, 5.15, 5.05, 5.06), F, F]
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(len(bars))])
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 10_000
    take = pd.Series(False, index=idx)
    take.iloc[0] = take.iloc[3] = True
    trades = MCL.backtest_session(df, DAY, ET, entry_bars=take, entry_shares=100,
                                  use_apex=False, profit_floor=PF)
    assert [t.reason for t in trades] == ["profit_floor", "window_close"]


# --- the parameter ------------------------------------------------------------

@pytest.mark.parametrize("bad", [(10, 15), (10, 10), (15.0, 10), (15, -1), (True, 0),
                                 (15,), "15,10", 15])
def test_bad_parameters_are_refused(run, bad):
    with pytest.raises(ValueError):
        run([F, F], profit_floor=bad)


def test_a_breakeven_floor_is_expressible(run):
    bars = [F, (5.02, 5.16, 5.12, 5.15), (5.14, 5.15, 5.00, 5.02), F]
    t = only(run(bars, profit_floor=(15, 0)))
    assert t.reason == "profit_floor" and t.exit_price == pytest.approx(5.00)


def test_both_engines_share_one_tick_size():
    assert MC5.TICK == MCL.TICK
