"""VA80 controls (REGISTERED_va80.md sec 3): C-RT random time (scored) and C-ND no-setup days (reported).
Seeded: np.random.default_rng([crc32(str(draw)), crc32(date), 80]); 1,000 draws. No clock.

C-RT  on each VA80 trade's session, same side, entry at the open of a random 1-min bar starting 10:00-15:00 at
      which the PRIOR bar closed inside the value area and the far edge has not yet been reached; same target
      (the far edge) and stop rule (1 tick past the day's extreme up to that entry) and 16:00 flat.
C-ND  sessions that opened INSIDE the value area; random side (the first draw of the generator), then a random bar
      as above for that side; target = the edge on that side, stop = 1 tick past the day's extreme on the other side
      so far.

A draw returns gross POINTS and exit-kind counts, not dollars: costs (IBKR, W15-0033) are applied by the study, which
knows target fills pay no tick add-on (sec 2.4). Nothing here is P&L.
"""
from __future__ import annotations

import zlib

import numpy as np

from strategy.va80 import spec as S
from strategy.va80.engine import Sess, walk_exit


def _rng(draw: int, date: str, tag: int = S.CR_SEED_TAG):
    return np.random.default_rng([zlib.crc32(str(draw).encode()), zlib.crc32(date.encode()), tag])


def candidates(s: Sess, side: int, val: float, vah: float) -> np.ndarray:
    """Bar indices i where a random-time entry is allowed: start 10:00-15:00, bar i-1 closed inside [VAL, VAH], and the
    far edge (the target for `side`) has not traded at or through in bars [:i]."""
    if s.n < 2:
        return np.array([], dtype=int)
    prior_in = (s.c[:-1] >= val) & (s.c[:-1] <= vah)
    reached = (np.minimum.accumulate(s.l)[:-1] <= val) if side == S.SHORT else (np.maximum.accumulate(s.h)[:-1] >= vah)
    m = s.minute[1:]
    ok = prior_in & ~reached & (m >= S.RANDOM_FROM_MIN) & (m <= S.RANDOM_TO_MIN)
    return np.flatnonzero(ok) + 1


def levels(s: Sess, i: int, side: int, val: float, vah: float) -> tuple[float, float]:
    """(target, stop) for an entry at bar i using bars strictly before i."""
    if side == S.SHORT:
        return val, float(s.h[:i].max() + S.TICK)
    return vah, float(s.l[:i].min() - S.TICK)


def edge_outcome(s: Sess, i: int, side: int, edge: float, stop: float) -> str:
    """'edge' | 'stop' | 'neither': does price TRADE AT the far edge (touch) before it hits the stop level, from bar i
    on? Stop wins a same-bar tie. (The 80% check of sec 3.)"""
    h, l = s.h[i:], s.l[i:]
    he = (l <= edge) if side == S.SHORT else (h >= edge)
    hs = (h >= stop) if side == S.SHORT else (l <= stop)
    big = len(h) + 1
    ie = int(np.argmax(he)) if he.any() else big
    is_ = int(np.argmax(hs)) if hs.any() else big
    if ie == big and is_ == big:
        return "neither"
    return "stop" if is_ <= ie else "edge"


class _Memo:
    def __init__(self):
        self.d = {}

    def get(self, s: Sess, i: int, side: int, val: float, vah: float):
        key = (s.date, i, side)
        if key not in self.d:
            tgt, stp = levels(s, i, side, val, vah)
            k, px, why = walk_exit(s, i, side, tgt, stp)
            self.d[key] = (side * (px - float(s.o[i])), why, edge_outcome(s, i, side, tgt, stp))
        return self.d[key]


def _empty(draws):
    return {k: np.zeros(draws) for k in ("n", "gross_pts", "n_target", "n_other", "n_edge", "n_stop", "n_neither", "unused")}


def run_crt(store, trades: list[dict], draws: int = S.CR_DRAWS) -> dict:
    """`trades`: dicts with date, side, val, vah (the VA80 trade sessions). Returns arrays of length `draws`."""
    out, memo = _empty(draws), _Memo()
    sess = {t["date"]: store.sess(t["date"]) for t in trades}
    cands = {t["date"]: candidates(sess[t["date"]], t["side"], t["val"], t["vah"]) for t in trades}
    for d in range(draws):
        for t in trades:
            c = cands[t["date"]]
            if not len(c):
                out["unused"][d] += 1
                continue
            i = int(c[_rng(d, t["date"]).integers(len(c))])
            g, why, edge = memo.get(sess[t["date"]], i, t["side"], t["val"], t["vah"])
            _add(out, d, g, why, edge)
    return out


def run_cnd(store, sessions: list[dict], draws: int = S.CR_DRAWS) -> dict:
    """`sessions`: dicts with date, val, vah for the sessions that opened inside the value area."""
    out, memo = _empty(draws), _Memo()
    sess = {t["date"]: store.sess(t["date"]) for t in sessions}
    cands = {(t["date"], sd): candidates(sess[t["date"]], sd, t["val"], t["vah"]) for t in sessions for sd in (S.LONG, S.SHORT)}
    for d in range(draws):
        for t in sessions:
            rng = _rng(d, t["date"])
            side = S.LONG if int(rng.integers(2)) == 1 else S.SHORT
            c = cands[(t["date"], side)]
            if not len(c):
                out["unused"][d] += 1
                continue
            i = int(c[rng.integers(len(c))])
            g, why, edge = memo.get(sess[t["date"]], i, side, t["val"], t["vah"])
            _add(out, d, g, why, edge)
    return out


def _add(out, d, g, why, edge):
    out["n"][d] += 1
    out["gross_pts"][d] += g
    out["n_target" if why == S.TARGET else "n_other"][d] += 1
    out[{"edge": "n_edge", "stop": "n_stop", "neither": "n_neither"}[edge]][d] += 1


def percentile_of(value: float, draws: np.ndarray) -> float:
    draws = np.asarray(draws)
    return float(100.0 * ((draws < value).mean() + 0.5 * (draws == value).mean()))


def summary(draws: np.ndarray) -> dict:
    return {f"p{q}": float(np.percentile(draws, q)) for q in (5, 50, 95, 99)}
