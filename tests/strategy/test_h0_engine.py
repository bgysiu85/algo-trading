#!/usr/bin/env python3
"""H0 wearing the backtest_session interface.

One property matters: the adapter must produce the trades `pit_h0` produces.
An adapter that quietly altered the control would invalidate every comparison
drawn through it -- and the comparisons drawn through it are the ones deciding
whether MCL's rules are worth anything.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import pit_h0 as P0
from common import pit_strategy as PS
from strategy.premkt import h0_engine as E
from strategy.premkt import hypotheses as H

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)


def frame(sym="AAA", n=330, px=4.0, step=0.01):
    b = pd.Timestamp(datetime.combine(D, dtime(4, 0), tzinfo=ET))
    idx = pd.DatetimeIndex([(b + timedelta(minutes=i)).tz_convert("UTC")
                            for i in range(n)])
    close = [px + step * i for i in range(n)]
    return pd.DataFrame({"symbol": sym, "open": close,
                         "high": [c + 0.02 for c in close],
                         "low": [c - 0.02 for c in close],
                         "close": close, "volume": [10_000.0] * n}, index=idx)


def rec(sym="AAA", h=4, m=30):
    fs = pd.Timestamp(datetime.combine(D, dtime(h, m), tzinfo=ET)
                      ).tz_convert("UTC").isoformat()
    return {"symbol": sym, "date": D.isoformat(), "first_seen": fs,
            "first_rank": 1, "best_rank": 1, "ticks_on": 10}


@pytest.mark.parametrize("h,m", [(4, 30), (6, 10), (8, 0)])
def test_the_adapter_reproduces_pit_h0_trade_for_trade(h, m):
    """THE headline. pit_h0's AS SCREENED arm floors at first_seen; this is the
    same rule reached through the strategy interface, and the two must agree
    field for field or the control has silently changed."""
    df = frame()
    theirs = P0.run_day(df, D.isoformat(), [rec(h=h, m=m)],
                        as_screened=True, trail=H.TRAIL_PRIMARY)
    mine = E.backtest_session(df, D, ET, entry_shares=H.ENTRY_SHARES,
                              not_before=dtime(h, m))
    assert len(theirs) == len(mine)
    for a, b in zip(theirs, mine):
        for f in ("entry_time", "exit_time", "entry_price", "exit_price",
                  "qty", "reason", "bars_held", "gross", "commission", "net"):
            assert a[f] == getattr(b, f), f


def test_no_floor_is_the_registered_rule_entering_at_0430():
    df = frame()
    t = E.backtest_session(df, D, ET, entry_shares=100)
    assert len(t) == 1
    assert pd.Timestamp(t[0].entry_time).tz_convert(ET).time() == H.ENTRY_FROM


def test_the_floor_can_only_move_the_entry_later():
    df = frame()
    for h, m in ((4, 0), (4, 15)):
        t = E.backtest_session(df, D, ET, entry_shares=100,
                               not_before=dtime(h, m))
        assert pd.Timestamp(t[0].entry_time).tz_convert(ET).time() \
            >= H.ENTRY_FROM


def test_one_entry_per_symbol_session_is_preserved():
    """The registration says one. A adapter that lost max_entries_per_session
    would quietly turn the control into a different and busier rule."""
    assert len(E.backtest_session(frame(n=330), D, ET, entry_shares=100)) == 1


def test_an_exit_knob_that_means_nothing_to_h0_raises():
    """MCL and MC5 take a long tail of exit knobs. Accepting `ladder=` here and
    ignoring it would hand back the unmodified control while the caller
    believed a mechanic had been applied."""
    with pytest.raises(TypeError):
        E.backtest_session(frame(), D, ET, entry_shares=100, ladder=object())


def test_pit_strategy_accepts_h0_as_an_engine():
    mod, extra = PS.engine("h0")
    assert mod is E and extra == {}


def test_pit_strategy_runs_h0_through_run_day():
    df = frame()
    rows, free, bit, seen = PS.run_day(df, D.isoformat(), [rec(h=8, m=0)],
                                       mod=E, extra={}, floor=True)
    assert seen == 1
    assert bit == 1, "unfloored H0 enters at 04:30, so an 08:00 floor must bite"
    assert rows and pd.Timestamp(
        rows[0]["entry_time"]).tz_convert(ET).time() >= dtime(8, 0)
    assert pd.Timestamp(
        free[0]["entry_time"]).tz_convert(ET).time() == H.ENTRY_FROM


def test_the_h0_report_omits_the_control_comparison():
    """H0 against H0 is +0.00 by construction. Printed in the same table as a
    real comparison, a tautology is something a reader quotes as a result."""
    t = [{"date": "2026-03-02", "symbol": f"S{i}", "net": -10.0,
          "first_seen": None} for i in range(200)]
    out = "\n".join(PS.render(
        "h0", {"stage2": t, "pit": t, "early": t, "pit_unfloored": t},
        {"pit": 50, "early": None},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        "2026-03-02", 500, 0, 1.0, traded_early=60))
    assert "NO CONTROL COMPARISON" in out
    assert "vs H0" not in out


def test_a_short_report_still_carries_the_caveats():
    """The H0 path returns early. The caveats are exactly the part that must
    not be dropped from a short report."""
    t = [{"date": "2026-03-02", "symbol": f"S{i}", "net": -10.0,
          "first_seen": None} for i in range(200)]
    out = "\n".join(PS.render(
        "h0", {"stage2": t, "pit": t, "early": t, "pit_unfloored": t},
        {"pit": 50, "early": None},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        "2026-03-02", 500, 0, 1.0, traded_early=60))
    assert "Not the published backtest" in out
    assert "SIGN STABILITY" in out
    assert "has NOT been spent" in out


def test_a_dead_floor_report_also_carries_the_caveats():
    t = [{"date": "2026-03-02", "symbol": f"S{i}", "net": -10.0,
          "first_seen": None} for i in range(200)]
    out = "\n".join(PS.render(
        "mcl", {"stage2": t, "pit": t, "early": t, "pit_unfloored": t},
        {"pit": 0, "early": None},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        {"stage2": 500, "pit": PS.H0_PIT_OFFERED, "early": 100},
        "2026-03-02", 500, 0, 1.0, traded_early=60))
    assert "ZERO" in out and "Not the published backtest" in out
