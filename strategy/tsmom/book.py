#!/usr/bin/env python3
"""The book: tranches, sizing, integer contracts, P/L on the held contract.

REGISTERED_tsmom section 2 and spec sections 1.3, 1.4, 4 and 6.

TIMING -- one rule, used everywhere
-----------------------------------
A rebalance on master session d trades AT THE CLOSE OF d, on information
through the close of the PREVIOUS master session (d-1): the signal's window
ends at d-1, the volatility is the estimate known at d-1 (so the return of d is
not in it -- MOP's "estimates at time t-1 applied to time-t returns"), and the
price used to size is the held contract's close at d-1. The new position earns
from d+1. Nothing in a decision reads the bar it trades on.

SLEEVES AND ROUNDING
--------------------
Five sleeves, each with a fifth of the equity, rebalanced on trading days
1/5/9/13/17 of the month (master calendar). Each sleeve holds a FRACTIONAL
target until its next rebalance. The fractional book is their sum. The integer
book is that sum rounded half away from zero -- ONE account holds one net
position per market; rounding each sleeve separately would model five
accounts. 0.4 of a contract is 0: not traded (spec section 1.3 [D]).

SIZING -- spec section 1.3 [D], per sleeve:
    target $vol per market = 0.40 * (E/5) / N,  N = markets live at d
    n* = mean_k sign_k * target / (vehicle point value * price * sigma)
The ensemble enters as the mean of the k-month signs (the equal-weight average
of the four single-k books), so a split signal is a smaller position.

A market is LIVE at d when it has WARMUP_RETURNS returns through d-1 and every
lookback window exists. A market that is not live is ABSENT (the `live` frame),
not flat -- REGISTERED_tsmom section 8 requires the two to be distinguishable.

P/L AND COSTS -- spec section 4 rule 3 and section 6
----------------------------------------------------
P/L(t) = pos(t-1) * dP(t) * vehicle point value, dP on the contract HELD over
t (roll.held_series). The continuous series never enters P/L.

Contract-sides at the close of t, with old = pos(t-1), new = pos(t):
  no roll:  rebalance sides = |new - old|
  roll:     the old contract is closed (|old|) and the new one opened (|new|);
            roll sides = 2*min(|old|,|new|) when both are on the same side,
            the remainder is rebalance. A roll with no size change is exactly
            2*|pos| sides of roll, the "two sides at every roll" of section 6.
Cost = sides * friction, at each of the three registered levels.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.tsmom.registry import (ENSEMBLE_KS, FRICTION, TARGET_VOL,
                                     TRANCHE_DAYS, WARMUP_RETURNS, Root)
from strategy.tsmom.signal import ensemble_sign, ewma_vol_info


def round_half_away(x):
    """Integer contracts: 0.5 -> 1, -0.5 -> -1, 0.4 -> 0, 1.5 -> 2 (not
    Python's banker's rounding, which sends 0.5 and 2.5 to the even number)."""
    a = np.asarray(x, dtype=float)
    return np.sign(a) * np.floor(np.abs(a) + 0.5)


def tranche_calendar(master: pd.DatetimeIndex,
                     days: tuple[int, ...] = TRANCHE_DAYS) -> pd.Series:
    """Sleeve number (0..len(days)-1) on each master session that is a tranche
    day, else -1. Day n = the n-th session of the calendar month, counting only
    sessions, so a holiday moves the tranche to the next session."""
    m = pd.DatetimeIndex(master)
    ym = m.year * 12 + m.month
    ordinal = pd.Series(1, index=m).groupby(ym).cumsum().to_numpy()
    lookup = {d: i for i, d in enumerate(days)}
    return pd.Series([lookup.get(int(o), -1) for o in ordinal], index=m, name="sleeve")


@dataclass
class BookResult:
    roots: list[str]
    equity: float
    live: pd.DataFrame
    signal: pd.DataFrame           # sign used at each rebalance (NaN between)
    pos_frac: pd.DataFrame
    pos_int: pd.DataFrame
    pnl_frac: pd.DataFrame         # gross, USD
    pnl_int: pd.DataFrame
    sides: dict = field(default_factory=dict)   # (sizing, "roll"|"rebalance") -> frame

    def costs(self, sizing: str, level: str) -> pd.DataFrame:
        fee = FRICTION[level]
        return (self.sides[(sizing, "roll")] + self.sides[(sizing, "rebalance")]) * fee

    def net(self, sizing: str, level: str) -> pd.DataFrame:
        gross = self.pnl_frac if sizing == "frac" else self.pnl_int
        return gross - self.costs(sizing, level)


def _sides(old: np.ndarray, new: np.ndarray, rolled: np.ndarray):
    ao, an = np.abs(old), np.abs(new)
    same = (old * new) > 0
    roll = np.where(rolled & same, 2 * np.minimum(ao, an), 0.0)
    total = np.where(rolled, ao + an, np.abs(new - old))
    return roll, total - roll


def run_book(series: dict[str, pd.DataFrame], roots: dict[str, Root], *,
             equity: float, ks=ENSEMBLE_KS, tranche_days=TRANCHE_DAYS,
             signal_mode: str = "tsmom", skip_months: int = 0) -> BookResult:
    """`series`: root name -> roll.held_series frame on that root's own sessions.
    `signal_mode`: "tsmom" (the registered spec) or "long" (the equal-weight,
    same-vol-scaled buy-and-hold benchmark of section 3 item 7).
    `skip_months`: 0 is the registered spec (no skip, spec section 1.1 [P]).
    1 is the skip-month NEIGHBOUR the section 2 table keeps as reported only:
    the window ends `skip_months` calendar months before the information date."""
    if signal_mode not in ("tsmom", "long"):
        raise ValueError(signal_mode)
    if skip_months < 0:
        raise ValueError(skip_months)
    names = [n for n in roots if n in series]
    if set(names) != set(roots):
        raise KeyError(f"no series for {sorted(set(roots) - set(series))}")
    master = pd.DatetimeIndex(sorted(set().union(*[series[n].index for n in names])))
    n_sl = len(tranche_days)
    sleeve = tranche_calendar(master, tranche_days).to_numpy()
    T, R = len(master), len(names)

    # decision inputs, known at the close of the PREVIOUS master session
    vol_i = np.full((T, R), np.nan)
    px_i = np.full((T, R), np.nan)
    nret_i = np.zeros((T, R))
    sig_i = np.full((T, R), np.nan)
    dP = np.zeros((T, R))
    rolled = np.zeros((T, R), dtype=bool)
    info = pd.DatetimeIndex(np.r_[master.values[:1], master.values[:-1]])  # d-1 (row 0 unused)
    for j, n in enumerate(names):
        f = series[n]
        vol = ewma_vol_info(f["ret"]).reindex(master).ffill()
        cnt = f["ret"].notna().cumsum().reindex(master).ffill().fillna(0)
        raw = f["raw"].reindex(master).ffill()
        vol_i[1:, j] = vol.to_numpy()[:-1]
        nret_i[1:, j] = cnt.to_numpy()[:-1]
        px_i[1:, j] = raw.to_numpy()[:-1]
        if signal_mode == "tsmom":
            cont = f["cont"].reindex(master).ffill()
            ends = info - pd.DateOffset(months=skip_months) if skip_months else info
            s = ensemble_sign(cont, pd.DatetimeIndex(ends), ks).to_numpy()
        else:
            s = np.where(cnt.to_numpy() > 0, 1.0, np.nan)
            s = np.r_[np.nan, s[:-1]]
        sig_i[1:, j] = s[1:]
        dP[:, j] = f["dP"].fillna(0.0).reindex(master, fill_value=0.0).to_numpy()
        rolled[:, j] = f["rolled"].astype(bool).reindex(master, fill_value=False).to_numpy()

    live = (nret_i >= WARMUP_RETURNS) & np.isfinite(sig_i) & np.isfinite(vol_i) \
        & (vol_i > 0) & np.isfinite(px_i)
    live[0, :] = False
    vpv = np.array([roots[n].vehicle_point_value for n in names])

    sleeve_pos = np.zeros((n_sl, R))
    pos_frac = np.zeros((T, R))
    signal_used = np.full((T, R), np.nan)
    live_at_reb = np.zeros((T, R), dtype=bool)
    for t in range(T):
        s_ix = sleeve[t]
        if t > 0 and s_ix >= 0:
            L = live[t]
            N = int(L.sum())
            new = np.zeros(R)
            if N:
                target = TARGET_VOL * (equity / n_sl) / N
                with np.errstate(divide="ignore", invalid="ignore"):
                    n_star = sig_i[t] * target / (vpv * px_i[t] * vol_i[t])
                new[L] = n_star[L]
            sleeve_pos[s_ix] = new
            signal_used[t] = np.where(L, sig_i[t], np.nan)
            live_at_reb[t] = L
        pos_frac[t] = sleeve_pos.sum(axis=0)
    pos_int = round_half_away(pos_frac)

    prev_f = np.vstack([np.zeros((1, R)), pos_frac[:-1]])
    prev_i = np.vstack([np.zeros((1, R)), pos_int[:-1]])
    pnl_f = prev_f * dP * vpv
    pnl_i = prev_i * dP * vpv
    rf, bf = _sides(prev_f, pos_frac, rolled)
    ri, bi = _sides(prev_i, pos_int, rolled)

    df = lambda a: pd.DataFrame(a, index=master, columns=names)  # noqa: E731
    return BookResult(
        roots=names, equity=equity,
        live=df(live), signal=df(signal_used),
        pos_frac=df(pos_frac), pos_int=df(pos_int),
        pnl_frac=df(pnl_f), pnl_int=df(pnl_i),
        sides={("frac", "roll"): df(rf), ("frac", "rebalance"): df(bf),
               ("int", "roll"): df(ri), ("int", "rebalance"): df(bi)})
