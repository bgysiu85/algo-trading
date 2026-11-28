"""Made-up 1-minute bars for the OWA-v0 tests (board W16-0040). No market
data: seeded random walks and flat days with hand-placed moves."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.w16 import open_window as OW

TICK = 0.25
FLAT = 1000.0
ATR = 4.0


def weekdays(n: int, start: str = "2015-03-09") -> list[str]:
    """`n` XNYS trading days from `start`, ascending."""
    out, d = [], pd.Timestamp(start)
    while len(out) < n:
        s = d.strftime("%Y-%m-%d")
        number = OW.day_number(s)
        if OW.trading_calendar(number, number):
            out.append(s)
        d += pd.Timedelta(days=1)
    return out


def day_index(date: str) -> pd.DatetimeIndex:
    """Globex-like minutes of one New York date: 00:00-16:59 and 18:00-23:59."""
    a = pd.date_range(f"{date} 00:00", f"{date} 16:59", freq="1min", tz=OW.ET)
    b = pd.date_range(f"{date} 18:00", f"{date} 23:59", freq="1min", tz=OW.ET)
    return a.append(b).tz_convert("UTC")


def flat_bars(dates: list[str], price: float = FLAT) -> pd.DataFrame:
    idx = day_index(dates[0])
    for d in dates[1:]:
        idx = idx.append(day_index(d))
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price,
                         "volume": 1, "held_id": 1}, index=idx)


def stamp(date: str, clock: str) -> pd.Timestamp:
    return pd.Timestamp(f"{date} {clock}", tz=OW.ET).tz_convert("UTC")


def set_minute(df: pd.DataFrame, date: str, clock: str, *, o=None, h=None, l=None, c=None):
    ts = stamp(date, clock)
    assert ts in df.index, ts
    for col, v in (("open", o), ("high", h), ("low", l), ("close", c)):
        if v is not None:
            df.loc[ts, col] = v


def set_from(df: pd.DataFrame, date: str, clock: str, price: float, until: str = "16:59"):
    """Flat at `price` from `clock` to `until` on `date`."""
    sel = (df.index >= stamp(date, clock)) & (df.index <= stamp(date, until))
    df.loc[sel, ["open", "high", "low", "close"]] = price


def random_bars(dates: list[str], seed: int = 7) -> pd.DataFrame:
    """A seeded random walk with drifting regimes (so the EMAs cross) and short
    bursts in the New York morning (so there are big bars)."""
    rng = np.random.default_rng(seed)
    idx = day_index(dates[0])
    for d in dates[1:]:
        idx = idx.append(day_index(d))
    n = len(idx)
    local = idx.tz_convert(OW.ET)
    minute = np.asarray(local.hour * 60 + local.minute)
    drift = np.repeat(rng.normal(0.0, 0.35, n // 90 + 1), 90)[:n]
    scale = np.ones(n)
    morning = np.flatnonzero((minute >= 8 * 60) & (minute < 12 * 60) & (minute % 5 == 0))
    for start in rng.choice(morning, size=max(1, len(morning) // 9), replace=False):
        push = rng.choice([-1.0, 1.0])
        scale[start:start + 5] = 5.0
        drift[start:start + 5] += push * 3.0
    step = np.round((drift + rng.normal(0.0, 1.0, n) * scale) / TICK) * TICK
    close = 5000.0 + np.cumsum(step)
    open_ = np.concatenate(([5000.0], close[:-1]))
    up = np.round(np.abs(rng.normal(0.0, 0.6, n)) * scale / TICK) * TICK
    down = np.round(np.abs(rng.normal(0.0, 0.6, n)) * scale / TICK) * TICK
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + up,
                         "low": np.minimum(open_, close) - down, "close": close,
                         "volume": 1, "held_id": 1}, index=idx)


def flat_market(n_days: int = 30, edits=None, start: str = "2015-03-09"):
    """(market, test date): flat days, the last one editable through
    `edits(df, date)`. ATR is pinned to 4.0 so stops are predictable."""
    dates = weekdays(n_days, start)
    df = flat_bars(dates)
    date = dates[-1]
    if edits:
        edits(df, date)
    mk = OW.prepare(df)
    mk.atr = np.full(len(mk.b5), ATR)
    return mk, date


def day_of(mk, date: str):
    return next(d for d in mk.days if d.date == date)


def bar_at(mk, date: str, clock: str) -> int:
    day = OW.day_number(date)
    h, m = (int(x) for x in clock.split(":"))
    hit = np.flatnonzero((mk.b5.day == day) & (mk.b5.minute == h * 60 + m))
    assert len(hit) == 1, (date, clock)
    return int(hit[0])


def minute_at(mk, date: str, clock: str) -> int:
    day = OW.day_number(date)
    h, m = (int(x) for x in clock.split(":"))
    hit = np.flatnonzero((mk.m1.day == day) & (mk.m1.minute == h * 60 + m))
    assert len(hit) == 1, (date, clock)
    return int(hit[0])


def forced_signals(mk, *, a_long=(), a_short=()) -> OW.Signals:
    """A Signals object that fires only where told to."""
    n = len(mk.b5)

    def at(idx):
        out = np.zeros(n, dtype=bool)
        for i in idx:
            out[i] = True
        return out

    none = np.zeros(n, dtype=bool)
    return OW.Signals(big=none, big_up=none, big_dn=none, a_long=at(a_long),
                      a_short=at(a_short), c_long=none, c_short=none, b_arm_long=none,
                      b_arm_short=none, b_touch_long=none, b_touch_short=none,
                      b_fire_long=none, b_fire_short=none)
