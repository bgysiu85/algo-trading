#!/usr/bin/env python3
r"""W05-0005 -- dist_from_high as an entry gate, on its OWN registration.

    python -m common.dist_from_high_gate --jobs 8

Registered in docs/research/REGISTERED_dist_from_high.md before this file
existed. `chase_gate_RESULT_20260918.md` tested `dist_from_high` INSTEAD of
the `ret_5m` chase ceiling, at a budget matched to `ret_5m <= 0.083`, and
found the only cell in that whole study to beat its own abstention control.
`session_close_20260918.md` was explicit that the two thresholds that scored
(-0.1594 MCL, -0.1993 MC5) cannot be promoted as-is -- they are the output of
a fence built to keep a good-looking number from being promoted after the
fact. This module reruns the SAME procedure as its own registration, all
five readings SCORED rather than fenced off.

THE RULE. A BUY entry is refused when `dist_from_high` -- the signal bar's
distance below the session's running high-to-date, always <= 0 -- is MORE
NEGATIVE than a threshold, i.e. the name has fallen further from its own
high than the threshold allows. Delivered through the `entry_gate` hook, the
same AND-mask `chase_gate.py` uses; it is a backtest-only parameter and does
not reach `evaluate_last_bar` (tests/common/test_dist_from_high_gate.py
pins that, mirroring tests/common/test_chase_gate.py).

TEN CELLS, FIVE BUDGETS PER BOOK -- REGISTRATION §3.
------------------------------------------------------------------------
Three budgets are SOLVED, reusing `chase_gate.solve_distance` unchanged: for
each of the ret_5m ceilings 0.033 / 0.083 / 0.100 -- three of the five values
`chase_gate.CEILS` already swept -- a `dist_from_high` threshold is solved so
it refuses the SAME COUNT that ceiling refuses, computed fresh from the
current features file, blind to any P&L. `c083` is the SAME solve chase_gate
already ran at its own ANCHOR, so its D must equal the fenced -0.1594 /
-0.1993 exactly; a test pins that too.

Two budgets are DIRECT: `dist_from_high` thresholds read straight off
its own observed distribution at signal time (the 10th and 35th
percentile of the non-missing values, per book) rather than matched to a
ret_5m count. This is the part of §3 registration text ("two additional
values spaced the same way over the observed range of dist_from_high at
signal time") that names dist_from_high's own range rather than ret_5m's,
and there is a judgment call in it worth flagging to Ben on review: the
registration does not pin the exact two percentile points, and 10 / 35 was
this build's choice -- reported plainly as such (see `direct_block`), never
solved against a P&L either way.

NOTHING HERE REPEATS THE FENCED CELL. The two numbers -0.1594 / -0.1993 are
not reused as thresholds; they fall out of the c083 solve here exactly as a
by-product, and the by-product is compared against the 2026-09-18 figures
only to confirm the two runs agree, never as an input.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

from common import gate_study as G
from common import running_up as RU
from common.chase_gate import solve_distance, stamp_on
from common.entry_shares import QTY
from common.report_io import emit

PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_dist_from_high.md"
CHASE_GATE_REGISTERED = "docs/research/REGISTERED_chase_gate.md"

# The three ret_5m ceilings reused from chase_gate.CEILS = (0.033, 0.050,
# 0.083, 0.100, 0.150); 0.083 is chase_gate's own ANCHOR, so the c083 cell's
# solved D must equal the fenced -0.1594 (MCL) / -0.1993 (MC5) exactly.
CEIL_BUDGETS = (0.033, 0.083, 0.100)
ANCHOR = 0.083
ANCHOR_BUDGET = "c083"
# Direct thresholds off dist_from_high's own distribution -- NOT matched to
# any ret_5m count. See the module docstring: this pair of percentiles is
# this build's choice, not something the registration pinned.
QUANTILE_BUDGETS = (10.0, 35.0)

FENCED = {"MCL-dist": -0.1594202898550724, "MC5-dist": -0.19926199261992616}


def _budget_name(kind: str, value: float) -> str:
    if kind == "ceil":
        return f"c{int(round(value * 1000)):03d}"
    return f"q{int(round(value)):02d}"


BUDGETS: tuple[tuple[str, str, float], ...] = (
    tuple(("ceil", c, _budget_name("ceil", c)) for c in CEIL_BUDGETS)
    + tuple(("quantile", q, _budget_name("quantile", q)) for q in QUANTILE_BUDGETS)
)
BUDGET_NAMES = tuple(name for _, _, name in BUDGETS)
assert ANCHOR_BUDGET in BUDGET_NAMES


def _dist_key(eng: str, budget: str) -> str:
    return f"{eng.upper()}-{budget}"


BOOKS: list[tuple] = []
for _eng in ("mcl", "mc5"):
    BOOKS.append((_eng.upper(), _eng, None))
    for _name in BUDGET_NAMES:
        BOOKS.append((_dist_key(_eng, _name), _eng, _name))
BOOKS = tuple(BOOKS)

PAIRED = tuple((eng.upper(), _dist_key(eng, name))
               for eng in ("mcl", "mc5") for name in BUDGET_NAMES)


def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x


# --- the solve ----------------------------------------------------------------------

def read_features(path: str) -> dict[str, list[dict]]:
    """book -> rows, same shape chase_gate.read_features produces."""
    import csv
    out: dict[str, list[dict]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["book"], []).append(r)
    return out


def solve_budgets(feats: dict[str, list[dict]]) -> tuple[dict, dict]:
    """dists[name] -> D, solved[name] -> (target_or_None, refused_by_distance).

    The three `ceil` budgets are solved exactly as chase_gate solves its own
    ANCHOR -- IMPORTED, not restated, so c083 reproduces the fenced number by
    construction. The two `quantile` budgets read the threshold straight off
    the observed, non-missing dist_from_high values; there is no target to
    match, only the count that percentile happens to refuse.
    """
    dists: dict[str, float] = {}
    solved: dict[str, tuple] = {}
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        rows = feats.get(base, [])
        dfh = np.array([_f(r["dist_from_high"]) for r in rows])
        dfh = dfh[~np.isnan(dfh)]
        for kind, value, name in BUDGETS:
            key = _dist_key(base, name)
            if kind == "ceil":
                d, target, got = solve_distance(rows, value)
                dists[key] = d
                solved[key] = (target, got)
            else:
                d = float(np.percentile(dfh, value)) if len(dfh) else float("-inf")
                got = int((dfh < d).sum())
                dists[key] = d
                solved[key] = (None, got)
    return dists, solved


# --- the gate -----------------------------------------------------------------------

def gate_for(df: pd.DataFrame, dist: float) -> pd.Series:
    """Boolean Series on `df`'s own index: True where an entry is allowed.

    Refused when dist_from_high < dist. NaN is ADMITTED -- too little session
    history to know how far off the high a name is, is not evidence that it
    has fallen. Same convention as chase_gate.gate_for's "dist" kind, and the
    same feature (common.running_up.dist_series), imported rather than
    restated.
    """
    return (~(RU.dist_series(df) < dist)).astype(bool)


# --- one session --------------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    from strategy.mc5 import mc5

    paths, day, universe, dists = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    res = {"books": {name: [] for name, _, _ in BOOKS}, "symdays": 0, "errors": 0,
           "error_days": [],
           "refused": {g: [] for _, g in PAIRED},
           "binding": {g: [0, 0, Counter()] for _, g in PAIRED}}

    for rec in universe:
        if not rec.get("first_seen"):
            continue
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            idx5 = mc5.to_5m(df).index
            got = {}
            for name, eng, budget in BOOKS:
                mod, extra = engines[eng]
                gate = None
                if budget is not None:
                    g = gate_for(df, dists[name])
                    gate = stamp_on(g, idx5 if eng == "mc5" else df.index)
                got[name] = mod.backtest_session(df, d, RU.ET, entry_shares=QTY,
                                                 not_before=floor, entry_gate=gate,
                                                 **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue

        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [G.trade_row(t, s, day, k)
                                   for k, t in enumerate(trades, 1)]

        for name, eng, budget in BOOKS:
            if budget is None:
                continue
            base = "MCL" if eng == "mcl" else "MC5"
            g = gate_for(df, dists[name])
            b = res["binding"][name]
            for t in got[base]:
                ts = pd.Timestamp(f"{day} {t.entry_time}", tz=RU.ET) \
                    if isinstance(t.entry_time, str) else t.entry_time
                allowed = bool(g.reindex([ts], method="ffill").fillna(True).iloc[0])
                b[1] += 1
                b[0] += 1
                b[2][int(allowed)] += 1
                if not allowed:
                    res["refused"][name].append(G.trade_row(t, s, day, 0))
    return day, res, ""


# --- the blocks this study adds -----------------------------------------------------

def threshold_block(dists: dict, solved: dict) -> list[str]:
    L = ["THE FIVE BUDGETS PER BOOK (§3): THREE SOLVED, TWO DIRECT", "",
         "  SOLVED (matched to a ret_5m ceiling's removal count, blind to P&L,",
         "  chase_gate.solve_distance reused unchanged):", ""]
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        for kind, value, name in BUDGETS:
            if kind != "ceil":
                continue
            key = _dist_key(base, name)
            target, got = solved[key]
            L.append(f"    {key:<10} ceil {value:<6} D {dists[key]:+.4f}   "
                     f"ceiling refuses {target:,}   pair refuses {got:,}   "
                     f"gap {abs(got - target):,}")
    L += ["", "  DIRECT (off dist_from_high's own observed range at signal time --",
          "  this build's choice of percentile, reported plainly as such, see",
          "  the module docstring; not solved against anything):", ""]
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        for kind, value, name in BUDGETS:
            if kind != "quantile":
                continue
            key = _dist_key(base, name)
            _, got = solved[key]
            L.append(f"    {key:<10} p{value:<5.0f} D {dists[key]:+.4f}   refuses {got:,}")
    L += ["", "  WHERE c083 LANDS AGAINST THE 2026-09-18 FENCED NUMBERS (not reused as",
          "  an input -- the fence exists precisely so a good-looking number could",
          "  not be promoted; this checks the SAME solve reproduces it, no more):",
          ""]
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        key = _dist_key(base, ANCHOR_BUDGET)
        fenced = FENCED.get(f"{base}-dist")
        got_d = dists[key]
        match = "matches exactly" if fenced is not None and abs(got_d - fenced) < 1e-9 \
            else f"DIFFERS from {fenced:+.4f}" if fenced is not None else "no fenced value on file"
        L.append(f"    {key:<10} D {got_d:+.4f}   {match}")
    L.append("")
    return L


def overlap_block(feats: dict, dists: dict) -> list[str]:
    """§5: of the trades this gate refuses at the matched (c083) budget, how
    many ret_5m's ceiling at the same budget already refused. Computed
    straight off the features population -- both signals are columns on the
    same row, so no engine pass is needed for this one. A gate mostly
    re-refusing the chase gate's own trades is not a second mechanism."""
    L = ["OVERLAP WITH THE CHASE GATE ITSELF, AT THE MATCHED (c083) BUDGET (§5)", "",
         "  Of the entries this gate refuses, the share ret_5m <= 0.083 already", "  refused too:", ""]
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        rows = feats.get(base, [])
        d = dists[_dist_key(base, ANCHOR_BUDGET)]
        dist_refused = [r for r in rows if _f(r["dist_from_high"]) < d]
        chase_refused_set = {(r["symbol"], r["date"], r["entry_et"])
                             for r in rows if _f(r["ret_5m"]) > ANCHOR}
        n = len(dist_refused)
        if not n:
            L.append(f"  {base:<5} the gate refused nothing at this budget")
            continue
        overlap = sum(1 for r in dist_refused
                     if (r["symbol"], r["date"], r["entry_et"]) in chase_refused_set)
        L.append(f"  {base:<5} dist_from_high refused {n:,}   also refused by "
                 f"ret_5m<=0.083: {overlap:,} ({100.0 * overlap / n:.1f}%)")
    L.append("")
    return L


