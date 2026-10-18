"""The online support-line tracker is the frozen TL-v0 line, bar for bar, plus a causal one-bar-ahead projection."""
import numpy as np
import pytest

from common.tl_v0_lines import atr14, find_pivots, walk_line_and_breaks
from exitmgr import lines as LN


def series(seed, n=2500, vol=0.15):
    rng = np.random.default_rng(seed)
    c = 60 + np.cumsum(rng.normal(0.002, vol, n))
    o = np.concatenate([[60.0], c[:-1]])
    h = np.maximum(o, c) + np.abs(rng.normal(0, vol / 2, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, vol / 2, n))
    atr = atr14(h, l, c).astype(float)
    atr[:13] = np.nan
    return h, l, c, atr


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("R,buf", [(5, 0.10), (3, 0.05), (8, 0.20)])
def test_identical_to_the_frozen_module(seed, R, buf):
    h, l, c, atr = series(seed)
    ref_line, ref_brk = walk_line_and_breaks(len(c), find_pivots(l, R, "low"), R, c, atr, "low", buf)
    line, brk, prj = LN.track(l, c, atr, R, buf)
    assert np.array_equal(brk, ref_brk)
    assert np.allclose(line, ref_line, equal_nan=True, rtol=0, atol=1e-12)
    assert np.isfinite(ref_line).sum() > 100        # the series really produces lines


def test_projection_is_the_next_bars_line_when_no_pivot_confirms_there():
    h, l, c, atr = series(7)
    R = 5
    ref_line, _ = walk_line_and_breaks(len(c), find_pivots(l, R, "low"), R, c, atr, "low", 0.10)
    _, _, prj = LN.track(l, c, atr, R, 0.10)
    confirm = {p[1] for p in find_pivots(l, R, "low")}
    checked = 0
    for j in range(1, len(c)):
        if j not in confirm:
            a, b = prj[j - 1], ref_line[j]
            assert (np.isnan(a) and np.isnan(b)) or a == pytest.approx(b, abs=1e-12)
            checked += 1
    assert checked > 2000


@pytest.mark.parametrize("k", [300, 777, 1500])
def test_truncation_invariance(k):
    """proj_next[j] uses bars <= j only: mutate every bar after k and nothing up to k moves."""
    h, l, c, atr = series(11)
    _, _, p0 = LN.track(l, c, atr, 5, 0.10)
    rng = np.random.default_rng(99)
    l2, c2, atr2 = l.copy(), c.copy(), atr.copy()
    l2[k + 1:] = rng.uniform(30, 90, len(l) - k - 1)
    c2[k + 1:] = rng.uniform(30, 90, len(l) - k - 1)
    atr2[k + 1:] = rng.uniform(0.01, 3, len(l) - k - 1)
    _, _, p1 = LN.track(l2, c2, atr2, 5, 0.10)
    assert np.array_equal(p0[: k + 1], p1[: k + 1], equal_nan=True)
    assert not np.array_equal(p0, p1, equal_nan=True)       # and the mutation is not a no-op
