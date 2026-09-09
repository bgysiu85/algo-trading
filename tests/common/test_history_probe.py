#!/usr/bin/env python3
"""The probe that decides whether MC5 can be warm at 04:00.

H6 in claude/multi_strategy_trader_spec.md. Nothing here talks to IB; what is
tested is the arithmetic that turns a frame into "warm or cold", and the two
places that arithmetic could quietly lie.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import history_probe as H
from common import strategy_adapter as SA
from strategy.mc5 import mc5 as MC5

ET = ZoneInfo("America/New_York")


def frame(n, start="2026-01-07 04:00", drop=()):
    t0 = pd.Timestamp(start, tz=ET)
    idx = [t0 + timedelta(minutes=i) for i in range(n) if i not in drop]
    # tz= explicitly, because an EMPTY DatetimeIndex has no timestamps to
    # infer a zone from and tz_convert then raises. The empty case is the one
    # this helper most needs to build.
    idx = pd.DatetimeIndex(idx, tz=ET).tz_convert("UTC")
    return pd.DataFrame({"open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0,
                         "volume": 100.0}, index=idx)


# --- counting buckets --------------------------------------------------------

def test_a_one_minute_strategy_counts_bars():
    assert H.buckets(frame(37), 1) == 37


def test_five_minute_buckets_are_counted_not_divided():
    """THE ERROR THIS AVOIDS. A bucket with no prints produces no row when the
    frame is resampled, and on a thin pre-market name that is a large fraction
    of them. len(df)/5 would overstate how warm MC5 is -- which is precisely
    the mistake this probe exists to stop us making."""
    # 60 consecutive minutes -> 12 buckets.
    assert H.buckets(frame(60), 5) == 12
    # The same hour with only the first minute of each bucket printing: still
    # 12 buckets, but len(df)/5 would say 2.
    sparse = frame(60, drop=[i for i in range(60) if i % 5 != 0])
    assert len(sparse) == 12
    assert H.buckets(sparse, 5) == 12
    assert len(sparse) // 5 == 2, "the wrong arithmetic, kept as the contrast"


def test_an_empty_frame_is_zero_buckets_not_a_crash():
    assert H.buckets(frame(0), 5) == 0
    assert H.buckets(None, 5) == 0


# --- warm or cold ------------------------------------------------------------

def test_mc5_needs_five_times_the_wall_clock_mcl_does():
    """The whole of H6 in one assertion. Both need 40 bars; MCL's are minutes
    and MC5's are five-minute buckets."""
    adapters = SA.build_all(["mcl", "mc5"])
    hour = frame(60)
    got = {r["name"]: r for r in H.measure(hour, adapters)}
    assert got["MCL"]["warm"] is True, "40 one-minute bars fit in an hour"
    assert got["MC5"]["warm"] is False, "40 five-minute buckets do not"


def test_mc5_is_warm_once_it_has_its_bars():
    adapters = SA.build_all(["mc5"])
    enough = frame(MC5.MIN_BARS_REQUIRED * MC5.BAR_MINUTES)
    assert H.measure(enough, adapters)[0]["warm"] is True


def test_warm_is_decided_on_the_boundary_not_approximately():
    adapters = SA.build_all(["mc5"])
    need = MC5.MIN_BARS_REQUIRED
    just_under = frame((need - 1) * MC5.BAR_MINUTES)
    assert H.measure(just_under, adapters)[0]["have"] == need - 1
    assert H.measure(just_under, adapters)[0]["warm"] is False


# --- the report --------------------------------------------------------------

def rows_for(bars_1d, bars_2d):
    adapters = SA.build_all(["mcl", "mc5"])
    def block(n):
        df = frame(n)
        local = df.index.tz_convert(ET)
        return {"bars": len(df), "first": str(local[0]), "last": str(local[-1]),
                "span_h": 1.0, "strategies": H.measure(df, adapters)}
    return [{"symbol": "WYHG", "requests": 3,
             "by_duration": {"1 D": block(bars_1d), "2 D": block(bars_2d)}}], adapters


def test_an_empty_response_is_called_ambiguous_not_no_data():
    """IB signals pacing by returning an empty list rather than an error. A
    probe that reported that as 'no history' would send the reader to the
    wrong problem."""
    adapters = SA.build_all(["mcl"])
    rows = [{"symbol": "X", "requests": 2,
             "by_duration": {"1 D": {"empty": True}, "2 D": {"empty": True}}}]
    text = "\n".join(H.render(rows, adapters, datetime.now(ET)))
    assert "EMPTY LIST" in text and "ambiguous" in text
    assert "no data" in text, "and says so in the reader's words"


