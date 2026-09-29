"""Synthetic single-market frames for the W15-0022 tests. No archive is read."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.futbt.core import Frame


def frame_from_close(close, *, spread=0.2, mult=1.0, tick_usd=0.01, start="2012-01-02", vol=None,
                     roll_at=(), opens=None, highs=None, lows=None) -> Frame:
    """Bars around a close path: open = previous close (or `opens`), high/low = +/- spread
    around max/min(open, close) unless given."""
    c = np.asarray(close, float)
    n = len(c)
    o = np.r_[c[0], c[:-1]] if opens is None else np.asarray(opens, float)
    h = np.maximum(o, c) + spread if highs is None else np.asarray(highs, float)
    l = np.minimum(o, c) - spread if lows is None else np.asarray(lows, float)
    ra = np.zeros(n, bool)
    for r in roll_at:
        ra[r] = True
    v = np.full(n, 1000.0) if vol is None else np.asarray(vol, float)
    return Frame("SYN", o, h, l, c, v, c.copy(), ra, pd.bdate_range(start, periods=n),
                 mult, tick_usd)


def squeeze_breakout_path(seed=3, warm=300, quiet=40, ramp=14, plateau=6, up=True, tail=40):
    """noisy warm-up -> quiet squeeze -> steady ramp (T) -> flat plateau -> drift back (MR)."""
    rng = np.random.default_rng(seed)
    x = 100 + np.cumsum(rng.normal(0, 1.5, warm))
    x = np.r_[x, x[-1] + np.cumsum(rng.normal(0, 0.03, quiet))]
    step = 0.6 if up else -0.6
    x = np.r_[x, x[-1] + step * np.arange(1, ramp + 1)]
    x = np.r_[x, x[-1] + np.cumsum(rng.normal(0, 0.03, plateau))]
    back = -0.35 if up else 0.35
    x = np.r_[x, x[-1] + back * np.arange(1, tail + 1)]
    return x
