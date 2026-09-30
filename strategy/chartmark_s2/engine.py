#!/usr/bin/env python3
"""CHARTMARK-S v2 engine. REGISTERED_chartmark_short_v2.md sec 2. The order machine (E1-E5), the backstop and the exits
(P0 / P1) are CHARTMARK-S v1's, called unchanged (strategy.chartmark_s.engine.run_position / backstop); only the context
(tiers) differs, and every trade is tagged with its tier (spec K4)."""
from __future__ import annotations

from dataclasses import dataclass, fields

from strategy.chartmark_s.engine import Trade, backstop, run_position
from strategy.chartmark_s2 import spec as S
from strategy.chartmark_s2.data import Frame, Ind, context_tiers

TICK = S.TICK


@dataclass
class TradeT(Trade):
    tier: int = 0            # 1 = Tier A, 2 = Tier B (tier on the last context bar)


def simulate(fr: Frame, ind: Ind, p: S.Params = S.BASE, *, start: int = 40, ctx_fn=None) -> tuple[list[TradeT], dict]:
    """Sell-stop order machine, sec 2.2 (v1 E1-E5). Returns (trades, counts); counts carry by-tier order / fill tallies."""
    ctx, tier = (ctx_fn or context_tiers)(fr, ind, p)          # ctx_fn: v3 swaps in its own context; default is v2's
    n = fr.n
    o, l = fr.o, fr.l
    cnt = dict(orders=0, fills=0, timeouts=0, ctx_cancels=0, roll_cancels=0, resets=0, gap_fills=0,
               reentries=0, same_bar=0, ev=[], orders_by_tier={1: 0, 2: 0}, fills_by_tier={1: 0, 2: 0})
    ev = cnt["ev"]
    trades: list[TradeT] = []
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
                tr_tier = int(tier[t - 1])                        # K4: tier on the last context bar
                cnt["fills"] += 1
                cnt["fills_by_tier"][tr_tier] += 1
                cnt["gap_fills"] += int(o[t] < lvl)
                cnt["reentries"] += int(bool(trades) and j0 == trades[-1].exit_j)
                tr = run_position(fr, ind, p, t, fill, a0, stop0, j0, o[t] < lvl)
                trades.append(TradeT(**{f.name: getattr(tr, f.name) for f in fields(Trade)}, tier=tr_tier))
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
            cnt["orders"] += 1; cnt["orders_by_tier"][int(tier[t])] += 1; ev.append(("order", t))
        t += 1
    return trades, cnt
