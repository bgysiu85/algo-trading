#!/usr/bin/env python3
"""TL-v2 retest scan: REGISTERED_tl_v2.md sec 2.2 (T1-T5) and sec 2.3 (S/R variant). Board: W15-0030.

A pure walk over arrays. It reads NO exit price and computes NO P&L; it only decides, bar by bar,
which qualified breaks turn into a retest ENTRY SIGNAL (at the close of retest bar s; the order fills
at the open of s+1, which the simulator does) and which do not, and why.

WHAT IS FROZEN
--------------
At a qualified break at bar t (TL-v1's E1 break of the sec 2.2 line, passing A1-A3 and the weekly
filter E2, all evaluated AT t) the broken line is frozen: value line[t], per-bar slope taken from
its own anchor A (line passes through A's pivot value), projected forward flat in slope:
    line_s = line[t] + slope * (s - t)
Nothing that happens after t can change it (guard test: prefix invariance).

THE RULES (long shown; short is the mirror)
--------------------------------------------
  T1 retest   low[s]   <= line_s + RETEST_BUF * ATR[s]      (0.25, the A1 touch buffer)
  T2 holds    close[s] >= line_s - HOLD_BUF   * ATR[s]      (0.10, the break buffer)
  T3 fail     a close through the line (close < line - 0.10 ATR) at any bar t+1.. before a retest
              bar, or the OPPOSITE raw break at any bar t+1..  -> setup dead, counted "failed"
  T4 timeout  no retest bar by t+N (N = 10)                  -> counted "no_retest"
  T5 entry    the first bar s meeting T1 and T2 -> signal at s's close (fill at s+1's open).
              The setup is used once and the line is never re-armed.

Bar s's own high/low/close are used for T1/T2 (they are known at s's close); the fill is at s+1's
open. A one-bar shift of either is what the guard tests break.

CODING CHOICES WHERE THE REGISTRATION IS SILENT (PRE-RUN; no result exists; see the handover)
---------------------------------------------------------------------------------------------
  C1. One live setup per market. While a setup is pending, a further qualified break in the SAME
      direction is ignored and counted ("ignored_pending"); the first setup keeps its frozen line.
      (An opposite qualified break is an opposite raw break, which kills the pending setup by T3
      and starts its own.)
  C2. On a bar where a raw opposite break and a retest coincide, the opposite break wins (T3).
  C3. A bar that closes through the line is a failure (T3) even if no retest bar came before it
      (it can never be a T2-holding retest bar).
  C4. A retest on the LAST bar cannot be filled: counted "open_at_end", not an entry.
  C5. S/R zone: pivots of the SAME KIND as the pivots that drew the broken line (highs for a
      resistance break), L = R = 5, confirmed before t (confirm bar < t), pivot bar in the 250 bars
      before t. A zone = >= 2 such pivots whose prices lie within 0.25 x ATR[t] of each other; the
      zone passes if its mean is within 0.5 x ATR[s] of line_s. Any qualifying zone passes. The S/R
      variant only FILTERS the T5 entry (the first retest bar); a setup whose first retest bar has
      no zone is used up, not carried to a later bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.tl_v1_lines import CROSS_BUFFER, TOUCH_BUFFER

RETEST_N = 10
RETEST_BUF = TOUCH_BUFFER          # 0.25 x ATR  (T1)
HOLD_BUF = CROSS_BUFFER            # 0.10 x ATR  (T2, T3)
SR_R = 5
SR_WINDOW = 250
SR_MIN_PIVOTS = 2
SR_CLUSTER_ATR = 0.25
SR_NEAR_ATR = 0.5

OUTCOMES = ("entry", "failed", "no_retest", "open_at_end", "ignored_pending")


@dataclass
class Side:
    """One direction's arrays. direction +1 = long (a resistance line broken upward)."""
    direction: int
    raw: np.ndarray              # E1 raw break at t (any line break; used for T3 and exits)
    qual: np.ndarray             # qualified break at t: raw & A1-A3 & weekly filter (E2)
    line: np.ndarray             # broken-line value per bar
    anchor: np.ndarray           # anchor bar A per bar (-1 none)
    ext: np.ndarray              # the series the anchor's pivot value is read from (high for res, low for sup)
    sr_pivots: list = field(default_factory=list)   # [(pivot_idx, confirm_idx, value)] R=5, same kind


@dataclass
class RetestScan:
    ent_up: np.ndarray           # entry signal at the close of this bar (long)
    ent_dn: np.ndarray
    sr_up: np.ndarray            # ... and the S/R zone coincided at that bar
    sr_dn: np.ndarray
    events: pd.DataFrame         # one row per qualified break (+ ignored ones), see EVENT_COLS


