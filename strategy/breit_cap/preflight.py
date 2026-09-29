#!/usr/bin/env python3
"""G2 -- BREIT-CAP pre-flight (training side only, COUNTS ONLY). REGISTERED_breit_cap.md sec 5.2.

Per market per year and per side: Q1 runs, runs failing Q2 and Q3, qualified runs, entries, the grade
distribution, the run-length k and D/ATR distributions, the initial stop distance in $ per vehicle
contract, and the share sizeable at each risk tier of $22,129. The same for CL 4H. NO EXIT PRICE IS
READ AND NO P&L IS COMPUTED HERE: only the entry side of each simulated trade is read (bar, side,
entry price, initial stop, grade, k, D/ATR). The walk that decides when a position is flat again (so
one-position-at-a-time entry counts are right) runs inside sim.simulate and is not read back.

G1 (sec 5.1): held-contract daily VOLUME must be non-zero on >= 99% of training bars per market. A
market that fails has its G-volume scored "no" throughout, and that must first be written into the
registration as a PRE-RUN amendment: `check_volume` returns the failing markets and the runner stops
with exit code 3 until the amendment is committed and --volume-amendment-committed is passed.

Stop rules (sec 5.2): fewer than 150 PRIMARY entries -> STOP, underpowered, back to Ben before any P&L.
CL 4H with fewer than 150 entries is demoted to reported-only (the primary continues).
"""
from __future__ import annotations

import numpy as np

from strategy.breit_cap import signals as SG
from strategy.breit_cap import sim as SIM
from strategy.breit_cap import spec as S
from strategy.futbt import core as K

TIERS = (0.005, 0.01, 0.02)


def _pct(v, q):
    return float(np.percentile(v, q)) if len(v) else None


def check_volume(frames: dict) -> dict:
    cov = {m: SG.volume_coverage(fr.vol) for m, fr in frames.items()}
    return dict(coverage=cov, failing=sorted(m for m, c in cov.items() if c < S.MIN_VOLUME_COVERAGE))


def _sizeable(dists, equity=K.EQUITY):
    return {f"{r:.1%}": (float(np.mean([np.floor(r * equity / d) >= 1 for d in dists])) if len(dists) else None)
            for r in TIERS}


def market_report(fr: K.Frame, params: S.Params = S.PRIMARY, *, no_volume: bool = False) -> dict:
    if no_volume:
        fr = K.Frame(fr.market, fr.o, fr.h, fr.l, fr.c, np.full(fr.n, np.nan), fr.rc, fr.roll_after,
                     fr.dates, fr.mult, fr.tick_usd, fr.venue, fr.chart)
    sg = SG.compute(fr, params)
    trades, cnt = SIM.simulate(fr, sg, equity=K.EQUITY, integer=False)
    years = fr.dates.year.to_numpy()
    rep = dict(market=fr.market, chart=fr.chart, bars=fr.n, signal_counts=dict(sg.counts), sim_counts=cnt,
               no_volume=no_volume, per_year={}, entries=[])
    for t in trades:                                  # entry side only
        rep["entries"].append(dict(year=int(years[t.entry_j]), side=int(t.direction), grade=int(t.grade),
                                   k=int(t.k), d_atr=float(t.d_atr),
                                   dist_usd=float(abs(t.entry_px - t.stop_init) * fr.mult)))
    runs = sg.runs
    for y in sorted(set(int(v) for v in years)):
        row = {}
        for side, nm in ((1, "long"), (-1, "short")):
            rs = [r for r in runs if r["side"] == side and int(years[min(r["end"], fr.n - 1)]) == y]
            e = [x for x in rep["entries"] if x["year"] == y and x["side"] == side]
            row[nm] = dict(q1_runs=len(rs), fail_q2=sum(1 for r in rs if not r["qualified"] and not r["q2_ever"]),
                           fail_q3=sum(1 for r in rs if not r["qualified"] and not r["q3_ever"]),
                           qualified=sum(1 for r in rs if r["qualified"]), entries=len(e))
        rep["per_year"][y] = row
    return rep


def run_all(frames: dict, params: S.Params = S.PRIMARY, *, no_volume=(), log=print) -> dict:
    reports = {}
    for name, fr in frames.items():
        reports[name] = market_report(fr, params, no_volume=name in set(no_volume))
        log(f"{name} ({fr.chart}): {fr.n} bars, {len(reports[name]['entries'])} entries")
    return reports


