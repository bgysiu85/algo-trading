#!/usr/bin/env python3
"""The bar-by-bar position walk: one sleeve, one market, daily bars.

REGISTERED_tl_v0 sections 2.1-2.2, in the order Pine's TL_v0.pine walks a bar
(the G3 reference), extended for v0-rev and the controls:

  A. a pending EXIT (v0-rev reversal / blocked reversal) fills at this open;
     if the open is already through the resting stop it is booked as a stop
     fill (with the tick of slippage) -- the resting order would have filled
     first
  B. a pending ENTRY fills at this open -- VOIDED (counted, not taken) if the
     open is already beyond its stop; sized from the actual fill:
     contracts = floor(risk $ / (|open - stop| x multiplier)); ZERO = SKIP,
     counted (integer sizing); fractional sizing never skips
  C. the resting stop, active from the entry bar: filled at the stop, or at
     the open if the bar opened through it; one tick of slippage on every
     stop fill (charged by pnl.py)
  D. the trail, at this close, applied from the next bar, never loosens,
     only if the new level is on the right side of the close
  E. signals at this close -> orders for the next open
  F. the last bar: an open position is closed at its close ("data_end")

The walk works on the BACK-ADJUSTED signal series only. It never sees a raw
price or a dollar except the sizing multiplier; pnl.py books the result on the
held contract.

THE THREE RULE SHAPES
---------------------
  rule="ignore"   v0, C2 and C1: while in a position every break is ignored
                  (counted); only the stop exits.
  rule="reverse"  v0-rev: an OPPOSITE break exits at the next open and
                  reverses if the weekly filter allows the new side; if it
                  does not, the position is simply closed (counted as
                  reversal_blocked_flat). A same-side break is ignored.
  chandelier_k    C2: stop = highest high (lowest low) since the signal bar
                  -/+ k x ATR(14), ratcheting, instead of the safety line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Trade:
    direction: int          # +1 long, -1 short
    entry_j: int
    exit_j: int
    entry_px: float         # back-adjusted
    exit_px: float          # back-adjusted, before slippage
    stop_init: float
    qty: float
    reason: str             # stop | stop_gap | reverse | flat_blocked | data_end
    stop_fill: bool         # a stop fill -> one tick of slippage


@dataclass
class Counts:
    breaks: int = 0
    signals: int = 0            # orders placed while flat (+ reversal orders)
    htf_blocked: int = 0
    ignored_in_position: int = 0
    reversals: int = 0
    reversal_blocked_flat: int = 0
    voided: int = 0
    skipped_size: int = 0
    no_stop: int = 0
    unfilled_at_end: int = 0
    entries: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class SimInput:
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    up: np.ndarray
    dn: np.ndarray
    htf: np.ndarray | None          # None = no top-down filter (C1)
    init_long: np.ndarray           # initial stop LEVEL for a long ordered at close j
    init_short: np.ndarray
    trail_long: np.ndarray          # trail candidate at close j (NaN = none)
    trail_short: np.ndarray
    atr: np.ndarray | None = None
    chandelier_k: float | None = None


@dataclass
class SimResult:
    trades: list = field(default_factory=list)
    counts: Counts = field(default_factory=Counts)


def _size(risk_usd: float, dist: float, mult: float, integer: bool) -> float:
    if not (dist > 0) or not np.isfinite(dist):
        return 0.0
    q = risk_usd / (dist * mult)
    return float(np.floor(q + 1e-12)) if integer else float(q)


def simulate(x: SimInput, *, rule: str, mult: float, risk_usd: float,
             integer: bool) -> SimResult:
    if rule not in ("ignore", "reverse"):
        raise ValueError(rule)
    o, h, lo, c = x.o, x.h, x.l, x.c
    n = len(c)
    res = SimResult()
    k = res.counts

    pos = 0
    stop = np.nan
    entry_j = -1
    entry_px = np.nan
    stop_init = np.nan
    qty = 0.0
    ext = np.nan                     # chandelier: highest high / lowest low since signal
    pend_entry = None                # (dir, stop, ext_seed)
    pend_exit = None                 # reason

    def close(j, px, reason, stop_fill):
        nonlocal pos, stop, qty
        res.trades.append(Trade(pos, entry_j, j, entry_px, px, stop_init, qty, reason, stop_fill))
        pos, stop, qty = 0, np.nan, 0.0

    for j in range(n):
        # A. pending exit at this open
        if pend_exit is not None and pos != 0:
            through = (pos == 1 and o[j] <= stop) or (pos == -1 and o[j] >= stop)
            close(j, o[j], "stop_gap" if through else pend_exit, through)
        pend_exit = None

        # B. pending entry at this open
        if pend_entry is not None:
            d, pst, seed = pend_entry
            pend_entry = None
            if (d == 1 and o[j] <= pst) or (d == -1 and o[j] >= pst):
                k.voided += 1
            else:
                q = _size(risk_usd, abs(o[j] - pst), mult, integer)
                if q <= 0:
                    k.skipped_size += 1
                else:
                    pos, stop, stop_init, qty = d, pst, pst, q
                    entry_j, entry_px, ext = j, o[j], seed
                    k.entries += 1

        # C. resting stop (includes the entry bar)
        if pos == 1 and lo[j] <= stop:
            close(j, min(o[j], stop), "stop" if o[j] > stop else "stop_gap", True)
        elif pos == -1 and h[j] >= stop:
            close(j, max(o[j], stop), "stop" if o[j] < stop else "stop_gap", True)

        # F. last bar: nothing can be ordered for a next bar
        if j == n - 1:
            if pos != 0:
                close(j, c[j], "data_end", False)
            if x.up[j] or x.dn[j]:
                k.breaks += 1
                k.unfilled_at_end += 1
            break

        # D. trail at this close
        if pos != 0:
            if x.chandelier_k is not None:
                if pos == 1:
                    ext = max(ext, h[j])
                    cand = ext - x.chandelier_k * x.atr[j]
                else:
                    ext = min(ext, lo[j])
                    cand = ext + x.chandelier_k * x.atr[j]
            else:
                cand = x.trail_long[j] if pos == 1 else x.trail_short[j]
            if np.isfinite(cand):
                if pos == 1 and cand < c[j]:
                    stop = max(stop, cand)
                elif pos == -1 and cand > c[j]:
                    stop = min(stop, cand)

        # E. signals at this close
        up, dn = bool(x.up[j]), bool(x.dn[j])
        if not (up or dn):
            continue
        k.breaks += int(up) + int(dn)

        def order(d):
            if x.chandelier_k is not None:
                seed = h[j] if d == 1 else lo[j]
                st = seed - x.chandelier_k * x.atr[j] if d == 1 else seed + x.chandelier_k * x.atr[j]
            else:
                seed = np.nan
                st = x.init_long[j] if d == 1 else x.init_short[j]
            if not np.isfinite(st) or (d == 1 and st >= c[j]) or (d == -1 and st <= c[j]):
                k.no_stop += 1
                return None
            return (d, st, seed)

        def allowed(d):
            return x.htf is None or x.htf[j] == d

        if pos == 0:
            d = 1 if up else -1                      # Pine: if upBrk ... else if dnBrk
            if allowed(d):
                pe = order(d)
                if pe is not None:
                    pend_entry = pe
                    k.signals += 1
            else:
                k.htf_blocked += 1
            # the other side of a two-way bar is not acted on (Pine)
            continue

        opposite = (pos == 1 and dn) or (pos == -1 and up)
        if rule == "ignore" or not opposite:
            k.ignored_in_position += int(up) + int(dn)
            continue
        # v0-rev: opposite break -> exit at next open, reverse if allowed
        d = -pos
        if allowed(d):
            pe = order(d)
            if pe is not None:
                pend_exit, pend_entry = "reverse", pe
                k.reversals += 1
                k.signals += 1
            else:
                pend_exit = "flat_blocked"
                k.reversal_blocked_flat += 1
        else:
            pend_exit = "flat_blocked"
            k.reversal_blocked_flat += 1
            k.htf_blocked += 1
    return res