EVENT_COLS = ("t", "direction", "outcome", "why", "s", "bars_to_retest", "line_t", "sr_ok")


def frozen_slope(line_t: float, anchor_bar: int, anchor_value: float, t: int) -> float:
    """Per-bar slope of the line through the anchor's pivot value and line[t]."""
    return (line_t - anchor_value) / (t - anchor_bar)


def sr_zone_ok(side: Side, t: int, s: int, line_s: float, atr: np.ndarray) -> bool:
    """C5. Uses only pivots confirmed before t and the ATRs of bars t and s."""
    cands = [v for (p, cidx, v) in side.sr_pivots if cidx < t and t - SR_WINDOW <= p < t]
    if len(cands) < SR_MIN_PIVOTS:
        return False
    width = SR_CLUSTER_ATR * atr[t]
    near = SR_NEAR_ATR * atr[s]
    for v0 in cands:
        grp = [v for v in cands if v0 <= v <= v0 + width]
        if len(grp) >= SR_MIN_PIVOTS and abs(float(np.mean(grp)) - line_s) <= near:
            return True
    return False


def scan(h: np.ndarray, l: np.ndarray, c: np.ndarray, atr: np.ndarray, up: Side, dn: Side, *,
         N: int = RETEST_N, buf: float = RETEST_BUF, hold_buf: float = HOLD_BUF) -> RetestScan:
    n = len(c)
    ent = {1: np.zeros(n, bool), -1: np.zeros(n, bool)}
    sr = {1: np.zeros(n, bool), -1: np.zeros(n, bool)}
    sides = {1: up, -1: dn}
    rows: list[dict] = []
    pend = None

    def row(**kw):
        base = dict(t=-1, direction=0, outcome="", why="", s=-1, bars_to_retest=np.nan,
                    line_t=np.nan, sr_ok=None)
        base.update(kw)
        rows.append(base)

    for j in range(n):
        if pend is not None and j > pend["t"]:
            d, t = pend["d"], pend["t"]
            opp = sides[-d].raw[j]
            lv = pend["line_t"] + pend["slope"] * (j - t)
            a = atr[j]
            through = (c[j] < lv - hold_buf * a) if d == 1 else (c[j] > lv + hold_buf * a)
            touched = (l[j] <= lv + buf * a) if d == 1 else (h[j] >= lv - buf * a)
            if opp:                                                   # T3, C2
                row(t=t, direction=d, outcome="failed", why="opposite_raw_break", line_t=pend["line_t"])
                pend = None
            elif through:                                             # T3, C3
                row(t=t, direction=d, outcome="failed", why="closed_through", line_t=pend["line_t"])
                pend = None
            elif touched:                                             # T1 + T2 -> T5
                if j == n - 1:                                        # C4
                    row(t=t, direction=d, outcome="open_at_end", why="retest_on_last_bar",
                        s=j, bars_to_retest=j - t, line_t=pend["line_t"])
                else:
                    ok = sr_zone_ok(sides[d], t, j, lv, atr)
                    ent[d][j] = True
                    sr[d][j] = ok
                    row(t=t, direction=d, outcome="entry", s=j, bars_to_retest=j - t,
                        line_t=pend["line_t"], sr_ok=bool(ok))
                pend = None
            elif j - t >= N:                                          # T4
                row(t=t, direction=d, outcome="no_retest", why="timeout", line_t=pend["line_t"])
                pend = None
        for d in (1, -1):                                             # up first, as TL-v1's sim does
            sd = sides[d]
            if not sd.qual[j]:
                continue
            if pend is not None:                                      # C1
                row(t=j, direction=d, outcome="ignored_pending", why="setup_already_pending",
                    line_t=float(sd.line[j]))
                continue
            pA = int(sd.anchor[j])
            if pA < 0 or not np.isfinite(sd.line[j]) or j <= pA:
                row(t=j, direction=d, outcome="failed", why="no_anchor", line_t=float(sd.line[j]))
                continue
            slope = frozen_slope(float(sd.line[j]), pA, float(sd.ext[pA]), j)
            pend = dict(d=d, t=j, line_t=float(sd.line[j]), slope=slope)
    if pend is not None:
        row(t=pend["t"], direction=pend["d"], outcome="open_at_end", why="data_end",
            line_t=pend["line_t"])
    ev = pd.DataFrame(rows, columns=list(EVENT_COLS))
    if len(ev):
        ev = ev.sort_values(["t", "direction"], ascending=[True, False]).reset_index(drop=True)
    return RetestScan(ent[1], ent[-1], sr[1] & ent[1], sr[-1] & ent[-1], ev)
