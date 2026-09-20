#!/usr/bin/env python3
"""Which contract is held on each session, and the two series built from it.

REGISTERED_tsmom section 2 and spec section 4, with amendment C (section 0.2):

  * the HELD contract is read from the `definition` calendar, never inferred
    from volume or open interest;
  * the SIGNAL series is the difference-back-adjusted continuous series built
    from the held sequence;
  * P/L is taken on the ACTUAL held contract. The continuous series is for the
    signal and the volatility estimate and for NOTHING else.

WHAT A "SESSION" IS HERE
------------------------
A session is a date on which the root's own bar files have a bar, Sundays
removed (`archive.py` drops them; see its docstring for why: GLBX daily bars
are UTC days, and a Sunday row is the first hour of Monday's session, not a
trading day). "Five trading days before" counts these sessions.

THE ROLL, PRECISELY
-------------------
For a contract C with event session X(C):

  rule "front": X(C) = the last session on or before C's expiration date;
  rule "cycle": X(C) = the first session on or after the 1st of C's delivery
                month, and only contracts whose month is in the root's cycle
                are eligible.

The roll session is R(C) = the session ROLL_OFFSET_SESSIONS before X(C). The
position is carried in C through the close of R(C) and moved into the next
contract AT that close, so C earns the close-to-close move of R(C) and the next
contract earns from R(C) onward. Hence:

    held(t) = the first eligible contract, in event order, with R(C) > t

i.e. `held(t)` is what is held AFTER the close of t. A contract whose event lies
beyond the last session has no roll inside the data (R = +inf).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.tsmom.registry import ROLL_OFFSET_SESSIONS, Root


def _as_sessions(sessions) -> pd.DatetimeIndex:
    s = pd.DatetimeIndex(sessions)
    if s.tz is not None:
        s = s.tz_localize(None)
    s = s.normalize()
    if not s.is_monotonic_increasing or s.has_duplicates:
        raise ValueError("sessions must be strictly increasing dates")
    if (s.dayofweek >= 5).any():
        raise ValueError("a weekend date is in the session calendar -- GLBX daily "
                         "bars are UTC days and the Sunday stub is not a session "
                         "(archive.py drops it); counting it would move every roll")
    return s


def roll_schedule(contracts: pd.DataFrame, sessions, root: Root,
                  offset: int = ROLL_OFFSET_SESSIONS) -> pd.DataFrame:
    """Eligible contracts in holding order, with their event and roll sessions.

    `contracts` needs columns: symbol, expiration (date-like), year, month.
    Returns columns: symbol, expiration, event, roll (NaT = no roll in data).
    Contracts that were rolled out of before the first session are dropped:
    they are never held.
    """
    s = _as_sessions(sessions)
    c = contracts.copy()
    c["expiration"] = pd.to_datetime(c["expiration"])
    if getattr(c["expiration"].dt, "tz", None) is not None:
        c["expiration"] = c["expiration"].dt.tz_localize(None)
    c["expiration"] = c["expiration"].dt.normalize()
    c = c.drop_duplicates("symbol")

    if root.rule == "cycle":
        if not root.cycle:
            raise ValueError(f"{root.name}: cycle rule with no cycle")
        c = c[c["month"].isin(root.cycle)].copy()
        first_of_month = pd.to_datetime(dict(year=c["year"], month=c["month"], day=1))
        idx = s.searchsorted(first_of_month.values, side="left")
        beyond = idx >= len(s)
    elif root.rule == "front":
        idx = s.searchsorted(c["expiration"].values, side="right") - 1
        beyond = c["expiration"].values > s[-1].to_datetime64()
    else:
        raise ValueError(f"{root.name}: unknown roll rule {root.rule!r}")

    idx = np.asarray(idx)
    beyond = np.asarray(beyond)
    ridx = idx - offset
    event = np.where(beyond, np.datetime64("NaT"),
                     s.values[np.clip(idx, 0, len(s) - 1)])
    roll = np.where(beyond, np.datetime64("NaT"),
                    s.values[np.clip(ridx, 0, len(s) - 1)])
    out = pd.DataFrame({"symbol": c["symbol"].values,
                        "expiration": c["expiration"].values,
                        "event": pd.to_datetime(event),
                        "roll": pd.to_datetime(roll)})
    # rolled out of before the data starts -> never held
    out = out[beyond | (ridx >= 0)]
    out = out.sort_values(["expiration", "symbol"]).reset_index(drop=True)
    r = out["roll"].dropna()
    if not r.is_monotonic_increasing or r.duplicated().any():
        raise ValueError(f"{root.name}: roll sessions are not strictly increasing "
                         f"in expiry order:\n{out}")
    return out


def held_contract(schedule: pd.DataFrame, sessions) -> pd.Series:
    """held(t): the contract held after the close of session t."""
    s = _as_sessions(sessions)
    rolls = schedule["roll"]
    finite = rolls.notna().values
    rv = rolls[finite].values
    j = np.searchsorted(rv, s.values, side="right")     # first roll strictly after t
    n_finite = int(finite.sum())
    if (j >= len(schedule)).any():
        raise ValueError("no contract in the calendar for the last sessions -- "
                         "the definition samples do not reach far enough")
    if n_finite and not finite[:n_finite].all():
        raise ValueError("a contract with no roll precedes one with a roll")
    return pd.Series(schedule["symbol"].values[j], index=s, name="held")


def held_series(prices: pd.DataFrame, held: pd.Series) -> pd.DataFrame:
    """The book's price arithmetic on the held sequence.

    `prices`: index = sessions, columns = contract symbols, close (NaN = no bar
    that session). A contract's price is carried forward over a session where
    it printed no bar, and the carry is COUNTED (`stale`), never hidden.

    Columns returned, per session t (h = held):
      held      h(t)
      raw       P_{h(t)}(t)               the price of what is held after the close
      dP        P_{h(t-1)}(t) - P_{h(t-1)}(t-1)   the held-contract P/L per unit
      base      P_{h(t-1)}(t-1)           the price dP is a change from
      ret       dP / base                 the held contract's daily return
      gap       P_{h(t)}(t) - P_{h(t-1)}(t) on a roll session, else 0
      rolled    True on a session where h changes
      cont      difference-back-adjusted continuous series:
                raw(t) + sum of gaps AFTER t, so the last segment is the raw
                price and cont.diff() == dP exactly
      stale     True where the held contract's price at t was carried forward
    """
    idx = held.index
    px = prices.reindex(idx)
    missing = [c for c in held.unique() if c not in px.columns]
    if missing:
        raise KeyError(f"held contracts with no price column: {missing}")
    filled = px.ffill()
    cols = {c: i for i, c in enumerate(filled.columns)}
    a = filled.to_numpy(dtype=float)
    raw_a = px.to_numpy(dtype=float)
    hi = np.array([cols[c] for c in held.values])
    n = len(idx)
    rows = np.arange(n)

    raw = a[rows, hi]
    stale = np.isnan(raw_a[rows, hi]) & ~np.isnan(raw)
    if np.isnan(raw).any():
        bad = idx[np.isnan(raw)][:5]
        raise ValueError(f"held contract has no price yet on {list(bad.date)} -- "
                         "it has not printed a bar by the session it is held")
    prev_h = np.r_[hi[0], hi[:-1]]
    p_prev_today = a[rows, prev_h]
    p_prev_yday = np.r_[np.nan, raw[:-1]]
    dP = p_prev_today - p_prev_yday
    rolled = np.r_[False, hi[1:] != hi[:-1]]
    gap = np.where(rolled, raw - p_prev_today, 0.0)
    after = np.r_[np.cumsum(gap[::-1])[::-1][1:], 0.0]     # sum of gaps strictly after t
    cont = raw + after
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = dP / p_prev_yday
    if (p_prev_yday[1:] <= 0).any():
        bad = idx[1:][p_prev_yday[1:] <= 0][:5]
        raise ValueError(f"held price <= 0 on {list(bad.date)}: a return is undefined")
    return pd.DataFrame({"held": held.values, "raw": raw, "dP": dP,
                         "base": p_prev_yday, "ret": ret, "gap": gap,
                         "rolled": rolled, "cont": cont, "stale": stale}, index=idx)


def roll_volume_share(volumes: pd.DataFrame, series: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic (amendment C): on each roll session, the held contract's share
    of the root's volume across the contracts on file. Selects nothing."""
    v = volumes.reindex(series.index).fillna(0.0)
    tot = v.sum(axis=1)
    rows = series.index[series["rolled"].values]
    out = []
    for t in rows:
        h = series.at[t, "held"]
        vh = float(v.at[t, h]) if h in v.columns else 0.0
        out.append({"session": t, "held": h, "held_volume": vh,
                    "root_volume": float(tot.at[t]),
                    "share": vh / float(tot.at[t]) if tot.at[t] > 0 else np.nan})
    return pd.DataFrame(out)
