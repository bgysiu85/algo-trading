#!/usr/bin/env python3
"""EXIT-CMP G6 (+ G3, G7): the count-only pre-flight. W15-0053 sub 2. REGISTERED_exit_cmp.md sec 12.

    python -m strategy.exit_cmp.preflight [--rewrite-ledger]

Prints and writes COUNTS ONLY: entries per year, how many trades reach each rule set's trigger (per year, per scenario), exits
by type, the median CL 1H ATR(14), how many S distances exceed the $0.60 emergency distance, the v1 trades held longer than the
HOLD cap, early-close sessions. NO exit price and NO P&L is printed (the walks run in memory because "reaches its trigger" is a
property of the walk; nothing priced leaves this module -- tests/strategy/exit_cmp/test_preflight.py checks the text). Then it
writes the ledger (G7). Every P&L / holdout / narrowing flag is refused."""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from exitmgr import rules as R
from strategy.chartmark.data import indicators, load_training_frame
from strategy.exit_cmp import entries as EN
from strategy.exit_cmp import ledger as LG
from strategy.exit_cmp import spec as S
from strategy.exit_cmp.walk import Study
from strategy.chartmark_clone.ledger import load_frame_cache
from strategy.futbt import runner_common as RC


def counts_report(st: Study, entries, per_year: dict, stamp: str) -> str:
    fr, ind = st.fr, st.ind
    years = np.asarray(fr.ny.year)
    ey = np.array([int(years[x.e]) for x in entries])
    s_dist = np.array([x.entry_px - x.s0 for x in entries])
    med_atr = float(np.nanmedian(ind.atr))
    L = [f"EXIT-CMP G6 count-only pre-flight, training side, {stamp}  (no exit price, no P&L)",
         f"data: {fr.label}; {fr.n} bars; entry set {len(entries)} fills (G3 ok), per year {per_year}",
         f"median CL 1H ATR(14) over training: {med_atr:.4f} (scales the sec 13 distances for other symbols)",
         f"entries whose S distance exceeds the ${S.EMERGENCY:.2f} emergency distance (sec 14 rail 3): "
         f"{int((s_dist > S.EMERGENCY).sum())} of {len(entries)}",
         f"early-close sessions in the frame (last bar before a gap, opening 13:00-15:59 NY): {st.early_closes}", ""]
    v1 = st.run(S.REFERENCE, "HOLD", cap=None)
    long_v1 = sum(1 for x, en in zip(v1, entries) if x.exit_j - en.e > S.HOLD_CAP)
    L.append(f"B-V1 (v1 exits unchanged, HOLD): trades held longer than the {S.HOLD_CAP}-bar cap: {long_v1} of {len(entries)} "
             f"(G2 parity runs B-V1 WITHOUT the cap; 0 here means the cap cannot affect it).")
    L.append("")
    for scen in S.SCENARIOS:
        L.append(f"== scenario {scen}")
        for rid in (S.BASELINE,) + S.SCORED + S.VARIANTS:
            ex = st.run(rid, scen)
            typ = Counter(x.reason for x in ex)
            fired = Counter(f for x in ex for f in x.fired)
            L.append(f"{rid}: exits by type {dict(sorted(typ.items()))}; triggers reached {dict(sorted(fired.items()))}; "
                     f"exit bar also raised a ratchet / trail (stop counted first, G5): {sum(x.stop_and_raise_same_bar for x in ex)}")
            if rid in S.TRIGGER:
                names = S.TRIGGER[rid]
                hit = np.array([any(n in x.fired for n in names) for x in ex])
                per = {int(y): int(hit[ey == y].sum()) for y in sorted(set(ey))}
                tot = int(hit.sum())
                tag = "" if tot >= S.NOT_READ_BELOW else f"   BELOW {S.NOT_READ_BELOW}: this rule set will be NOT READ"
                L.append(f"    trades reaching the trigger ({'/'.join(names)}): {tot} of {len(ex)}; per entry year {per}{tag}")
        L.append("")
    L.append("STOP RULE (sec 12): a rule set whose trigger fires on fewer than 200 trades is NOT READ; the others run.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("EXIT-CMP count-only pre-flight (G3, G6, G7)")
    ap.add_argument("--frame-cache", help="load the training frame from this .npz (var/clone_frame_w15_0050.npz) instead of the archive")
    ap.add_argument("--rewrite-ledger", action="store_true", help="only before the outcome run, e.g. after a PRE-RUN amendment")
    a = ap.parse_args(argv)
    out = Path(a.out)
    fr = load_frame_cache(Path(a.frame_cache)) if a.frame_cache else load_training_frame(RC.archive_path(a.archive))
    ind = indicators(fr)
    entries = EN.entry_set(fr, ind)
    per_year = EN.check_registered(fr, entries)
    st = Study(fr, ind, entries)
    stamp = date.today().strftime("%Y%m%d")
    text = counts_report(st, entries, per_year, stamp)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"w15_0053_exit_cmp_preflight_{stamp}.txt"
    f.write_text(text, encoding="utf-8")
    print(text)
    LG.create(out, fr=fr, per_year=per_year, n_entries=len(entries), preflight_file=f.name, rewrite=a.rewrite_ledger)
    print(f"ledger written: {LG.path(out)}\nNEXT: python -m strategy.exit_cmp.parity   (G2), then the outcome run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
