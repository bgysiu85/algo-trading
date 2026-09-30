"""H-B daily bars, rebuilt from the owned ES.v.0 / NQ.v.0 1-minute bars (REGISTERED_otf_gate.md sec 2.3, G6).

CME trading date: 18:00 ET of the prior day -> 17:00 ET, the candle TradingView's ES1! / NQ1! draws. Label of a
bar = the calendar date of (ET wall clock + 6h), so Sunday 18:00 ET -> Monday's label and Friday 16:59 ET ->
Friday's. Bars that start 17:00-17:59 ET (the maintenance hour) belong to no session and are dropped.

Back-adjustment is additive at every change of instrument id: gap = open of the first 1-min bar of the new id
minus close of the last 1-min bar of the old id, and the two bars must be <= 5 minutes apart -- otherwise STOP
and report (sec 2.3). Adjusted price = raw + sum of the gaps of all later switches (the last segment is raw).

The holdout is cut FIRST: bar labels go through holdout.split_dates("H-B") before any switch, gap or daily bar
is built (G3/G4). Weeks (Mon-Fri labels = the CME week Sunday 18:00 -> Friday 17:00) and months come from the
label, in otf.Stack.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.otf_gate import spec as S
from strategy.otf_gate.holdout import H as HOLD

ET = "America/New_York"


class RollGapError(SystemExit):
    """A roll switch whose two 1-min bars are more than 5 minutes apart (sec 2.3: stop and report)."""


def trading_labels(idx: pd.DatetimeIndex):
    """(label dates as datetime64[D] array, in_session bool array) for a tz-aware UTC bar-start index."""
    if idx.tz is None:
        raise ValueError("index must be tz-aware")
    et = idx.tz_convert(ET).tz_localize(None)
    in_session = et.hour != 17
    label = (et + pd.Timedelta(hours=S.CME_OPEN_SHIFT_HOURS)).normalize()
    return label.to_numpy("datetime64[ns]"), np.asarray(in_session)


def _id_col(df):
    for c in ("held_id", "instrument_id"):
        if c in df.columns:
            return c
    raise KeyError("expected a 'held_id' or 'instrument_id' column")


def find_switches(df: pd.DataFrame) -> pd.DataFrame:
    """Every change of instrument id in a time-sorted 1-min frame, with its gap and its time distance."""
    ids = df[_id_col(df)].to_numpy()
    k = np.flatnonzero(ids[1:] != ids[:-1]) + 1
    t = df.index
    op, cl = df["open"].to_numpy(dtype=float), df["close"].to_numpy(dtype=float)
    return pd.DataFrame({
        "k": k, "time_old": t[k - 1], "time_new": t[k], "id_old": ids[k - 1], "id_new": ids[k],
        "minutes": (t[k] - t[k - 1]).total_seconds() / 60.0,
        "gap": op[k] - cl[k - 1],
    }).assign(ok=lambda x: x["minutes"] <= S.HB_MAX_SWITCH_MINUTES)


def back_adjust(df: pd.DataFrame, sw: pd.DataFrame, strict: bool = True) -> pd.DataFrame:
    """Additive back-adjustment; returns a copy with adjusted open/high/low/close."""
    if strict and len(sw) and not sw["ok"].all():
        bad = sw.loc[~sw["ok"], ["time_old", "time_new", "minutes", "id_old", "id_new"]]
        raise RollGapError("STOP: roll switch(es) whose 1-min bars are more than "
                           f"{S.HB_MAX_SWITCH_MINUTES} minutes apart (sec 2.3):\n{bad.to_string()}")
    g = np.zeros(len(df))
    if len(sw):
        np.add.at(g, sw["k"].to_numpy() - 1, sw["gap"].to_numpy())
    off = np.cumsum(g[::-1])[::-1]
    out = df.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = out[c].to_numpy(dtype=float) + off
    return out


def cut_training(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Keep only bars whose trading-date label is a H-B TRAINING day (the holdout is cut first)."""
    lab, ins = trading_labels(df_1m.index)
    days = pd.DatetimeIndex(lab).strftime("%Y-%m-%d")
    uniq = sorted(set(days))
    keep, _n, _ = HOLD.split_dates("H-B", uniq)
    m = np.isin(days, list(keep)) & ins
    return df_1m.loc[m]


def rebuild_daily(df_1m: pd.DataFrame, strict: bool = True):
    """(daily frame date/open/high/low/close/volume/n_bars, switches). Training bars only, weekdays only."""
    df = cut_training(df_1m.sort_index())
    if df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "n_bars"]), pd.DataFrame()
    sw = find_switches(df)
    adj = back_adjust(df, sw, strict=strict)
    lab, _ = trading_labels(adj.index)
    wk = pd.DatetimeIndex(lab).dayofweek < 5
    adj, lab = adj.loc[wk], lab[wk]
    vol = adj["volume"].to_numpy(dtype=float) if "volume" in adj.columns else np.zeros(len(adj))
    g = pd.DataFrame({"date": lab, "open": adj["open"].to_numpy(), "high": adj["high"].to_numpy(),
                      "low": adj["low"].to_numpy(), "close": adj["close"].to_numpy(), "volume": vol}
                     ).groupby("date", sort=True)
    daily = pd.DataFrame({"date": g["open"].first().index,
                          "open": g["open"].first().to_numpy(), "high": g["high"].max().to_numpy(),
                          "low": g["low"].min().to_numpy(), "close": g["close"].last().to_numpy(),
                          "volume": g["volume"].sum().to_numpy(), "n_bars": g["open"].size().to_numpy()})
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.reset_index(drop=True), sw


def session_check(daily: pd.DataFrame) -> dict:
    """G6: rebuilt sessions per year vs XNYS trading days. Missing > 1% in a year -> stop."""
    from strategy.w16.sessions import session_date_range
    have = set(daily["date"].dt.strftime("%Y-%m-%d"))
    y0, y1 = int(daily["date"].dt.year.min()), int(daily["date"].dt.year.max())
    first, last = daily["date"].min().strftime("%Y-%m-%d"), daily["date"].max().strftime("%Y-%m-%d")
    xnys = [d for d in session_date_range(y0, y1) if first <= d <= last]
    rows = {}
    for y in range(y0, y1 + 1):
        ys = [d for d in xnys if d.startswith(str(y))]
        miss = [d for d in ys if d not in have]
        rows[y] = {"xnys_days": len(ys), "rebuilt": len(ys) - len(miss), "missing": len(miss),
                   "missing_share": (len(miss) / len(ys)) if ys else 0.0, "missing_dates": miss[:10]}
    extra = sorted(have - set(xnys))
    return {"years": rows, "extra_cme_days": len(extra),
            "stop": any(r["missing_share"] > S.HB_MISSING_STOP for r in rows.values())}


def load_root(archive, root: str) -> pd.DataFrame:
    """The owned ES.v.0 / NQ.v.0 ohlcv-1m (W16 archive), held_id attached, sorted. Reuses W16's own loader."""
    from strategy.w16.preflight import load_root_bars
    return load_root_bars(archive, root)
