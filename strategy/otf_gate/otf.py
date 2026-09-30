"""One-time-framing (OTF) state machine, REGISTERED_otf_gate.md sec 2.1 / 2.2.

State after the close of bar t in {UP, DOWN, BAL}; BAL carries a reference bar (its high/low).

    OTF-up(t)   = H[t] > H[t-1] and L[t] > L[t-1] and C[t] > H[t-1]        (Imre)
    OTF-down(t) = L[t] < L[t-1] and H[t] < H[t-1] and C[t] < L[t-1]
    UP   : OTF-up -> UP ; else OTF-down -> DOWN ; else -> BAL, ref = bar t
    DOWN : OTF-down -> DOWN ; else OTF-up -> UP ; else -> BAL, ref = bar t
    BAL  : C[t] > H[ref] -> UP ; C[t] < L[ref] -> DOWN ; else stay BAL, ref UNCHANGED
    initial state: BAL with ref = the first bar. Strict inequalities.

`rule="dalton"` is the reported variant (sec 2.5): OTF-up = L[t] > L[t-1] only, OTF-down = H[t] < H[t-1] only.
When both are true (an inside bar) the table above resolves it: UP stays UP, DOWN stays DOWN, BAL uses the ref.

A bar is "completed before tau" (the look-ahead rule, G4 a/b): its last session is before the entry session AND
it is not the week/month the entry session belongs to. Nothing here reads a bar at or after the entry session,
except the reported "live" variant, which reads only the sessions of the current week/month BEFORE the entry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.otf_gate.spec import BAL, DOWN, UNDEF, UP


def step(prev, ref_h, ref_l, ph, pl, h, l, c, rule="imre"):
    """One transition. Returns (state, ref_h, ref_l). ref is meaningful only while state == BAL."""
    if rule == "imre":
        up = (h > ph) and (l > pl) and (c > ph)
        dn = (l < pl) and (h < ph) and (c < pl)
    elif rule == "dalton":
        up = l > pl
        dn = h < ph
    else:
        raise ValueError(f"unknown OTF rule {rule!r}")
    if prev == UP:
        if up:
            return UP, np.nan, np.nan
        if dn:
            return DOWN, np.nan, np.nan
        return BAL, h, l
    if prev == DOWN:
        if dn:
            return DOWN, np.nan, np.nan
        if up:
            return UP, np.nan, np.nan
        return BAL, h, l
    if c > ref_h:                       # BAL: only the reference bar ends it
        return UP, np.nan, np.nan
    if c < ref_l:
        return DOWN, np.nan, np.nan
    return BAL, ref_h, ref_l


def run_states(high, low, close, rule="imre"):
    """State, ref high, ref low after every bar. Bar 0 is BAL with ref = bar 0."""
    h, l, c = (np.asarray(x, dtype=float) for x in (high, low, close))
    n = len(h)
    st = np.zeros(n, dtype=np.int8)
    rh = np.full(n, np.nan)
    rl = np.full(n, np.nan)
    if n == 0:
        return st, rh, rl
    s, a, b = BAL, h[0], l[0]
    st[0], rh[0], rl[0] = s, a, b
    for t in range(1, n):
        s, a, b = step(s, a, b, h[t - 1], l[t - 1], h[t], l[t], c[t], rule)
        st[t], rh[t], rl[t] = s, a, b
    return st, rh, rl


def iso_week_key(dates) -> np.ndarray:
    """ISO (year, week) as an int yyyyww for each session date."""
    iso = pd.DatetimeIndex(dates).isocalendar()
    return (iso["year"].to_numpy(dtype=np.int64) * 100 + iso["week"].to_numpy(dtype=np.int64))


def month_key(dates) -> np.ndarray:
    d = pd.DatetimeIndex(dates)
    return d.year.to_numpy(dtype=np.int64) * 100 + d.month.to_numpy(dtype=np.int64)


def aggregate(daily: pd.DataFrame, keys) -> pd.DataFrame:
    """Daily rows (date, open, high, low, close) -> one bar per run of equal `keys`
    (open = first open, high/low = extremes, close = last close)."""
    keys = np.asarray(keys)
    if len(keys) != len(daily):
        raise ValueError("keys must have one entry per daily row")
    if len(keys) == 0:
        return pd.DataFrame(columns=["key", "first_date", "last_date", "open", "high", "low", "close", "n"])
    new = np.r_[True, keys[1:] != keys[:-1]]
    gid = np.cumsum(new) - 1
    g = daily.assign(_g=gid).groupby("_g", sort=True)
    out = pd.DataFrame({
        "key": keys[new],
        "first_date": g["date"].first().to_numpy(),
        "last_date": g["date"].last().to_numpy(),
        "open": g["open"].first().to_numpy(),
        "high": g["high"].max().to_numpy(),
        "low": g["low"].min().to_numpy(),
        "close": g["close"].last().to_numpy(),
        "n": g["date"].size().to_numpy(),
    })
    if out["key"].duplicated().any():
        raise ValueError("bar keys are not monotone: a key re-appears after another key")
    return out


class Timeframe:
    """The bars of one timeframe, the OTF state after each, and 'as of the entry session' lookups."""

    def __init__(self, bars: pd.DataFrame, key_of, rule="imre"):
        self.bars, self.key_of, self.rule = bars.reset_index(drop=True), key_of, rule
        self.h, self.l, self.c = (self.bars[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
        self.last = pd.DatetimeIndex(self.bars["last_date"]).to_numpy("datetime64[ns]")
        self.keys = self.bars["key"].to_numpy()
        self.state, self.ref_h, self.ref_l = run_states(self.h, self.l, self.c, rule)
        self.run_id = self.state.astype(np.int64)

    def completed_index(self, session) -> int:
        """Index of the last bar completed before the entry session's open; -1 if none."""
        s = np.datetime64(pd.Timestamp(session), "ns")
        i = int(np.searchsorted(self.last, s, side="left")) - 1
        if i >= 0 and self.keys[i] == self.key_of(session):
            i -= 1                                  # the week/month of the entry session is still in progress
        return i

    def state_at(self, session) -> int:
        i = self.completed_index(session)
        return UNDEF if i < 0 else int(self.state[i])

    def naive_at(self, session) -> int:
        """C-N: sign of (close - previous close) on the last completed bar. 0 if it has no predecessor."""
        i = self.completed_index(session)
        if i < 0:
            return UNDEF
        if i == 0:
            return 0
        return int(np.sign(self.c[i] - self.c[i - 1]))


