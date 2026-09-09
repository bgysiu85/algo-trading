#!/usr/bin/env python3
"""The adapter the live trader reads instead of a strategy module.

Stage 2 of claude/multi_strategy_trader_spec.md. The hazard it exists for is
H2: with two strategies imported, `S.TRAIL_PCT` answers for whichever module
was imported last -- and MCL and MC5 agree on every constant today, so a
trader reading the wrong one is correct-looking until the day one changes.
"""
from __future__ import annotations

from datetime import time as dtime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common import strategy_adapter as A
from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")


def bars1m(n: int, start="2026-01-07 04:00", price=5.0, step=0.01):
    t0 = pd.Timestamp(start, tz=ET)
    idx = pd.DatetimeIndex(
        [t0 + timedelta(minutes=i) for i in range(n)]).tz_convert("UTC")
    px = [price + step * i for i in range(n)]
    return pd.DataFrame(
        {"open": px, "high": [p + 0.02 for p in px],
         "low": [p - 0.02 for p in px], "close": px,
         "volume": [10_000.0] * n}, index=idx)


def et(s):
    return pd.Timestamp(s, tz=ET)


# --- the values come off the module -----------------------------------------

def test_every_field_is_read_from_the_strategy_not_restated():
    """A copy of TRAIL_PCT in the adapter is a second source of truth that
    agrees with the first until someone changes one of them."""
    a = A.mcl_adapter()
    assert a.name == MCL.STRATEGY_NAME
    assert a.trail_pct == MCL.TRAIL_PCT
    assert (a.price_min, a.price_max) == (MCL.PRICE_MIN, MCL.PRICE_MAX)
    assert (a.session_start, a.session_end) == (MCL.SESSION_START,
                                                MCL.SESSION_END)
    assert a.enforce_band == MCL.ENFORCE_PRICE_BAND
    assert a.commission_plan == MCL.COMMISSION_PLAN


def test_a_change_to_the_strategy_reaches_the_adapter(monkeypatch):
    """The direct check that these are reads. If any field were a literal, the
    adapter would keep answering with the old number after a strategy edit --
    which is the live/backtest split this project keeps paying for."""
    monkeypatch.setattr(MC5, "TRAIL_PCT", 8.5)
    monkeypatch.setattr(MC5, "PRICE_MAX", 33.0)
    a = A.mc5_adapter()
    assert a.trail_pct == 8.5
    assert a.price_max == 33.0


def test_the_two_adapters_do_not_share_a_trail(monkeypatch):
    """H2. Today both are 5.0, which is exactly why a mix-up is invisible."""
    monkeypatch.setattr(MC5, "TRAIL_PCT", 9.0)
    assert A.mcl_adapter().trail_pct == MCL.TRAIL_PCT
    assert A.mc5_adapter().trail_pct == 9.0
    assert A.mcl_adapter().trail_pct != A.mc5_adapter().trail_pct


def test_each_adapter_carries_its_own_bar_size():
    assert A.mcl_adapter().bar_minutes == 1
    assert A.mc5_adapter().bar_minutes == MC5.BAR_MINUTES == 5


# --- the band ---------------------------------------------------------------

def test_in_band_uses_the_strategy_s_own_bounds():
    a = A.mcl_adapter()
    assert a.in_band(5.0)
    assert not a.in_band(0.9)
    assert not a.in_band(41.0)


def test_a_strategy_with_the_band_off_trades_anything(monkeypatch):
    monkeypatch.setattr(MC5, "ENFORCE_PRICE_BAND", False)
    a = A.mc5_adapter()
    assert a.in_band(4_152.0), (
        "band off has always meant no restriction; a hard-coded floor here "
        "would be a rule the strategy never asked for")


def test_size_for_delegates_rather_than_reimplementing():
    a = A.mcl_adapter()
    for px in (2.5, 7.0, 19.5):
        assert a.size_for(px) == MCL.size_for(px)


# --- evaluate ---------------------------------------------------------------

def test_mcl_through_the_adapter_matches_calling_it_directly():
    df = bars1m(120)
    direct = MCL.evaluate_last_bar(df)
    through = A.mcl_adapter().evaluate(df, et("2026-01-07 06:00"))
    assert (direct is None) == (through is None)
    assert direct.long_entry == through.long_entry
    assert direct.close == through.close


def test_mcl_ignores_now_because_its_last_bar_is_already_closed():
    """The trader drops the forming MINUTE before handing bars over, so for a
    1-minute strategy the last row is closed by construction."""
    df = bars1m(120)
    early = A.mcl_adapter().evaluate(df, et("2026-01-07 04:00"))
    late = A.mcl_adapter().evaluate(df, et("2026-01-07 23:00"))
    assert early.close == late.close


