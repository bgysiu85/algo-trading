#!/usr/bin/env python3
"""EXIT-CMP sec 6: the rule sets as small state machines. W15-0053 sub 2.

ONE CODE PATH. The backtest (strategy/exit_cmp/walk.py) and the live manager (sub 4) both drive these components the same way:

    comp.start()            once, at the close of the entry bar
    comp.levels(j)          sell-stops working for bar j, [(level, priority, tag)], from data <= j-1 ONLY
    comp.on_close(j)        at the close of bar j: update state for bar j+1; return a tag if the rule says
                            "market-sell at the next open", else None

Components never see a bar after the one being closed (tests/exitmgr/test_lookahead.py breaks each with a one-bar shift).
`b` is any object with float arrays o, h, l, c, atr, e9, e21, hist indexed by bar (the backtest passes the CHARTMARK frame and
indicators; the manager passes the same arrays built from IBKR bars). Long only; a short is the mirror and is unit-tested
in sub 4. Nothing here is tuned: every number is REGISTERED_exit_cmp.md sec 6.

Interpretations fixed before any outcome (PRE-RUN, listed in the handover):
  I1  "highest high since entry" includes the entry bar's own high: a buy-stop fill happens at the first touch of the level,
      so the bar's high was reached at or after the fill. Anything computed from it works from the NEXT bar.
  I2  M1 (three red bars) uses only bars after the entry bar: bars j-2..j must all be > entry bar.
  I3  X-ALERT: the level working in bar j is the line projected from the state after bar j-1 (pivots confirmed <= j-1), and it is
      eligible only while below close[j-1]. X-ALERT-close fires at the close of j when close[j] < that same level - buf x ATR[j].
  I4  X-JUMP: a swing low is bar i with low[i] < the lows of the L bars either side (strict); confirmed at the close of bar i+L;
      only swings with i after the arming bar are used; the stop moves to low[i] - 1 tick only if that is above the entry price.
  I5  X-JUMP-1R-half: once X-JUMP has armed, the R-BEN half-profit ratchet also applies (stop = max of both).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Level = tuple[float, int, str]          # (sell-stop price, tie priority, tag)
NAN = math.nan
EPS = 1e-9                       # prices carry float noise from the back-adjustment; thresholds are compared with this slack

# CHARTMARK-v1 constants (strategy.chartmark.spec) -- the manager must not import strategy/, so they are mirrored here and
# tests/exitmgr/test_rules.py asserts they equal the originals.
V1_P1_ARM, V1_P2_ARM = 1.0, 2.0
V1_R_WICK, V1_R_MIN_RANGE, V1_R_LIFE = 0.5, 0.3, 3

RULES = ("B-STOP", "B-V1", "R-BEN", "R-MOM", "X-ALERT-touch", "X-ALERT-close", "X-JUMP")
VARIANTS = ("R-BEN-EMA", "R-MOM+BEN", "X-JUMP-1R-half")
SCORED = ("R-BEN", "R-MOM", "X-ALERT-touch", "X-ALERT-close", "X-JUMP")


@dataclass(frozen=True)
class Params:
    ben_arm: float = 0.20          # price distance (CL / MCL $/bbl); symbols.arm_distance() for other symbols
    ben_frac: float = 0.50
    mom_run: int = 3
    mom_wick: float = 0.50
    mom_min_range: float = 0.30
    mom_life: int = 3
    al_L: int = 5                  # pivot L = R
    al_buf: float = 0.10           # x ATR, both the line's break and the close-alert buffer
    jump_arm: float = 1.0          # x R0
    jump_L: int = 2


BASE = Params()


class Comp:
    """Base. `fired` collects trigger names for the G6 counts (no prices)."""

    def __init__(self, b, e: int, entry: float, a0: float, s0: float, tick: float):
        self.b, self.e, self.entry, self.a0, self.s0, self.tick = b, e, entry, a0, s0, tick
        self.fired: set[str] = set()

    def start(self) -> None:
        pass

    def levels(self, j: int) -> list[Level]:
        return []

    def on_close(self, j: int):
        return None


class Floor(Comp):
    """S: the initial stop, a resting floor that is never loosened (every rule set keeps it)."""

    def levels(self, j):
        return [(self.s0, 0, "S")]


class EmaTrail(Comp):
    """CHARTMARK-v1 P1 (EMA9 once travelled >= 1.0 A0) and P2 (EMA21 at >= 2.0 A0). Port of engine.run_position."""

    def __init__(self, *a):
        super().__init__(*a)
        self.maxc, self.phase = self.b.c[self.e], 0

    def levels(self, j):
        if self.phase >= 1:
            ema = self.b.e21 if self.phase == 2 else self.b.e9
            lv = ema[j - 1]
            if lv == lv:
                return [(lv, 1, "P2" if self.phase == 2 else "P1")]
        return []

    def on_close(self, j):
        self.maxc = max(self.maxc, self.b.c[j])
        trav = (self.maxc - self.entry) / self.a0
        if trav >= V1_P1_ARM:
            self.phase = max(self.phase, 1)
        if trav >= V1_P2_ARM:
            self.phase = 2
        if self.phase:
            self.fired.add("ema_trail")
        return None


class Reversal(Comp):
    """Reversal-candle exit: long upper wick on a range >= min_range x A0 -> sell-stop at the body low - 1 tick, live `life`
    bars. v1 R (tag 'R') and R-MOM M2 (tag 'M2') are this class with different tags/parameters."""

    def __init__(self, *a, wick=V1_R_WICK, min_range=V1_R_MIN_RANGE, life=V1_R_LIFE, tag="R"):
        super().__init__(*a)
        self.wick, self.min_range, self.life, self.tag = wick, min_range, life, tag
        self.orders: list[tuple[float, int]] = []

    def levels(self, j):
        return [(lv, 2, self.tag) for lv, last in self.orders if last >= j]

    def on_close(self, j):
        b = self.b
        rng = b.h[j] - b.l[j]
        wick = b.h[j] - max(b.o[j], b.c[j])
        if rng > 0 and wick >= self.wick * rng and rng >= self.min_range * self.a0:
            self.orders.append((min(b.o[j], b.c[j]) - self.tick, j + self.life))
            self.fired.add("m2_placed" if self.tag == "M2" else "reversal")
        return None


class RedRun(Comp):
    """M1: the last `run` closes are each below their own open AND MACD histogram < 0 -> market sell at the next open (I2)."""

    def __init__(self, *a, run=3):
        super().__init__(*a)
        self.run = run

    def on_close(self, j):
        b = self.b
        if j - (self.run - 1) <= self.e:
            return None
        h = b.hist[j]
        if not h < 0:
            return None
        for k in range(j - self.run + 1, j + 1):
            if not b.c[k] < b.o[k]:
                return None
        self.fired.add("m1")
        return "M1"


class Ratchet(Comp):
    """R-BEN: once highest high since entry >= entry + arm, stop = max(stop, entry + frac x (highest high - entry)), recomputed
    at each close, effective from the next bar, never loosened (I1)."""

    def __init__(self, *a, arm=0.20, frac=0.50):
        super().__init__(*a)
        self.arm, self.frac = arm, frac
        self.hh, self.stop = self.b.h[self.e], -math.inf
        self.force = False                    # I5: X-JUMP-1R-half arms it from outside

    def _eval(self):
        if self.hh - self.entry >= self.arm - EPS or self.force:
            self.fired.add("ratchet_armed")
            self.stop = max(self.stop, self.entry + self.frac * (self.hh - self.entry))

    def start(self):
        self._eval()

    def levels(self, j):
        return [(self.stop, 1, "RATCHET")] if self.stop > -math.inf else []

    def on_close(self, j):
        self.hh = max(self.hh, self.b.h[j])
        self._eval()
        return None


class AlertTouch(Comp):
    """X-ALERT-touch: sell-stop at the support line's projected level while it is below the prior close (I3)."""

    def __init__(self, *a, proj):
        super().__init__(*a)
        self.proj = proj                      # proj[k] = level for bar k+1 from state after bar k (exitmgr.lines.track)

    def levels(self, j):
        p = self.proj[j - 1]
        if p == p:
            self.fired.add("line_active")
            if p < self.b.c[j - 1]:
                return [(p, 1, "ALERT")]
        return []


