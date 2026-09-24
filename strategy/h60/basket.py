#!/usr/bin/env python3
"""The market control: an equal-weight basket of every eligible name, as an
index over the panel's marks. W14-0003, REGISTERED_h60_v0.md §2.5, §4.2.

    market-relative $ = trade $ - notional x (I[exit mark] / I[entry mark] - 1)

WHY AN INDEX, AND WHAT IT APPROXIMATES
-------------------------------------
§2.5 asks what the trade's notional "in an equal-weight basket of every
eligible name would have made from the same entry bar's open to the same exit
time". Asked literally per trade that is a mean over ~900 names for each of
hundreds of thousands of trades (and a thousand random draws of them). The
index rebalances to equal weight at every mark instead: I[m] = I[m-1] x
(1 + mean over eligible names of their return from the previous mark to m).
Over a hold of at most six sessions the difference from buy-and-hold equal
weight is second order (the drift between rebalances), and the positive
control (§4.3) is run through exactly this subtraction, so a construction
that biased it would fail there.

A STEP IS COUNTED ONLY BETWEEN ADJACENT MARKS
---------------------------------------------
A name contributes a return to mark m only if it also has the mark just
before m in the market's sequence -- open->close inside a bar, close->next
bar's open between bars and overnight. A name missing a bar contributes
nothing across the gap rather than a lump. Steps across a split date (§5.1)
and into a bad symbol-day are dropped: a 2-for-1 split read as -50% would
move a 900-name basket by 5.5 bps in one step.
"""
from __future__ import annotations

import numpy as np

from strategy.h60.panel import Panel


class Basket:
    def __init__(self, marks: np.ndarray, level: np.ndarray, n_names: np.ndarray):
        self.marks = marks            # sorted mark ids that exist
        self.level = level            # index level AT each mark
        self.n_names = n_names        # names contributing the step INTO it

    def at(self, mark) -> np.ndarray:
        mk = np.asarray(mark)
        pos = np.searchsorted(self.marks, mk)
        pos = np.clip(pos, 0, len(self.marks) - 1)
        if not np.array_equal(self.marks[pos], mk):
            raise KeyError("a trade mark is not a market mark")
        return self.level[pos]

    def ret(self, entry_mark, exit_mark) -> np.ndarray:
        return self.at(exit_mark) / self.at(entry_mark) - 1.0


def build(panel: Panel, *, excluded_days: set | None = None,
          split_days: set | None = None) -> Basket:
    """excluded_days / split_days: {(symbol, session_index)}. A split day
    drops the overnight step INTO that session. An excluded day drops every
    step that STARTS or ENDS on one of its marks -- the step into it, the
    steps inside it and the overnight step out of it, which starts from the
    bad close (the first draft kept that one; the W14-0003 review measured
    -2.31% on a ten-name basket from one day 30% wrong)."""
    excluded_days = excluded_days or set()
    split_days = split_days or set()
    all_marks = []
    per_sym = []
    for sym in panel.symbols:
        a = panel.arrays(sym)
        mk = np.empty(2 * a.n, dtype=np.int64)
        mk[0::2] = 2 * a.g
        mk[1::2] = 2 * a.g + 1
        px = np.empty(2 * a.n)
        px[0::2] = a.o
        px[1::2] = a.c
        ses = np.repeat(a.s, 2)
        elig = np.repeat(a.eligible, 2)
        overnight = np.zeros(2 * a.n, bool)
        overnight[0::2] = np.r_[True, a.s[1:] != a.s[:-1]]
        # a step INTO the first bar of a segment is never counted: a gap
        # already fails adjacency, and a ticker reused on consecutive
        # sessions (two companies, one symbol) must not either
        seg_start = np.zeros(2 * a.n, bool)
        for st, _ in panel.segment_bounds(sym):
            seg_start[2 * st] = True
        all_marks.append(mk)
        per_sym.append((sym, mk, px, ses, elig, overnight, seg_start))
    marks = np.unique(np.concatenate(all_marks)) if all_marks else np.zeros(0, np.int64)
    ex_by = _by_symbol(excluded_days)
    sp_by = _by_symbol(split_days)
    tot = np.zeros(len(marks))
    cnt = np.zeros(len(marks))
    for sym, mk, px, ses, elig, overnight, seg_start in per_sym:
        rk = np.searchsorted(marks, mk)
        adj = np.r_[False, rk[1:] == rk[:-1] + 1]
        r = np.r_[np.nan, px[1:] / px[:-1] - 1.0]
        ok = adj & elig & np.isfinite(r) & ~seg_start
        if sym in ex_by:
            bad = np.isin(ses, ex_by[sym])
            ok &= ~bad & ~np.r_[False, bad[:-1]]
        if sym in sp_by:
            ok &= ~(np.isin(ses, sp_by[sym]) & overnight)
        idx = rk[ok]
        tot += np.bincount(idx, weights=r[ok], minlength=len(marks))
        cnt += np.bincount(idx, minlength=len(marks))
    step = np.divide(tot, cnt, out=np.zeros_like(tot), where=cnt > 0)
    level = np.cumprod(1.0 + step)
    return Basket(marks, level, cnt.astype(np.int64))


def _by_symbol(days) -> dict:
    out: dict = {}
    for sym, s in (days or ()):
        out.setdefault(sym, []).append(int(s))
    return {k: np.array(sorted(v)) for k, v in out.items()}
