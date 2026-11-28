#!/usr/bin/env python3
"""WICK-REV bars: 1-minute (NQ) or 1-hour (CL) or 30-minute (IBKR MCL) source bars -> 30m / 1H / 4H.
W15-0063, REGISTERED_wick_reversal.md sec 2.

Same session convention as strategy.htf.bars (CME 18:00 -> 17:00 New York, bucketed on the NAIVE
wall-clock so a daylight-saving week does not shift a bar an hour). This module generalises its
hour grid to minutes so 30m, 1H and 4H come from one function. 4H bars start 18, 22, 02, 06, 10,
14; the 14:00 bar runs to 17:00 (3 hours) and is kept and flagged `short`. Bars with no trades are
not made up. A source bar at or after elapsed 23h (the 17:00-18:00 hour) is not traded and is dropped.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import bars as HB
from strategy.wick_rev import spec as S

OUT_COLUMNS = ["session", "bar", "t_open", "t_end", "held_id", "open", "high", "low", "close",
               "volume", "n_src", "short"]


def session_dates(df: pd.DataFrame) -> pd.DatetimeIndex:
    return HB.session_of(HB.local_naive(df.index))


def cut_sessions(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Rows whose SESSION date (18:00 ET open) lies in [start, end], inclusive. Called FIRST, before
    resampling or back-adjusting, so a window's neighbours never leak into its bars."""
    if df.empty:
        return df
    sess = session_dates(df)
    keep = np.asarray((sess >= pd.Timestamp(start)) & (sess <= pd.Timestamp(end)))
    return df[keep]


def build_bars(df: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    """Source bars (tz-aware index; held_id/open/high/low/close/volume) -> bars of `bar_minutes`."""
    if df.empty:
        return pd.DataFrame(columns=OUT_COLUMNS)
    naive = HB.local_naive(df.index)
    sess = HB.session_of(naive)
    open_naive = HB.session_open_naive(sess)
    elapsed = np.asarray((naive - open_naive) / pd.Timedelta(minutes=1), dtype=float)
    if (elapsed < 0).any() or (elapsed >= 1440).any():
        raise HB.SessionBoundsError("a source bar's elapsed-since-open fell outside [0, 1440)")
    keep = elapsed < S.SESSION_MINUTES
    d = df[keep].copy()
    sess_k, elapsed_k = sess[keep], elapsed[keep]
    d["session"] = np.asarray(sess_k)
    d["bar"] = np.floor(elapsed_k / bar_minutes).astype(int)
    d["_t"] = d.index
    d = d.sort_values(["session", "bar", "_t"], kind="mergesort")
    g = d.groupby(["session", "bar"], sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
        "held_id": g["held_id"].last(), "n_src": g["open"].size(),
    }).reset_index()
    base = HB.session_open_naive(out["session"])
    start = base + out["bar"] * pd.Timedelta(minutes=bar_minutes)
    end_min = np.minimum((out["bar"] + 1) * bar_minutes, S.SESSION_MINUTES)
    end = base + pd.to_timedelta(end_min, unit="m")

    def utc(x):
        return x.dt.tz_localize(HB.ET, nonexistent="shift_forward", ambiguous=False).dt.tz_convert("UTC")
    out["t_open"], out["t_end"] = utc(start), utc(end)
    out["short"] = (end_min - out["bar"] * bar_minutes) < bar_minutes
    out["session"] = out["session"].dt.date
    return out[OUT_COLUMNS]


def back_adjust_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Difference back-adjust (never ratio): adds open_adj/high_adj/low_adj/close_adj (strategy.htf)."""
    return HB.back_adjust(bars)


def fine_frame(df_fine: pd.DataFrame) -> pd.DataFrame:
    """Finer source bars for resolving same-bar double touches, back-adjusted on their own rolls.
    Columns: t_open (UTC), high_adj, low_adj."""
    f = pd.DataFrame({"t_open": df_fine.index, "held_id": df_fine["held_id"].to_numpy(),
                      "open": df_fine["open"].to_numpy(), "high": df_fine["high"].to_numpy(),
                      "low": df_fine["low"].to_numpy(), "close": df_fine["close"].to_numpy()})
    f = HB.back_adjust(f)
    return f[["t_open", "high_adj", "low_adj"]]


def split_held_v0(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """NQ.v.0 rows (volume-led continuous), held_id = instrument_id, de-duplicated on timestamp."""
    d = df
    if "symbol" in d.columns:
        d = d[d["symbol"] == symbol]
    d = d.copy()
    d = d[~d.index.duplicated(keep="first")]
    if "held_id" not in d.columns:
        d["held_id"] = d["instrument_id"].astype("int64")
    return d.sort_index()
