#!/usr/bin/env python3
"""Trading-day bars built from the 1H frame (18:00 NY roll) and the F1 daily-trend flag. REGISTERED_chartmark_clone.md sec 6.

Everything a candidate at decision bar t reads from here comes from bars <= t: completed days are the days before the
day of bar t (all of their bars are before t), and today's partial bar is built from bars first..t only."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.chartmark import spec as V1
from strategy.chartmark.data import Frame
from strategy.chartmark_clone import spec as S
from strategy.htf.signals import ema_seeded

WEEKDAY = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass
class Daily:
    day_of_bar: np.ndarray       # trading-day number of every 1H bar
    first: np.ndarray            # first 1H bar index of each day
    last: np.ndarray             # last 1H bar index of each day
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    weekday: np.ndarray          # 0 = Mon .. 6 = Sun of the trading day
    e9: np.ndarray               # EMA over closes of days 0..i (prefix-consistent)
    e21: np.ndarray
    atr: np.ndarray              # Wilder ATR(14) over days 0..i (prefix-consistent), for sub 4's F2

    @property
    def n(self) -> int:
        return len(self.c)


def day_numbers(fr: Frame) -> tuple[np.ndarray, np.ndarray]:
    """(trading-day number per bar, weekday of that trading day per bar)."""
    wall = fr.ny.tz_localize(None) + pd.Timedelta(hours=S.DAY_ROLL_HOURS)
    days = wall.normalize().to_numpy().astype("datetime64[D]").astype(np.int64)
    dn = np.concatenate([[0], np.cumsum(days[1:] != days[:-1])]).astype(np.int64)
    wd = ((days + 3) % 7).astype(np.int64)         # 1970-01-01 was a Thursday
    return dn, wd


def build_daily(fr: Frame) -> Daily:
    dn, wd_bar = day_numbers(fr)
    nd = int(dn[-1]) + 1
    first = np.searchsorted(dn, np.arange(nd), side="left")
    last = np.searchsorted(dn, np.arange(nd), side="right") - 1
    o = fr.o[first]
    c = fr.c[last]
    h = np.maximum.reduceat(fr.h, first)
    l = np.minimum.reduceat(fr.l, first)
    wd = wd_bar[first]
    close = pd.Series(c)
    e9 = ema_seeded(close, 9).to_numpy()
    e21 = ema_seeded(close, 21).to_numpy()
    atr = _wilder_atr(h, l, c, V1.ATR_LEN)
    return Daily(dn, first, last, o, h, l, c, wd, e9, e21, atr)


def _wilder_atr(h, l, c, n) -> np.ndarray:
    """Wilder ATR: seeded on the mean of the first n true ranges; NaN before that. Prefix-consistent."""
    k = len(c)
    out = np.full(k, np.nan)
    if k < n + 1:
        return out
    tr = np.empty(k)
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - pc), np.abs(l[1:] - pc)))
    out[n - 1] = tr[:n].mean()
    for i in range(n, k):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def f1_daily_trend(d: Daily, t: int) -> int:
    """F1: +1 when the last completed daily close is above the daily EMA21, else -1 (warm-up counts as -1, I4)."""
    day = int(d.day_of_bar[t])
    if day < 1:
        return -1
    e = d.e21[day - 1]
    if np.isnan(e):
        return -1
    return 1 if d.c[day - 1] > e else -1


def f1_is_warmup(d: Daily, t: int) -> bool:
    day = int(d.day_of_bar[t])
    return day < 1 or bool(np.isnan(d.e21[day - 1]))


def partial_today(fr: Frame, d: Daily, t: int) -> tuple[float, float, float, float]:
    """Open, high, low, close of today's trading day built from 1H bars first..t only."""
    day = int(d.day_of_bar[t])
    a = int(d.first[day])
    return float(fr.o[a]), float(fr.h[a: t + 1].max()), float(fr.l[a: t + 1].min()), float(fr.c[t])
