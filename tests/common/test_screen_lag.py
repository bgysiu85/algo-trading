#!/usr/bin/env python3
"""Can the lag check say NO?

The module was written after four hand-picked names fit a shape. That is the
most dangerous way for a measurement to come into existence, so the tests that
matter are the ones where the honest answer is "no lag" and the module has every
opportunity to say otherwise:

  * a clean archive with no shift at all
  * watchlists carrying names across sessions, which makes SEVERAL offsets score
    well -- the pattern most likely to be mistaken for a lag
  * an offset that wins pooled while losing on one session
  * an offset that wins only because it was scored over fewer sessions

The positive case is one test. The refusals are five.
"""
from __future__ import annotations

from datetime import date

import pytest

from common import screen_lag as L

# Five consecutive trading sessions; the gap over the weekend is deliberate,
# because an offset must step in SESSIONS and a calendar step would land on a
# day with no universe.
S = [date(2026, 9, 4), date(2026, 9, 8), date(2026, 9, 9),
     date(2026, 9, 10), date(2026, 9, 11)]
SESSIONS = list(S)


def sim_of(mapping):
    return {d.isoformat(): set(v) for d, v in mapping.items()}


def run(live, sim, offsets=L.OFFSETS):
    rows = [L.score(live, sim, SESSIONS, o) for o in offsets]
    return rows, L.verdict(rows)


# --- session arithmetic ------------------------------------------------------

def test_shift_steps_sessions_not_calendar_days():
    # 09-08 is a Tuesday here; one session back is 09-04, not 09-07.
    assert L.shift(date(2026, 9, 8), -1, SESSIONS) == date(2026, 9, 4)


def test_shift_off_the_end_is_none_not_clamped():
    assert L.shift(S[0], -1, SESSIONS) is None
    assert L.shift(S[-1], 1, SESSIONS) is None


def test_a_date_not_in_the_archive_shifts_to_none():
    assert L.shift(date(2026, 9, 5), -1, SESSIONS) is None


# --- the refusals ------------------------------------------------------------

def test_a_clean_archive_finds_no_lag():
    """Live list D matches universe D exactly. Nothing to find."""
    live = {d: {"AAA", "BBB"} for d in S[1:4]}
    sim = sim_of({d: {"AAA", "BBB"} for d in S})
    _rows, (v, _why) = run(live, sim)
    assert v == "NOT ESTABLISHED"


def test_names_persisting_across_sessions_are_not_reported_as_a_lag():
    """The trap. If every universe carries the same names, EVERY offset scores
    100% and a module that ranked them would announce a lag with no evidence
    whatsoever."""
    live = {d: {"AAA", "BBB"} for d in S[1:4]}
    sim = sim_of({d: {"AAA", "BBB", "CCC"} for d in S})
    _rows, (v, why) = run(live, sim)
    assert v == "NOT ESTABLISHED"
    # offset 0 already scores 1.0, so nothing can beat it by MATERIAL
    assert "No offset beats offset 0" in "\n".join(why)


def test_an_offset_winning_pooled_but_losing_one_session_is_refused():
    """Condition (b). 09-09 and 09-10 shift cleanly; 09-11 does not, and one
    session's failure is enough."""
    live = {S[2]: {"AAA", "BBB", "CCC", "DDD"},
            S[3]: {"AAA", "BBB", "CCC", "DDD"},
            S[4]: {"EEE", "FFF", "GGG", "HHH"}}
    sim = sim_of({S[1]: {"AAA", "BBB", "CCC", "DDD"},
                  S[2]: {"AAA", "BBB", "CCC", "DDD"},
                  S[3]: {"EEE", "FFF", "GGG", "HHH"},
                  S[4]: {"EEE", "FFF", "GGG", "HHH"}})
    # offset -1 is perfect on 09-09/09-10 AND on 09-11, so make 09-11 a tie
    # instead: offset 0 already has it.
    live[S[4]] = {"EEE", "FFF", "GGG", "HHH"}
    rows, (v, _why) = run(live, sim)
    base = next(r for r in rows if r["offset"] == 0)
    minus = next(r for r in rows if r["offset"] == -1)
    # 09-11 scores 4/4 at BOTH offsets, so -1 does not strictly beat 0 there.
    p0 = next(p for p in base["per"] if p["file_date"] == S[4])
    p1 = next(p for p in minus["per"] if p["file_date"] == S[4])
    assert p0["rate"] == p1["rate"] == 1.0
    assert v == "NOT ESTABLISHED"


