#!/usr/bin/env python3
"""Context for CHARTMARK-S v1 (sec 2.1). Frames and indicators are the long side's (strategy.chartmark.data): same CL 1H
training cut (before 2022-01-01, then resample and difference-back-adjust), same EMA/MACD/ATR/volume-SMA code.
Every value at bar t uses bars <= t only."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view as swv

from strategy.chartmark.data import (Frame, Ind, avoid_flag, indicators, load_seen_frame,   # noqa: F401
                                     load_training_frame, make_frame)
from strategy.chartmark_s import spec as S


def bars_since_high(h: np.ndarray, N: int = S.TOP_N) -> np.ndarray:
    """At t: bars since the highest high of bars t-N+1..t (oldest bar wins a tie). NaN for t < N-1."""
    n = len(h)
    out = np.full(n, np.nan)
    if n >= N:
        w = swv(h, N)                              # w[i] = h[i..i+N-1] -> bar t = i+N-1
        out[N - 1:] = (N - 1) - np.argmax(w, axis=1)
    return out


def range_pos(fr: Frame, N: int = S.RANGE_N) -> np.ndarray:
    """V-RANGE: (close[t] - lowest low t-N+1..t) / (highest high - lowest low). NaN for t < N-1."""
    n = fr.n
    out = np.full(n, np.nan)
    if n >= N:
        lo = swv(fr.l, N).min(axis=1)
        hi = swv(fr.h, N).max(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[N - 1:] = (fr.c[N - 1:] - lo) / (hi - lo)
    return out


def context(fr: Frame, ind: Ind, p: S.Params) -> np.ndarray:
    """X1 & X2 & X3 [& V-RANGE] [& V-SESSION] [& ~AVOID], evaluated at the CLOSE of each bar t."""
    key = ("S", p.x1_window, p.rng, p.session, p.avoid)
    if key in ind._cache:
        return ind._cache[key]
    n = fr.n
    with np.errstate(invalid="ignore"):
        x1 = bars_since_high(fr.h) <= p.x1_window
        x2 = ind.e9 >= ind.e21 - S.XTOL * ind.atr
        x3 = np.zeros(n, bool)
        x3[1:] = ind.hist[1:] < ind.hist[:-1]
        ok = x1 & x2 & x3
        ok &= ~np.isnan(ind.atr) & ~np.isnan(ind.hist) & ~np.isnan(ind.e21)
        if p.rng:
            ok &= range_pos(fr) >= S.RANGE_MIN
        if p.session:
            ok &= (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
        if p.avoid:
            ok &= ~avoid_flag(fr, ind)
    ok = np.nan_to_num(ok.astype(float), nan=0.0).astype(bool)
    ind._cache[key] = ok
    return ok
