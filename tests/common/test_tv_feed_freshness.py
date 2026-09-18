#!/usr/bin/env python3
"""H-F1: the first poll of a session must not arm yesterday's screen.

REGISTERED_feed_freshness.md. TradingView holds the previous session's
`premarket_*` values until today's prints arrive, so `tv_feed`'s first poll
returns yesterday's screen as ordinary live rows -- stamped at 04:00:05,
04:00:06, 04:00:08 and 04:00:26 on four sessions, and eighteen live names over
seven sessions that `screen_validate` had to set aside.

The rule: a name may not reach the watchlist until its premarket_volume has
been seen to CHANGE within the session.

Two halves, and the second matters more than the first. The gate must WITHHOLD
a stale row -- and it must be incapable of removing a name already in the file,
because the trader holds positions in those names and Ben's rule since
2026-09-05 is "do not remove but deprioritise".
"""
from __future__ import annotations

import inspect
import math
from datetime import date

import pytest

from common import tv_feed
from common.tv_feed import Freshness, Ranking
from common.tv_screener import VOLUME_COLUMN

D1, D2 = date(2026, 9, 9), date(2026, 9, 10)


def row(t, vol, px=5.0):
    return {"ticker": t, "symbol": f"NASDAQ:{t}", "premarket_close": px,
            VOLUME_COLUMN: vol}


def tickers(rows):
    return [r["ticker"] for r in rows]


# --- the defect --------------------------------------------------------------

def test_a_name_is_withheld_until_its_volume_moves():
    """The whole rule, in one test. First sight proves nothing -- the number
    could be yesterday's."""
    f = Freshness()
    f.begin_session(D1)

    out, held = f.admit([row("BIAF", 480_000)])
    assert out == [], "a first sighting reached the watchlist"
    assert held == ["BIAF"]

    out, held = f.admit([row("BIAF", 480_000)])
    assert out == [], "an unchanged volume is still yesterday's number"
    assert held == [], "the hold is logged once, not on every poll"

    out, held = f.admit([row("BIAF", 502_000)])
    assert tickers(out) == ["BIAF"], "a moved volume must be admitted"


def test_the_carry_over_is_withheld_while_a_live_name_gets_through():
    """The shape of a real 04:00 poll: yesterday's names sitting at yesterday's
    numbers, beside a name that is actually trading today."""
    f = Freshness()
    f.begin_session(D2)
    stale = [row("BIAF", 480_000), row("RML", 1_250_000)]
    live = row("VEEA", 120_000)

    out, _ = f.admit(stale + [live])
    assert out == []

    out, _ = f.admit([row("BIAF", 480_000), row("RML", 1_250_000),
                      row("VEEA", 143_500)])
    assert tickers(out) == ["VEEA"], "only the name that printed may arm"


def test_a_volume_that_FALLS_is_a_change_too():
    """Yesterday's cumulative volume is usually LARGER than today's first
    prints, so the common real case is a decrease. A rule written as `>` would
    withhold exactly the names it is meant to release."""
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 4_800_000)])          # yesterday's full pre-market
    out, _ = f.admit([row("BIAF", 118_000)])   # today's first prints
    assert tickers(out) == ["BIAF"]


def test_admission_is_permanent_for_the_session():
    """Once a name has proven itself today it is never re-gated -- including on
    a poll where its volume happens not to have moved."""
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("VEEA", 120_000)])
    f.admit([row("VEEA", 143_500)])
    for _ in range(5):
        out, held = f.admit([row("VEEA", 143_500)])
        assert tickers(out) == ["VEEA"]
        assert held == []
    # An admitted name is no longer HELD, and the file header reports len(held).
    # Without this the count drifts up all session and the one number that says
    # whether the gate is stuck becomes unreadable.
    assert f.held == set()


