#!/usr/bin/env python3
"""The TL-bounce bar walk: entries (E1-E4), stop/trail (S1-S2), exit (X1).
REGISTERED_tl_bounce.md sec 2.2-2.3.

SCOPE: THIS IS G2's WALK, NOT THE FULL BACKTEST ENGINE
---------------------------------------------------------
sec 5.2: "No exit price is read and no P&L is computed; the runner refuses
both in this mode." This module tracks entry/exit BAR INDEX and the initial
stop LEVEL (a price, needed for sec 5.2's own stop-distance stats -- not a
P&L figure), never a $ result. It does not book dollars, so it has no
friction, no roll handling, and no held-contract conversion -- that is
strategy/tl_bounce/pnl.py's job, built alongside the full engine for
W15-0016 (the backtest item), not this one.

STOP TESTING IS AT ENTRY-CHART GRANULARITY HERE, NOT 1-HOUR
--------------------------------------------------------------
sec 2.3 "Fills" registers stop testing on 1-HOUR bars even for the 4-hour
entry chart (HTF-Ben v0 S3-S4's convention). Reproducing that exactly needs
a nested 1-hour walk inside each entry-chart bar, which changes ordering
between a touch and a stop test by up to ~3 hours -- consequential for
booked $ (W15-0016's job) but not, on a first-order basis, for G2's own
counts (touch bars, held, entries, re-entries). This walk tests the stop
against the ENTRY-CHART bar's own low/high instead, flagged here as a
documented approximation for review before the full engine (which DOES test
on 1-hour bars, per sec 2.3) replaces it -- not a silent substitution.

BOUNCE-ONCE (sec 2.5) IS APPROXIMATED AS "NO RE-ENTRY AT ALL", NOT "PER LINE"
--------------------------------------------------------------------------------
sec 2.5 registers bounce-once as "E4 off: one entry per line" (a second entry
is allowed once the active line's identity changes, e.g. a new pivot pair
re-arms it). walk_line_and_breaks (common/tl_v0_lines.py) does not expose a
line-identity id, only its current value, so re-arming to a genuinely new
pair cannot yet be told apart from the same line persisting. This walk
instead disables ALL re-entries for the run (`allow_reentry=False`) -- a
strictly narrower rule than registered, producing FEWER bounce-once entries
than the true variant would. Flagged for a line-identity id to be added to
lines.py before bounce-once's own numbers are read for real (does not block
the main "bounce" rule set or the other variants, which do not use E4-off).

BOUNCE-LIMIT (sec 2.5) IS NOT YET IMPLEMENTED
------------------------------------------------
Its E1/E2 are structurally different (a resting limit order at the touch
buffer, filling on the touch itself, before the close/hold is known) rather
than a toggle on this walk. Tracked separately; `variants.py` raises
NotImplementedError for it rather than silently returning zero entries.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from strategy.tl_bounce.spec import STOP_BUF
from strategy.tl_bounce.signals import Signals

TICK = 0.01   # CL/MCL price tick, $/bbl (E2's "1 tick" -- sec 2.3 S1)


@dataclass
class Entry:
    direction: int         # +1 long, -1 short
    entry_j: int
    exit_j: int | None      # None = still open at data end handled as data_end below
    stop_init: float
    exit_reason: str | None = None   # 'stop' | 'X1' | 'data_end'
    is_reentry: bool = False


@dataclass
class Counts:
    touch_bars: int = 0
    touch_long: int = 0
    touch_short: int = 0
    held: int = 0             # E1 met and (E0 allows and, if bounce-once, allowed) -> order queued
    e0_blocked: int = 0
    ignored_in_position: int = 0
    voided: int = 0
    entries: int = 0
    re_entries: int = 0
    exit_stop: int = 0
    exit_x1: int = 0
    exit_data_end: int = 0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _s1_long(sup_j, atr_j, lo_j):
    return min(sup_j - STOP_BUF * atr_j, lo_j - TICK)


def _s1_short(res_j, atr_j, hi_j):
    return max(res_j + STOP_BUF * atr_j, hi_j + TICK)


def simulate(s: Signals, *, e0_on: bool = True, x1_on: bool = True,
            allow_reentry: bool = True) -> tuple[list[Entry], Counts]:
    """Walk one market's entry-chart Signals. `e0_on`=False is the
    bounce-noE0 variant; `x1_on`=False is bounce-noX1 (exits via S1/S2
    only); `allow_reentry`=False is bounce-once (see module docstring for
    its narrower-than-registered scope)."""
    o, h, lo, c, a = s.o, s.h, s.l, s.c, s.atr
    sup, res = s.sup, s.res
    n = s.n
    entries: list[Entry] = []
    k = Counts()

    pos = 0
    stop = np.nan
    entry_j = -1
    stop_init = np.nan
    cur: Entry | None = None
    has_entered = False

    pend_entry: tuple[int, float] | None = None    # (direction, stop0)
    pend_exit = False                               # X1 fired at prior close

    def close_pos(j, reason):
        nonlocal pos, stop, cur
        cur.exit_j, cur.exit_reason = j, reason
        entries.append(cur)
        {"stop": lambda: setattr(k, "exit_stop", k.exit_stop + 1),
         "X1": lambda: setattr(k, "exit_x1", k.exit_x1 + 1),
         "data_end": lambda: setattr(k, "exit_data_end", k.exit_data_end + 1)}[reason]()
        pos, stop, cur = 0, np.nan, None

    for j in range(n):
        exited_this_bar = False

        # 1. pending X1 exit fills at this open
        if pend_exit and pos != 0:
            close_pos(j, "X1")
            exited_this_bar = True
        pend_exit = False

        # 2. pending entry fills / voids at this open
        if pend_entry is not None:
            d, s0 = pend_entry
            pend_entry = None
            voided = (d == 1 and o[j] <= s0) or (d == -1 and o[j] >= s0)
            if voided:
                k.voided += 1
            else:
                pos, stop, stop_init, entry_j = d, s0, s0, j
                is_re = has_entered
                cur = Entry(d, j, None, s0, is_reentry=is_re)
                has_entered = True
                k.entries += 1
                if is_re:
                    k.re_entries += 1

        # 3. resting stop test (entry-chart granularity -- see module docstring)
        if pos == 1 and lo[j] <= stop:
            close_pos(j, "stop")
            exited_this_bar = True
        elif pos == -1 and h[j] >= stop:
            close_pos(j, "stop")
            exited_this_bar = True

        last_bar = (j == n - 1)
        if last_bar and pos != 0:
            close_pos(j, "data_end")
            exited_this_bar = True

        # 4. trail (S2), only if still in position
        if pos != 0 and not np.isnan(a[j]):
            if pos == 1:
                line_ref = sup[j] if not np.isnan(sup[j]) else np.inf
                cand = min(s.swing_low[j], line_ref) - STOP_BUF * a[j]
                if np.isfinite(cand) and cand < c[j]:
                    stop = max(stop, cand)
            else:
                line_ref = res[j] if not np.isnan(res[j]) else -np.inf
                cand = max(s.swing_high[j], line_ref) + STOP_BUF * a[j]
                if np.isfinite(cand) and cand > c[j]:
                    stop = min(stop, cand)

        # 5. touches at this close
        tl, ts = bool(s.touch_long[j]), bool(s.touch_short[j])
        if tl or ts:
            k.touch_bars += 1
            k.touch_long += int(tl)
            k.touch_short += int(ts)

        if pos == 0 and not exited_this_bar and not last_bar:
            e0_dir = None if s.e0 is None or not e0_on else s.e0[j]
            took = False
            if tl and not np.isnan(sup[j]):
                if allow_reentry or not has_entered:
                    if e0_dir is None or e0_dir == 1:
                        s0 = _s1_long(sup[j], a[j], lo[j])
                        pend_entry = (1, s0)
                        k.held += 1
                        took = True
                    elif e0_dir is not None:
                        k.e0_blocked += 1
            if not took and ts and not np.isnan(res[j]):
                if allow_reentry or not has_entered:
                    if e0_dir is None or e0_dir == -1:
                        s0 = _s1_short(res[j], a[j], h[j])
                        pend_entry = (-1, s0)
                        k.held += 1
                    elif e0_dir is not None:
                        k.e0_blocked += 1
        elif pos != 0 and (tl or ts):
            k.ignored_in_position += 1

        # 6. X1 signal at this close (queued for next bar's open)
        if pos != 0 and x1_on:
            fires = (pos == 1 and s.sup_breaks[j]) or (pos == -1 and s.res_breaks[j])
            if fires:
                pend_exit = True

        if last_bar:
            break

    return entries, k
