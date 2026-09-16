#!/usr/bin/env python3
"""The forming-bar trim, after it stopped being unconditional.

MEASURED FIRST. `common/bar_freshness.py` ran on BNC on 2026-09-16 and answered
the question the function was built around: IB DOES include the forming minute,
10 of 11 countable samples. So the trim stays.

The eleventh sample is why this file exists:

    06:04:05  raw last 06:03  -> acts on 06:02   (closed, raw 65s)

The 06:03 bar had already closed. `df.iloc[:-1]` threw it away anyway and the
strategy acted a full minute late. A minute with no print produces no bar --
`mc5.last_closed_bucket` documents the same mechanism -- so on a thin name the
response often ends with a finished bar.

Whether IB sends the forming minute is not a property of IB. It is a property
of the moment you ask, and the probe's verdict reported the mode of that
distribution as though it were a constant. The trim now asks the clock.

Registered in docs/research/REGISTERED_bar_trim.md BEFORE the change.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from brokers.ibkr import trader as M

ET = M.ET


def frame(last_label: str, n: int = 5) -> pd.DataFrame:
    """n 1-minute bars ending with one labelled `last_label` (ET)."""
    end = pd.Timestamp(last_label, tz=ET)
    idx = pd.DatetimeIndex(
        [end - timedelta(minutes=n - 1 - i) for i in range(n)]
    ).tz_convert("UTC")
    px = [5.0 + 0.01 * i for i in range(n)]
    return pd.DataFrame({"open": px, "high": px, "low": px, "close": px,
                         "volume": [1000.0] * n}, index=idx)


def at(s: str) -> datetime:
    return pd.Timestamp(s, tz=ET).to_pydatetime()


def last_of(df) -> str:
    return f"{df.index[-1].tz_convert(ET):%H:%M}"


# --- the 90.9% case: nothing changes ---------------------------------------

def test_a_forming_bar_is_still_dropped():
    """The majority case from the probe, and the one the trim exists for.
    Acting on a partial bar is H1; this must not have become possible."""
    df = frame("2026-09-16 06:03")
    assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:03:18"))) == "06:02"


@pytest.mark.parametrize("second", [0, 1, 18, 34, 50, 58])
def test_dropped_at_every_point_inside_the_minute(second):
    df = frame("2026-09-16 06:03")
    now = at(f"2026-09-16 06:03:{second:02d}")
    assert last_of(M.drop_forming_bar(df, now)) == "06:02"


# --- the 9.1% case: the minute that used to be lost -------------------------

def test_an_already_closed_last_bar_is_kept():
    """THE OBSERVED SAMPLE, replayed. At 06:04:05 the response ended at 06:03
    and 06:03 had closed five seconds earlier. The old trim acted on 06:02."""
    df = frame("2026-09-16 06:03")
    assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:04:05"))) == "06:03"


def test_the_old_behaviour_would_have_lost_that_minute():
    """The counter-case, so the test above is known to be capable of failing."""
    df = frame("2026-09-16 06:03")
    assert last_of(df.iloc[:-1]) == "06:02"


# --- the boundary, and which way it errs ------------------------------------

@pytest.mark.parametrize("when,want", [
    ("06:03:59", "06:02"),   # still forming, one second to run
    ("06:04:00", "06:02"),   # closed this instant -- inside the skew margin
    ("06:04:01", "06:02"),   # ditto
    ("06:04:02", "06:03"),   # BAR_CLOSE_SKEW_S clear
    ("06:04:30", "06:03"),
])
def test_the_skew_margin_errs_toward_dropping(when, want):
    """`BAR_CLOSE_SKEW_S` guards one direction only: a local clock running fast
    calls a bar closed with time still to run. Inside the margin the function
    falls back to the old, safe answer, so the error is always a minute of lag
    and never a partial bar."""
    df = frame("2026-09-16 06:03")
    assert last_of(M.drop_forming_bar(df, at(f"2026-09-16 {when}"))) == want


def test_the_margin_is_read_from_the_module_not_restated_here():
    """Moving the constant moves the behaviour. A test carrying its own copy of
    2.0 would pass forever after someone changed the real one."""
    df = frame("2026-09-16 06:03")
    real = M.BAR_CLOSE_SKEW_S
    try:
        M.BAR_CLOSE_SKEW_S = 30.0
        assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:04:20"))) == "06:02"
        assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:04:31"))) == "06:03"
    finally:
        M.BAR_CLOSE_SKEW_S = real


# --- degenerate shapes ------------------------------------------------------

def test_a_single_bar_frame_is_never_emptied():
    """Returning an empty frame would make `df.index[-1]` raise inside
    step_symbol on the one poll where history had just started."""
    df = frame("2026-09-16 06:03", n=1)
    assert len(M.drop_forming_bar(df, at("2026-09-16 06:03:10"))) == 1
    assert len(M.drop_forming_bar(df, at("2026-09-16 06:09:10"))) == 1


def test_a_stale_frame_keeps_its_last_bar():
    """Nothing has printed for ten minutes. Every bar in the frame has closed,
    so none of them is forming and none is dropped. Judging that frame stale is
    `bar_session_ok`'s job and not this function's -- one concern each."""
    df = frame("2026-09-16 06:03")
    assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:13:00"))) == "06:03"


def test_a_naive_now_raises_rather_than_guessing():
    """The caller controls `now`; a naive one is a programming error, not a
    market condition. Guessing its zone decides whether a partial bar reaches a
    strategy, so it is the one thing this function will not do quietly."""
    df = frame("2026-09-16 06:03")
    with pytest.raises(ValueError, match="aware"):
        M.drop_forming_bar(df, datetime(2026, 9, 16, 6, 4, 5))


def test_the_bar_length_is_a_parameter_not_a_hard_coded_minute():
    """The trader fetches 1-minute bars, but the function should not be the
    place that knows so -- a 5-minute caller would otherwise keep a bucket that
    had four minutes to run."""
    df = frame("2026-09-16 06:00")
    assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:03:00"), 5)) == "05:59"
    assert last_of(M.drop_forming_bar(df, at("2026-09-16 06:05:30"), 5)) == "06:00"


# --- the caller ------------------------------------------------------------

def test_the_probe_calls_the_trader_and_does_not_copy_it():
    """`common/bar_freshness.py` must report what the trader really does. It
    imports the function; this fails the day someone reimplements it there."""
    from common import bar_freshness as BF
    assert BF.drop_forming_bar is M.drop_forming_bar