def test_a_volume_that_returns_to_its_baseline_stays_admitted():
    """WHY `admitted` IS A SET AND NOT JUST `vol != baseline`.

    The comparison alone is almost equivalent, because pre-market volume is
    cumulative and rarely revisits a value. Almost: yesterday's baseline is a
    number today's cumulative volume passes THROUGH, and on the poll where they
    coincide the comparison rule would withhold a name the trader may already
    hold a position in. Admission has to be a fact that is remembered, not a
    condition that is re-evaluated.
    """
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 480_000)])            # yesterday's cumulative volume
    out, _ = f.admit([row("BIAF", 118_000)])   # today's first prints
    assert tickers(out) == ["BIAF"]
    out, _ = f.admit([row("BIAF", 480_000)])   # today's volume passes through it
    assert tickers(out) == ["BIAF"], "an admitted name was retracted"


# --- the safety property -----------------------------------------------------

def test_the_gate_can_delay_a_name_but_never_remove_one(  # noqa: D103
):
    """THE PROPERTY THAT MAKES THIS SAFE. The trader holds positions in these
    names; a gate that could retract one would orphan a position, which is the
    thing the three-tier ranking exists to prevent.

    Run a session's worth of polls with volumes moving and stalling at random,
    and assert the admitted set only ever grows.
    """
    import random
    rng = random.Random(20260918)
    f = Freshness()
    f.begin_session(D1)
    names = [f"S{i}" for i in range(12)]
    vols = {n: rng.randrange(100_000, 900_000) for n in names}

    seen: set[str] = set()
    for _ in range(200):
        for n in names:
            if rng.random() < 0.3:
                vols[n] += rng.randrange(1, 5_000)
        out, _ = f.admit([row(n, vols[n]) for n in names])
        got = set(tickers(out))
        assert seen <= got, f"a previously admitted name was withheld: {seen - got}"
        seen |= got
    assert seen, "nothing was ever admitted -- the fixture never moved"


def test_a_held_name_is_withheld_ENTIRELY_and_not_demoted_to_cold():
    """COLD is an ordering, not a veto: the trader arms every symbol in the
    file. A stale name written as COLD is a stale name that gets armed.

    So the gate runs BEFORE the ranker, and a held name never enters `ever`.
    """
    f, r = Freshness(), Ranking()
    f.begin_session(D2)
    r.begin_session(D2)

    out, _ = f.admit([row("BIAF", 480_000), row("VEEA", 120_000)])
    r.tiers(out)
    symbols = r.update(out)
    assert symbols == []
    assert r.ever == {}, "a withheld name entered the ranker's memory"

    out, _ = f.admit([row("BIAF", 480_000), row("VEEA", 143_500)])
    assert r.update(out) == ["VEEA"]
    assert "BIAF" not in r.ever


# --- the rows that cannot be compared ----------------------------------------

@pytest.mark.parametrize("bad", [None, "480000", float("nan"), True])
def test_a_volume_that_cannot_be_compared_is_never_admitted(bad):
    """A row that cannot be shown to have moved has not been shown to have
    moved. NaN is the one that bites: `nan != nan` is True, so an unguarded
    comparison reads it as "changed" and admits the row.
    """
    f = Freshness()
    f.begin_session(D1)
    for _ in range(3):
        out, _ = f.admit([row("BIAF", bad)])
        assert out == []


def test_nan_does_not_release_a_name_that_was_held():
    """The specific failure: a real baseline, then a NaN. `nan != 480_000` is
    True, so the naive rule admits it."""
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 480_000)])
    out, _ = f.admit([row("BIAF", float("nan"))])
    assert out == [], "NaN was read as a change"


def test_the_volume_reader_is_not_fooled_by_a_bool():
    assert Freshness._volume({VOLUME_COLUMN: True}) is None
    assert Freshness._volume({VOLUME_COLUMN: 5}) == 5.0
    assert Freshness._volume({}) is None
    assert Freshness._volume({VOLUME_COLUMN: float("nan")}) is None


# --- the session roll --------------------------------------------------------

def test_a_new_session_clears_the_evidence():
    """Yesterday's ADMISSION must not admit a name today -- that would be the
    original defect wearing the fix's clothes."""
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 480_000)])
    f.admit([row("BIAF", 502_000)])
    assert "BIAF" in f.admitted

    f.begin_session(D2)
    assert f.admitted == set() and f.first_volume == {}
    out, _ = f.admit([row("BIAF", 502_000)])
    assert out == [], "yesterday's admission survived the roll"


