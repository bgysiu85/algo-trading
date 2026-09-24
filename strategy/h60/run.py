#!/usr/bin/env python3
"""H60-v0 runner -- W14-0004 runs this on Ben's PC; W14-0003 built it.
REGISTERED_h60_v0.md §0, §4, §5, §7, §8.

    python -m strategy.h60.run --build-cache       # 1-min RTH -> 60-min parquet
    python -m strategy.h60.holdout --cut           # once; commit holdout_h60.json
    python -m strategy.h60.run --preflight         # §5: G2 + counts, NO P&L
    python -m strategy.h60.run --score             # §4.3 G7, then §7, training side

THE GATES, IN THE ORDER THIS FILE ENFORCES THEM
-----------------------------------------------
    grid (amendment B)   bars.GRID is None -> every path refuses
    G6 holdout cut       holdout.split_sessions refuses without the file
    G2 cross-source      --score reads the pre-flight's xcheck; STOP -> refuse
    G5 hindsight guards  run over every booked trade before any figure
    G7 positive control  run first inside --score; a fail prints nothing else
    G3 MR-60             rules.mr60 refuses -> "not run", verdict False
    G4 TL-60             rules.tl60 refuses -> "not run", DON carries trend
Nothing here spends the holdout. That is a separate, deliberate call
(holdout.split_sessions(spend=True, ...)) after Ben has read the result.

MONEY IN THE REPORT: negatives in brackets, as (1,234.56).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.h60 import bars as B
from strategy.h60 import basket as K
from strategy.h60 import controls as CT
from strategy.h60 import engine as E
from strategy.h60 import guards as G
from strategy.h60 import holdout as H
from strategy.h60 import rules as R
from strategy.h60 import score as SC
from strategy.h60 import xcheck as XC
from strategy.h60.panel import Panel, Universe

REPORT_DIR = Path("var/reports")
STATE_DIR = Path("var/h60")
PREFLIGHT_REPORT = REPORT_DIR / "h60_preflight.txt"
SCORE_REPORT = REPORT_DIR / "h60_training.txt"
XCHECK_STATE = STATE_DIR / "xcheck.json"
GUARD_SYMBOLS = 25          # symbols per book whose signals are re-run truncated
GUARD_CUTS = 25             # cut points per symbol


def money(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def archive_root(archive: str | None) -> Path:
    if archive:
        return Path(archive)
    from common.databento_fetch import default_archive
    from strategy.h60.data_plan import H60_SUBDIR
    return Path(default_archive()) / H60_SUBDIR


def session_list(archive: str | None = None) -> list:
    df = B.load_cache(archive_root(archive))
    return sorted(df["session"].unique())


def training_panel(archive: str | None = None, *, cut_path=None) -> Panel:
    from strategy.h60 import data_plan
    bars = B.load_cache(archive_root(archive))
    train, n_locked, side = H.split_sessions(sorted(bars["session"].unique()),
                                             path=cut_path or H.CUT_PATH)
    keep = bars["session"].isin(set(train))
    print(f"sessions: {len(train)} {side}; {n_locked} set aside", flush=True)
    return Panel.build(bars[keep], Universe(data_plan.load_universe()), B.require_grid())


# --------------------------------------------------------------------------
# books
# --------------------------------------------------------------------------

def run_books(panel: Panel, books=None, symbols=None) -> dict:
    """{book name: (trades, counts)}; a rule that refuses is ('not run', why)."""
    return E.run_books(panel, books or R.books(), symbols, progress=100)


def apply_xcheck(trades: pd.DataFrame, x: dict) -> tuple[pd.DataFrame, dict]:
    splits = {tuple(v) for v in x["split_days"]}
    excl = {tuple(v) for v in x["excluded_days"]}
    void = E.voids_from_splits(trades, splits)
    touch = E.touches_days(trades, excl) & ~void
    return trades[~void & ~touch].reset_index(drop=True), {
        "voided_split": int(void.sum()), "excluded_bad_day": int(touch.sum())}


def guard(panel: Panel, bk, trades: pd.DataFrame) -> dict:
    """G5 over the real book: membership and fills on every trade; the
    look-ahead check on a crc32-chosen sample of symbols and cut points."""
    G.check_membership(trades, panel)
    G.check_fills(trades, panel)
    syms = sorted(panel.symbols, key=lambda s: CT.seed("guard", bk.name, s))[:GUARD_SYMBOLS]
    fn = R.RULES[bk.rule]
    n = 0
    from strategy.h60.panel import slice_arrays
    for s in syms:
        # the longest segment: the series the engine actually ran the rule on
        st, en = max(panel.segment_bounds(s), key=lambda b: b[1] - b[0])
        a = slice_arrays(panel.arrays(s), st, en)
        if a.n < 100:
            continue
        rng = np.random.default_rng(CT.seed("guard-cuts", bk.name, s))
        cuts = sorted(rng.choice(np.arange(60, a.n - 1), min(GUARD_CUTS, a.n - 61), replace=False))
        n += G.check_no_lookahead(fn, a, cuts, bk.variant)
    return {"trades_checked": len(trades), "lookahead_cuts": n}


# --------------------------------------------------------------------------
# §5 pre-flight -- counts only
# --------------------------------------------------------------------------

def preflight_counts(panel: Panel, trades: pd.DataFrame, counts: Counter) -> list[str]:
    L = []
    if trades.empty:
        return ["    no trades"]
    years = pd.Series([d.year for d in trades["entry_session"]])
    sig_years = Counter(panel.sessions[s].year for s in trades["s_signal"])
    L.append("    trades per year      " + ", ".join(f"{y}: {n}" for y, n in sorted(years.value_counts().items())))
    L.append(f"    trades per session   {len(trades) / panel.n_sessions:.2f}")
    bod = trades["entry_slot"].value_counts().sort_index()
    L.append("    entries by bar       " + ", ".join(f"slot {k}: {v}" for k, v in bod.items()))
    L.append(f"    median hold (bars)   {trades['bars_held'].median():.0f}")
    tc = (trades["reason"] == "time_cap").mean()
    L.append(f"    exited by time cap   {tc:.1%}")
    L.append("    exit reasons         " + ", ".join(f"{k}: {v}" for k, v in trades["reason"].value_counts().items()))
    c = E.concurrency(trades)
    L.append(f"    max concurrent       {c['max_concurrent']} positions")
    L.append("    signal->trade        " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    thin = "TOO THIN TO JUDGE (< 300 training trades) -- not scored" if len(trades) < SC.MIN_TRADES else "ok"
    L.append(f"    >= 300 trades        {thin}")
    return L


def preflight(archive: str | None, eod_dir: Path = XC.EOD_DIR) -> int:
    panel = training_panel(archive)
    x = XC.run(panel, eod_dir)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    XCHECK_STATE.write_text(json.dumps({
        "split_days": sorted(x.split_days), "excluded_days": sorted(x.excluded_days),
        "bad_share": x.bad_share, "stop": x.stop,
        "excluded_codes": x.excluded_codes}, indent=0), encoding="utf-8")
    L = ["H60-v0 PRE-FLIGHT -- REGISTERED_h60_v0.md §5, training side, NO P&L",
         f"grid: {panel.grid}; sessions {panel.sessions[0]} -> {panel.sessions[-1]} "
         f"({panel.n_sessions})", "", XC.report(x, panel), "", "UNIVERSE"]
    names = [len(panel.eligible_symbols(s)) for s in range(panel.n_sessions)]
    L.append(f"  eligible names per session: median {int(np.median(names))}, "
             f"min {min(names)}, max {max(names)}")
    bps = panel.bars.groupby(["symbol", "s"]).size()
    L.append(f"  bars per symbol-day: median {bps.median():.0f}; share with 7: "
             f"{(bps == 7).mean():.1%}")
    unres = Counter()
    have = set(panel.symbols)
    for s in range(0, panel.n_sessions, 21):
        for sym in panel.universe.symbols_on(panel.sessions[s]):
            if sym not in have:
                unres[panel.sessions[s].year] += 1
    L.append("  eligible tickers with no bars, sampled monthly: "
             + (", ".join(f"{y}: {n}" for y, n in sorted(unres.items())) or "none"))
    if x.stop:
        L += ["", "STOPPED at §5.1: nothing below was computed."]
        from common.report_io import emit
        emit("\n".join(L), PREFLIGHT_REPORT, header="strategy.h60.run --preflight")
        return 2
    L += ["", "RULE SETS (counts only)"]
    for name, res in run_books(panel).items():
        L.append(f"  {name}")
        if isinstance(res[0], str):
            L.append(f"    NOT RUN -- {res[1]}")
            continue
        trades, counts = res
        kept, drop = apply_xcheck(trades, json.loads(XCHECK_STATE.read_text(encoding="utf-8")))
        L.append(f"    voided (split) {drop['voided_split']}, excluded (bad day) "
                 f"{drop['excluded_bad_day']}")
        L += preflight_counts(panel, kept, counts)
    from common.report_io import emit
    emit("\n".join(L), PREFLIGHT_REPORT, header="strategy.h60.run --preflight")
    return 0


# --------------------------------------------------------------------------
# §4.3 then §7 -- training side
# --------------------------------------------------------------------------

def score_all(archive: str | None, *, n_draws: int = CT.N_DRAWS) -> int:
    from common.report_io import emit
    if not XCHECK_STATE.exists():
        raise SystemExit("run --preflight first: G2 (§5.1) has not been read.")
    x = json.loads(XCHECK_STATE.read_text(encoding="utf-8"))
    if x["stop"]:
        raise SystemExit("G2 STOPPED at §5.1: diagnose the data path before any P&L.")
    panel = training_panel(archive)
    excl = {tuple(v) for v in x["excluded_days"]}
    splits = {tuple(v) for v in x["split_days"]}
    build = lambda p: K.build(p, excluded_days=excl, split_days=splits)
    L = ["H60-v0 TRAINING-SIDE RESULT -- REGISTERED_h60_v0.md §7, L2 scoring", ""]

    pc = CT.positive_control(panel, build, excluded_days=excl)
    L += ["§4.3 POSITIVE CONTROL (G7)",
          f"  planted: {pc['planted']['trades']} trades, market-relative gross "
          f"{money(pc['planted']['mr_gross_per_trade'])} per trade (want 20.00 +/- 2.00)",
          f"  null:    {pc['null']['trades']} trades, {money(pc['null']['mr_gross_per_trade'])} "
          "per trade (want 0.00 +/- 2.00)",
          f"  {'PASS' if pc['pass'] else 'FAIL'}"]
    if not pc["pass"]:
        L += ["", "G7 FAILED: the booking or the market-relative subtraction is wrong. "
              "Nothing in §7 is scored (§4.3)."]
        emit("\n".join(L), SCORE_REPORT, header="strategy.h60.run --score")
        return 2

    basket = build(panel)
    results = run_books(panel)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    scored: dict = {}
    L += ["", "BOOKS"]
    for bk in R.books():
        res = results[bk.name]
        if isinstance(res[0], str):
            L.append(f"  {bk.name}: NOT RUN -- {res[1]}")
            continue
        trades, counts = res
        trades, drop = apply_xcheck(trades, x)
        g = guard(panel, bk, trades)
        sc = SC.score(trades, basket, panel.grid)
        sc.to_csv(STATE_DIR / f"trades_{bk.name.replace('/', '_')}.csv", index=False)
        scored[bk.name] = (bk, sc, counts, drop, g)

    # the TL ensemble's scored book is the union of its sleeves
    for ens, parts in R.ENSEMBLES.items():
        if all(p in scored for p in parts):
            sc = pd.concat([scored[p][1] for p in parts], ignore_index=True)
            scored[ens] = (R.Book(ens, ens, "ensemble", True, 10_000.0), sc,
                           Counter(), {}, {})

    train = panel.sessions
    verdicts = {r: False for r in R.PRIORITY}
    evals: dict = {}
    don = None
    for name in [b for b in R.PRIORITY if b in scored] + \
            [n for n in scored if n not in R.PRIORITY]:
        bk, sc, counts, drop, g = scored[name]
        sleeves = 3 if name in R.ENSEMBLES else 1
        rc = {"p95": None}
        if bk.scored:
            if name in R.ENSEMBLES:
                pairs = [CT.price_pairs(panel, scored[p][0], basket, split_days=splits,
                                        excluded_days=excl) for p in R.ENSEMBLES[name]]
                allp = CT.Pairs(np.concatenate([q.sym for q in pairs]),
                                np.concatenate([q.s_sig for q in pairs]),
                                np.concatenate([q.mr_net for q in pairs]), pairs[0].names)
            else:
                allp = CT.price_pairs(panel, bk, basket, split_days=splits,
                                      excluded_days=excl)
            eps = sc.groupby("s_signal").size().to_dict()
            rc = CT.random_control(allp, eps, name, n_draws=n_draws)
            if sleeves == 3 and rc["p95"] is not None:
                rc["p95"] = rc["p95"] * 3            # per $10,000, like the book
        ev = SC.evaluate(sc, name=name, training_sessions=train, random_p95=rc["p95"],
                         sleeves=sleeves,
                         don_mr_per_trade=(don if name == "TL-60" else None))
        if name == "DON-60":
            don = ev["1_mr_net_per_trade_gt_0"]["value"]
        evals[name] = ev
        if bk.scored and name in verdicts:
            verdicts[name] = bool(ev["all_pass"])
        L += book_lines(name, bk, sc, counts, drop, g, ev, rc, sleeves)
        L.append(f"  §4.2 basket over the union of its holding windows: "
                 f"{SC.union_basket_return(sc, basket):+.2%}")

    L += ["", "VERDICTS (§8: the holdout may be spent only by the first True, in this order)"]
    for r in R.PRIORITY:
        L.append(f"  {r:<8} {'PASSES every §7 criterion' if verdicts[r] else 'does not pass'}")
    (STATE_DIR / "verdicts.json").write_text(json.dumps(
        {"verdicts": verdicts, "positive_control": pc,
         "evaluations": {k: {c: v for c, v in e.items()} for k, e in evals.items()}},
        indent=1, default=str), encoding="utf-8")
    emit("\n".join(L), SCORE_REPORT, header="strategy.h60.run --score")
    return 0


def book_lines(name, bk, sc, counts, drop, g, ev, rc, sleeves) -> list[str]:
    n = len(sc) / sleeves if sleeves else len(sc)
    per = lambda c: sc[c].sum() / n if n else float("nan")
    L = ["", f"== {name} {'(scored)' if bk.scored else '(reported, never scored)'} =="]
    if len(sc) == 0:
        return L + ["  no trades"]
    wins = int((sc["net_L2"] > 0).sum())
    L += [f"  trades {len(sc)}" + (f" sleeve trades = {n:.0f} x $10k" if sleeves > 1 else "")
          + f"; wins {wins}, losses {len(sc) - wins}",
          f"  gross       {money(sc['gross'].sum()):>14}   per trade {money(per('gross'))}",
          f"  costs L2    {money(sc['cost_L2'].sum()):>14}   per trade {money(per('cost_L2'))}",
          f"  net L1/L2/L3 per trade   {money(per('net_L1'))} / {money(per('net_L2'))} / {money(per('net_L3'))}",
          f"  market      {money(sc['mkt'].sum()):>14}   (sum over trades of notional x basket, same windows)",
          f"  mr net L2   {money(sc['mr_net_L2'].sum()):>14}   per trade {money(per('mr_net_L2'))}",
          f"  levered 2:1 net L2 per trade {money(per('net_L2_levered'))} (reported, never scored)"]
    bod = sc["entry_slot"].value_counts().sort_index()
    L.append("  entries by bar: " + ", ".join(f"slot {k}: {v}" for k, v in bod.items()))
    cap = E.capped_book(sc)
    if len(cap):
        L.append(f"  2-slot capped book: {len(cap)} trades, net L2 {money(cap['net_L2'].sum())} "
                 "(reported, never scored)")
    c = E.concurrency(sc)
    L.append(f"  max concurrent {c['max_concurrent']}, capital tied up "
             f"{money(c['max_capital'])}")
    if drop:
        L.append(f"  voided (split) {drop.get('voided_split', 0)}, excluded (bad day) "
                 f"{drop.get('excluded_bad_day', 0)}")
    if g:
        L.append(f"  G5 guards: {g['trades_checked']} trades, {g['lookahead_cuts']} look-ahead cuts: clean")
    if rc.get("p95") is not None:
        L.append(f"  random entries, same exit: p95 {money(rc['p95'])} per trade "
                 f"({len(rc.get('draws', []))} draws)")
    for k, v in ev.items():
        if k == "all_pass":
            continue
        L.append(f"  [{'PASS' if v['pass'] else 'fail'}] {k}: {v['value']}")
    L.append(f"  ALL §7: {'PASS' if ev['all_pass'] else 'no'}")
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--archive", help="H60 archive root (default <shared archive>/H60)")
    ap.add_argument("--build-cache", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--eod-dir", default=str(XC.EOD_DIR))
    a = ap.parse_args(argv)
    if a.build_cache:
        from strategy.h60.data_plan import DATASET, RTH_DIR
        root = archive_root(a.archive)
        src = root / DATASET / RTH_DIR
        if not any(src.glob("*.dbn.zst")):
            raise SystemExit(f"no 1-minute RTH files under {src}. The W14-0002 pull "
                             f"writes <H60 root>/{DATASET}/{RTH_DIR} "
                             "(data_plan.rth_root, called on the SHARED archive, "
                             "lands here); pass --archive if they are elsewhere. "
                             "--archive takes the H60 root itself -- do not pass "
                             "the shared archive or rth_root will double the H60 "
                             "segment.")
        print(f"reading {src}", flush=True)
        res = B.build_cache(src, root)
        print(json.dumps(res, indent=1, default=str))
        return 0
    if a.preflight:
        return preflight(a.archive, Path(a.eod_dir))
    if a.score:
        return score_all(a.archive)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
