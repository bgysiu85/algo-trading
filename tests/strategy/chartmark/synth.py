import numpy as np
import pandas as pd

from strategy.chartmark.data import make_frame


def walk(n=3000, seed=1, drift=0.0, vol=0.15, start="2015-01-05 00:00", roll_every=None):
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, periods=n, freq="h", tz="UTC")
    ret = rng.normal(drift, vol, n)
    c = 60 + np.cumsum(ret)
    o = np.concatenate([[60.0], c[:-1]]) + rng.normal(0, 0.02, n)
    hi = np.maximum(o, c) + np.abs(rng.normal(0, vol / 2, n))
    lo = np.minimum(o, c) - np.abs(rng.normal(0, vol / 2, n))
    v = rng.integers(500, 3000, n).astype(float)
    ra = np.zeros(n, bool)
    if roll_every:
        ra[roll_every::roll_every] = True
    return make_frame(t, o, hi, lo, c, v, ra, "synthetic")


def cut(fr, k):
    return make_frame(fr.t[:k], fr.o[:k], fr.h[:k], fr.l[:k], fr.c[:k], fr.v[:k], fr.roll_after[:k], "cut")
