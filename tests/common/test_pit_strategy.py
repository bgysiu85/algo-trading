#!/usr/bin/env python3
"""MCL/MC5 on the point-in-time universe.

Two properties carry this module, and both are about the entry floor:

1. `not_before=None` must be BIT-IDENTICAL to the published engines. These are
   modules whose output is already written into the docs; a default that moved
   would rewrite history silently.
2. The floor must actually SUPPRESS something, and the report must refuse a
   verdict when it does not -- because an unwired floor and a strategy that
   never enters early produce the same trade list, and only one of them is a
   result.
"""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import pit_strategy as P
from strategy.mcl import mcl as MCL
from strategy.mc5 import mc5 as MC5

ET = ZoneInfo("America/New_York")
D = date(2026, 3, 2)


def frame(sym="AAA", n=330, period=40, amp=0.30, drift=0.004,
          base_v=40_000.0, spike=130_000.0):
    """Two 04:00-09:30 sessions with a real overnight gap between them.

    Shaped to MCL's actual entry conditions rather than to something that looks
    like a rally, because the first attempt at this fixture entered zero times
    and would have made every floor assertion below vacuously true:

      * a WOBBLY uptrend, not a ramp. A monotone ramp pins RSI at 100, and
        `rising()` is false on a flat series, so a pure ramp never enters.
      * spike volume 3.25x the baseline, not 9x. `c_vol` wants today >= 3x
        yesterday, but `c_floor` wants yesterday >= half the 60-bar average --
        and too tall a spike lifts that average out of its own reach.
      * two SEPARATE day-blocks. A continuous 660-minute run never reaches the
        target date at all, so the session mask selected nothing.
    """
    idx = []
    for d in (D - timedelta(days=1), D):
        b = pd.Timestamp(datetime.combine(d, dtime(4, 0), tzinfo=ET))
        idx += [(b + timedelta(minutes=i)).tz_convert("UTC") for i in range(n)]
    idx = pd.DatetimeIndex(idx)
    close = [4.0 + drift * i + amp * math.sin(2 * math.pi * i / period)
             for i in range(len(idx))]
    vol = [spike if i % 3 == 0 else base_v for i in range(len(idx))]
    return pd.DataFrame({"symbol": sym, "open": close,
                         "high": [c + 0.02 for c in close],
                         "low": [c - 0.02 for c in close],
                         "close": close, "volume": vol}, index=idx)


def rec(sym="AAA", h=4, m=30):
    fs = pd.Timestamp(datetime.combine(D, dtime(h, m), tzinfo=ET)
                      ).tz_convert("UTC").isoformat()
    return {"symbol": sym, "date": D.isoformat(), "first_seen": fs}


# --- 1. the published engines are untouched by default ----------------------

@pytest.mark.parametrize("mod, extra", [(MCL, dict(use_apex=False,
                                                   require_macd_pos=True)),
                                        (MC5, {})])
def test_not_before_none_is_bit_identical_to_the_published_engine(mod, extra):
    """The whole reason `not_before` defaults to None. If this drifts, every
    figure in every doc quietly refers to code that no longer exists."""
    df = frame()
    a = mod.backtest_session(df, D, ET, entry_shares=100, **extra)
    b = mod.backtest_session(df, D, ET, entry_shares=100, not_before=None,
                             **extra)
    assert [vars(t) for t in a] == [vars(t) for t in b]


@pytest.mark.parametrize("mod, extra", [(MCL, dict(use_apex=False,
                                                   require_macd_pos=True)),
                                        (MC5, {})])
def test_a_floor_at_session_start_is_inert(mod, extra):
    """A floor EARLIER than the session can only be a no-op. If it were
    permissive in that direction it could pull an entry forward, which is the
    defect it exists to prevent, wearing the costume of a fix."""
    df = frame()
    a = mod.backtest_session(df, D, ET, entry_shares=100, **extra)
    b = mod.backtest_session(df, D, ET, entry_shares=100,
                             not_before=dtime(0, 0), **extra)
    assert [vars(t) for t in a] == [vars(t) for t in b]


@pytest.mark.parametrize("mod, extra", [(MCL, dict(use_apex=False,
                                                   require_macd_pos=True)),
                                        (MC5, {})])
def test_no_entry_ever_lands_before_the_floor(mod, extra):
    df = frame()
    for h, m in ((5, 0), (6, 30), (8, 0)):
        for t in mod.backtest_session(df, D, ET, entry_shares=100,
                                      not_before=dtime(h, m), **extra):
            got = pd.Timestamp(t.entry_time).tz_convert(ET).time()
            assert got >= dtime(h, m), f"entered {got} under floor {h}:{m}"


@pytest.mark.parametrize("mod, extra", [(MCL, dict(use_apex=False,
                                                   require_macd_pos=True)),
                                        (MC5, {})])
