#!/usr/bin/env python3
"""CHARTMARK-CLONE chart features F1-F15, computed at the decision bar t from bars <= t and the buy-stop level L.
REGISTERED_chartmark_clone.md sec 6 (+ Amendment 2 interpretations I10-I13). Gate G5: look-ahead guards, tests/.

NO PRICE OUTCOME, EXIT OR P&L IS READ HERE. The only inputs are the 1H frame (bars <= t), the order level L from the
manifest and the clock time of the bar the order works into (bar j = t+1, known at the close of t; its prices are not).

    features_at(cd, t, level, j_open_ny) -> dict    one candidate
    feature_table(cd, manifest)          -> DataFrame one row per manifest row, columns FEATURE_COLUMNS

Interpretations fixed here before any fit (Amendment 2):
  I10  ATR = the v1 1H ATR(14) (Pine-rma, ind.atr); H = ind.hist = MACD(12,26,9) - signal (SMA-seeded).
       A feature that cannot be computed yet (too little history, no daily EMA21/ATR yet) is NaN. Rules never fire on a NaN;
       the model imputes the training fold's median.
  I11  F9: sign changes of (close - EMA21) over the 20 bars t-19..t = the 19 consecutive-bar changes in that window.
       F14: bars since the last bar at which (EMA9 > EMA21) changed value, counted back from t, capped at 50 (none in the
       last 50 bars -> 50). F10: bars with no volume SMA(20) yet count as not-below.
  I12  F15 = share of the 500 bars t-500..t-1 whose ATR is strictly below ATR[t]; NaN if fewer than 500 of those bars
       have an ATR.
  I13  F12: session bucket of bar j's open, New York wall clock (Asia 18:00-01:59 = 0, London 02:00-07:59 = 1, US-AM
       08:00-11:59 = 2, US-PM 12:00-17:59 = 3) and the calendar weekday (Mon = 0 .. Sun = 6) of that open;
       the open's hour is carried too (F12_hour) for the event-hour rule (reason 6) and is not a model input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.chartmark_clone import daily as DL
from strategy.chartmark_clone.chartdata import ChartData

FEATURES = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F13", "F14", "F15"]
FEATURE_COLUMNS = FEATURES + ["F12_session", "F12_weekday", "F12_hour"]
SESSION_NAMES = ("Asia", "London", "US-AM", "US-PM")
ATR_HIST = 500


def session_bucket(hour: int) -> int:
    if hour >= 18 or hour < 2:
        return 0
    if hour < 8:
        return 1
    if hour < 12:
        return 2
    return 3


def features_at(cd: ChartData, t: int, level: float, j_open_ny: pd.Timestamp) -> dict:
    """All features for the decision at the close of bar t. Reads fr.*[:t+1], ind.*[:t+1], daily bars completed before
    the day of bar t. `j_open_ny` is only a clock time."""
    fr, ind, dly = cd.fr, cd.ind, cd.daily
    s = slice(max(0, t - 19), t + 1)
    atr = float(ind.atr[t])
    out = {k: np.nan for k in FEATURE_COLUMNS}
    out["F1"] = float(DL.f1_daily_trend(dly, t))
    day = int(dly.day_of_bar[t])
    if day >= 1 and not np.isnan(dly.e21[day - 1]) and not np.isnan(dly.atr[day - 1]) and dly.atr[day - 1] > 0:
        out["F2"] = float((dly.e9[day - 1] - dly.e21[day - 1]) / dly.atr[day - 1])
    out["F12_session"] = float(session_bucket(int(j_open_ny.hour)))
    out["F12_weekday"] = float(j_open_ny.weekday())
    out["F12_hour"] = float(j_open_ny.hour)
    o_t, h_t, l_t, c_t = float(fr.o[t]), float(fr.h[t]), float(fr.l[t]), float(fr.c[t])
    rng_t = h_t - l_t
    out["F13"] = float((h_t - max(o_t, c_t)) / rng_t) if rng_t > 0 else 0.0
    if np.isnan(atr) or atr <= 0:
        return out
    e9, e21, hist = ind.e9, ind.e21, ind.hist
    if not (np.isnan(e9[t]) or np.isnan(e21[t])):
        out["F3"] = float((e9[t] - e21[t]) / atr)
        out["F8"] = float((level - e21[t]) / atr)
    if not np.isnan(hist[t]):
        out["F4"] = float(hist[t] / atr)
        if t >= 2 and not np.isnan(hist[t - 2]):
            out["F5"] = float((hist[t] - hist[t - 2]) / atr)
    out["F6"] = float((level - c_t) / atr)
    if t >= 19:
        out["F7"] = float((c_t - fr.l[s].min()) / atr)
        out["F11"] = float((fr.h[s].max() - fr.l[s].min()) / atr)
        pos = fr.c[s] > e21[s]
        valid = ~np.isnan(e21[s])
        ch = (pos[1:] != pos[:-1]) & valid[1:] & valid[:-1]
        out["F9"] = float(ch.sum())
        vs = ind.vol_sma[t - 9: t + 1]
        below = (fr.v[t - 9: t + 1] < vs) & ~np.isnan(vs)
        out["F10"] = float(below.mean()) if t >= 9 else np.nan
    # F14: bars since the last EMA9/EMA21 cross, capped at 50
    lo = max(1, t - 49)
    since = 50
    for k in range(t, lo - 1, -1):
        if np.isnan(e21[k]) or np.isnan(e21[k - 1]):
            break
        if (e9[k] > e21[k]) != (e9[k - 1] > e21[k - 1]):
            since = t - k
            break
    out["F14"] = float(min(since, 50))
    if t >= ATR_HIST:
        prior = ind.atr[t - ATR_HIST: t]
        if not np.isnan(prior).any():
            out["F15"] = float((prior < atr).mean())
    return out


def feature_table(cd: ChartData, manifest: pd.DataFrame) -> pd.DataFrame:
    """One row per candidate in manifest order. The fill-bar open time (candidate_id, NY wall clock) is bar j's clock."""
    rows = []
    for r in manifest.itertuples(index=False):
        j_open = pd.Timestamp(r.candidate_id)
        d = features_at(cd, int(r.decision_idx), float(r.level), j_open)
        d["candidate_id"] = r.candidate_id
        rows.append(d)
    return pd.DataFrame(rows, columns=["candidate_id"] + FEATURE_COLUMNS)