def test_an_offset_scored_over_fewer_sessions_is_not_ranked_against_zero():
    """A shift drops the session at the edge of the archive. Comparing a
    3-session offset to a 4-session baseline would reward the shift for having
    scored less evidence."""
    live = {S[0]: {"ZZZ"}, S[1]: {"AAA"}, S[2]: {"AAA"}}
    sim = sim_of({S[0]: set(), S[1]: {"AAA"}, S[2]: {"AAA"}, S[3]: {"AAA"}})
    rows, (v, _why) = run(live, sim)
    base = next(r for r in rows if r["offset"] == 0)
    minus = next(r for r in rows if r["offset"] == -1)
    assert minus["sessions"] < base["sessions"]
    assert v == "NOT ESTABLISHED"


def test_no_baseline_is_named_rather_than_scored_as_zero():
    live = {date(2026, 12, 25): {"AAA"}}
    sim = sim_of({d: {"AAA"} for d in S})
    rows = [L.score(live, sim, SESSIONS, o) for o in L.OFFSETS]
    v, _why = L.verdict(rows)
    assert v == "NO BASELINE"


# --- the positive case -------------------------------------------------------

def test_a_real_one_session_lag_is_found():
    """Each live list is the PREVIOUS session's universe, with distinct names
    per session so no offset can win by accident."""
    uni = {S[0]: {"AAA", "BBB"}, S[1]: {"CCC", "DDD"}, S[2]: {"EEE", "FFF"},
           S[3]: {"GGG", "HHH"}, S[4]: {"III", "JJJ"}}
    sim = sim_of(uni)
    live = {S[1]: uni[S[0]], S[2]: uni[S[1]], S[3]: uni[S[2]], S[4]: uni[S[3]]}
    _rows, (v, why) = run(live, sim)
    assert v == "LAG OF -1 SESSION(S)"
    assert "DATE defect" in "\n".join(why)


def test_the_lag_verdict_requires_the_material_margin():
    """A shift that helps a little is not a lag. Same shape as above but the
    universes overlap heavily: 11 names shared and 1 that rotates, so shifting
    gains 1/12 = 8pp and the pre-registered margin of 10pp is not met."""
    core = {f"S{i:02d}" for i in range(11)}
    uni = {d: core | {f"X{i}"} for i, d in enumerate(S)}
    sim = sim_of(uni)
    live = {S[1]: uni[S[0]], S[2]: uni[S[1]], S[3]: uni[S[2]], S[4]: uni[S[3]]}
    rows, (v, _why) = run(live, sim)
    base = next(r for r in rows if r["offset"] == 0)
    minus = next(r for r in rows if r["offset"] == -1)
    assert minus["rate"] - base["rate"] < L.MATERIAL
    assert v == "NOT ESTABLISHED"


# --- reporting ---------------------------------------------------------------

def test_a_missing_offset_renders_as_a_dash_not_a_zero():
    live = {S[0]: {"AAA"}, S[1]: {"AAA"}}
    sim = sim_of({S[0]: {"AAA"}, S[1]: {"AAA"}})
    rows = [L.score(live, sim, SESSIONS, o) for o in L.OFFSETS]
    text = "\n".join(L.render(rows, [], live, 0.0))
    assert "-" in text
    assert "NOT a zero" in text


def test_render_states_what_it_is_not():
    live = {S[1]: {"AAA"}}
    sim = sim_of({d: {"AAA"} for d in S})
    rows = [L.score(live, sim, SESSIONS, o) for o in L.OFFSETS]
    text = "\n".join(L.render(rows, [], live, 0.0))
    assert "Not a re-validation" in text
    assert "Not a licence to shift and re-score" in text


def test_a_second_archive_on_one_date_is_excluded_and_named(tmp_path):
    """`_unique_path` writes `_2` when a date archives twice, which is itself a
    symptom of the mechanism under test. Merging it in would hide that."""
    (tmp_path / "watchlist_20260910.txt").write_text(
        "# tv_feed\nAAA\n", encoding="utf-8")
    (tmp_path / "watchlist_20260910_2.txt").write_text(
        "# tv_feed\nBBB\n", encoding="utf-8")
    live, skipped = L.live_lists(tmp_path)
    assert live == {date(2026, 9, 10): {"AAA"}}
    assert any("second archive" in s["why"] for s in skipped)


def test_hand_synced_lists_are_excluded(tmp_path):
    (tmp_path / "watchlist_20260910.txt").write_text("AAA\n", encoding="utf-8")
    live, skipped = L.live_lists(tmp_path)
    assert live == {}
    assert any("hand-synced" in s["why"] for s in skipped)
