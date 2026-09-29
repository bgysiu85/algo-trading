#!/usr/bin/env python3
"""G2 -- CRUDELE-3S pre-flight (training side only, COUNTS ONLY). REGISTERED_crudele_3s.md sec 5.2.

Per market per year: the share of bars in each state; T episodes; MR arms and triggers; C stop-runs;
entries by arm and side; the initial stop distance in $ per vehicle contract; the share of entries
sizeable at 0.5%, 1% and 2% of $22,129. NO EXIT PRICE IS READ AND NO P&L IS COMPUTED HERE: this module
reads only the entry side of each simulated trade (bar, side, arm, entry price, initial stop). The walk
that decides WHEN a position is flat again (so that one-position-at-a-time entry counts are right)
runs inside sim.simulate and is not read back; the runner has no P&L flag (run.py refuses one).

Stop rules (sec 5.2): fewer than 150 entries in total -> STOP, underpowered, back to Ben before any P&L;
an arm with fewer than 30 entries is "too few to read" (does not stop the study).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.crudele_3s import sim as SIM
from strategy.crudele_3s import spec as S
from strategy.crudele_3s import states as ST
from strategy.futbt import core as K

RISKS = (0.005, 0.01, 0.02)
FORBIDDEN_KEYS = ("exit_px", "gross", "net", "pnl", "reason_px")


def _pct(v, q):
    return float(np.percentile(v, q)) if len(v) else None


def _sizeable(dists, equity=K.EQUITY):
    out = {}
    for r in RISKS:
        out[f"{r:.3%}"] = (float(np.mean([np.floor(r * equity / d) >= 1 for d in dists])) if len(dists) else None)
    return out


def market_report(fr: K.Frame, params: S.Params = S.PRIMARY) -> dict:
    sg = ST.compute(fr, params)
    trades, cnt = SIM.simulate(fr, sg, equity=K.EQUITY, integer=False)
    first = S.BWR_WIN + S.BB_LEN - 2
    years = fr.dates.year.to_numpy()
    rep = dict(market=fr.market, chart=fr.chart, bars=fr.n, first_valid=int(first), counts=dict(sg.counts),
               sim_counts=cnt, per_year={}, entries=[])
    for t in trades:                                     # entry side only
        dist_usd = abs(t.entry_px - t.stop_init) * fr.mult
        tgt = sg.sig_tgt[t.signal_j]
        usable = bool(t.arm == S.ARM_T and np.isfinite(tgt) and ((t.direction == 1 and tgt > t.entry_px)
                                                                  or (t.direction == -1 and tgt < t.entry_px)))
        rep["entries"].append(dict(year=int(years[t.entry_j]), arm=t.arm, side=int(t.direction),
                                   dist_usd=float(dist_usd), t_target_usable=usable))
    ys = sorted(set(int(y) for y in years))
    for y in ys:
        m = (years == y) & (np.arange(fr.n) >= first)
        nb = int(m.sum())
        st = sg.state[m]
        e = [x for x in rep["entries"] if x["year"] == y]
        rep["per_year"][y] = dict(
            bars=nb, **{f"share_{ST.STATE_NAMES[k]}": (float((st == k).mean()) if nb else None) for k in (0, 1, 2, 3)},
            t_signals=int(((sg.sig_arm == 1) & m).sum()), mr_triggers=int(((sg.sig_arm == 2) & m).sum()),
            c_stop_runs=int(((sg.sig_arm == 3) & m).sum()),
            bands_in=int(((sg.bands_in_ep >= 0) & m).sum()),
            entries={f"{a}_{'long' if s == 1 else 'short'}": sum(1 for x in e if x["arm"] == a and x["side"] == s)
                     for a in S.ARMS for s in (1, -1)})
    trans = int((np.diff(sg.state[first:].astype(int)) != 0).sum())
    rep["state_transitions"] = trans
    rep["t_signals_no_target"] = int(((sg.sig_arm == 1) & ~np.isfinite(sg.sig_tgt)).sum())
    rep["t_entries_target_usable"] = sum(1 for x in rep["entries"] if x["t_target_usable"])
    return rep


def run_all(frames: dict, params: S.Params = S.PRIMARY, log=print) -> dict:
    reports = {}
    for name, fr in frames.items():
        reports[name] = market_report(fr, params)
        log(f"{name}: {fr.n} bars, {len(reports[name]['entries'])} entries")
    entries = [e for r in reports.values() for e in r["entries"]]
    by_arm = {a: sum(1 for e in entries if e["arm"] == a) for a in S.ARMS}
    dist = {a: [e["dist_usd"] for e in entries if e["arm"] == a] for a in S.ARMS}
    summary = dict(
        total_entries=len(entries), by_arm=by_arm,
        by_arm_side={f"{a}_{'long' if s == 1 else 'short'}": sum(1 for e in entries if e["arm"] == a and e["side"] == s)
                     for a in S.ARMS for s in (1, -1)},
        stop_dist_usd={a: dict(median=_pct(d, 50), p90=_pct(d, 90), max=(max(d) if d else None),
                               sizeable=_sizeable(d)) for a, d in dist.items()},
        underpowered=len(entries) < S.MIN_ENTRIES,
        arms_too_few={a: n < S.MIN_ARM_ENTRIES for a, n in by_arm.items()},
        totals={k: sum(r["counts"].get(k, 0) for r in reports.values()) for k in
                ("t_episodes", "t_bands_in", "t_timeouts", "mr_arms", "mr_arms_skipped_h", "mr_triggers",
                 "mr_expired", "c_stop_runs", "c_both_sides")},
        sim_totals={k: sum(r["sim_counts"].get(k, 0) for r in reports.values())
                    for k in reports[next(iter(reports))]["sim_counts"]} if reports else {},
        t_signals_no_target=sum(r["t_signals_no_target"] for r in reports.values()),
        t_entries_target_usable=sum(r["t_entries_target_usable"] for r in reports.values()),
        state_transitions=sum(r["state_transitions"] for r in reports.values()))
    return dict(summary=summary, markets=reports)


def _clean(rep: dict) -> dict:
    """Entries are kept as counts and distances only (no keys that could be a price or a P&L)."""
    out = {"summary": rep["summary"], "markets": {}}
    for m, r in rep["markets"].items():
        r2 = {k: v for k, v in r.items() if k != "entries"}
        r2["n_entries"] = len(r["entries"])
        out["markets"][m] = r2
    return out


def render(rep: dict, *, scoped: bool = False, notes=()) -> str:
    s = rep["summary"]
    L = []
    p = L.append
    p("CRUDELE-3S G2 PRE-FLIGHT -- REGISTERED_crudele_3s.md sec 5.2 (W15-0022 subitem 5)")
    p("TRAINING SIDE ONLY (2010-06 .. 2021-12), COUNTS ONLY: no exit price is read and no P&L is computed.")
    if scoped:
        p("!" * 100)
        p("SCOPED RUN (--markets): NOT THE REGISTERED PRE-FLIGHT.")
        p("!" * 100)
    for n in notes:
        p(n)
    p("")
    p(f"TOTAL ENTRIES: {s['total_entries']}  (stop rule: fewer than {S.MIN_ENTRIES} -> STOP)")
    p("  -> " + ("UNDERPOWERED -- STOP. Report to Ben before any P&L is computed." if s["underpowered"]
                 else "at or above 150: continue to the backtest item."))
    p("")
    p("ENTRIES BY ARM (fractional book at $22,129, one position per market):")
    for a in S.ARMS:
        tag = "   <-- too few to read (< 30)" if s["arms_too_few"][a] else ""
        p(f"  {a:>3}: {s['by_arm'][a]:>5}  (long {s['by_arm_side'][a + '_long']}, short {s['by_arm_side'][a + '_short']}){tag}")
    p("")
    p("STATE-MACHINE COUNTS (all markets): " + ", ".join(f"{k}={v}" for k, v in s["totals"].items()))
    p(f"  state transitions {s['state_transitions']}; T signals with no earlier-episode target: {s['t_signals_no_target']};"
      f" T entries whose earlier-episode target is usable (beyond the fill): {s['t_entries_target_usable']}")
    p("  walk counts: " + ", ".join(f"{k}={v}" for k, v in s["sim_totals"].items()))
    p("")
    p("INITIAL STOP DISTANCE, $ per vehicle contract (MES, M2K, MCL, MGC, SIL, MHG, M6x, MTN; full NG and 6J):")
    for a in S.ARMS:
        d = s["stop_dist_usd"][a]
        if d["median"] is None:
            p(f"  {a:>3}: no entries")
            continue
        sz = ", ".join(f"{k}: {100 * v:.0f}%" for k, v in d["sizeable"].items() if v is not None)
        p(f"  {a:>3}: median ${d['median']:,.0f}, p90 ${d['p90']:,.0f}, max ${d['max']:,.0f};  sizeable at 0.5/1/2% of $22,129 -> {sz}")
    p("")
    p("PER MARKET PER YEAR: share of bars in N / C / T / MR, T signals, bands-in, MR triggers, C stop-runs, entries")
    for m, r in rep["markets"].items():
        p(f"\n{m}  ({r['chart']}, {r['bars']} bars)  transitions {r['state_transitions']}  entries {r['n_entries']}")
        p(f"  {'year':<6}{'N':>6}{'C':>6}{'T':>6}{'MR':>6}{'Tsig':>6}{'in':>5}{'MRtr':>6}{'Cst':>5}   entries by arm/side")
        for y, v in r["per_year"].items():
            if not v["bars"]:
                continue
            en = " ".join(f"{k}={n}" for k, n in v["entries"].items() if n)
            p(f"  {y:<6}{100 * v['share_N']:>5.0f}%{100 * v['share_C']:>5.0f}%{100 * v['share_T']:>5.0f}%"
              f"{100 * v['share_MR']:>5.0f}%{v['t_signals']:>6}{v['bands_in']:>5}{v['mr_triggers']:>6}"
              f"{v['c_stop_runs']:>5}   {en}")
    return "\n".join(L) + "\n"