def summarize(reports: dict, cl4h_key: str | None = "CL4H") -> dict:
    prim = {m: r for m, r in reports.items() if m != cl4h_key}
    ents = [e for r in prim.values() for e in r["entries"]]

    def block(es):
        return dict(
            entries=len(es), long=sum(1 for e in es if e["side"] == 1), short=sum(1 for e in es if e["side"] == -1),
            grade_dist={g: sum(1 for e in es if e["grade"] == g) for g in range(6)},
            k=dict(median=_pct([e["k"] for e in es], 50), p90=_pct([e["k"] for e in es], 90),
                   max=(max(e["k"] for e in es) if es else None)),
            d_atr=dict(median=_pct([e["d_atr"] for e in es], 50), p90=_pct([e["d_atr"] for e in es], 90),
                       max=(max(e["d_atr"] for e in es) if es else None)),
            stop_dist_usd=dict(median=_pct([e["dist_usd"] for e in es], 50), p90=_pct([e["dist_usd"] for e in es], 90),
                               max=(max(e["dist_usd"] for e in es) if es else None),
                               sizeable=_sizeable([e["dist_usd"] for e in es])))

    out = dict(primary=block(ents))
    out["primary"]["underpowered"] = len(ents) < S.MIN_ENTRIES
    out["primary"]["counts"] = {k: sum(r["signal_counts"].get(k, 0) for r in prim.values())
                                for k in next(iter(prim.values()))["signal_counts"]} if prim else {}
    out["primary"]["sim_counts"] = {k: sum(r["sim_counts"].get(k, 0) for r in prim.values())
                                    for k in next(iter(prim.values()))["sim_counts"]} if prim else {}
    if cl4h_key in reports:
        cl = reports[cl4h_key]
        out["cl4h"] = block(cl["entries"])
        out["cl4h"]["demoted_to_reported_only"] = len(cl["entries"]) < S.MIN_ENTRIES
        out["cl4h"]["counts"] = cl["signal_counts"]
        out["cl4h"]["sim_counts"] = cl["sim_counts"]
    return out


def _block_lines(p, title, b):
    p(title)
    p(f"  entries {b['entries']}  (long {b['long']}, short {b['short']})")
    p("  grade distribution: " + ", ".join(f"{g}:{n}" for g, n in b["grade_dist"].items()))
    if b["entries"]:
        p(f"  run length k: median {b['k']['median']:.0f}, p90 {b['k']['p90']:.0f}, max {b['k']['max']}")
        p(f"  D/ATR[O]: median {b['d_atr']['median']:.1f}, p90 {b['d_atr']['p90']:.1f}, max {b['d_atr']['max']:.1f}")
        d = b["stop_dist_usd"]
        sz = ", ".join(f"{k}: {100 * v:.0f}%" for k, v in d["sizeable"].items() if v is not None)
        p(f"  initial stop $/contract: median ${d['median']:,.0f}, p90 ${d['p90']:,.0f}, max ${d['max']:,.0f};"
          f" sizeable at 0.5/1/2% of $22,129 -> {sz}")
    if b.get("counts"):
        p("  signal counts: " + ", ".join(f"{k}={v}" for k, v in b["counts"].items()))
        p("  walk counts:   " + ", ".join(f"{k}={v}" for k, v in b["sim_counts"].items()))


def render(reports: dict, summary: dict, vol: dict | None, *, scoped=False, notes=()) -> str:
    L = []
    p = L.append
    p("BREIT-CAP G2 PRE-FLIGHT -- REGISTERED_breit_cap.md sec 5.2 (W15-0022 subitem 5)")
    p("TRAINING SIDE ONLY (2010-06 .. 2021-12), COUNTS ONLY: no exit price is read and no P&L is computed.")
    if scoped:
        p("!" * 100)
        p("SCOPED RUN (--markets): NOT THE REGISTERED PRE-FLIGHT.")
        p("!" * 100)
    for n in notes:
        p(n)
    if vol:
        p("")
        p("G1 VOLUME COVERAGE (share of training bars with held-contract volume > 0; need >= 99%):")
        for m, c in vol["coverage"].items():
            p(f"  {m:>5}: {100 * c:6.2f}%" + ("   <-- FAILS: G-volume scored 'no' throughout (PRE-RUN amendment)" if c < S.MIN_VOLUME_COVERAGE else ""))
    pr = summary["primary"]
    p("")
    p(f"PRIMARY BOOK (daily, 12 markets, both sides, graded): {pr['entries']} entries "
      f"(stop rule: fewer than {S.MIN_ENTRIES} -> STOP)")
    p("  -> " + ("UNDERPOWERED -- STOP. Report to Ben before any P&L is computed." if pr["underpowered"]
                 else "at or above 150: continue to the backtest item."))
    _block_lines(p, "", pr)
    if "cl4h" in summary:
        cl = summary["cl4h"]
        p("")
        p(f"CL 4-HOUR SECONDARY: {cl['entries']} entries -> "
          + ("DEMOTED to reported-only (fewer than 150); the primary continues" if cl["demoted_to_reported_only"]
             else "scored secondary (>= 150)"))
        _block_lines(p, "", cl)
    p("")
    p("PER MARKET PER YEAR AND SIDE: Q1 runs / fail Q2 / fail Q3 / qualified / entries")
    for m, r in reports.items():
        p(f"\n{m} ({r['chart']}, {r['bars']} bars)" + ("   [G-volume forced to 'no']" if r["no_volume"] else ""))
        p(f"  {'year':<6}{'side':<7}{'Q1':>5}{'!Q2':>5}{'!Q3':>5}{'qual':>6}{'entr':>6}")
        for y, row in r["per_year"].items():
            for nm in ("long", "short"):
                v = row[nm]
                if v["q1_runs"]:
                    p(f"  {y:<6}{nm:<7}{v['q1_runs']:>5}{v['fail_q2']:>5}{v['fail_q3']:>5}{v['qualified']:>6}{v['entries']:>6}")
    return "\n".join(L) + "\n"