def test_polls_inside_one_session_do_not_roll():
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 480_000)])
    for _ in range(10):
        assert f.begin_session(D1) is False
    assert f.first_volume == {"BIAF": 480_000.0}


def test_the_first_session_is_not_reported_as_a_roll():
    f = Freshness()
    assert f.begin_session(D1) is False


def test_a_roll_with_something_to_clear_reports_it():
    f = Freshness()
    f.begin_session(D1)
    f.admit([row("BIAF", 480_000)])
    assert f.begin_session(D2) is True


# --- the caller --------------------------------------------------------------

def test_the_loop_gates_before_it_tiers_and_gives_both_the_same_rows():
    """The ordering trap this module already documents for the session roll:
    `tiers()` runs before `update()`, so a filter applied inside one of them
    would report one tiering and write another. The gate must sit above both.
    """
    src = inspect.getsource(tv_feed._loop)
    i_roll = src.index("fresh.begin_session(")
    i_admit = src.index("fresh.admit(")
    i_tiers = src.index("rank.tiers(")
    i_update = src.index("rank.update(")
    assert i_roll < i_admit < i_tiers < i_update


def test_the_loop_actually_holds_a_stale_row_end_to_end(monkeypatch, tmp_path):
    """The gap a unit test on Freshness leaves: the class can be perfect and
    never be called. Drive `_loop` with a canned endpoint over two polls and
    read the file the trader would read.
    """
    polls = [
        [row("BIAF", 480_000), row("VEEA", 120_000)],   # 04:00:05, both unproven
        [row("BIAF", 480_000), row("VEEA", 143_500)],   # VEEA printed
    ]
    calls = {"n": 0}

    def fake_fetch(limit=None):
        i = min(calls["n"], len(polls) - 1)
        calls["n"] += 1
        return [dict(r) for r in polls[i]]

    monkeypatch.setattr(tv_feed, "fetch", fake_fetch)
    out = tmp_path / "watchlist.txt"
    args = tv_feed.build_parser().parse_args(
        ["--once", "--all-hours", "--out", str(out), "--no-telegram",
         "--heartbeat", "0"])

    rank, fresh = tv_feed.Ranking(), tv_feed.Freshness()
    tg = tv_feed.notify.Notifier()
    assert tv_feed._loop(args, rank, fresh, tg, set(), 0.0, 0.0) == 0
    written = [ln for ln in out.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.startswith("#")]
    assert written == [], f"the first poll armed {written}"

    assert tv_feed._loop(args, rank, fresh, tg, set(), 0.0, 0.0) == 0
    text = out.read_text(encoding="utf-8")
    written = [ln for ln in text.splitlines()
               if ln.strip() and not ln.startswith("#")]
    assert written == ["VEEA"], written
    # BIAF is still held, VEEA no longer is. A count that only ever rises can
    # never say whether the gate is stuck.
    assert "held=1" in text.splitlines()[0], text.splitlines()[0]


def test_the_header_reports_how_many_are_held(monkeypatch, tmp_path):
    """A hold that is invisible in the file is a hold nobody will notice on the
    morning it is wrong."""
    monkeypatch.setattr(tv_feed, "fetch",
                        lambda limit=None: [row("BIAF", 480_000),
                                            row("RML", 1_250_000)])
    out = tmp_path / "watchlist.txt"
    args = tv_feed.build_parser().parse_args(
        ["--once", "--all-hours", "--out", str(out), "--no-telegram",
         "--heartbeat", "0"])
    tv_feed._loop(args, tv_feed.Ranking(), tv_feed.Freshness(),
                  tv_feed.notify.Notifier(), set(), 0.0, 0.0)
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert "held=2" in header, header


def test_the_column_is_read_from_the_screener_not_restated():
    """A second copy of the string is a second source of truth. If the screen's
    volume column is ever renamed, this gate must follow it or it silently
    stops gating -- every row would read None and every name would be held.
    """
    src = inspect.getsource(tv_feed.Freshness)
    assert '"premarket_volume"' not in src and "'premarket_volume'" not in src
    assert "VOLUME_COLUMN" in src
    import common.tv_screener as tvs
    assert any(f["left"] == tvs.VOLUME_COLUMN for f in tvs.FILTERS)
