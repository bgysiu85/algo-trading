"""G5 of REGISTERED_tl_v1.md sec 5.1: "the line in force at t uses only
pivots confirmed by t - 1's close; touch pivots confirmed by t - 1; ER
percentiles from training bars only (a test fails if a holdout bar changes
them)." Board: W15-0019.

Mirrors tests/test_tl_v0_hindsight_guard.py's approach for TL-v0's own G5:
prove no line/touch/ER value at bar t changes if bars AFTER t are altered or
appended, and prove the proof would actually fail on a mutated (off-by-one)
implementation, not just pass vacuously.
"""
from __future__ import annotations

import numpy as np

from common.tl_v0_lines import find_pivots
from common.tl_v1_lines import build_series, touch_pivots_between, efficiency_ratio


def _synthetic_prefix(n=30):
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, n))
    closes[5] = closes[5] + 8      # a clean high pivot
    closes[15] = closes[15] + 12   # a clean, flatter high pivot after it
    atr = np.full(n, 1.0)
    return closes, atr


def test_line_and_breaks_up_to_t_are_unchanged_by_bars_appended_after_t():
    closes, atr = _synthetic_prefix(30)
    R = 3
    pivots = find_pivots(closes, R, "high")
    out_short = build_series(len(closes), pivots, closes, atr, "res")

    # extend the series with bars that would themselves create new pivots
    # confirmed only after t=29 (the original last bar) -- these must never
    # reach back and change anything at or before bar 29
    ext = np.concatenate([closes, closes[-1] + np.array([5, -5, 9, -9, 20, -20, 1, 1])])
    atr_ext = np.full(len(ext), 1.0)
    pivots_ext = find_pivots(ext, R, "high")
    out_long = build_series(len(ext), pivots_ext, ext, atr_ext, "res")

    cut = len(closes)
    assert np.array_equal(out_short["breaks"], out_long["breaks"][:cut])
    for j in range(cut):
        a, b = out_short["line"][j], out_long["line"][j]
        assert (np.isnan(a) and np.isnan(b)) or np.isclose(a, b), (j, a, b)


def test_a_pivot_is_not_usable_before_its_own_confirm_bar():
    """The building block G5 depends on: build_series must never arm a pair
    whose point B has not yet confirmed. Regression form: feed the walk a
    (mutated) pivot list where B's reported confirm index is one bar EARLY,
    and show the line then appears one bar sooner than it should -- proving
    this test actually catches the class of bug it exists for.

    Deterministic pivots (near-flat decline, well clear of the flat close
    series -- same shape test_build_series_flat_price_never_breaks in
    tests/test_tl_v1_lines.py uses) so the line's own validity never
    confounds the confirm-timing question this test is about."""
    n = 20
    atr = np.full(n, 1.0)
    closes = np.full(n, 90.0)
    pivots = [(2, 4, 105.0), (6, 8, 104.9)]
    out = build_series(n, pivots, closes, atr, "res")
    p2_confirm = pivots[1][1]
    assert np.isnan(out["line"][p2_confirm - 1]), (
        "a two-pivot line appeared before its second pivot's own confirm bar")

    mutated = [(p, c - 1, v) for (p, c, v) in pivots]  # confirm one bar early
    out_mut = build_series(n, mutated, closes, atr, "res")
    assert not np.isnan(out_mut["line"][p2_confirm - 1]), (
        "mutating the confirm index earlier did not change the result -- "
        "this test would not catch a real off-by-one regression")


def test_touch_pivots_between_ignores_touches_at_or_after_t():
    line = np.full(20, 100.0)
    atr = np.full(20, 1.0)
    touches = [(3, 5, 99.9), (10, 12, 99.9), (14, 16, 99.9)]
    cnt, hits = touch_pivots_between(0, 14, touches, line, atr, "res")
    # t=14: only touches with pidx <= t-1=13 AND cidx <= t-1=13 count
    assert hits == [3, 10]
    assert cnt == 2


def test_er_at_t_is_unaffected_by_bars_after_t():
    rng = np.random.default_rng(3)
    closes = 100 + np.cumsum(rng.normal(0, 0.4, 40))
    er_short = efficiency_ratio(closes, 20)
    ext = np.concatenate([closes, closes[-1] + rng.normal(0, 5, 10)])
    er_long = efficiency_ratio(ext, 20)
    cut = len(closes)
    for j in range(cut):
        a, b = er_short[j], er_long[j]
        assert (np.isnan(a) and np.isnan(b)) or np.isclose(a, b), (j, a, b)
