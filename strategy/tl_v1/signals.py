#!/usr/bin/env python3
"""TL-v1 signal arrays: her extreme-anchor line (sec 2.2) + the A+ checklist (sec 2.3),
turned into the arrays strategy.tl_v0.sim.simulate reads. Board: W15-0020.

Everything except the ENTRY SIDE is TL-v0-rev's, word for word (REGISTERED_tl_v1.md
sec 2.1): the weekly filter, the v0-rev safety line, the reversal, sizing, costs, fills.
So this module only builds two things per (market, pivot size R):

  raw_up / raw_dn     the sec 2.2 line breaks (close beyond the line by > 0.10 x ATR).
                      An OPPOSITE raw break always exits at the next open (sec 2.4).
  qual_up / qual_dn   the raw breaks that ALSO pass A1 (>= 3 touches), A2 (>= 7 calendar
                      days from A to the last counted touch) and A3 (ER(20) >= the market's
                      TRAINING-ONLY q25). Only these may enter, or reverse.

A2 is coded exactly as the registration's table says ("calendar time from A's bar to the
last counted touch"). NOTE the pre-flight (common/tl_v1_preflight.py) measured A's bar to
the BREAK bar t (its _span_days(dates, pA, t)); Amendment E reports A2 failed on zero
breaks under that reading. The registered text is A -> last touch, so that is what is coded
here, and the report prints how many breaks each reading would have failed (information).

The line code is common/tl_v1_lines.py (G3 cleared, Amendment F); nothing in it is
re-implemented. ATR is the pre-flight's (common.tl_v0_lines.atr14, no warm-up gate) for the
line and touch tests, and breaks are then masked where the repo's gated ATR(14) is unknown,
which is what the simulator's order sizing needs.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from common.tl_v0_lines import atr14, find_pivots
from common.tl_v1_lines import (MAX_SPAN, MIN_SPAN_DAYS, MIN_TOUCHES, TOUCH_BUFFER, WINDOW,
                                build_series, efficiency_ratio)
from strategy.tl_v0.bars import MarketBars
from strategy.tl_v0.engine import tl_input
from strategy.tl_v0.signals import atr_gated, market_signals
from strategy.tl_v0.sim import SimInput
from strategy.tl_v0.spec import Market

ER_LEN = 20
ER_Q = 0.25
ER_QS = (0.20, 0.25, 0.33)

# REGISTERED_tl_v1.md sec 2.3, Amendment E (PRE-RUN, W15-0019 G2, training side 2010-06 -> 2021-12)
REGISTERED_ER_Q25 = {"ES": 0.104, "RTY": 0.100, "CL": 0.109, "NG": 0.095, "6A": 0.094,
                     "6B": 0.093, "6E": 0.091, "6J": 0.086, "GC": 0.103, "SI": 0.110,
                     "HG": 0.090, "MTN": 0.086}
REGISTERED_ER = {0.20: {"ES": 0.084, "RTY": 0.074, "CL": 0.087, "NG": 0.075, "6A": 0.076,
                        "6B": 0.074, "6E": 0.073, "6J": 0.067, "GC": 0.079, "SI": 0.088,
                        "HG": 0.071, "MTN": 0.067},
                 0.25: REGISTERED_ER_Q25,
                 0.33: {"ES": 0.140, "RTY": 0.129, "CL": 0.147, "NG": 0.125, "6A": 0.127,
                        "6B": 0.126, "6E": 0.120, "6J": 0.117, "GC": 0.134, "SI": 0.148,
                        "HG": 0.120, "MTN": 0.121}}

# sec 2.5 reported variants (fixed, never ranked)
VARIANTS: dict[str, dict] = {
    "v1": {},
    "v1-A+": {"aplus": False},          # her line, every break taken
    "v1-A3": {"a3": False},             # no trending filter
    "v1-2touch": {"min_touches": 2},    # her 2-touch playbook
}


@dataclass
class Gate:
    raw_up: np.ndarray
    raw_dn: np.ndarray
    qual_up: np.ndarray
    qual_dn: np.ndarray
    touches_up: np.ndarray       # touch count at each RES break bar (0 elsewhere)
    touches_dn: np.ndarray
    span_up: np.ndarray          # A -> last counted touch, calendar days (nan elsewhere)
    span_dn: np.ndarray
    span_to_break_up: np.ndarray  # A -> break bar (the pre-flight's reading), information only
    span_to_break_dn: np.ndarray
    fail_a1_up: np.ndarray
    fail_a1_dn: np.ndarray
    fail_a2_up: np.ndarray
    fail_a2_dn: np.ndarray
    fail_a3_up: np.ndarray
    fail_a3_dn: np.ndarray


class MarketCtx:
    """One market's training bars and every cached array the signals need."""

    def __init__(self, mb: MarketBars, m: Market):
        f = mb.frame
        self.mb, self.m, self.frame = mb, m, f
        self.name = m.name
        self.dates = pd.DatetimeIndex(f["date"])
        self.o, self.h, self.l, self.c = (f[k].to_numpy(dtype=float)
                                          for k in ("open", "high", "low", "close"))
        self.n = len(self.c)
        self.a_raw = atr14(self.h, self.l, self.c).astype(float)
        self.a_gate = atr_gated(self.h, self.l, self.c)
        self.er = efficiency_ratio(self.c, ER_LEN)
        # TRAINING bars only: mb.frame is cut by the holdout before any bar exists
        self.er_thr = {q: float(np.nanquantile(self.er, q)) for q in ER_QS}
        self.touch_h = find_pivots(self.h, 2, "high")
        self.touch_l = find_pivots(self.l, 2, "low")
        self._v0, self._lines, self._touch = {}, {}, {}

    def v0sig(self, R):
        if R not in self._v0:
            self._v0[R] = market_signals(self.frame, R)
        return self._v0[R]

    def lines(self, R, window):
        key = (R, window)
        if key not in self._lines:
            ph = find_pivots(self.h, R, "high")
            pl = find_pivots(self.l, R, "low")
            self._lines[key] = {
                "res": build_series(self.n, ph, self.c, self.a_raw, "res", window=window),
                "sup": build_series(self.n, pl, self.c, self.a_raw, "sup", window=window)}
        return self._lines[key]

    def touch_info(self, R, window, buf, kind):
        """Per break bar of `kind`: touch count, A -> last touch days, A -> break days."""
        key = (R, window, buf, kind)
        if key in self._touch:
            return self._touch[key]
        out = self.lines(R, window)[kind]
        tp = self.touch_h if kind == "res" else self.touch_l
        line, anchor = out["line"], out["anchor_bar"]
        cnt = np.zeros(self.n, dtype=int)
        span = np.full(self.n, np.nan)
        span_b = np.full(self.n, np.nan)
        dvals = self.dates.to_numpy()
        for t in np.nonzero(out["breaks"])[0]:
            pA = int(anchor[t])
            if pA < 0:
                continue
            hits = []
            for (pidx, cidx, val) in tp:
                if pidx < pA or pidx > t - 1 or cidx > t - 1 or np.isnan(line[pidx]):
                    continue
                lv = line[pidx]
                tol = buf * self.a_raw[pidx]
                if (kind == "res" and val >= lv - tol) or (kind == "sup" and val <= lv + tol):
                    hits.append(pidx)
            cnt[t] = len(hits)
            span_b[t] = (dvals[t] - dvals[pA]) / np.timedelta64(1, "D")
            span[t] = (dvals[max(hits)] - dvals[pA]) / np.timedelta64(1, "D") if hits else 0.0
        self._touch[key] = (cnt, span, span_b)
        return self._touch[key]


