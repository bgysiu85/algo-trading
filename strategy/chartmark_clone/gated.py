#!/usr/bin/env python3
"""CHARTMARK-CLONE sub 5: the CHARTMARK-v1 long engine with a take/skip gate at every would-be fill.
REGISTERED_chartmark_clone.md sec 9.3 (+ Amendment 3, PRE-RUN).

`simulate_gated` is E.simulate (strategy/chartmark/engine.py, unchanged and still the reference) with ONE addition: when the
buy-stop working for bar t is touched (E4: h[t] >= level) the gate is asked. The decision is made as of the close of bar t-1
(the labelling decision point): gate(t_dec = t-1, level, t) with the level the order held at that close.
  take  -> the fill and the exits are exactly v1's (or, for V-EXIT2, the CHARTMARK-v2 exits).
  skip  -> no fill; the order state carries on as if bar t had not touched the level (E2 re-set, E3 timeout count and E5
           re-arm are processed at the close of t exactly as v1 does for an unfilled bar).
The gate is never asked on a bar that would not have filled (same as the labelling, which only ever showed fill bars).
Always-take must reproduce v1 trade for trade, always-skip must give no trade (gate G6, tests + the runner).

NO FILE WITH AN OUTCOME COLUMN IS READ HERE. Outcomes are only what the engine walks out of the frame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.chartmark import engine as E
from strategy.chartmark import spec as S1
from strategy.chartmark.data import Frame, Ind, context
from strategy.chartmark_clone import clone as CL
from strategy.chartmark_clone import features as FT
from strategy.chartmark_clone.chartdata import ChartData
from strategy.chartmark_v2 import engine as E2
from strategy.chartmark_v2 import spec as S2

TICK = S1.TICK


# ------------------------------------------------------------------------------------------------ gates
class AlwaysTake:
    def __call__(self, t_dec: int, level: float, j: int) -> bool:
        return True


class AlwaysSkip:
    def __call__(self, t_dec: int, level: float, j: int) -> bool:
        return False


class CloneGate:
    """The frozen clone as a gate. kind 'R' (rules), 'M' (logistic) or 'M-GB' (boosting, `gb` = the refitted model).
    Decisions are memoised on (decision bar, level): the clone is a pure function of those and of bar j's clock time."""

    def __init__(self, cd: ChartData, kind: str, frozen: dict, gb=None):
        if kind not in ("R", "M", "M-GB"):
            raise ValueError(kind)
        self.cd, self.kind, self.frozen, self.gb = cd, kind, frozen, gb
        self.ny = cd.fr.ny
        self.memo: dict[tuple[int, float], bool] = {}
        self.calls = 0

    def __call__(self, t_dec: int, level: float, j: int) -> bool:
        key = (t_dec, float(level))
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        self.calls += 1
        row = FT.features_at(self.cd, t_dec, float(level), self.ny[j])
        X = pd.DataFrame([row], columns=FT.FEATURE_COLUMNS)
        if self.kind == "R":
            take = bool(CL.predict_rules(self.frozen["R"]["rules"], X)[0] == 1)
        elif self.kind == "M":
            take = bool(CL.proba_logit(self.frozen["M"], X)[0] >= self.frozen["M"]["threshold"])
        else:
            take = bool(CL.proba_gb(self.gb, X)[0] >= self.frozen["M_GB"]["threshold"])
        self.memo[key] = take
        return take


class RandomGate:
    """C3: take with probability p_y, y = the New York year of the would-be fill bar j. Fresh generator per draw."""

    def __init__(self, p_by_year: dict[int, float], year_of_bar: np.ndarray, rng: np.random.Generator,
                 default_p: float):
        self.p, self.year, self.rng, self.default = p_by_year, year_of_bar, rng, default_p

    def __call__(self, t_dec: int, level: float, j: int) -> bool:
        return bool(self.rng.random() < self.p.get(int(self.year[j]), self.default))


