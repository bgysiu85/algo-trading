#!/usr/bin/env python3
"""Frames and indicators for CHARTMARK-v1. Training frame = CL 1H, cut to sessions before 2022-01-01 FIRST, then
resampled and difference-back-adjusted (strategy.futbt.loading / strategy.htf.bars). Seen frame = the TradingView
CL1! bars Ben marked (no archive bars from 2022 on are read by this package)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14
from strategy.chartmark import spec as S
from strategy.htf import bars as HB
from strategy.htf.signals import ema_seeded, macd_seeded


@dataclass
class Frame:
    t: pd.DatetimeIndex            # bar open, UTC
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    roll_after: np.ndarray         # bool: held contract changes between j and j+1
    label: str = ""

    @property
    def n(self) -> int:
        return len(self.c)

    @property
    def ny(self) -> pd.DatetimeIndex:
        return self.t.tz_convert(HB.ET)


@dataclass
class Ind:
    atr: np.ndarray
    e9: np.ndarray
    e21: np.ndarray
    hist: np.ndarray
    hour: np.ndarray               # NY hour of bar open
    vol_sma: np.ndarray
    _cache: dict = field(default_factory=dict)


def make_frame(t, o, h, l, c, v, roll_after=None, label="") -> Frame:
    n = len(c)
    ra = np.zeros(n, bool) if roll_after is None else np.asarray(roll_after, bool)
    return Frame(pd.DatetimeIndex(t), *(np.asarray(x, float) for x in (o, h, l, c, v)), ra, label)


def indicators(fr: Frame) -> Ind:
    close = pd.Series(fr.c)
    atr = atr14(fr.h, fr.l, fr.c).astype(float)
    atr[: S.ATR_LEN - 1] = np.nan
    e9 = ema_seeded(close, 9).to_numpy()
    e21 = ema_seeded(close, 21).to_numpy()
    line, sig = macd_seeded(close)
    hist = (line - sig).to_numpy()
    vol_sma = pd.Series(fr.v).rolling(S.AVOID_VOLSMA, min_periods=S.AVOID_VOLSMA).mean().to_numpy()
    return Ind(atr, e9, e21, hist, np.asarray(fr.ny.hour), vol_sma)


def context(fr: Frame, ind: Ind, p: S.Params) -> np.ndarray:
    """Context at the CLOSE of each bar t (bar t's values only): X1 & X2 & X3 [& X4] [& ~AVOID]."""
    key = (p.session, p.x4, p.x4_lb, p.avoid)
    if key in ind._cache:
        return ind._cache[key]
    n = fr.n
    h_, e9, e21, c = ind.hist, ind.e9, ind.e21, fr.c
    with np.errstate(invalid="ignore"):
        rising = np.zeros(n, bool)
        rising[2:] = (h_[2:] > h_[1:-1]) & (h_[1:-1] > h_[:-2])
        x1 = (h_ >= 0) | rising
        x2 = c > e21
        ok = x1 & x2 & ~np.isnan(ind.atr) & ~np.isnan(h_) & ~np.isnan(e21)
        if p.session:
            ok &= (ind.hour >= S.SESSION_FIRST) & (ind.hour <= S.SESSION_LAST)
        if p.x4:
            gap = e21 - e9
            dn = np.zeros(n, bool)
            dn[1:] = gap[1:] < gap[:-1]
            narrowed = pd.Series(dn.astype(float)).rolling(p.x4_lb, min_periods=p.x4_lb).min().fillna(0).to_numpy() > 0
            ok &= (e9 >= e21) | narrowed
        if p.avoid:
            ok &= ~avoid_flag(fr, ind)
    ind._cache[key] = ok
    return ok


def avoid_flag(fr: Frame, ind: Ind) -> np.ndarray:
    """Amendment A.1: |EMA21[t]-EMA21[t-10]| < 0.5 ATR[t] and >= 7 of bars t-9..t below their own SMA20 volume."""
    n, L = fr.n, S.AVOID_LOOK
    flat = np.zeros(n, bool)
    below = (fr.v < ind.vol_sma).astype(float)
    below[np.isnan(ind.vol_sma)] = 0.0
    cnt = pd.Series(below).rolling(L, min_periods=L).sum().to_numpy()
    with np.errstate(invalid="ignore"):
        slope = np.full(n, np.nan)
        slope[L:] = np.abs(ind.e21[L:] - ind.e21[:-L])
        flat = (slope < S.AVOID_SLOPE * ind.atr) & (cnt >= S.AVOID_MIN_LOW)
    return np.nan_to_num(flat, nan=False).astype(bool)


def load_training_frame(archive) -> Frame:
    """CL 1H, sessions 2010-06-06 .. 2021-12-31 only. The cut is made before resample / back-adjust."""
    from strategy.futbt import loading as LD
    df = LD.cut_1h_to_training(HB.load_1h(archive))
    e = HB.back_adjust(HB.resample(df, "1H"))
    held = e["held_id"].to_numpy()
    ra = np.zeros(len(e), bool)
    ra[:-1] = held[1:] != held[:-1]
    return make_frame(pd.to_datetime(e["t_open"], utc=True), e["open_adj"], e["high_adj"], e["low_adj"],
                      e["close_adj"], e["volume"], ra, "CL 1H training 2010-06..2021-12 (back-adjusted)")


def load_seen_frame(csv_path) -> Frame:
    """TradingView CL1! 1H bars (Ben's marked window, 2025-09-08 on). Reported only: seen -- not evidence."""
    d = pd.read_csv(csv_path)
    t = pd.to_datetime(d["t"], unit="s", utc=True)
    return make_frame(t, d["o"], d["h"], d["l"], d["c"], d["v"], None, "TradingView CL1! 1H seen window")
