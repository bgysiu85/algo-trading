#!/usr/bin/env python3
"""What is shared per SYMBOL and what is private per STRATEGY.

Stage 3 of claude/multi_strategy_trader_spec.md.

H3: qualifying a contract is an IB request and IB paces them account-wide at
~60 per 10 minutes -- signalling the limit by returning EMPTY LISTS rather than
errors -- and a streaming data line is one of about a hundred. Two strategies
watching one name must not spend two of each.

H2: Position.trail_level() read S.TRAIL_PCT, a module global. MCL and MC5 are
both at 5.0 today, so a position exiting on the wrong strategy's trail is
invisible until one of them changes.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from brokers.ibkr import trader as M


def test_a_state_without_a_feed_makes_its_own():
    """Every existing caller constructs SymbolState(symbol=...) and nothing
    else. That has to keep working -- the suite is this refactor's control."""
    st = M.SymbolState(symbol="TEST")
    assert st.feed is not None
    assert st.feed.symbol == "TEST"


def test_two_strategies_on_one_symbol_share_one_feed():
    feed = M.SymbolFeed(symbol="WYHG")
    a = M.SymbolState(symbol="WYHG", feed=feed)
    b = M.SymbolState(symbol="WYHG", feed=feed)

    a.contract = object()
    a.ticker = object()
    a.min_tick = 0.01
    assert b.contract is a.contract, "one contract qualification, not two"
    assert b.ticker is a.ticker, "one market-data line, not two"
    assert b.min_tick == 0.01


def test_a_name_ibkr_refuses_is_refused_for_every_strategy():
    """Blocked is a fact about the SYMBOL. Rediscovering it per strategy costs
    a rejected order to learn the same thing twice."""
    feed = M.SymbolFeed(symbol="JLHL")
    a, b = (M.SymbolState(symbol="JLHL", feed=feed) for _ in range(2))
    a.blocked = True
    assert b.blocked is True


def test_the_bar_cache_is_shared_because_both_strategies_want_1m_bars():
    """MC5 resamples its own 5-minute buckets from these, so one fetch serves
    both. A per-strategy cache would double the history requests for
    byte-identical data."""
    feed = M.SymbolFeed(symbol="WYHG")
    a, b = (M.SymbolState(symbol="WYHG", feed=feed) for _ in range(2))
    a.bars_df = "frame"
    a.bars_minute = (8, 11)
    a.bars_fetched_at = 123.0
    assert (b.bars_df, b.bars_minute, b.bars_fetched_at) == ("frame", (8, 11), 123.0)


def test_positions_are_private_to_a_strategy():
    """The one thing that must NOT be shared. Two strategies holding the same
    name hold two positions, and a shared one would let either close the
    other's."""
    feed = M.SymbolFeed(symbol="WYHG")
    a, b = (M.SymbolState(symbol="WYHG", feed=feed) for _ in range(2))
    a.position = M.Position(symbol="WYHG", qty=100, entry_price=5.82,
                            entry_time=datetime(2026, 9, 8, 8, 11, tzinfo=M.ET),
                            peak=5.82)
    assert b.position is None


def test_bar_bookkeeping_and_retirement_are_private_too():
    """last_bar_ts is 'this strategy has evaluated this bar'. Sharing it would
    let one strategy's evaluation suppress the other's."""
    feed = M.SymbolFeed(symbol="WYHG")
    a, b = (M.SymbolState(symbol="WYHG", feed=feed) for _ in range(2))
    a.last_bar_ts = datetime(2026, 9, 8, 8, 11, tzinfo=M.ET)
    a.retired = True
    assert b.last_bar_ts is None
    assert b.retired is False


def test_every_shared_field_is_delegated_in_both_directions():
    """Reading through the state and writing through the feed must agree, or a
    caller that sets one and reads the other sees stale data."""
    feed = M.SymbolFeed(symbol="X")
    st = M.SymbolState(symbol="X", feed=feed)
    for name in M._FEED_FIELDS:
        setattr(feed, name, "via-feed")
        assert getattr(st, name) == "via-feed", name
        setattr(st, name, "via-state")
        assert getattr(feed, name) == "via-state", name


def test_the_shared_field_list_matches_what_the_feed_actually_holds():
    """_FEED_FIELDS drives the property pairs. If it drifted from SymbolFeed,
    a field would silently stop being shared."""
    import dataclasses
    held = {f.name for f in dataclasses.fields(M.SymbolFeed)} - {"symbol"}
    assert held == set(M._FEED_FIELDS)


def test_no_shared_field_is_also_a_state_field():
    """A dataclass field would shadow the property and break the sharing
    without any error."""
    import dataclasses
    own = {f.name for f in dataclasses.fields(M.SymbolState)}
    assert own & set(M._FEED_FIELDS) == set()


# --- the trail travels with the position ------------------------------------

def pos(peak=100.0, **kw):
    return M.Position(symbol="T", qty=100, entry_price=90.0,
                      entry_time=datetime(2026, 9, 8, 8, 11, tzinfo=M.ET),
                      peak=peak, **kw)


def test_the_trail_comes_from_the_position_not_a_module():
    assert pos(trail_pct=10.0).trail_level() == pytest.approx(90.0)
    assert pos(trail_pct=5.0).trail_level() == pytest.approx(95.0)


def test_two_positions_can_carry_different_trails_at_once():
    """H2 in one line. This is what a shared module global cannot do."""
    a, b = pos(trail_pct=5.0), pos(trail_pct=12.0)
    assert a.trail_level() != b.trail_level()


def test_changing_the_module_does_not_move_an_open_position_s_trail(monkeypatch):
    """A position entered under one trail must keep it. Reading the module at
    EXIT time means a config change mid-session silently re-prices every stop
    already on the book."""
    p = pos(trail_pct=5.0)
    before = p.trail_level()
    monkeypatch.setattr(M.S, "TRAIL_PCT", 25.0)
    assert p.trail_level() == before


def test_the_default_is_mcls_so_the_refactor_changed_no_behaviour():
    """Stage 3 is a pure refactor: every pre-existing caller constructs a
    Position without a trail and must get exactly what it got before. Stage 4
    removes the default once every caller is strategy-aware."""
    assert pos().trail_pct == M.S.TRAIL_PCT


def test_asking_twice_for_a_symbols_feed_returns_the_same_one():
    """SURVIVED A MUTATION UNTIL THIS EXISTED. With one strategy _subscribe
    runs once per symbol, so building a fresh feed each call is
    indistinguishable -- and would duplicate the contract qualification and the
    data line the moment a second strategy arrived."""
    from types import SimpleNamespace
    tr = SimpleNamespace(feeds={})
    a = M.MCLPaperTrader.feed_for(tr, "WYHG")
    b = M.MCLPaperTrader.feed_for(tr, "WYHG")
    assert a is b
    assert M.MCLPaperTrader.feed_for(tr, "BNC") is not a
    assert set(tr.feeds) == {"WYHG", "BNC"}
