#!/usr/bin/env python3
"""The CRUDELE-3S state machine and its signals, as arrays (REGISTERED_crudele_3s.md sec 2.2-2.4,
Amendment A). No position, no P&L, no fills: this is what pre-flight (G2) counts and what the
sim (sim.py) trades.

Everything at close t uses bars <= t (G4). Signals at close t are orders for the open of t + 1.

READINGS OF THE REGISTRATION'S TEXT (each a coding decision, none a threshold)
------------------------------------------------------------------------------
* BWR[t] = share of BW over bars t-249..t (t included) that is <= BW[t]; NaN until 250 BW values.
* Squeeze[t] = BWR <= thr on at least 5 of bars t-9..t.
* The range box is compared PRIOR to the bar under test: a bar's own high can never be "beyond"
  a box that already contains it. On the bar C is entered the box (highest high / lowest low of
  bars t-19..t) includes bar t and nothing is tested that bar. While C lasts it is extended AFTER
  each bar's tests. When C is left the box is kept, frozen, for the 5-bar grace in which T may fire.
* T (long): BW rose on each of the last `exp_bars` bars, U[t] > U[t-1] and close[t] > the prior box
  high; mirror for short. Evaluated while in C or within `C_GRACE` bars after leaving it (or always,
  in the "T without squeeze" variant, against the prior 20-bar high/low).
* "Bands come in" = BW falls on 2 consecutive bars counted from the bar T fired (the falls must be
  inside the episode). U*/L* run over bars t_start..t and are frozen at that close.
* MR is armed at that close for 20 bars (t .. t+19). It triggers on the FIRST close in the window with
  close < line30 (short after a long trend; mirror otherwise); `close < line30` is the registered
  test, and it is evaluated on the arm close itself. The arm is consumed by its trigger (state -> N),
  whether or not the sim can take the trade. If H is not positive the arm is skipped and counted.
* A new T firing ends an armed MR (registration table); in the registered rule set that cannot
  happen (C, hence T, is off while MR is armed); it can in the "T without squeeze" variant.
* If one bar pokes both sides of the box and closes back inside, no C trade is signalled (counted).
* At each close the state label is chosen MR > T > C > N.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from strategy.crudele_3s import spec as S
from strategy.crudele_3s.beacon import beacon_pair
from strategy.futbt.core import Frame, bollinger, sma

N_, C_, T_, MR_ = 0, 1, 2, 3
STATE_NAMES = {N_: "N", C_: "C", T_: "T", MR_: "MR"}
ARM_CODE = {0: "", 1: S.ARM_T, 2: S.ARM_MR, 3: S.ARM_C}


@dataclass
class Signals:
    n: int
    params: S.Params
    state: np.ndarray             # int8 per bar (N/C/T/MR at the close)
    sig_arm: np.ndarray           # 0 none, 1 T, 2 MR, 3 C
    sig_dir: np.ndarray
    sig_stop: np.ndarray          # initial stop LEVEL (T: box edge -/+ 1 tick; MR: line0; C: poke -/+ 0.10 ATR)
    sig_tgt: np.ndarray           # T: previous episode price extreme (NaN if none); MR: line50; C: NaN (mid)
    sig_line30: np.ndarray        # MR: the close-back level; NaN otherwise
    sig_ep: np.ndarray            # episode id
    t_fire: np.ndarray            # bool: a T fired at this close
    bands_in_ep: np.ndarray       # episode id whose bands came in at this close, else -1
    mid: np.ndarray               # Bollinger middle (M)
    ma: np.ndarray                # trend exit MA
    atr: np.ndarray
    bwr: np.ndarray
    counts: dict = field(default_factory=dict)
    episodes: list = field(default_factory=list)


def indicators(fr: Frame, p: S.Params):
    M, U, L = bollinger(fr.c, S.BB_LEN, p.sd)
    BW = U - L
    n = fr.n
    bwr = np.full(n, np.nan)
    w = S.BWR_WIN
    for t in range(w - 1 + S.BB_LEN - 1, n):
        win = BW[t - w + 1:t + 1]
        bwr[t] = float((win <= BW[t]).mean())
    return M, U, L, BW, bwr


def compute(fr: Frame, p: S.Params = S.PRIMARY) -> Signals:
    n = fr.n
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    tick = fr.tick
    M, U, L, BW, bwr = indicators(fr, p)
    ma = sma(c, p.exit_ma)
    atr = fr.atr()
    if p.beacon_mr:
        pm, vm = beacon_pair(U, L)

    state = np.zeros(n, np.int8)
    sig_arm = np.zeros(n, np.int8)
    sig_dir = np.zeros(n, np.int8)
    sig_stop = np.full(n, np.nan)
    sig_tgt = np.full(n, np.nan)
    sig_l30 = np.full(n, np.nan)
    sig_ep = np.full(n, -1, np.int64)
    t_fire = np.zeros(n, bool)
    bands_in_ep = np.full(n, -1, np.int64)
    cnt = dict(t_episodes=0, t_timeouts=0, t_bands_in=0, mr_arms=0, mr_arms_skipped_h=0,
               mr_arms_skipped_beacon=0, mr_triggers=0, mr_expired=0, c_stop_runs=0, c_both_sides=0,
               t_signals_long=0, t_signals_short=0)
    episodes: list[dict] = []

    below = np.where(np.isfinite(bwr), bwr <= p.bwr_thr, False)
    sq = np.zeros(n, bool)
    for t in range(S.SQ_OF - 1, n):
        sq[t] = below[t - S.SQ_OF + 1:t + 1].sum() >= S.SQ_COUNT

    in_c = False
    c_grace = 0
    box_hi = box_lo = np.nan
    t_dir = 0
    t_ep = -1
    t_start = -1
    ustar = lstar = np.nan
    u_at = l_at = -1
    falls = 0
    mr = None                                   # dict(dir, l30, l50, l0, end)
    last_peak = {1: np.nan, -1: np.nan}         # previous COMPLETED T episode's price extreme, by direction
    first = S.BWR_WIN + S.BB_LEN - 2            # first index with a valid BWR

    for t in range(n):
        if t < first or not np.isfinite(atr[t]):
            continue
        fired_t = False

        # --- a running T episode: extremes, falls, bands come in, timeout ---------------------
        if t_dir != 0:
            if U[t] > ustar:
                ustar, u_at = U[t], t
            if L[t] < lstar:
                lstar, l_at = L[t], t
            if t > t_start:
                falls = falls + 1 if BW[t] < BW[t - 1] else 0
            if falls >= S.IN_FALLS:
                cnt["t_bands_in"] += 1
                bands_in_ep[t] = t_ep
                ext_bar = u_at if t_dir == 1 else l_at
                last_peak[t_dir] = h[ext_bar] if t_dir == 1 else l[ext_bar]
                episodes[t_ep]["end"], episodes[t_ep]["end_reason"] = t, "bands_in"
                H = ustar - lstar
                d_mr = -t_dir
                arm_ok = H > 0
                u0, l0 = ustar, lstar
                if p.beacon_mr:
                    u0, l0 = pm[t], vm[t]
                    H = u0 - l0
                    arm_ok = H > 0 and ((d_mr == -1 and u0 > c[t]) or (d_mr == 1 and l0 < c[t]))
                    if not arm_ok:
                        cnt["mr_arms_skipped_beacon"] += 1
                elif not arm_ok:
                    cnt["mr_arms_skipped_h"] += 1
                if arm_ok:
                    if d_mr == -1:      # short after a long trend: measured DOWN from the peak
                        mr = dict(dir=-1, l30=u0 - S.FIB_ENTRY * H, l50=u0 - S.FIB_TARGET * H, l0=u0,
                                  end=t + S.MR_ARM - 1, ep=t_ep)
                    else:               # long after a short trend: measured UP from the trough
                        mr = dict(dir=1, l30=l0 + S.FIB_ENTRY * H, l50=l0 + S.FIB_TARGET * H, l0=l0,
                                  end=t + S.MR_ARM - 1, ep=t_ep)
                    cnt["mr_arms"] += 1
                t_dir = 0
                falls = 0
            elif t - t_start >= S.T_TIMEOUT:
                cnt["t_timeouts"] += 1
                ext_bar = u_at if t_dir == 1 else l_at
                last_peak[t_dir] = h[ext_bar] if t_dir == 1 else l[ext_bar]
                episodes[t_ep]["end"], episodes[t_ep]["end_reason"] = t, "timeout"
                t_dir = 0
                falls = 0

        # --- an armed MR: expiry, trigger -------------------------------------------------------
        if mr is not None:
            if t > mr["end"]:
                cnt["mr_expired"] += 1
                mr = None
            else:
                hit = c[t] < mr["l30"] if mr["dir"] == -1 else c[t] > mr["l30"]
                if hit:
                    sig_arm[t], sig_dir[t] = 2, mr["dir"]
                    sig_stop[t], sig_tgt[t], sig_l30[t], sig_ep[t] = mr["l0"], mr["l50"], mr["l30"], mr["ep"]
                    cnt["mr_triggers"] += 1
                    mr = None

        # --- T: fires from C (or its grace), or anywhere in the "no squeeze" variant ---------------
        if t_dir == 0 and (in_c or c_grace > 0 or p.t_free) and t >= S.BOX_LEN:
            if p.t_free:
                bh, bl = h[t - S.BOX_LEN:t].max(), l[t - S.BOX_LEN:t].min()
            else:
                bh, bl = box_hi, box_lo
            k = p.exp_bars
            expanding = t >= k and all(BW[t - i] > BW[t - i - 1] for i in range(k))
            if expanding and np.isfinite(bh):
                d = 0
                if U[t] > U[t - 1] and c[t] > bh:
                    d = 1
                elif L[t] < L[t - 1] and c[t] < bl:
                    d = -1
                if d != 0:
                    fired_t = True
                    t_fire[t] = True
                    t_dir, t_start, falls = d, t, 0
                    ustar, lstar, u_at, l_at = U[t], L[t], t, t
                    t_ep = len(episodes)
                    episodes.append(dict(ep=t_ep, dir=d, start=t, end=-1, end_reason=""))
                    cnt["t_episodes"] += 1
                    cnt["t_signals_long" if d == 1 else "t_signals_short"] += 1
                    sig_arm[t], sig_dir[t], sig_ep[t] = 1, d, t_ep
                    sig_stop[t] = (bl - tick) if d == 1 else (bh + tick)
                    sig_tgt[t] = last_peak[d]
                    if mr is not None:              # a new T ends an armed MR
                        mr = None
                    in_c, c_grace = False, 0

        # --- C: squeeze, box, stop-run --------------------------------------------------------
        if t_dir == 0 and mr is None and not fired_t and sig_arm[t] == 0:
            if sq[t]:
                if not in_c:
                    in_c, c_grace = True, 0
                    box_hi, box_lo = h[t - S.BOX_LEN + 1:t + 1].max(), l[t - S.BOX_LEN + 1:t + 1].min()
                else:
                    up = h[t] > box_hi and c[t] < box_hi
                    dn = l[t] < box_lo and c[t] > box_lo
                    if up and dn:
                        cnt["c_both_sides"] += 1
                    elif up or dn:
                        cnt["c_stop_runs"] += 1
                        sig_arm[t] = 3
                        sig_dir[t] = -1 if up else 1
                        sig_stop[t] = (h[t] + S.C_STOP_ATR * atr[t]) if up else (l[t] - S.C_STOP_ATR * atr[t])
                    box_hi, box_lo = max(box_hi, h[t]), min(box_lo, l[t])
            elif in_c:
                in_c, c_grace = False, S.C_GRACE + 1     # +1: decremented on this same bar below
        if not in_c and c_grace > 0:
            c_grace -= 1
        if t_dir != 0:
            in_c = False

        state[t] = (MR_ if mr is not None else T_ if t_dir != 0 else C_ if in_c else N_)

    for e in episodes:
        if e["end"] < 0:
            e["end_reason"] = "data_end"
    return Signals(n, p, state, sig_arm, sig_dir, sig_stop, sig_tgt, sig_l30, sig_ep, t_fire,
                   bands_in_ep, M, ma, atr, bwr, cnt, episodes)
