#!/usr/bin/env python3
"""Pivot / trend-line geometry for TL-v0 (REGISTERED_tl_v0.md sec 2.1).

Pure functions: pivots, line construction with the validity/span guard, and
crossover (action-line break) detection. No I/O, no position state -- that
lives in common/tl_v0_preflight.py.

Line construction only ever looks at the two MOST RECENTLY confirmed pivots
of a type. If that pair fails the falling/rising or validity test, there is
NO active line of that type until the next pivot confirms and the (now
newest) pair is retested -- older pivots are not searched for a qualifying
earlier pair. This is a judgement call the registration's text does not
fully pin down and is flagged in the pre-flight report for review before the
step-4 backtest engine is built.
"""
from __future__ import annotations
import numpy as np

from common.indicators import atr as _atr_pine   # ta.rma-based, matches Pine ta.atr

MAX_SPAN = 400
BUFFER_MULT = 0.10


def atr14(h, l, c):
    import pandas as pd
    return _atr_pine(pd.Series(h), pd.Series(l), pd.Series(c), 14).to_numpy()


def find_pivots(vals, R, kind):
    """kind='high' or 'low'. Returns [(pivot_idx, confirm_idx, value), ...],
    confirmed at pivot_idx + R (ta.pivothigh/pivotlow with left=right=R)."""
    n = len(vals)
    out = []
    for i in range(R, n - R):
        w = vals[i - R:i + R + 1]
        if kind == "high" and vals[i] >= w.max():
            out.append((i, i + R, vals[i]))
        elif kind == "low" and vals[i] <= w.min():
            out.append((i, i + R, vals[i]))
    return out


def build_line_series(n, pivots, R, closes, atr, kind):
    """Active line value at every bar (NaN when no active line), from the
    two most recently confirmed pivots of one type."""
    line = np.full(n, np.nan)
    active = None
    last_two = []
    for (pidx, cidx, val) in pivots:
        last_two.append((pidx, val))
        if len(last_two) > 2:
            last_two = last_two[-2:]
        if len(last_two) == 2:
            (p1, v1), (p2, v2) = last_two
            slope = (v2 - v1) / (p2 - p1)
            direction_ok = (v2 < v1) if kind == "high" else (v2 > v1)
            valid = direction_ok and (p2 - p1) <= MAX_SPAN
            if valid:
                for j in range(p1, min(cidx, n - 1) + 1):
                    lv = v2 + slope * (j - p2)
                    if kind == "high":
                        if closes[j] - lv > BUFFER_MULT * atr[j]:
                            valid = False
                            break
                    else:
                        if lv - closes[j] > BUFFER_MULT * atr[j]:
                            valid = False
                            break
            active = (p2, v2, slope) if valid else None
        start = cidx
        if start < n:
            if active is not None:
                ref_idx, ref_val, slope = active
                js = np.arange(start, n)
                line[start:n] = ref_val + slope * (js - ref_idx)
            else:
                line[start:n] = np.nan
    return line


def break_events(c, res, sup, a):
    """Crossover-style breakout detection: close crosses beyond the active
    line by > 0.10*ATR14, first bar of the crossing only."""
    n = len(c)
    ups, downs = np.zeros(n, bool), np.zeros(n, bool)
    for j in range(1, n):
        if not np.isnan(res[j]) and (c[j] - res[j]) > BUFFER_MULT * a[j]:
            prev_ok = np.isnan(res[j - 1]) or (c[j - 1] - res[j - 1]) <= BUFFER_MULT * a[j - 1]
            if prev_ok:
                ups[j] = True
        if not np.isnan(sup[j]) and (sup[j] - c[j]) > BUFFER_MULT * a[j]:
            prev_ok = np.isnan(sup[j - 1]) or (sup[j - 1] - c[j - 1]) <= BUFFER_MULT * a[j - 1]
            if prev_ok:
                downs[j] = True
    return ups, downs


def swing_fallback(pivots_low, pivots_high, high_arr, low_arr, atr, R, idx,
                    entry_px, direction):
    """Fallback initial stop, REGISTERED_tl_v0 sec 2.1 'Initial stop,
    fallback' row -- used when no opposing line is active at entry."""
    if direction == "long":
        confirmed = [p for p in pivots_low if p[1] < idx]
        if confirmed:
            swing = confirmed[-1][2]
            if swing < entry_px:
                return swing - 0.25 * atr[idx]
        lo = max(0, idx - (2 * R + 1))
        window = low_arr[lo:idx] if idx > lo else low_arr[max(0, idx - 1):idx + 1]
        return None if len(window) == 0 else window.min() - 0.25 * atr[idx]
    else:
        confirmed = [p for p in pivots_high if p[1] < idx]
        if confirmed:
            swing = confirmed[-1][2]
            if swing > entry_px:
                return swing + 0.25 * atr[idx]
        lo = max(0, idx - (2 * R + 1))
        window = high_arr[lo:idx] if idx > lo else high_arr[max(0, idx - 1):idx + 1]
        return None if len(window) == 0 else window.max() + 0.25 * atr[idx]
