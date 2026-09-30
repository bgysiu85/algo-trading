#!/usr/bin/env python3
"""CHARTMARK-v2 long engine. REGISTERED_chartmark_v2.md sec 2 + Amendments 1-4.

Anticipating buy-stop on 1H bars. At the CLOSE of bar t the engine decides whether an order works in bar t+1 and where
(the lowest price at which every trigger condition holds LIVE, cleared above the red-candle open and, when on, the previous
high). Everything decided at the close of t reads bars <= t only. One position at a time.

    simulate(fr, ind, params) -> (trades, counts)     counts only; no P&L is computed here
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.chartmark.data import Frame, Ind, avoid_flag
from strategy.chartmark_v2 import spec as S
from strategy.htf.signals import ema_seeded

TICK = S.TICK
A9, A21, A12, A26, AS = 2 / 10, 2 / 22, 2 / 13, 2 / 27, 2 / 10


@dataclass
class Trade:
    entry_j: int
    exit_j: int
    entry_px: float
    exit_px: float
    reason: str            # BACKSTOP / BACKSTOP-fillbar / EMA21 / UNCONFIRMED / data_end
    arm: str               # A-early / A-fresh / B
    placed_j: int          # bar at whose close the order was placed
    level: float
    dist: float            # backstop distance used
    n_rolls: int = 0
    gap_fill: bool = False
    clauses: tuple = ()    # EMA21 exits: which of clauses 1/2/3 held
    phase: int = 0         # kept so strategy.chartmark.book.trade_frame accepts a v2 Trade


@dataclass
class Pre:
    """Per-frame arrays that do not depend on the parameters."""
    e12: np.ndarray
    e26: np.ndarray
    sig: np.ndarray
    run: np.ndarray        # consecutive bars ending at t with EMA9 > EMA21
    gap: np.ndarray
    avoid: np.ndarray | None = None


def precompute(fr: Frame, ind: Ind) -> Pre:
    close = pd.Series(fr.c)
    e12 = ema_seeded(close, 12).to_numpy()
    e26 = ema_seeded(close, 26).to_numpy()
    sig = ema_seeded(pd.Series(e12 - e26), 9).to_numpy()
    with np.errstate(invalid="ignore"):
        up = ind.e9 > ind.e21
    run = np.zeros(fr.n, int)
    for i in range(fr.n):
        run[i] = (run[i - 1] + 1 if i else 1) if up[i] else 0
    return Pre(e12, e26, sig, run, ind.e9 - ind.e21)


# ----------------------------------------------------------------------- arming (close of t)
def _arm_kind(fr: Frame, ind: Ind, pre: Pre, p: S.Params, t: int):
    """Sec 2.1 arming conditions at the close of t (bars <= t only). Returns 'A-early' / 'A-fresh' / 'B' / None."""
    a = ind.atr[t]
    if t < 3 or np.isnan(a) or np.isnan(ind.hist[t - 2]) or np.isnan(ind.e21[t]) or np.isnan(pre.sig[t]):
        return None
    e9, e21, hist = ind.e9, ind.e21, ind.hist
    if e9[t] <= e21[t]:
        d0, d1, d2 = e21[t] - e9[t], e21[t - 1] - e9[t - 1], e21[t - 2] - e9[t - 2]
        if d0 < d1 < d2 and hist[t] > hist[t - 1] > hist[t - 2] and d0 <= S.NEAR_GAP * a and not p.confirmed:
            return "A-early"
        return None
    r = pre.run[t]
    if r <= S.FRESH_MAX and hist[t] > hist[t - 1]:
        return "A-fresh"
    if r >= p.par_bars and hist[t] > hist[t - 1]:
        if p.confirmed:
            if hist[t] >= p.theta * a and hist[t - 1] < 0 and pre.gap[t] > pre.gap[t - 1]:
                return "B"
        elif -S.NEAR_MACD * a <= hist[t] < 0:
            return "B"
    return None


def _red_level(fr: Frame, t: int):
    """Amendment 2: open + 1 tick of the most recent red bar among t-9..t whose open is above close[t]."""
    o, c = fr.o, fr.c
    for k in range(t, max(-1, t - S.RED_LOOK), -1):
        if c[k] < o[k] and o[k] > c[t]:
            return o[k] + TICK
    return None


def _wick_gate(fr: Frame, t: int) -> bool:
    n = 0
    for b in range(max(0, t - 2), t + 1):
        rng = fr.h[b] - fr.l[b]
        if fr.c[b] > fr.o[b] and rng > 0 and (fr.h[b] - max(fr.o[b], fr.c[b])) >= S.WICK_FRAC * rng:
            n += 1
    return n >= 2


def _level(fr: Frame, ind: Ind, pre: Pre, p: S.Params, t: int, kind: str):
    """L* for bar t+1 (Amendments 1-3). None = no order. Inputs: bars <= t."""
    lv = _red_level(fr, t)
    if lv is None:
        return None, "no_red"
    terms = [lv]
    use_prev = p.prev_high and (not p.wickgate or _wick_gate(fr, t))
    if use_prev:
        terms.append(fr.h[t] + TICK)
    if not (p.confirmed or p.redtop):
        e9, e21, hist, atr = ind.e9, ind.e21, ind.hist, ind.atr
        # EMA9(P) > EMA21(P)
        p_cross = ((1 - A21) * e21[t] - (1 - A9) * e9[t]) / (A9 - A21)
        hk = (1 - AS) * (A12 - A26)
        h0 = (1 - AS) * ((1 - A12) * pre.e12[t] - (1 - A26) * pre.e26[t] - pre.sig[t])
        if kind == "B":
            p_h = (p.theta * atr[t] - h0) / hk                                   # H(P) >= theta * ATR[t]
            p_g = (pre.gap[t] - ((1 - A9) * e9[t] - (1 - A21) * e21[t])) / (A9 - A21)   # G(P) > G[t]
            req = [p_h, p_g, p_cross]
        else:
            req = [p_cross, (hist[t] - h0) / hk]                                 # EMA cross; H(P) > H[t]
        terms += [x + TICK for x in req]
    lvl = float(np.ceil(max(terms) / TICK - 1e-9) * TICK)
    if lvl <= fr.c[t]:
        return None, "below_market"
    return lvl, ""


# ----------------------------------------------------------------------- EMA21 exit helpers
def _below_run(hist: np.ndarray, k: int) -> int:
    r = 0
    while k - r >= 0 and hist[k - r] < 0:
        r += 1
    return r


def _clauses(ind: Ind, br: list, k: int, hk: int, window: int) -> tuple:
    """Sec 2.5 clauses at a breach at bar k. hk = last bar whose MACD may be read (k, or k-1 for V-WICK)."""
    hist = ind.hist
    out = []
    if any(k - b <= window - 1 for b in br):
        out.append(1)
    below = _below_run(hist, hk)
    if below >= S.BELOW_N:
        out.append(2)
    if below >= S.ACCEL_N and hk - S.ACCEL_N - 1 >= 0:
        g = -hist
        d = [g[hk - i] - g[hk - i - 1] for i in range(S.ACCEL_N)]        # d[0] newest
        if d[2] > 0 and d[1] > d[2] and d[0] > d[1]:
            out.append(3)
    return tuple(out)


def _walk(fr: Frame, ind: Ind, p: S.Params, e: int, fill: float, stop: float):
    """Bars e+1.. . Returns (exit_j, exit_px, reason, clauses)."""
    n = fr.n
    o, l, c, e21 = fr.o, fr.l, fr.c, ind.e21
    br: list[int] = []
    for j in range(e + 1, n):
        if o[j] <= stop:
            return j, o[j], "BACKSTOP", ()
        stop_hit = l[j] <= stop
        if p.wick:
            lvl = e21[j - 1]
            wick_exit = None
            if not np.isnan(lvl) and l[j] < lvl:
                cl = _clauses(ind, br, j, j - 1, p.ema_window)
                br = [b for b in br if j - b <= p.ema_window - 1] + [j]
                if cl:
                    wick_exit = (min(lvl, o[j]), cl)
            if stop_hit and (wick_exit is None or stop >= lvl):
                return j, stop, "BACKSTOP", ()
            if wick_exit is not None:
                return j, wick_exit[0], "EMA21", wick_exit[1]
            continue
        if stop_hit:
            return j, stop, "BACKSTOP", ()
        if not np.isnan(e21[j]) and c[j] < e21[j]:
            cl = _clauses(ind, br, j, j, p.ema_window)
            br = [b for b in br if j - b <= p.ema_window - 1] + [j]
            if cl:
                return (j + 1, o[j + 1], "EMA21", cl) if j + 1 < n else (j, c[j], "data_end", ())
    return n - 1, c[n - 1], "data_end", ()


def _confirmed_at_close(fr: Frame, ind: Ind, pre: Pre, p: S.Params, j: int, arm: str) -> bool:
    """Sec 2.3 (V-REDTOP): confirmation at the fill bar's close."""
    if arm in ("A-early", "A-fresh"):
        return bool(ind.e9[j] > ind.e21[j] and ind.hist[j] > ind.hist[j - 1])
    return bool(ind.hist[j] >= p.theta * ind.atr[j] and pre.gap[j] > pre.gap[j - 1])


