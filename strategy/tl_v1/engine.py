#!/usr/bin/env python3
"""Runs every TL-v1 sleeve, variant and the Donchian control on one market's training bars.

REGISTERED_tl_v1.md sec 2-3. Same walk as strategy/tl_v0/engine.py (same simulate(), same
booking, same 1%-of-$22,129 fixed-equity convention, same four sizings); what differs is
only the SimInput (strategy/tl_v1/signals.py). Rule is always "reverse" (v0-rev exits, sec 2.4):
an opposite raw break exits, and reverses only when that break is A+ and passes the weekly filter.

Specs written into the trade rows:
  v1         her line + A1-A3, ensemble sleeves (1/3 risk each) and each R alone (full risk)
  v1-A+      her line, every break taken           (sec 2.5)
  v1-A3      no trending filter                    (sec 2.5)
  v1-2touch  A1 = >= 2 touches                     (sec 2.5)
  C1         Donchian 20/10, one sleeve at 1%      (sec 3; same code as TL-v0's C1)
C2 (TL-v0-rev) is NOT re-run: it is read from the W15-0014 output (sec 3, "from the W15-0014 run").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.tl_v0.bars import MarketBars
from strategy.tl_v0.engine import SIZINGS, _run, donchian_input
from strategy.tl_v0.sim import simulate
from strategy.tl_v0.spec import EQUITY, PIVOT_SIZES, RISK_PCT, Market
from strategy.tl_v1.signals import VARIANTS, MarketCtx, break_events, v1_input

VARIANT_SIZINGS = SIZINGS[:2]          # fractional + integer @ $22,129 (the two the verdict reads)


@dataclass
class MarketRun:
    market: str
    trades: pd.DataFrame
    daily: dict
    counts: pd.DataFrame
    dates: pd.DatetimeIndex
    events: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: dict = field(default_factory=dict)


def run_market(mb: MarketBars, m: Market, ctx: MarketCtx | None = None) -> tuple[MarketRun, MarketCtx]:
    ctx = ctx or MarketCtx(mb, m)
    frame = mb.frame
    rows, counts, daily, events = [], [], {}, []

    def one(spec, R, share, x, rule, frac_share, sizings, gate=None):
        for sizing, eq in sizings:
            risk = RISK_PCT * eq * frac_share
            r = simulate(x, rule=rule, mult=m.mult, risk_usd=risk, integer=(sizing == "int"))
            key = dict(market=m.name, spec=spec, R=R, share=share, sizing=sizing, equity=eq)
            start = len(rows)
            _run(key, r.trades, frame, m, risk, rows, daily, (spec, R, share, sizing, eq))
            if gate is not None:                       # touches / span of the break that fired the entry
                for row in rows[start:]:
                    sj = row["entry_j"] - 1
                    up = row["direction"] > 0
                    row["touches"] = int((gate.touches_up if up else gate.touches_dn)[sj])
                    row["span_days"] = float((gate.span_up if up else gate.span_dn)[sj])
            counts.append({**key, **r.counts.as_dict()})

    diag = {}
    for R in PIVOT_SIZES:
        for spec, kw in VARIANTS.items():
            x, g = v1_input(ctx, R, **kw)
            sizings = SIZINGS if spec == "v1" else VARIANT_SIZINGS
            one(spec, R, "sleeve", x, "reverse", 1.0 / len(PIVOT_SIZES), sizings, g)
            one(spec, R, "alone", x, "reverse", 1.0, sizings, g)
            if spec == "v1":
                ev = break_events(ctx, R, g, x.htf)
                events.append(ev)
                diag[f"raw_breaks_R{R}"] = int(g.raw_up.sum() + g.raw_dn.sum())
                diag[f"aplus_breaks_R{R}"] = int(g.qual_up.sum() + g.qual_dn.sum())
    one("C1", 0, "single", donchian_input(frame), "ignore", 1.0, SIZINGS)
    run = MarketRun(m.name, pd.DataFrame(rows), daily, pd.DataFrame(counts),
                    pd.DatetimeIndex(frame["date"]),
                    pd.concat(events, ignore_index=True) if events else pd.DataFrame(), diag)
    return run, ctx
