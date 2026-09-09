#!/usr/bin/env python3
"""Two strategies, one account, one cap.

Stage 4 of claude/multi_strategy_trader_spec.md, and the first stage that
changes behaviour rather than moving code.

H4: the position cap counts across every strategy, because the IB account is
shared. A cap that counted only its own would be two caps of two on an account
sized for two -- and the second strategy would be committing buying power the
first had already spent.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time as dtime

import pytest

from brokers.ibkr import trader as M
from common import strategy_adapter as SA


def state(sym, adapter, feed=None, position=None):
    st = M.SymbolState(symbol=sym, feed=feed, strategy=adapter)
    st.position = position
    return st


def a_position(sym="WYHG", trail=5.0):
    return M.Position(symbol=sym, qty=100, entry_price=5.82,
                      entry_time=datetime(2026, 9, 8, 8, 11, tzinfo=M.ET),
                      peak=6.00, trail_pct=trail)


class Book:
    """The parts of the trader the cap and the loop actually read."""

    def __init__(self, strategies):
        self.strategies = strategies
        self.states = {}
        self.feeds = {}


def book(strategies):
    """Bound to the real methods, not reimplementations of them. A stand-in
    that reimplemented in_session would pass while the trader's own version
    was wrong."""
    b = Book(strategies)
    b.feed_for = lambda sym: M.MCLPaperTrader.feed_for(b, sym)
    b.in_session = lambda now, a=None: M.MCLPaperTrader.in_session(b, now, a)
    b.any_session_open = lambda now: M.MCLPaperTrader.any_session_open(b, now)
    return b


# --- the states ------------------------------------------------------------

def test_one_symbol_carries_a_state_per_strategy_over_one_feed():
    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    b = book([mcl, mc5])
    feed = M.MCLPaperTrader.feed_for(b, "WYHG")
    a = state("WYHG", mcl, feed)
    c = state("WYHG", mc5, feed)
    b.states[(mcl.name, "WYHG")] = a
    b.states[(mc5.name, "WYHG")] = c

    assert len(b.states) == 2, "two strategies, two states"
    assert len(b.feeds) == 1, "one contract qualification and one data line"
    assert a.feed is c.feed


def test_the_symbols_view_collapses_the_two_states_to_one_name():
    """sync_watchlist subscribes to symbols not yet held. Keyed by (strategy,
    symbol), a naive `set(self.states)` would be tuples and every symbol would
    look missing on every poll -- re-subscribing forever, which is precisely
    how IB's pacing limit gets hit."""
    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    tr = M.MCLPaperTrader.__new__(M.MCLPaperTrader)
    tr.states = {(mcl.name, "WYHG"): None, (mc5.name, "WYHG"): None,
                 (mcl.name, "BNC"): None}
    assert tr.symbols == {"WYHG", "BNC"}


# --- the cap ---------------------------------------------------------------

def test_the_cap_counts_positions_from_every_strategy():
    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    states = {
        (mcl.name, "AAA"): state("AAA", mcl, position=a_position("AAA")),
        (mc5.name, "BBB"): state("BBB", mc5, position=a_position("BBB")),
        (mcl.name, "CCC"): state("CCC", mcl),
    }
    open_now = sum(1 for s in states.values() if s.position is not None)
    assert open_now == M.MAX_CONCURRENT_POSITIONS, (
        "one position each already fills a cap of two; a per-strategy count "
        "would read 1 and let a third open")


def test_the_same_symbol_held_by_two_strategies_counts_twice():
    """Two strategies both long WYHG is two positions and two lots of capital,
    even though it is one name and one data line."""
    mcl, mc5 = SA.mcl_adapter(), SA.mc5_adapter()
    feed = M.SymbolFeed(symbol="WYHG")
    states = {
        (mcl.name, "WYHG"): state("WYHG", mcl, feed, a_position()),
        (mc5.name, "WYHG"): state("WYHG", mc5, feed, a_position()),
    }
    assert sum(1 for s in states.values() if s.position) == 2


# --- sessions --------------------------------------------------------------

def test_each_strategy_is_asked_about_its_own_window():
    mcl = SA.mcl_adapter()
    b = book([mcl])
    inside = datetime(2026, 9, 8, 8, 0, tzinfo=M.ET)
    outside = datetime(2026, 9, 8, 10, 0, tzinfo=M.ET)
    assert b.in_session(inside, mcl) is True
    assert b.in_session(outside, mcl) is False


