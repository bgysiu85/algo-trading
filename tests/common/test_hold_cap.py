#!/usr/bin/env python3
"""The maximum-hold-time exit, and the study around it.

The mechanism is tested against constructed sessions rather than through the
report, because the report's job is to be read and the cap's job is to fire on
the right bar at the right price.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import hold_cap_study as H
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def frame(closes):
    """The established MCL fixture shape, matching tests/strategy/test_entry_delay.

    Volume surges every 10 bars from 60 onward, because MCL needs a 3x surge on
    the entry bar over a live trailing average and a flat volume series yields
    no trades at all -- every assertion below would then pass vacuously.
    """
    n = len(closes)
    vols = [5000.0] * n
    for i in range(60, n, 10):
        vols[i] = vols[i - 1] * MCL.VOL_MULTIPLE * 1.2
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET)
    idx = pd.DatetimeIndex([t0 + timedelta(minutes=i) for i in range(n)],
                           tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": closes, "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes], "close": closes,
                         "volume": vols}, index=idx)


def uptrend(n=160):
    """NOT a straight line: on a monotone rise RSI and MFI saturate at 100 and
    stop RISING, so the entry never fires. The wobble is what makes the fixture
    exercise anything."""
    return [round(3.00 + 0.012 * i + 0.12 * math.sin(i / 2.5), 4)
            for i in range(n)]


ENTRY_I = 80        # where uptrend()'s first entry lands, measured not assumed


def run(df, **kw):
    return MCL.backtest_session(df, date(2026, 3, 2), ET, use_apex=False,
                                require_macd_pos=True, **kw)


def test_the_fixture_still_enters_where_the_others_assume():
    """ENTRY_I is used to place collapses relative to the entry. If MCL's entry
    rules move, the fixtures below stop testing what they say they test and
    would fail in confusing ways rather than here."""
    t = run(frame(uptrend()))[0]
    t0 = pd.Timestamp("2026-03-02 04:00", tz=ET).tz_convert("UTC")
    got = int((pd.Timestamp(t.entry_time) - t0).total_seconds() // 60)
    assert got == ENTRY_I


# --- the parameter itself ---------------------------------------------------

def test_none_means_no_cap_and_is_the_default():
    import inspect
    sig = inspect.signature(MCL.backtest_session)
    assert sig.parameters["max_hold_bars"].default is None


def test_no_cap_is_byte_identical_to_the_old_behaviour():
    """If passing max_hold_bars=None changes anything, every figure this
    project has published silently moves."""
    df = frame(uptrend())
    a = run(df, max_hold_bars=None)
    b = run(df)
    assert [(t.entry_time, t.exit_time, t.net, t.reason) for t in a] == \
           [(t.entry_time, t.exit_time, t.net, t.reason) for t in b]


def test_zero_is_the_tightest_cap_not_a_disabled_one():
    """`if max_hold_bars:` would make 0 mean 'no cap', so the tightest cell of
    a sweep would secretly be the loosest -- and the report would print it as a
    number rather than fail. The same trap was live in trail_cents.

    Read off the SOURCE, because on a session that exits quickly anyway a
    behavioural test cannot separate 'cap of 0' from 'no cap'.
    """
    import inspect
    src = inspect.getsource(MCL.backtest_session)
    assert "max_hold_bars is not None" in src, (
        "the cap must be tested against None, never for truthiness")


# --- when it fires ----------------------------------------------------------

@pytest.mark.parametrize("cap", [3, 5, 10, 15])
def test_the_cap_closes_the_trade_after_exactly_that_many_bars(cap):
    """Entry is at the close of the signal bar, so a cap of 5 exits five bars
    later -- five minutes of holding, which is what was asked for."""
    trades = run(frame(uptrend()), max_hold_bars=cap)
    assert trades, "no trade taken; the fixture is not exercising the cap"
    assert trades[0].bars_held == cap
    assert trades[0].reason == "hold_cap"


def test_the_uncapped_trade_really_does_run_long():
    """Without this the cap tests could pass on a fixture that exits in two
    bars anyway, and the cap would be doing nothing."""
    t = run(frame(uptrend()))[0]
    assert t.bars_held == 79 and t.reason == "window_close"


def test_a_trade_that_ends_sooner_is_untouched():
    """A cap must not lengthen anything. A collapse eight bars after entry
    trips the 5% trail long before a 15-bar cap is reached."""
    px = uptrend()
    px = [px[i] if i < ENTRY_I + 8 else px[ENTRY_I + 7] * 0.80
          for i in range(len(px))]
    base = run(frame(px))
    caps = run(frame(px), max_hold_bars=15)
    assert base[0].reason == caps[0].reason == "trailing_stop"
    assert base[0].bars_held == caps[0].bars_held == 8
    assert base[0].net == caps[0].net


def test_a_longer_cap_cannot_produce_a_shorter_hold():
    """Monotonicity. If 10 ever held for fewer bars than 5, the cap is
    interacting with position management rather than bounding it."""
    df = frame(uptrend())
    held = [run(df, max_hold_bars=c)[0].bars_held for c in (3, 5, 10, 15)]
    assert held == sorted(held) == [3, 5, 10, 15]


# --- priority against the exits that already exist --------------------------

def test_the_trailing_stop_wins_on_a_shared_bar():
    """The trail is protection and fires intrabar; the cap fires at the close.
    If the cap outranked it, a stop that was actually hit would be recorded as
    a time exit and the exit mix would stop meaning anything.

    The drop lands on exactly the bar the 5-bar cap would fire.
    """
    px = uptrend()
    px = [px[i] if i <= ENTRY_I else
          (px[ENTRY_I] if i < ENTRY_I + 5 else px[ENTRY_I] * 0.90)
          for i in range(len(px))]
    t = run(frame(px), max_hold_bars=5)[0]
    assert t.bars_held == 5
    assert t.reason == "trailing_stop"


def test_window_close_keeps_its_label_on_the_final_bar():
    """The session forcing the position flat is not a decision the cap gets to
    relabel. At cap=29 the second trade reaches 29 bars ON the last bar of the
    session -- both rules fire and window_close must win."""
    trades = run(frame(uptrend()), max_hold_bars=29)
    assert [(t.reason, t.bars_held) for t in trades] == \
        [("hold_cap", 29), ("window_close", 29)]


def test_capping_frees_the_slot_and_changes_the_trade_count():
    """Not incidental -- it is why the paired comparison below exists. One
    79-bar hold becomes two shorter ones, so variant TOTALS are not comparing
    the same trades."""
    df = frame(uptrend())
    assert len(run(df)) == 1
    assert len(run(df, max_hold_bars=5)) == 2


# --- the study's own controls ----------------------------------------------

def test_the_halves_split_is_derived_from_the_sessions_scored():
    """prior_spike hard-coded a split that fell outside the range it scored, so
    every `late` figure was 0.00 and `(x) * 0` printed as a sign flip -- two
    confident verdicts from a control that divided nothing."""
    assert H.halves_split(["2026-01-01", "2026-01-02", "2026-01-03"]) \
        == "2026-01-02"
    assert H.halves_split([]) == ""


def test_an_empty_half_draws_no_verdict():
    """Every trade on one side of the split must suppress the verdict, not
    produce one from a comparison with zero."""
    class T:
        net, bars_held, reason, entry_time = 10.0, 2, "trailing_stop", "t0"
    trades = [("AAA", "2026-01-01", T()) for _ in range(20)]
    out = "\n".join(H.render([("no cap", trades), ("5 bars", trades)],
                             "2020-01-01", 20, 0))
    assert "DID NOT DIVIDE THIS RUN" in out
    assert "VERDICT on the" not in out


def test_the_emptiness_check_is_on_counts_not_sums():
    """A half netting exactly zero is not an empty half. Checking the sum would
    suppress a real verdict and look like the guard working."""
    class T:
        bars_held, reason, entry_time = 2, "trailing_stop", "t0"
        def __init__(self, n): self.net = n
    # Two trades in the late half that cancel to exactly 0.0.
    trades = ([("A", "2026-01-01", T(10.0)) for _ in range(10)]
              + [("A", "2026-06-01", T(MCL_F := 4.26 + 5.0)),
                 ("A", "2026-06-02", T(4.26 - 5.0))])
    s = H.stats(trades, "2026-03-01")
    assert s["late_n"] == 2 and s["late"] == pytest.approx(0.0)
    out = "\n".join(H.render([("no cap", trades), ("5 bars", trades)],
                             "2026-03-01", 12, 0))
    assert "DID NOT DIVIDE THIS RUN" not in out


def test_pairing_matches_on_the_entry_not_on_position_in_the_list():
    """A capped run frees the slot earlier and can enter again, so the two
    variants need not have the same number of trades. Pairing on (symbol, date,
    entry_time) compares the same trade under both rules; zipping two lists
    would silently compare different ones."""
    class T:
        bars_held, reason = 2, "x"
        def __init__(self, e, n): self.entry_time, self.net = e, n
    base = [("A", "d1", T("t1", 10.0)), ("A", "d1", T("t2", 20.0))]
    capped = [("A", "d1", T("t2", 5.0)), ("A", "d1", T("t3", 99.0))]
    p = H.paired(base, capped)
    assert p["n"] == 1                      # only t2 is in both
    assert p["total"] == pytest.approx(-15.0)
    assert p["worse"] == 1 and p["better"] == 0


def test_the_primary_is_five_and_the_boundary_does_not_contain_it():
    """5 is what Ben asked for. If it drifted into the boundary tuple the
    'best cell sits at an edge' check would be testing the primary."""
    assert H.PRIMARY_BARS == 5
    assert 5 not in H.BOUNDARY_BARS
    assert min(H.BOUNDARY_BARS) < 5 < max(H.BOUNDARY_BARS)
