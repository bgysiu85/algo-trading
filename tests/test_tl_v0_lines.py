"""AT-113 (G3): regression test for the stale-broken-line re-fire bug.

Pine's tlCore() sets resOn/supOn := false the instant a break fires, and
only a fresh confirmed, revalidated pivot pair re-arms it. The old
build_line_series()+break_events() pairing had no such state: the line kept
extrapolating past a break, so a later whipsaw back across it could
re-fire a second signal. walk_line_and_breaks() fixes this. See
common/tl_v0_lines.py's walk_line_and_breaks docstring and
claude/... AT-113 Result doc for the full writeup.
"""
import numpy as np

from common.tl_v0_lines import walk_line_and_breaks, build_line_series, break_events


def _synthetic_case():
    # One resistance line: pivots (2, val=110) confirmed at bar 4, and
    # (6, val=105) confirmed at bar 8 (R=2). No further high pivot forms.
    # Price crosses above the line once (bar 9), dips back under (10-11),
    # then crosses back above with NO new pivot in between (bar 12).
    n = 16
    atr = np.full(n, 1.0)
    closes = np.array([100, 101, 109, 101, 100, 99, 104, 100, 99,
                        103.0, 99.0, 98.0, 104.0, 100, 100, 100])
    pivots = [(2, 4, 110.0), (6, 8, 105.0)]
    return n, pivots, atr, closes


def test_stale_line_does_not_refire():
    """The Pine-faithful walk fires exactly once; the old pairing fires twice
    (kept here as a mutation check -- if walk_line_and_breaks regresses to
    the old, stateless behaviour, this test catches it)."""
    n, pivots, atr, closes = _synthetic_case()
    line, breaks = walk_line_and_breaks(n, pivots, 2, closes, atr, "high")
    assert breaks.sum() == 1, f"expected exactly 1 break, got {breaks.sum()} at {np.nonzero(breaks)[0]}"
    assert breaks[9] and not breaks[12]
    assert np.isnan(line[10]) and np.isnan(line[12]), "line must go cold (NaN) after it breaks"


def test_old_pairing_exhibits_the_bug():
    """Documents the bug in the superseded functions: they DO double-fire on
    the same synthetic case. This pins the before/after contrast; it is not
    an endorsement of build_line_series/break_events for signal detection."""
    n, pivots, atr, closes = _synthetic_case()
    res = build_line_series(n, pivots, 2, closes, atr, "high")
    sup = np.full(n, np.nan)
    ups, _ = break_events(closes, res, sup, atr)
    assert ups.sum() == 2 and ups[9] and ups[12]


def test_no_pivots_never_signals():
    n = 10
    atr = np.full(n, 1.0)
    closes = np.linspace(100, 110, n)
    line, breaks = walk_line_and_breaks(n, [], 2, closes, atr, "high")
    assert not breaks.any()
    assert np.isnan(line).all()


def test_new_pivot_can_rearm_after_a_break():
    """After a break goes cold, a fresh valid pivot pair CAN produce a new
    signal later (only a NEW pivot re-arms it -- confirms re-arming isn't
    permanently disabled by the fix). Bars 0-9 are the proven first-break
    case; bars 10-18 mirror that same validated shape (shifted +10 bars,
    -20 price) so the second pair (12, 90)-(16, 85) revalidates and breaks
    at bar 18."""
    closes = np.array([100, 101, 109, 101, 100, 99, 104, 100, 99, 103.0,
                        99.0, 98.0, 89.0, 81.0, 80.0, 79.0, 84.0, 80.0, 90.0])
    n = len(closes)
    atr = np.full(n, 1.0)
    pivots = [(2, 4, 110.0), (6, 8, 105.0), (12, 14, 90.0), (16, 18, 85.0)]
    line, breaks = walk_line_and_breaks(n, pivots, 2, closes, atr, "high")
    assert breaks[9]
    assert breaks[18], f"expected the re-armed line to break at bar 18, breaks={np.nonzero(breaks)[0]}"
