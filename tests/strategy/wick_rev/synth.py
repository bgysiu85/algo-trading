"""Synthetic bars for the WICK-REV tests (no archive)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.wick_rev import signals as G


def series(o, h, l, c, *, market="MNQ", tf="1H", start="2020-01-06", minutes=60, held=None, short=None,
           fine=None):
    """Series from raw arrays; bars spaced `minutes` apart, one 'session' per calendar day-block of 20 bars."""
    n = len(c)
    t0 = pd.Timestamp(start, tz="UTC")
    t_open = (t0 + pd.to_timedelta(np.arange(n) * minutes, unit="m")).asi8
    t_end = t_open + minutes * 60 * 10**9
    sess = (np.datetime64(start, "D") + (np.arange(n) // 20)).astype("datetime64[D]")
    s = G.Series(market, tf, t_open, t_end, sess, np.asarray(o, float), np.asarray(h, float),
                 np.asarray(l, float), np.asarray(c, float),
                 np.zeros(n, int) if held is None else np.asarray(held),
                 np.zeros(n, bool) if short is None else np.asarray(short))
    if fine is not None:
        s.fine_t, s.fine_h, s.fine_l = fine
    return s


def random_walk(n=3000, seed=1, step=1.0, market="MNQ", tf="1H", **kw):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, step, n))
    open_ = np.concatenate([[100.0], close[:-1]]) + rng.normal(0, step * 0.1, n)
    up = np.abs(rng.normal(0, step * 0.8, n))
    dn = np.abs(rng.normal(0, step * 0.8, n))
    high = np.maximum(open_, close) + up
    low = np.minimum(open_, close) - dn
    return series(open_, high, low, close, market=market, tf=tf, **kw)


def raw_bars(index, o, h, l, c, v=None, held=1):
    """A tz-aware source frame for bars.build_bars."""
    n = len(index)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": np.ones(n) if v is None else v,
                         "held_id": np.full(n, held) if np.isscalar(held) else held}, index=index)


def flat(n=60, hi=101.0, lo=99.0, px=100.0, **kw):
    """Constant bars (TR = 2, so ATR = 2 exactly); tests then overwrite specific bars."""
    o = np.full(n, px); h = np.full(n, hi); l = np.full(n, lo); c = np.full(n, px)
    return o, h, l, c


def prefix(s: G.Series, m: int) -> G.Series:
    """The first m bars of a Series."""
    kw = {k: getattr(s, k)[:m] for k in ("t_open", "t_end", "session", "o", "h", "l", "c", "held", "short")}
    return G.Series(s.market, s.tf, **kw, fine_t=s.fine_t, fine_h=s.fine_h, fine_l=s.fine_l)


def minute_fine(s: G.Series, j: int, hs, ls):
    """Fine bars filling bar j, one per minute; hs / ls are the per-minute highs / lows."""
    t = s.t_open[j] + np.arange(len(hs)) * 60 * 10**9
    return t, np.asarray(hs, float), np.asarray(ls, float)
