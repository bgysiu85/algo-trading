#!/usr/bin/env python3
"""CHARTMARK-v2 G2: count-only pre-flight, training side (Amendment 4.7). K1-K4 on the full training window, split by the
development (2010-06..2015-12) and confirmation (2016-01..2021-12) windows. Orders, fills, no-fills, exits by type, arms, per year.
NO exit price, NO P&L: the runner refuses every P&L flag and this module prints no price.

    python -m strategy.chartmark_v2.preflight

A candidate with < 75 fills in either window is reported and dropped from selection (not replaced)."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from strategy.chartmark.data import Frame, indicators, load_training_frame
from strategy.chartmark_v2 import engine as E
from strategy.chartmark_v2 import spec as S
from strategy.futbt import runner_common as RC

PREDICTION = (400, 900)          # sec 9, base fills on training


def window_of(day: str) -> str | None:
    if S.DEV_FIRST <= day <= S.DEV_LAST:
        return "dev"
    if S.CONF_FIRST <= day <= S.CONF_LAST:
        return "conf"
    return None


def counts_block(fr: Frame, trades: list, cnt: dict) -> dict:
    ny = fr.ny
    days = [str(ny[t.entry_j].date()) for t in trades]
    per_year: dict[int, dict] = {}
    for t, d in zip(trades, days):
        y = int(d[:4])
        r = per_year.setdefault(y, dict(fills=0, exits=Counter(), arms=Counter()))
        r["fills"] += 1
        r["exits"][t.reason] += 1
        r["arms"][t.arm] += 1
    win = {}
    for w in ("dev", "conf"):
        tt = [t for t, d in zip(trades, days) if window_of(d) == w]
        win[w] = dict(fills=len(tt), exits=dict(Counter(t.reason for t in tt)), arms=dict(Counter(t.arm for t in tt)),
                      gap_fills=sum(t.gap_fill for t in tt),
                      med_bars_held=float(np.median([t.exit_j - t.entry_j for t in tt])) if tt else None,
                      rolls_carried=sum(t.n_rolls > 0 for t in tt))
    win["dev"]["ok"] = win["dev"]["fills"] >= S.MIN_TRADES_WINDOW
    win["conf"]["ok"] = win["conf"]["fills"] >= S.MIN_TRADES_WINDOW
    return dict(counts=cnt, n=len(trades), windows=win, eligible=bool(win["dev"]["ok"] and win["conf"]["ok"]),
                per_year={y: dict(fills=r["fills"], exits=dict(r["exits"]), arms=dict(r["arms"])) for y, r in sorted(per_year.items())})


def render(blocks: dict, stamp: str, label: str, n_bars: int, first, last) -> str:
    L = [f"CHARTMARK-v2 G2 count-only pre-flight, training side, {stamp}",
         f"data: {label}; {n_bars} bars {first} .. {last}; no price or P&L is reported here.",
         f"windows (NY entry date): development {S.DEV_FIRST}..{S.DEV_LAST}; confirmation {S.CONF_FIRST}..{S.CONF_LAST}.",
         f"Amendment 4.7 rule: a candidate with < {S.MIN_TRADES_WINDOW} fills in either window is dropped from selection.", ""]
    for name, b in blocks.items():
        c = b["counts"]
        L += [f"== {name}  {S.CANDIDATES[name]}",
              f"order-bars {c['orders']}  fills {c['fills']}  unfilled {c['unfilled']}  no red bar {c['no_red']}  "
              f"level not above the close {c['below_market']}  roll-blocked {c['roll_blocked']}  gap-through fills {c['gap_fills']}",
              f"armed closes by type {c['arms']}  fills by arm {c['fills_by_arm']}",
              f"exits by type {c['exits']}",
              f"EMA21 exits by clause: first-true {c['clauses_first']}  any-true {c['clauses_any']}"]
        for w, lab in (("dev", "development"), ("conf", "confirmation")):
            x = b["windows"][w]
            L.append(f"  {lab}: fills {x['fills']} {'OK' if x['ok'] else 'BELOW ' + str(S.MIN_TRADES_WINDOW)}  exits {x['exits']}  arms {x['arms']}  "
                     f"median bars held {x['med_bars_held']}  positions carried through a roll {x['rolls_carried']}")
        L.append("  per year (fills / exits / arms):")
        for y, r in b["per_year"].items():
            L.append(f"    {y}: {r['fills']:4d}  {r['exits']}  {r['arms']}")
        L.append(f"  selection: {'ELIGIBLE' if b['eligible'] else 'DROPPED (fewer than 75 fills in a window)'}")
        L.append("")
    elig = [k for k, b in blocks.items() if b["eligible"]]
    k1 = blocks["K1"]["n"]
    L += [f"SELECTION POOL: {elig or 'EMPTY -- NOT READ, stop and report to Ben'}",
          f"Registered prediction (sec 9), base K1 fills on training: {PREDICTION[0]}-{PREDICTION[1]}; observed {k1} "
          + ("(inside)" if PREDICTION[0] <= k1 <= PREDICTION[1] else "(OUTSIDE the range)"),
          ("STOP: no candidate is eligible." if not elig else "Step S may run for the eligible candidates only."), ""]
    return "\n".join(L)


def run(archive, out_dir: Path, stamp: str, log=print) -> Path:
    fr = load_training_frame(archive)
    ind = indicators(fr)
    pre = E.precompute(fr, ind)
    blocks = {}
    for name, p in S.CANDIDATES.items():
        trades, cnt = E.simulate(fr, ind, p, pre=pre)
        blocks[name] = counts_block(fr, trades, cnt)
    text = render(blocks, stamp, fr.label, fr.n, fr.ny[0], fr.ny[-1])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"w15_0036_v2_preflight_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    (out_dir / f"w15_0036_v2_preflight_{stamp}.json").write_text(json.dumps(blocks, indent=1, default=str), encoding="utf-8")
    log(text)
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-v2 count-only pre-flight (training side, K1-K4).")
    a = ap.parse_args(argv)
    if a.markets:
        raise SystemExit("--markets is not a CHARTMARK option (CL only).")
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