def marginal_block(books: dict) -> list[str]:
    """What each REFUSED trade was worth, adapted from chase_gate.marginal_block
    for this module's own BOOKS."""
    L = ["WHAT EACH REFUSED TRADE WAS WORTH (the marginal trade)", "",
         "  (tot(cell) - tot(base)) / (n(cell) - n(base)). A gate refusing",
         "  trades WORSE than the book's average is selecting; one refusing",
         "  trades better than it is abstaining into its own average.", ""]
    for base in ("MCL", "MC5"):
        rows = books.get(base, [])
        n0, t0 = len(rows), sum(float(r["net"]) - G.MEASURED_FRICTION for r in rows)
        L.append(f"  {base}  base {n0:,} trades, {t0 / n0:+.2f}/trade"
                 if n0 else f"  {base}  base empty")
        for name, eng, budget in BOOKS:
            if budget is None or eng.upper() != base:
                continue
            rs = books.get(name, [])
            n1 = len(rs)
            t1 = sum(float(r["net"]) - G.MEASURED_FRICTION for r in rs)
            if n1 == n0:
                L.append(f"    {name:<12} removed 0 -- the gate never bound")
                continue
            L.append(f"    {name:<12} {n1:>6,} trades  {n1 - n0:+6,}  "
                     f"per trade {t1 / n1 if n1 else float('nan'):+7.2f}   "
                     f"MARGINAL {(t1 - t0) / (n1 - n0):+7.2f}")
        L.append("")
    return L


