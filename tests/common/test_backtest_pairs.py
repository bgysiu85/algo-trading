#!/usr/bin/env python3
"""backtest.load_pairs takes several lists, and unions them.

THE BUG THESE REPLACE, 2026-09-07
---------------------------------
The first version of this file tested `databento_fetch.load_pairs`, which
already took a list. The function the backtest actually calls is
`backtest.load_pairs` -- a DIFFERENT function with the same name in a different
module, which still took a single Path. Every test passed and the real command
died on the first line it reached:

    AttributeError: 'list' object has no attribute 'read_text'

Two functions, one name. A test has to import the one the entry point calls.
"""
from __future__ import annotations

import json

from common.backtest import load_pairs


def write(p, pairs):
    p.write_text(json.dumps([{"symbol": s, "date": d} for s, d in pairs]))
    return p


def keys(rows):
    return [(r["symbol"], r["date"]) for r in rows]


def test_a_single_path_still_works(tmp_path):
    """Every existing caller passes one Path. That signature must keep working
    while the new one is added."""
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    assert keys(load_pairs(a)) == [("AAA", "2026-03-16")]


def test_a_single_path_as_a_string_works(tmp_path):
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    assert keys(load_pairs(str(a))) == [("AAA", "2026-03-16")]


def test_two_lists_are_unioned(tmp_path):
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    b = write(tmp_path / "b.json", [("BBB", "2026-03-16")])
    assert keys(load_pairs([a, b])) == [("AAA", "2026-03-16"),
                                        ("BBB", "2026-03-16")]


def test_a_pair_in_both_lists_is_not_scored_twice(tmp_path):
    """A symbol-day cannot be both a survivor and a reject, but if the lists
    ever overlap the engine must not run it twice -- the P/L would double and
    nothing about the run would look wrong."""
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    b = write(tmp_path / "b.json", [("AAA", "2026-03-16"),
                                    ("BBB", "2026-03-16")])
    assert len(load_pairs([a, b])) == 2


def test_the_non_equity_filter_applies_across_every_list(tmp_path):
    """Dotted symbols and non-alphabetic tickers are dropped. A second list
    must not be a way back in."""
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    b = write(tmp_path / "b.json", [("BRK.B", "2026-03-16"),
                                    ("AA1", "2026-03-16"),
                                    ("BBB", "2026-03-16")])
    assert keys(load_pairs([a, b])) == [("AAA", "2026-03-16"),
                                        ("BBB", "2026-03-16")]


def test_the_cli_default_is_a_list_not_a_string():
    """With nargs='+' a bare string default hands the code a string to iterate
    character by character, and the failure is a missing file called 'v'."""
    import inspect

    from common import backtest as B
    assert 'default=["var/state/traded_pairs.json"]' in inspect.getsource(B)


def test_the_entry_point_calls_this_very_function():
    """The test that would have caught the original bug. Asserting on a
    same-named function in another module proves nothing about this one."""
    import inspect

    from common import backtest as B
    assert B.load_pairs is load_pairs
    assert "load_pairs(paths)" in inspect.getsource(B.main_async)


def test_there_is_only_one_of_this_function_now():
    """backtest.py carried a byte-identical copy with a comment promising the
    two would be kept in step. They were not. This asserts the copy is gone
    rather than trusting the comment."""
    import inspect

    from common import backtest as B
    from common import cache_io as C
    assert B.load_pairs is C.load_pairs
    assert "def load_pairs" not in inspect.getsource(B)


def test_the_other_load_pairs_is_a_different_job_and_stays_separate():
    """databento_fetch.load_pairs returns (symbol, date) TUPLES for the archive
    and applies no equity filter -- it must fetch what it was asked for. It is
    a genuinely different function that happens to share a name, which is what
    made the original mistake so easy."""
    from common.cache_io import load_pairs as equities
    from common.databento_fetch import load_pairs as archive
    assert archive is not equities
