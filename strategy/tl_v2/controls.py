#!/usr/bin/env python3
"""TL-v2 C3 (random selection of retest entries) and the 27-cell neighbour grid.
REGISTERED_tl_v2.md sec 3 and sec 4 (criteria 6 and 9). Board: W15-0049. NO P&L is read here on the
real archive until the runner (strategy/tl_v2/run.py) is started, and the runner refuses to start until
the count-only pre-flight has been read (W15-0048).

Both read FRACTIONAL ENSEMBLE SLEEVES at $22,129, MID friction = the IBKR mid level of Amendment 1
(fee + 1 tick per side; strategy/tl_v2/costs.py). Nothing here uses TL-v0's flat friction.

C3 -- HOW "THE POOL = THE RETEST ENTRIES OF EVERY LINE BREAK, THINNED TO TL-v2's ENTRY COUNT" IS CODED
                                                                       (PRE-RUN coding note, Amendment 3)
-----------------------------------------------------------------------------------------------------
Per market and pivot size R (the seed already carries both):
  POOL   the retest ENTRY signals (T1-T5, N = 10, touch buffer 0.25) of the sec 2.2 line breaks with the
         weekly filter ON and A1-A3 OFF ("A+ not required"): the same retest scan as TL-v2 on a break set
         that is a superset of TL-v2's. One live setup per market (Amendment 2 C1) applies to that scan
         too, so a non-A+ break can occupy the slot an A+ break would have used; TL-v2's own entries are
         therefore not guaranteed to be a subset of the pool. The report prints how many are.
  COUNT  n = TL-v2's own retest entry signals for that market and R (retest_signals(ctx, R) with the
         registered gate). Matched on entry SIGNALS, not on filled trades: a filled-trade count depends
         on the path (an entry inside an open position is ignored by the simulator). The median filled
         trade count of the draws is printed beside TL-v2's own so the reader can see they are comparable.
  DRAW   d picks k = min(n, |pool|) signals uniformly without replacement, with
         np.random.default_rng([crc32(str(d)), crc32(market), R]) (seeded; one market's draw never depends
         on how many other markets ran), and feeds them to the SAME simulate() through the SAME
         to_sim_input(): same v0-rev safety line, weekly state, exits, sizing, IBKR costs.
  RESULT total net at mid over all markets and R, 1,000 draws: p5 / p50 / p95 / p99.
Criterion 6 reads the p99.

THE GRID (sec 3): touch buffer {0.15, 0.25, 0.35} x window W {125, 250, 400} x N {5, 10, 20}; ER stays at
q25. The buffer moves BOTH A1's touch buffer and T1's (signals.py). The centre cell (0.25, 250, 10) is
the verdict book and must equal it exactly (the report checks). Unranked; there is no best-cell table.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from strategy.tl_v0 import pnl
from strategy.tl_v0.engine import tl_input
from strategy.tl_v0.sim import simulate
from strategy.tl_v0.spec import EQUITY, PIVOT_SIZES, RISK_PCT
from strategy.tl_v1.signals import MarketCtx
from strategy.tl_v2 import costs as C
from strategy.tl_v2.signals import retest_signals, to_sim_input, v2_input

ENS_RISK = RISK_PCT * EQUITY / len(PIVOT_SIZES)
GRID_BUF = (0.15, 0.25, 0.35)
GRID_W = (125, 250, 400)
GRID_N = (5, 10, 20)
CENTRE = (0.25, 250, 10)
PERCENTILES = (5, 50, 95, 99)


def sim_net_mid(ctx: MarketCtx, x, risk: float = ENS_RISK) -> tuple[float, int]:
    """Net at IBKR mid and trade count for one sleeve walk (fractional, rule "reverse")."""
    r = simulate(x, rule="reverse", mult=ctx.m.mult, risk_usd=risk, integer=False)
    net = 0.0
    for t in r.trades:
        net += C.net(pnl.book(t, ctx.frame, ctx.m), "mid", t.qty, ctx.m)
    return float(net), len(r.trades)


def draw_rng(d: int, market: str, R: int) -> np.random.Generator:
    """Registered seed (sec 3): one draw of one market at one pivot size."""
    return np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(market.encode()), R])


def c3_pick(d: int, market: str, R: int, pool_size: int, k: int) -> np.ndarray:
    """Indices (into the pool) drawn by draw d: k of pool_size, no replacement."""
    k = min(k, pool_size)
    if k <= 0:
        return np.array([], dtype=int)
    return draw_rng(d, market, R).choice(pool_size, size=k, replace=False)


def c3_setup(ctxs: dict[str, MarketCtx]) -> dict:
    out = {}
    for name, ctx in ctxs.items():
        for R in PIVOT_SIZES:
            own = retest_signals(ctx, R)                          # TL-v2 itself: registered gate
            n_sel = int(own.scan.ent_up.sum() + own.scan.ent_dn.sum())
            pool = retest_signals(ctx, R, a1=False, a2=False, a3=False)   # every break, weekly ON
            pu = np.nonzero(pool.scan.ent_up)[0]
            pd_ = np.nonzero(pool.scan.ent_dn)[0]
            own_bars = {(1, int(j)) for j in np.nonzero(own.scan.ent_up)[0]} | \
                       {(-1, int(j)) for j in np.nonzero(own.scan.ent_dn)[0]}
            pool_bars = {(1, int(j)) for j in pu} | {(-1, int(j)) for j in pd_}
            base = tl_input(ctx.v0sig(R), "v0-rev")
            out[(name, R)] = dict(base=base, raw_up=pool.gate.raw_up, raw_dn=pool.gate.raw_dn,
                                  pool_up=pu, pool_dn=pd_, n_sel=n_sel,
                                  own_in_pool=len(own_bars & pool_bars), own_total=len(own_bars))
    return out


def c3_draw(ctxs: dict[str, MarketCtx], setup: dict, d: int) -> tuple[float, int]:
    total, entries = 0.0, 0
    for (name, R), s in setup.items():
        pu, pd_ = s["pool_up"], s["pool_dn"]
        size = len(pu) + len(pd_)
        pick = c3_pick(d, name, R, size, s["n_sel"])
        if not len(pick):
            continue
        n = len(s["base"].c)
        qu, qd = np.zeros(n, bool), np.zeros(n, bool)
        qu[pu[pick[pick < len(pu)]]] = True
        qd[pd_[pick[pick >= len(pu)] - len(pu)]] = True
        x = to_sim_input(s["base"], s["raw_up"], s["raw_dn"], qu, qd)
        net, ne = sim_net_mid(ctxs[name], x)
        total += net
        entries += ne
    return total, entries


def run_c3(ctxs: dict[str, MarketCtx], draws: int = 1000, progress=None) -> dict:
    setup = c3_setup(ctxs)
    totals, ents = [], []
    for d in range(draws):
        t, e = c3_draw(ctxs, setup, d)
        totals.append(t)
        ents.append(e)
        if progress and (d + 1) % 100 == 0:
            progress(d + 1)
    a = np.array(totals)
    pc = {f"p{q}": float(np.percentile(a, q)) for q in PERCENTILES}
    return dict(draws=draws, **pc, mean=float(a.mean()), entries_median=float(np.median(ents)),
                selected_entries=int(sum(s["n_sel"] for s in setup.values())),
                pool_entries=int(sum(len(s["pool_up"]) + len(s["pool_dn"]) for s in setup.values())),
                own_in_pool=int(sum(s["own_in_pool"] for s in setup.values())),
                own_total=int(sum(s["own_total"] for s in setup.values())),
                totals=a)


def run_grid(ctxs: dict[str, MarketCtx], progress=None) -> pd.DataFrame:
    rows = []
    for N in GRID_N:
        for W in GRID_W:
            for buf in GRID_BUF:
                net, n = 0.0, 0
                for name, ctx in ctxs.items():
                    for R in PIVOT_SIZES:
                        x, _ = v2_input(ctx, R, N=N, buf=buf, window=W)
                        a, b = sim_net_mid(ctx, x)
                        net += a
                        n += b
                rows.append(dict(touch_buf=buf, window=W, N=N, net_mid=net, trades=n))
                if progress:
                    progress(len(rows))
    return pd.DataFrame(rows)