class AlertClose(Comp):
    """X-ALERT-close: close[j] < level - buf x ATR[j] -> market sell at the next open (I3)."""

    def __init__(self, *a, proj, buf=0.10):
        super().__init__(*a)
        self.proj, self.buf = proj, buf

    def on_close(self, j):
        p = self.proj[j - 1]
        if p == p:
            self.fired.add("line_active")
            b = self.b
            if p < b.c[j - 1] and b.c[j] < p - self.buf * b.atr[j]:
                self.fired.add("alert_fired")
                return "ALERT"
        return None


class Jump(Comp):
    """X-JUMP (I4). R0 = entry - S. Arms when the highest high >= entry + arm x R0; then each confirmed swing low (formed after
    the arming bar) above the entry price moves the stop to swing low - 1 tick; never loosens."""

    def __init__(self, *a, arm=1.0, L=2, ratchet: Ratchet | None = None):
        super().__init__(*a)
        self.arm, self.L, self.ratchet = arm, L, ratchet
        self.r0 = self.entry - self.s0
        self.hh, self.armed_at, self.stop = self.b.h[self.e], None, -math.inf

    def _arm_check(self, j):
        if self.armed_at is None and self.hh - self.entry >= self.arm * self.r0 - EPS:
            self.armed_at = j
            self.fired.add("jump_armed")
            if self.ratchet is not None:
                self.ratchet.force = True

    def start(self):
        self._arm_check(self.e)

    def levels(self, j):
        return [(self.stop, 1, "JUMP")] if self.stop > -math.inf else []

    def on_close(self, j):
        b, L = self.b, self.L
        self.hh = max(self.hh, b.h[j])
        self._arm_check(j)
        if self.armed_at is not None:
            i = j - L
            if i > self.armed_at and i - L >= 0:
                lo = b.l[i]
                if all(lo < b.l[k] for k in range(i - L, i)) and all(lo < b.l[k] for k in range(i + 1, i + L + 1)):
                    cand = lo - self.tick
                    if cand > self.entry and cand > self.stop:
                        self.stop = cand
                        self.fired.add("swing_used")
        return None


