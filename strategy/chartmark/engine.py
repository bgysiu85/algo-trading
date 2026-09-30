#!/usr/bin/env python3
"""CHARTMARK-v1 long engine: intrabar stop orders on 1H bars. REGISTERED_chartmark_v1.md sec 2 (+ Amendment A).

Two pieces: run_position() walks one open position bar by bar (exits), simulate() finds entries with the
buy-stop order machine (E1-E5) and calls it. Every rule below reads bars <= t for anything decided at the close of t.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from strategy.chartmark import spec as S
from strategy.chartmark.data import Frame, Ind, context

TICK = S.TICK


@dataclass
class Trade:
    entry_j: int
    exit_j: int
    entry_px: float
    exit_px: float
    stop0: float
    a0: float
    reason: str            # S / P1 / P2 / R / V-STALL / data_end
    phase: int             # highest phase reached (0/1/2)
    n_rolls: int
    placed_j: int = -1     # bar at whose close the order was first placed (-1 = random entry)
    gap_fill: bool = False
    stop_from_entry_bar: bool = False


def _hh(x: np.ndarray, t: int, L: int) -> float:
    return float(x[max(0, t - L + 1): t + 1].max())


def _ll(x: np.ndarray, t: int, L: int) -> float:
    return float(x[max(0, t - L + 1): t + 1].min())


def initial_stop(fr: Frame, e: int, L: int) -> tuple[float, bool]:
    """Sec 2.3: lowest low of the L bars ending at the entry bar, minus a tick."""
    s = _ll(fr.l, e, L) - TICK
    own = fr.l[e] <= (_ll(fr.l, e - 1, L - 1) if L > 1 and e >= 1 else np.inf)
    return s, bool(own)


def run_position(fr: Frame, ind: Ind, p: S.Params, e: int, entry_px: float, a0: float, stop0: float,
                 placed_j: int = -1, gap_fill: bool = False, own_low: bool = False) -> Trade:
    """Walk bars e+1.. until an exit. Orders working for bar j are fixed from data <= j-1 (sec 2.4 clarification)."""
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    maxc = c[e]
    phase = 0
    max_phase = 0
    r_orders: list[tuple[float, int]] = []          # (level, last live bar)
    stall_level = None
    for j in range(e + 1, n):
        levels = [(stop0, 0, "S")]
        if phase >= 1:
            ema = ind.e21 if (phase == 2 and p.p2) else ind.e9
            lv = ema[j - 1]
            if not np.isnan(lv):
                levels.append((lv, 1, "P2" if (phase == 2 and p.p2) else "P1"))
        for lvl, last in r_orders:
            if last >= j:
                levels.append((lvl, 2, "R"))
        stall_limit = None
        if stall_level is not None:
            if stall_level <= c[j - 1]:
                levels.append((stall_level, 3, "V-STALL"))
            else:
                stall_limit = stall_level
        # highest sell-stop triggers first as price falls; ties resolve S, P, R, V-STALL by prio index above
        best = max(levels, key=lambda x: (x[0], -x[1]))
        lvl, _, why = best
        if o[j] <= lvl:
            return _done(e, j, entry_px, o[j], stop0, a0, why, max_phase, fr, placed_j, gap_fill, own_low)
        if l[j] <= lvl:
            return _done(e, j, entry_px, lvl, stop0, a0, why, max_phase, fr, placed_j, gap_fill, own_low)
        if stall_limit is not None and h[j] >= stall_limit:
            return _done(e, j, entry_px, max(stall_limit, o[j]), stop0, a0, "V-STALL", max_phase, fr, placed_j,
                         gap_fill, own_low)
        # ---- close of bar j: update what will be working for j+1 ----
        maxc = max(maxc, c[j])
        trav = (maxc - entry_px) / a0
        if trav >= p.p1_arm:
            phase = max(phase, 1)
        if p.p2 and trav >= p.p2_arm:
            phase = 2
        max_phase = max(max_phase, phase)
        if p.r:
            rng = h[j] - l[j]
            wick = h[j] - max(o[j], c[j])
            if rng > 0 and wick >= S.R_WICK * rng and rng >= S.R_MIN_RANGE * a0:
                r_orders.append((min(o[j], c[j]) - TICK, j + S.R_LIFE))
        if p.stall_n and stall_level is None and phase == 0 and j == e + p.stall_n:
            if c[e: j + 1].max() < entry_px + S.STALL_PROGRESS * a0:
                stall_level = entry_px + p.stall_rt
        if stall_level is not None and phase >= 1:
            stall_level = None
    return _done(e, n - 1, entry_px, c[n - 1], stop0, a0, "data_end", max_phase, fr, placed_j, gap_fill, own_low)


def _done(e, x, entry_px, exit_px, stop0, a0, why, max_phase, fr, placed_j, gap_fill, own_low) -> Trade:
    rolls = int(fr.roll_after[e:x].sum()) if x > e else 0
    return Trade(e, x, float(entry_px), float(exit_px), float(stop0), float(a0), why, int(max_phase), rolls,
                 placed_j, gap_fill, own_low)


def simulate(fr: Frame, ind: Ind, p: S.Params = S.BASE, *, start: int = 0) -> tuple[list[Trade], dict]:
    """Entry order machine (sec 2.1-2.2, E1-E5). Returns (trades, counts)."""
    ctx = context(fr, ind, p)
    n = fr.n
    o, h = fr.o, fr.h
    cnt = dict(orders=0, fills=0, timeouts=0, ctx_cancels=0, roll_cancels=0, resets=0, gap_fills=0,
               same_bar_touch=0, stop_from_entry_bar=0)
    trades: list[Trade] = []
    pending = None                  # [level, placed_j]
    need_false = False
    t = max(start, 1)
    while t < n - 1:
        if pending is not None:
            lvl, j0 = pending
            if h[t] >= lvl:                                   # E4
                fill = max(lvl, o[t])
                a0 = ind.atr[t - 1]
                stop0, own = initial_stop(fr, t, p.stop_lookback)
                cnt["fills"] += 1
                cnt["gap_fills"] += int(o[t] > lvl)
                cnt["stop_from_entry_bar"] += int(own)
                cnt["same_bar_touch"] += int(fr.l[t] <= stop0)
                tr = run_position(fr, ind, p, t, fill, a0, stop0, j0, o[t] > lvl, own)
                trades.append(tr)
                pending = None
                t = tr.exit_j                                 # flat again at the close of the exit bar
                if t >= n - 1:
                    break
        # ---- close of bar t ----
        if not ctx[t]:
            need_false = False
        if pending is not None:
            if fr.roll_after[t]:
                pending = None; cnt["roll_cancels"] += 1
            elif not ctx[t]:
                pending = None; cnt["ctx_cancels"] += 1
            elif t - pending[1] >= p.K:                       # E3
                pending = None; cnt["timeouts"] += 1; need_false = True
            else:                                             # E2 re-set, can only rise
                new = _hh(h, t, p.e1_lookback) + TICK
                if new > pending[0]:
                    cnt["resets"] += 1
                pending[0] = max(pending[0], new)
        elif ctx[t] and not need_false and not fr.roll_after[t]:
            pending = [_hh(h, t, p.e1_lookback) + TICK, t]
            cnt["orders"] += 1
        t += 1
    return trades, cnt
