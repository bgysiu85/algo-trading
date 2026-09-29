#!/usr/bin/env python3
"""Random-entry controls (seeded, reproducible), shared by both methods.

Draw d uses np.random.default_rng([crc32(str(d)), crc32(market), salt]) (crc32 of the draw number as
registered), so one market's draw does not depend on how many other markets ran.

CRUDELE C2 (REGISTERED_crudele_3s.md sec 3.6): for each market and year, the same number of trades
per arm and side as the real system took there, on random bars of that year; each held for the number
of bars of a randomly chosen real trade of that ARM (pooled over markets); the same risk fraction, and
a stop at the same ATR distance. Entry at the random bar's open; exit at the stop (gap rule as the real
walks) else at the open of the bar `hold` later (the close of the entry bar if hold is 0).

BREIT C3 (REGISTERED_breit_cap.md sec 3.6): the same count per market and year and the same side mix,
on random bars; stop at the lowest low (highest high for shorts) of the prior k bars, k drawn from the
real run lengths of that market's trades (pooled if none); the same prior-bar-low trail; entry at the
random bar's open; risk fraction copied from the matched real trade. Exit on the trail else data end.

Caveats (printed in the report): random trades within one market may overlap in time, where the real
methods hold one position per market; and a random entry has no setup at all, which is the point.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from strategy.futbt import core as K
from strategy.futbt.core import Trade2, size


def rng_for(d: int, market: str, salt: int = 0):
    return np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(market.encode()), salt])


def _year_index(fr: K.Frame) -> dict:
    y = fr.dates.year.to_numpy()
    out = {}
    for yr in np.unique(y):
        out[int(yr)] = np.nonzero(y == yr)[0]
    return out


def _stop_hit(fr, j0, jmax, d, stop):
    """first bar in [j0, jmax] whose range reaches the (fixed) stop, else -1."""
    seg = fr.l[j0:jmax + 1] <= stop if d == 1 else fr.h[j0:jmax + 1] >= stop
    return int(j0 + np.argmax(seg)) if seg.any() else -1


def crudele_c2_market(fr: K.Frame, real: pd.DataFrame, hold_pool: dict, d: int, equity: float) -> float:
    """net (mid, fractional) of one C2 draw on one market. `real`: this market's real trade rows
    (arm, direction, entry_date, risk_frac, atr_dist); `hold_pool`: arm -> array of real holds."""
    if not len(real):
        return 0.0
    rng = rng_for(d, fr.market, 2)
    atr = fr.atr()
    years = _year_index(fr)
    ry = pd.to_datetime(real["entry_date"]).dt.year.to_numpy()
    trades = []
    n = fr.n
    for (yr, arm, side), grp in real.assign(_y=ry).groupby(["_y", "arm", "direction"]):
        idx = years.get(int(yr))
        if idx is None:
            continue
        pool = hold_pool.get(arm)
        if pool is None or not len(pool):
            continue
        for _, r in grp.iterrows():
            j = int(rng.choice(idx))
            if j < 1 or j >= n - 1 or not np.isfinite(atr[j - 1]):
                continue
            hold = int(rng.choice(pool))
            dist = float(r["atr_dist"]) * atr[j - 1] if np.isfinite(r["atr_dist"]) else np.nan
            if not (dist > 0):
                continue
            side = int(r["direction"])
            px = fr.o[j]
            stop = px - side * dist
            q = size(float(r["risk_frac"]) * equity, dist, fr.mult, False)
            if q <= 0:
                continue
            jx = min(j + hold, n - 1)
            hit = _stop_hit(fr, j, jx if hold > 0 else j, side, stop)
            if hit >= 0:
                ex = min(fr.o[hit], stop) if side == 1 else max(fr.o[hit], stop)
                if hit == j:
                    ex = stop if (side == 1 and fr.o[hit] > stop) or (side == -1 and fr.o[hit] < stop) else fr.o[hit]
                trades.append(Trade2(side, j, hit, px, ex, stop, q, "stop", True))
            else:
                trades.append(Trade2(side, j, jx, px, fr.o[jx] if hold > 0 else fr.c[j], stop, q, "time", False))
    return K.net_mid(trades, fr)


def run_crudele_c2(frames: dict, real_trades: pd.DataFrame, draws: int, equity: float, progress=None) -> dict:
    hold_pool = {a: g["hold"].to_numpy() for a, g in real_trades.groupby("arm")}
    per_mkt = {m: real_trades[real_trades["market"] == m] for m in frames}
    totals = []
    for d in range(draws):
        totals.append(sum(crudele_c2_market(frames[m], per_mkt[m], hold_pool, d, equity) for m in frames))
        if progress and (d + 1) % 100 == 0:
            progress(d + 1)
    a = np.array(totals)
    return dict(draws=draws, p5=float(np.percentile(a, 5)), p50=float(np.percentile(a, 50)),
                p95=float(np.percentile(a, 95)), mean=float(a.mean()), totals=a)


def breit_c3_market(fr: K.Frame, real: pd.DataFrame, k_pool: np.ndarray, d: int, equity: float) -> float:
    if not len(real):
        return 0.0
    rng = rng_for(d, fr.market, 3)
    years = _year_index(fr)
    ry = pd.to_datetime(real["entry_date"]).dt.year.to_numpy()
    trades = []
    n, tick = fr.n, fr.tick
    for _, r in real.assign(_y=ry).iterrows():
        idx = years.get(int(r["_y"]))
        if idx is None:
            continue
        j = int(rng.choice(idx))
        k = int(rng.choice(k_pool)) if len(k_pool) else 4
        if j < k + 1 or j >= n - 1:
            continue
        side = int(r["direction"])
        px = fr.o[j]
        stop0 = fr.l[j - k:j].min() - tick if side == 1 else fr.h[j - k:j].max() + tick
        if (side == 1 and px <= stop0) or (side == -1 and px >= stop0):
            continue
        q = size(float(r["risk_frac"]) * equity, abs(px - stop0), fr.mult, False)
        if q <= 0:
            continue
        # trail: for bar i > j the stop is max(stop0, max_{j<=m<i}(low[m] - tick)) (short: min(.., high + tick))
        span = min(n, j + 400)
        while True:
            if side == 1:
                run = np.maximum.accumulate(fr.l[j:span] - tick)
                stops = np.maximum(stop0, np.r_[-np.inf, run[:-1]])
                hit = fr.l[j:span] <= stops
            else:
                run = np.minimum.accumulate(fr.h[j:span] + tick)
                stops = np.minimum(stop0, np.r_[np.inf, run[:-1]])
                hit = fr.h[j:span] >= stops
            if hit.any() or span >= n:
                break
            span = n
        if hit.any():
            i = int(np.argmax(hit))
            s = stops[i]
            ex = min(fr.o[j + i], s) if side == 1 else max(fr.o[j + i], s)
            trades.append(Trade2(side, j, j + i, px, ex, stop0, q, "stop", True))
        else:
            trades.append(Trade2(side, j, n - 1, px, fr.c[-1], stop0, q, "data_end", False))
    return K.net_mid(trades, fr)


def run_breit_c3(frames: dict, real_trades: pd.DataFrame, draws: int, equity: float, progress=None) -> dict:
    pool_all = real_trades["k"].to_numpy() if len(real_trades) else np.array([], int)
    per = {m: real_trades[real_trades["market"] == m] for m in frames}
    totals = []
    for d in range(draws):
        s = 0.0
        for m, fr in frames.items():
            kp = per[m]["k"].to_numpy() if len(per[m]) else pool_all
            s += breit_c3_market(fr, per[m], kp, d, equity)
        totals.append(s)
        if progress and (d + 1) % 100 == 0:
            progress(d + 1)
    a = np.array(totals)
    return dict(draws=draws, p5=float(np.percentile(a, 5)), p50=float(np.percentile(a, 50)),
                p95=float(np.percentile(a, 95)), mean=float(a.mean()), totals=a)
