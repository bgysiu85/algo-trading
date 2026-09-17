#!/usr/bin/env python3
r"""MCL as published on two tapes -- XNAS.BASIC (TRF-contaminated before 2026-03-30) and XNAS.ITCH (exchange only).

    python -m common.tape_compare --jobs 8

Registered in docs/research/REGISTERED_tape_compare.md before it ran. Same
universe, same floor, same engine, same costs; the only thing that differs
between the two books is the bars. Read as a measurement of the tape, not of
the strategy.
"""
from __future__ import annotations

import argparse
import os
import time
from collections import Counter, defaultdict
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.entry_shares import MEASURED_FRICTION, QTY
from common.report_io import emit
from common.tape_spikes import spike_mask

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
TRF_CUT = "2026-03-30"           # the day the TRF began opening at 04:00
A, B = "XNAS.BASIC", "XNAS.ITCH"


def trade_rows(trades, symbol, day):
    out = []
    for t in trades:
        e = pd.Timestamp(t.entry_time).tz_convert(ET)
        out.append({"symbol": symbol, "date": day, "net": float(t.net),
                    "entry_hour": int(e.hour), "reason": t.reason,
                    "entry_px": float(t.entry_price), "exit_px": float(t.exit_price)})
    return out


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths_a, paths_b, day, universe = args
    frames = {}
    spikes = {}
    for tag, paths in ((A, paths_a), (B, paths_b)):
        parts = []
        for pth in paths:
            try:
                f = read_dbn(Path(pth))
            except Exception as e:                          # noqa: BLE001
                return day, None, f"{tag} unreadable ({type(e).__name__}: {e})"
            if not f.empty:
                parts.append((Path(pth).name[:10], f))
        if not parts or parts[-1][0] != day:
            return day, None, f"{tag} has no slice for {day}"
        frames[tag] = build_frame(parts, day)
        today = parts[-1][1]
        spikes[tag] = (int(len(today)), int(spike_mask(today).sum()))

    mod, extra = engine("mcl")
    d = _date.fromisoformat(day)
    res = {"trades": {A: [], B: []}, "spikes": spikes, "symdays": 0,
           "b_missing": 0, "b_bars": 0, "a_bars": 0, "errors": []}
    for rec in universe:
        dfa = frames[A][frames[A]["symbol"] == rec["symbol"]]
        dfb = frames[B][frames[B]["symbol"] == rec["symbol"]]
        if dfa.empty or not rec.get("first_seen"):
            continue
        res["symdays"] += 1
        if dfb.empty:
            res["b_missing"] += 1
        res["a_bars"] += int(len(dfa)); res["b_bars"] += int(len(dfb))
        floor = first_seen_time(rec)
        for tag, df in ((A, dfa), (B, dfb)):
            if df.empty:
                continue
            try:
                tr = mod.backtest_session(df.sort_index(kind="mergesort"), d, ET,
                                          entry_shares=QTY, not_before=floor, **extra)
            except Exception as e:                          # noqa: BLE001
                res["errors"].append(f"{tag} {rec['symbol']} {day}: {type(e).__name__}: {e}")
                continue
            res["trades"][tag] += trade_rows(tr, rec["symbol"], day)
    return day, res, ""


# --- report -----------------------------------------------------------------

