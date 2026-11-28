"""WICK-REV month-block bootstrap and Spearman (W15-0063 sec 5)."""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from strategy.wick_rev import stats as ST


def _months(n, per=40):
    return (np.arange(n) // per).astype(int) + 600


def test_draw_i_is_seeded_with_crc32_of_the_draw_number():
    d = ST._draws(12)
    want = np.random.default_rng(zlib.crc32(b"7")).integers(0, 12, 12)
    assert np.array_equal(d[7], want) and d.shape == (2000, 12)


def test_edge_ci_is_deterministic_and_excludes_zero_only_for_a_real_effect():
    rng = np.random.default_rng(0)
    bm = _months(8000)
    base = (rng.random(8000) < 0.30).astype(float)
    sm = bm[:2000]
    null = (rng.random(2000) < 0.30).astype(float)
    a, b = ST.edge_ci(sm, null, bm, base), ST.edge_ci(sm, null, bm, base)
    assert a == b
    assert a["lo995"] < 0 < a["hi995"]
    real = (rng.random(2000) < 0.40).astype(float)
    e = ST.edge_ci(sm, real, bm, base)
    assert e["lo995"] > 0 and 0.05 < e["edge"] < 0.15


def test_edge_with_no_signals_is_nan_not_an_error():
    e = ST.edge_ci(np.array([]), np.array([]), np.array([600]), np.array([1.0]))
    assert np.isnan(e["edge"])


def test_spearman_matches_pandas_and_handles_ties():
    rng = np.random.default_rng(1)
    x = rng.integers(0, 10, 600).astype(float)
    y = x * 0.5 + rng.normal(0, 3, 600)
    r = ST.spearman_ci(x, y, _months(600, 30))
    want = pd.Series(x).rank().corr(pd.Series(y).rank())      # Pearson on average ranks = Spearman
    assert abs(r["rho"] - want) < 1e-9
    assert r["lo95"] < r["rho"] < r["hi95"]
    mono = ST.spearman_ci(np.arange(100.0), np.arange(100.0) * 3, _months(100, 10))
    assert abs(mono["rho"] - 1.0) < 1e-12
    flat = ST.spearman_ci(np.ones(50), np.arange(50.0), _months(50, 10))
    assert np.isnan(flat["rho"])
