#!/usr/bin/env python3
"""Two session-open defects found in the live paper record, 2026-09-16.

DEFECT 1 -- THE CLOCK WAS CHECKED AND THE BAR WAS NOT.

`MCLPaperTrader.in_session` asks what time it is. At 04:00:10 that is inside
04:00-09:30, so the poll proceeded; but nothing had printed yet today, so the
frame IB handed back still ended with YESTERDAY'S 19:59 bar. The strategy
evaluated it, the entry dedupe saw a timestamp it had never seen before and let
it through, and the trader bought at the open on a signal from last night's
close.

Two checks that look like one check. This is the project's shape *a check
placed one step short of the thing it protects*: the clock gate protects "are
we trading now", and what needed protecting was "is this signal about now".

DEFECT 2 -- THE TRAIL STARTED FROM A PRICE THE POSITION NEVER TRADED AT.

The entry seeded `peak=max(avg, sig.close)`. `sig.close` is the SIGNAL bar's
close, from before the order existed. On VEEA the signal bar closed at 5.8709
and the fill came at 5.70, so the position opened with a trail level of 5.5774
against an entry of 5.70 -- eleven cents from a stop it had never had the
chance to earn. A trail measures GIVEBACK, and giveback can only be measured
from a high the position actually saw.

The two neighbouring paths already had this right: `manage_position` refuses a
bar high from a bar that closed before entry, and the restart-adoption path
seeds from `max(entry_price, highs since entry)`. Three of four agreed; the
fourth was the one placing orders.

WHY THE PARITY TEST IS THE POINT. A gate written only here would be a fourth
opinion about what "in session" means. `strategy/mcl/mcl.in_session_mask` is
the engine's own construction, extracted from `backtest_session` unchanged, and
`test_gate_agrees_with_the_engine_bar_for_bar` runs both over one frame. Had
the test restated the expression instead, it would have been a guard tested by
a copy of itself.
"""
from __future__ import annotations

import asyncio
import csv
import dataclasses
import tempfile
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA
from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as S

from tests.brokers.ibkr.test_dryrun_roundtrip import (FakeTicker,
                                                      find_firing_series)
from tests.brokers.ibkr.test_live_paths import FakeIB, FakeTrade

ET = M.ET


# --------------------------------------------------------------------------
# frames
# --------------------------------------------------------------------------

def firing_frame(scale_to: float | None = None) -> pd.DataFrame:
    """The suite's firing series, truncated so the ENTRY BAR IS THE LAST BAR.

    Truncating matters: the gate is applied to the bar the signal was computed
    on, so a frame whose entry is thirty bars back would be testing the gate
    against a timestamp the trader never sees.

    `scale_to` multiplies every price so the entry bar closes there. MCL's
    entry conditions are all ratios -- MACD crossings, RSI/MFI direction,
    volume against its own average -- so scaling moves the price and nothing
    else, the same trick `test_price_band` uses.
    """
    full, _seed, _spike = find_firing_series(140)
    assert full is not None, "the firing series no longer fires an entry"
    fires = [i for i, e in enumerate(S.signals(full)["entry"]) if e]
    assert fires, "the firing series no longer fires an entry"
    df = full.iloc[: fires[0] + 1]
    assert len(df) >= M.MIN_BARS_REQUIRED
    if scale_to is not None:
        factor = scale_to / float(df["close"].iloc[-1])
        df = df.copy()
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] * factor
    sig = M.evaluate(df)
    assert sig is not None and sig.long_entry, (
        "the truncated frame must still fire on its last bar, or every "
        "end-to-end case below would pass by never reaching the gate")
    return df


def retimed(df: pd.DataFrame, last_et: str) -> pd.DataFrame:
    """Same bars, re-stamped so the LAST one sits at `last_et` (ET), 1/minute.

    MCL reads no timestamps at all, so this moves when the signal happened
    without touching what the signal is.
    """
    end = pd.Timestamp(last_et, tz=ET)
    idx = pd.DatetimeIndex(
        [end - timedelta(minutes=len(df) - 1 - i) for i in range(len(df))]
    ).tz_convert("UTC")
    out = df.copy()
    out.index = idx
    return out