def test_the_report_states_all_three_outcomes_it_could_have():
    """Cold on 1 D and warm on 2 D, cold on both, warm on 1 D. The middle one
    is not a bug to fix but a fact about the strategy, and the report has to
    say so or someone will 'fix' it."""
    rows, adapters = rows_for(60, 300)
    text = "\n".join(H.render(rows, adapters, datetime.now(ET)))
    assert "one argument in _fetch_bars" in text
    assert "back half" in text
    assert "false alarm" in text


def test_the_report_shows_warm_and_cold_per_strategy():
    rows, adapters = rows_for(60, MC5.MIN_BARS_REQUIRED * MC5.BAR_MINUTES)
    text = "\n".join(H.render(rows, adapters, datetime.now(ET)))
    assert "COLD" in text and "warm" in text


def test_the_report_says_when_it_was_asked():
    """The answer depends on the time of day: at 04:10 '1 D' may hold ten
    minutes or a whole prior session, and only one of those is a problem."""
    rows, adapters = rows_for(60, 300)
    when = datetime(2026, 9, 10, 4, 10, tzinfo=ET)
    text = "\n".join(H.render(rows, adapters, when))
    assert "2026-09-10 04:10" in text


# --- safety ------------------------------------------------------------------

def test_it_refuses_a_live_port():
    """Same guard as the trader, not a copy of the numbers."""
    from brokers.ibkr import trader as T
    assert set(H.LIVE_PORTS) == set(T.LIVE_PORTS)
    assert set(H.PAPER_PORTS) == set(T.PAPER_PORTS)
    for port in T.LIVE_PORTS:
        with pytest.raises(SystemExit) as e:
            H.main(["--symbols", "AAPL", "--port", str(port)])
        assert "REFUSING TO RUN" in str(e.value)


def test_it_refuses_a_port_that_is_merely_unknown():
    with pytest.raises(SystemExit) as e:
        H.main(["--symbols", "AAPL", "--port", "9999"])
    assert "not a known paper port" in str(e.value)


# --- what the probe decided --------------------------------------------------

def test_the_trader_asks_for_enough_history_for_its_hungriest_strategy():
    """MEASURED, not chosen. common/history_probe.py at 06:22 ET on four live
    names: "1 D" returned ~143 bars starting 04:00 -- this session so far, so
    NO warm-up at the open -- and "2 D" returned ~1,100.

    MC5 needs 40 five-minute buckets, so it is blind for 200 minutes of a
    330-minute session on "1 D". The duration belongs to the FEED, which is
    shared per symbol, so there is one of them and it must satisfy the
    hungriest strategy.
    """
    from brokers.ibkr import trader as T

    assert T.HISTORY_DURATION == "2 D"
    worst = max(getattr(a.module, "MIN_BARS_REQUIRED", 0) * a.bar_minutes
                for a in SA.build_all(list(SA.BUILDERS)))
    assert worst == 200, "MC5 is the hungriest at 40 x 5m"
    # "1 D" measured at ~2.4 hours into the session and starting AT the open,
    # so it cannot cover a 200-minute warm-up under any reading.
    assert worst > 143, (
        "if a strategy's warm-up ever fits inside a '1 D' response, re-run "
        "the probe before assuming this constant still needs to be '2 D'")


def test_the_duration_is_used_and_not_merely_defined():
    """A constant nothing reads is a comment. Asserted by calling the fetch
    with a stub and reading back what it asked for."""
    import asyncio

    from brokers.ibkr import trader as T

    asked = {}

    class Stub:
        async def reqHistoricalDataAsync(self, contract, **kw):
            asked.update(kw)
            return []

    tr = T.MCLPaperTrader.__new__(T.MCLPaperTrader)
    tr.ib = Stub()
    st = T.SymbolState(symbol="X")
    st.contract = object()
    asyncio.run(T.MCLPaperTrader._fetch_bars(tr, st))
    assert asked.get("durationStr") == T.HISTORY_DURATION
    assert asked.get("useRTH") is False, "pre-market or the warm-up is moot"