def test_the_floor_actually_suppresses_entries(mod, extra):
    """The control that proves the control. A frame that enters early, floored
    late, must lose that entry -- otherwise every 'floored' result in this
    module is an unfloored result with a different label."""
    df = frame()
    free = mod.backtest_session(df, D, ET, entry_shares=100, **extra)
    assert free, "fixture does not enter at all; it cannot test a floor"
    first = pd.Timestamp(free[0].entry_time).tz_convert(ET).time()
    late = mod.backtest_session(df, D, ET, entry_shares=100,
                                not_before=dtime(9, 0), **extra)
    assert first < dtime(9, 0)
    assert not late or pd.Timestamp(
        late[0].entry_time).tz_convert(ET).time() >= dtime(9, 0)


def test_the_floor_does_not_move_the_forced_flatten():
    """`entry_allowed` is a MASK over entries, never a narrowing of `idx`.

    `idx` also decides which bar is `last_of_session`, so narrowing it would
    make an ENTRY restriction silently rewrite the EXIT model -- the forced
    09:30 flatten would land on whatever bar happened to survive the floor.
    Here a floor at 08:45 removes seven of the eight entries, and the one that
    survives must still be flattened on the session's true final bar.
    """
    df = frame()
    loc = df.index.tz_convert(ET)
    m = ((loc.date == D) & (loc.time >= MCL.SESSION_START)
         & (loc.time < MCL.SESSION_END))
    last_bar = df.index[m][-1]

    free = MCL.backtest_session(df, D, ET, entry_shares=100, use_apex=False,
                                require_macd_pos=True)
    held = MCL.backtest_session(df, D, ET, entry_shares=100, use_apex=False,
                                require_macd_pos=True, not_before=dtime(8, 45))
    assert len(held) < len(free), "floor removed nothing; test proves nothing"
    assert held, "floor removed everything; nothing left to check the exit on"
    assert held[-1].reason == "window_close"
    assert pd.Timestamp(held[-1].exit_time) == last_bar
    assert held[-1].exit_time == free[-1].exit_time


def test_a_floor_past_every_signal_returns_no_trades_rather_than_failing():
    df = frame()
    assert MCL.backtest_session(df, D, ET, entry_shares=100, use_apex=False,
                                require_macd_pos=True,
                                not_before=dtime(9, 29)) == []


# --- 2. the runner ----------------------------------------------------------

def test_run_day_counts_the_symbol_days_where_the_floor_bit():
    df = frame()
    _, bit, seen = P.run_day(df, D.isoformat(), [rec(h=9, m=0)],
                             mod=MCL, extra=dict(use_apex=False,
                                                 require_macd_pos=True),
                             floor=True)
    assert bit == 1 and seen == 1


def test_run_day_with_no_floor_never_counts_a_bite():
    """The stage-2 arm has no first_seen and must not be charged with one."""
    df = frame()
    rows, bit, seen = P.run_day(df, D.isoformat(),
                                [{"symbol": "AAA", "date": D.isoformat(),
                                  "first_seen": None}],
                                mod=MCL, extra=dict(use_apex=False,
                                                    require_macd_pos=True),
                                floor=False)
    assert bit == 0 and seen == 1


def test_a_symbol_with_no_bars_is_skipped_not_crashed():
    df = frame(sym="AAA")
    rows, bit, seen = P.run_day(df, D.isoformat(), [rec(sym="ZZZ")],
                                mod=MCL, extra={}, floor=True)
    assert rows == [] and bit == 0 and seen == 0,  "a missing name was counted"


# --- 3. the early arm is derived, not re-run --------------------------------

def test_early_trades_is_a_strict_subset_selected_on_first_seen():
    rows = [{"symbol": "A", "date": "2026-03-02", "net": 1.0,
             "first_seen": rec(h=4, m=10)["first_seen"]},
            {"symbol": "B", "date": "2026-03-02", "net": 1.0,
             "first_seen": rec(h=7, m=10)["first_seen"]}]
    got = P.early_trades(rows)
    assert [r["symbol"] for r in got] == ["A"]


def test_early_trades_drops_records_with_no_first_seen():
    """A stage-2 record can never be 'early' -- it has no first_seen because it
    was never screened in time at all. Treating a missing value as early would
    quietly readmit the leaky universe into the honest arm."""
    assert P.early_trades([{"symbol": "A", "date": "2026-03-02", "net": 1.0,
                            "first_seen": None}]) == []


def test_needed_symbols_keeps_a_slice_for_the_days_that_warm_up_on_it():
    days = ["2026-03-02", "2026-03-03", "2026-03-04"]
    uni = {"2026-03-04": [{"symbol": "ZZZ"}]}
    want = P.needed_symbols([uni], days, warmup=1)
    assert "ZZZ" in want["2026-03-04"]
    assert "ZZZ" in want["2026-03-03"], "warm-up slice was not retained"
    assert "ZZZ" not in want.get("2026-03-02", set())


# --- 4. the report ----------------------------------------------------------

def trades(spec):
    return [{"date": d, "symbol": s, "net": n, "first_seen": None}
            for d, s, n in spec]


def arms(per, n=200):
    t = trades([(f"2026-{1 + i % 9:02d}-01", f"S{i}", per + 4.26)
                for i in range(n)])
    return {"stage2": t, "pit": t, "early": t}


