#!/usr/bin/env python3
"""The H60 panel: every symbol's 60-minute bars on one global session clock,
with point-in-time eligibility attached. W14-0003, REGISTERED_h60_v0.md §2.1.

GLOBAL CLOCK
------------
`sessions` is the sorted list of dates that have bars. Session index `s`
counts SESSIONS, not calendar days, so "the fifth session after the entry
session" is `s + 5` whatever weekends and holidays sit between.

A grid slot is `g = s * 7 + bar`. Each slot has two MARKS, its open (2g) and
its close (2g + 1); the market basket (basket.py) is an index over marks, and
every fill in the engine happens at a mark:

    open of a bar        -> mark 2g       (entries, next-open exits, gap fills)
    inside a bar         -> mark 2g + 1   (a resting stop or target touched
                                           intrabar is booked against the
                                           basket at that bar's close)
    close of a bar       -> mark 2g + 1   (the time cap)

ELIGIBILITY IS THE SWING CHAT'S HINDSIGHT GUARD, REUSED
-------------------------------------------------------
`Spell.covers` (strategy/swing/pit_universe.py) decides whether a membership
spell covers a day; the EODHD code -> Databento raw symbol mapping is
data_plan.to_raw_symbol. Neither is rewritten here (§2.1).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.h60.bars import BARS_PER_SESSION, normalise
from strategy.h60.data_plan import to_raw_symbol

NB = BARS_PER_SESSION

# A symbol's bars are split into SEGMENTS, and every rule runs on one segment
# at a time, where the series (a) skips more than SEGMENT_GAP sessions -- the
# pull fetched a name only while it was a member, so a name that left the
# index and came back has a months-long hole -- or (b) the membership code
# behind the raw symbol changes (ticker reuse: two companies, one symbol).
# §2.2 runs indicators "on the continuous hourly series ... as a TradingView
# chart does"; a chart has the bars in between, this archive does not, and
# splicing across the hole (or across two companies) would feed a DON channel
# or a TL pivot bars that are not this series. Each segment re-warms (§2.2's
# 30 sessions) from its own start. Raised by the W14-0003 review.
SEGMENT_GAP = 5


@dataclass
class SymArrays:
    symbol: str
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    s: np.ndarray            # session index per bar
    bar: np.ndarray          # grid slot within the session
    g: np.ndarray            # global slot id
    t: pd.DatetimeIndex      # bar START, UTC
    eligible: np.ndarray     # member on this bar's session
    last_of_session: np.ndarray

    @property
    def n(self) -> int:
        return len(self.o)

    def frame(self) -> pd.DataFrame:
        """OHLCV frame indexed by bar start -- what the imported signal
        functions (mcl.signals, mc5.signals, ...) take."""
        return pd.DataFrame({"open": self.o, "high": self.h, "low": self.l,
                             "close": self.c, "volume": self.v}, index=self.t)


def slice_arrays(a: "SymArrays", st: int, en: int) -> "SymArrays":
    """Bars [st, en) of a symbol as their own series."""
    s = a.s[st:en]
    return SymArrays(symbol=a.symbol, o=a.o[st:en], h=a.h[st:en], l=a.l[st:en],
                     c=a.c[st:en], v=a.v[st:en], s=s, bar=a.bar[st:en],
                     g=a.g[st:en], t=a.t[st:en], eligible=a.eligible[st:en],
                     last_of_session=np.r_[s[1:] != s[:-1], True] if len(s) else s.astype(bool))


class Universe:
    """Raw-symbol eligibility per session from membership spells."""

    def __init__(self, spells):
        self.by_sym: dict[str, list] = {}
        for sp in spells:
            r = to_raw_symbol(sp.code)
            if r:
                self.by_sym.setdefault(r, []).append(sp)

    def eligible(self, symbol: str, day: dt.date) -> bool:
        return any(sp.covers(day) for sp in self.by_sym.get(symbol, ()))

    def code_on(self, symbol: str, day: dt.date) -> str | None:
        for sp in self.by_sym.get(symbol, ()):
            if sp.covers(day):
                return sp.code
        return None

    def matrix(self, symbol: str, sessions: list[dt.date]) -> np.ndarray:
        return np.array([self.eligible(symbol, d) for d in sessions], dtype=bool)

    def symbols_on(self, day: dt.date) -> list[str]:
        return sorted(r for r, sps in self.by_sym.items()
                      if any(sp.covers(day) for sp in sps))


@dataclass
class Panel:
    grid: str
    sessions: list
    bars: pd.DataFrame
    universe: Universe
    elig: dict = field(default_factory=dict)       # symbol -> bool[n_sessions]
    _off: dict = field(default_factory=dict)
    _cache: dict = field(default_factory=dict)

    @classmethod
    def build(cls, bars: pd.DataFrame, universe: Universe, grid: str) -> "Panel":
        b = normalise(bars)
        sessions = sorted(b["session"].unique())
        s_of = {d: i for i, d in enumerate(sessions)}
        b["s"] = b["session"].map(s_of).astype(int)
        b["g"] = b["s"] * NB + b["bar"]
        p = cls(grid=grid, sessions=sessions, bars=b, universe=universe)
        sym = b["symbol"].to_numpy()
        starts = np.flatnonzero(np.r_[True, sym[1:] != sym[:-1]])
        ends = np.r_[starts[1:], len(sym)]
        for a, e in zip(starts, ends):
            p._off[sym[a]] = (int(a), int(e))
        for s in p._off:
            p.elig[s] = universe.matrix(s, sessions)
        return p

    @property
    def symbols(self) -> list[str]:
        return sorted(self._off)

    @property
    def n_sessions(self) -> int:
        return len(self.sessions)

    def arrays(self, symbol: str) -> SymArrays:
        if symbol in self._cache:
            return self._cache[symbol]
        a, e = self._off[symbol]
        d = self.bars.iloc[a:e]
        s = d["s"].to_numpy()
        last = np.r_[s[1:] != s[:-1], True]
        arr = SymArrays(
            symbol=symbol,
            o=d["open"].to_numpy(float), h=d["high"].to_numpy(float),
            l=d["low"].to_numpy(float), c=d["close"].to_numpy(float),
            v=d["volume"].to_numpy(float), s=s, bar=d["bar"].to_numpy(),
            g=d["g"].to_numpy(), t=pd.DatetimeIndex(d["t_open"]),
            eligible=self.elig[symbol][s], last_of_session=last)
        self._cache[symbol] = arr
        return arr

    def segment_bounds(self, symbol: str) -> list[tuple[int, int]]:
        key = ("seg", symbol)
        if key in self._cache:
            return self._cache[key]
        a = self.arrays(symbol)
        if a.n == 0:
            return []
        us = np.unique(a.s)
        code = {int(s): self.universe.code_on(symbol, self.sessions[s]) for s in us}
        prev_s = np.r_[a.s[0], a.s[:-1]]
        gap = (a.s - prev_s - 1) > SEGMENT_GAP
        cb = np.array([code[int(s)] for s in a.s], dtype=object)
        cprev = np.r_[cb[:1], cb[:-1]]
        changed = np.array([x is not None and y is not None and x != y
                            for x, y in zip(cb, cprev)], dtype=bool)
        starts = np.flatnonzero(gap | changed)
        starts = np.r_[0, starts[starts > 0]]
        ends = np.r_[starts[1:], a.n]
        out = [(int(x), int(y)) for x, y in zip(starts, ends)]
        self._cache[key] = out
        return out

    def eligible_symbols(self, s: int) -> list[str]:
        return [sym for sym, m in self.elig.items() if m[s]]
