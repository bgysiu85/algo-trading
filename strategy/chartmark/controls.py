#!/usr/bin/env python3
"""Controls C1 (Donchian 20/10, long, same session filter) and C3 (random entries, same exits). Sec 3."""
from __future__ import annotations

from zlib import crc32

import numpy as np

from strategy.chartmark import spec as S
from strategy.chartmark import engine as E
from strategy.chartmark.data import Frame, Ind, context


def donchian_c1(fr: Frame, ind: Ind, N_in: int = 20, N_out: int = 10) -> tuple[list, dict]:
    """Buy-stop at the highest high of the last 20 bars + 1 tick, placed at the close of t if bar t opens in the
    session; one bar life, re-set each bar. Exit: sell-stop at the lowest low of the last 10 bars (as of the prior
    close), also the initial stop. Fills min/max(level, open). Same friction, same costs, same roll rule."""
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    sess = (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
    trades = []
    t = N_in
    while t < n - 1:
        if sess[t] and not fr.roll_after[t]:
            level = float(h[t - N_in + 1: t + 1].max()) + S.TICK
            j = t + 1
            if h[j] >= level:
                fill = max(level, o[j])
                x, px = None, None
                for k in range(j + 1, n):
                    lvl = float(l[k - N_out: k].min())
                    if o[k] <= lvl:
                        x, px = k, o[k]; break
                    if l[k] <= lvl:
                        x, px = k, lvl; break
                if x is None:
                    x, px = n - 1, c[n - 1]
                    why = "data_end"
                else:
                    why = "S"
                rolls = int(fr.roll_after[j:x].sum()) if x > j else 0
                trades.append(E.Trade(j, x, float(fill), float(px), float(l[j - N_out: j].min()), 0.0, why, 0, rolls))
                t = x
        t += 1
    return trades, dict(entries=len(trades))


def candidate_outcomes(fr: Frame, ind: Ind, p: S.Params = S.BASE) -> tuple[np.ndarray, list]:
    """Every in-session bar as a standalone random-entry candidate: enter at its open, sec 2.3 stop from the bars ending
    the bar before, A0 = ATR[e-1], exits by the same walk. Returns (bar indices, trades)."""
    sess = (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
    idx, trs = [], []
    for e in range(max(S.ATR_LEN + 1, p.stop_lookback + 1), fr.n - 1):
        if not sess[e] or np.isnan(ind.atr[e - 1]):
            continue
        stop0 = float(fr.l[e - p.stop_lookback: e].min()) - S.TICK
        if stop0 >= fr.o[e]:
            continue
        trs.append(E.run_position(fr, ind, p, e, fr.o[e], ind.atr[e - 1], stop0))
        idx.append(e)
    return np.array(idx), trs


def c3_draws(fr: Frame, cand_idx: np.ndarray, cand_net: np.ndarray, base_entries_per_year: dict, draws: int = 1000):
    """1,000 seeded draws: per year, the same number of entries as the base, sampled from that year's candidates.
    Seed = default_rng([crc32(str(d)), crc32("CL"), N]) with N the base's total entries (registered)."""
    years = np.asarray(fr.ny.year)[cand_idx]
    N = int(sum(base_entries_per_year.values()))
    pools = {y: cand_net[years == y] for y in base_entries_per_year}
    tot = np.empty(draws)
    for d in range(draws):
        rng = np.random.default_rng([crc32(str(d).encode()), crc32(b"CL"), N])
        s = 0.0
        for y in sorted(base_entries_per_year):
            k, pool = base_entries_per_year[y], pools[y]
            if k and len(pool):
                s += float(pool[rng.integers(0, len(pool), size=k)].sum())
        tot[d] = s
    return tot