def gate_for(ctx: MarketCtx, R: int, *, window=WINDOW, touch_buf=TOUCH_BUFFER, erq=ER_Q,
             min_touches=MIN_TOUCHES, a1=True, a2=True, a3=True) -> Gate:
    thr = ctx.er_thr[erq] if erq in ctx.er_thr else float(np.nanquantile(ctx.er, erq))
    ok_atr = ~np.isnan(ctx.a_gate)
    er_ok = np.isfinite(ctx.er) & np.isfinite(thr) & (ctx.er >= thr)
    res = {}
    for kind, tag in (("res", "up"), ("sup", "dn")):
        raw = ctx.lines(R, window)[kind]["breaks"] & ok_atr
        cnt, span, span_b = ctx.touch_info(R, window, touch_buf, kind)
        f1 = raw & ~(cnt >= min_touches)
        f2 = raw & ~(span >= MIN_SPAN_DAYS)
        f3 = raw & ~er_ok
        q = raw.copy()
        if a1:
            q &= (cnt >= min_touches)
        if a2:
            q &= (span >= MIN_SPAN_DAYS)
        if a3:
            q &= er_ok
        res[tag] = (raw, q, cnt, span, span_b, f1, f2, f3)
    u, d = res["up"], res["dn"]
    return Gate(u[0], d[0], u[1], d[1], u[2], d[2], u[3], d[3], u[4], d[4],
                u[5], d[5], u[6], d[6], u[7], d[7])


def v1_input(ctx: MarketCtx, R: int, *, aplus=True, **kw) -> tuple[SimInput, Gate]:
    """SimInput for one TL-v1 sleeve. Stops, weekly filter and sizing inputs are the
    v0-rev SimInput unchanged; only up/dn (raw line breaks) and qual_* are replaced."""
    g = gate_for(ctx, R, **kw)
    base = tl_input(ctx.v0sig(R), "v0-rev")
    if aplus:
        x = replace(base, up=g.raw_up, dn=g.raw_dn, qual_up=g.qual_up, qual_dn=g.qual_dn)
    else:
        x = replace(base, up=g.raw_up, dn=g.raw_dn, qual_up=None, qual_dn=None)
    return x, g


def break_events(ctx: MarketCtx, R: int, g: Gate, htf: np.ndarray) -> pd.DataFrame:
    """One row per raw break bar: why it did or did not become an A+ entry."""
    rows = []
    for tag, d, raw, q, cnt, span, span_b, f1, f2, f3 in (
            ("up", 1, g.raw_up, g.qual_up, g.touches_up, g.span_up, g.span_to_break_up,
             g.fail_a1_up, g.fail_a2_up, g.fail_a3_up),
            ("dn", -1, g.raw_dn, g.qual_dn, g.touches_dn, g.span_dn, g.span_to_break_dn,
             g.fail_a1_dn, g.fail_a2_dn, g.fail_a3_dn)):
        for t in np.nonzero(raw)[0]:
            rows.append(dict(market=ctx.name, R=R, j=int(t), date=ctx.dates[t], year=int(ctx.dates[t].year),
                             direction=d, touches=int(cnt[t]), span_days=float(span[t]),
                             span_to_break_days=float(span_b[t]), er=float(ctx.er[t]),
                             fail_a1=bool(f1[t]), fail_a2=bool(f2[t]), fail_a3=bool(f3[t]),
                             aplus=bool(q[t]), weekly_ok=bool(htf[t] == d),
                             fail_a2_preflight_reading=bool(not (span_b[t] >= MIN_SPAN_DAYS))))
    return pd.DataFrame(rows)
