#!/usr/bin/env python3
"""BREIT-CAP runs, grade and orders as arrays (REGISTERED_breit_cap.md sec 2.2-2.4). No fills, no P&L.

Everything at close t uses bars <= t (G4). Long setup after a down-run; the short setup is the
mirror throughout (runs of bars each HOLDING PRIOR LOWS, an up-move of >= 3 ATR, a close above the
upper band, a sell-stop at the prior bar's low - 1 tick, a stop above the run's highest high).

Definitions
-----------
Q1  k = the number of consecutive bars ending at t with high[i] <= high[i-1] (long). k >= k_min.
    O = t - k is the origin bar (the bar before the run's first bar).
Q2  D = high[O] - min(low over the run) >= q2 x ATR[O]      (ATR measured at the origin).
Q3  at least one close in the run is below the lower Bollinger (20, q3_sd) band AT THAT BAR.
A run is "qualified" at every close where Q1-Q3 hold; each such close carries one order for t + 1.
Both sides qualifying on one bar (nested inside bars with a huge range) place NO order (counted).

Grade factors (sec 2.3), measured at the qualifying close t:
  speed   max true range of bars t-1, t >= 1.5 x ATR[O]
  legs    >= 3 down-legs from the 60-bar high (latest occurrence in t-59..t) to t; a zigzag with a
          reversal of 1.0 x ATR[O]. A leg counts once its decline from its own start extreme reaches the
          reversal; a bounce of that size off its low ends it; a fall of that size from the bounce
          high starts the next. The leg in progress at t counts.
  volume  max over bars t-2..t of vol[i] / mean(vol[i-20..i-1]) >= 2.0  (NaN volume -> no)
  boring  ATR[O]/rc[O] <= median of ATR[j]/rc[j] over j = O-250..O-1 (needs all 250; else no)
  long    k >= 6
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.breit_cap import spec as S
from strategy.futbt.core import Frame, bollinger


@dataclass
class Signals:
    n: int
    params: S.Params
    ok: np.ndarray                 # (2, n) bool: side index 0 = long, 1 = short; a qualified order at close t
    entry: np.ndarray              # (2, n) buy/sell-stop LEVEL for bar t+1
    stop: np.ndarray               # (2, n) initial stop LEVEL
    grade: np.ndarray              # (2, n) int
    k: np.ndarray                  # (2, n) run length
    d_atr: np.ndarray              # (2, n) D / ATR[O]
    run_id: np.ndarray             # (2, n) first bar of the run (identifies it)
    tgt50: np.ndarray              # (2, n) 50% retrace level of the whole move
    mid: np.ndarray                # Bollinger middle (SMA20) for the MA-target variant
    atr: np.ndarray
    counts: dict = field(default_factory=dict)
    runs: list = field(default_factory=list)


def true_range(h, l, c):
    pc = np.r_[c[0], c[:-1]]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def zigzag_legs(h, l, start: int, t: int, thr: float) -> int:
    """Down-legs from bar `start` (a swing high) to t, counted with a zigzag of reversal `thr`."""
    if not np.isfinite(thr) or thr <= 0:
        return 0
    peak = h[start]
    low_run = peak
    legs, counted, state = 0, False, "down"
    high_run = peak
    for i in range(start + 1, t + 1):
        if state == "down":
            low_run = min(low_run, l[i])
            if not counted and low_run <= peak - thr:
                legs += 1
                counted = True
            if counted and h[i] >= low_run + thr:
                state, high_run = "up", h[i]
        else:
            high_run = max(high_run, h[i])
            if l[i] <= high_run - thr:
                state, peak, low_run, counted = "down", high_run, l[i], False
                if low_run <= peak - thr:
                    legs += 1
                    counted = True
    return legs


def volume_ratio(vol: np.ndarray) -> np.ndarray:
    s = pd.Series(vol)
    avg = s.shift(1).rolling(S.VOL_AVG, min_periods=S.VOL_AVG).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (s / avg).to_numpy()
    return r


def volume_coverage(vol: np.ndarray) -> float:
    v = np.asarray(vol, float)
    return float(np.mean(np.isfinite(v) & (v > 0))) if len(v) else 0.0


def compute(fr: Frame, p: S.Params = S.PRIMARY) -> Signals:
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    tick = fr.tick
    atr = fr.atr()
    mid, _, lo_band = bollinger(c, S.BB_LEN, p.q3_sd)
    _, up_band, _ = bollinger(c, S.BB_LEN, p.q3_sd)
    tr = true_range(h, l, c)
    vr = volume_ratio(fr.vol)
    ratio = atr / fr.rc
    med = pd.Series(ratio).shift(1).rolling(S.BORING_WIN, min_periods=S.BORING_WIN).median().to_numpy()

    ok = np.zeros((2, n), bool)
    entry = np.full((2, n), np.nan)
    stop = np.full((2, n), np.nan)
    grade = np.full((2, n), -1, np.int64)
    kk = np.zeros((2, n), np.int64)
    dat = np.full((2, n), np.nan)
    run_id = np.full((2, n), -1, np.int64)
    tgt50 = np.full((2, n), np.nan)
    cnt = dict(q1_runs_long=0, q1_runs_short=0, qualified_runs_long=0, qualified_runs_short=0,
               runs_fail_q2_long=0, runs_fail_q2_short=0, runs_fail_q3_long=0, runs_fail_q3_short=0,
               orders_long=0, orders_short=0, both_sides_no_order=0)
    runs: list[dict] = []

    for s, sd_ in ((0, 1), (1, -1)):
        hold = np.zeros(n, bool)                     # long: high <= prior high ; short: low >= prior low
        hold[1:] = (h[1:] <= h[:-1]) if sd_ == 1 else (l[1:] >= l[:-1])
        beyond = np.zeros(n, bool)
        with np.errstate(invalid="ignore"):
            beyond = (c < lo_band) if sd_ == 1 else (c > up_band)
        beyond = np.where(np.isfinite(lo_band) & np.isfinite(up_band), beyond, False)
        cum_beyond = np.cumsum(beyond)
        runlen = np.zeros(n, np.int64)
        for t in range(1, n):
            runlen[t] = runlen[t - 1] + 1 if hold[t] else 0
        cur = None
        for t in range(n):
            k = int(runlen[t])
            if k < p.k_min:
                cur = None
                continue
            O = t - k
            if O < 0 or not np.isfinite(atr[O]) or atr[O] <= 0:
                continue
            first = O + 1
            if cur is None or cur["start"] != first:
                cur = dict(side=sd_, start=first, end=t, k_max=k, q2_ever=False, q3_ever=False, qualified=False)
                runs.append(cur)
                cnt["q1_runs_long" if sd_ == 1 else "q1_runs_short"] += 1
            cur["end"], cur["k_max"] = t, k
            if sd_ == 1:
                extreme = l[first:t + 1].min()
                D = h[O] - extreme
            else:
                extreme = h[first:t + 1].max()
                D = extreme - l[O]
            q2 = D >= p.q2 * atr[O]
            q3 = (cum_beyond[t] - cum_beyond[O]) > 0
            cur["q2_ever"] |= bool(q2)
            cur["q3_ever"] |= bool(q3)
            if p.require_q2q3 and not (q2 and q3):
                continue
            cur["qualified"] = True
            # --- grade ---
            g = 0
            g += int(max(tr[t - 1], tr[t]) >= S.G_SPEED_TR * atr[O])
            w0 = max(0, t - S.LEG_WINDOW + 1)
            if sd_ == 1:
                swing = w0 + int(len(h[w0:t + 1]) - 1 - np.argmax(h[w0:t + 1][::-1]))
                legs = zigzag_legs(h, l, swing, t, S.LEG_ATR * atr[O])
            else:
                swing = w0 + int(len(l[w0:t + 1]) - 1 - np.argmax((-l[w0:t + 1])[::-1]))
                legs = zigzag_legs(-l, -h, swing, t, S.LEG_ATR * atr[O])
            g += int(legs >= S.G_LEGS_MIN)
            v3 = vr[max(0, t - 2):t + 1]
            g += int(np.isfinite(v3).any() and np.nanmax(v3) >= S.G_VOL_X)
            g += int(np.isfinite(med[O]) and np.isfinite(ratio[O]) and ratio[O] <= med[O])
            g += int(k >= S.G_LONG_RUN)
            ok[s, t] = True
            grade[s, t], kk[s, t], dat[s, t], run_id[s, t] = g, k, D / atr[O], first
            if sd_ == 1:
                entry[s, t] = h[t] + S.TICKS_BEYOND * tick
                stop[s, t] = extreme - S.TICKS_BEYOND * tick
                tgt50[s, t] = extreme + 0.5 * D
            else:
                entry[s, t] = l[t] - S.TICKS_BEYOND * tick
                stop[s, t] = extreme + S.TICKS_BEYOND * tick
                tgt50[s, t] = extreme - 0.5 * D
            cnt["orders_long" if sd_ == 1 else "orders_short"] += 1

    both = ok[0] & ok[1]
    if both.any():
        cnt["both_sides_no_order"] = int(both.sum())
        ok[:, both] = False
    for r in runs:
        sfx = "long" if r["side"] == 1 else "short"
        if r["qualified"]:
            cnt[f"qualified_runs_{sfx}"] += 1
        else:
            if not r["q2_ever"]:
                cnt[f"runs_fail_q2_{sfx}"] += 1
            if not r["q3_ever"]:
                cnt[f"runs_fail_q3_{sfx}"] += 1
    return Signals(n, p, ok, entry, stop, grade, kk, dat, run_id, tgt50, mid, atr, cnt, runs)
