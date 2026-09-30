#!/usr/bin/env python3
"""CHARTMARK-S v3 G2: count-only pre-flight, training side, by tier and per year. NO exit price, NO P&L.

    python -m strategy.chartmark_s3.preflight
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from strategy.chartmark_s2 import preflight as P2
from strategy.chartmark_s3 import engine as E
from strategy.chartmark_s3 import spec as S
from strategy.chartmark_s3.data import context_tiers, indicators, load_training_frame
from strategy.futbt import runner_common as RC

STOP_RULE = 150
NAME = "CHARTMARK-S v3"


def report(fr, blocks, share, stamp) -> str:
    txt = P2.report(fr, blocks, share, stamp, name=NAME)
    return txt.replace("Registered prediction (sec 10): 400-1,500 base fills; V-A fewest, V-B most.",
                       "Registered prediction (v3 sec 10): 4,300-6,000 base fills, Tier A still about 3,000.")


def run(archive, out_dir: Path, stamp: str, log=print) -> Path:
    fr = load_training_frame(archive)
    ind = indicators(fr)
    log(f"training frame: {fr.n} 1H bars {fr.ny[0]} .. {fr.ny[-1]}")
    blocks = {n: P2.counts_table(fr, *E.simulate(fr, ind, p)) for n, p in S.VARIANTS.items()}
    text = report(fr, blocks, P2.context_share(fr, ind, S.BASE, ctx_fn=context_tiers), stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"w15_0042_chartmark_short_v3_preflight_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    log(text)
    return path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-S v3 count-only pre-flight (training side).")
    a = ap.parse_args(argv)
    if a.markets:
        raise SystemExit("--markets is not a CHARTMARK-S option (CL only).")
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
