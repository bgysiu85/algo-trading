#!/usr/bin/env python3
"""The ranker's memory must not outlive the session it describes.

`Ranking`'s docstring said "session-scoped memory" and nothing in it knew what
a session was. A process spanning midnight carried yesterday's names into
today's watchlist as COLD, and the trader arms every name in the file.

    09-09 file: ... | BNC WYHG                 <- 09-08's names
    09-10 file: ... | BIAF RML ODD SUNE IRD    <- 09-09's names

Five of 09-10's seven `screen_validate` "misses" were that carry-over. The
simulation was right about all five.

The tests that matter are the pair: a roll must CLEAR, and a poll inside one
session must NOT -- because Ben's rule is "do not remove but deprioritise", and
a fix that forgot within a session would break the thing the ranker is for.
"""
from __future__ import annotations

from datetime import date

import pytest

from common.tv_feed import Ranking


def row(t, px=5.0):
    return {"ticker": t, "premarket_close": px, "close": px}


D1, D2 = date(2026, 9, 9), date(2026, 9, 10)


# --- the carry-over ----------------------------------------------------------

def test_a_new_session_drops_yesterdays_names():
    r = Ranking()
    r.begin_session(D1)
    r.update([row("BIAF"), row("RML")])
    assert set(r.ever) == {"BIAF", "RML"}

    r.begin_session(D2)
    assert r.ever == {}, "yesterday's names survived into a new session"
    out = r.update([row("ACVA")])
    assert out == ["ACVA"]
    assert "BIAF" not in out and "RML" not in out


def test_the_roll_is_reported_so_it_is_not_silent():
    r = Ranking()
    r.begin_session(D1)
    r.update([row("BIAF")])
    assert r.begin_session(D2) is True


def test_the_first_session_is_not_reported_as_a_roll():
    """Starting up is not a carry-over, and logging it as one would train the
    reader to ignore the line."""
    r = Ranking()
    assert r.begin_session(D1) is False


def test_an_empty_session_rolls_without_claiming_it_cleared_anything():
    r = Ranking()
    r.begin_session(D1)
    assert r.begin_session(D2) is False


# --- what must NOT change ----------------------------------------------------

def test_within_one_session_a_name_that_stops_screening_is_KEPT():
    """Ben, 2026-09-05: do not remove, deprioritise. A fix that forgot inside
    the session would orphan a held position."""
    r = Ranking()
    r.begin_session(D1)
    r.update([row("BIAF"), row("RML")])
    out = r.update([row("BIAF")])
    assert out == ["BIAF", "RML"], "RML must survive as COLD, just later"


def test_repeated_polls_in_one_session_never_roll():
    r = Ranking()
    r.begin_session(D1)
    r.update([row("BIAF")])
    for _ in range(10):
        assert r.begin_session(D1) is False
    assert set(r.ever) == {"BIAF"}


def test_cold_ordering_is_still_most_recent_first():
    r = Ranking()
    r.begin_session(D1)
    r.update([row("AAA")], now=100.0)
    r.update([row("BBB")], now=200.0)
    out = r.update([row("CCC")], now=300.0)
    assert out == ["CCC", "BBB", "AAA"]


def test_the_size_cap_still_takes_from_the_cold_end():
    r = Ranking(max_symbols=2)
    r.begin_session(D1)
    r.update([row("AAA")], now=100.0)
    r.update([row("BBB")], now=200.0)
    out = r.update([row("CCC")], now=300.0)
    assert out == ["CCC", "BBB"]


# --- the caller --------------------------------------------------------------

def test_the_loop_rolls_before_it_tiers():
    """`tiers()` runs before `update()` on every poll. A roll hidden inside
    `update` would report one tiering and write another, so the call order in
    the loop is part of the fix."""
    import inspect
    from common import tv_feed
    src = inspect.getsource(tv_feed._loop)
    i_begin = src.index("rank.begin_session(")
    i_tiers = src.index("rank.tiers(")
    i_update = src.index("rank.update(")
    assert i_begin < i_tiers < i_update
