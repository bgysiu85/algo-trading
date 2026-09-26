#!/usr/bin/env python3
"""HTF-Ben v1's per-bar entry building blocks: hist/spread series, the two
trigger routes (E1a cross, E1b curl), the new E2 confirmation, and F1's
range-ratio series. W15-0011, REGISTERED_htf_ben_v1.md sec 2.1.

NO P&L, NO STATE MACHINE HERE, same split as v0's signals.py vs preflight.py:
this module produces per-bar arrays/series; strategy/htf/v1_preflight.py
turns them into the one-trigger-at-a-time walk, the G2 counts, and (once T
and F2 are folded in from v1_lines.py) the final entries.

WHICH CHART EACH RULE RUNS ON -- AN ASSUMPTION FLAGGED, SAME SPIRIT AS
v1_lines.py's OWN NOTE
------------------------------------------------------------------------
Sec 2's Notation defines hist/spread/ATR once, ending "... ATR = ATR(14) on
the 4-hour back-adjusted series" -- read together with sec 2.1's E1a/E1b/E2
row sources ("v0 E1", "W15-0008: ...", inheriting v0's own Amendment 0,
which already reads "4-hour bar" as "the scenario's own entry-chart bar" for
these MACD/EMA rules) and F1/F2's own explicit "four-hour bars ending at c"
wording, this module reads it as a SPLIT, matching v1_lines.py's precedent
(T and F2 already pinned to the 4-hour frame there) and W15-0007's v0-TL
precedent (the trend-line gate always on 4H, everything else on the
scenario's own chart):

  - E1a (cross), E1b (curl trigger), E2 (confirmation) -- computed from
    hist/ema9/spread on the SCENARIO'S OWN ENTRY CHART (entry_chart_
    indicators below), exactly like v0's E1/E2 always were.
  - F1's own ratio test, T (via v1_lines) and F2 (via v1_lines) -- always
    on the fixed 4-hour frame (four_h_indicators below), mapped to each
    entry-chart bar's own last-closed-4H bar via
    strategy.htf.tl_variant.map_to_last_closed_4h, same as v1_lines.py.

This is a judgement call the registered text does not fully pin down;
flagged here rather than silently assumed, and checked by
tests/strategy/htf/test_v1_signals.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import signals as SIG

F1_WINDOW_4H = 9   # REGISTERED sec 2.1 F1: "N = 9 four-hour bars"


# --- indicators --------------------------------------------------------

def entry_chart_indicators(entry_adj: pd.DataFrame):
    """(macd_line, signal_line, hist, ema9, ema21, spread) on the scenario's
    own entry chart, all SMA-seeded per v0's E7 (reuses signals.py's
    macd_seeded/ema_seeded unchanged -- REGISTERED sec 2 preamble: 'E7
    indicator seeding and warm-up' is inherited from v0)."""
    close = entry_adj["close_adj"]
    macd_line, signal_line = SIG.macd_seeded(close)
    hist = macd_line - signal_line
    ema9 = SIG.ema_seeded(close, SIG.EMA_FAST)
    ema21 = SIG.ema_seeded(close, SIG.EMA_SLOW)
    spread = ema9 - ema21
    return macd_line, signal_line, hist, ema9, ema21, spread


def four_h_indicators(four_h_adj: pd.DataFrame):
    """(hist_4h, spread_4h) -- the same MACD-histogram / EMA9-EMA21 spread,
    computed on the fixed 4-hour frame for F1's own ratio test (see module
    docstring). Returned as plain numpy arrays (F1's ratio series works
    positionally against v1_lines.build_4h_lines' own atr array)."""
    close = four_h_adj["close_adj"]
    macd_line, signal_line = SIG.macd_seeded(close)
    hist_4h = (macd_line - signal_line).to_numpy(dtype=float)
    ema9 = SIG.ema_seeded(close, SIG.EMA_FAST)
    ema21 = SIG.ema_seeded(close, SIG.EMA_SLOW)
    spread_4h = (ema9 - ema21).to_numpy(dtype=float)
    return hist_4h, spread_4h


