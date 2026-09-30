#!/usr/bin/env python3
"""Context for CHARTMARK-S v2 (sec 2.1): X1 and (Tier A or Tier B). Frames and indicators are v1's / the long side's
(same CL 1H training cut, resample, difference back-adjust, EMA / MACD / ATR code). Every value at bar t uses bars <= t only
(Tier B's B1 uses bar t-1 and bar t)."""
from __future__ import annotations

import numpy as np

from strategy.chartmark.data import avoid_flag                      # noqa: F401
from strategy.chartmark_s.data import (Frame, Ind, bars_since_high, indicators, load_seen_frame,   # noqa: F401
                                       load_training_frame, range_pos)
from strategy.chartmark_s2 import spec as S


def tier_array(fr: Frame, ind: Ind, tiers: str = "AB") -> np.ndarray:
    """int8 per bar: 1 = Tier A (EMA9 < EMA21), 2 = Tier B (EMA9 >= EMA21 and B1-B4), 0 = neither. Not yet combined with X1."""
    n = fr.n
    out = np.zeros(n, np.int8)
    with np.errstate(invalid="ignore"):
        a = ind.e9 < ind.e21
        b1 = np.zeros(n, bool)
        b1[1:] = fr.c[:-1] < ind.e9[:-1]                                # close[t-1] < EMA9[t-1]
        b2 = fr.h >= ind.e9 - S.RETEST_TICKS * S.TICK                   # the bar rallies to EMA9
        b3 = fr.c < ind.e9                                              # and closes back below it
        b4 = ind.hist < 0                                               # MACD below its signal line
        tb = (~a) & b1 & b2 & b3 & b4
        if "A" in tiers:
            out[a] = S.TIER_A
        if "B" in tiers:
            out[tb & (out == 0)] = S.TIER_B
    return out


def context_tiers(fr: Frame, ind: Ind, p: S.Params) -> tuple[np.ndarray, np.ndarray]:
    """(ctx, tier): ctx = X1 & tier in {A, B} [& V-RANGE] [& V-SESSION] [& ~AVOID]; tier = the tier at every ctx bar (0 elsewhere)."""
    key = ("S2", p.x1_window, p.tiers, p.rng, p.session, p.avoid)
    if key in ind._cache:
        return ind._cache[key]
    with np.errstate(invalid="ignore"):
        x1 = bars_since_high(fr.h) <= p.x1_window
        ok = x1 & (tier_array(fr, ind, p.tiers) > 0)
        ok &= ~np.isnan(ind.atr) & ~np.isnan(ind.hist) & ~np.isnan(ind.e21)
        if p.rng:
            ok &= range_pos(fr) >= S.RANGE_MIN
        if p.session:
            ok &= (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
        if p.avoid:
            ok &= ~avoid_flag(fr, ind)
    ok = np.nan_to_num(ok.astype(float), nan=0.0).astype(bool)
    tier = np.where(ok, tier_array(fr, ind, p.tiers), 0).astype(np.int8)
    ind._cache[key] = (ok, tier)
    return ok, tier


def context(fr: Frame, ind: Ind, p: S.Params) -> np.ndarray:
    return context_tiers(fr, ind, p)[0]