def decisions(fr: Frame, ind: Ind, p: S.Params = S.K1, pre: Pre | None = None) -> list:
    """(arm kind, level) at the close of every bar t >= 3, ignoring position state. The look-ahead guard compares this
    stream between a frame and its truncation: it must agree for every t the truncated frame contains."""
    pre = pre or precompute(fr, ind)
    out = []
    for t in range(3, fr.n):
        k = _arm_kind(fr, ind, pre, p, t)
        out.append((k, _level(fr, ind, pre, p, t, k)[0] if k else None))
    return out


# ----------------------------------------------------------------------- the order machine
def simulate(fr: Frame, ind: Ind, p: S.Params = S.K1, *, start: int = 0,
             pre: Pre | None = None) -> tuple[list[Trade], dict]:
    """Counts and trades. `start` = the first bar whose CLOSE the engine may act on (flat before it)."""
    pre = pre or precompute(fr, ind)
    n = fr.n
    o, h = fr.o, fr.h
    av = avoid_flag(fr, ind) if p.avoid else None
    cnt = dict(arms={"A-early": 0, "A-fresh": 0, "B": 0}, fills_by_arm={"A-early": 0, "A-fresh": 0, "B": 0},
               orders=0, fills=0, unfilled=0, no_red=0, below_market=0, roll_blocked=0, session_blocked=0,
               gap_fills=0, unconfirmed=0, exits={}, clauses_first={1: 0, 2: 0, 3: 0}, clauses_any={1: 0, 2: 0, 3: 0})
    trades: list[Trade] = []
    need_false = False
    t = max(start, 3)
    while t < n - 1:
        k = _arm_kind(fr, ind, pre, p, t)
        if k is not None and av is not None and av[t]:
            k = None
        if k is None:
            need_false = False
            t += 1
            continue
        if need_false or fr.roll_after[t]:
            cnt["roll_blocked"] += int(bool(fr.roll_after[t]))
            t += 1
            continue
        cnt["arms"][k] += 1
        if p.session and not (S.SESSION_FIRST <= ind.hour[t + 1] <= S.SESSION_LAST):
            cnt["session_blocked"] += 1
            t += 1
            continue
        lvl, why = _level(fr, ind, pre, p, t, k)
        if lvl is None:
            cnt[why] += 1
            t += 1
            continue
        cnt["orders"] += 1
        j = t + 1
        if h[j] < lvl:
            cnt["unfilled"] += 1
            t += 1
            continue
        fill = max(lvl, o[j])
        dist = p.backstop_atr * ind.atr[t] if p.backstop_atr is not None else p.backstop
        stop = fill - dist
        cnt["fills"] += 1
        cnt["fills_by_arm"][k] += 1
        cnt["gap_fills"] += int(o[j] > lvl)
        cl: tuple = ()
        if fr.l[j] <= stop:
            x, px, why = j, stop, "BACKSTOP-fillbar"
        elif p.redtop and not _confirmed_at_close(fr, ind, pre, p, j, k):
            cnt["unconfirmed"] += 1
            need_false = True
            x, px, why = (j + 1, o[j + 1], "UNCONFIRMED") if j + 1 < n else (j, fr.c[j], "data_end")
        else:
            x, px, why, cl = _walk(fr, ind, p, j, fill, stop)
        rolls = int(fr.roll_after[j:x].sum()) if x > j else 0
        trades.append(Trade(j, x, float(fill), float(px), why, k, t, float(lvl), float(dist), rolls, bool(o[j] > lvl), cl))
        cnt["exits"][why] = cnt["exits"].get(why, 0) + 1
        if cl:
            cnt["clauses_first"][cl[0]] += 1
            for c_ in cl:
                cnt["clauses_any"][c_] += 1
        t = x
    return trades, cnt

