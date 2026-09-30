#!/usr/bin/env python3
"""CHARTMARK-S v1 training-side backtest (W15-0032 sub 9). TRAINING ONLY: 2010-06 -> 2021-12-31.

    python -m strategy.chartmark_s.run

Needs the G2 pre-flight to have cleared the 150-fill stop rule (checked again here). No holdout path: --holdout, --limit
and every narrowing flag are refused. Headline = BASE, 1 MCL, mid friction (IBKR, sec 2.5); 1 CL beside it.
Variants, C2, the grid and the seen window are reported, never ranked, never headline."""
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
from strategy.chartmark_s import controls as CT
from strategy.chartmark_s import engine as E
from strategy.chartmark_s import spec as S
from strategy.chartmark_s.data import indicators, load_seen_frame, load_training_frame
from strategy.futbt import runner_common as RC
from strategy.htf import book as HBK

OUT = Path(os.environ.get("CHARTMARK_OUT", r"D:\Trading\Claude outputs"))
FIRST, LAST = "2010-06-06", "2021-12-31"


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def summarize(trades, fr, sym="MCL", level="mid", tf=BK.trade_frame) -> dict:
    df = tf(trades, fr, sym, level)
    s = HBK.summarize(df) if len(df) else None
    yn = HBK.year_table(df) if len(df) else {}
    h1, h2 = HBK.split_halves(df) if len(df) else (0.0, 0.0)
    return dict(df=df, n=len(df), wins=s.wins if s else 0, losses=s.losses if s else 0,
                gross=s.gross if s else 0.0, cost=s.cost if s else 0.0, net=s.net if s else 0.0,
                avg_win=s.avg_win if s else None, avg_loss=s.avg_loss if s else None,
                largest_loss=s.largest_loss if s else None, streak=s.worst_loss_streak if s else 0,
                year_net=yn, h1=h1, h2=h2, dd=BK.max_drawdown(df),
                top_share=HBK.top_year_share(yn)[1] if yn else 0.0)


def exits(trades) -> dict:
    return dict(Counter(t.reason for t in trades))


def year_rows(fr, trades, cnt) -> list[dict]:
    """Sec 3 per-year table (BASE): orders, fills, cancels, timeouts, re-entries, exits by type, P1 share, medians, W/L, $."""
    yrs = np.asarray(fr.ny.year)
    ev = Counter((k, int(yrs[t])) for k, t in cnt["ev"])
    rows = []
    prev_exit = -1
    reent = Counter()
    for t in trades:
        if t.placed_j == prev_exit:
            reent[int(yrs[t.entry_j])] += 1
        prev_exit = t.exit_j
    dfs = {(s, lv): BK.trade_frame(trades, fr, s, lv) for s in ("MCL", "CL") for lv in S.LEVELS}
    for y in sorted(set(int(v) for v in yrs[[t.entry_j for t in trades]])):
        tt = [t for t in trades if int(yrs[t.entry_j]) == y]
        m = dfs[("MCL", "mid")]
        g = m[m.year == y]
        rows.append(dict(year=y, orders=ev[("order", y)], fills=len(tt), cancels=ev[("cancel", y)], timeouts=ev[("timeout", y)],
                         reentries=reent[y], exits=exits(tt), p1=sum(t.phase >= 1 for t in tt),
                         med_o2f=float(np.median([t.entry_j - t.placed_j for t in tt])),
                         med_f2x=float(np.median([t.exit_j - t.entry_j for t in tt])),
                         wins=int((g.net > 0).sum()), losses=int((g.net < 0).sum()), gross=float(g.gross.sum()),
                         cost=float(g.cost.sum()), net_low=float(dfs[("MCL", "low")].query("year==@y").net.sum()),
                         net_mid=float(g.net.sum()), net_high=float(dfs[("MCL", "high")].query("year==@y").net.sum()),
                         cl_mid=float(dfs[("CL", "mid")].query("year==@y").net.sum())))
    return rows


