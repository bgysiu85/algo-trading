#!/usr/bin/env python3
"""CHARTMARK-v1 G2: count-only pre-flight, training side. Orders, fills, no-fills, exits by type, phase reached, per year.
NO exit price, NO P&L: the runner refuses every P&L flag and this module never touches a price beyond the engine's own.

    python -m strategy.chartmark.preflight
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark import engine as E
from strategy.chartmark import spec as S
from strategy.chartmark.data import indicators, load_training_frame
from strategy.futbt import runner_common as RC

STOP_RULE = 150


def counts_table(fr, trades: list, cnt: dict) -> dict:
    """Counts only. Returns overall + per-year dict."""
    years = np.asarray(fr.ny.year)
    per = {}
    for y in sorted(set(years[[t.entry_j for t in trades]])) if trades else []:
        tt = [t for t in trades if years[t.entry_j] == y]
        per[int(y)] = dict(fills=len(tt), exits=dict(Counter(t.reason for t in tt)),
                           reached_p1=sum(t.phase >= 1 for t in tt), reached_p2=sum(t.phase >= 2 for t in tt))
    order_to_fill = [t.entry_j - t.placed_j for t in trades if t.placed_j >= 0]
    fill_to_exit = [t.exit_j - t.entry_j for t in trades]
    return dict(counts=cnt, n=len(trades), exits=dict(Counter(t.reason for t in trades)),
                reached_p1=sum(t.phase >= 1 for t in trades), reached_p2=sum(t.phase >= 2 for t in trades),
                med_order_to_fill=float(np.median(order_to_fill)) if order_to_fill else None,
                med_fill_to_exit=float(np.median(fill_to_exit)) if fill_to_exit else None,
                rolls_carried=sum(t.n_rolls > 0 for t in trades), per_year=per)


def run(archive, out_dir: Path, stamp: str, log=print) -> Path:
    fr = load_training_frame(archive)
    ind = indicators(fr)
    log(f"training frame: {fr.n} 1H bars {fr.ny[0]} .. {fr.ny[-1]}")
    blocks = {}
    for name, p in S.VARIANTS.items():
        trades, cnt = E.simulate(fr, ind, p)
        blocks[name] = counts_table(fr, trades, cnt)
    lines = [f"CHARTMARK-v1 G2 count-only pre-flight, training side, {stamp}",
             f"data: {fr.label}; {fr.n} bars; no price or P&L is reported here.", ""]
    for name, b in blocks.items():
        c = b["counts"]
        lines += [f"== {name}",
                  f"orders {c['orders']}  fills {c['fills']}  no-fills (E3 timeouts) {c['timeouts']}  "
                  f"context cancels {c['ctx_cancels']}  roll cancels {c['roll_cancels']}  re-sets {c['resets']}",
                  f"gap-through fills {c['gap_fills']}  entry bars whose own low sets the stop {c['stop_from_entry_bar']}  "
                  f"same-bar level+stop touches {c['same_bar_touch']}",
                  f"exits by type {b['exits']}  reached P1 {b['reached_p1']} ({_pct(b['reached_p1'], b['n'])})  "
                  f"P2 {b['reached_p2']} ({_pct(b['reached_p2'], b['n'])})  positions carried through a roll {b['rolls_carried']}",
                  f"median bars order->fill {b['med_order_to_fill']}  fill->exit {b['med_fill_to_exit']}", ""]
    base = blocks["BASE"]
    lines += ["BASE per year (fills / exits / reached P1 / P2):"]
    for y, r in base["per_year"].items():
        lines.append(f"  {y}: {r['fills']:4d}  {r['exits']}  P1 {r['reached_p1']}  P2 {r['reached_p2']}")
    n = base["n"]
    lines += ["", f"STOP RULE (sec 5): BASE fills = {n}; threshold {STOP_RULE}. "
              + ("UNDERPOWERED -- stop, report to Ben before any P&L." if n < STOP_RULE else "Clears the threshold; the backtest may run."),
              "Registered prediction (sec 10): 300-600 fills."]
    text = "\n".join(lines) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"w15_0032_chartmark_preflight_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    log(text)
    return path


def _pct(a, b) -> str:
    return f"{100 * a / b:.0f}%" if b else "n/a"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-v1 count-only pre-flight (training side).")
    a = ap.parse_args(argv)
    if a.markets:
        raise SystemExit("--markets is not a CHARTMARK option (CL only).")
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()      # the archive ROOT (E:\\Databento)
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
