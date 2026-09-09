#!/usr/bin/env python3
"""Chunking the universe pull.

Chunks decide two things that are expensive to get wrong: what is re-fetched
after a failure, and whether two chunks can cover the same bars twice.
"""
from __future__ import annotations

from common import databento_universe as U

# --- per-weekday windowed chunks --------------------------------------------
# Added 2026-09-09 for the screener simulation, which needs 04:00-09:30 ET and
# nothing else. Month chunks cannot express a time of day: a request from 04:00
# on the 1st to 09:30 on the 31st spans the whole 24-hour tape in between.

def test_a_windowed_chunk_covers_one_day_not_a_month():
    got = U.day_chunks("2026-08-03", "2026-08-08", "04:00-09:30")
    assert len(got) == 5, "Mon-Fri"
    _, lo, hi = got[0]
    assert lo == "2026-08-03T08:00:00" and hi == "2026-08-03T13:30:00"


def test_weekends_are_not_requested():
    """Every chunk costs a metadata round trip, and a Saturday buys nothing."""
    labels = [l for l, _, _ in U.day_chunks("2026-08-08", "2026-08-11",
                                            "04:00-09:30")]
    assert labels == ["2026-08-10_0400_0930"], "Sat and Sun dropped"


def test_the_label_carries_the_window():
    """THE CORRUPTION THIS PREVENTS. Chunks are skipped when the file already
    exists, so without the window in the name a later pull covering different
    hours would silently reuse the old bars -- and produce a plausible screen
    rather than an error."""
    a = U.day_chunks("2026-08-03", "2026-08-04", "04:00-09:30")[0][0]
    b = U.day_chunks("2026-08-03", "2026-08-04", "04:00-04:30")[0][0]
    assert a != b
    assert a.startswith("2026-08-03") and b.startswith("2026-08-03")


def test_windowed_chunks_never_overlap():
    """dbn_io.daily_frame warns on duplicate symbol-date rows precisely because
    an overlapping scheme would double volume and corrupt every relative-volume
    figure downstream."""
    got = U.day_chunks("2026-08-03", "2026-08-15", "04:00-09:30")
    for (_, _, hi), (_, lo2, _) in zip(got, got[1:]):
        assert hi <= lo2


def test_the_window_follows_daylight_saving():
    """A fixed offset would pull the wrong hours for five months of the year
    and return plausible bars rather than an error."""
    summer = U.day_chunks("2026-08-03", "2026-08-04", "04:00-09:30")[0][1]
    winter = U.day_chunks("2026-01-05", "2026-01-06", "04:00-09:30")[0][1]
    assert summer.endswith("T08:00:00") and winter.endswith("T09:00:00")


def test_no_window_still_chunks_by_month():
    """The daily archive was pulled this way and must stay reproducible."""
    got = U.month_chunks("2026-07-01", "2026-09-01")
    assert [l for l, _, _ in got] == ["2026-07", "2026-08"]
