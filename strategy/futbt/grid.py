#!/usr/bin/env python3
"""The 27-cell neighbour grids of CRUDELE-3S (sec 3 item 7) and BREIT-CAP (sec 3 item 7).

Robustness only: every cell is the FRACTIONAL book at $22,129, mid friction, all markets, the system's
own arms / sizing. Nothing is ranked and no best cell is reported. The centre cell (the registered
values) must reproduce the verdict book's net exactly; the report prints the difference (~0).
"""
from __future__ import annotations

import itertools

import pandas as pd

from strategy.futbt import core as K


def crudele_cells() -> list[tuple[dict, object]]:
    from strategy.crudele_3s import spec as S
    out = []
    for bwr, exp, ma in itertools.product(S.GRID_BWR, S.GRID_EXP, S.GRID_MA):
        out.append((dict(bwr=bwr, exp_bars=exp, exit_ma=ma),
                    S.PRIMARY.with_(bwr_thr=bwr, exp_bars=exp, exit_ma=ma)))
    return out


def breit_cells() -> list[tuple[dict, object]]:
    from strategy.breit_cap import spec as S
    out = []
    for q2, k, sd in itertools.product(S.GRID_Q2, S.GRID_K, S.GRID_SD):
        out.append((dict(q2=q2, k_min=k, q3_sd=sd), S.PRIMARY.with_(q2=q2, k_min=k, q3_sd=sd)))
    return out


def run_grid(frames: dict, method, sim, cells, *, equity: float = K.EQUITY, progress=None) -> pd.DataFrame:
    rows = []
    for i, (label, params) in enumerate(cells, 1):
        net, n = 0.0, 0
        for fr in frames.values():
            sg = method.compute(fr, params)
            trades, _ = sim.simulate(fr, sg, equity=equity, integer=False)
            net += K.net_mid(trades, fr)
            n += len(trades)
        rows.append(dict(label, net_mid=net, trades=n))
        if progress:
            progress(i)
    return pd.DataFrame(rows)
