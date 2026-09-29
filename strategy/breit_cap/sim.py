#!/usr/bin/env python3
"""The BREIT-CAP position walk: one market, one sizing, both sides (REGISTERED_breit_cap.md sec 2.4).

Per bar j:
  B. a resting entry ORDER placed at the close of j-1 (from strategy/breit_cap/signals.py):
       long  buy-stop  at E = high[j-1] + 1 tick: fills when high[j] >= E, at max(open, E)
       short sell-stop at E = low[j-1]  - 1 tick: fills when low[j]  <= E, at min(open, E)
     An order that does not fill is not carried (the run extends and a new order is placed at the
     close). Taken only if flat; a qualified order while a position is open is counted
     (skipped_in_position) and dropped. Sized from the actual fill: qty = risk $ / (|fill - stop| x mult);
     integer floors and zero = SKIP (counted). The entry bar's own range decides a same-bar stop: if
     the bar trades to the initial stop the trade is stopped in that bar (conservative, sec 2.4).
  C. resting stop / target inside a later bar: the stop first (fills at the stop or at the open if it
     gapped through: a stop fill); then the variant's limit target.
  D. the trail at this close, for the next bar: stop = max(stop, low[j] - 1 tick) (short: min(stop,
     high[j] + 1 tick)); it never loosens. Applying it at the entry bar's close is "from the first bar
     after the entry bar" (the bar-j+1 stop uses the entry bar's low).
  F. the last bar closes any open position at its close ("data_end").

Exit reasons: same_bar_stop | initial_stop | trailed_stop | target | data_end.
"""
from __future__ import annotations

import numpy as np

from strategy.breit_cap import spec as S
from strategy.breit_cap.signals import Signals
from strategy.futbt.core import Frame, Trade2, size


def new_counts() -> dict:
    return dict(orders=0, unfilled=0, skipped_in_position=0, skipped_size=0, entries=0,
                entries_long=0, entries_short=0, grade_skipped=0, side_off=0, unfilled_at_end=0)


def risk_for(p: S.Params, side: int, grade: int) -> float:
    if p.sizing == "flat":
        return S.FLAT_RISK
    r = S.grade_risk(int(grade))
    return r if side == 1 else r * S.SHORT_FACTOR


def simulate(fr: Frame, sig: Signals, *, equity: float, integer: bool) -> tuple[list, dict]:
    p = sig.params
    o, h, l, c = fr.o, fr.h, fr.l, fr.c
    n, tick, mult = fr.n, fr.tick, fr.mult
    trades: list[Trade2] = []
    k = new_counts()
    pos = 0
    st = None
    order = None                     # (side_i, entry, stop, grade, k, dATR, run_id, tgt50, signal_j)

    def close(j, px, reason, stop_fill):
        nonlocal pos, st
        trades.append(Trade2(pos, st["j"], j, st["px"], px, st["stop0"], st["qty"], reason, stop_fill,
                             arm=S.B, grade=st["grade"], risk_frac=st["risk"], k=st["k"],
                             d_atr=st["d_atr"], signal_j=st["sj"], atr_dist=st["atr_dist"], ep=st["run"]))
        pos, st = 0, None

    def target_for(side, j, tgt50):
        if p.target == "50":
            return tgt50
        if p.target == "ma":
            return sig.mid[j - 1]
        return np.nan

    for j in range(n):
        had_pos = pos != 0
        # C. resting stop, then target, for a position that was open when the bar began
        if had_pos:
            stop = st["stop"]
            tgt = target_for(pos, j, st["tgt"]) if p.target == "ma" else st["tgt"]
            if np.isfinite(tgt) and ((pos == 1 and tgt <= st["px"]) or (pos == -1 and tgt >= st["px"])):
                tgt = np.nan                                   # a target is used only if beyond the fill
            if pos == 1:
                if l[j] <= stop:
                    close(j, min(o[j], stop), "trailed_stop" if stop > st["stop0"] else "initial_stop", True)
                elif np.isfinite(tgt) and h[j] >= tgt:
                    close(j, max(o[j], tgt), "target", False)
            else:
                if h[j] >= stop:
                    close(j, max(o[j], stop), "trailed_stop" if stop < st["stop0"] else "initial_stop", True)
                elif np.isfinite(tgt) and l[j] <= tgt:
                    close(j, min(o[j], tgt), "target", False)

        # B. resting entry order for this bar (dropped if a position was open at the bar's start)
        if order is not None:
            si, E, stop0, g, kr, dat, run, t50, sj = order
            order = None
            d = 1 if si == 0 else -1
            k["orders"] += 1
            fills = h[j] >= E if d == 1 else l[j] <= E
            if had_pos:
                k["skipped_in_position"] += 1
            elif not fills:
                k["unfilled"] += 1
            else:
                fill = max(o[j], E) if d == 1 else min(o[j], E)
                risk = risk_for(p, d, g)
                q = size(risk * equity, abs(fill - stop0), mult, integer)
                if q <= 0:
                    k["skipped_size"] += 1
                else:
                    pos = d
                    st = dict(j=j, px=fill, stop=stop0, stop0=stop0, qty=q, risk=risk, grade=g, k=kr,
                              d_atr=dat, sj=sj, run=run, tgt=target_for(d, j, t50),
                              atr_dist=abs(fill - stop0) / sig.atr[sj] if sig.atr[sj] > 0 else np.nan)
                    k["entries"] += 1
                    k["entries_long" if d == 1 else "entries_short"] += 1
                    # entry bar: a bar that trades to the initial stop is stopped in that bar
                    if (d == 1 and l[j] <= stop0) or (d == -1 and h[j] >= stop0):
                        px = min(o[j], stop0) if d == 1 else max(o[j], stop0)
                        close(j, px, "same_bar_stop", True)

        if j == n - 1:
            if pos != 0:
                close(j, c[j], "data_end", False)
            if sig.ok[:, j].any():
                k["unfilled_at_end"] += 1
            break

        # D. trail at this close
        if pos == 1:
            st["stop"] = max(st["stop"], l[j] - tick)
        elif pos == -1:
            st["stop"] = min(st["stop"], h[j] + tick)

        # E. order for the next bar
        for si, d in ((0, 1), (1, -1)):
            if not sig.ok[si, j]:
                continue
            if d not in p.sides:
                k["side_off"] += 1
                continue
            if sig.grade[si, j] < p.min_grade:
                k["grade_skipped"] += 1
                continue
            order = (si, sig.entry[si, j], sig.stop[si, j], int(sig.grade[si, j]), int(sig.k[si, j]),
                     float(sig.d_atr[si, j]), int(sig.run_id[si, j]), sig.tgt50[si, j], j)
    return trades, k
