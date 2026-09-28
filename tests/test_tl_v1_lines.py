"""W15-0019: unit tests for common/tl_v1_lines.py (extreme-anchor line +
A+ checklist, REGISTERED_tl_v1.md sec 2.2-2.3). Synthetic data only --
mirrors tests/test_tl_v0_lines.py's style."""
import numpy as np

from common.tl_v1_lines import (
    efficiency_ratio, anchor_pair_at, build_series, touch_pivots_between,
    a_plus_checklist, CROSS_BUFFER,
)


def test_efficiency_ratio_trending_is_high_choppy_is_low():
    n = 60
    trend = np.linspace(100, 130, n)  # straight line up: ER -> 1
    er_t = efficiency_ratio(trend, 20)
    assert np.nanmax(er_t) > 0.9

    rng = np.random.default_rng(0)
    chop = 100 + np.cumsum(rng.choice([-1.0, 1.0], n))
    er_c = efficiency_ratio(chop, 20)
    # not a strict guarantee for any seed, but this seed produces a
    # materially choppier ER than the straight trend above
    assert np.nanmean(er_c[20:]) < np.nanmean(er_t[20:])


def test_efficiency_ratio_short_series_is_all_nan():
    er = efficiency_ratio(np.arange(10.0), 20)
    assert np.isnan(er).all()


def test_anchor_pair_picks_extreme_then_flattest_valid():
    # Three confirmed 'res' (high) pivots: extreme at bar 2 (120), a steep
    # partner at bar 6 (110) and a flatter valid partner at bar 10 (116).
    # Anchor must be the extreme (bar 2, highest price); point B must be
    # the FLATTEST of the two valid choices (bar 10), not the first one
    # found (bar 6).
    n = 16
    atr = np.full(n, 1.0)
    closes = np.full(n, 90.0)
    pivots = [(2, 4, 120.0), (6, 8, 110.0), (10, 12, 116.0)]
    got = anchor_pair_at(12, pivots, closes, atr, "res")
    assert got is not None
    pA, vA, pB, vB, slope = got
    assert (pA, vA) == (2, 120.0)
    assert pB == 10, f"expected the flatter partner (bar 10), got {pB}"


def test_anchor_pair_none_when_only_one_pivot_in_window():
    n = 10
    atr = np.full(n, 1.0)
    closes = np.full(n, 90.0)
    assert anchor_pair_at(9, [(2, 4, 120.0)], closes, atr, "res") is None


def test_anchor_pair_respects_window_and_max_span():
    n = 500
    atr = np.full(n, 1.0)
    closes = np.full(n, 90.0)
    # A near-flat decline (slope -0.025/bar) so the line stays well above
    # the flat close series for hundreds of bars -- isolates the WINDOW
    # test from L4's never-crossed test, which a steep line would trip on
    # its own as it extrapolates far below/above a flat price.
    pivots = [(2, 4, 105.0), (6, 8, 104.9)]
    assert anchor_pair_at(400, pivots, closes, atr, "res") is None  # both aged out (t-A>250)
    assert anchor_pair_at(200, pivots, closes, atr, "res") is not None


def test_build_series_flat_price_never_breaks():
    n = 20
    atr = np.full(n, 1.0)
    closes = np.full(n, 100.0)
    # near-flat decline, well above the flat close series throughout
    pivots = [(2, 4, 105.0), (6, 8, 104.9)]
    out = build_series(n, pivots, closes, atr, "res")
    assert not out["breaks"].any()
    assert not np.isnan(out["line"][19])  # line stays armed


def test_build_series_break_fires_once_per_crossing_episode():
    n = 20
    atr = np.full(n, 1.0)
    # near-flat decline (slope -0.25/bar): line stays ~100 through bar 19,
    # so a brief price bump is the ONLY crossing episode -- no confound
    # from the line itself decaying back down into a flat close series.
    pivots = [(2, 4, 102.0), (6, 8, 101.0)]
    closes = np.full(n, 90.0)
    closes[10:13] = 103.0
    out = build_series(n, pivots, closes, atr, "res")
    fired = np.nonzero(out["breaks"])[0]
    assert len(fired) == 1
    assert fired[0] == 10


def test_touch_pivots_between_counts_within_buffer():
    n = 20
    atr = np.full(n, 1.0)
    line = np.full(n, np.nan)
    line[5:20] = 100.0  # flat resistance at 100 from bar 5
    touch_pivots = [
        (6, 8, 99.9),   # within 0.25*ATR of 100 -> touch
        (9, 11, 95.0),  # too far below -> not a touch
        (12, 14, 100.5),  # above the line but still within buffer on close basis
    ]
    cnt, hits = touch_pivots_between(5, 19, touch_pivots, line, atr, "res")
    assert cnt == 2
    assert hits == [6, 12]


def test_a_plus_checklist_requires_all_three():
    ok, detail = a_plus_checklist(t=50, pA=10, touches_count=3, span_days=7,
                                   er_value=0.5, er_threshold=0.4)
    assert ok and all(detail.values())

    ok2, detail2 = a_plus_checklist(t=50, pA=10, touches_count=2, span_days=7,
                                     er_value=0.5, er_threshold=0.4)
    assert not ok2 and detail2["A1_touches"] is False

    ok3, detail3 = a_plus_checklist(t=50, pA=10, touches_count=3, span_days=6,
                                     er_value=0.5, er_threshold=0.4)
    assert not ok3 and detail3["A2_span"] is False

    ok4, detail4 = a_plus_checklist(t=50, pA=10, touches_count=3, span_days=7,
                                     er_value=0.3, er_threshold=0.4)
    assert not ok4 and detail4["A3_trending"] is False
