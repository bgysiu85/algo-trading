#!/usr/bin/env python3
"""Shorts for the long-only rule engine (exitmgr/rules.py), by reflection (W15-0053 sub 4a; the sub 2 handover left the
short mirror to sub 4).

A short trade on bars X is the long trade on X reflected about the entry price P: every price p becomes 2P - p, so highs and
lows swap (h' = 2P - l, l' = 2P - h), opens and closes reflect, EMAs reflect (an EMA is a weighted average whose weights sum
to 1), the MACD histogram changes sign (a difference of EMAs), and ATR is unchanged (true range is a distance). The long
rule's sell-stop level L on the reflected bars is the short's buy-stop level 2P - L; a long "market sell at the next open"
is the short's "market buy at the next open". rules.py itself is imported unchanged.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np


def reflect(x, pivot: float):
    return 2.0 * pivot - np.asarray(x, float)


def mirror_bars(b, pivot: float):
    """The reflected copy of a bar object (o, h, l, c, atr, e9, e21, hist)."""
    return SimpleNamespace(o=reflect(b.o, pivot), h=reflect(b.l, pivot), l=reflect(b.h, pivot), c=reflect(b.c, pivot),
                           atr=np.asarray(b.atr, float).copy(), e9=reflect(b.e9, pivot), e21=reflect(b.e21, pivot),
                           hist=-np.asarray(b.hist, float))


def short_inputs(entry: float, s0: float) -> tuple[float, float]:
    """(entry, initial stop) of a short as the reflected long sees them: entry stays, the stop above becomes a stop below."""
    return entry, 2.0 * entry - s0


def to_short_level(level: float, pivot: float) -> float:
    """A long sell-stop level on reflected bars -> the short's buy-stop level on real bars."""
    return 2.0 * pivot - level
