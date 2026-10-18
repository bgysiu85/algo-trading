#!/usr/bin/env python3
"""EXIT-CMP sec 7: C-RANDX. Take a rule set's own holding times over the entry set, shuffle them across trades, exit each trade at
its assigned bar's close (S still live as the floor, the scenario's cap still applies). Vectorised: the S-only walk is done once."""
from __future__ import annotations

import numpy as np

from exitmgr import symbols as SY
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.walk import Exit, Study


def prepare(st: Study, scenario: str) -> dict:
    """Per entry: the bar where S alone would fill (inf if never, or only after the scenario's cap), its price, the cap bar."""
    base = st.run(S.BASELINE, scenario)
    e = np.array([x.e for x in st.entries])
    ep = np.array([x.entry_px for x in st.entries])
    cap = np.empty(len(e), int)
    for i, (ex, en) in enumerate(zip(base, st.entries)):
        cap[i] = ex.exit_j                                  # B-STOP exits at S or at the scenario's end: its exit IS the cap
    sj = np.array([ex.exit_j if ex.reason == "S" else 10 ** 9 for ex in base])
    sp = np.array([ex.exit_px for ex in base])
    return dict(e=e, ep=ep, cap=cap, sj=sj, sp=sp, c=st.fr.c, n=st.n, roll_cum=st.roll_cum)


def draw_net(prep: dict, hold: np.ndarray, perm: np.ndarray, sym: str, level: str) -> float:
    """Total net ($, 1 contract) of one draw: trade i exits `hold[perm[i]]` bars after entry."""
    e, ep = prep["e"], prep["ep"]
    tj = np.minimum(np.minimum(e + hold[perm], prep["cap"]), prep["n"] - 1)
    hit = prep["sj"] <= tj
    xj = np.where(hit, prep["sj"], tj)
    xp = np.where(hit, prep["sp"], prep["c"][tj])
    rolls = prep["roll_cum"][xj] - prep["roll_cum"][e]
    s = SY.get(sym)
    return float(((xp - ep) * s.point_usd - s.per_side(level) * (2 + 2 * rolls)).sum())


def c_randx(st: Study, rule_id: str, exits: list[Exit], scenario: str, sym: str = "MCL", level: str = "mid",
            draws: int = S.CONTROL_DRAWS) -> dict:
    prep = prepare(st, scenario)
    hold = np.array([x.exit_j - en.e for x, en in zip(exits, st.entries)])
    nets = np.empty(draws)
    for d in range(draws):
        perm = S.draw_rng(d, rule_id).permutation(len(hold))
        nets[d] = draw_net(prep, hold, perm, sym, level)
    q = np.percentile(nets, [5, 50, 95, 99])
    return dict(p5=float(q[0]), p50=float(q[1]), p95=float(q[2]), p99=float(q[3]), draws=draws)