def at(s: str) -> datetime:
    return pd.Timestamp(s, tz=ET).to_pydatetime()


MCL = SA.mcl_adapter()


# --------------------------------------------------------------------------
# 1. the gate itself
# --------------------------------------------------------------------------

def ok(ts, now, adapter=MCL):
    return M.bar_session_ok(ts, at(now), adapter.session_start,
                            adapter.session_end)


def test_yesterdays_last_bar_is_refused_at_the_open():
    """THE OBSERVED DEFECT. 19:59 the previous evening, evaluated at 04:00:10."""
    good, why = ok(pd.Timestamp("2026-09-15 19:59", tz=ET),
                   "2026-09-16 04:00:10")
    assert not good
    assert "not today" in why


def test_an_overnight_bar_from_today_is_refused():
    """03:59 IS today, so the date check alone would have passed it. The window
    is what refuses it -- which is why both conditions are here and neither is
    a restatement of the other."""
    good, why = ok(pd.Timestamp("2026-09-16 03:59", tz=ET),
                   "2026-09-16 04:00:10")
    assert not good
    assert "outside" in why


def test_the_first_real_bar_of_the_session_is_allowed():
    """THE CONTROL. A gate that refused this would be indistinguishable from
    one that works, on a day with no entries -- and every session-open entry
    would quietly stop happening."""
    good, why = ok(pd.Timestamp("2026-09-16 04:00", tz=ET),
                   "2026-09-16 04:01:05")
    assert good, why


def test_the_last_bar_before_the_close_is_allowed():
    good, why = ok(pd.Timestamp("2026-09-16 09:29", tz=ET),
                   "2026-09-16 09:29:40")
    assert good, why


def test_the_closing_boundary_is_half_open():
    """09:30 is the flatten time, not a tradeable bar. Left-labelled bars make
    09:29 the last one inside a session ending at 09:30."""
    good, _why = ok(pd.Timestamp("2026-09-16 09:30", tz=ET),
                    "2026-09-16 09:30:10")
    assert not good


def test_a_naive_timestamp_is_refused_rather_than_guessed():
    """Fails CLOSED. Guessing the zone of a naive stamp is a five-hour error in
    whichever direction the guess fell, and one of those directions admits
    exactly the bar this gate exists to stop."""
    good, why = ok(pd.Timestamp("2026-09-16 05:00"), "2026-09-16 05:01:00")
    assert not good
    assert "timezone" in why


def test_a_signal_with_no_bar_timestamp_is_refused():
    good, why = ok(None, "2026-09-16 05:01:00")
    assert not good
    assert "bar timestamp" in why


def test_the_window_comes_from_the_adapter_not_from_mcl():
    """VW9 runs to 20:00. A gate reading a module constant would refuse its
    whole afternoon while reporting that it had checked the session -- the
    same failure `in_session` was already written to avoid."""
    late = dataclasses.replace(MCL, name="vw9-shaped",
                               session_end=dtime(20, 0))
    ts = pd.Timestamp("2026-09-16 19:59", tz=ET)
    assert not ok(ts, "2026-09-16 19:59:30")[0]
    assert ok(ts, "2026-09-16 19:59:30", late)[0]


# --------------------------------------------------------------------------
# 2. parity with the engine
# --------------------------------------------------------------------------

def test_gate_agrees_with_the_engine_bar_for_bar():
    """The live gate and `backtest_session`'s own mask, over three days.

    Not a restatement of the rule: `in_session_mask` is the function
    `backtest_session` calls, so this fails the day either side moves.
    """
    idx = pd.date_range("2026-09-14 00:00", "2026-09-16 23:59",
                        freq="1min", tz=ET).tz_convert("UTC")
    session_date = pd.Timestamp("2026-09-16", tz=ET).date()
    engine = S.in_session_mask(idx, session_date, ET)
    now = at("2026-09-16 09:00:00")

    disagreed = [ts for ts, want in zip(idx, engine)
                 if M.bar_session_ok(ts, now, S.SESSION_START,
                                     S.SESSION_END)[0] != bool(want)]
    assert not disagreed, (
        f"{len(disagreed)} bars judged differently, first {disagreed[:3]}")
    # And the mask is not trivially all-False or all-True, or agreeing with it
    # would mean nothing.
    assert 0 < sum(bool(x) for x in engine) < len(idx)