def out(per=1.0, bit=7, counts=None, with_bars=None):
    counts = counts or {"stage2": 500, "pit": 400, "early": 100}
    return "\n".join(P.render(
        "mcl", arms(per), {"pit": bit, "early": None}, counts,
        with_bars or dict(counts), "2026-05-01", 500, 0, 1.0))


def test_a_floor_that_never_bit_refuses_every_verdict():
    o = out(bit=0)
    assert "ZERO" in o
    assert "NO VERDICT" not in o.split("ZERO")[0]
    for banned in ("WHAT THE LOOK-AHEAD WAS WORTH", "DO THE RULES BEAT"):
        assert banned not in o, f"{banned} rendered under a dead floor"


def test_a_live_floor_reports_the_leak_as_a_subtraction():
    o = out()
    assert "the leak" in o
    assert "WHAT THE LOOK-AHEAD WAS WORTH" in o


def test_a_thin_arm_gets_no_verdict_and_says_the_floor():
    o = "\n".join(P.render("mcl",
                           {"stage2": trades([("2026-01-01", "A", 5.0)]),
                            "pit": trades([("2026-01-01", "A", 5.0)]),
                            "early": []},
                           {"pit": 1, "early": None},
                           {"stage2": 1, "pit": 1, "early": 0},
                           {"stage2": 1, "pit": 1, "early": 0},
                           "2026-01-01", 10, 0, 1.0))
    assert "NO VERDICT" in o
    assert str(P.MIN_TRADES) in o


def test_beating_the_control_while_still_losing_is_said_plainly():
    """The likeliest outcome, and the one most open to being written up as a
    win. -$5 beats H0's -$15.78 and is still -$5."""
    o = out(per=-5.0)
    assert "beat the control and still lose money" in o


def test_losing_to_the_control_says_the_old_verdict_stands():
    o = out(per=-25.0)
    assert "do NOT beat the control" in o


def test_clearing_zero_asks_for_the_holdout_rather_than_another_variation():
    o = out(per=5.0)
    assert "holdout" in o and "not another in-sample variation" in o


def test_every_arm_is_reported_at_all_three_friction_levels():
    o = out()
    for label, _ in P.FRICTIONS:
        assert o.count(label) >= 3, f"{label} missing from an arm"
    assert "SIGN STABILITY" in o


def test_the_report_refuses_to_be_compared_to_a_published_figure():
    """Different warm-up and a different tape. Every prior result-inflating
    bug in this project was two numbers that looked comparable and were not."""
    o = out()
    assert "never to a figure from a doc" in o
    assert "Not the published backtest" in o


def test_the_report_says_the_holdout_has_not_been_spent():
    assert "has NOT been spent" in out()


def test_warmup_shortfall_is_reported_rather_than_absorbed():
    o = "\n".join(P.render("mcl", arms(1.0), {"pit": 5, "early": None},
                           {"stage2": 500, "pit": 400, "early": 100},
                           {"stage2": 500, "pit": 400, "early": 100},
                           "2026-05-01", 500, 12, 1.0))
    assert "less warm-up than" in o


def test_h0_reference_names_its_source():
    assert "pit_h0.txt" in out()


def test_a_degenerate_drop_top_5_prints_na_not_zero():
    """With DROP or fewer symbols the drop removes the whole arm and the column
    is exactly $0 -- identical to what a genuinely balanced arm prints. One of
    those is a result and the other is an empty set; they must not look the
    same."""
    few = {"stage2": trades([("2026-01-01", f"S{i}", 5.0) for i in range(3)]),
           "pit": trades([("2026-01-01", f"S{i}", 5.0) for i in range(3)]),
           "early": []}
    o = "\n".join(P.render("mcl", few, {"pit": 1, "early": None},
                           {"stage2": 3, "pit": 3, "early": 0},
                           {"stage2": 3, "pit": 3, "early": 0},
                           "2026-01-01", 10, 0, 1.0))
    rows = [ln for ln in o.splitlines()
            if ln.strip().startswith(("$1.00", "$4.26", "$8.92"))]
    assert rows
    for ln in rows:
        assert "n/a" in ln, ln


def test_a_real_drop_top_5_still_prints_a_number():
    o = out()
    assert "n/a" not in o


def test_unequal_tape_attrition_between_the_arms_is_flagged():
    """The stage-2 universe was built on a different tape, so names missing
    from XNAS.BASIC drop out of that arm and not the other. If the two arms
    keep very different shares of what they were offered, the leak subtraction
    is comparing two subsamples while looking exactly like a like-for-like."""
    o = out(counts={"stage2": 500, "pit": 400, "early": 100},
            with_bars={"stage2": 200, "pit": 390, "early": 98})
    assert "CAVEAT" in o and "upper bound" in o


def test_even_attrition_draws_no_caveat():
    o = out(counts={"stage2": 500, "pit": 400, "early": 100},
            with_bars={"stage2": 480, "pit": 388, "early": 97})
    assert "CAVEAT" not in o


def test_each_arm_reports_how_many_names_had_bars():
    assert "had bars on this tape" in out()
