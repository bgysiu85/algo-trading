#!/usr/bin/env python3
"""Controls (sec 3): C1 Donchian 20/10 short, C2 the long rules mirrored for shorts, C3 random short entries."""
from __future__ import annotations

from dataclasses import replace
from zlib import crc32

import numpy as np

from strategy.chartmark import engine as LE
from strategy.chartmark import spec as LS
from strategy.chartmark_s import engine as E
from strategy.chartmark_s import spec as S
from strategy.chartmark_s.data import Frame, Ind, make_frame, indicators


def donchian_c1(fr: Frame, ind: Ind, N_in: int = 20, N_out: int = 10) -> tuple[list, dict]:
    """Sell-stop at the lowest low of the last 20 bars - 1 tick, placed at the close of t (one-bar life, re-set each bar);
    exit: buy-stop at the highest high of the last 10 bars as of the prior close, also capped by the sec 2.3 backstop
    (20-bar high ending at the entry bar + 1 tick). Fills min/max(level, open). Same friction, costs and roll rule."""
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    trades = []
    t = N_in
    while t < n - 1:
        if not fr.roll_after[t]:
            level = float(l[t - N_in + 1: t + 1].min()) - S.TICK
            j = t + 1
            if l[j] <= level:
                fill = min(level, o[j])
                stop0 = E.backstop(fr, j, 20)
                x = px = why = None
                for k in range(j + 1, n):
                    lvl = min(stop0, float(h[k - N_out: k].max()))
                    if h[k] >= lvl:
                        x, px, why = k, max(lvl, o[k]), "S"
                        break
                if x is None:
                    x, px, why = n - 1, c[n - 1], "data_end"
                rolls = int(fr.roll_after[j:x].sum()) if x > j else 0
                trades.append(E.Trade(j, x, float(fill), float(px), float(stop0), 0.0, why, 0, rolls))
                t = x
        t += 1
    return trades, dict(entries=len(trades))


def mirror(fr: Frame) -> Frame:
    """Price-negated frame: a long on it is a short on the original (highs <-> lows, EMAs and MACD flip sign)."""
    return make_frame(fr.t, -fr.o, -fr.l, -fr.h, -fr.c, fr.v, fr.roll_after, fr.label + " (mirrored)")


def c2_mirrored_long(fr: Frame) -> tuple[list, dict]:
    """The CHARTMARK-v1 long BASE run on the mirrored frame. Gross of a returned trade = exit_m - entry_m (a short's P&L on the
    original), so strategy.chartmark.book.trade_frame(trades, mirrored_frame) scores it correctly. Reference only."""
    mf = mirror(fr)
    from strategy.chartmark.data import indicators as lind
    tr, cnt = LE.simulate(mf, lind(mf), LS.BASE)
    return tr, dict(cnt, mirrored=mf)


def candidate_outcomes(fr: Frame, ind: Ind, p: S.Params = S.BASE) -> tuple[np.ndarray, list]:
    """Every bar as a standalone random short: sell at its open, backstop = 20-bar high of the bars ending the bar BEFORE
    (+1 tick), A0 = ATR[e-1], the same exit walk (J10)."""
    idx, trs = [], []
    for e in range(max(S.ATR_LEN + 1, p.backstop_n + 1), fr.n - 1):
        if np.isnan(ind.atr[e - 1]):
            continue
        stop0 = float(fr.h[e - p.backstop_n: e].max()) + S.TICK
        if stop0 <= fr.o[e]:
            continue
        trs.append(E.run_position(fr, ind, p, e, fr.o[e], ind.atr[e - 1], stop0))
        idx.append(e)
    return np.array(idx), trs


def c3_draws(fr: Frame, cand_idx: np.ndarray, cand_net: np.ndarray, base_entries_per_year: dict, draws: int = 1000):
    """1,000 seeded draws: per year, the same number of entries as the base, sampled from that year's candidates.
    Seed = default_rng([crc32(str(d)), crc32("CL-S"), N]) with N the base's total entries (registered)."""
    years = np.asarray(fr.ny.year)[cand_idx]
    N = int(sum(base_entries_per_year.values()))
    pools = {y: cand_net[years == y] for y in base_entries_per_year}
    tot = np.empty(draws)
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(b"CL-S"), N])
        s = 0.0
        for y in sorted(base_entries_per_year):
            k, pool = base_entries_per_year[y], pools[y]
            if k and len(pool):
                s += float(pool[rng.integers(0, len(pool), size=k)].sum())
        tot[d] = s
    return tot
