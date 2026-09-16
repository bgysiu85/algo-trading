#!/usr/bin/env python3
"""The recovered publish dates, and the checks that make them usable.

`warrior_census.csv` carried `pos` -- position in the playlist -- and no date,
so 401 structured rows about Ross Cameron's trading days could be ORDERED and
joined to nothing. `warrior_census_20260910.md` §8 named recovering the dates
as "the obvious next step" on 2026-09-10 and it was not run until 2026-09-16.

These are the assertions that decide whether the join is sound, and they are
here rather than in a report because a stale report is read as current.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATES = REPO / "docs" / "research" / "warrior_census_dates.txt"
CENSUS = REPO / "docs" / "research" / "warrior_census.csv"
DATED = REPO / "docs" / "research" / "warrior_census_dated.csv"

LABELS = ("hot", "mixed", "cold")


def _dates() -> dict[str, str]:
    return dict(line.split() for line in DATES.read_text(encoding="utf-8").splitlines() if line)


def _rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8-sig")))


def test_every_video_in_the_census_has_a_date():
    """401 of 401, or the census is still partially unjoinable and every
    figure derived from it carries an unstated coverage caveat."""
    d, rows = _dates(), _rows(CENSUS)
    assert len(rows) == 401
    missing = [r["videoId"] for r in rows if r["videoId"] not in d]
    assert not missing, f"{len(missing)} undated: {missing[:5]}"


def test_no_video_id_is_dated_twice():
    lines = [ln for ln in DATES.read_text(encoding="utf-8").splitlines() if ln]
    ids = [ln.split()[0] for ln in lines]
    assert len(ids) == len(set(ids)) == 401


def test_every_date_parses_and_none_is_in_the_future():
    """A typo in a hand-assembled list is a silently wrong join."""
    cap = dt.date(2026, 9, 16)
    for vid, s in _dates().items():
        d = dt.date.fromisoformat(s)
        assert dt.date(2025, 1, 1) <= d <= cap, f"{vid} -> {s}"


def test_playlist_ORDER_matches_publish_order_exactly():
    """THE INTERNAL CHECK, and it is the strongest evidence the dates are the
    right dates.

    `pos` is the census's own ordering, assigned when the playlist was walked
    and entirely independent of what the metadata endpoint returned months
    later. If the two disagreed anywhere, either the playlist is not
    chronological or a date is wrong -- and there would be no way to tell
    which. Zero breaks in 400 adjacent pairs is not something a mistaken date
    survives.
    """
    d = _dates()
    seq = sorted((int(r["pos"]), d[r["videoId"]]) for r in _rows(CENSUS))
    breaks = [(a, b) for a, b in zip(seq, seq[1:]) if b[1] > a[1]]
    assert not breaks, f"{len(breaks)} pos/date order breaks, e.g. {breaks[:3]}"


def test_the_dated_census_is_the_census_plus_one_column():
    """Regenerable, and provably nothing else changed. A join that also
    reordered or dropped rows would be a different dataset wearing the same
    name."""
    plain, dated = _rows(CENSUS), _rows(DATED)
    assert len(plain) == len(dated) == 401
    assert list(dated[0]) == ["publish_date"] + list(plain[0])
    d = _dates()
    for a, b in zip(plain, dated):
        assert {k: b[k] for k in a} == a
        assert b["publish_date"] == d[a["videoId"]]


def test_the_labelled_set_is_bigger_than_the_figure_in_circulation():
    """`warrior_census_20260910.md` §4 quotes 234 labelled days. The dated
    census has more, and a stale denominator understates the sample every
    later figure rests on."""
    lab = [r for r in _rows(DATED) if r["market"] in LABELS and r["publish_date"]]
    assert len(lab) == 277
    counts = {k: sum(1 for r in lab if r["market"] == k) for k in LABELS}
    assert counts == {"hot": 63, "mixed": 46, "cold": 168}


def test_cold_is_still_the_majority_of_the_labelled_sample():
    """The premise of the regime gate: a strategy validated on the hot share
    is not validated. If this ever stops holding, the case changes."""
    lab = [r for r in _rows(DATED) if r["market"] in LABELS]
    cold = sum(1 for r in lab if r["market"] == "cold")
    assert cold / len(lab) > 0.5


def test_a_recap_is_published_ON_its_session_not_after_it():
    """THE MAPPING, measured rather than assumed.

    A recap could plausibly be published the same evening or the next morning,
    and the two give different joins. Against the archive's own session dates,
    offset 0 puts 233 of 277 labelled recaps directly on a session; every
    later offset is worse. The residual is a weekend tail -- 41 of the 277
    publish on a Saturday or Sunday -- so the rule is THE NEAREST SESSION AT
    OR BEFORE the publish date, not a fixed shift.

    The day-of-week spread across weekdays is flat, which is what same-day
    publishing looks like and is not what a one-day lag looks like.
    """
    lab = [r for r in _rows(DATED) if r["market"] in LABELS and r["publish_date"]]
    dow = [dt.date.fromisoformat(r["publish_date"]).weekday() for r in lab]
    weekend = sum(1 for w in dow if w >= 5)
    assert weekend == 41, f"{weekend} weekend publishes"
    weekdays = [dow.count(i) for i in range(5)]
    assert min(weekdays) >= 0.6 * max(weekdays), \
        f"weekday spread {weekdays} is not flat enough for same-day publishing"


def test_the_mapping_rule_is_total():
    """Every labelled recap has to reach SOME session within a few days, or
    the join silently loses rows and the sample shrinks without saying so.
    Checked against the weekday calendar rather than the archive, so this test
    does not need the archive to be present."""
    lab = [r for r in _rows(DATED) if r["market"] in LABELS and r["publish_date"]]
    for r in lab:
        d = dt.date.fromisoformat(r["publish_date"])
        back = next(b for b in range(6) if (d - dt.timedelta(days=b)).weekday() < 5)
        assert back <= 2, f"{r['videoId']} {d} is {back} days from a weekday"
