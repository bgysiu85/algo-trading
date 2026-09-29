#!/usr/bin/env python3
"""TL-v1 backtest, TRAINING SIDE ONLY. W15-0020.

    python -m strategy.tl_v1.run
    python -m strategy.tl_v1.run --markets CL GC     # scoped: banner says NOT the result

Writes into "D:\\Trading\\Claude outputs":
    tl_v1_backtest_<date>.txt            sec 3 report + sec 4 verdict
    tl_v1_backtest_trades_<date>.csv     every simulated trade, every book
    tl_v1_backtest_books_<date>.csv      one row per book
    tl_v1_backtest_counts_<date>.csv     simulator counts per market / sleeve / sizing
    tl_v1_backtest_breaks_<date>.csv     one row per raw break: touches, span, ER, which gate it failed
    tl_v1_backtest_c3_<date>.csv         C3 draw totals
    tl_v1_backtest_grid_<date>.csv       the 27 neighbour cells

THE HOLDOUT: bars come from strategy.tl_v0.bars.load_market, which cuts 2022-01-01 onward
before any bar is built (same cut the TL-v1 pre-flight used; both ledgers lock the same
training window). This runner has no path to the holdout: --holdout and --limit are refused.
The TL-v1 holdout is spent, once, by a separate step only if the training verdict passes
all ten criteria (REGISTERED_tl_v1.md sec 6).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from strategy.tl_v0 import bars as B
from strategy.tl_v0.spec import MARKETS
from strategy.tl_v1 import controls as K
from strategy.tl_v1 import engine as E
from strategy.tl_v1 import report as Rp

ROOT = Path(__file__).resolve().parents[2]
REGISTERED_DRAWS = 1000


class RunRefused(SystemExit):
    pass


def default_archive() -> Path:
    from common.tsmom_fetch import default_archive as da, DATASET
    return da() / DATASET


def latest_c2_books(out_dir: Path) -> Path | None:
    hits = sorted(out_dir.glob("tl_v0_backtest_books_*.csv"))
    return hits[-1] if hits else None


def run(archive: Path, markets: list[str], out_dir: Path, stamp: str, *, draws=REGISTERED_DRAWS,
        c2_books: Path | None = None, loader=None, log=print) -> Path:
    """`loader(market) -> (MarketBars, c0)` is injectable for tests."""
    if loader is None:
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        loader = lambda name: B.load_market(archive, MARKETS[name])
    t0 = time.time()
    runs, ctxs = [], {}
    for name in markets:
        mb, _c0 = loader(name)
        r, ctx = E.run_market(mb, MARKETS[name])
        runs.append(r)
        ctxs[name] = ctx
        log(f"{name}: {mb.n} sessions, {len(r.trades)} trade rows ({time.time() - t0:.0f}s)")
    calendar = pd.DatetimeIndex(sorted(set().union(*[set(r.dates) for r in runs])))
    log(f"C3: {draws} draws ...")
    c3 = K.run_c3(ctxs, draws, progress=lambda d: log(f"  C3 draw {d} ({time.time() - t0:.0f}s)"))
    log("27-cell grid ...")
    grid = K.run_grid(ctxs, progress=lambda i: log(f"  grid cell {i}/27 ({time.time() - t0:.0f}s)"))
    c2 = Rp.load_c2_reference(c2_books) if c2_books else None
    scoped = sorted(markets) != sorted(MARKETS) or draws != REGISTERED_DRAWS
    notes = [f"Markets ({len(markets)}): {', '.join(markets)}.",
             "Sec 2.2 line + sec 2.3 A+ checklist on TL-v0-rev's safety line, weekly filter, reversal, sizing and costs.",
             "A3 thresholds: per-market q25 of ER(20) on the training bars (Amendment E, PRE-RUN)."]
    text, summary = Rp.render(runs, ctxs, calendar, c3=c3, grid=grid, c2ref=c2, scoped=scoped, notes=notes)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"tl_v1_backtest_{stamp}.txt"
    rep.write_text(text, encoding="utf-8")
    pd.concat([r.trades for r in runs], ignore_index=True).to_csv(
        out_dir / f"tl_v1_backtest_trades_{stamp}.csv", index=False, encoding="utf-8")
    summary.to_csv(out_dir / f"tl_v1_backtest_books_{stamp}.csv", index=False, encoding="utf-8")
    pd.concat([r.counts for r in runs], ignore_index=True).to_csv(
        out_dir / f"tl_v1_backtest_counts_{stamp}.csv", index=False, encoding="utf-8")
    pd.concat([r.events for r in runs if len(r.events)], ignore_index=True).to_csv(
        out_dir / f"tl_v1_backtest_breaks_{stamp}.csv", index=False, encoding="utf-8")
    pd.DataFrame({"draw": range(len(c3["totals"])), "net_mid": c3["totals"]}).to_csv(
        out_dir / f"tl_v1_backtest_c3_{stamp}.csv", index=False, encoding="utf-8")
    grid.to_csv(out_dir / f"tl_v1_backtest_grid_{stamp}.csv", index=False, encoding="utf-8")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--markets", nargs="+", default=list(MARKETS), choices=list(MARKETS))
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--c3-draws", type=int, default=REGISTERED_DRAWS)
    ap.add_argument("--c2-books", type=Path, default=None,
                    help="W15-0014 tl_v0_backtest_books_*.csv (default: newest in --out-dir)")
    ap.add_argument("--holdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    a.markets = list(dict.fromkeys(a.markets))
    if a.holdout:
        raise RunRefused("the TL-v1 holdout is not spent by this runner. It is spent once, by TL-v1 "
                         "only, after a training verdict that passes all ten criteria "
                         "(REGISTERED_tl_v1.md sec 6).")
    if a.limit is not None:
        raise RunRefused("--limit is refused (REGISTERED_tl_v1.md sec 6): a narrowed sample is not "
                         "the registered sample.")
    c2 = a.c2_books or latest_c2_books(a.out_dir)
    rep = run(a.archive or default_archive(), a.markets, a.out_dir, a.stamp,
              draws=a.c3_draws, c2_books=c2)
    print(f"report: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
