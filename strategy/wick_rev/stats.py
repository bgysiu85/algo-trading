#!/usr/bin/env python3
"""WICK-REV statistics: month-block bootstrap and Spearman. W15-0063, REGISTERED sec 5-6.

Block bootstrap BY CALENDAR MONTH (consecutive long-wick bars share look-ahead windows, so signals
are never resampled one by one): 2,000 resamples, draw i seeded with crc32 of the draw number. Every
bootstrapped quantity is built from per-month sums, so a resample is a handful of integer additions.
Spearman: ranks are taken once on the full sample, then Pearson is bootstrapped on those fixed ranks.
"""
from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np

from strategy.wick_rev import spec as S


@lru_cache(maxsize=64)
def _draws(m: int, n_draws: int = S.BOOT_DRAWS) -> np.ndarray:
    """(n_draws, m) month indices; draw i uses default_rng(crc32(str(i)))."""
    out = np.empty((n_draws, m), dtype=np.int64)
    for i in range(n_draws):
        out[i] = np.random.default_rng(zlib.crc32(str(i).encode("ascii"))).integers(0, m, m)
    return out


def month_codes(session: np.ndarray) -> np.ndarray:
    """datetime64[D] -> an integer per calendar month."""
    mo = session.astype("datetime64[M]")
    return mo.astype(int)


def _q(x: np.ndarray, level: float) -> tuple[float, float]:
    a = (1 - level) / 2
    lo, hi = np.nanquantile(x, [a, 1 - a])
    return float(lo), float(hi)


def edge_ci(sig_months, sig_rev, base_months, base_rev, universe_months=None) -> dict:
    """edge = P(rev | signals) - P(rev | base), in fractional points, with month-block bootstrap CIs.
    sig_rev / base_rev are 0/1 arrays aligned to sig_months / base_months."""
    sig_months, base_months = np.asarray(sig_months), np.asarray(base_months)
    ns, nb = len(sig_months), len(base_months)
    if ns == 0 or nb == 0:
        return {"edge": float("nan"), "lo95": float("nan"), "hi95": float("nan"),
                "lo995": float("nan"), "hi995": float("nan")}
    months = np.unique(np.concatenate([base_months, sig_months]) if universe_months is None else universe_months)
    pos = {m: i for i, m in enumerate(months.tolist())}
    M = len(months)
    sm = np.array([pos[m] for m in sig_months.tolist()])
    bm = np.array([pos[m] for m in base_months.tolist()])
    n_s = np.bincount(sm, minlength=M).astype(float)
    r_s = np.bincount(sm, weights=np.asarray(sig_rev, float), minlength=M)
    n_b = np.bincount(bm, minlength=M).astype(float)
    r_b = np.bincount(bm, weights=np.asarray(base_rev, float), minlength=M)
    point = r_s.sum() / n_s.sum() - r_b.sum() / n_b.sum()
    idx = _draws(M)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = r_s[idx].sum(1) / n_s[idx].sum(1) - r_b[idx].sum(1) / n_b[idx].sum(1)
    lo95, hi95 = _q(e, S.CI_LEVEL)
    lo995, hi995 = _q(e, S.CI_LEVEL_BONF)
    return {"edge": float(point), "lo95": lo95, "hi95": hi95, "lo995": lo995, "hi995": hi995}


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (ties share), 1-based."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    xs = x[order]
    i = 0
    n = len(x)
    while i < n:
        j = i
        while j + 1 < n and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman_ci(x, y, months) -> dict:
    """Spearman rho between x and y with a month-block bootstrap 95% CI (fixed full-sample ranks)."""
    x, y, months = np.asarray(x, float), np.asarray(y, float), np.asarray(months)
    n = len(x)
    nan = {"rho": float("nan"), "lo95": float("nan"), "hi95": float("nan"), "n": n}
    if n < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return nan
    rx, ry = _rank(x), _rank(y)
    um = np.unique(months)
    pos = {m: i for i, m in enumerate(um.tolist())}
    mi = np.array([pos[m] for m in months.tolist()])
    M = len(um)

    def agg(v):
        return np.bincount(mi, weights=v, minlength=M)
    cnt = np.bincount(mi, minlength=M).astype(float)
    sx, sy, sxx, syy, sxy = agg(rx), agg(ry), agg(rx * rx), agg(ry * ry), agg(rx * ry)

    def pearson(c, a, b, aa, bb, ab):
        with np.errstate(divide="ignore", invalid="ignore"):
            num = ab - a * b / c
            den = np.sqrt((aa - a * a / c) * (bb - b * b / c))
            return num / den
    rho = float(pearson(cnt.sum(), sx.sum(), sy.sum(), sxx.sum(), syy.sum(), sxy.sum()))
    idx = _draws(M)
    boots = pearson(cnt[idx].sum(1), sx[idx].sum(1), sy[idx].sum(1), sxx[idx].sum(1), syy[idx].sum(1), sxy[idx].sum(1))
    lo, hi = _q(boots, S.CI_LEVEL)
    return {"rho": rho, "lo95": lo, "hi95": hi, "n": n}
