#!/usr/bin/env python3
"""TL-v2 count-only pre-flight: REGISTERED_tl_v2.md sec 5, gate G2. Board: W15-0030.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_v2.preflight

TRAINING SIDE ONLY (2010-06-01 .. 2021-12-31: strategy.tl_v0.bars cuts the holdout before any bar is
built). NO EXIT PRICE IS READ AND NO P&L IS COMPUTED. This module never calls the simulator; it counts
what happens to each qualified break (entry / failed / no retest / ...) and whether an entry could be
sized. The sizing read uses the stop known at the signal bar and the next open (the fill), nothing later.
Every output column is checked against a whitelist and against forbidden words (exit, pnl, net, gross,
return ...); --holdout, --limit and any P&L/exit flag are refused.

STOP RULE, fixed in sec 5 before any count: fewer than 150 TL-v2 retest entries on the training side
(all markets, the three pivot sleeves, N = 10) -> stop as underpowered, report as the finding, back to
Ben before any P&L. No parameter is changed to fix it.

Writes into "D:\\Trading\\Claude outputs":
    w15_0030_tl_v2_preflight_<date>.txt   the report
    w15_0030_tl_v2_preflight_<date>.csv   counts per market x pivot size x break year x N
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.tl_v0.spec import EQUITY, MARKETS, PIVOT_SIZES, RISK_PCT
from strategy.tl_v1.signals import REGISTERED_ER_Q25, MarketCtx
from strategy.tl_v2.signals import size_entry, v2_input

ROOT = Path(__file__).resolve().parents[2]
STOP_RULE_MIN_ENTRIES = 150
NS = (10, 20)                      # 10 = the registered primary, 20 = the reported window variant

COLUMNS = ("market", "R", "N", "year", "qualified", "ignored_pending", "failed", "no_retest",
           "open_at_end", "entries", "entries_sr", "no_stop", "void", "sizeable_sleeve",
           "sizeable_full", "median_bars_to_retest")
FORBIDDEN = ("exit", "pnl", "p&l", "net", "gross", "return", "profit", "slip", "hold", "drawdown")


class PreflightRefused(SystemExit):
    pass


def assert_count_only(columns) -> None:
    """Refuse any output column that names an exit, a P&L or a return."""
    bad = [c for c in columns if any(w in str(c).lower() for w in FORBIDDEN)]
    if bad:
        raise PreflightRefused(f"the pre-flight is count-only (REGISTERED_tl_v2.md sec 5, G2): "
                               f"refusing output column(s) {bad}")
    extra = [c for c in columns if c not in COLUMNS]
    if extra:
        raise PreflightRefused(f"unregistered pre-flight column(s) {extra}")


def market_rows(ctx: MarketCtx, m) -> list[dict]:
    rows = []
    risk_sleeve = RISK_PCT * EQUITY / len(PIVOT_SIZES)
    risk_full = RISK_PCT * EQUITY
    for R in PIVOT_SIZES:
        for N in NS:
            x, sig = v2_input(ctx, R, N=N)
            ev = sig.scan.events
            if not len(ev):
                continue
            ev = ev.assign(year=[int(ctx.dates[t].year) for t in ev["t"]])
            ent = ev[ev["outcome"] == "entry"].copy()
            sized = {"sleeve": [], "full": []}
            for _, e in ent.iterrows():
                for k, risk in (("sleeve", risk_sleeve), ("full", risk_full)):
                    sized[k].append(size_entry(x, int(e["s"]), int(e["direction"]),
                                               mult=m.mult, risk_usd=risk))
            ent["status_sleeve"] = [z["status"] for z in sized["sleeve"]]
            ent["status_full"] = [z["status"] for z in sized["full"]]
            for year, g in ev.groupby("year"):
                ge = ent[ent["year"] == year]
                cnt = g["outcome"].value_counts()
                rows.append(dict(
                    market=m.name, R=R, N=N, year=int(year),
                    qualified=int((g["outcome"] != "ignored_pending").sum()),
                    ignored_pending=int(cnt.get("ignored_pending", 0)),
                    failed=int(cnt.get("failed", 0)), no_retest=int(cnt.get("no_retest", 0)),
                    open_at_end=int(cnt.get("open_at_end", 0)), entries=int(len(ge)),
                    entries_sr=int(ge["sr_ok"].eq(True).sum()),
                    no_stop=int((ge["status_sleeve"] == "no_stop").sum()),
                    void=int((ge["status_sleeve"] == "void").sum()),
                    sizeable_sleeve=int((ge["status_sleeve"] == "sizeable").sum()),
                    sizeable_full=int((ge["status_full"] == "sizeable").sum()),
                    median_bars_to_retest=float(ge["bars_to_retest"].median()) if len(ge) else np.nan))
    return rows


def er_check(ctx: MarketCtx) -> tuple[float, float]:
    return ctx.er_thr[0.25], REGISTERED_ER_Q25.get(ctx.name, float("nan"))


def build_report(df: pd.DataFrame, er_rows: list[tuple], markets: list[str], scoped: bool) -> str:
    L: list[str] = []
    p = L.append
    p("TL-v2 PRE-FLIGHT -- REGISTERED_tl_v2.md sec 5, gate G2 (W15-0030)")
    p("Training side only (2010-06-01 .. 2021-12-31). NO EXIT PRICE READ, NO P&L COMPUTED.")
    if scoped:
        p("*** SCOPED RUN (not all 12 markets): NOT the registered pre-flight; the stop rule is not read. ***")
    p(f"Markets ({len(markets)}): {', '.join(markets)}.")
    p("Lines, A1-A3, weekly filter, safety line: TL-v1's (unchanged). Only the entry timing is new (T1-T5).")
    p("")
    if df.empty:
        p("No qualified break on any market.")
        return "\n".join(L)
    prim = df[df["N"] == 10]
    tot = int(prim["entries"].sum())
    p("=" * 78)
    p("1. WHAT HAPPENED TO EACH QUALIFIED BREAK (primary, N = 10, all markets)")
    p("=" * 78)
    s = prim.groupby("R")[["qualified", "entries", "failed", "no_retest", "open_at_end",
                           "ignored_pending"]].sum()
    s.loc["all"] = s.sum()
    p(s.to_string())
    q = int(s.loc["all", "qualified"])
    p("")
    p(f"TOTAL TL-v2 retest entries (all markets, three pivot sleeves, N = 10): {tot}"
      f"  ({(100 * tot / q if q else 0):.0f}% of {q} qualified breaks)")
    p(f"Stop rule (sec 5): fewer than {STOP_RULE_MIN_ENTRIES} entries -> stop as underpowered, report as the")
    p("finding, back to Ben before any P&L. No parameter is changed to fix it.")
    if scoped:
        p("Not read (scoped run).")
    elif tot < STOP_RULE_MIN_ENTRIES:
        p(f"*** STOP RULE HIT: {tot} < {STOP_RULE_MIN_ENTRIES}. Underpowered as registered. Back to Ben. ***")
    else:
        p(f"Clears the stop rule ({tot} >= {STOP_RULE_MIN_ENTRIES}).")
    p("")
    p("=" * 78)
    p("2. SIZEABLE SHARE (integer contracts >= 1 at 1% of $22,129; stop from the signal bar, fill = next open)")
    p("=" * 78)
    ent = prim[["entries", "no_stop", "void", "sizeable_sleeve", "sizeable_full"]].sum()
    n = max(int(ent["entries"]), 1)
    p(f"entries {int(ent['entries'])}: no usable stop {int(ent['no_stop'])}, void (open through the stop) "
      f"{int(ent['void'])}")
    p(f"sizeable as an ensemble sleeve (1/3 risk): {int(ent['sizeable_sleeve'])} ({100 * ent['sizeable_sleeve'] / n:.0f}%)")
    p(f"sizeable alone (full 1% risk):             {int(ent['sizeable_full'])} ({100 * ent['sizeable_full'] / n:.0f}%)")
    p("(the backtest counts the entries it skips for size; sec 3)")
    p("")
    p("=" * 78)
    p("3. PER MARKET (primary, N = 10, three sleeves summed)")
    p("=" * 78)
    pm = prim.groupby("market").agg(qualified=("qualified", "sum"), entries=("entries", "sum"),
                                    failed=("failed", "sum"), no_retest=("no_retest", "sum"),
                                    sizeable_sleeve=("sizeable_sleeve", "sum"),
                                    median_bars=("median_bars_to_retest", "median"))
    p(pm.to_string())
    p("")
    p("=" * 78)
    p("4. PER BREAK YEAR (primary, N = 10, all markets, three sleeves summed)")
    p("=" * 78)
    py = prim.groupby("year")[["qualified", "entries", "failed", "no_retest"]].sum()
    p(py.to_string())
    p("")
    p("=" * 78)
    p("5. PER PIVOT SIZE (primary, N = 10)")
    p("=" * 78)
    p(prim.groupby("R")[["qualified", "entries", "failed", "no_retest", "sizeable_sleeve"]].sum().to_string())
    p("")
    p("=" * 78)
    p("6. REPORTED VARIANTS (never ranked; cannot spend the holdout)")
    p("=" * 78)
    v20 = int(df[df["N"] == 20]["entries"].sum())
    sr = int(prim["entries_sr"].sum())
    p(f"N = 20:        {v20} retest entries")
    p(f"S/R variant:   {sr} retest entries where a horizontal zone coincides (of {tot}); "
      f"{'below' if sr < STOP_RULE_MIN_ENTRIES else 'at or above'} the {STOP_RULE_MIN_ENTRIES}-trade floor.")
    p("Sec 2.3 expected the S/R variant to be NOT READ. No variant may be swapped in to rescue the primary's count.")
    p("")
    p("=" * 78)
    p("7. A3 THRESHOLDS: computed on the training bars vs the registered TL-v1 q25 (should agree)")
    p("=" * 78)
    for name, cur, reg in er_rows:
        flag = "" if abs(cur - reg) <= 0.0006 else "   <-- DIFFERS"
        p(f"  {name}: computed {cur:.3f}  registered {reg:.3f}{flag}")
    p("")
    p("=" * 78)
    p("8. WHAT THIS RUN DOES NOT ANSWER")
    p("=" * 78)
    p("No exit, no return, no P&L, no win rate, no hold time. Whether waiting for the retest helps or hurts")
    p("is the backtest's question (W15-0031), and only after this stop rule has been read.")
    return "\n".join(L)


def run(archive, markets: list[str], out_dir: Path, stamp: str, *, loader=None, log=print) -> Path:
    """`loader(name) -> (MarketBars, c0)` is injectable for tests."""
    if loader is None:
        from strategy.tl_v0 import bars as B
        from strategy.tsmom import archive as A
        A.read_manifest(archive)
        loader = lambda name: B.load_market(archive, MARKETS[name])
    rows, er_rows = [], []
    for name in markets:
        mb, _c0 = loader(name)
        ctx = MarketCtx(mb, MARKETS[name])
        r = market_rows(ctx, MARKETS[name])
        rows += r
        cur, reg = er_check(ctx)
        er_rows.append((name, cur, reg))
        log(f"{name}: {mb.n} sessions, {sum(x['entries'] for x in r if x['N'] == 10)} retest entries (N = 10)")
    df = pd.DataFrame(rows, columns=list(COLUMNS))
    assert_count_only(df.columns)
    scoped = sorted(markets) != sorted(MARKETS)
    text = build_report(df, er_rows, markets, scoped)
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = out_dir / f"w15_0030_tl_v2_preflight_{stamp}.txt"
    rep.write_text(text + "\n", encoding="utf-8")
    df.to_csv(out_dir / f"w15_0030_tl_v2_preflight_{stamp}.csv", index=False, encoding="utf-8")
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--markets", nargs="+", default=list(MARKETS), choices=list(MARKETS))
    ap.add_argument("--out-dir", type=Path, default=ROOT / "Claude outputs")
    ap.add_argument("--stamp", default=date.today().strftime("%Y%m%d"))
    for flag in ("--holdout", "--pnl", "--exits", "--simulate"):
        ap.add_argument(flag, action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.holdout or a.limit is not None:
        raise PreflightRefused("the pre-flight reads the training side only and takes no --holdout or "
                               "--limit (REGISTERED_tl_v2.md sec 5-6).")
    if a.pnl or a.exits or a.simulate:
        raise PreflightRefused("the pre-flight is count-only: no exit price, no P&L, no simulation "
                               "(REGISTERED_tl_v2.md sec 5, G2).")
    if a.archive is None:
        from common.tsmom_fetch import DATASET, default_archive
        a.archive = default_archive() / DATASET
    a.markets = list(dict.fromkeys(a.markets))
    print(f"report: {run(a.archive, a.markets, a.out_dir, a.stamp)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