def money(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def per(rows) -> float:
    f = MEASURED_FRICTION
    return sum(r["net"] - f for r in rows) / len(rows) if rows else 0.0


def tot(rows) -> float:
    return sum(r["net"] - MEASURED_FRICTION for r in rows)


def drop_top(rows, n=5) -> float:
    v = sorted((r["net"] - MEASURED_FRICTION for r in rows), reverse=True)
    return sum(v[n:])


def line(label, ra, rb) -> str:
    return (f"  {label:<30}{len(ra):>7,} {money(per(ra)):>9}/t {money(tot(ra)):>13}"
            f"   | {len(rb):>7,} {money(per(rb)):>9}/t {money(tot(rb)):>13}")


def render(days, got, elapsed, jobs) -> list[str]:
    ta = [t for r in got.values() for t in r["trades"][A]]
    tb = [t for r in got.values() for t in r["trades"][B]]
    symdays = sum(r["symdays"] for r in got.values())
    b_missing = sum(r["b_missing"] for r in got.values())
    a_bars = sum(r["a_bars"] for r in got.values()); b_bars = sum(r["b_bars"] for r in got.values())
    sa = [r["spikes"][A] for r in got.values()]; sb = [r["spikes"][B] for r in got.values()]
    cut = days[len(days) // 2] if days else ""
    L = ["MCL AS PUBLISHED ON TWO TAPES", "",
         "  registered  docs/research/REGISTERED_tape_compare.md",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}   {QTY} shares, $4.26 friction",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)", "",
         "COVERAGE", "",
         f"  symbol-days with no {B} bars at all: {b_missing:,} of {symdays:,}",
         f"  bars on the universe's symbol-days: {A} {a_bars:,}   {B} {b_bars:,}   ({100 * b_bars / a_bars if a_bars else 0:.0f}%)",
         f"  spike bars, whole slices: {A} {sum(s for _, s in sa):,} of {sum(n for n, _ in sa):,}"
         f"   {B} {sum(s for _, s in sb):,} of {sum(n for n, _ in sb):,}", "",
         f"THE BOOKS   {A:>40}   | {B:>33}", ""]
    L.append(line("all sessions", ta, tb))
    L.append(line(f"  drop top 5", [], [])[:32] + f"{'':>7} {'':>9}   {money(drop_top(ta)):>13}   | {'':>7} {'':>9}   {money(drop_top(tb)):>13}")
    ea, la = [t for t in ta if t["date"] < cut], [t for t in ta if t["date"] >= cut]
    eb, lb = [t for t in tb if t["date"] < cut], [t for t in tb if t["date"] >= cut]
    L.append(line("  early half", ea, eb)); L.append(line("  late half", la, lb))
    L += ["", f"THE SPLIT AT {TRF_CUT} (the TRF began opening at 04:00)", ""]
    pa, qa = [t for t in ta if t["date"] < TRF_CUT], [t for t in ta if t["date"] >= TRF_CUT]
    pb, qb = [t for t in tb if t["date"] < TRF_CUT], [t for t in tb if t["date"] >= TRF_CUT]
    L.append(line("before", pa, pb)); L.append(line("after", qa, qb))
    L.append(f"  before minus after, per trade      {per(pa) - per(qa):>+9.2f}"
             f"{'':>15}   | {per(pb) - per(qb):>+9.2f}")
    L.append("  (negative = the earlier period was worse; if the tape is the cause it shrinks on the right)")
    L += ["", "BY ENTRY HOUR (ET), per trade", "",
          f"  {'hour':<8}{A + ' before':>20}{A + ' after':>20}   | {B + ' before':>20}{B + ' after':>20}"]
    for h in range(4, 10):
        def f(rows):
            sel = [t for t in rows if t["entry_hour"] == h]
            return f"{money(per(sel))} ({len(sel):,})" if sel else "-"
        L.append(f"  {h:02d}:00   {f(pa):>20}{f(qa):>20}   | {f(pb):>20}{f(qb):>20}")
    L += [""]

    # Paired by symbol-day.
    ka = defaultdict(float); kb = defaultdict(float)
    for t in ta: ka[(t["symbol"], t["date"])] += t["net"] - MEASURED_FRICTION
    for t in tb: kb[(t["symbol"], t["date"])] += t["net"] - MEASURED_FRICTION
    keys = sorted(set(ka) | set(kb))
    dd = np.array([kb.get(k, 0.0) - ka.get(k, 0.0) for k in keys])
    if len(dd):
        rng = np.random.default_rng(20260917)
        bs = np.array([rng.choice(dd, len(dd)).sum() for _ in range(2000)])
        L += ["PAIRED BY SYMBOL-DAY (exchange-only minus contaminated, net at $4.26)", "",
              f"  symbol-days with a trade on either tape: {len(keys):,}",
              f"  better on {B}: {int((dd > 0.005).sum()):,}   worse: {int((dd < -0.005).sum()):,}   same: {int((abs(dd) <= 0.005).sum()):,}",
              f"  total delta {money(dd.sum())}   bootstrap 95% [{money(np.percentile(bs, 2.5))}, {money(np.percentile(bs, 97.5))}]   P(>0) {float((bs > 0).mean()):.3f}", ""]
    errs = [e for r in got.values() for e in r["errors"]]
    if errs:
        L += [f"  {len(errs)} symbol-day engine errors (dropped from that tape only):"] + [f"    {e}" for e in errs[:10]] + [""]
    L += ["WHAT THIS IS", "",
          "  A measurement of the tape. Same trades rule, same universe, same",
          "  costs; the bars are the only difference. It says nothing about",
          "  whether MCL works. If it is still negative on the exchange-only",
          "  tape, the closed findings stand on a better measurement; if it is",
          "  not, the closed studies are re-run on this tape under their own",
          "  registrations before anything is said.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/tape_compare_mcl.txt")
    p.add_argument("--csv", default="var/reports/tape_compare_mcl.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    sa = {date_of(p): p for p in window_slices(archive, A)}
    sb = {date_of(p): p for p in window_slices(archive, B)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in sa and d in sb]
    only_a = [d for d in days if d in sa and d not in sb]
    print(f"tape_compare: {len(have):,} session(s) on both tapes; {len(only_a)} on {A} only", flush=True)
    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        win = have[first:k + 1]
        tasks.append(([str(sa[d]) for d in win], [str(sb[d]) for d in win], day, by_date[day]))
    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    t0 = time.time()
    got = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=2)
    for k, (day, res, err) in enumerate(it, 1):
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if res is not None:
            got[day] = res
        if k % 50 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()
    run_days = sorted(got)
    emit("\n".join(render(run_days, {d: got[d] for d in run_days}, time.time() - t0, jobs)), a.out)
    rows = [dict(t, tape=tag) for d in run_days for tag in (A, B) for t in got[d]["trades"][tag]]
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.csv, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
