#!/usr/bin/env python3
"""--pairs takes several lists, and unions them.

The screened run has to score survivors and rejects in ONE pass: two passes
into one state directory would have the second rewrite the first's trades CSV,
and the leakage control compares the two populations from that single file.
"""
from __future__ import annotations

import json

from common.databento_fetch import load_pairs


def write(p, pairs):
    p.write_text(json.dumps([{"symbol": s, "date": d} for s, d in pairs]))
    return p


def test_two_lists_are_unioned(tmp_path):
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    b = write(tmp_path / "b.json", [("BBB", "2026-03-16")])
    assert load_pairs([a, b]) == [("AAA", "2026-03-16"), ("BBB", "2026-03-16")]


def test_a_pair_in_both_lists_is_not_run_twice(tmp_path):
    """A symbol-day cannot be both a survivor and a reject, but if the lists
    ever overlap the engine must not score it twice -- the P/L would double
    and nothing about the run would look wrong."""
    a = write(tmp_path / "a.json", [("AAA", "2026-03-16")])
    b = write(tmp_path / "b.json", [("AAA", "2026-03-16"), ("BBB", "2026-03-16")])
    assert len(load_pairs([a, b])) == 2


def test_the_default_is_still_a_list_the_parser_can_hand_over():
    """nargs='+' with a bare string default would give the code a string to
    iterate character by character -- 'v', 'a', 'r', '/', ... -- and the error
    would be a missing file called 'v'."""
    from common import backtest as B
    p = B.build_parser() if hasattr(B, "build_parser") else None
    if p is None:
        import inspect
        src = inspect.getsource(B)
        assert 'default=["var/state/traded_pairs.json"]' in src
        return
    assert isinstance(p.parse_args([]).pairs, list)
