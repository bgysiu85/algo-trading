"""G5 of `docs/research/REGISTERED_tl_v0.md`: "The hindsight guard is
tested. A synthetic series where a pivot confirms at bar i+R: a line through
it must not exist at bar i+R-1. Mutation-checked (shift the pivot back, the
test must fail)."

This is a property of the existing pivot/line machinery in
common/tl_v0_lines.py, not new production code: find_pivots() only reports a
pivot as (pivot_idx, confirm_idx=pivot_idx+R, value), and
walk_line_and_breaks() only arms a pivot pair on the bar j == confirm_idx
(see its pivot_at dict, keyed by cidx). AT-113's stale-line regression test
(tests/test_tl_v0_lines.py) already exercises the general walk; this file's
job is narrower and specific to G5: prove no line/signal exists before its
confirming bar, and prove that proof would actually fail if the confirm bar
were computed one bar early -- the exact off-by-one class TSMOM's own
holdout guard was built to catch in a different form (tests/strategy/
test_tsmom_holdout.py::test_a_bare_year_month_lands_on_the_right_side_of_the_boundary).
"""
from __future__ import annotations

import numpy as np

from common.tl_v0_lines import find_pivots, walk_line_and_breaks


def _synthetic_case(R=3):
    """Two confirmed high pivots (falling, so a valid resistance line forms
    between them) with nothing before or after to confound the read.

    Pivot 1 at bar 3 (value 200), confirmed at bar 3+R.
    Pivot 2 at bar 9 (value 150, lower -> "falling", valid), confirmed at
    bar 9+R. The line is only ever active from the SECOND pivot's confirm
    bar onward (a single pivot cannot define a line -- two points are
    needed), so bar 9+R is the one G5 is actually about here.

    Between the two pivots and up to the confirm bar, every close sits far
    below the forming line (REGISTERED_tl_v0.md section 2.1's "line validity
    at birth" test: invalid if any close beyond it by > 0.10*ATR before
    confirmation) -- a nearly-flat, strictly-decreasing baseline elsewhere
    avoids both that violation and the tie-pivot behaviour a truly flat
    series would trigger (every bar of a flat run is its own window max
    under this module's find_pivots, which is real but a different test's
    concern, not this one's).
    """
    n = 16
    R_ = R
    atr = np.full(n, 1.0)
    closes = np.array([90.0 - 0.1 * i for i in range(n)])
    closes[3] = 200.0
    closes[9] = 150.0
    pivots = find_pivots(closes, R_, "high")
    # sanity: the two pivots we designed are actually found and confirm at
    # pivot_idx + R, not earlier and not later
    assert (3, 3 + R_, 200.0) in pivots, pivots
    assert (9, 9 + R_, 150.0) in pivots, pivots
    assert len(pivots) == 2, pivots  # nothing else in the baseline qualifies
    return n, pivots, atr, closes, R_


def test_pivots_confirm_exactly_at_pivot_idx_plus_R():
    """The building block G5 depends on: find_pivots' own confirm index."""
    n, pivots, atr, closes, R = _synthetic_case()
    for pidx, cidx, _ in pivots:
        assert cidx == pidx + R


def test_no_line_exists_before_the_confirming_pivot():
    """The core G5 property: at bar (second_pivot_idx + R) - 1, one bar
    before the second pivot confirms and the line can legitimately arm,
    no line value exists (line is NaN) and no break can have fired there."""
    n, pivots, atr, closes, R = _synthetic_case()
    line, breaks = walk_line_and_breaks(n, pivots, R, closes, atr, "high")

    second_pidx, second_cidx, _ = [p for p in pivots if p[0] == 9][0]
    assert np.isnan(line[second_cidx - 1]), (
        f"a line exists at bar {second_cidx - 1}, one bar BEFORE its "
        f"confirming pivot at bar {second_cidx} -- hindsight leak")
    assert not breaks[second_cidx - 1]
    # and from the confirm bar onward, the line is live
    assert not np.isnan(line[second_cidx])


def test_shifting_the_pivot_confirm_bar_one_early_is_caught_by_the_guard():
    """The mutation check REGISTERED_tl_v0.md section 0 asks for: "shift the
    pivot back, the test must fail." We construct the corrupted pivot list
    an off-by-one confirm computation (pivot_idx + R - 1 instead of + R)
    would produce, and show the PREVIOUS test's assertion -- "no line exists
    one bar before the true confirm" -- would then be FALSE. That is the
    proof the guard test is actually sensitive to this bug class, not
    vacuously true.
    """
    n, pivots, atr, closes, R = _synthetic_case()
    true_second_cidx = [c for (p, c, v) in pivots if p == 9][0]

    # The bug being simulated: confirm_idx computed as pidx + R - 1.
    mutated = [(p, c - 1, v) for (p, c, v) in pivots]

    line, _breaks = walk_line_and_breaks(n, mutated, R, closes, atr, "high")

    # If the guard test's assertion still held here, the mutation would be
    # undetectable and the guard would not be a guard.
    leaked_bar = true_second_cidx - 1
    assert not np.isnan(line[leaked_bar]), (
        "expected the one-bar-early confirm mutation to leak a line at bar "
        f"{leaked_bar} (one bar before the TRUE confirm bar "
        f"{true_second_cidx}); if this line is NaN, "
        "test_no_line_exists_before_the_confirming_pivot would not actually "
        "have caught the bug it exists to catch")


def test_a_single_pivot_never_arms_a_line_at_any_bar():
    """A line needs two confirmed pivots of one kind (common/tl_v0_lines.py:
    build_line_series/walk_line_and_breaks docstrings). One pivot must never
    produce a line -- the zero-pivots-before-confirm case taken to its limit.

    n is kept to exactly 2R+1 so find_pivots only ever evaluates the single
    centre bar (range(R, n-R) == [R]): a longer flat run either side of the
    spike would itself tie-qualify as a pivot under this module's >= test
    (every bar in a flat window is its own window max), which is a real and
    already-covered property of find_pivots, just not the one this test is
    about.
    """
    R = 3
    n = 2 * R + 1
    atr = np.full(n, 1.0)
    closes = np.full(n, 100.0)
    closes[R] = 130.0  # the only bar that can possibly be evaluated
    pivots = find_pivots(closes, R, "high")
    assert len(pivots) == 1 and pivots[0][:2] == (R, 2 * R)
    line, breaks = walk_line_and_breaks(n, pivots, R, closes, atr, "high")
    assert np.isnan(line).all(), "a single pivot must never arm a line"
    assert not breaks.any()
