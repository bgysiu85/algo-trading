#!/usr/bin/env python3
"""Runs every TL-v2 sleeve and variant, plus the Donchian control C1, on one market's training bars.

REGISTERED_tl_v2.md sec 2-3. Same walk as strategy/tl_v1/engine.py (same simulate(), same booking,
same 1%-of-$22,129 fixed-equity convention, same sizings); only the SimInput differs
(strategy/tl_v2/signals.py) and the dollars charged: IBKR fee + 0/1/2 ticks per side, no separate
stop-fill tick (Amendment 1 of the registration; strategy/tl_v2/costs.py). Rule is always "reverse" (v0-rev exits): an opposite raw break exits,
and the strategy re-enters only on a qualified RETEST entry, never straight off a raw break.

Specs written into the trade rows:
  v2       primary, N = 10, ensemble sleeves (1/3 risk each) and each R alone (full risk)
  v2-SR    retest entries only where an S/R zone coincides (sec 2.3), reported only
  v2-N20   N = 20 (sec 2.3), reported only
  C1       Donchian 20/10 (same code as TL-v0's C1)
C2 (TL-v1 immediate entry) is NOT re-run: read from W15-0020's books. C3 (random selection of
retest entries), the 27-cell grid and the report layer are the backtest step (W15-0031).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from strategy.tl_v0 import pnl
from strategy.tl_v0.bars import MarketBars
from strategy.tl_v0.engine import SIZINGS, _trade_rows, donchian_input
from strategy.tl_v0.sim import simulate
from strategy.tl_v0.spec import LEVELS, PIVOT_SIZES, RISK_PCT, Market
from strategy.tl_v1.signals import MarketCtx
from strategy.tl_v2 import costs as C
from strategy.tl_v2.signals import VARIANTS, v2_input

VARIANT_SIZINGS = SIZINGS[:2]          # fractional + integer @ $22,129, as TL-v1


@dataclass
class MarketRun:
    market: str
    trades: pd.DataFrame
    daily: dict
    counts: pd.DataFrame
    dates: pd.DatetimeIndex
    events: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: dict = field(default_factory=dict)


def _run(label_key, trades, frame, m: Market, risk_usd, rows, daily_store, dkey):
    """TL-v0's booking, priced at IBKR (strategy/tl_v2/costs.py): net_low/mid/high are gross minus
    the IBKR per-side level x contracts x sides, no separate stop-fill tick (Amendment 1)."""
    booked = [pnl.book(t, frame, m) for t in trades]
    new = _trade_rows(trades, booked, frame, label_key, risk_usd)
    for row, b, t in zip(new, booked, trades):
        row["slip"] = 0.0
        for lv in LEVELS:
            row["net_" + lv] = C.net(b, lv, t.qty, m)
    rows.extend(new)
    daily_store[dkey] = C.daily(trades, booked, frame, m)


def run_market(mb: MarketBars, m: Market, ctx: MarketCtx | None = None) -> tuple[MarketRun, MarketCtx]:
    ctx = ctx or MarketCtx(mb, m)
    frame = mb.frame
    rows, counts, daily, events = [], [], {}, []

    def one(spec, R, share, x, rule, frac_share, sizings):
        for sizing, eq in sizings:
            risk = RISK_PCT * eq * frac_share
            r = simulate(x, rule=rule, mult=m.mult, risk_usd=risk, integer=(sizing == "int"))
            key = dict(market=m.name, spec=spec, R=R, share=share, sizing=sizing, equity=eq)
            _run(key, r.trades, frame, m, risk, rows, daily, (spec, R, share, sizing, eq))
            counts.append({**key, **r.counts.as_dict()})

    diag = {}
    for R in PIVOT_SIZES:
        for spec, kw in VARIANTS.items():
            x, s = v2_input(ctx, R, **kw)
            sizings = SIZINGS if spec == "v2" else VARIANT_SIZINGS
            one(spec, R, "sleeve", x, "reverse", 1.0 / len(PIVOT_SIZES), sizings)
            one(spec, R, "alone", x, "reverse", 1.0, sizings)
            if spec in ("v2", "v2-N20"):
                ev = s.scan.events.copy()
                ev.insert(0, "market", m.name)
                ev.insert(1, "R", R)
                ev.insert(2, "spec", spec)
                events.append(ev)
            if spec == "v2":
                diag[f"qualified_R{R}"] = int(s.qual_up_w.sum() + s.qual_dn_w.sum())
                diag[f"retest_entries_R{R}"] = int(s.scan.ent_up.sum() + s.scan.ent_dn.sum())
    one("C1", 0, "single", donchian_input(frame), "ignore", 1.0, SIZINGS)
    run = MarketRun(m.name, pd.DataFrame(rows), daily, pd.DataFrame(counts),
                    pd.DatetimeIndex(frame["date"]),
                    pd.concat(events, ignore_index=True) if events else pd.DataFrame(), diag)
    return run, ctx
