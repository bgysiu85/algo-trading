#!/usr/bin/env python3
"""The bar cache, at every hour of the day including the awkward one.

2026-09-16. `tests/brokers/ibkr/test_pacing_and_trail.py` forced a cache miss
by setting `st.bars_minute = (0, 0)` and calling it an impossible value. It is
not impossible. It is midnight ET -- and midnight ET is early afternoon in
Australia, which is when this suite actually gets run.

So for one minute a day the check failed, and for the other 1,439 it passed.
That is the worst possible failure rate: often enough to be seen, rarely
enough to be dismissed as flaky and re-run.

**A sentinel that is also a legal value is not a sentinel**, which is the same
shape as a control whose output is indistinguishable from the failure it
detects. The test was wrong, not the trader -- `SymbolState.bars_minute`
defaults to None and production never writes (0, 0) -- but nothing in the
suite pinned the behaviour at a named hour, so nothing could have said so.

These do. The clock is supplied rather than observed, so each case is the same
assertion at a chosen time rather than a different assertion depending on when
it runs.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

import pytest

from brokers.ibkr import trader as M
from tests.brokers.ibkr.test_live_paths import build
from tests.brokers.ibkr.test_dryrun_roundtrip import find_firing_series


@pytest.fixture
def frozen(monkeypatch):
    """`bars()` reads `datetime.now(ET)`. Hand it the time instead.

    Patching the name on the module rather than the `datetime` class itself,
    so nothing outside this module's view of the clock moves.
    """
    def at(when: datetime):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return when
        monkeypatch.setattr(M, "datetime", Clock)
        return when
    return at


def a_trader(tag):
    tr, st, ib, log, out = build(tag, [])
    full, _, _ = find_firing_series(140)
    calls = {"n": 0}

    async def counting(_st):
        calls["n"] += 1
        return full

    tr._fetch_bars = counting
    return tr, st, log, calls


def prime(tr, st, calls, when):
    """One real fetch, so the cache holds bars and a stamped minute."""
    asyncio.run(tr.bars(st))
    assert calls["n"] == 1
    assert st.bars_minute == (when.hour, when.minute)


MIDNIGHT = datetime(2026, 9, 16, 0, 0, tzinfo=M.ET)
MIDDAY = datetime(2026, 9, 16, 12, 34, tzinfo=M.ET)


@pytest.mark.parametrize("hh,mm", [(0, 0), (12, 34), (23, 59), (0, 1), (9, 30)])
def test_a_new_minute_refreshes_at_EVERY_hour(frozen, hh, mm):
    """THE ONE THAT WOULD HAVE CAUGHT IT. (0, 0) is in the list on purpose.

    Whatever minute the cache was stamped with, the next minute must fetch.
    """
    tr, st, log, calls = a_trader(f"clk{hh}{mm}")
    first = frozen(datetime(2026, 9, 16, hh, mm, tzinfo=M.ET))
    prime(tr, st, calls, first)

    frozen(first.replace(minute=(mm + 1) % 60,
                         hour=(hh + (mm + 1) // 60) % 24))
    st.bars_fetched_at -= 999          # past the pacing floor
    asyncio.run(tr.bars(st))
    log.close()
    assert calls["n"] == 2, "a new wall-clock minute must re-request history"


def test_the_same_minute_does_not_refresh_at_midnight_either(frozen):
    """The other half. If the fix had been to ignore `bars_minute` entirely,
    the cache would be gone and IB's pacing limit would be hit within a
    minute -- 60 requests per 10 minutes, after which the strategy goes blind
    without being told."""
    tr, st, log, calls = a_trader("clksame")
    prime(tr, st, calls, frozen(MIDNIGHT))
    st.bars_fetched_at -= 999
    asyncio.run(tr.bars(st))
    log.close()
    assert calls["n"] == 1, "the same minute must be served from cache"


def test_the_pacing_floor_holds_even_across_a_minute_boundary(frozen):
    """BAR_MIN_INTERVAL_S is the hard floor, and it outranks the minute
    stamp. A symbol subscribed at 09:29:59 must not fetch twice in two
    seconds just because the clock rolled."""
    tr, st, log, calls = a_trader("clkfloor")
    prime(tr, st, calls, frozen(datetime(2026, 9, 16, 9, 29, tzinfo=M.ET)))
    frozen(datetime(2026, 9, 16, 9, 30, tzinfo=M.ET))
    st.bars_fetched_at = time.monotonic()      # just fetched
    asyncio.run(tr.bars(st))
    log.close()
    assert calls["n"] == 1


def test_the_cache_still_returns_data_and_not_None(frozen):
    """A cache hit that returned None would blind the strategy in exactly the
    way the cache exists to prevent."""
    tr, st, log, calls = a_trader("clkdata")
    prime(tr, st, calls, frozen(MIDDAY))
    st.bars_fetched_at -= 999
    df = asyncio.run(tr.bars(st))
    log.close()
    assert df is not None and not df.empty


def test_the_unfetched_sentinel_is_not_a_wall_clock_minute():
    """`SymbolState.bars_minute` starts as None rather than (0, 0).

    None cannot equal `(now.hour, now.minute)` at any instant. A tuple can,
    and that is the whole bug above -- so this pins the default rather than
    leaving the next person free to pick a 'safe-looking' pair.
    """
    st = M.SymbolState(symbol="X", strategy=None)
    assert st.bars_minute is None
    now = datetime.now(M.ET)
    assert st.bars_minute != (now.hour, now.minute)


def test_a_first_fetch_happens_whatever_the_clock_says(frozen):
    """With no bars yet, the minute stamp must be irrelevant. Otherwise a
    symbol subscribed at 00:00 would never get its first history request."""
    tr, st, log, calls = a_trader("clkfirst")
    frozen(MIDNIGHT)
    st.bars_minute = (0, 0)            # the value that used to mean 'never'
    asyncio.run(tr.bars(st))
    log.close()
    assert calls["n"] == 1, "no bars in hand means fetch, whatever the stamp"
