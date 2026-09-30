#!/usr/bin/env python3
"""Context for CHARTMARK-S v3 (sec 2.1): X1 and (Tier A or Tier B), Tier B = B2 & B3 & B4 (B1 removed). Bar t only for Tier B;
every value at bar t uses bars <= t only. Frames and indicators are v1's / v2's."""
from __future__ import annotations

import numpy as np

from strategy.chartmark.data import avoid_flag                      # noqa: F401
from strategy.chartmark_s2.data import (Frame, Ind, bars_since_high, indicators, load_seen_frame,   # noqa: F401
                                        load_training_frame, range_pos)
from strategy.chartmark_s3 import spec as S


def tier_array(fr: Frame, ind: Ind, tiers: str = "AB", b1: bool = False) -> np.ndarray:
    """int8 per bar: 1 = Tier A (EMA9 < EMA21), 2 = Tier B (EMA9 >= EMA21 and B2, B3, B4 [and B1 when b1]), 0 = neither."""
    n = fr.n
    out = np.zeros(n, np.int8)
    with np.errstate(invalid="ignore"):
        a = ind.e9 < ind.e21
        b2 = fr.h >= ind.e9 - S.RETEST_TICKS * S.TICK                   # the bar rallies to EMA9
        b3 = fr.c < ind.e9                                              # and closes back below it
        b4 = ind.hist < 0                                               # MACD below its signal line
        tb = (~a) & b2 & b3 & b4
        if b1:                                                          # v2's extra condition, only for V-B1
            p1 = np.zeros(n, bool)
            p1[1:] = fr.c[:-1] < ind.e9[:-1]
            tb &= p1
        if "A" in tiers:
            out[a] = S.TIER_A
        if "B" in tiers:
            out[tb & (out == 0)] = S.TIER_B
    return out


def context_tiers(fr: Frame, ind: Ind, p: S.Params) -> tuple[np.ndarray, np.ndarray]:
    key = ("S3", p.x1_window, p.tiers, p.b1, p.rng, p.session, p.avoid)
    if key in ind._cache:
        return ind._cache[key]
    with np.errstate(invalid="ignore"):
        x1 = bars_since_high(fr.h) <= p.x1_window
        ta = tier_array(fr, ind, p.tiers, p.b1)
        ok = x1 & (ta > 0)
        ok &= ~np.isnan(ind.atr) & ~np.isnan(ind.hist) & ~np.isnan(ind.e21)
        if p.rng:
            ok &= range_pos(fr) >= S.RANGE_MIN
        if p.session:
            ok &= (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
        if p.avoid:
            ok &= ~avoid_flag(fr, ind)
    ok = np.nan_to_num(ok.astype(float), nan=0.0).astype(bool)
    tier = np.where(ok, ta, 0).astype(np.int8)
    ind._cache[key] = (ok, tier)
    return ok, tier


def context(fr: Frame, ind: Ind, p: S.Params) -> np.ndarray:
    return context_tiers(fr, ind, p)[0]
