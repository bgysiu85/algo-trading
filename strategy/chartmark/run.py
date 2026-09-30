#!/usr/bin/env python3
"""CHARTMARK-v1 training-side backtest (W15-0032 sub 5). TRAINING ONLY: 2010-06 -> 2021-12-31.

    python -m strategy.chartmark.run

Needs the G2 pre-flight to have cleared the 150-fill stop rule (checked again here). No holdout path: --holdout, --limit
and every narrowing flag are refused. Headline = BASE, 1 MCL, mid friction (IBKR, Amendment A.3); 1 CL beside it.
Variants, C2 and the seen window are reported, never ranked, never headline."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark import book as BK
from strategy.chartmark import controls as CT
from strategy.chartmark import engine as E
from strategy.chartmark import spec as S
from strategy.chartmark.data import indicators, load_training_frame, load_seen_frame
from strategy.futbt import runner_common as RC
from strategy.htf import book as HBK

OUT = Path(r"D:\Trading\Claude outputs")
FIRST, LAST = "2010-06-06", "2021-12-31"


def money(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"(${abs(x):,.0f})" if x < 0 else f"${x:,.0f}"


def pts(x) -> str:
    return f"({abs(x):.2f})" if x < 0 else f"{x:.2f}"


def summarize(trades, fr, sym="MCL", level="mid") -> dict:
    df = BK.trade_frame(trades, fr, sym, level)
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
    d = {}
    for t in trades:
        d[t.reason] = d.get(t.reason, 0) + 1
    return d


def run(archive, out_dir: Path, stamp: str, *, draws=1000, seen_csv=None, log=print) -> dict:
    fr = load_training_frame(archive)
    ind = indicators(fr)
    log(f"training frame {fr.n} bars {fr.ny[0]} .. {fr.ny[-1]}")
    res = {"stamp": stamp, "window": f"{FIRST} .. {LAST}"}
    # ---- variants ----
    V = {}
    for name, p in S.VARIANTS.items():
        tr, cnt = E.simulate(fr, ind, p)
        V[name] = dict(trades=tr, cnt=cnt)
        for sym in ("MCL", "CL"):
            for lv in S.LEVELS:
                V[name][f"{sym}_{lv}"] = summarize(tr, fr, sym, lv)
    base = V["BASE"]
    n_fills = base["cnt"]["fills"]
    if n_fills < 150:
        raise SystemExit(f"STOP RULE: BASE fills = {n_fills} < 150 -- underpowered; report to Ben, no P&L.")
    # ---- controls ----
    c1_tr, _ = CT.donchian_c1(fr, ind)
    C1 = {f"{sym}_{lv}": summarize(c1_tr, fr, sym, lv) for sym in ("MCL", "CL") for lv in S.LEVELS}
    idx, cand = CT.candidate_outcomes(fr, ind, S.BASE)
    cand_net = np.array([(t.exit_px - t.entry_px) * S.MULT["MCL"] - S.per_side("MCL", "mid") * (2 + 2 * t.n_rolls)
                         for t in cand])
    years = np.asarray(fr.ny.year)
    per_year_entries = pd.Series(years[[t.entry_j for t in base["trades"]]]).value_counts().sort_index().to_dict()
    c3 = CT.c3_draws(fr, idx, cand_net, {int(k): int(v) for k, v in per_year_entries.items()}, draws)
    c3p = {k: float(np.percentile(c3, q)) for k, q in (("p5", 5), ("p50", 50), ("p95", 95), ("p99", 99))}
    base_net = base["MCL_mid"]["net"]
    c3_rank = float((c3 < base_net).mean())
    # ---- grid ----
    grid = []
    for L in S.GRID_E1:
        for a in S.GRID_P1:
            for sl in S.GRID_STOP:
                tr, _ = E.simulate(fr, ind, replace(S.BASE, e1_lookback=L, p1_arm=a, stop_lookback=sl))
                grid.append(dict(e1=L, p1=a, stop=sl, n=len(tr), net=summarize(tr, fr)["net"]))
    n_pos = sum(g["net"] > 0 for g in grid)
    # ---- criteria ----
    crit = BK.evaluate(base["MCL_mid"]["df"], base["MCL_high"]["df"], c1_mid=C1["MCL_mid"]["df"], c3_p99=c3p["p99"],
                       n_grid_pos=n_pos, first=FIRST, last=LAST)
    verdict = BK.verdict(crit)
    res.update(V=V, C1=C1, c3=c3p, c3_rank=c3_rank, grid=grid, n_pos=n_pos, crit=crit, verdict=verdict,
               per_year_entries=per_year_entries)
    # ---- seen window (reported only) ----
    if seen_csv and Path(seen_csv).exists():
        sf = load_seen_frame(seen_csv)
        str_, scnt = E.simulate(sf, indicators(sf), S.BASE)
        res["seen"] = dict(n=len(str_), **{k: summarize(str_, sf)[k] for k in ("net", "gross", "wins", "losses")})
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = report(res, fr)
    (out_dir / f"w15_0032_chartmark_backtest_{stamp}.txt").write_text(txt, encoding="utf-8")
    base["MCL_mid"]["df"].to_csv(out_dir / f"w15_0032_chartmark_trades_base_{stamp}.csv", index=False)
    js = dict(stamp=stamp, verdict=verdict, criteria=[{**c, "value": _js(c["value"])} for c in crit], c3=c3p, c3_rank=c3_rank,
              grid=grid, n_pos=n_pos,
              variants={k: {"fills": v["cnt"]["fills"], "exits": exits(v["trades"]),
                            **{m: {q: _js(v[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "h1", "h2", "dd", "top_share")}
                               for m in ("MCL_mid", "MCL_high", "CL_mid")}} for k, v in V.items()},
              c1={m: {q: _js(C1[m][q]) for q in ("n", "wins", "losses", "gross", "cost", "net", "dd")} for m in ("MCL_mid", "MCL_high", "CL_mid")},
              base_year={int(y): float(v) for y, v in base["MCL_mid"]["year_net"].items()},
              seen=res.get("seen"))
    (out_dir / f"w15_0032_chartmark_backtest_{stamp}.json").write_text(json.dumps(js, indent=1, default=str), encoding="utf-8")
    log(txt)
    return res


def _js(x):
    if isinstance(x, tuple):
        return [float(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def report(r: dict, fr) -> str:
    V, C1 = r["V"], r["C1"]
    b = V["BASE"]
    m, h, cl = b["MCL_mid"], b["MCL_high"], b["CL_mid"]
    L = [f"W15-0032 CHARTMARK-v1 (long) -- training-side backtest, CL 1H, {r['window']}, run {r['stamp']}",
         "Registered: REGISTERED_chartmark_v1.md incl. Amendment A. Costs IBKR (A.3). 1 MCL headline, mid friction. Negatives in brackets.",
         "", f"VERDICT: {r['verdict']}", ""]
    L += ["HEADLINE (BASE, 1 MCL, mid):",
          f"  trades {m['n']}  wins {m['wins']}  losses {m['losses']}  gross {money(m['gross'])}  costs {money(m['cost'])}  net {money(m['net'])}",
          f"  avg win {money(m['avg_win'])}  avg loss {money(m['avg_loss'])}  largest loss {money(m['largest_loss'])}  worst losing run {m['streak']}  max drawdown {money(m['dd'])}",
          f"  halves {money(m['h1'])} / {money(m['h2'])}   net at high friction {money(h['net'])}   1 CL mid net {money(cl['net'])}", ""]
    L += ["SEC 4 CRITERIA (base):"]
    for c in r["crit"]:
        ok = "PASS" if c["ok"] else ("n/a" if c["ok"] is None else "FAIL")
        L.append(f"  {c['n']:2d}. {c['name']:<55s} {ok:5s} {_fmt(c['value'])}")
    L += ["", "BASE per year (1 MCL, mid):", f"  {'year':>5} {'orders/fills':>13} {'trades':>7} {'W/L':>9} {'gross':>10} {'cost':>9} {'net':>10}"]
    df = m["df"]
    for y, g in df.groupby("year"):
        L.append(f"  {y:>5} {'':>13} {len(g):>7} {int((g.net>0).sum()):>4}/{int((g.net<0).sum()):<4} {money(g.gross.sum()):>10} {money(g.cost.sum()):>9} {money(g.net.sum()):>10}")
    L += ["", "EXITS BY TYPE (base): " + str(exits(b["trades"])),
          f"Reached P1 {sum(t.phase>=1 for t in b['trades'])}/{m['n']}  P2 {sum(t.phase>=2 for t in b['trades'])}/{m['n']}  "
          f"orders {b['cnt']['orders']} fills {b['cnt']['fills']} timeouts {b['cnt']['timeouts']} ctx cancels {b['cnt']['ctx_cancels']}", ""]
    L += ["CONTROLS (1 MCL, mid):",
          f"  C1 Donchian 20/10 long, session-filtered: trades {C1['MCL_mid']['n']} net {money(C1['MCL_mid']['net'])} (high {money(C1['MCL_high']['net'])})",
          f"  C3 random entries, same count per year, same exits (1,000 draws): p5 {money(r['c3']['p5'])}  p50 {money(r['c3']['p50'])}  p95 {money(r['c3']['p95'])}  p99 {money(r['c3']['p99'])}; base beats {100*r['c3_rank']:.1f}% of draws",
          "  C2 HTF-Ben v2: reference only -- see its own RESULT doc (NinjaTrader friction, not re-scored).", ""]
    L += ["VARIANTS (reported, never ranked; 1 MCL mid): trades / W-L / gross / net / net at high / halves / max DD"]
    for k, v in V.items():
        x = v["MCL_mid"]
        L.append(f"  {k:<12s} {x['n']:5d}  {x['wins']}/{x['losses']}  {money(x['gross']):>10}  {money(x['net']):>10}  {money(v['MCL_high']['net']):>10}  "
                 f"{money(x['h1'])} / {money(x['h2'])}  DD {money(x['dd'])}  exits {exits(v['trades'])}")
    L += ["", f"NEIGHBOUR GRID (27 cells, unranked): {r['n_pos']} of 27 net > $0 at mid.",
          "  cells (E1 lookback, P1 arm, stop lookback -> trades, net):"]
    for g in r["grid"]:
        L.append(f"   E1={g['e1']} P1={g['p1']:<4} S={g['stop']} -> {g['n']:5d}  {money(g['net'])}")
    if r.get("seen"):
        s = r["seen"]
        L += ["", f"SEEN WINDOW (TradingView CL1! 2025-09-08 on; seen -- not evidence): engine BASE {s['n']} trades, gross {money(s['gross'])}, net {money(s['net'])}"]
    L += ["", "CAVEATS: 1H OHLC cannot show the path inside a bar (level+stop same-bar touches counted in the pre-flight, 0 for the base by construction); "
          "C3 trades are independent single-trade outcomes (overlap allowed); criterion 5 volatility definition is I9 in spec.py."]
    return "\n".join(L) + "\n"


def _fmt(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(money(x) if abs(x) > 5 else f"{x:.2f}" for x in v) + ")"
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 5 else money(v)
    return str(v)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    RC.refuse_pnl_flags([a for a in argv if a != "--seen-csv"])
    ap = RC.base_parser("CHARTMARK-v1 training backtest")
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args(argv)
    from common.tsmom_fetch import default_archive
    arch = Path(a.archive) if a.archive else default_archive()
    run(arch, Path(a.out), date.today().strftime("%Y%m%d"), draws=a.draws,
        seen_csv=Path(a.out) / "w15_0032_cl1_1h_bars_indicators.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