def build(rule_id: str, b, e: int, entry: float, a0: float, s0: float, tick: float, p: Params = BASE, proj=None) -> list[Comp]:
    """The components of one rule set for one trade. `proj` is the X-ALERT projected-level array for (p.al_L, p.al_buf)."""
    a = (b, e, entry, a0, s0, tick)
    fl = Floor(*a)
    if rule_id == "B-STOP":
        return [fl]
    if rule_id == "B-V1":
        return [fl, EmaTrail(*a), Reversal(*a)]
    if rule_id == "R-BEN":
        return [fl, Ratchet(*a, arm=p.ben_arm, frac=p.ben_frac)]
    if rule_id == "R-BEN-EMA":
        return [fl, Ratchet(*a, arm=p.ben_arm, frac=p.ben_frac), EmaTrail(*a)]
    if rule_id == "R-MOM":
        return [fl, RedRun(*a, run=p.mom_run),
                Reversal(*a, wick=p.mom_wick, min_range=p.mom_min_range, life=p.mom_life, tag="M2")]
    if rule_id == "R-MOM+BEN":
        return [fl, RedRun(*a, run=p.mom_run),
                Reversal(*a, wick=p.mom_wick, min_range=p.mom_min_range, life=p.mom_life, tag="M2"),
                Ratchet(*a, arm=p.ben_arm, frac=p.ben_frac)]
    if rule_id == "X-ALERT-touch":
        return [fl, AlertTouch(*a, proj=proj)]
    if rule_id == "X-ALERT-close":
        return [fl, AlertClose(*a, proj=proj, buf=p.al_buf)]
    if rule_id == "X-JUMP":
        return [fl, Jump(*a, arm=p.jump_arm, L=p.jump_L)]
    if rule_id == "X-JUMP-1R-half":
        r = Ratchet(*a, arm=math.inf, frac=p.ben_frac)         # armed only from outside
        return [fl, Jump(*a, arm=p.jump_arm, L=p.jump_L, ratchet=r), r]      # Jump first: it arms the ratchet in the same bar
    raise KeyError(rule_id)