def test_mc5_through_the_adapter_refuses_the_forming_bucket():
    """H1, end to end. At 08:07 the 08:05 bucket holds two of its five
    minutes; the adapter must answer from 08:00 instead."""
    df = bars1m(400)
    part = df[df.index <= et("2026-01-07 08:06").tz_convert("UTC")]
    a = A.mc5_adapter()
    early = a.evaluate(part, et("2026-01-07 08:07"))
    assert early is not None
    closed = MC5.to_5m(part)
    assert early.close == pytest.approx(
        float(closed.loc[et("2026-01-07 08:00").tz_convert("UTC"), "close"]))


def test_the_adapter_passes_now_through_unaltered():
    """SURVIVED A MUTATION UNTIL THIS EXISTED. An adapter that handed MC5 a
    `now` ten minutes ahead passed every other test here, because the case
    they use is also blocked by the data-side half of the completeness rule.

    Here the data IS complete through the 08:05 bucket -- bars to 08:09 -- and
    only the clock is short: at 08:09:30 the bucket has not closed. So the
    answer must still come from 08:00, and any adapter that shifts `now`
    forward will take 08:05 and be caught.
    """
    df = bars1m(400)
    full = df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")]
    got = A.mc5_adapter().evaluate(full, et("2026-01-07 08:09:30"))
    closed = MC5.to_5m(full)
    assert got.close == pytest.approx(
        float(closed.loc[et("2026-01-07 08:00").tz_convert("UTC"), "close"]))


def test_mc5_through_the_adapter_takes_the_bucket_once_it_closes():
    df = bars1m(400)
    full = df[df.index <= et("2026-01-07 08:09").tz_convert("UTC")]
    a = A.mc5_adapter()
    got = a.evaluate(full, et("2026-01-07 08:10"))
    closed = MC5.to_5m(full)
    assert got.close == pytest.approx(
        float(closed.loc[et("2026-01-07 08:05").tz_convert("UTC"), "close"]))


def test_the_same_bars_give_the_two_strategies_different_answers():
    """If both adapters returned the same thing on the same frame, nothing
    here would be testing that they route to different code."""
    # Cut mid-bucket on purpose. At 08:08 with data to 08:07, MCL's last
    # CLOSED bar is 08:07 and MC5's last CLOSED bucket is 08:00 (ending
    # 08:04) -- the 08:05 one is still forming. Cutting on a bucket boundary
    # instead would make the two agree by arithmetic and test nothing.
    df = bars1m(400)
    df = df[df.index <= et("2026-01-07 08:07").tz_convert("UTC")]
    now = et("2026-01-07 08:08")
    mcl = A.mcl_adapter().evaluate(df, now)
    mc5 = A.mc5_adapter().evaluate(df, now)
    assert mcl is not None and mc5 is not None
    assert mcl.close != mc5.close, (
        "MCL reads the last 1-minute bar, MC5 the last closed 5-minute bucket")
    assert set(mcl.detail) != set(mc5.detail), (
        "different conditions, so different diagnostics in the fill log")


def test_a_cold_frame_gives_none_from_either():
    df = bars1m(10)
    now = et("2026-01-07 04:11")
    assert A.mcl_adapter().evaluate(df, now) is None
    assert A.mc5_adapter().evaluate(df, now) is None


# --- the registry -----------------------------------------------------------

def test_build_returns_the_strategy_that_was_asked_for():
    assert A.build("mcl").name == "MCL"
    assert A.build("mc5").name == "MC5"


def test_an_unknown_strategy_fails_loudly_and_says_what_is_available():
    with pytest.raises(SystemExit) as e:
        A.build("vw9")
    assert "mcl" in str(e.value) and "mc5" in str(e.value)


def test_build_all_preserves_order():
    """Order is not cosmetic: with a shared book and a concurrency cap, the
    strategy evaluated first takes the last free slot."""
    assert [a.name for a in A.build_all(["mc5", "mcl"])] == ["MC5", "MCL"]
    assert [a.name for a in A.build_all(["mcl", "mc5"])] == ["MCL", "MC5"]


def test_every_registered_key_maps_to_a_strategy_that_names_itself():
    for key in A.BUILDERS:
        a = A.build(key)
        assert a.name and a.name != "?"
        assert a.name.lower() == key


def test_the_adapter_exposes_no_more_than_the_live_path_needs():
    """Kept small on purpose. Every field added here is another thing the
    trader can read from the wrong strategy."""
    import dataclasses
    fields = {f.name for f in dataclasses.fields(A.StrategyAdapter)}
    assert fields == {
        "name", "module", "bar_minutes", "session_start", "session_end",
        "price_min", "price_max", "enforce_band", "trail_pct",
        "commission_plan", "_evaluate"}
