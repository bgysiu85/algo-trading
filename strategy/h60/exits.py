#!/usr/bin/env python3
"""The ONE exit implementation for H60 -- rule trades, random-entry controls
and the positive control all go through `simulate`. W14-0003,
REGISTERED_h60_v0.md §2.3.

Vectorised over entries: every candidate entry of one symbol is walked
forward together, one bar-step at a time, so a whole symbol's worth of
candidates (or every (symbol, bar) pair a random control can draw) costs one
loop of at most (cap_sessions + 1) x 7 steps.

ORDER OF EVENTS INSIDE A BAR -- the pessimistic branch first
------------------------------------------------------------
1. OPEN.  A close-decided exit from the previous bar (DON's channel, VW9's
          VWAP-lost, ...) fills at this bar's open. §2.2: a decision taken on
          a bar can first be acted on at the next bar's open.
2. INTRABAR, stop first. The resting stop level is the highest of the
          active stops (fixed / trail / safety line / ATR trail). If the low
          reaches it the fill is min(level, open) -- a bar that OPENS through a
          stop fills at the open, never at the level (gap_fills=True).
          The trail is derived from the peak as of the PREVIOUS bar and tested
          against this bar's low (MCL's exit modelling, unchanged); the peak
          is seeded from the fill price, never the fill bar's high.
3. INTRABAR, target second. A resting limit sell at the target fills AT
          the target -- also when the bar opens above it. A limit would get
          the better open in practice; booking it would be the optimistic
          branch, and VW9's source (strategy/vw9/backtest.py) fills at the
          level. A bar that reaches both resolves as the stop.
4. CLOSE. The time cap: exit at the close of the last bar of the fifth
          session after the entry session. If the symbol's bars stop before
          that (a delisting, an index exit, a data gap across the cap) the
          last bar it has at or before the cap is the exit (§12).
5. CLOSE. A close-decided exit signal on this bar is queued for step 1 of
          the next bar.

Prices here are RAW PRINTS. No tick of slippage is added: friction is charged
separately and in dollars by costs.py at three levels (§2.4), and adding a
tick here too would charge it twice.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from strategy.h60.panel import NB, SymArrays

# reason codes
R_SIGNAL, R_STOP, R_TRAIL, R_SAFETY, R_TRAIL_ATR, R_TARGET, R_TIME, R_DATA_END, R_DATA_GAP = range(9)
REASONS = ("signal_exit", "stop", "trail", "safety_line", "trail_atr", "target",
           "time_cap", "data_end", "data_gap")
# engine.py relabels a data_end that is only the end of a SEGMENT (the series
# resumes later, after a membership gap or under another code) as this
SEGMENT_END = "segment_end"
STOP_REASONS = (R_STOP, R_TRAIL, R_SAFETY, R_TRAIL_ATR)

PH_OPEN, PH_INTRA, PH_CLOSE = 0, 1, 2
CAP_SESSIONS = 5


@dataclass(frozen=True)
class ExitSpec:
    """Which exits are live. Every field off by default; a rule turns on its
    own. `cap_sessions` is §2.3's five-session cap (0 = the entry session's
    own close, used by the positive control)."""
    trail_pct: float | None = None
    trail_atr: float | None = None
    fixed_stop: bool = False
    target_r: float | None = None
    close_exit: bool = False
    ratchet: bool = False
    cap_sessions: int = CAP_SESSIONS

    def window(self) -> int:
        return (self.cap_sessions + 1) * NB


@dataclass
class ExitResult:
    fill_idx: np.ndarray
    fill_px: np.ndarray
    exit_idx: np.ndarray
    exit_px: np.ndarray
    phase: np.ndarray
    reason: np.ndarray
    void: np.ndarray            # opened at or beyond its own stop: no trade

    @property
    def stop_fill(self) -> np.ndarray:
        return np.isin(self.reason, STOP_REASONS)


def simulate(a: SymArrays, fill_idx, spec: ExitSpec, *, fixed_stop=None,
             xsig=None, ratchet=None, atr_prev=None) -> ExitResult:
    """Walk every entry in `fill_idx` (indices into `a`, the bar whose OPEN is
    the fill) to its exit.

    fixed_stop  per-entry resting stop (ORB's range low, VW9's structure
                stop, TL's initial stop). Required iff spec.fixed_stop.
    xsig        per-BAR bool: an exit decided at that bar's close.
    ratchet     per-BAR stop candidate computed at that bar's close (NaN when
                none); the live level is the running max from the fill bar
                on, applied from the NEXT bar, and it never loosens.
    atr_prev    per-BAR ATR as of the PREVIOUS bar's close (the ATR trail's
                width is never read from the bar it is tested against).
    """
    fill = np.asarray(fill_idx, dtype=np.int64)
    m = len(fill)
    n = a.n
    if m == 0:
        z = np.zeros(0)
        zi = np.zeros(0, dtype=np.int64)
        return ExitResult(zi, z, zi, z, zi, zi, np.zeros(0, bool))
    if (fill < 0).any() or (fill >= n).any():
        raise IndexError("fill index outside the symbol's bars")
    if spec.fixed_stop and fixed_stop is None:
        raise ValueError("spec.fixed_stop needs per-entry fixed_stop")
    if spec.close_exit and xsig is None:
        raise ValueError("spec.close_exit needs a per-bar xsig")
    if spec.ratchet and ratchet is None:
        raise ValueError("spec.ratchet needs a per-bar ratchet")
    if spec.trail_atr is not None and atr_prev is None:
        raise ValueError("spec.trail_atr needs atr_prev")

    o, h, l, c, s = a.o, a.h, a.l, a.c, a.s
    fill_px = o[fill].copy()
    cap_s = s[fill] + spec.cap_sessions
    fstop = (np.asarray(fixed_stop, float) if spec.fixed_stop
             else np.full(m, -np.inf))
    target = (fill_px + spec.target_r * (fill_px - fstop)
              if spec.target_r is not None else np.full(m, np.inf))

    # VOID: a position whose fill is at or below a stop it already carries
    # was never holdable -- counted by the caller, never booked (TL-v0 §3.8).
    void = fill_px <= fstop

    peak = fill_px.copy()
    rat = np.full(m, -np.inf)
    pend = np.zeros(m, bool)
    done = void.copy()
    exit_idx = np.full(m, -1, dtype=np.int64)
    exit_px = np.full(m, np.nan)
    phase = np.full(m, -1, dtype=np.int64)
    reason = np.full(m, -1, dtype=np.int64)

    def book(mask, j, px, ph, rc):
        exit_idx[mask] = j[mask]
        exit_px[mask] = px[mask]
        phase[mask] = ph
        reason[mask] = rc
        done[mask] = True

    for k in range(spec.window() + 1):
        live = ~done
        if not live.any():
            break
        j = fill + k
        inb = j < n
        if (live & ~inb).any():               # pragma: no cover - the close
            raise AssertionError("walked past the last bar without an exit")
        jj = np.where(inb, j, n - 1)

        # 1. OPEN -- a queued close-decided exit
        hit = live & pend
        if hit.any():
            book(hit, jj, o[jj], PH_OPEN, R_SIGNAL)
        live = ~done

        # 2. INTRABAR -- the resting stop, the highest of those in force
        lvl = fstop.copy()
        why = np.full(m, R_STOP)
        if spec.trail_pct is not None:
            t = peak * (1.0 - spec.trail_pct / 100.0)
            up = t > lvl
            lvl, why = np.where(up, t, lvl), np.where(up, R_TRAIL, why)
        if spec.trail_atr is not None:
            t = peak - spec.trail_atr * atr_prev[jj]
            up = t > lvl
            lvl, why = np.where(up, t, lvl), np.where(up, R_TRAIL_ATR, why)
        if spec.ratchet:
            up = rat > lvl
            lvl, why = np.where(up, rat, lvl), np.where(up, R_SAFETY, why)
        hit = live & (l[jj] <= lvl)
        if hit.any():
            px = np.minimum(lvl, o[jj])
            exit_idx[hit] = jj[hit]
            exit_px[hit] = px[hit]
            phase[hit] = np.where(o[jj] <= lvl, PH_OPEN, PH_INTRA)[hit]
            reason[hit] = why[hit]
            done[hit] = True
        live = ~done

        # 3. INTRABAR -- the resting target
        if spec.target_r is not None:
            hit = live & (h[jj] >= target)
            if hit.any():
                exit_idx[hit] = jj[hit]
                exit_px[hit] = target[hit]
                phase[hit] = np.where(o[jj] >= target, PH_OPEN, PH_INTRA)[hit]
                reason[hit] = R_TARGET
                done[hit] = True
            live = ~done

        # 4. CLOSE -- the time cap, or the last bar the symbol has
        nxt = np.minimum(jj + 1, n - 1)
        is_last = jj == n - 1
        beyond = is_last | (s[nxt] > cap_s)
        hit = live & beyond
        if hit.any():
            rc = np.where(s[jj] >= cap_s, R_TIME,
                          np.where(is_last, R_DATA_END, R_DATA_GAP))
            exit_idx[hit] = jj[hit]
            exit_px[hit] = c[jj][hit]
            phase[hit] = PH_CLOSE
            reason[hit] = rc[hit]
            done[hit] = True
        live = ~done

        # 5. CLOSE -- queue a close-decided exit for the next open
        if spec.close_exit:
            pend = live & xsig[jj]

        # after the bar: the peak and the safety line move for the NEXT bar
        peak = np.where(live, np.maximum(peak, h[jj]), peak)
        if spec.ratchet:
            r = ratchet[jj]
            ok = live & ~np.isnan(r)
            rat = np.where(ok, np.maximum(rat, r), rat)

    if not done.all():                         # pragma: no cover
        raise AssertionError("an entry left the window without an exit")
    return ExitResult(fill, fill_px, exit_idx, exit_px, phase, reason, void)


def exit_mark(a: SymArrays, res: ExitResult) -> np.ndarray:
    """Global basket mark of each exit: the bar's open for an open fill, its
    close for an intrabar or close fill (panel.py, GLOBAL CLOCK)."""
    idx = np.where(res.exit_idx < 0, 0, res.exit_idx)
    return 2 * a.g[idx] + np.where(res.phase == PH_OPEN, 0, 1)


def entry_mark(a: SymArrays, res: ExitResult) -> np.ndarray:
    return 2 * a.g[res.fill_idx]
