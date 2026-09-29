#!/usr/bin/env python3
"""C3 (random selection of the same lines' breaks) and the 27-cell neighbour grid.
REGISTERED_tl_v1.md sec 3. Both read fractional ensemble sleeves at $22,129, mid friction.

C3 -- HOW "THINNED AT RANDOM TO TL-v1'S ENTRY COUNT" IS CODED (PRE-RUN coding note)
----------------------------------------------------------------------------------
Pool per market and pivot size R: every raw sec 2.2 break whose direction agrees with the
weekly filter (TL-v1-A+'s breaks, weekly filter on). N = the number of those same-direction
breaks that ALSO pass A1-A3 (TL-v1's own selected BREAKS, counted on the bars, independent
of position). Each draw picks N of the pool uniformly without replacement and runs them
through the SAME simulate() (same v0-rev safety line, reversal, sizing, costs). N is matched
on breaks, not on filled entries, because a filled-entry count depends on the path (same-side
breaks inside a position are ignored); the median filled-entry count of the draws is printed
beside TL-v1's own so the reader can see the two are comparable. Draw d uses
np.random.default_rng([crc32(str(d)), crc32(market), R]): seeded, reproducible, and one
market's draw does not depend on how many other markets ran.
"""
from __future__ import annotations

import zlib
from dataclasses import replace

import numpy as np
import pandas as pd

from strategy.tl_v0 import pnl
from strategy.tl_v0.sim import simulate
from strategy.tl_v0.spec import EQUITY, PIVOT_SIZES, RISK_PCT
from strategy.tl_v1.signals import MarketCtx, v1_input

ENS_RISK = RISK_PCT * EQUITY / len(PIVOT_SIZES)
GRID_BUF = (0.15, 0.25, 0.35)
GRID_W = (125, 250, 400)
GRID_Q = (0.20, 0.25, 0.33)


def sim_net_mid(ctx: MarketCtx, x, risk: float = ENS_RISK) -> tuple[float, int]:
    r = simulate(x, rule="reverse", mult=ctx.m.mult, risk_usd=risk, integer=False)
    net = 0.0
    for t in r.trades:
        net += pnl.book(t, ctx.frame, ctx.m).net("mid", t.qty)
    return float(net), len(r.trades)


def c3_setup(ctxs: dict[str, MarketCtx]) -> dict:
    out = {}
    for name, ctx in ctxs.items():
        for R in PIVOT_SIZES:
            x, g = v1_input(ctx, R, aplus=False)           # every break, weekly filter still in x.htf
            htf = x.htf
            pool_up = np.nonzero(g.raw_up & (htf == 1))[0]
            pool_dn = np.nonzero(g.raw_dn & (htf == -1))[0]
            n_sel = int((g.qual_up & (htf == 1)).sum() + (g.qual_dn & (htf == -1)).sum())
            out[(name, R)] = dict(x=x, pool_up=pool_up, pool_dn=pool_dn, n_sel=n_sel)
    return out


def c3_draw(ctxs: dict[str, MarketCtx], setup: dict, d: int) -> tuple[float, int]:
    total, entries = 0.0, 0
    for (name, R), s in setup.items():
        pu, pd_ = s["pool_up"], s["pool_dn"]
        size = len(pu) + len(pd_)
        k = min(s["n_sel"], size)
        if k == 0:
            continue
        rng = np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(name.encode()), R])
        pick = rng.choice(size, size=k, replace=False)
        n = len(s["x"].c)
        qu, qd = np.zeros(n, bool), np.zeros(n, bool)
        qu[pu[pick[pick < len(pu)]]] = True
        qd[pd_[pick[pick >= len(pu)] - len(pu)]] = True
        net, ne = sim_net_mid(ctxs[name], replace(s["x"], qual_up=qu, qual_dn=qd))
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
    return dict(draws=draws, p5=float(np.percentile(a, 5)), p50=float(np.percentile(a, 50)),
                p95=float(np.percentile(a, 95)), mean=float(a.mean()),
                entries_median=float(np.median(ents)),
                selected_breaks=int(sum(s["n_sel"] for s in setup.values())),
                pool_breaks=int(sum(len(s["pool_up"]) + len(s["pool_dn"]) for s in setup.values())),
                totals=a)


def run_grid(ctxs: dict[str, MarketCtx], progress=None) -> pd.DataFrame:
    rows = []
    for W in GRID_W:
        for buf in GRID_BUF:
            for q in GRID_Q:
                net, n = 0.0, 0
                for name, ctx in ctxs.items():
                    for R in PIVOT_SIZES:
                        x, _ = v1_input(ctx, R, window=W, touch_buf=buf, erq=q)
                        a, b = sim_net_mid(ctx, x)
                        net += a
                        n += b
                rows.append(dict(window=W, touch_buf=buf, er_pct=int(round(q * 100)), net_mid=net, trades=n))
                if progress:
                    progress(len(rows))
    return pd.DataFrame(rows)