def population_refusal(books: dict, feats: dict) -> list[str]:
    """§5's input-refusal rule, identical shape to chase_gate.population_refusal."""
    L = []
    for base in ("MCL", "MC5"):
        here = {(r["symbol"], r["date"], r["entry_et"]) for r in books.get(base, [])}
        there = {(r["symbol"], r["date"], r["entry_et"]) for r in feats.get(base, [])}
        if here == there:
            L.append(f"  {base:<5} {len(here):,} baseline entries   matches the "
                     f"features file exactly")
        else:
            L.append(f"  {base:<5} *** INPUT REFUSAL *** {len(here):,} here against "
                     f"{len(there):,} in the features file")
            L.append(f"        {len(here - there):,} only here, "
                     f"{len(there - here):,} only there -- the solve ran on a "
                     f"different population and the §3 comparison is VOID")
    return ["THE SOLVE'S POPULATION, CHECKED AFTER THE RUN", ""] + L + [""]


# --- cli ----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--features", default=None,
                   help="the pre-flight's features CSV; the solve's population "
                        "(default: running_up_preflight's own --csv default)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/dist_from_high_gate.txt")
    p.add_argument("--csv", default="var/reports/dist_from_high_gate_trades.csv")
    p.add_argument("--skip", type=int, default=0,
                   help="chunking aid: skip this many sessions from the front "
                        "of the sorted day list before taking --limit")
    p.add_argument("--resume-pickle", default=None,
                   help="chunking aid: accumulate {day: res} here across several "
                        "invocations (each a separate --skip/--limit slice) so a "
                        "run that cannot stay alive in one process can still be "
                        "assembled from parts, never by re-deriving a day already run")
    p.add_argument("--finalize", action="store_true",
                   help="aggregate everything in --resume-pickle and write the "
                        "report; runs no new sessions unless --limit is also given")
    return p


