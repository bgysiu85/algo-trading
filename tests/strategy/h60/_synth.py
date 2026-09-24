"""Synthetic 60-minute panels for the H60 tests. No real bar is read anywhere
in this suite (REGISTERED_h60_v0.md §2.2: the grid amendment comes first)."""
from __future__ import annotations

import datetime as dt
import zlib

import numpy as np
import pandas as pd

from strategy.h60.bars import ET, slot_start_min
from strategy.h60.panel import Panel, Universe
from strategy.swing.pit_universe import Spell

D0 = dt.date(2020, 1, 6)            # a Monday


def sessions(n: int, start: dt.date = D0) -> list[dt.date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def t_open(day: dt.date, slot: int, grid: str) -> pd.Timestamp:
    base = pd.Timestamp(dt.datetime.combine(day, dt.time(0, 0)), tz=ET)
    return (base + pd.Timedelta(minutes=slot_start_min(slot, grid))).tz_convert("UTC")


def bars_from_closes(symbol: str, days: list[dt.date], closes, *, grid="primary",
                     spread=0.002, volume=1000.0, opens=None, highs=None,
                     lows=None, vols=None, slots=7) -> pd.DataFrame:
    """One row per (day, slot) in order; `closes` is flat over them. Opens
    default to the previous close; highs/lows bracket open and close."""
    closes = np.asarray(closes, float)
    n = len(days) * slots
    assert len(closes) == n, (len(closes), n)
    o = np.r_[closes[0], closes[:-1]] if opens is None else np.asarray(opens, float)
    hi = np.maximum(o, closes) * (1 + spread) if highs is None else np.asarray(highs, float)
    lo = np.minimum(o, closes) * (1 - spread) if lows is None else np.asarray(lows, float)
    v = np.full(n, volume) if vols is None else np.asarray(vols, float)
    rows = []
    k = 0
    for d in days:
        for b in range(slots):
            rows.append((symbol, d, b, t_open(d, b, grid), o[k], hi[k], lo[k],
                         closes[k], v[k], 60))
            k += 1
    return pd.DataFrame(rows, columns=["symbol", "session", "bar", "t_open", "open",
                                       "high", "low", "close", "volume", "n_min"])


def random_walk(symbol: str, days, *, seed_extra: str = "", vol=0.004, drift=0.0,
                start=100.0, grid="primary") -> pd.DataFrame:
    rng = np.random.default_rng(zlib.crc32(f"{symbol}|{seed_extra}".encode("utf-8")))
    n = len(days) * 7
    r = rng.normal(drift, vol, n)
    closes = start * np.exp(np.cumsum(r))
    opens = np.r_[start, closes[:-1]] * np.exp(rng.normal(0, vol / 3, n))
    hi = np.maximum(opens, closes) * np.exp(np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(opens, closes) * np.exp(-np.abs(rng.normal(0, vol / 2, n)))
    vols = rng.lognormal(10, 0.5, n)
    return bars_from_closes(symbol, days, closes, opens=opens, highs=hi, lows=lo,
                            vols=vols, grid=grid)


def spells_for(symbols, start=None, end=None, index="sp500"):
    return [Spell(index, s, s, start, end, True, False) for s in symbols]


def panel(frames, spells=None, grid="primary") -> Panel:
    bars = pd.concat(frames, ignore_index=True)
    if spells is None:
        spells = spells_for(sorted(bars["symbol"].unique()))
    return Panel.build(bars, Universe(spells), grid)
