#!/usr/bin/env python3
"""CHARTMARK-S v1 engine: intrabar stop orders on 1H bars, SHORT only. REGISTERED_chartmark_short_v1.md sec 2.

run_position() walks one open short bar by bar (backstop, P0 cut, P1 retest); simulate() is the sell-stop order machine
(E1-E5). Orders working in bar j are fixed from data <= j-1 (EMA9[j-1], the poke high after its bar closed)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from strategy.chartmark_s import spec as S
from strategy.chartmark_s.data import Frame, Ind, context

TICK = S.TICK


@dataclass
class Trade:
    entry_j: int
    exit_j: int
    entry_px: float
    exit_px: float
    stop0: float            # backstop
    a0: float
    reason: str             # P0 / P1 / C9 / S / data_end
    phase: int              # 1 if P1 was reached
    n_rolls: int
    placed_j: int = -1
    gap_fill: bool = False
    same_bar: bool = False


def backstop(fr: Frame, e: int, n: int = 20) -> float:
    """Sec 2.3: highest high of the n bars ending at the entry bar (inclusive) + 1 tick."""
    return float(fr.h[max(0, e - n + 1): e + 1].max()) + TICK


def run_position(fr: Frame, ind: Ind, p: S.Params, e: int, entry_px: float, a0: float, stop0: float,
                 placed_j: int = -1, gap_fill: bool = False) -> Trade:
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    e9 = ind.e9
    minc = c[e]
    armed = (entry_px - c[e]) / a0 >= p.p1_arm
    pokes, poke_hi = 0, None
    reached = armed
    for j in range(e + 1, n):
        lv = e9[j - 1] + S.POKE_TICKS * TICK
        levels = [(stop0, "S")]
        if not armed:
            if not p.wide:
                levels.append((e9[j - 1] + p.cut_ticks * TICK, "P0"))
        elif p.close9:
            if c[j - 1] > e9[j - 1]:
                levels.append((o[j], "C9"))
        elif pokes >= 1:
            levels.append((min(lv, poke_hi - TICK), "P1"))
        hits = [(max(x, o[j]), w) for x, w in levels if h[j] >= x]
        if hits:
            px, why = min(hits)
            return _done(e, j, entry_px, px, stop0, a0, why, reached, fr, placed_j, gap_fill)
        # ---- close of bar j ----
        if armed and h[j] > lv and not p.close9:
            pokes += 1
            if poke_hi is None:
                poke_hi = h[j]
        minc = min(minc, c[j])
        if (entry_px - minc) / a0 >= p.p1_arm:
            armed = True
            reached = True
    return _done(e, n - 1, entry_px, c[n - 1], stop0, a0, "data_end", reached, fr, placed_j, gap_fill)


def _done(e, x, entry_px, exit_px, stop0, a0, why, reached, fr, placed_j, gap_fill) -> Trade:
    rolls = int(fr.roll_after[e:x].sum()) if x > e else 0
    return Trade(e, x, float(entry_px), float(exit_px), float(stop0), float(a0), why, int(bool(reached)), rolls,
                 placed_j, gap_fill, False)


def simulate(fr: Frame, ind: Ind, p: S.Params = S.BASE, *, start: int = 40) -> tuple[list[Trade], dict]:
    """Sell-stop order machine, sec 2.1-2.2 (E1-E5). Returns (trades, counts)."""
    ctx = context(fr, ind, p)
    n = fr.n
    o, l = fr.o, fr.l
    cnt = dict(orders=0, fills=0, timeouts=0, ctx_cancels=0, roll_cancels=0, resets=0, gap_fills=0,
               reentries=0, same_bar=0, ev=[])
    ev = cnt["ev"]                  # (kind, bar) events, for the per-year table
    trades: list[Trade] = []
    pending = None                  # [level, placed_j]
    need_false = False
    t = max(start, 1)
    while t < n - 1:
        if pending is not None:
            lvl, j0 = pending
            if l[t] <= lvl:                                       # E4: sell-stop through the level
                fill = min(lvl, o[t])
                a0 = ind.atr[t - 1]
                stop0 = backstop(fr, t, p.backstop_n)
                cnt["fills"] += 1
                cnt["gap_fills"] += int(o[t] < lvl)
                cnt["reentries"] += int(bool(trades) and j0 == trades[-1].exit_j)
                tr = run_position(fr, ind, p, t, fill, a0, stop0, j0, o[t] < lvl)
                trades.append(tr)
                pending = None
                need_false = False
                t = tr.exit_j                                     # flat again at the close of the exit bar (E5)
                if t >= n - 1:
                    break
        # ---- close of bar t ----
        if not ctx[t]:
            need_false = False
        if pending is not None:
            if fr.roll_after[t]:
                pending = None; cnt["roll_cancels"] += 1; ev.append(("roll", t))
            elif not ctx[t]:
                pending = None; cnt["ctx_cancels"] += 1; ev.append(("cancel", t))
            elif t - pending[1] >= p.K:                           # E3
                pending = None; cnt["timeouts"] += 1; need_false = True; ev.append(("timeout", t))
            else:                                                 # E2 re-set, may move up or down
                new = float(fr.l[t]) - TICK
                if new != pending[0]:
                    cnt["resets"] += 1
                pending[0] = new
        elif ctx[t] and not need_false and not fr.roll_after[t]:
            pending = [float(fr.l[t]) - TICK, t]
            cnt["orders"] += 1; ev.append(("order", t))
        t += 1
    return trades, cnt