def _features_default() -> str:
    from common.running_up_preflight import build_parser as ru_parser
    for a in ru_parser()._actions:
        if a.dest == "csv":
            return a.default
    return "var/reports/running_up_features.csv"


def main(argv=None) -> int:
    import pickle
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    features = a.features or _features_default()
    archive = Path(a.archive) if a.archive else default_archive()

    if not Path(features).exists():
        sys.exit(f"the features file {features} does not exist. It is written "
                 f"by:\n    python -m common.running_up_preflight --jobs 8\n"
                 "and this study solves its budgets on that population, so it "
                 "is refused rather than run without it.")
    feats = read_features(features)
    dists, solved = solve_budgets(feats)

    # Chunking aid (see --skip/--resume-pickle/--finalize): a run too long to
    # stay alive in one process is assembled from several slices of the SAME
    # sorted day list, day order fixed regardless of --skip so a day is never
    # re-sliced differently between chunks.
    all_tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, None)
    chunk = all_tasks[a.skip:a.skip + a.limit] if a.limit else all_tasks[a.skip:]
    chunk = [(p, d, u, dists) for p, d, u in chunk]
    jobs = G.jobs_from(a.jobs)
    if chunk:
        chunk_got, elapsed = G.run_sessions(run_day, chunk, jobs, "dist_from_high_gate")
    else:
        chunk_got, elapsed = {}, 0.0

    resume = Path(a.resume_pickle) if a.resume_pickle else None
    cum_elapsed = elapsed
    if resume is not None:
        got = pickle.loads(resume.read_bytes()) if resume.exists() else {}
        cum_elapsed = got.pop("__elapsed__", 0.0) + elapsed
        got.update(chunk_got)
        resume.parent.mkdir(parents=True, exist_ok=True)
        to_save = dict(got)
        to_save["__elapsed__"] = cum_elapsed
        resume.write_bytes(pickle.dumps(to_save))
        print(f"resume pickle now holds {len(got):,} day(s) (of {len(all_tasks):,}), "
              f"this chunk added {len(chunk_got):,} in {elapsed:.1f}s", flush=True)
    else:
        got = chunk_got

    if not a.finalize:
        print(f"chunk done ({a.skip}:{a.skip + len(chunk)}), not finalizing "
              "(pass --finalize to aggregate and write the report)", flush=True)
        return 0

    elapsed = cum_elapsed
    books = {name: [] for name, _, _ in BOOKS}
    refused = {g: [] for _, g in PAIRED}
    binding = {g: [0, 0, Counter()] for _, g in PAIRED}
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        for name in refused:
            refused[name] += r["refused"][name]
            b, rb = binding[name], r["binding"][name]
            b[0] += rb[0]
            b[1] += rb[1]
            b[2].update(rb[2])
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    binding_t = {k: (v[0], v[1], dict(v[2])) for k, v in binding.items()}
    preamble = (population_refusal(books, feats) + threshold_block(dists, solved)
               + overlap_block(feats, dists))
    body = G.render(
        "W05-0005: dist_from_high AS AN ENTRY GATE, ON ITS OWN REGISTRATION",
        REGISTERED, books, PAIRED, (), symdays, errors, run_days,
        elapsed, jobs, refused, binding_t, error_days, preamble=preamble,
        universe=a.pairs, dataset=a.dataset)
    body += marginal_block(books)
    emit("\n".join(body), a.out,
         header=f"common.dist_from_high_gate pairs={a.pairs} dataset={a.dataset} "
                f"sessions={len(run_days)} symbol_days={symdays} qty={QTY} "
                f"registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays,
                 run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else ""),
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "ceil_budgets": list(CEIL_BUDGETS), "quantile_budgets": list(QUANTILE_BUDGETS),
                  "dist_solved": {k: (None if v == float("-inf") else v)
                                  for k, v in dists.items()}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
