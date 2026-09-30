#!/usr/bin/env python3
"""CHARTMARK-S v3 training-side backtest (W15-0042 sub 4). TRAINING ONLY: 2010-06 -> 2021-12-31.

    python -m strategy.chartmark_s3.run

Needs the G2 pre-flight to have cleared the 150-fill stop rule (checked again here). No holdout path: --holdout, --limit and every
narrowing flag are refused. Headline = BASE, 1 MCL, mid friction (IBKR); 1 CL beside it. Variants (V-A, V-B, V-B1 = v2's base,
V-RANGE, V-SESSION, V-AVOID), the v1 base, the grid and the seen window are reported, never ranked, never headline.
Every report carries the G6 waiver line (v3 Amendment 1)."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark_s import book as BK
from strategy.chartmark_s.run import _fmt, _js, money, summarize
from strategy.chartmark_s3 import controls as CT
from strategy.chartmark_s3 import engine as E
from strategy.chartmark_s3 import spec as S
from strategy.chartmark_s3.data import context_tiers, indicators, load_seen_frame, load_training_frame
from strategy.futbt import runner_common as RC

OUT = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
FIRST, LAST = "2010-06-06", "2021-12-31"
WAIVER = "G6 waived for 8 Sep 08:00 (Amendment 1): v3 is NOT evidence of anything on the training side; only the holdout counts."


def exits(trades) -> dict:
    return dict(Counter(t.reason for t in trades))


def tier_rows(trades, fr) -> dict:
    """Per tier (A, B): fills, W/L, gross, cost, net at low / mid / high (1 MCL), exits, P1 share."""
    out = {}
    dfs = {lv: BK.trade_frame(trades, fr, "MCL", lv) for lv in S.LEVELS}
    for code, nm in ((S.TIER_A, "A"), (S.TIER_B, "B")):
        mask = np.array([t.tier == code for t in trades], bool)
        m = dfs["mid"][mask] if len(trades) else dfs["mid"]
        out[nm] = dict(fills=int(mask.sum()), wins=int((m.net > 0).sum()), losses=int((m.net < 0).sum()),
                       gross=float(m.gross.sum()), cost=float(m.cost.sum()),
                       net_low=float(dfs["low"][mask].net.sum()), net_mid=float(m.net.sum()), net_high=float(dfs["high"][mask].net.sum()),
                       exits=exits([t for t, k in zip(trades, mask) if k]),
                       p1=int(sum(t.phase >= 1 for t, k in zip(trades, mask) if k)))
    return out


def year_rows(fr, trades, cnt) -> list[dict]:
    """Per-year (BASE): orders, fills by tier, cancels, timeouts, exits, W/L, gross, cost, net low / mid / high, net mid by tier, 1 CL mid."""
    yrs = np.asarray(fr.ny.year)
    ev = Counter((k, int(yrs[t])) for k, t in cnt["ev"])
    dfs = {(s, lv): BK.trade_frame(trades, fr, s, lv) for s in ("MCL", "CL") for lv in S.LEVELS}
    tiers = np.array([t.tier for t in trades])
    rows = []
    for y in sorted(set(int(v) for v in yrs[[t.entry_j for t in trades]])):
        sel = np.array([int(yrs[t.entry_j]) == y for t in trades])
        m = dfs[("MCL", "mid")][sel]
        rows.append(dict(year=y, orders=ev[("order", y)], fills=int(sel.sum()), A=int((sel & (tiers == 1)).sum()),
                         B=int((sel & (tiers == 2)).sum()), cancels=ev[("cancel", y)], timeouts=ev[("timeout", y)],
                         exits=exits([t for t, k in zip(trades, sel) if k]),
                         p1=int(sum(t.phase >= 1 for t, k in zip(trades, sel) if k)),
                         wins=int((m.net > 0).sum()), losses=int((m.net < 0).sum()), gross=float(m.gross.sum()), cost=float(m.cost.sum()),
                         net_low=float(dfs[("MCL", "low")][sel].net.sum()), net_mid=float(m.net.sum()),
                         net_high=float(dfs[("MCL", "high")][sel].net.sum()),
                         net_A=float(m[tiers[sel] == 1].net.sum()), net_B=float(m[tiers[sel] == 2].net.sum()),
                         cl_mid=float(dfs[("CL", "mid")][sel].net.sum())))
    return rows


def run_frames(fr, out_dir: Path, stamp: str, *, draws=1000, seen_fr=None, log=print, write=True) -> dict:
    ind = indicators(fr)
    log(f"training frame {fr.n} bars {fr.ny[0]} .. {fr.ny[-1]}")
    res = {"stamp": stamp, "window": f"{FIRST} .. {LAST}"}
    V = {}
    for name, p in S.VARIANTS.items():
        tr, cnt = E.simulate(fr, ind, p)
        V[name] = dict(trades=tr, cnt=cnt)
        for sym in ("MCL", "CL"):
            for lv in S.LEVELS:
                V[name][f"{sym}_{lv}"] = summarize(tr, fr, sym, lv)
        log(f"  {name}: {len(tr)} trades, MCL mid net {money(V[name]['MCL_mid']['net'])}")
    base = V["BASE"]
    if base["cnt"]["fills"] < 150:
        raise SystemExit(f"STOP RULE: BASE fills = {base['cnt']['fills']} < 150 -- underpowered; report to Ben, no P&L.")
    # ---- controls ----
    c1_tr, _ = CT.donchian_c1(fr, ind)
    C1 = {f"{sym}_{lv}": summarize(c1_tr, fr, sym, lv) for sym in ("MCL", "CL") for lv in S.LEVELS}
    idx, cand = CT.candidate_outcomes(fr, ind, S.BASE)
    cand_net = np.array([(t.entry_px - t.exit_px) * S.MULT["MCL"] - S.per_side("MCL", "mid") * (2 + 2 * t.n_rolls) for t in cand])
    yrs = np.asarray(fr.ny.year)
    per_year_entries = pd.Series(yrs[[t.entry_j for t in base["trades"]]]).value_counts().sort_index().to_dict()
    c3 = CT.c3_draws(fr, idx, cand_net, {int(k): int(v) for k, v in per_year_entries.items()}, draws)
    c3p = {k: float(np.percentile(c3, q)) for k, q in (("p5", 5), ("p50", 50), ("p95", 95), ("p99", 99))}
    c3_rank = float((c3 < base["MCL_mid"]["net"]).mean())
    # ---- v1 base, reference only ----
    from strategy.chartmark_s import engine as E1
    from strategy.chartmark_s import spec as S1
    v1_tr, _ = E1.simulate(fr, ind, S1.BASE)
    v1 = {f"MCL_{lv}": summarize(v1_tr, fr, "MCL", lv) for lv in S.LEVELS}
    # ---- grid ----
    grid = []
    for X in S.GRID_X1:
        for a in S.GRID_P1:
            for cb in S.GRID_CUT:
                tr, _ = E.simulate(fr, ind, replace(S.BASE, x1_window=X, p1_arm=a, cut_ticks=cb))
                grid.append(dict(x1=X, p1=a, cut=cb, n=len(tr), net=summarize(tr, fr)["net"]))
    n_pos = sum(g["net"] > 0 for g in grid)
    crit = BK.evaluate(base["MCL_mid"]["df"], base["MCL_high"]["df"], c1_mid=C1["MCL_mid"]["df"], c3_p99=c3p["p99"],
                       n_grid_pos=n_pos, first=FIRST, last=LAST)
    verdict = BK.verdict(crit)
    ctx, tier = context_tiers(fr, ind, S.BASE)
    res.update(V=V, C1=C1, v1=v1, v1_n=len(v1_tr), c3=c3p, c3_rank=c3_rank, grid=grid, n_pos=n_pos, crit=crit, verdict=verdict,
               per_year_entries=per_year_entries, years=year_rows(fr, base["trades"], base["cnt"]),
               tiers=tier_rows(base["trades"], fr), c1_n=len(c1_tr),
               share=dict(ctx=int(ctx.sum()), A=int((tier == 1).sum()), B=int((tier == 2).sum())))
    if seen_fr is not None:
        str_, _ = E.simulate(seen_fr, indicators(seen_fr), S.BASE)
        sm = summarize(str_, seen_fr)
        res["seen"] = dict(n=len(str_), net=sm["net"], gross=sm["gross"], wins=sm["wins"], losses=sm["losses"])
    txt = report(res)
    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"w15_0042_chartmark_short_v3_backtest_{stamp}.txt").write_text(txt, encoding="utf-8")
        base["MCL_mid"]["df"].to_csv(out_dir / f"w15_0042_chartmark_short_v3_trades_base_{stamp}.csv", index=False)
        js = dict(stamp=stamp, waiver=WAIVER, verdict=verdict, criteria=[{**c, "value": _js(c["value"])} for c in crit], c3=c3p,
                  c3_rank=c3_rank, grid=grid, n_pos=n_pos, years=res["years"], tiers=res["tiers"], share=res["share"],
                  variants={k: {"fills": v["cnt"]["fills"], "exits": exits(v["trades"]),
                                **{m: {q: _js(v[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "h1", "h2", "dd", "top_share")}
                                   for m in ("MCL_low", "MCL_mid", "MCL_high", "CL_mid")},
                                "year_net": {int(y): float(x) for y, x in v["MCL_mid"]["year_net"].items()}} for k, v in V.items()},
                  c1={m: {q: _js(C1[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "dd")} for m in ("MCL_mid", "MCL_high", "CL_mid")},
                  v1_base={m: {q: _js(v1[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net")} for m in ("MCL_mid", "MCL_high")},
                  seen=res.get("seen"))
        (out_dir / f"w15_0042_chartmark_short_v3_backtest_{stamp}.json").write_text(json.dumps(js, indent=1, default=str), encoding="utf-8")
    log(txt)
    return res


def run(archive, out_dir: Path, stamp: str, *, draws=1000, seen_csv=None, log=print) -> dict:
    sf = load_seen_frame(seen_csv) if seen_csv and Path(seen_csv).exists() else None
    return run_frames(load_training_frame(archive), out_dir, stamp, draws=draws, seen_fr=sf, log=log)


def report(r: dict) -> str:
    V, C1 = r["V"], r["C1"]
    b = V["BASE"]
    m, h, lo, cl = b["MCL_mid"], b["MCL_high"], b["MCL_low"], b["CL_mid"]
    L = [f"W15-0042 CHARTMARK-S v3 (short) -- training-side backtest, CL 1H, {r['window']}, run {r['stamp']}",
         "Registered: REGISTERED_chartmark_short_v3.md (v2 with B1 removed) incl. Amendment 1. Costs IBKR. 1 MCL headline, mid friction. Negatives in brackets.",
         WAIVER, "", f"VERDICT: {r['verdict']}", ""]
    L += ["HEADLINE (BASE, 1 MCL, mid):",
          f"  trades {m['n']}  wins {m['wins']}  losses {m['losses']}  gross {money(m['gross'])}  costs {money(m['cost'])}  net {money(m['net'])}",
          f"  net at low {money(lo['net'])} / mid {money(m['net'])} / high {money(h['net'])}   1 CL: low {money(b['CL_low']['net'])} / mid {money(cl['net'])} / high {money(b['CL_high']['net'])}",
          f"  avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  worst losing run {m['streak']}  max drawdown {money(m['dd'])}",
          f"  halves {money(m['h1'])} / {money(m['h2'])}", ""]
    sh = r["share"]
    L += [f"BY TIER (BASE, 1 MCL): context bars {sh['ctx']}: Tier A {sh['A']} ({100*sh['A']/max(sh['ctx'],1):.0f}%), Tier B {sh['B']} ({100*sh['B']/max(sh['ctx'],1):.0f}%)",
          f"  {'tier':<5}{'fills':>6}{'W/L':>10}{'gross':>10}{'costs':>9}{'net low':>10}{'net mid':>10}{'net high':>10}  P1  exits"]
    for nm, t in r["tiers"].items():
        L.append(f"  {nm:<5}{t['fills']:>6}{str(t['wins'])+'/'+str(t['losses']):>10}{money(t['gross']):>10}{money(t['cost']):>9}"
                 f"{money(t['net_low']):>10}{money(t['net_mid']):>10}{money(t['net_high']):>10}  {t['p1']}  {t['exits']}")
    L += ["", "SEC 4 CRITERIA (base):"]
    for c in r["crit"]:
        ok = "PASS" if c["ok"] else ("n/a" if c["ok"] is None else "FAIL")
        L.append(f"  {c['n']:2d}. {c['name']:<55s} {ok:5s} {_fmt(c['value'])}")
    L += ["", "BASE per year (1 MCL; fills A/B; net low / mid / high; net mid by tier; 1 CL mid):",
          f"  {'year':>4} {'orders':>6} {'fills':>5} {'A':>4} {'B':>4} {'cancel':>6} {'t/out':>5} {'P1%':>4} {'W/L':>9} {'gross':>9} {'cost':>8} "
          f"{'net low':>9} {'net mid':>9} {'net high':>9} {'net A':>9} {'net B':>9} {'CL mid':>10}  exits"]
    for y in r["years"]:
        L.append(f"  {y['year']:>4} {y['orders']:>6} {y['fills']:>5} {y['A']:>4} {y['B']:>4} {y['cancels']:>6} {y['timeouts']:>5} "
                 f"{100*y['p1']/max(y['fills'],1):>3.0f}% {y['wins']:>4}/{y['losses']:<4} {money(y['gross']):>9} {money(y['cost']):>8} "
                 f"{money(y['net_low']):>9} {money(y['net_mid']):>9} {money(y['net_high']):>9} {money(y['net_A']):>9} {money(y['net_B']):>9} "
                 f"{money(y['cl_mid']):>10}  {y['exits']}")
    L += ["", f"EXITS BY TYPE (base): {exits(b['trades'])}  share reaching P1 {sum(t.phase>=1 for t in b['trades'])}/{m['n']}  "
          f"orders {b['cnt']['orders']} fills {b['cnt']['fills']} cancels {b['cnt']['ctx_cancels']} timeouts {b['cnt']['timeouts']} "
          f"re-entries {b['cnt']['reentries']} same-bar backstop touches {b['cnt']['same_bar']} (0 by construction)", ""]
    L += ["CONTROLS (1 MCL, mid):",
          f"  C1 Donchian 20/10 short: trades {C1['MCL_mid']['n']} net {money(C1['MCL_mid']['net'])} (high {money(C1['MCL_high']['net'])})",
          f"  C3 random short entries, same count per year, same exits (1,000 draws): p5 {money(r['c3']['p5'])}  p50 {money(r['c3']['p50'])}  p95 {money(r['c3']['p95'])}  p99 {money(r['c3']['p99'])}; base beats {100*r['c3_rank']:.1f}% of draws",
          f"  REFERENCE, CHARTMARK-S v1 base (not a control): trades {r['v1_n']} gross {money(r['v1']['MCL_mid']['gross'])} net {money(r['v1']['MCL_mid']['net'])} (high {money(r['v1']['MCL_high']['net'])})", ""]
    L += ["VARIANTS (reported, never ranked; 1 MCL; V-B1 = v2's base): trades / W-L / gross / net mid / net high / net low / halves / max DD / exits"]
    for k, v in V.items():
        x = v["MCL_mid"]
        L.append(f"  {k:<10s} {x['n']:5d}  {x['wins']}/{x['losses']}  {money(x['gross']):>10}  {money(x['net']):>10}  {money(v['MCL_high']['net']):>10}  {money(v['MCL_low']['net']):>10}  "
                 f"{money(x['h1'])} / {money(x['h2'])}  DD {money(x['dd'])}  exits {exits(v['trades'])}")
    L += ["", f"NEIGHBOUR GRID (27 cells, unranked): {r['n_pos']} of 27 net > $0 at mid.",
          "  cells (X1 window, P1 arm, P0 cut buffer ticks -> trades, net):"]
    for g in r["grid"]:
        L.append(f"   X1={g['x1']:<2} P1={g['p1']:<4} cut={g['cut']} -> {g['n']:5d}  {money(g['net'])}")
    if r.get("seen"):
        s = r["seen"]
        L += ["", f"SEEN WINDOW (TradingView CL1! 2025-09-08 on; seen -- not evidence): engine BASE {s['n']} trades, gross {money(s['gross'])}, net {money(s['net'])} (1 MCL, mid)"]
    L += ["", "CAVEATS: 1H OHLC cannot show the path inside a bar; every fill is a stop order priced at the level or the open (gap), one tick of slippage per side at mid. "
          "C3 trades are independent single-trade outcomes (overlap allowed). Backstop same-bar touches are 0 by construction. "
          "Third short version on the same training bars; the holdout is the only evidence that counts."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-S v3 training backtest")
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args(argv)
    if a.markets:
        raise SystemExit("--markets is not a CHARTMARK-S option (CL only).")
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"), draws=a.draws, seen_csv=OUT / "w15_0032_cl1_1h_bars_indicators.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
