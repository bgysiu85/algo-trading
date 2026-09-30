#!/usr/bin/env python3
"""TL-v1 CL 4-hour variant, TRAINING SIDE ONLY, reported only. W15-0027.

    python -m strategy.tl_v1_cl4h.run

Reads the CL 1-hour archive (strategy.htf.bars.load_1h) and writes into "D:\\Trading\\Claude outputs":
    w15_0027_tl_v1_cl4h_<stamp>.txt          the report
    w15_0027_tl_v1_cl4h_trades_<stamp>.csv   every trade, every spec, FIX book (1/3 MCL sleeves, 1 MCL alone)
    w15_0027_tl_v1_cl4h_books_<stamp>.csv    one row per spec/book/part
    w15_0027_tl_v1_cl4h_counts_<stamp>.csv   simulator counts
    w15_0027_tl_v1_cl4h_c3_<stamp>.csv       C3 draw totals
    w15_0027_tl_v1_cl4h_grid_<stamp>.csv     the 27 neighbour cells

The 1-hour frame is cut to sessions 2010-06-06 .. 2021-12-31 before any bar is built; --holdout
and --limit are refused (REGISTERED_tl_v1.md sec 6: the TL-v1 holdout is not spent by this study).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.tl_v1_cl4h import engine as E
from strategy.tl_v1_cl4h import report as Rp

ROOT = Path(__file__).resolve().parents[2]
REGISTERED_DRAWS = 1000


class RunRefused(SystemExit):
    pass


def run(df_1h: pd.DataFrame, out_dir: Path, stamp: str, *, draws=REGISTERED_DRAWS, log=print) -> Path:
    t0 = time.time()
    frame, daily = E.build_frames(df_1h)
    log(f"bars: {len(frame)} 4H, {len(daily)} daily ({time.time() - t0:.0f}s)")
    ctx = E.Ctx4H(frame, daily)
    res, counts, gates = E.run_all(ctx)
    log(f"variants + controls C1/C2 ({time.time() - t0:.0f}s)")
    c3 = E.run_c3(ctx, draws, progress=lambda d: log(f"  C3 draw {d} ({time.time() - t0:.0f}s)"))
    grid = E.run_grid(ctx, progress=lambda i: log(f"  grid cell {i}/27 ({time.time() - t0:.0f}s)"))
    text, extra = Rp.render(frame, daily, res, counts, gates, c3, grid, scoped=(draws != REGISTERED_DRAWS))
    out_dir.mkdir(parents=True, exist_ok=True)
    p = lambda name: out_dir / f"w15_0027_tl_v1_cl4h_{name}_{stamp}"
    rep = p("").with_name(f"w15_0027_tl_v1_cl4h_{stamp}.txt")
    rep.write_text(text, encoding="utf-8")
    rows = []
    for spec, books in res.items():
        fx = books["FIX"]
        parts = {"single": fx} if spec == "C1" else {f"R{R}_{t}": d for (R, t), d in fx.items()}
        for part, df in parts.items():
            if len(df):
                rows.append(df.assign(spec=spec, part=part))
    pd.concat(rows, ignore_index=True).to_csv(p("trades").with_suffix(".csv"), index=False, encoding="utf-8")
    extra["summary"].to_csv(p("books").with_suffix(".csv"), index=False, encoding="utf-8")
    counts.to_csv(p("counts").with_suffix(".csv"), index=False, encoding="utf-8")
    pd.DataFrame({"draw": range(len(c3["totals"])), "net_mid": c3["totals"]}).to_csv(
        p("c3").with_suffix(".csv"), index=False, encoding="utf-8")
    grid.to_csv(p("grid").with_suffix(".csv"), index=False, encoding="utf-8")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--c3-draws", type=int, default=REGISTERED_DRAWS)
    ap.add_argument("--holdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.holdout:
        raise RunRefused("the TL-v1 holdout is not spent by this runner or by this study "
                         "(REGISTERED_tl_v1.md sec 2.5, sec 6).")
    if a.limit is not None:
        raise RunRefused("--limit is refused: a narrowed sample is not the registered sample.")
    from common.tsmom_fetch import default_archive
    from strategy.htf import bars as HB
    df_1h = HB.load_1h(a.archive or default_archive())
    rep = run(df_1h, a.out_dir, a.stamp, draws=a.c3_draws)
    print(f"report: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
