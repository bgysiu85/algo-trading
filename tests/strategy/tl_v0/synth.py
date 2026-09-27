"""Synthetic contracts and bars for the TL-v0 engine tests. No archive is read."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tsmom.registry import Root

ROOT = Root("XX", 1000.0, "MXX", 0.1)      # front-month roll rule


def weekdays(start="2012-01-02", n=900) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def contracts_and_rows(n=900, start="2012-01-02", seed=7, trend=True,
                       carry=0.8, with_sundays=False):
    """Quarterly contracts; each lists ~200 sessions before expiry and trades
    at the underlying path + a contract-specific carry offset (so every roll
    has a real gap). Returns (rows, contracts, underlying close)."""
    rng = np.random.default_rng(seed)
    days = weekdays(start, n)
    steps = rng.normal(0, 1.0, n)
    if trend:
        regime = np.sign(np.sin(np.arange(n) / 45.0)) * 0.35
        steps = steps + regime
    und = 100 + np.cumsum(steps)
    exps = pd.date_range(days[0] + pd.Timedelta(days=40), days[-1] + pd.Timedelta(days=200), freq="QE-MAR")
    con, rows = [], []
    for i, e in enumerate(exps):
        sym = f"XXH{i}"
        con.append({"symbol": sym, "expiration": e.normalize(), "year": e.year, "month": e.month})
        live = (days <= e) & (days > e - pd.Timedelta(days=300))
        off = carry * (i + 1)
        for d, u in zip(days[live], und[live]):
            o = u + rng.normal(0, 0.3)
            c = u + rng.normal(0, 0.3)
            h = max(o, c) + abs(rng.normal(0, 0.6))
            lo = min(o, c) - abs(rng.normal(0, 0.6))
            rows.append({"date": d, "contract": sym, "open": o + off, "high": h + off,
                         "low": lo + off, "close": c + off, "volume": 100.0, "rank": 0})
    rows = pd.DataFrame(rows)
    if with_sundays:
        mon = rows[rows["date"].dt.dayofweek == 0].copy()
        mon["date"] = mon["date"] - pd.Timedelta(days=1)
        mon["high"] = mon["open"] + 0.1
        mon["low"] = mon["open"] - 0.1
        rows = pd.concat([rows, mon], ignore_index=True)
    return rows, pd.DataFrame(con), und