# --------------------------------------------------------------------------
# 3. the live path
# --------------------------------------------------------------------------

def one(tag, adapter, fill_price=5.00):
    out = Path(tempfile.gettempdir()) / f"stale_{tag}.csv"
    if out.exists():
        out.unlink()
    log = M.FillLog(out)
    tr = M.MCLPaperTrader(FakeIB([FakeTrade(100, fill_price, "Filled")] * 8),
                          Path(tempfile.gettempdir()) / "wl.txt", log,
                          dry_run=False)
    tr.equity = 22290.96
    st = M.SymbolState(symbol="TEST", strategy=adapter)
    st.contract = object()
    st.ticker = FakeTicker()
    tr.states[(adapter.name, "TEST")] = st
    return tr, st, log, out


def drive(tag, df, now, adapter=MCL, polls=1, fill_price=5.00):
    tr, st, log, out = one(tag, adapter, fill_price)
    tr.bars = lambda _s, _d=df: asyncio.sleep(0, result=_d)

    async def go():
        for i in range(polls):
            await tr.step_symbol(st, at(now) + timedelta(seconds=i))
    asyncio.run(go())
    log.close()
    return st, list(csv.DictReader(out.open(encoding="utf-8")))


def rows_with(rows, status):
    return [r for r in rows if r.get("status") == status]


def bought(rows):
    return [r for r in rows if r.get("action") == "BUY"
            and r.get("status") in ("FILLED", "PARTIAL_FILL", "DRY_RUN")]


def test_live_refuses_yesterdays_bar_and_records_why():
    """A silent skip is indistinguishable from "no signal fired" when the
    session is reviewed afterwards, which is exactly how this survived."""
    df = retimed(firing_frame(), "2026-09-15 19:59")
    st, rows = drive("yesterday", df, "2026-09-16 04:00:10")
    assert st.position is None
    assert not bought(rows)
    assert len(rows_with(rows, "SKIPPED_STALE_BAR")) == 1
    assert "not today" in rows_with(rows, "SKIPPED_STALE_BAR")[0]["reject_reason"]


def test_live_refuses_an_overnight_bar():
    df = retimed(firing_frame(), "2026-09-16 03:59")
    st, rows = drive("overnight", df, "2026-09-16 04:00:10")
    assert st.position is None
    assert not bought(rows)
    assert len(rows_with(rows, "SKIPPED_STALE_BAR")) == 1


def test_live_still_takes_the_first_real_bar():
    """THE CONTROL AGAIN, through step_symbol this time. Without it every
    assertion above is satisfied by a trader that has stopped trading."""
    df = retimed(firing_frame(), "2026-09-16 04:00")
    st, rows = drive("firstbar", df, "2026-09-16 04:01:05")
    assert not rows_with(rows, "SKIPPED_STALE_BAR")
    assert bought(rows), "the fix refuses a bar it should have taken"
    assert st.position is not None


def test_a_stale_bar_is_logged_once_and_not_once_per_poll():
    """The gate sits AFTER the dedupe deliberately. Before it, a frame frozen
    at last night's close would write a refusal every second until the first
    print of the day -- thousands of rows saying the same thing, in the ledger
    every downstream reader opens."""
    df = retimed(firing_frame(), "2026-09-15 19:59")
    _st, rows = drive("repeat", df, "2026-09-16 04:00:10", polls=5)
    assert len(rows_with(rows, "SKIPPED_STALE_BAR")) == 1


def test_a_naive_frame_stops_trading_rather_than_trading_blind():
    df = retimed(firing_frame(), "2026-09-16 05:00")
    df.index = df.index.tz_localize(None)
    st, rows = drive("naive", df, "2026-09-16 05:01:00")
    assert st.position is None
    assert "timezone" in rows_with(rows, "SKIPPED_STALE_BAR")[0]["reject_reason"]


