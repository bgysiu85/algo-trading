#!/usr/bin/env python3
"""CHARTMARK-S v2 G2: count-only pre-flight, training side. Orders, fills, cancels, timeouts, re-entries, exits by type, share
reaching P1, per year, BY TIER (A / B), plus the share of context bars that are Tier A vs Tier B. NO exit price, NO P&L.

    python -m strategy.chartmark_s2.preflight
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from strategy.chartmark_s2 import engine as E
from strategy.chartmark_s2 import spec as S
from strategy.chartmark_s2.data import context_tiers, indicators, load_training_frame
from strategy.futbt import runner_common as RC

STOP_RULE = 150
TIERS = {S.TIER_A: "A", S.TIER_B: "B"}


def counts_table(fr, trades: list, cnt: dict) -> dict:
    years = np.asarray(fr.ny.year)
    per = {}
    for y in sorted(set(int(v) for v in years[[t.entry_j for t in trades]])) if trades else []:
        tt = [t for t in trades if years[t.entry_j] == y]
        per[y] = dict(fills=len(tt), exits=dict(Counter(t.reason for t in tt)), reached_p1=sum(t.phase >= 1 for t in tt),
                      A=sum(t.tier == S.TIER_A for t in tt), B=sum(t.tier == S.TIER_B for t in tt))
    o2f = [t.entry_j - t.placed_j for t in trades if t.placed_j >= 0]
    f2x = [t.exit_j - t.entry_j for t in trades]
    by_tier = {}
    for code, nm in TIERS.items():
        tt = [t for t in trades if t.tier == code]
        by_tier[nm] = dict(orders=cnt["orders_by_tier"][code], fills=len(tt), exits=dict(Counter(t.reason for t in tt)),
                           reached_p1=sum(t.phase >= 1 for t in tt),
                           med_fill_to_exit=float(np.median([t.exit_j - t.entry_j for t in tt])) if tt else None)
    return dict(counts=cnt, n=len(trades), exits=dict(Counter(t.reason for t in trades)),
                reached_p1=sum(t.phase >= 1 for t in trades), by_tier=by_tier,
                med_order_to_fill=float(np.median(o2f)) if o2f else None,
                med_fill_to_exit=float(np.median(f2x)) if f2x else None,
                rolls_carried=sum(t.n_rolls > 0 for t in trades), per_year=per)


def context_share(fr, ind, p=S.BASE, ctx_fn=None) -> dict:
    ctx, tier = (ctx_fn or context_tiers)(fr, ind, p)
    a, b = int((tier == S.TIER_A).sum()), int((tier == S.TIER_B).sum())
    return dict(context_bars=int(ctx.sum()), A=a, B=b, total_bars=int(fr.n))


def _pct(a, b) -> str:
    return f"{100 * a / b:.0f}%" if b else "n/a"


def report(fr, blocks: dict, share: dict, stamp: str, name: str = "CHARTMARK-S v2") -> str:
    L = [f"{name} G2 count-only pre-flight, training side, {stamp}",
         f"data: {fr.label}; {fr.n} bars; no price or P&L is reported here.", ""]
    for name, b in blocks.items():
        c = b["counts"]
        L += [f"== {name}",
              f"orders {c['orders']}  fills {c['fills']}  cancels (E2 context) {c['ctx_cancels']}  timeouts (E3) {c['timeouts']}  "
              f"roll cancels {c['roll_cancels']}  re-sets {c['resets']}  re-entries after an exit {c['reentries']}",
              f"gap-through fills {c['gap_fills']}  same-bar backstop touches {c['same_bar']} (0 by construction, v1 J3)",
              f"exits by type {b['exits']}  reached P1 {b['reached_p1']} ({_pct(b['reached_p1'], b['n'])})  "
              f"positions carried through a roll {b['rolls_carried']}",
              f"median bars order->fill {b['med_order_to_fill']}  fill->exit {b['med_fill_to_exit']}"]
        for nm, r in b["by_tier"].items():
            L.append(f"  Tier {nm}: orders {r['orders']}  fills {r['fills']}  exits {r['exits']}  reached P1 {r['reached_p1']} "
                     f"({_pct(r['reached_p1'], r['fills'])})  median bars fill->exit {r['med_fill_to_exit']}")
        L.append("")
    base = blocks["BASE"]
    L += ["BASE per year (fills / Tier A / Tier B / exits / reached P1):"]
    for y, r in base["per_year"].items():
        L.append(f"  {y}: {r['fills']:4d}  A {r['A']:4d}  B {r['B']:4d}  {r['exits']}  P1 {r['reached_p1']}")
    ctxb = share["context_bars"]
    L += ["", f"Context bars (BASE, before the order machine): {ctxb} of {share['total_bars']}; Tier A {share['A']} ({_pct(share['A'], ctxb)}), "
          f"Tier B {share['B']} ({_pct(share['B'], ctxb)})."]
    n = base["n"]
    L += ["", f"STOP RULE (sec 5 G2): BASE fills = {n}; threshold {STOP_RULE}. "
          + ("UNDERPOWERED -- stop, report to Ben before any P&L." if n < STOP_RULE else "Clears the threshold; the backtest may run."),
          "Registered prediction (sec 10): 400-1,500 base fills; V-A fewest, V-B most."]
    return "\n".join(L) + "\n"


def run(archive, out_dir: Path, stamp: str, log=print) -> Path:
    fr = load_training_frame(archive)
    ind = indicators(fr)
    log(f"training frame: {fr.n} 1H bars {fr.ny[0]} .. {fr.ny[-1]}")
    blocks = {}
    for name, p in S.VARIANTS.items():
        trades, cnt = E.simulate(fr, ind, p)
        blocks[name] = counts_table(fr, trades, cnt)
    text = report(fr, blocks, context_share(fr, ind), stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"w15_0039_chartmark_short_v2_preflight_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    log(text)
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-S v2 count-only pre-flight (training side).")
    a = ap.parse_args(argv)
    if a.markets:
        raise SystemExit("--markets is not a CHARTMARK-S option (CL only).")
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
