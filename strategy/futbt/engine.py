#!/usr/bin/env python3
"""Runs a method's variants and the Donchian control on one market, and assembles books.

A "method" is any module with compute(frame, params) -> signals and
simulate(frame, signals, *, equity, integer) -> (trades, counts): strategy.crudele_3s and
strategy.breit_cap (their sim modules are passed as `sim`).

Books are strategy.tl_v0.report.Book objects (so the measures, bootstraps and drop-top rules are the
ones TL-v0 / TL-v1 were read with): trades DataFrame, and the daily mark-to-market as
level -> DataFrame(date x market). The verdict book is the FRACTIONAL book at $22,129; the integer
book at $22,129 is carried beside it (sec 2.1 of both registrations).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.futbt import core as K
from strategy.tl_v0.engine import donchian_input
from strategy.tl_v0.report import Book
from strategy.tl_v0.sim import simulate as tl_simulate
from strategy.tl_v0.spec import LEVELS

CAL_KEYS = ("frac", "int")


@dataclass
class MarketOut:
    market: str
    trades: pd.DataFrame
    daily: dict                    # (variant, sizing) -> (n, 3)
    counts: dict                   # (variant, sizing) -> dict
    dates: pd.DatetimeIndex
    signal_counts: dict = field(default_factory=dict)     # variant -> the signal module's counts
    extra: dict = field(default_factory=dict)


def run_market(fr: K.Frame, method, sim, variants: dict, *, sizings=K.VERDICT_SIZINGS,
               c1: bool = True) -> MarketOut:
    rows, daily, counts, sigcounts = [], {}, {}, {}
    for name, params in variants.items():
        sg = method.compute(fr, params)
        sigcounts[name] = dict(sg.counts)
        for sizing, eq in sizings:
            trades, cnt = sim.simulate(fr, sg, equity=eq, integer=(sizing == "int"))
            key = dict(variant=name, market=fr.market, sizing=sizing, equity=eq)
            rows.extend(K.trade_rows(trades, fr, key))
            daily[(name, sizing)] = K.daily_marks(trades, fr)
            counts[(name, sizing)] = cnt
    if c1:
        for sizing, eq in sizings:
            trades = donchian_trades(fr, eq, sizing == "int")
            key = dict(variant="C1", market=fr.market, sizing=sizing, equity=eq)
            rows.extend(K.trade_rows(trades, fr, key))
            daily[("C1", sizing)] = K.daily_marks(trades, fr)
            counts[("C1", sizing)] = dict(entries=len(trades))
    return MarketOut(fr.market, pd.DataFrame(rows), daily, counts, fr.dates, sigcounts)


def donchian_trades(fr: K.Frame, equity: float, integer: bool, risk_frac: float = 0.01):
    """C1: Donchian 20/10 as TL-v0's control (same code), one sleeve at 1% of the book's equity."""
    frame = pd.DataFrame({"open": fr.o, "high": fr.h, "low": fr.l, "close": fr.c})
    x = donchian_input(frame)
    r = tl_simulate(x, rule="ignore", mult=fr.mult, risk_usd=risk_frac * equity, integer=integer)
    return r.trades


def build_book(outs: list, variant: str, sizing: str, equity: float, calendar) -> Book:
    tr, per = [], {lv: {} for lv in LEVELS}
    for o in outs:
        t = o.trades
        if len(t):
            m = (t["variant"] == variant) & (t["sizing"] == sizing) & (t["equity"] == equity)
            tr.append(t[m])
        arr = o.daily.get((variant, sizing))
        if arr is None:
            continue
        for i, lv in enumerate(LEVELS):
            per[lv][o.market] = pd.Series(arr[:, i], index=o.dates)
    daily = {lv: pd.DataFrame(per[lv]).reindex(calendar).fillna(0.0) for lv in LEVELS}
    trades = pd.concat(tr, ignore_index=True) if tr else pd.DataFrame()
    return Book(variant, "all", sizing, equity, trades, daily, calendar)