class Stack:
    """Daily / weekly / monthly OTF states for one host series (sec 2.2, sec 2.3)."""

    def __init__(self, daily: pd.DataFrame, rule="imre", week_key=iso_week_key, month_key_fn=month_key):
        d = daily[["date", "open", "high", "low", "close"]].copy()
        d["date"] = pd.to_datetime(d["date"])
        d = d.sort_values("date").reset_index(drop=True)
        if d["date"].duplicated().any():
            raise ValueError("duplicate daily dates")
        self.daily, self.rule = d, rule
        self._wk = lambda s: int(week_key([s])[0])
        self._mk = lambda s: int(month_key_fn([s])[0])
        self._week_key, self._month_key = week_key, month_key_fn
        dd = d.assign(key=d["date"]).assign(first_date=d["date"], last_date=d["date"], n=1)
        self.D = Timeframe(dd[["key", "first_date", "last_date", "open", "high", "low", "close", "n"]],
                           key_of=lambda s: np.datetime64(pd.Timestamp(s), "ns"), rule=rule)
        self.W = Timeframe(aggregate(d, week_key(d["date"])), self._wk, rule)
        self.M = Timeframe(aggregate(d, month_key_fn(d["date"])), self._mk, rule)
        # cumulative partial-bar OHLC inside the current week / month, for the reported "live" variant
        self._cum = {}
        for name, keys in (("W", week_key(d["date"])), ("M", month_key_fn(d["date"]))):
            new = np.r_[True, keys[1:] != keys[:-1]]
            gid = np.cumsum(new) - 1
            ch = d.groupby(gid)["high"].cummax().to_numpy()
            cl = d.groupby(gid)["low"].cummin().to_numpy()
            self._cum[name] = (keys, ch, cl)

    def states_at(self, sessions, live=False) -> pd.DataFrame:
        """Columns d, w, m (state codes) and nd, nw, nm (naive signs) for each entry session date."""
        rows = []
        dates = self.daily["date"].to_numpy("datetime64[ns]")
        close = self.daily["close"].to_numpy(dtype=float)
        for s in pd.DatetimeIndex(sessions):
            r = {"d": self.D.state_at(s), "w": self.W.state_at(s), "m": self.M.state_at(s),
                 "nd": self.D.naive_at(s), "nw": self.W.naive_at(s), "nm": self.M.naive_at(s)}
            if live:
                p = int(np.searchsorted(dates, np.datetime64(s, "ns"), side="left")) - 1   # last daily row < s
                for name, tf, ks in (("w", self.W, self._wk), ("m", self.M, self._mk)):
                    keys, ch, cl = self._cum["W" if name == "w" else "M"]
                    if p >= 0 and keys[p] == ks(s):                      # part of the current week/month is done
                        i = tf.completed_index(s)
                        if i < 0:
                            r[name] = BAL_LIVE_FIRST
                        else:
                            st, _, _ = step(tf.state[i], tf.ref_h[i], tf.ref_l[i], tf.h[i], tf.l[i],
                                            ch[p], cl[p], close[p], self.rule)
                            r[name] = int(st)
            rows.append(r)
        return pd.DataFrame(rows, index=pd.DatetimeIndex(sessions), columns=["d", "w", "m", "nd", "nw", "nm"])


BAL_LIVE_FIRST = 0     # a live partial bar with no completed predecessor: still the initial BAL
