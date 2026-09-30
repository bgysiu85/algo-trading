"""Hand-built and random sessions for the VA80 tests."""
import numpy as np
import pandas as pd

from strategy.va80.engine import Sess

ET = "America/New_York"


def path_sess(date="2019-03-05", knots=((570, 100.0), (959, 100.0)), overrides=None, inst=1, close_min=960, vol=10.0):
    """A full RTH session (one bar per minute 09:30..close-1). Close of bar m = linear interpolation of `knots`
    (minute, price); open = previous close (bar 0 opens at f(570)); high/low = max/min(open, close) unless overridden:
    overrides = {minute: (o, h, l, c)}."""
    minute = np.arange(570, close_min)
    xs, ys = zip(*knots)
    c = np.interp(minute, xs, ys)
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c), np.minimum(o, c)
    o, h, l, c = o.copy(), h.copy(), l.copy(), c.copy()
    for m, (oo, hh, ll, cc) in (overrides or {}).items():
        i = m - 570
        o[i], h[i], l[i], c[i] = oo, hh, ll, cc
        if i + 1 < len(o) and (i + 1) not in {mm - 570 for mm in (overrides or {})}:
            o[i + 1] = cc
            h[i + 1], l[i + 1] = max(o[i + 1], c[i + 1], h[i + 1]), min(o[i + 1], c[i + 1], l[i + 1])
    return Sess(date, minute.astype(np.int64), o, h, l, c, np.full(len(minute), vol), frozenset({inst}), close_min)


def rth_frames(dates, seed=0, gap_sd=6.0, vol=0.6):
    """{date: tz-aware RTH frame} with an overnight gap between consecutive days (a random walk of daily bases)."""
    rng = np.random.default_rng(seed)
    base, out = 4000.0, {}
    for d in dates:
        base += rng.normal(0, gap_sd)
        naive = pd.date_range(f"{d} 09:30", f"{d} 15:59", freq="min")
        utc = naive.tz_localize(ET).tz_convert("UTC")
        close = base + np.cumsum(rng.normal(0, vol, len(utc)))
        close = np.round(close * 4) / 4
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + np.round(rng.uniform(0, 0.5, len(utc)) * 4) / 4
        low = np.minimum(open_, close) - np.round(rng.uniform(0, 0.5, len(utc)) * 4) / 4
        out[d] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                               "volume": rng.integers(1, 60, len(utc)).astype(float), "held_id": 1}, index=utc)
        base = close[-1]
    return out


def xnys_days(first, n):
    from strategy.w16.sessions import session_date_range
    y = int(first[:4])
    ds = [d for d in session_date_range(y, y + 1) if d >= first]
    return ds[:n]


def one_min_frame(frames: dict) -> pd.DataFrame:
    return pd.concat([frames[d] for d in sorted(frames)]).sort_index()