def run(archive, out_dir: Path, stamp: str, *, draws=1000, seen_csv=None, log=print) -> dict:
    fr = load_training_frame(archive)
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
    from strategy.chartmark import book as LB
    c2_tr, c2c = CT.c2_mirrored_long(fr)
    mf = c2c["mirrored"]
    C2 = {f"{sym}_{lv}": summarize(c2_tr, mf, sym, lv, tf=LB.trade_frame) for sym in ("MCL",) for lv in S.LEVELS}
    idx, cand = CT.candidate_outcomes(fr, ind, S.BASE)
    cand_net = np.array([(t.entry_px - t.exit_px) * S.MULT["MCL"] - S.per_side("MCL", "mid") * (2 + 2 * t.n_rolls) for t in cand])
    yrs = np.asarray(fr.ny.year)
    per_year_entries = pd.Series(yrs[[t.entry_j for t in base["trades"]]]).value_counts().sort_index().to_dict()
    c3 = CT.c3_draws(fr, idx, cand_net, {int(k): int(v) for k, v in per_year_entries.items()}, draws)
    c3p = {k: float(np.percentile(c3, q)) for k, q in (("p5", 5), ("p50", 50), ("p95", 95), ("p99", 99))}
    c3_rank = float((c3 < base["MCL_mid"]["net"]).mean())
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
    res.update(V=V, C1=C1, C2=C2, c3=c3p, c3_rank=c3_rank, grid=grid, n_pos=n_pos, crit=crit, verdict=verdict,
               per_year_entries=per_year_entries, years=year_rows(fr, base["trades"], base["cnt"]),
               c2_n=len(c2_tr), c1_n=len(c1_tr))
    if seen_csv and Path(seen_csv).exists():
        sf = load_seen_frame(seen_csv)
        str_, _ = E.simulate(sf, indicators(sf), S.BASE)
        sm = summarize(str_, sf)
        res["seen"] = dict(n=len(str_), net=sm["net"], gross=sm["gross"], wins=sm["wins"], losses=sm["losses"])
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = report(res)
    (out_dir / f"w15_0032_chartmark_short_backtest_{stamp}.txt").write_text(txt, encoding="utf-8")
    base["MCL_mid"]["df"].to_csv(out_dir / f"w15_0032_chartmark_short_trades_base_{stamp}.csv", index=False)
    js = dict(stamp=stamp, verdict=verdict, criteria=[{**c, "value": _js(c["value"])} for c in crit], c3=c3p, c3_rank=c3_rank,
              grid=grid, n_pos=n_pos, years=res["years"],
              variants={k: {"fills": v["cnt"]["fills"], "exits": exits(v["trades"]),
                            **{m: {q: _js(v[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "h1", "h2", "dd", "top_share",
                                                             "avg_win", "avg_loss", "largest_loss", "streak")}
                               for m in ("MCL_low", "MCL_mid", "MCL_high", "CL_mid")},
                            "year_net": {int(y): float(x) for y, x in v["MCL_mid"]["year_net"].items()}} for k, v in V.items()},
              c1={m: {q: _js(C1[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "dd")} for m in ("MCL_mid", "MCL_high", "CL_mid")},
              c2={m: {q: _js(C2[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "dd")} for m in ("MCL_mid", "MCL_high")},
              seen=res.get("seen"))
    (out_dir / f"w15_0032_chartmark_short_backtest_{stamp}.json").write_text(json.dumps(js, indent=1, default=str), encoding="utf-8")
    log(txt)
    return res


def _js(x):
    if isinstance(x, tuple):
        return [float(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def _fmt(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(money(x) if abs(x) > 5 else f"{x:.2f}" for x in v) + ")"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 5 else money(v)
    return str(v)


def report(r: dict) -> str:
    V, C1, C2 = r["V"], r["C1"], r["C2"]
    b = V["BASE"]
    m, h, lo, cl = b["MCL_mid"], b["MCL_high"], b["MCL_low"], b["CL_mid"]
    L = [f"W15-0032 CHARTMARK-S v1 (short) -- training-side backtest, CL 1H, {r['window']}, run {r['stamp']}",
         "Registered: REGISTERED_chartmark_short_v1.md incl. Amendment A. Costs IBKR (sec 2.5). 1 MCL headline, mid friction. Negatives in brackets.",
         "", f"VERDICT: {r['verdict']}", ""]
    L += ["HEADLINE (BASE, 1 MCL, mid):",
          f"  trades {m['n']}  wins {m['wins']}  losses {m['losses']}  gross {money(m['gross'])}  costs {money(m['cost'])}  net {money(m['net'])}",
          f"  net at low {money(lo['net'])} / mid {money(m['net'])} / high {money(h['net'])}   1 CL: low {money(b['CL_low']['net'])} / mid {money(cl['net'])} / high {money(b['CL_high']['net'])}",
          f"  avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  worst losing run {m['streak']}  max drawdown {money(m['dd'])}",
          f"  halves {money(m['h1'])} / {money(m['h2'])}", ""]
    L += ["SEC 4 CRITERIA (base):"]
    for c in r["crit"]:
        ok = "PASS" if c["ok"] else ("n/a" if c["ok"] is None else "FAIL")
        L.append(f"  {c['n']:2d}. {c['name']:<55s} {ok:5s} {_fmt(c['value'])}")
    L += ["", "BASE per year (1 MCL; net low / mid / high; 1 CL mid):",
          f"  {'year':>4} {'orders':>6} {'fills':>5} {'cancel':>6} {'t/out':>5} {'re-ent':>6} {'P1%':>4} {'W/L':>9} {'gross':>9} {'cost':>8} {'net low':>9} {'net mid':>9} {'net high':>9} {'CL mid':>10}  exits"]
    for y in r["years"]:
        L.append(f"  {y['year']:>4} {y['orders']:>6} {y['fills']:>5} {y['cancels']:>6} {y['timeouts']:>5} {y['reentries']:>6} "
                 f"{100*y['p1']/max(y['fills'],1):>3.0f}% {y['wins']:>4}/{y['losses']:<4} {money(y['gross']):>9} {money(y['cost']):>8} "
                 f"{money(y['net_low']):>9} {money(y['net_mid']):>9} {money(y['net_high']):>9} {money(y['cl_mid']):>10}  {y['exits']}  "
                 f"med bars order->fill {y['med_o2f']:.0f}, fill->exit {y['med_f2x']:.0f}")
    L += ["", f"EXITS BY TYPE (base): {exits(b['trades'])}  share reaching P1 {sum(t.phase>=1 for t in b['trades'])}/{m['n']}  "
          f"orders {b['cnt']['orders']} fills {b['cnt']['fills']} cancels {b['cnt']['ctx_cancels']} timeouts {b['cnt']['timeouts']} "
          f"re-entries {b['cnt']['reentries']} same-bar backstop touches {b['cnt']['same_bar']} (0 by construction)", ""]
    L += ["CONTROLS (1 MCL, mid):",
          f"  C1 Donchian 20/10 short: trades {C1['MCL_mid']['n']} net {money(C1['MCL_mid']['net'])} (high {money(C1['MCL_high']['net'])})",
          f"  C2 long rules mirrored for shorts (reference only): trades {C2['MCL_mid']['n']} gross {money(C2['MCL_mid']['gross'])} net {money(C2['MCL_mid']['net'])} (high {money(C2['MCL_high']['net'])})",
          f"  C3 random short entries, same count per year, same exits (1,000 draws): p5 {money(r['c3']['p5'])}  p50 {money(r['c3']['p50'])}  p95 {money(r['c3']['p95'])}  p99 {money(r['c3']['p99'])}; base beats {100*r['c3_rank']:.1f}% of draws", ""]
    L += ["VARIANTS (reported, never ranked; 1 MCL): trades / W-L / gross / net mid / net high / net low / halves / max DD / exits"]
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
          "C3 trades are independent single-trade outcomes (overlap allowed); criterion 5 volatility is I9 (spec J9). Backstop same-bar touches are 0 by construction (J3)."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags(argv)
    ap = RC.base_parser("CHARTMARK-S v1 training backtest")
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args(argv)
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"), draws=a.draws,
        seen_csv=OUT / "w15_0032_cl1_1h_bars_indicators.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
