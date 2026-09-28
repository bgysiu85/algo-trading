#!/usr/bin/env python3
"""TL-bounce backtest, TRAINING SIDE ONLY. W15-0016.
REGISTERED_tl_bounce.md sec 3-4.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_bounce.run

Reads the GLBX archive (default: common.tsmom_fetch.default_archive(), the
same one G2/HTF-Ben/TSMOM read), writes into "D:\\Trading\\Claude outputs":

    tl_bounce_backtest_<date>.txt          sec 3 report + sec 4 verdict,
                                            both entry charts, all 4 built
                                            variants, all 3 friction levels
    tl_bounce_backtest_trades_<date>.csv   every simulated "bounce" trade
                                            (4H, training side, every level)

THE HOLDOUT
-----------
Same convention as preflight.py (G2, already delivered): this runner never
reports or scores a trade whose own session falls on or after
common.tl_bounce_holdout.LOCK_FROM. It does NOT cut the archive on load
(G2's own established pattern for this study) -- --holdout and --limit are
refused outright, and spending the holdout is a distinct, later, registered
step (common.tl_bounce_holdout.split_dates(spend=True, candidate="TL-bounce"),
sec 6), not something this runner can trigger.

WHAT IS SCORED, AND WHAT IS ONLY REPORTED
------------------------------------------
sec 4's nine criteria are read on ONE book only: "bounce", 4-hour chart, 1
MCL, mid friction (net_high supplies criterion 7), training side. C1, C2
and the 27-cell grid are built ONLY for that same book (sec 4's own scope).
Every other variant/chart/level combination sec 3 requires is still
computed and printed, just never scored against sec 4 (sec 2.5's own
header: "never ranked, cannot spend the holdout").
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.htf import bars as B
from strategy.htf import book as BK
from strategy.tl_bounce import controls as CT
from strategy.tl_bounce import engine as E
from strategy.tl_bounce import grid as G
from strategy.tl_bounce import report as Rp
from strategy.tl_bounce.preflight import (BUILT_VARIANTS, NOT_BUILT_CONTROLS,
                                          NOT_BUILT_VARIANTS, prepare_grids)
from strategy.tl_bounce.spec import LEVELS, TRAIN_END, TRAIN_START

ROOT = Path(__file__).resolve().parents[2]


class RunRefused(SystemExit):
    pass


def _training_only(trades: list) -> list:
    return [t for t in trades if TRAIN_START <= str(t.session)[:10] <= TRAIN_END]


def run(archive: Path, out_dir: Path, stamp: str, *, loader=None) -> Path:
    if loader is None:
        loader = B.load_1h
    df_1h = loader(archive)
    grids = prepare_grids(df_1h)
    hourly = B.back_adjust(B.resample(df_1h, "1H"))

    header_notes = [
        "Amendment 0 (PRE-RUN, 2026-09-26): board ids W01-0013/0016/0017 renumbered to "
        "W15-0014/0015/0016. Amendment 1 (POST-RUN, 2026-09-28): G3 closed, mismatches "
        "explained by a CL1! roll-timing difference between TradingView and this archive's "
        "held_id series (does not touch P&L). Both in REGISTERED_tl_bounce.md before this run.",
        "Known approximation, carried from G2 (sim.py/engine.py docstrings): bounce-once is "
        "coded as 'no re-entry at all', narrower than the registered 'one entry per line' -- "
        "common/tl_v0_lines.py has no line-identity to tell the two apart yet.",
    ]

    all_trades_csv = []
    primary_book = {}   # {level: trades}, "bounce" on 4H, training side

    text_parts = []
    verdict_crit = None

    for entry_chart, (entry_frame, higher_frame, higher_bar_hours) in grids.items():
        for variant, opts in BUILT_VARIANTS.items():
            trades, counts = E.simulate_market(entry_frame, higher_frame, higher_bar_hours,
                                               hourly, **opts)
            train_trades = _training_only(trades)
            for t in train_trades:
                all_trades_csv.append({
                    "entry_chart": entry_chart, "variant": variant, "session": t.session,
                    "direction": t.direction, "entry_t": t.entry_t, "fill_raw": t.fill_raw,
                    "stop_dist": t.stop_dist, "exit_t": t.exit_t,
                    "exit_price_raw": t.exit_price_raw, "exit_reason": t.exit_reason,
                    "trail_started": t.trail_started, "n_rolls": t.n_rolls,
                    "is_reentry": t.is_reentry,
                })
            if variant == "bounce" and entry_chart == "4H":
                primary_book = {lvl: train_trades for lvl in LEVELS}

    ef4, hf4, hh4 = grids["4H"]
    bounce_trades_4h_full, _ = E.simulate_market(ef4, hf4, hh4, hourly, **BUILT_VARIANTS["bounce"])
    bounce_train_4h = _training_only(bounce_trades_4h_full)

    c1_trades_full, _ = CT.run_c1(ef4)
    c1_trades = _training_only(c1_trades_full)

    c2_result = CT.run_c2(ef4, hourly, bounce_train_4h, seed_prefix="tl_bounce-")

    neighbour = G.run_grid(ef4, hf4, hh4, hourly)

    text, crit = Rp.render(
        symbol="MCL", qty=1, trades_by_level=primary_book, neighbour=neighbour,
        c1_trades=c1_trades, c2_result=c2_result,
        not_built={"variants": list(NOT_BUILT_VARIANTS), "controls": list(NOT_BUILT_CONTROLS)},
        header_notes=header_notes, stamp=stamp,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"tl_bounce_backtest_{stamp}.txt"
    rep.write_text(text, encoding="utf-8")
    pd.DataFrame(all_trades_csv).to_csv(out_dir / f"tl_bounce_backtest_trades_{stamp}.csv",
                                        index=False)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--holdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.holdout:
        raise RunRefused("the TL-bounce holdout is not spent by this runner. It is spent "
                         "once, by 'TL-bounce' only, via common.tl_bounce_holdout.split_dates"
                         "(spend=True) in a separate registered step after the training "
                         "verdict (REGISTERED_tl_bounce.md section 6).")
    if a.limit is not None:
        raise RunRefused("--limit is refused (REGISTERED_tl_bounce.md section 6): a narrowed "
                         "sample is not the registered sample.")

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()
    rep = run(archive, a.out_dir, a.stamp)
    print(f"report: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
