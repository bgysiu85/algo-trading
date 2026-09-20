"""Synthetic futures for the TSMOM tests. No archive is read here, ever."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tsmom.engine import RootInputs

MONTH_CODE = "FGHJKMNQUVXZ"


def sessions(start: str, end: str, holidays=()) -> pd.DatetimeIndex:
    s = pd.bdate_range(start, end)
    return s[~s.isin(pd.to_datetime(list(holidays)))]


def monthly_contracts(root: str, first: str, last: str, months=range(1, 13),
                      expiry_day: int = 20) -> pd.DataFrame:
    """One contract per listed month, expiring on `expiry_day` of that month."""
    rows = []
    for p in pd.period_range(first, last, freq="M"):
        if p.month not in months:
            continue
        rows.append({"symbol": f"{root}{MONTH_CODE[p.month - 1]}{p.year % 10}_{p.year}",
                     "expiration": pd.Timestamp(p.year, p.month, expiry_day),
                     "year": p.year, "month": p.month})
    return pd.DataFrame(rows)


def prices_for(contracts: pd.DataFrame, sess: pd.DatetimeIndex, base: np.ndarray,
               step: float = 1.0) -> pd.DataFrame:
    """Contract i trades at base + i*step (a constant, known gap between
    neighbours) on every session up to its expiration."""
    out = {}
    for i, c in enumerate(contracts.itertuples()):
        p = pd.Series(base + i * step, index=sess)
        p[sess > pd.Timestamp(c.expiration)] = np.nan
        out[c.symbol] = p
    return pd.DataFrame(out, index=sess)


def trending_root(root: str, start="2017-01-02", end="2021-12-31", drift=0.0004,
                  seed=1, level=100.0, step=0.5, months=(3, 6, 9, 12)) -> RootInputs:
    sess = sessions(start, end)
    rng = np.random.default_rng(seed)
    r = drift + 0.01 * rng.standard_normal(len(sess))
    base = level * np.cumprod(1 + r)
    con = monthly_contracts(root, pd.Timestamp(start).to_period("M").strftime("%Y-%m"),
                            (pd.Timestamp(end) + pd.DateOffset(months=6)).strftime("%Y-%m"),
                            months=months)
    return RootInputs(con, prices_for(con, sess, base, step))
