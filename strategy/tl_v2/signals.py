#!/usr/bin/env python3
"""TL-v2 signal arrays: TL-v1's qualified breaks, entered on the retest. Board: W15-0030.

Everything except the ENTRY TIMING is TL-v1's, word for word (REGISTERED_tl_v2.md sec 2.1): the
line (common/tl_v1_lines), A1-A3, the weekly filter, the v0-rev safety line / trail / initial
stop, sizing, costs, fills. TL-v1's own code (strategy.tl_v1.signals) builds the gate; this module
adds only the retest scan and turns its output into the arrays strategy.tl_v0.sim.simulate reads.

HOW A RETEST ENTRY IS FED TO THE UNCHANGED SIMULATOR
----------------------------------------------------
  up / dn      = raw line breaks  OR  retest entry bars.   A raw break still exits at the next
                 open (sec 2.4: an opposite raw break exits); a retest bar is the entry trigger.
  qual_up/dn   = the retest entry bars ONLY.  A raw break, qualified or not, therefore never
                 enters and never reverses by itself: it can only exit, and the simulator books
                 it as not_aplus / flat_blocked (sec 2.2: "reverse only into another qualified
                 retest entry; otherwise flat").
  htf          = the weekly direction, except ON a retest entry bar, where it is set to the
                 entry's own direction. The weekly filter was already applied at the break bar t
                 (sec 2.1: a qualified break includes E2); it is not re-applied at bar s.
  init stops   = as of the signal bar s (the entry bar), exactly as TL-v1 computes them at entry.
sim.py is not touched, so the TL-v0 / TL-v1 tests are untouched.

The touch-buffer axis of the sec 3 neighbour grid moves BOTH A1's touch buffer and T1's (the
registration defines T1 as "the A1 touch buffer"); `buf` here feeds both.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from common.tl_v0_lines import find_pivots
from common.tl_v1_lines import TOUCH_BUFFER, WINDOW
from strategy.tl_v0.engine import tl_input
from strategy.tl_v0.sim import SimInput
from strategy.tl_v1.signals import ER_Q, Gate, MarketCtx, gate_for
from strategy.tl_v2 import retest as RT

VARIANTS: dict[str, dict] = {
    "v2": {},                    # primary: N = 10
    "v2-SR": {"sr": True},       # S/R double confirmation (gap 10), reported only
    "v2-N20": {"N": 20},         # window variant, reported only
}


@dataclass
class V2Signals:
    scan: RT.RetestScan
    gate: Gate
    qual_up_w: np.ndarray        # qualified break AND weekly ok, at the break bar t
    qual_dn_w: np.ndarray


def _sr_pivots(ctx: MarketCtx, kind: str):
    key = ("sr", kind)
    if key not in ctx._touch:
        vals = ctx.h if kind == "res" else ctx.l
        ctx._touch[key] = find_pivots(vals, RT.SR_R, "high" if kind == "res" else "low")
    return ctx._touch[key]


def retest_signals(ctx: MarketCtx, R: int, *, N: int = RT.RETEST_N, buf: float = TOUCH_BUFFER,
                   window: int = WINDOW, erq: float = ER_Q, **gate_kw) -> V2Signals:
    g = gate_for(ctx, R, window=window, touch_buf=buf, erq=erq, **gate_kw)
    htf = tl_input(ctx.v0sig(R), "v0-rev").htf
    qu = g.qual_up & (htf == 1)
    qd = g.qual_dn & (htf == -1)
    lines = ctx.lines(R, window)
    up = RT.Side(1, g.raw_up, qu, lines["res"]["line"], lines["res"]["anchor_bar"], ctx.h,
                 _sr_pivots(ctx, "res"))
    dn = RT.Side(-1, g.raw_dn, qd, lines["sup"]["line"], lines["sup"]["anchor_bar"], ctx.l,
                 _sr_pivots(ctx, "sup"))
    sc = RT.scan(ctx.h, ctx.l, ctx.c, ctx.a_raw, up, dn, N=N, buf=buf)
    return V2Signals(sc, g, qu, qd)


def v2_input(ctx: MarketCtx, R: int, *, sr: bool = False, **kw) -> tuple[SimInput, V2Signals]:
    """SimInput for one TL-v2 sleeve (see the module docstring)."""
    s = retest_signals(ctx, R, **kw)
    base = tl_input(ctx.v0sig(R), "v0-rev")
    eu = s.scan.sr_up if sr else s.scan.ent_up
    ed = s.scan.sr_dn if sr else s.scan.ent_dn
    return to_sim_input(base, s.gate.raw_up, s.gate.raw_dn, eu, ed), s


def to_sim_input(base: SimInput, raw_up, raw_dn, ent_up, ent_dn) -> SimInput:
    """The one place a retest entry is fed to the unchanged simulator (module docstring)."""
    htf = base.htf.copy()
    htf[ent_up] = 1
    htf[ent_dn] = -1
    return replace(base, up=raw_up | ent_up, dn=raw_dn | ent_dn, qual_up=ent_up, qual_dn=ent_dn, htf=htf)


def size_entry(x: SimInput, s: int, direction: int, *, mult: float, risk_usd: float) -> dict:
    """What the simulator would do with an entry signal at bar s, WITHOUT running it and WITHOUT
    reading any bar after s+1's open: no_stop / void / contracts. The pre-flight's sizeable share.
    Mirrors strategy.tl_v0.sim (order(): stop must be finite and on the right side of the signal
    close; fill: void if the open is already through the stop; integer contracts = floor(risk /
    (|open - stop| x mult)), zero = skip). A test pins it against simulate()."""
    st = x.init_long[s] if direction == 1 else x.init_short[s]
    if not np.isfinite(st) or (direction == 1 and st >= x.c[s]) or (direction == -1 and st <= x.c[s]):
        return dict(status="no_stop", contracts=0)
    if s + 1 >= len(x.o):
        return dict(status="unfilled", contracts=0)
    op = x.o[s + 1]
    if (direction == 1 and op <= st) or (direction == -1 and op >= st):
        return dict(status="void", contracts=0)
    dist = abs(op - st)
    q = int(np.floor(risk_usd / (dist * mult) + 1e-12)) if dist > 0 else 0
    return dict(status="sizeable" if q >= 1 else "skipped_size", contracts=q)
