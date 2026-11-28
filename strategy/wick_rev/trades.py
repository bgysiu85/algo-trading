#!/usr/bin/env python3
"""WICK-REV trade-shaped translation in dollars. W15-0063, REGISTERED_wick_reversal.md sec 4.

For each primary-group signal at bar t: SHORT (side +1) or LONG (side -1), 1 contract, entered at the
OPEN of t+1. Stop = entry +/- 1 x ATR(t), target = entry -/+ 1 x ATR(t), time exit at the CLOSE of t+3.
A gap through the stop or target (bars after the entry bar) fills at that bar's open. A same-bar double
touch is resolved on finer bars where owned, otherwise STOP FIRST. One position at a time per
market / timeframe / direction: a signal at bar s is skipped if the open trade has not exited before
the close of s (exit bar > s). Prices are back-adjusted (differences are exact; levels are not the
quoted prices). Stops and targets are not rounded to the tick.
"""
from __future__ import annotations

import numpy as np

from strategy.wick_rev import spec as S
from strategy.wick_rev.signals import Features, Series


def _double_touch(s: Series, j: int, stop: float, target: float, side: int) -> str:
    """Which of stop / target is touched first inside bar j, from finer bars; 'stop' when unknowable."""
    if s.fine_t is None:
        return "stop"
    lo = np.searchsorted(s.fine_t, s.t_open[j], side="left")
    hi = np.searchsorted(s.fine_t, s.t_end[j], side="left")
    if hi <= lo:
        return "stop"
    fh, fl = s.fine_h[lo:hi], s.fine_l[lo:hi]
    if side == 1:                       # short: stop above, target below
        ts, tt = fh >= stop, fl <= target
    else:                               # long: stop below, target above
        ts, tt = fl <= stop, fh >= target
    anyt = ts | tt
    if not anyt.any():
        return "stop"
    i = int(np.argmax(anyt))
    if ts[i] and tt[i]:
        return "stop"
    return "stop" if ts[i] else "target"


def simulate(s: Series, f: Features, idx: np.ndarray, side: int) -> dict:
    """Walk the primary-group signals `idx` (sorted) in order. Returns trade arrays and the skipped count."""
    usd = S.MARKETS[s.market]["usd_per_point"]
    rows = []
    busy_until = -1                      # bar index at which the open trade exits
    skipped = 0
    for t in idx.tolist():
        if t < busy_until:
            skipped += 1
            continue
        e = t + 1
        entry = s.o[e]
        atr = f.atr[t]
        if side == 1:
            stop, target = entry + atr, entry - atr
        else:
            stop, target = entry - atr, entry + atr
        exit_px, reason, xb = None, "time", t + S.WINDOW
        for j in range(e, t + S.WINDOW + 1):
            if j > e:                                   # a gap can only happen after the entry bar
                if (side == 1 and s.o[j] >= stop) or (side == -1 and s.o[j] <= stop):
                    exit_px, reason, xb = s.o[j], "stop-gap", j
                    break
                if (side == 1 and s.o[j] <= target) or (side == -1 and s.o[j] >= target):
                    exit_px, reason, xb = s.o[j], "target-gap", j
                    break
            hit_s = (s.h[j] >= stop) if side == 1 else (s.l[j] <= stop)
            hit_t = (s.l[j] <= target) if side == 1 else (s.h[j] >= target)
            if hit_s and hit_t:
                first = _double_touch(s, j, stop, target, side)
                exit_px, reason, xb = (stop, "stop", j) if first == "stop" else (target, "target", j)
                break
            if hit_s:
                exit_px, reason, xb = stop, "stop", j
                break
            if hit_t:
                exit_px, reason, xb = target, "target", j
                break
        if exit_px is None:
            exit_px, reason, xb = s.c[t + S.WINDOW], "time", t + S.WINDOW
        gross = (entry - exit_px) * usd if side == 1 else (exit_px - entry) * usd
        busy_until = xb
        rows.append((t, s.session[t], entry, exit_px, reason, gross))
    n = len(rows)
    out = {"signal_bar": np.array([r[0] for r in rows], dtype=int),
           "signal_date": np.array([r[1] for r in rows], dtype="datetime64[D]") if n else np.zeros(0, "datetime64[D]"),
           "entry": np.array([r[2] for r in rows], float), "exit": np.array([r[3] for r in rows], float),
           "reason": np.array([r[4] for r in rows], dtype=object),
           "gross": np.array([r[5] for r in rows], float), "skipped": skipped}
    rt = {lv: 2 * S.side_cost(s.market, lv) for lv in S.LEVELS}          # round trip, 1 contract
    out["cost"] = {lv: rt[lv] for lv in S.LEVELS}
    out["net"] = {lv: out["gross"] - rt[lv] for lv in S.LEVELS}
    return out
