#!/usr/bin/env python3
"""TL-v0 / TL-v0-rev step-4 backtest, TRAINING SIDE ONLY. W15-0014 subitem 2.

    python -m strategy.tl_v0.run
    python -m strategy.tl_v0.run --markets CL GC      # scoped: banner says NOT the result

Reads the GLBX archive (default: common.tsmom_fetch.default_archive() /
GLBX.MDP3, the same one the pre-flight and TSMOM read), writes into
"D:\\Trading\\Claude outputs":

    tl_v0_backtest_<date>.txt              the section 3 report + section 4 verdict
    tl_v0_backtest_trades_<date>.csv       every simulated trade, every book
    tl_v0_backtest_books_<date>.csv        one row per book (summary figures)
    tl_v0_backtest_counts_<date>.csv       per market / sleeve / sizing counts

THE HOLDOUT
-----------
This runner has no way to read 2022-01-01 onward: bars.training_sessions()
passes every date through common.tl_v0_holdout.split_dates (spend=False)
before a bar is built. Spending the holdout is a later, separate registered
step (v0-rev only, once) and is refused here, as is --limit.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.tl_v0 import bars as B
from strategy.tl_v0 import engine as E
from strategy.tl_v0 import report as Rp
from strategy.tl_v0.spec import MARKETS, PIVOT_SIZES

ROOT = Path(__file__).resolve().parents[2]


class RunRefused(SystemExit):
    pass


def default_archive() -> Path:
    from common.tsmom_fetch import default_archive as da, DATASET
    return da() / DATASET


def median_holds(runs: list) -> dict[str, int]:
    """C3's H: the median hold (sessions) of each TL rule set's ENSEMBLE
    trades, fractional sizing, pooled over markets."""
    t = pd.concat([r.trades for r in runs], ignore_index=True)
    out = {}
    if not len(t):
        return {"v0": 20, "v0-rev": 20}
    for rs in ("v0", "v0-rev"):
        sel = t[(t["spec"] == rs) & (t["share"] == "sleeve") & (t["sizing"] == "frac")]
        out[rs] = int(round(float(sel["hold"].median()))) if len(sel) else 20
    return out


def coverage_row(mb: B.MarketBars, c0: pd.Series, diag: dict) -> dict:
    from strategy.tsmom import rollcheck
    f = mb.frame
    gaps = int((f["date"].diff().dt.days > 5).sum())
    row = {"market": mb.market, **{k: mb.notes.get(k) for k in (
        "sessions", "first", "last", "rolls", "stale_bars", "roll_new_close_stale",
        "sunday_rows_folded", "sunday_rows_dropped", "saturday_rows_dropped", "unmapped_rows",
        "locked_rows_dropped_on_load")},
        "gaps_gt5d": gaps}
    try:
        tab = rollcheck.compare(c0, mb.schedule[["symbol", "expiration"]])
        v = rollcheck.verdict(tab)
        row["rollcheck"] = f"{v['result']} ({v['disagree_gt1']}/{v['rolls_compared']})"
    except Exception as exc:                       # reported, never silently dropped
        row["rollcheck"] = f"error: {exc.__class__.__name__}"
    for R in PIVOT_SIZES:
        row[f"brk~roll R{R}"] = f"{diag.get(f'breaks_within_3_of_roll_R{R}')}/{diag.get(f'breaks_R{R}')}"
    pvm = mb.notes.get("point_value_mismatch") or []
    row["pv_check"] = "ok" if not pvm else "; ".join(pvm)
    return row


def run(archive: Path, markets: list[str], out_dir: Path, stamp: str, *, loader=None) -> Path:
    """`loader(market) -> (MarketBars, c0)` is injectable for tests."""
    if loader is None:
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        loader = lambda name: B.load_market(archive, MARKETS[name])
    runs, cov = [], []
    for name in markets:
        m = MARKETS[name]
        mb, c0 = loader(name)
        r = E.run_market(mb, m)
        runs.append((mb, m, r))
        cov.append(coverage_row(mb, c0, r.diagnostics))
        print(f"{name}: {mb.n} sessions, {len(r.trades)} trade rows", flush=True)
    H = median_holds([r for _, _, r in runs])
    merged = []
    for mb, m, r in runs:
        r3 = E.run_market(mb, m, c3_hold=H)
        r.trades = pd.concat([r.trades, r3.trades], ignore_index=True)
        r.daily.update(r3.daily)
        r.counts = pd.concat([r.counts, r3.counts], ignore_index=True)
        merged.append(r)
    calendar = pd.DatetimeIndex(sorted(set().union(*[set(r.dates) for r in merged])))
    for row, r in zip(cov, merged):
        t = r.trades
        row["trades_stale_fill"] = int(t["stale_fill"].sum()) if len(t) else 0
        row["trades_stale_roll"] = int(t["stale_roll"].sum()) if len(t) else 0
    notes = [
        f"Markets ({len(markets)}): {', '.join(markets)}. Vehicles: "
        + ", ".join(f"{k}->{MARKETS[k].vehicle}" for k in markets) + ".",
        "Amendment A (PRE-RUN, 2026-09-28): Sunday UTC stub rows folded into the next session; "
        "12 markets, MTN the only rates market (Ben: \"12 markets, MTN only\"). Amendment B "
        "(PRE-RUN, 2026-09-28): verdict on the fractional book @ $22,129, integer printed beside "
        "it (Ben: \"Fractional @ $22,129\"). Both in REGISTERED_tl_v0.md before this run.",
    ]
    text, summary = Rp.render(merged, calendar, pd.DataFrame(cov).set_index("market"),
                              scoped=sorted(markets) != sorted(MARKETS), c3_hold=H,
                              header_notes=notes)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"tl_v0_backtest_{stamp}.txt"
    rep.write_text(text, encoding="utf-8")
    pd.concat([r.trades for r in merged], ignore_index=True).to_csv(
        out_dir / f"tl_v0_backtest_trades_{stamp}.csv", index=False)
    summary.to_csv(out_dir / f"tl_v0_backtest_books_{stamp}.csv", index=False)
    pd.concat([r.counts for r in merged], ignore_index=True).to_csv(
        out_dir / f"tl_v0_backtest_counts_{stamp}.csv", index=False)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--markets", nargs="+", default=list(MARKETS), choices=list(MARKETS))
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--holdout", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    a.markets = list(dict.fromkeys(a.markets))            # "CL CL" is one market, once
    if a.holdout:
        raise RunRefused("the TL-v0 holdout is not spent by this runner. It is spent once, by "
                         "v0-rev only, in a separate registered step after the training verdict "
                         "(REGISTERED_tl_v0.md section 6).")
    if a.limit is not None:
        raise RunRefused("--limit is refused (REGISTERED_tl_v0.md section 6): a narrowed sample "
                         "is not the registered sample.")
    rep = run(a.archive or default_archive(), a.markets, a.out_dir, a.stamp)
    print(f"report: {rep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
