#!/usr/bin/env python3
"""The seven H60 rule sets, each at its source's parameters, nothing re-fitted.
W14-0003, REGISTERED_h60_v0.md §3.

"IMPORTED" MEANS CALLED, NOT COPIED (PROGRAM_INDEX §1, the parity rule)
---------------------------------------------------------------------
    MCL-60   strategy.mcl.mcl.signals()                         §3.1
    MC5-60   strategy.mc5.mc5.signals()                         §3.2
    VW9-60   strategy.vw9.vw9.classify_regime / track_setups,
             strategy.vw9.backtest._passes_entry_gates          §3.7
    TL-60    common.tl_v0_lines (pivots, walk_line_and_breaks,
             swing_fallback, atr14)                              §3.5
    ORB-60, DON-60  written here (§3.3, §3.4 say so)
    MR-60    NOT BUILT -- its rules come from Ben's Pine source by PRE-RUN
             amendment A (gate G3, W14-0005). `mr60` refuses until then.

No sweep parameter is passed to any imported function; the module constants
are what run.

WHERE A PORT DIFFERS FROM ITS SOURCE, AND WHY (each forced by §2 or the data)
----------------------------------------------------------------------------
* Every close-decided exit (DON's channel, VW9's VWAP-lost and ride_ema9)
  fills at the NEXT bar's open (§2.2). VW9's 5-minute source fills VWAP-lost
  at that bar's close. On a bar that touches the 2R target intrabar and then
  closes below VWAP, H60 books the target -- it happened first -- where the
  source, checking VWAP before the target, books VWAP-lost.
* A target is filled AT the level, as the source does, never at a better
  gap open (exits.py).
* VW9's indicators are rebuilt here (vw9_indicators) rather than by calling
  vw9.apply_indicators, because §3.7 makes EMA9/ATR continuous across
  sessions and VWAP per 09:30 session; the regime rule and both setup
  trackers are vw9's own (classify_regime, track_setups).
* On the FALLBACK grid (amendment B, bars.py) the session's first bar is the
  09:30-10:00 half hour: ORB-60's "range" becomes that 30-minute bar and its
  entry window the 10:00-14:00 bars; VW9-60's first possible trigger (the
  third bar's close) moves from 11:30 to 12:00. Slots, not clock times, are
  what the code reads -- amendment B has to say which it means.

Every rule returns, per symbol, a boolean ENTRY per bar -- "the rule fires on
this bar's close" -- plus what its exit needs. The engine fills at the next
bar's open. A rule never sees a bar after the one it is deciding on: the
look-ahead guard (guards.py) truncates the series and checks every rule's
entry bits against the untruncated run.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from strategy.h60.exits import ExitSpec
from strategy.h60.panel import SymArrays

TRAIL_PCT = 5.0            # MCL / MC5 / ORB trail, as published

# Gate G4 (REGISTERED_h60_v0.md §0): TL-60 runs only once the TL-v0 Python
# engine has passed its Pine parity check (W01-0006). W01-0006 closed Done
# 2026-09-25 (commit 4529c51); Ben confirmed on W14-0008 the same day, in his
# words: "Yes". Recorded in the registration beside amendment B, before any
# H60 bar was read -- never on a result from this study.
TL_PARITY_PASSED = True

# Gate G3: MR-60's parameters come from amendment A. Set by that commit.
MR_AMENDMENT_A = False


class NotRegistered(SystemExit):
    """A rule set whose registration is not complete refuses to run."""


@dataclass
class RuleOut:
    entry: np.ndarray
    spec: ExitSpec
    # stop(sig_idx, fill_px) -> per-entry resting stop (NaN = none available)
    stop: Callable | None = None
    # the same for an ARBITRARY bar -- what a random entry at that bar gets
    stop_any: Callable | None = None
    xsig: np.ndarray | None = None
    ratchet: np.ndarray | None = None
    atr_prev: np.ndarray | None = None
    session_cap: int | None = None
    diag: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Book:
    """One book of trades: a rule set at one exit / sleeve, scored or only
    reported."""
    name: str
    rule: str
    variant: str
    scored: bool
    notional: float = 10_000.0


def _session_slices(s: np.ndarray):
    starts = np.flatnonzero(np.r_[True, s[1:] != s[:-1]])
    ends = np.r_[starts[1:], len(s)]
    return list(zip(starts, ends))


def _shift1(x: np.ndarray) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    out[0] = np.nan
    out[1:] = x[:-1]
    return out


# A rule's signal work is shared by its exit variants (VW9's four exits, TL's
# sleeve and alone books): the engine runs a rule's books symbol by symbol
# (engine.run_books), so a small cache of the last few symbols' cores is hit
# by every variant. Keyed on the bars themselves, never on object identity.
_CORE: "OrderedDict[tuple, dict]" = OrderedDict()
_CORE_MAX = 8


def _core_key(kind: str, a: SymArrays, extra=None) -> tuple:
    """A digest of every input the core reads -- prices, volume, sessions,
    slots, times, eligibility -- so two different series can never share a
    cached core (a key on symbol and length alone did, in the first draft)."""
    h = hashlib.blake2b(digest_size=16)
    for x in (a.o, a.h, a.l, a.c, a.v, a.s, a.bar, a.g,
              np.asarray(a.t.asi8), a.eligible):
        h.update(np.ascontiguousarray(x).tobytes())
    return (kind, a.symbol, a.n, h.hexdigest(), extra)


def _memo(key: tuple, build):
    hit = _CORE.get(key)
    if hit is not None:
        _CORE.move_to_end(key)
        return hit
    val = build()
    _CORE[key] = val
    while len(_CORE) > _CORE_MAX:
        _CORE.popitem(last=False)
    return val


def _rolling_min_in_session(x: np.ndarray, s: np.ndarray, window: int) -> np.ndarray:
    """min of x over the last `window` bars of the same session, inclusive."""
    out = x.astype(float).copy()
    for k in range(1, window):
        prev = np.r_[np.full(k, np.nan), x[:-k]] if len(x) > k else np.full(len(x), np.nan)
        same = np.r_[np.zeros(k, bool), s[k:] == s[:-k]] if len(x) > k else np.zeros(len(x), bool)
        out = np.where(same, np.fmin(out, prev), out)
    return out


class _Cols:
    """The three things vw9.track_setups reads from its frame -- len(),
    frame[col].tolist() and frame.index -- over plain lists, so the imported
    tracker runs ~2M session slices without building 2M DataFrames. It is
    still vw9.track_setups that runs."""

    class _L(list):
        def tolist(self):
            return self

    def __init__(self, cols: dict, index):
        self._c = cols
        self.index = index

    def __len__(self):
        return len(self.index)

    def __getitem__(self, k):
        return _Cols._L(self._c[k])


# --------------------------------------------------------------------------
# §3.1 MCL-60, §3.2 MC5-60
# --------------------------------------------------------------------------

def mcl60(a: SymArrays, variant: str = "trail5") -> RuleOut:
    from strategy.mcl import mcl
    sig = mcl.signals(a.frame())
    return RuleOut(entry=sig["entry"].fillna(False).to_numpy(bool),
                   spec=ExitSpec(trail_pct=TRAIL_PCT))


def mc5_60(a: SymArrays, variant: str = "trail5") -> RuleOut:
    from strategy.mc5 import mc5
    sig = mc5.signals(a.frame())
    return RuleOut(entry=sig["entry"].fillna(False).to_numpy(bool),
                   spec=ExitSpec(trail_pct=TRAIL_PCT))


# --------------------------------------------------------------------------
# §3.3 ORB-60 -- one 60-minute range (the session's first bar)
# --------------------------------------------------------------------------

# the 10:30 .. 14:30 bars on the primary grid; on the fallback grid slots 1-5
# are 10:00 .. 14:00 and slot 0 (the range) is only 30 minutes -- see the
# module docstring and amendment B
ORB_FIRST_SLOT, ORB_LAST_SLOT = 1, 5


def orb60(a: SymArrays, variant: str = "structure_trail5") -> RuleOut:
    n = a.n
    entry = np.zeros(n, bool)
    rng_lo = np.full(n, np.nan)
    for st, en in _session_slices(a.s):
        if a.bar[st] != 0:
            continue                       # no range bar: no ORB that session
        hi, lo = a.h[st], a.l[st]
        rng_lo[st:en] = lo
        for j in range(st + 1, en):
            if ORB_FIRST_SLOT <= a.bar[j] <= ORB_LAST_SLOT and a.c[j] > hi:
                entry[j] = True
                break                      # the FIRST such bar only

    def stop(idx, fill_px):
        return rng_lo[np.asarray(idx)]

    return RuleOut(entry=entry, spec=ExitSpec(fixed_stop=True, trail_pct=TRAIL_PCT),
                   stop=stop, stop_any=stop)


# --------------------------------------------------------------------------
# §3.4 DON-60 -- 20/10 Donchian
# --------------------------------------------------------------------------

DON_ENTRY, DON_EXIT = 20, 10


def don60(a: SymArrays, variant: str = "channel") -> RuleOut:
    h, l, c = pd.Series(a.h), pd.Series(a.l), pd.Series(a.c)
    upper = h.rolling(DON_ENTRY).max().shift(1)
    lower = l.rolling(DON_EXIT).min().shift(1)
    entry = (c > upper).fillna(False).to_numpy(bool)
    xsig = (c < lower).fillna(False).to_numpy(bool)
    return RuleOut(entry=entry, spec=ExitSpec(close_exit=True), xsig=xsig)


# --------------------------------------------------------------------------
# §3.7 VW9-60 -- VWAP + 9 EMA, both setups
# --------------------------------------------------------------------------

VW9_EXITS = ("fixed_2r", "ride_ema9", "trail_atr", "trail_pct")
VW9_DEPLOYED = "fixed_2r"
VW9_LIQUIDITY_OFF = 0.0                   # §3.7: the $40k/min gate is off


def vw9_indicators(a: SymArrays) -> pd.DataFrame:
    """EMA9 and ATR14 continuous across sessions; VWAP, cumulative $ volume
    and the maturity bar count restart at each 09:30 session (§3.7)."""
    from common.indicators import atr, ema
    from strategy.vw9 import vw9
    f = a.frame()
    f["ema9"] = ema(f["close"], vw9.EMA_FAST).to_numpy()
    f["atr14"] = atr(f["high"], f["low"], f["close"], vw9.ATR_LENGTH).to_numpy()
    sess = pd.Series(a.s, index=f.index)
    tp = (f["high"] + f["low"] + f["close"]) / 3.0
    cpv = (tp * f["volume"]).groupby(sess).cumsum()
    cv = f["volume"].groupby(sess).cumsum()
    f["vwap"] = (cpv / cv.where(cv > 0)).to_numpy()
    f["cum_dv"] = (f["close"] * f["volume"]).groupby(sess).cumsum().to_numpy()
    nsess = sess.groupby(sess).cumcount() + 1
    ntot = pd.Series(np.arange(1, a.n + 1), index=f.index)
    mature = ((ntot >= vw9.EMA_FAST)
              & (nsess >= vw9.MIN_VWAP_BARS)
              & (f["cum_dv"] >= vw9.MIN_VWAP_DOLLAR_VOL))
    f["mature"] = mature.to_numpy()
    f["regime"] = vw9.classify_regime(f["close"], f["ema9"], f["vwap"], f["mature"])
    return f


def _vw9_core(a: SymArrays) -> dict:
    from strategy.vw9 import backtest as B
    from strategy.vw9 import vw9
    f = vw9_indicators(a)
    n = a.n
    entry = np.zeros(n, bool)
    struct = np.full(n, np.nan)
    kinds = np.full(n, "", dtype=object)
    closes = f["close"].to_numpy()
    ema9 = f["ema9"].to_numpy()
    atr_ = f["atr14"].to_numpy()
    vol = f["volume"].to_numpy()
    vwap = f["vwap"].to_numpy()
    cols = {"high": a.h.tolist(), "low": a.l.tolist(), "close": closes.tolist(),
            "atr14": atr_.tolist(), "volume": vol.tolist(),
            "regime": f["regime"].tolist()}
    blocked = {"ext": 0, "pullback_vol": 0}
    for st, en in _session_slices(a.s):
        view = _Cols({k: v[st:en] for k, v in cols.items()}, a.t[st:en])
        for su in vw9.track_setups(view):
            t = st + su.bar_index
            ext = ((closes[t] - ema9[t]) / atr_[t]) if atr_[t] else None
            if not B._passes_entry_gates(su, 60, ext, closes[t] * vol[t],
                                         min_trigger_dv_per_min=VW9_LIQUIDITY_OFF,
                                         max_ext_atr=B.MAX_EXT_ATR):
                blocked["ext" if (ext is not None and ext > B.MAX_EXT_ATR)
                        else "pullback_vol"] += 1
                continue
            entry[t] = True
            struct[t] = su.structure_low
            kinds[t] = su.kind
    return {"entry": entry, "struct": struct, "kinds": kinds, "closes": closes,
            "ema9": ema9, "atr": atr_, "vwap_lost": np.asarray(closes <= vwap) & ~np.isnan(vwap),
            "any_low": _rolling_min_in_session(a.l, a.s, vw9.RECLAIM_LOOKBACK),
            "blocked": blocked}


def vw9_60(a: SymArrays, variant: str = VW9_DEPLOYED) -> RuleOut:
    from strategy.vw9 import backtest as B
    if variant not in VW9_EXITS:
        raise ValueError(f"unknown VW9-60 exit {variant!r}")
    k = _memo(_core_key("vw9", a), lambda: _vw9_core(a))
    struct, atr_, any_low = k["struct"], k["atr"], k["any_low"]

    def stop(idx, fill_px):
        idx = np.asarray(idx)
        return struct[idx] - B.STOP_BUFFER_ATR * np.nan_to_num(atr_[idx])

    def stop_any(idx, fill_px):
        # a random entry has no setup: its "structure" is the lowest low of
        # the last RECLAIM_LOOKBACK bars of that session, Setup A's own cap
        idx = np.asarray(idx)
        return any_low[idx] - B.STOP_BUFFER_ATR * np.nan_to_num(atr_[idx])

    vwap_lost = k["vwap_lost"]
    if variant == "fixed_2r":
        spec = ExitSpec(fixed_stop=True, target_r=B.TARGET_R, close_exit=True)
        xsig = vwap_lost
    elif variant == "ride_ema9":
        spec = ExitSpec(fixed_stop=True, close_exit=True)
        xsig = vwap_lost | (k["closes"] < k["ema9"])
    elif variant == "trail_atr":
        spec = ExitSpec(fixed_stop=True, trail_atr=B.TRAIL_ATR, close_exit=True)
        xsig = vwap_lost
    else:
        spec = ExitSpec(fixed_stop=True, trail_pct=B.TRAIL_PCT, close_exit=True)
        xsig = vwap_lost
    return RuleOut(entry=k["entry"], spec=spec, stop=stop, stop_any=stop_any,
                   xsig=xsig, atr_prev=_shift1(atr_),
                   session_cap=B.MAX_ENTRIES_PER_SESSION,
                   diag={"gate_blocked": dict(k["blocked"]), "kind": k["kinds"]})


# --------------------------------------------------------------------------
# §3.5 TL-60 -- TL-v0 (not v0-rev), long side, daily top-down filter
# --------------------------------------------------------------------------

TL_PIVOTS = (3, 5, 8)
TL_STOP_ATR = 0.25


def _daily(a: SymArrays):
    sl = _session_slices(a.s)
    o = np.array([a.o[st] for st, _ in sl])
    h = np.array([a.h[st:en].max() for st, en in sl])
    l = np.array([a.l[st:en].min() for st, en in sl])
    c = np.array([a.c[en - 1] for _, en in sl])
    ses = np.array([a.s[st] for st, _ in sl])
    return o, h, l, c, ses


def daily_filter(a: SymArrays, R: int) -> np.ndarray:
    """Per hourly bar: True if the last DAILY line break, among daily bars
    COMPLETED before this bar's session, was upward. A bar never sees the
    daily bar of its own session (REGISTERED_tl_v0.md §8, the forming-bar
    trap, one timeframe step down)."""
    from common.tl_v0_lines import atr14, find_pivots, walk_line_and_breaks
    o, h, l, c, ses = _daily(a)
    if len(c) < 2:
        return np.zeros(a.n, bool)
    at = atr14(h, l, c)
    _, ups = walk_line_and_breaks(len(c), find_pivots(h, R, "high"), R, c, at, "high")
    _, downs = walk_line_and_breaks(len(c), find_pivots(l, R, "low"), R, c, at, "low")
    state = np.zeros(len(c), dtype=np.int8)          # +1 long, -1 short, 0 none
    cur = 0
    for j in range(len(c)):
        if ups[j]:
            cur = 1
        elif downs[j]:
            cur = -1
        state[j] = cur
    # daily bar k's state is usable from the NEXT session this symbol trades
    pos = np.searchsorted(ses, a.s, side="left") - 1
    return np.where(pos >= 0, state[np.clip(pos, 0, None)] == 1, False)


def tl60(a: SymArrays, variant: str = "R5") -> RuleOut:
    if not TL_PARITY_PASSED:
        raise NotRegistered(
            "TL-60 does not run until gate G4 is cleared: the TL-v0 Python "
            "engine's Pine parity check (W01-0006). REGISTERED_h60_v0.md §0 "
            "G4 -- report TL-60 as 'not run' and let DON-60 carry the trend "
            "family alone.")
    return tl60_unchecked(a, variant)


def tl60_unchecked(a: SymArrays, variant: str = "R5") -> RuleOut:
    """TL-60 with the G4 gate bypassed -- for tests and the pre-flight's
    signal counts only. Never called by the scoring path."""
    from common.tl_v0_lines import (atr14, find_pivots, swing_fallback,
                                    walk_line_and_breaks)
    R = int(str(variant).lstrip("R"))
    if R not in TL_PIVOTS:
        raise ValueError(f"TL-60 pivot size must be one of {TL_PIVOTS}")
    h, l, c = a.h, a.l, a.c

    def build():
        at = atr14(h, l, c)
        ph, pl = find_pivots(h, R, "high"), find_pivots(l, R, "low")
        _, ups = walk_line_and_breaks(a.n, ph, R, c, at, "high")
        sup, _ = walk_line_and_breaks(a.n, pl, R, c, at, "low")
        return {"at": at, "ph": ph, "pl": pl, "entry": ups & daily_filter(a, R),
                "safety": sup - TL_STOP_ATR * at}
    k = _memo(_core_key("tl", a, R), build)
    ph, pl, entry, safety = k["ph"], k["pl"], k["entry"], k["safety"]
    # at_prev[j] = ATR as of bar j-1's close, ONE LONGER than the series, so
    # the fallback can be asked about fill index sig+1 even when the series
    # ends at the signal bar (the look-ahead guard cuts it exactly there --
    # the W14-0003 review found the first draft raised IndexError on it)
    at_prev = np.r_[np.nan, k["at"]]

    def stop(idx, fill_px):
        idx = np.asarray(idx)
        fpx = np.asarray(fill_px, float)
        out = safety[idx].copy()
        for m in np.flatnonzero(np.isnan(out)):
            # no opposing line: the registered fallback, evaluated as of the
            # SIGNAL bar -- pivots confirmed before the fill bar, the lows up
            # to the signal bar, and the signal bar's ATR (at_prev[fill])
            fb = swing_fallback(pl, ph, h, l, at_prev, R, int(idx[m]) + 1,
                                float(fpx[m]), "long")
            out[m] = np.nan if fb is None else fb
        return out

    return RuleOut(entry=entry, spec=ExitSpec(fixed_stop=True, ratchet=True),
                   stop=stop, stop_any=stop, ratchet=safety)


# --------------------------------------------------------------------------
# §3.6 MR-60 -- waits for amendment A
# --------------------------------------------------------------------------

def mr60(a: SymArrays, variant: str = "pine_defaults") -> RuleOut:
    raise NotRegistered(
        "MR-60 has no rules yet. REGISTERED_h60_v0.md §3.6 / gate G3: every "
        "parameter comes from Ben's saved Pine file (W14-0005) by PRE-RUN "
        "amendment A, committed before any MR-60 code exists.")


# --------------------------------------------------------------------------
# the registry -- §8's holdout priority order is the order here
# --------------------------------------------------------------------------

RULES = {
    "MR-60": mr60,
    "DON-60": don60,
    "TL-60": tl60,
    "ORB-60": orb60,
    "VW9-60": vw9_60,
    "MC5-60": mc5_60,
    "MCL-60": mcl60,
}
PRIORITY = tuple(RULES)          # §8: MR, DON, TL, ORB, VW9, MC5, MCL


def books() -> list[Book]:
    """Every book the run reports. `scored` marks the one per rule set that
    §7 judges; the rest are reported, never scored."""
    out = [
        Book("MR-60", "MR-60", "pine_defaults", True),
        Book("DON-60", "DON-60", "channel", True),
    ]
    third = 10_000.0 / len(TL_PIVOTS)
    for R in TL_PIVOTS:
        out.append(Book(f"TL-60/sleeve-R{R}", "TL-60", f"R{R}", False, third))
    for R in TL_PIVOTS:
        out.append(Book(f"TL-60/R{R}-alone", "TL-60", f"R{R}", False))
    out += [
        Book("ORB-60", "ORB-60", "structure_trail5", True),
        Book("VW9-60", "VW9-60", VW9_DEPLOYED, True),
    ]
    out += [Book(f"VW9-60/{x}", "VW9-60", x, False)
            for x in VW9_EXITS if x != VW9_DEPLOYED]
    out += [Book("MC5-60", "MC5-60", "trail5", True),
            Book("MCL-60", "MCL-60", "trail5", True)]
    return out


# TL-60's scored book is the ENSEMBLE: the union of its three sleeves.
ENSEMBLES = {"TL-60": tuple(f"TL-60/sleeve-R{R}" for R in TL_PIVOTS)}
