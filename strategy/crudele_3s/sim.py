#!/usr/bin/env python3
"""The CRUDELE-3S position walk: one market, one sizing, the three arms (sec 2.4).

Bar j is walked in the order the TL-v0 sim uses (strategy/tl_v0/sim.py), extended for targets:

  A. a pending EXIT (rule exit decided at the previous close) fills at this open; if the open is
     already through the resting stop it is booked as a stop fill (with the tick of slippage)
  B. a pending ENTRY fills at this open. VOIDED, counted, when the open is already beyond the
     initial stop (the trade would be stopped at once) or, for MR and C, already through the target.
     Sized from the actual fill: qty = risk $ / (|open - stop| x mult); fractional never skips,
     integer floors and ZERO = SKIP, counted.
  C. resting orders inside bar j (the entry bar included): stop first (fills at the stop, or at the
     open if it gapped through: a stop fill, one tick of slippage); then the limit target (fills at the
     target, or at the open if it gapped through in our favour; no slippage). A stop and a target in
     one bar -> the stop (sec 2.1).
  D. rules at this close -> an exit at the NEXT open: T: bands come in, first close beyond the exit MA
     (SMA8 by default); MR: a close back beyond line30, or the 10-bar time stop; C: a T fired, or the
     5-bar time stop. A time stop counts the entry bar as bar 1: at the close of bar N the position
     leaves at the next open.
  E. signals at this close -> an order for the next open. It is taken only if flat, or if the position
     is leaving at that same open; otherwise it is counted (skipped_in_position) and dropped.
  F. the last bar closes any open position at its close ("data_end").

A C trade's target is the middle band as it stood at the PREVIOUS close (mid[j-1]), refreshed every bar.
"""
from __future__ import annotations

import numpy as np

from strategy.crudele_3s import spec as S
from strategy.crudele_3s.states import Signals
from strategy.futbt.core import Frame, Trade2, size

RISK = {S.ARM_T: S.RISK_T, S.ARM_MR: S.RISK_MR, S.ARM_C: S.RISK_C}
ARM_OF = {1: S.ARM_T, 2: S.ARM_MR, 3: S.ARM_C}


def new_counts() -> dict:
    d = dict(voided=0, void_target=0, skipped_size=0, skipped_in_position=0, unfilled_at_end=0)
    for a in S.ARMS:
        d.update({f"signals_{a}": 0, f"entries_{a}": 0, f"entries_{a}_long": 0, f"entries_{a}_short": 0})
    return d


def simulate(fr: Frame, sig: Signals, *, equity: float, integer: bool, arms=None,
             risk_of=None) -> tuple[list, dict]:
    arms = tuple(sig.params.arms if arms is None else arms)
    risk_of = risk_of or RISK
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    n = fr.n
    mult = fr.mult
    mid = sig.mid
    trades: list[Trade2] = []
    k = new_counts()

    pos = 0
    st = None                       # open-position record
    pend_entry = None
    pend_exit = None

    def close(j, px, reason, stop_fill):
        nonlocal pos, st
        trades.append(Trade2(pos, st["j"], j, st["px"], px, st["stop0"], st["qty"], reason, stop_fill,
                             arm=st["arm"], risk_frac=st["risk"], signal_j=st["sj"],
                             atr_dist=st["atr_dist"], ep=st["ep"]))
        pos, st = 0, None

    for j in range(n):
        # A. pending exit at this open
        if pend_exit is not None and pos != 0:
            through = (pos == 1 and o[j] <= st["stop"]) or (pos == -1 and o[j] >= st["stop"])
            close(j, o[j], "stop_gap" if through else pend_exit, through)
        pend_exit = None

        # B. pending entry at this open
        if pend_entry is not None:
            arm, d, stop, tgt, l30, ep, sj = pend_entry
            pend_entry = None
            if (d == 1 and o[j] <= stop) or (d == -1 and o[j] >= stop):
                k["voided"] += 1
            else:
                tj = mid[j - 1] if arm == S.ARM_C else tgt
                if arm == S.ARM_T:
                    tj = tgt if (np.isfinite(tgt) and ((d == 1 and tgt > o[j]) or (d == -1 and tgt < o[j]))) else np.nan
                if arm != S.ARM_T and np.isfinite(tj) and ((d == 1 and o[j] >= tj) or (d == -1 and o[j] <= tj)):
                    k["void_target"] += 1
                else:
                    q = size(risk_of[arm] * equity, abs(o[j] - stop), mult, integer)
                    if q <= 0:
                        k["skipped_size"] += 1
                    else:
                        pos = d
                        st = dict(arm=arm, j=j, px=o[j], stop=stop, stop0=stop, tgt=tj, l30=l30, ep=ep,
                                  qty=q, risk=risk_of[arm], sj=sj,
                                  atr_dist=abs(o[j] - stop) / sig.atr[sj] if sig.atr[sj] > 0 else np.nan)
                        k[f"entries_{arm}"] += 1
                        k[f"entries_{arm}_{'long' if d == 1 else 'short'}"] += 1

        # C. resting orders inside the bar (stop first)
        if pos != 0:
            stop = st["stop"]
            tgt = mid[j - 1] if st["arm"] == S.ARM_C else st["tgt"]
            if pos == 1:
                if l[j] <= stop:
                    close(j, min(o[j], stop), "stop" if o[j] > stop else "stop_gap", True)
                elif np.isfinite(tgt) and h[j] >= tgt:
                    close(j, max(o[j], tgt), "target", False)
            else:
                if h[j] >= stop:
                    close(j, max(o[j], stop), "stop" if o[j] < stop else "stop_gap", True)
                elif np.isfinite(tgt) and l[j] <= tgt:
                    close(j, min(o[j], tgt), "target", False)

        if j == n - 1:                                            # F
            if pos != 0:
                close(j, c[j], "data_end", False)
            if sig.sig_arm[j] != 0:
                k["unfilled_at_end"] += 1
            break

        # D. rule exits at this close -> next open
        if pos != 0:
            arm, held = st["arm"], j - st["j"] + 1
            why = None
            if arm == S.ARM_T:
                if sig.bands_in_ep[j] == st["ep"]:
                    why = "bands_in"
                elif np.isfinite(sig.ma[j]) and ((pos == 1 and c[j] < sig.ma[j]) or (pos == -1 and c[j] > sig.ma[j])):
                    why = "ma"
            elif arm == S.ARM_MR:
                if (pos == -1 and c[j] > st["l30"]) or (pos == 1 and c[j] < st["l30"]):
                    why = "back30"
                elif held >= S.MR_TIME_STOP:
                    why = "time"
            else:
                if sig.t_fire[j]:
                    why = "T_fired"
                elif held >= S.C_TIME_STOP:
                    why = "time"
            if why:
                pend_exit = why

        # E. signal at this close -> order for the next open
        a = int(sig.sig_arm[j])
        if a:
            arm = ARM_OF[a]
            k[f"signals_{arm}"] += 1
            if arm in arms:
                if pos == 0 or pend_exit is not None:
                    pend_entry = (arm, int(sig.sig_dir[j]), sig.sig_stop[j], sig.sig_tgt[j],
                                  sig.sig_line30[j], int(sig.sig_ep[j]), j)
                else:
                    k["skipped_in_position"] += 1
    return trades, k
