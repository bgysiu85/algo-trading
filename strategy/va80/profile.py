"""Prior-session volume profile, POC and value area (REGISTERED_va80.md sec 2.1).

Each 1-minute bar's volume is spread EVENLY over every tick from its low to its high inclusive (tick 0.25).
POC = the tick with the most volume; ties -> the tied tick closest to the prior session's 16:00 close, still tied
-> the lower one. The value area starts at the POC and repeatedly compares the volume of the next tick above the
area with the next tick below it, adding the larger (tie -> the one above), and stops as soon as it holds at least
`share` of the session's volume. VAH / VAL = the area's top and bottom ticks.

Tick volumes are rounded to 1e-9 before any comparison so that two ticks that are equal on paper are equal in
floating point (the registration's tie rules depend on it). Prices are on-tick in the real data; off-tick test
prices are rounded to the nearest tick.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from strategy.va80.spec import TICK, VA_SHARE

EPS = 1e-9


@dataclass(frozen=True)
class Profile:
    t0: int                # tick index of vol[0]  (price = tick_index * TICK)
    vol: np.ndarray        # volume per tick, rounded
    poc: int               # tick index of the POC
    total: float
    last_close: float

    def price(self, tick_index: int) -> float:
        return tick_index * TICK


def build_profile(high, low, volume, last_close: float) -> Profile:
    """Volume profile of one session's bars (arrays of equal length)."""
    h = np.rint(np.asarray(high, dtype=float) / TICK).astype(np.int64)
    l = np.rint(np.asarray(low, dtype=float) / TICK).astype(np.int64)
    v = np.asarray(volume, dtype=float)
    if len(h) == 0:
        raise ValueError("empty session")
    t0 = int(l.min())
    prof = np.zeros(int(h.max()) - t0 + 1)
    for hi, lo, vol in zip(h, l, v):
        n = int(hi - lo + 1)
        prof[int(lo) - t0:int(hi) - t0 + 1] += vol / n
    prof = np.round(prof, 9)
    top = prof.max()
    tied = np.flatnonzero(prof == top)
    if len(tied) == 1:
        poc = int(tied[0])
    else:
        dist = np.abs((t0 + tied) * TICK - last_close)
        best = tied[dist == dist.min()]
        poc = int(best.min())                     # still tied -> the lower one
    return Profile(t0, prof, t0 + poc, float(prof.sum()), float(last_close))


def value_area(p: Profile, share: float = VA_SHARE) -> tuple[float, float]:
    """(VAL, VAH) prices for the given share of the session's volume."""
    vol, n = p.vol, len(p.vol)
    lo = hi = p.poc - p.t0
    acc = float(vol[lo])
    need = share * p.total - EPS * max(p.total, 1.0)
    while acc < need:
        up = vol[hi + 1] if hi + 1 < n else None
        dn = vol[lo - 1] if lo - 1 >= 0 else None
        if up is None and dn is None:
            break
        if dn is None or (up is not None and up >= dn):          # tie -> the tick above
            hi += 1
            acc += float(up)
        else:
            lo -= 1
            acc += float(dn)
    return (p.t0 + lo) * TICK, (p.t0 + hi) * TICK
