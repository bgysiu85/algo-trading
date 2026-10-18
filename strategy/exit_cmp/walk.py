#!/usr/bin/env python3
"""EXIT-CMP sec 5: the simulated broker. One trade is walked bar by bar against a rule set's components.
W15-0053 sub 2. The rules themselves are exitmgr.rules (the code the live manager imports); this module only decides what the
orders would have done inside a 1H bar.

Fills (sec 5): a sell-stop at or above the bar's open fills at the open, otherwise at the level (v1 I4). Within a bar every
sell-stop is tested BEFORE anything that bar's high would raise (conservative order, G5). A market exit decided at the close of
bar j fills at the open of j+1 (before that bar's stops are looked at: the same price). FLAT: if still open, exit at the close of the
session's last bar (hour 16 NY, or the last bar before a gap on an early close). HOLD: carried, with an optional time cap."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from exitmgr import lines as LN
from exitmgr import rules as R
from strategy.chartmark.data import Frame, Ind
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.entries import Entry

TICK = 0.01


@dataclass
class Exit:
    exit_j: int
    exit_px: float
    reason: str
    mfe_px: float                      # highest high from the entry bar up to (not including) the exit bar's unknown path
    fired: frozenset = frozenset()
    stop_and_raise_same_bar: int = 0     # G5: the exit bar's high would also have raised a ratchet / trail; the stop was counted first


def session_end(fr: Frame, ind: Ind) -> tuple[np.ndarray, int]:
    """True on the last bar of a session: opens at hour 16 NY, or an early close (a bar opening 13..15 followed by a gap)."""
    n = fr.n
    hr = ind.hour
    t = fr.t.to_numpy()                      # datetime64 in whatever unit pandas holds (ns on 2.x, us/s possible on 3.x)
    gap = np.zeros(n, bool)
    gap[:-1] = (t[1:] - t[:-1]) > np.timedelta64(1, "h")
    early = gap & (hr >= 13) & (hr < S.FLAT_HOUR)
    return (hr == S.FLAT_HOUR) | early, int(early.sum())


def walk(b, e: int, entry: float, a0: float, s0: float, comps: list, *, scenario: str, sess_end: np.ndarray,
         cap: int | None, n: int) -> Exit:
    o, h, l, c = b.o, b.h, b.l, b.c
    for comp in comps:
        comp.start()
    hh = h[e]
    pend = None
    both = 0

    def done(j, px, why, mfe):
        fired = set()
        for comp in comps:
            fired |= comp.fired
        return Exit(j, float(px), why, float(mfe), frozenset(fired), both)

    for j in range(e + 1, n):
        if pend:
            return done(j, o[j], pend, hh)
        best = None
        for comp in comps:
            for lv in comp.levels(j):
                if best is None or (lv[0], -lv[1]) > (best[0], -best[1]):
                    best = lv
        if best is not None:
            lvl, _, tag = best
            if o[j] <= lvl:
                both = int(h[j] > hh)
                return done(j, o[j], tag, hh)
            if l[j] <= lvl:
                both = int(h[j] > hh)
                return done(j, lvl, tag, hh)
        hh = max(hh, h[j])
        fired = None
        for comp in comps:
            t = comp.on_close(j)
            if t and fired is None:
                fired = t
        if scenario == "FLAT" and sess_end[j]:
            return done(j, c[j], "flat", hh)
        if cap is not None and j == e + cap:
            return done(j, c[j], "time_cap", hh)
        if fired:
            pend = fired
    return done(n - 1, c[n - 1], "data_end", hh)


class Study:
    """The frame, its indicators and the entry set, with the walks cached per (rule, scenario, params)."""

    def __init__(self, fr: Frame, ind: Ind, entries: list[Entry], tick: float = TICK):
        self.fr, self.ind, self.entries, self.tick = fr, ind, entries, tick
        self.n = fr.n
        self.sess_end, self.early_closes = session_end(fr, ind)
        self.roll_cum = np.concatenate([[0], np.cumsum(fr.roll_after.astype(int))])      # rolls in [e, x) = cum[x]-cum[e]
        self._proj: dict = {}
        self._cache: dict = {}
        self.b = fr
        for name in ("atr", "e9", "e21", "hist"):                                         # one namespace for the components
            setattr(fr, name, getattr(ind, name))

    def proj(self, L: int, buf: float) -> np.ndarray:
        k = (L, buf)
        if k not in self._proj:
            self._proj[k] = LN.track(self.fr.l, self.fr.c, self.ind.atr, L, buf)[2]
        return self._proj[k]

    def run(self, rule_id: str, scenario: str, p: R.Params = R.BASE, *, cap: int | None | str = "default") -> list[Exit]:
        if cap == "default":
            cap = S.HOLD_CAP if scenario == "HOLD" else None
        key = (rule_id, scenario, p, cap)
        if key in self._cache:
            return self._cache[key]
        proj = self.proj(p.al_L, p.al_buf) if rule_id.startswith("X-ALERT") else None
        out = []
        for x in self.entries:
            comps = R.build(rule_id, self.b, x.e, x.entry_px, x.a0, x.s0, self.tick, p, proj)
            out.append(walk(self.b, x.e, x.entry_px, x.a0, x.s0, comps, scenario=scenario, sess_end=self.sess_end,
                            cap=cap, n=self.n))
        self._cache[key] = out
        return out
