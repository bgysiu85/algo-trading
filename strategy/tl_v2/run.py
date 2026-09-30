#!/usr/bin/env python3
"""TL-v2 backtest, TRAINING SIDE ONLY. Board: W15-0049 (this runner), W15-0031 (the run and Result doc).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_v2.run
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_v2.run --markets CL GC --c3-draws 50   # scoped

THE STOP RULE COMES FIRST (REGISTERED_tl_v2.md sec 5). This runner computes P&L, so it refuses to start
until the count-only pre-flight (W15-0048: python -m strategy.tl_v2.preflight) has been run on ALL 12
markets and shows at least 150 retest entries (N = 10, three pivot sizes). It looks for the newest
`w15_0030_tl_v2_preflight_*.csv` in --out-dir (or the file given by --preflight-csv). No such file, a
scoped pre-flight, or fewer than 150 entries -> refused, with the reason. There is no override flag:
under 150 entries the study stops as underpowered and goes back to Ben (sec 5).

Writes into "D:\\Trading\\Claude outputs":
    w15_0031_tl_v2_backtest_<date>.txt           sec 3 report + sec 4 verdict
    w15_0031_tl_v2_backtest_trades_<date>.csv    every simulated trade, every book (IBKR net low/mid/high)
    w15_0031_tl_v2_backtest_books_<date>.csv     one row per book
    w15_0031_tl_v2_backtest_counts_<date>.csv    simulator counts per market / sleeve / sizing
    w15_0031_tl_v2_backtest_events_<date>.csv    one row per qualified break: outcome, bars to retest
    w15_0031_tl_v2_backtest_c3_<date>.csv        C3 draw totals
    w15_0031_tl_v2_backtest_grid_<date>.csv      the 27 neighbour cells

THE HOLDOUT: bars come from strategy.tl_v0.bars.load_market, which cuts 2022-01-01 onward before any bar
is built (the same cut the TL-v2 pre-flight used; strategy/tl_v2/holdout.py locks the same window).
This runner has no path to the holdout: --holdout and --limit are refused, it never imports the ledger's
spend path, and the TL-v2 holdout is spent once, by a separate step, only if all ten criteria pass with
criterion 6 at p99 (sec 6).
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
from strategy.tl_v2 import controls as K
from strategy.tl_v2 import engine as E
from strategy.tl_v2 import report as Rp

ROOT = Path(__file__).resolve().parents[2]
REGISTERED_DRAWS = 1000
STOP_RULE_MIN_ENTRIES = 150
PREFLIGHT_GLOB = "w15_0030_tl_v2_preflight_*.csv"
OUT_PREFIX = "w15_0031_tl_v2_backtest"


class RunRefused(SystemExit):
    pass


def default_archive() -> Path:
    from common.tsmom_fetch import default_archive as da, DATASET
    return da() / DATASET


def latest_preflight_csv(out_dir: Path) -> Path | None:
    hits = sorted(out_dir.glob(PREFLIGHT_GLOB))
    return hits[-1] if hits else None


def check_stop_rule(csv: Path | None) -> int:
    """Sec 5. Returns the pre-flight's primary retest-entry total, or refuses to start."""
    if csv is None or not Path(csv).exists():
        raise RunRefused("no TL-v2 pre-flight found (w15_0030_tl_v2_preflight_*.csv). Run the count-only "
                         "pre-flight first (W15-0048: python -m strategy.tl_v2.preflight) and read its "
                         "stop-rule line (REGISTERED_tl_v2.md sec 5). This runner computes P&L and will "
                         "not start without it.")
    df = pd.read_csv(csv, encoding="utf-8")
    prim = df[df["N"] == 10]
    missing = sorted(set(MARKETS) - set(prim["market"]))
    if missing:
        raise RunRefused(f"the pre-flight {Path(csv).name} is scoped: markets missing {missing}. The stop "
                         f"rule is read on all 12 markets (sec 5). Re-run the pre-flight without --markets.")
    total = int(prim["entries"].sum())
    if total < STOP_RULE_MIN_ENTRIES:
        raise RunRefused(f"STOP RULE HIT: the pre-flight {Path(csv).name} shows {total} retest entries "
                         f"(< {STOP_RULE_MIN_ENTRIES}). Underpowered as registered; the study stops and goes "
                         f"back to Ben before any P&L (REGISTERED_tl_v2.md sec 5). No parameter is changed "
                         f"to fix it and no variant is swapped in.")
    return total


def run(archive: Path, markets: list[str], out_dir: Path, stamp: str, *, draws=REGISTERED_DRAWS,
        preflight_csv: Path | None = None, loader=None, log=print) -> Path:
    """`loader(market) -> (MarketBars, c0)` is injectable for tests."""
    preflight_total = check_stop_rule(preflight_csv if preflight_csv else latest_preflight_csv(out_dir))
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
    scoped = sorted(markets) != sorted(MARKETS) or draws != REGISTERED_DRAWS
    notes = [f"Markets ({len(markets)}): {', '.join(markets)}.",
             "TL-v1's line, A1-A3, weekly filter, safety line, exits, sizing and series; only the entry timing "
             "is new (T1-T5, N = 10). Costs: IBKR (Amendment 1).",
             "A3 thresholds: per-market q25 of ER(20) on the training bars (TL-v1 Amendment E)."]
    text, summary = Rp.render(runs, ctxs, calendar, c3=c3, grid=grid, scoped=scoped, notes=notes,
                              preflight_total=preflight_total)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"{OUT_PREFIX}_{stamp}.txt"
    rep.write_text(text, encoding="utf-8")
    pd.concat([r.trades for r in runs], ignore_index=True).to_csv(
        out_dir / f"{OUT_PREFIX}_trades_{stamp}.csv", index=False, encoding="utf-8")
    summary.to_csv(out_dir / f"{OUT_PREFIX}_books_{stamp}.csv", index=False, encoding="utf-8")
    pd.concat([r.counts for r in runs], ignore_index=True).to_csv(
        out_dir / f"{OUT_PREFIX}_counts_{stamp}.csv", index=False, encoding="utf-8")
    ev = Rp.load_events(runs)
    ev.to_csv(out_dir / f"{OUT_PREFIX}_events_{stamp}.csv", index=False, encoding="utf-8")
    pd.DataFrame({"draw": range(len(c3["totals"])), "net_mid": c3["totals"]}).to_csv(
        out_dir / f"{OUT_PREFIX}_c3_{stamp}.csv", index=False, encoding="utf-8")
    grid.to_csv(out_dir / f"{OUT_PREFIX}_grid_{stamp}.csv", index=False, encoding="utf-8")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--markets", nargs="+", default=list(MARKETS), choices=list(MARKETS))
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--c3-draws", type=int, default=REGISTERED_DRAWS)
    ap.add_argument("--preflight-csv", type=Path, default=None,
                    help="the W15-0048 pre-flight csv (default: newest in --out-dir)")
    ap.add_argument("--holdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    a.markets = list(dict.fromkeys(a.markets))
    if a.holdout:
        raise RunRefused("the TL-v2 holdout is not spent by this runner. It is spent once, by TL-v2 only, "
                         "after a training verdict that passes all ten criteria with criterion 6 at p99 "
                         "(REGISTERED_tl_v2.md sec 6).")
    if a.limit is not None:
        raise RunRefused("--limit is refused (REGISTERED_tl_v2.md sec 6): a narrowed sample is not "
                         "the registered sample.")
    rep = run(a.archive or default_archive(), a.markets, a.out_dir, a.stamp,
              draws=a.c3_draws, preflight_csv=a.preflight_csv)
    print(f"report: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