# ------------------------------------------------------------------------------------------------ V-EXIT2
def v2_exit(fr: Frame, ind: Ind, t_dec: int, j: int, level: float, fill: float,
            p2: S2.Params = S2.K1) -> E2.Trade:
    """CHARTMARK-v2 exits on a v1 entry (registration sec 9.4 V-EXIT2): $0.60 backstop below the fill, the fill-bar rule of
    v2 Amendment 5, then the EMA21 two-breach rules. t_dec is the arming close (the decision bar)."""
    stop = fill - p2.backstop
    if E2._fillbar_hit(fr, ind, p2, t_dec, j, level, stop):
        x, px, why, cl = j, stop, "BACKSTOP-fillbar", ()
    else:
        x, px, why, cl = E2._walk(fr, ind, p2, j, fill, stop)
    rolls = int(fr.roll_after[j:x].sum()) if x > j else 0
    return E2.Trade(j, x, float(fill), float(px), why, "v1-entry", t_dec, float(level), float(p2.backstop), rolls,
                    bool(fr.o[j] > level), cl)


# ------------------------------------------------------------------------------------------------ the engine
def simulate_gated(fr: Frame, ind: Ind, p: S1.Params = S1.BASE, gate=None, *, exits: str = "v1",
                   start: int = 0) -> tuple[list, dict]:
    """E.simulate with the gate at E4. gate=None behaves as always-take (and counts nothing). exits: 'v1' | 'v2'."""
    if exits not in ("v1", "v2"):
        raise ValueError(exits)
    ctx = context(fr, ind, p)
    n = fr.n
    o, h = fr.o, fr.h
    years = np.asarray(fr.ny.year)
    cnt = dict(orders=0, fills=0, timeouts=0, ctx_cancels=0, roll_cancels=0, resets=0, gap_fills=0,
               same_bar_touch=0, stop_from_entry_bar=0, would_be=0, takes=0, skips=0, wb_year={}, take_year={})
    trades: list = []
    pending = None                  # [level, placed_j]
    need_false = False
    t = max(start, 1)
    while t < n - 1:
        if pending is not None:
            lvl, j0 = pending
            if h[t] >= lvl:                                   # E4: the level is touched in bar t
                take = True
                if gate is not None:
                    cnt["would_be"] += 1
                    y = int(years[t])
                    cnt["wb_year"][y] = cnt["wb_year"].get(y, 0) + 1
                    take = bool(gate(t - 1, lvl, t))
                    if take:
                        cnt["takes"] += 1
                        cnt["take_year"][y] = cnt["take_year"].get(y, 0) + 1
                    else:
                        cnt["skips"] += 1
                if take:
                    fill = max(lvl, o[t])
                    cnt["fills"] += 1
                    cnt["gap_fills"] += int(o[t] > lvl)
                    if exits == "v1":
                        a0 = ind.atr[t - 1]
                        stop0, own = E.initial_stop(fr, t, p.stop_lookback)
                        cnt["stop_from_entry_bar"] += int(own)
                        cnt["same_bar_touch"] += int(fr.l[t] <= stop0)
                        tr = E.run_position(fr, ind, p, t, fill, a0, stop0, j0, o[t] > lvl, own)
                    else:
                        tr = v2_exit(fr, ind, t - 1, t, lvl, fill)
                    trades.append(tr)
                    pending = None
                    t = tr.exit_j                             # flat again at the close of the exit bar
                    if t >= n - 1:
                        break
        # ---- close of bar t (identical to v1) ----
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
                new = E._hh(h, t, p.e1_lookback) + TICK
                if new > pending[0]:
                    cnt["resets"] += 1
                pending[0] = max(pending[0], new)
        elif ctx[t] and not need_false and not fr.roll_after[t]:
            pending = [E._hh(h, t, p.e1_lookback) + TICK, t]
            cnt["orders"] += 1
        t += 1
    return trades, cnt


def trade_key(tr) -> tuple:
    """Identity of a trade for parity checks: what happened, never what it was worth."""
    return (tr.entry_j, tr.exit_j, round(float(tr.entry_px), 6), round(float(tr.exit_px), 6), tr.reason)


def net_mid_1mcl(trades: list) -> float:
    """Total net, 1 MCL, IBKR mid, of a trade list (the C3 draw statistic)."""
    if not trades:
        return 0.0
    side = S1.per_side("MCL", "mid")
    return float(sum((t.exit_px - t.entry_px) * S1.MULT["MCL"] - side * (2 + 2 * t.n_rolls) for t in trades))
