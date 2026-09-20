#!/usr/bin/env python3
"""The ex-ante volatility estimate and the trailing-return signal.

VOLATILITY -- MOP eq. (1), p. 233, REGISTERED_tsmom section 2:

    sigma^2_t = 261 * sum_i (1-delta) delta^i (r_{t-1-i} - rbar_t)^2,
    delta = 60/61 (centre of mass 60), rbar_t the EW mean computed the same way,
    and the estimate at t-1 is applied to returns at t ("lagged one day").

`pandas.ewm(com=60, adjust=True).var(bias=True)` is the same weighted sum with
the weights normalised over the history available, which is what equation (1)'s
"weights add up to one" means on a finite sample. `bias=False` multiplies by a
debiasing factor equation (1) does not have and still produces a plausible
number; the test suite tells the two apart against a hand-built sum.

The returns are the HELD contract's daily returns (roll.held_series `ret`):
dP / previous price of the contract held over that day. That is the paper's
"daily excess return of the most liquid futures contract" (p. 230) and it is
what the difference-adjusted continuous series moves by, divided by the price
level actually held -- never by an adjusted level, which on a series that has
rolled 60+ times can be near zero or negative.

SIGNAL -- MOP eq. (5) and section 3.2: the sign of the past return over
t-k-1 ... t-1, NO skip month (spec section 1.1 [P]; footnote 10's skip belongs
to the cross-sectional factor). On the difference-adjusted series the k-month
sign is the sign of the DOLLAR change cont(i) - cont(start): a level ratio would
flip sign wherever the back-adjusted level crosses zero, and the dollar change
equals the sum of the held contracts' own dollar moves over the window, gaps
excluded. That reading is fixed here, before any return is computed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tsmom.registry import ANNUALISE, EWMA_COM, WARMUP_RETURNS


def ewma_var_annual(ret: pd.Series) -> pd.Series:
    """Annualised EW variance of returns THROUGH t (unlagged). Equation (1)
    without the lag; `ex_ante_vol` applies the lag."""
    return ret.ewm(com=EWMA_COM, adjust=True).var(bias=True) * ANNUALISE


def ewma_vol_info(ret: pd.Series) -> pd.Series:
    """sqrt of the above: the estimate KNOWN at the close of t."""
    return np.sqrt(ewma_var_annual(ret))


def ex_ante_vol(ret: pd.Series) -> pd.Series:
    """sigma applied to day t: the estimate known at t-1 (MOP p. 233), and NaN
    until WARMUP_RETURNS returns exist before t (spec section 1.2 [D])."""
    vol = ewma_vol_info(ret).shift(1)
    n_before = ret.notna().cumsum().shift(1)
    return vol.where(n_before >= WARMUP_RETURNS)


def lookback_start(info_dates: pd.DatetimeIndex, calendar: pd.DatetimeIndex,
                   k: int) -> np.ndarray:
    """For each information date i, the last calendar session on or before
    i minus k calendar months (-1 if none)."""
    target = pd.DatetimeIndex(info_dates) - pd.DateOffset(months=k)
    return calendar.searchsorted(target.values, side="right") - 1


def trailing_sign(cont: pd.Series, info_dates: pd.DatetimeIndex, k: int) -> pd.Series:
    """sign(cont(i) - cont(start_k(i))) for each information date i.

    `cont` is on a session calendar (NaN before the root exists). NaN where the
    window's start is before the data -- the root is not yet eligible.
    """
    cal = pd.DatetimeIndex(cont.index)
    info_dates = pd.DatetimeIndex(info_dates)
    end_pos = cal.searchsorted(info_dates.values, side="right") - 1
    start_pos = lookback_start(info_dates, cal, k)
    vals = cont.to_numpy(dtype=float)
    out = np.full(len(info_dates), np.nan)
    ok = (start_pos >= 0) & (end_pos >= 0)
    e = vals[end_pos[ok]]
    s = vals[start_pos[ok]]
    out[ok] = np.sign(e - s)          # NaN propagates if either end is missing
    return pd.Series(out, index=info_dates, name=f"sign_k{k}")


def ensemble_sign(cont: pd.Series, info_dates: pd.DatetimeIndex, ks) -> pd.Series:
    """Equal-weight ensemble: the mean of the k-month signs. NaN if any k is not
    yet available, so the root enters only when every lookback exists."""
    frame = pd.concat([trailing_sign(cont, info_dates, k) for k in ks], axis=1)
    m = frame.mean(axis=1, skipna=False)
    m.name = "ensemble"
    return m
