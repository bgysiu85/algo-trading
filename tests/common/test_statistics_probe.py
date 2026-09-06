#!/usr/bin/env python3
"""The probe has to survive a record shape nobody here has seen.

It was written without a single statistics record to look at, so the tests pin
the two things that matter: the arithmetic the decision turns on, and that an
unexpected shape produces a report rather than a traceback.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from common import statistics_probe as P


# --- naming stat types ------------------------------------------------------

def test_a_known_stat_type_is_named():
    assert "CLEARED_VOLUME" in P.stat_type_name(6)
    assert "(6)" in P.stat_type_name(6)


def test_an_unknown_stat_type_is_reported_not_dropped():
    """A code this build of databento_dbn has never heard of is a finding --
    it means the dataset publishes something the enum does not cover. Silently
    dropping it would hide exactly the surprise worth knowing about."""
    assert P.stat_type_name(31337) == "UNKNOWN (31337)"


def test_a_non_numeric_stat_type_does_not_raise():
    assert P.stat_type_name("weird") == "weird"


# --- choosing what to sample ------------------------------------------------

def test_symbols_come_from_the_busiest_day_in_the_pair_list(tmp_path):
    """Sampling real screened candidates matters: MCL trades sub-$20 small
    caps, and whether the venue publishes statistics for THOSE is the whole
    question. A hand-picked large cap would answer a different one."""
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": "AAA", "date": "2026-08-04"},
               {"symbol": "BBB", "date": "2026-08-04"},
               {"symbol": "CCC", "date": "2026-08-04"},
               {"symbol": "ZZZ", "date": "2026-08-05"}], open(p, "w"))
    day, syms = P.pick_symbols(p, 2)
    assert day == "2026-08-04"
    assert syms == ["AAA", "BBB"]


def test_an_empty_pair_list_is_an_error(tmp_path):
    p = tmp_path / "pairs.json"
    json.dump([], open(p, "w"))
    with pytest.raises(SystemExit, match="no pairs"):
        P.pick_symbols(p, 5)


# --- the arithmetic that decides --------------------------------------------

def frame(stat_types, symbols):
    return pd.DataFrame({"stat_type": stat_types, "symbol": symbols,
                         "price": [1.0] * len(stat_types)})


def test_the_scoped_projection_is_per_symbol_day_times_the_screened_universe():
    """This is the number the decision turns on. 20 KB across 5 symbols is
    4 KB per symbol-day, which over 12,128 screened symbol-days is ~48.5 MB --
    trivially worth taking. Get this arithmetic wrong in either direction and
    the conclusion flips."""
    df = frame([6, 11, 6], ["AAA", "AAA", "BBB"])
    out = "\n".join(P.summarise(df, "2026-08-04",
                                ["AAA", "BBB", "CCC", "DDD", "EEE"], 20_000))
    assert "4,000" in out                      # bytes per symbol-day
    assert "48.5 MB" in out


def test_an_empty_result_is_reported_as_a_finding_not_a_crash():
    """No statistics for these symbols is itself the answer, and it must not
    divide by zero or read as a broken run."""
    out = "\n".join(P.summarise(frame([], []), "2026-08-04", ["AAA"], 0))
    assert "NOTHING CAME BACK" in out


def test_stat_types_are_counted_with_their_symbol_coverage():
    df = frame([6, 6, 11], ["AAA", "BBB", "AAA"])
    out = "\n".join(P.summarise(df, "2026-08-04", ["AAA", "BBB"], 1000))
    assert "CLEARED_VOLUME" in out and "CLOSE_PRICE" in out


def test_a_frame_without_stat_type_says_so_instead_of_raising():
    """Written against a record shape nobody here has seen. A missing column
    must produce a report saying which columns DID arrive -- that is the
    measurement -- rather than a traceback that reports nothing."""
    df = pd.DataFrame({"mystery": [1, 2], "symbol": ["AAA", "BBB"]})
    out = "\n".join(P.summarise(df, "2026-08-04", ["AAA", "BBB"], 1000))
    assert "no stat_type column" in out
    assert "mystery" in out


def test_unmapped_symbols_are_called_out_loudly():
    """An ALL_SYMBOLS-style mapping failure once produced '864 symbol-days, 0
    distinct symbols' and exit code 0. Every per-symbol figure here would be
    meaningless in that state, so it says so rather than printing zeroes."""
    df = pd.DataFrame({"stat_type": [6], "symbol": [None]})
    out = "\n".join(P.summarise(df, "2026-08-04", ["AAA"], 1000))
    assert "SYMBOLS DID NOT MAP" in out


def test_days_outside_the_dataset_range_are_excluded_when_sampling(tmp_path):
    """The screened list starts 2023-03-28, from EQUS.MINI. EQUS.SUMMARY only
    begins 2024-07-01, so the busiest day in the list is quite likely one this
    dataset has never heard of -- and the request would fail with a range error
    that reads like a broken tool rather than a mis-chosen day."""
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": "OLD1", "date": "2023-05-01"},
               {"symbol": "OLD2", "date": "2023-05-01"},
               {"symbol": "OLD3", "date": "2023-05-01"},   # busiest overall
               {"symbol": "NEW1", "date": "2025-02-03"},
               {"symbol": "NEW2", "date": "2025-02-03"}], open(p, "w"))
    day, syms = P.pick_symbols(p, 5, not_before="2024-07-01", not_after="2026-09-05")
    assert day == "2025-02-03"
    assert syms == ["NEW1", "NEW2"]


def test_a_pair_list_entirely_outside_the_range_says_which_window_was_empty(tmp_path):
    p = tmp_path / "pairs.json"
    json.dump([{"symbol": "OLD", "date": "2023-05-01"}], open(p, "w"))
    with pytest.raises(SystemExit, match="2024-07-01"):
        P.pick_symbols(p, 5, not_before="2024-07-01")


def test_the_dataset_range_reader_tolerates_both_key_spellings():
    """get_dataset_range has returned 'start'/'end' and 'start_date'/'end_date'
    across versions; databento_probe already handles both and this must not
    diverge from it."""
    class C:
        class metadata:
            @staticmethod
            def get_dataset_range(ds):
                return {"start_date": "2024-07-01T00:00:00", "end_date": "2026-09-05"}
    assert P.dataset_range(C, "EQUS.SUMMARY") == ("2024-07-01", "2026-09-05")