def test_mc5s_last_complete_bucket_can_be_before_the_session_opens():
    """MC5's bucket is not MCL's minute, and this is where that bites.

    At 04:00:11 the newest COMPLETE five-minute bucket is 03:55 -- a bucket
    that closed before the session started. `last_closed_bucket` is right about
    it being complete; it is simply not a bar this session may trade.

    Only `long_entry` is forced. The bucket timestamp is real MC5 output, which
    is the part under test.
    """
    # Back into the previous evening, because MC5 needs MIN_BARS_REQUIRED
    # FIVE-minute buckets and the overnight is where they have to come from.
    idx = pd.date_range("2026-09-15 18:00", "2026-09-16 03:59",
                        freq="1min", tz=ET).tz_convert("UTC")
    px = [5.0 + 0.01 * i for i in range(len(idx))]
    df = pd.DataFrame({"open": px, "high": [p + .02 for p in px],
                       "low": [p - .02 for p in px], "close": px,
                       "volume": [10_000.0] * len(idx)}, index=idx)

    real = MC5.evaluate_last_bar(df, at("2026-09-16 04:00:11"))
    assert real is not None
    assert pd.Timestamp(real.bar_ts).tz_convert(ET) == \
        pd.Timestamp("2026-09-16 03:55", tz=ET)

    forced = dataclasses.replace(real, long_entry=True)
    mc5 = dataclasses.replace(SA.mc5_adapter(), _evaluate=lambda _d, _n: forced)
    st, rows = drive("mc5", df, "2026-09-16 04:00:11", adapter=mc5)
    assert st.position is None
    assert len(rows_with(rows, "SKIPPED_STALE_BAR")) == 1


# --------------------------------------------------------------------------
# 4. the trail peak
# --------------------------------------------------------------------------

VEEA_SIGNAL_CLOSE = 5.8709
VEEA_FILL = 5.70


def veea():
    df = retimed(firing_frame(scale_to=VEEA_SIGNAL_CLOSE), "2026-09-16 05:00")
    return drive("veea", df, "2026-09-16 05:01:00", fill_price=VEEA_FILL)


def test_the_peak_starts_at_the_fill_not_at_the_signal_close():
    st, _rows = veea()
    assert st.position is not None, "no entry -- the case never reached a peak"
    assert st.position.peak == pytest.approx(VEEA_FILL)
    assert st.position.trail_level() == pytest.approx(5.415, abs=1e-9)


def test_a_price_above_the_trail_does_not_exit():
    """5.55 is 2.6% below the 5.70 fill and the trail is 5%.

    Under `peak=max(avg, sig.close)` the level was 5.5774 and this exited -- a
    losing trade produced entirely by a price the position never traded at.
    """
    st, _rows = veea()
    st.ticker.bid, st.ticker.ask = 5.54, 5.55
    tr = M.MCLPaperTrader(FakeIB([]), Path(tempfile.gettempdir()) / "wl.txt",
                          M.FillLog(Path(tempfile.gettempdir()) / "veea2.csv"),
                          dry_run=True)
    tr.states[(st.strategy.name, st.symbol)] = st
    asyncio.run(tr.manage_position(st, at("2026-09-16 05:02:00"),
                                   bar_close=5.55, detail={}))
    assert st.position is not None, "trailing stop fired above its own level"
    assert st.position.exiting is None


def test_the_old_seeding_would_have_exited_on_that_same_price():
    """The counter-case, so the test above is known to be capable of failing.

    A trail level derived from 5.8709 IS hit by 5.55; the fix is the seed, not
    the comparison.
    """
    old = M.Position(symbol="TEST", qty=100, entry_price=VEEA_FILL,
                     entry_time=at("2026-09-16 05:01:00"),
                     peak=max(VEEA_FILL, VEEA_SIGNAL_CLOSE),
                     trail_pct=MCL.trail_pct)
    assert 5.55 <= old.trail_level()
    new = dataclasses.replace(old, peak=VEEA_FILL)
    assert 5.55 > new.trail_level()