def test_the_loop_stays_awake_while_any_strategy_is_still_trading():
    """H5. MCL and MC5 both stop at 09:30 so this does not bite today; VW9
    runs to 20:00 and the loop must not stop under it."""
    mcl = SA.mcl_adapter()
    late = SA.mcl_adapter()
    object.__setattr__(late, "session_end", dtime(20, 0))
    object.__setattr__(late, "name", "LATE")

    at_ten = datetime(2026, 9, 8, 10, 0, tzinfo=M.ET)
    assert book([mcl]).any_session_open(at_ten) is False
    assert book([mcl, late]).any_session_open(at_ten) is True


def test_the_stop_time_is_the_latest_end_not_the_first():
    mcl = SA.mcl_adapter()
    late = SA.mcl_adapter()
    object.__setattr__(late, "session_end", dtime(20, 0))
    assert max(a.session_end for a in (mcl, late)) == dtime(20, 0)


# --- attribution -----------------------------------------------------------

def test_a_fill_row_names_the_strategy_that_produced_it():
    assert "strategy" in M.FIELDS
    st = state("WYHG", SA.mc5_adapter())
    assert M.MCLPaperTrader._name_of(st) == "MC5"


def test_an_unattributed_state_gets_a_blank_label_not_a_default():
    """Same rule notify.py applies: a row labelled with the WRONG strategy is
    worse than one labelled with none."""
    st = M.SymbolState(symbol="WYHG")
    assert M.MCLPaperTrader._name_of(st) == ""


def test_one_fill_file_not_one_per_strategy():
    """The account is shared, so only a single ledger reconciles against it --
    and a per-strategy file could not show two strategies competing for one
    cap."""
    assert M.FIELDS.index("strategy") == 1, (
        "second column, right after the timestamp, so a row is attributable "
        "at a glance")


# --- the refusal to guess --------------------------------------------------

def test_stepping_a_state_with_no_strategy_raises():
    """Rather than defaulting. A state attributed to the wrong strategy sizes,
    bands and trails against rules it never agreed to -- and every one of those
    constants matches between MCL and MC5 today, so it would look fine."""
    tr = M.MCLPaperTrader.__new__(M.MCLPaperTrader)
    st = M.SymbolState(symbol="WYHG")
    with pytest.raises(RuntimeError, match="no strategy attached"):
        asyncio.run(M.MCLPaperTrader.step_symbol(tr, st, datetime.now(M.ET)))


def test_the_adapters_the_live_trader_accepts_are_the_ones_main_allows():
    import main
    assert set(SA.BUILDERS) == set(main.LIVE_STRATEGIES), (
        "main.py gates --strategy on LIVE_STRATEGIES and the trader builds "
        "from BUILDERS; if they disagree, one of them is a lie")


# --- the trail the entry writes onto the position ---------------------------

def test_an_entry_takes_its_trail_from_the_adapter_not_the_module():
    """SURVIVED A MUTATION UNTIL THIS EXISTED.

    Replacing `trail_pct=st.strategy.trail_pct` with `trail_pct=S.TRAIL_PCT`
    at the entry site passed the whole suite, because MCL and MC5 are both at
    5.0 -- which is H2 exactly: the constants agreeing is what makes reading
    the wrong one invisible.

    So the adapter here is given a trail that matches NEITHER module, and the
    position must come out carrying it.
    """
    from tests.brokers.ibkr.test_dryrun_roundtrip import find_firing_series
    from tests.brokers.ibkr.test_live_paths import FakeTrade, build, feed

    df, _seed, spike = find_firing_series(140)
    assert df is not None, "no firing series; this test would be vacuous"

    odd = SA.mcl_adapter()
    object.__setattr__(odd, "trail_pct", 9.0)
    assert odd.trail_pct != M.S.TRAIL_PCT
    assert odd.trail_pct != SA.mc5_adapter().trail_pct

    tr, st, ib, log, out = build("trailsrc", [FakeTrade(100, 5.00, "Filled")])
    object.__setattr__(st, "strategy", odd)
    asyncio.run(feed(tr, st, [df.iloc[: spike + 1]]))
    log.close()

    assert st.position is not None, "the fixture did not produce an entry"
    assert st.position.trail_pct == 9.0, (
        "the position took its trail from a module instead of the strategy "
        "that entered it")