# --- E1a cross route / E1b curl route triggers --------------------------

def curl_trigger_series(hist: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(curl_long, curl_short) at bar t (E1b): long -- hist[t] < 0 and hist
    has risen 2 bars in a row (hist[t-2] < hist[t-1] < hist[t]), MACD
    curling up toward its signal before crossing. Short is the mirror:
    hist[t] > 0 and hist[t-2] > hist[t-1] > hist[t]. Uses only t, t-1, t-2,
    all closed by t's own close."""
    h = hist
    h1, h2 = h.shift(1), h.shift(2)
    rising_2 = (h2 < h1) & (h1 < h)
    falling_2 = (h2 > h1) & (h1 > h)
    curl_long = ((h < 0) & rising_2).fillna(False)
    curl_short = ((h > 0) & falling_2).fillna(False)
    return curl_long, curl_short


# --- E2 confirmation (replaces v0 E2) -----------------------------------

def e2_confirms(ema9: pd.Series, spread: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(confirms_long, confirms_short) at bar c (E2): long -- EMA9[c] >
    EMA9[c-1] and spread[c] > spread[c-1]. Short is the mirror (both <).
    Sec 2.1: 'Covers EMA9 rising toward EMA21 from below and EMA9 widening
    above it; rejects EMA9 converging from above.'"""
    ema9_up = ema9 > ema9.shift(1)
    ema9_down = ema9 < ema9.shift(1)
    spread_up = spread > spread.shift(1)
    spread_down = spread < spread.shift(1)
    confirms_long = (ema9_up & spread_up).fillna(False)
    confirms_short = (ema9_down & spread_down).fillna(False)
    return confirms_long, confirms_short


# --- F1 no-range ratio series --------------------------------------------

def f1_ratio_series(hist_4h: np.ndarray, spread_4h: np.ndarray, atr_4h: np.ndarray,
                    window: int = F1_WINDOW_4H) -> tuple[np.ndarray, np.ndarray]:
    """(ratio_h, ratio_e) on the 4-hour frame: ratio_h[j] = max(|hist_4h|)
    over the `window` 4-hour bars ending at j (inclusive) / atr_4h[j];
    ratio_e[j] mirrors it for spread_4h. NaN where atr_4h[j] is NaN/0 or
    the window has no valid reading yet. These are BOTH the raw values G2
    takes percentiles of (q_h, q_e, over all training-side bars) and the
    values F1 itself compares a trigger's own t4 reading against."""
    n = len(hist_4h)
    ratio_h = np.full(n, np.nan)
    ratio_e = np.full(n, np.nan)
    hist_abs = np.abs(hist_4h)
    spread_abs = np.abs(spread_4h)
    for j in range(n):
        if np.isnan(atr_4h[j]) or atr_4h[j] == 0:
            continue
        lo = max(0, j - window + 1)
        seg_h = hist_abs[lo:j + 1]
        seg_e = spread_abs[lo:j + 1]
        if np.isnan(seg_h).all():
            continue
        ratio_h[j] = np.nanmax(seg_h) / atr_4h[j]
        ratio_e[j] = np.nanmax(seg_e) / atr_4h[j]
    return ratio_h, ratio_e


def f1_blocked_at(t4: int, ratio_h: np.ndarray, ratio_e: np.ndarray,
                  q_h: float, q_e: float) -> bool:
    """True iff F1 blocks (skip: 'blocked_range') the trigger whose own
    last-closed-4H bar is t4: both ratios at t4 are at or below their
    training-side percentile thresholds. NaN at t4 (still in 4H warm-up) ->
    not blocked (there is nothing yet to call a flat range)."""
    if t4 < 0 or t4 >= len(ratio_h):
        return False
    rh, re = ratio_h[t4], ratio_e[t4]
    if np.isnan(rh) or np.isnan(re):
        return False
    return bool(rh <= q_h and re <= q_e)
