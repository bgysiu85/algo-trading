#!/usr/bin/env python3
r"""H-P1 -- refuse the entry when the name has already run.

    python -m common.chase_gate --jobs 8

Registered in docs/research/REGISTERED_chase_gate.md before this file existed.
The one cell from the Running Up pre-flight pointing the right way: on MCL the
trades that die on the next bar were entered after a median +11.43% five-minute
move and the survivors after +4.90% (AUC 0.751 against a rand control at
0.526). A gate on "is it running up" keeps MORE of the dying trades at every
threshold; the same numbers reversed are a filter.

THE RULE. An entry is refused when `ret_5m` at the entry bar exceeds CEIL.
Delivered through the engines' `entry_gate` hook -- an AND-mask over the rule's
own entries, signal-ordinal, None bit-identical -- the same hook H-B3 and H-B4
used. `ret_5m` comes from common.running_up, IMPORTED rather than restated, so
the gate is the pre-flight's own feature by construction.

WHY MOST OF THE WORK HERE IS ABOUT THE SECOND CONDITION
-------------------------------------------------------
The tempting cell is the two-condition one -- near the session high AND not
extended -- which reads 3.3% one-bar on MCL against a 12.6% base. Registering
that as a cell would bury the fact that `dist_from_high` separates almost
nothing on its own: AUC 0.494 on MCL and 0.443 on MC5, against `rand` at
0.526 / 0.505, while `ret_5m` reads 0.751 / 0.636. On a losing book,
tightening ANY condition improves the total, so the second knob would look
like it was contributing whatever it did.

So the second condition is a COMPARISON at a matched abstention budget, the
way H-S6 compared the give-back's shape against a flat stop: D is SOLVED so
that `dist_from_high >= D` ALONE refuses as close as possible to the number of
baseline entries `ret_5m <= ANCHOR` refuses. Two rules, one budget, spent on
DIFFERENT trades -- never one ANDed onto the other, which would be a superset
whose closest match to the incumbent's own count is always "no second
condition at all". D never comes from a P&L.

WHERE THE SOLVE GETS ITS POPULATION
-----------------------------------
From the pre-flight's own features CSV, which holds every baseline entry of
both books on this universe with all eleven features already computed -- 3,908
MCL and 6,462 MC5, the two published counts. Solving D there rather than from
a first engine pass saves a whole tape read.

That makes this a study reading another study's output, so it carries the
refusal that rule earned (§5): AFTER the run, the baseline entries this pass
produced are compared against the features file's population, and a mismatch
is reported as an input refusal rather than absorbed. A features file from a
different tape or universe cannot be used without saying so.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common import running_up as RU
from common.entry_shares import QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_chase_gate.md"
def _preflight_csv_default() -> str:
    """The pre-flight's OWN --csv default, read from its parser rather than
    restated here.

    It is `running_up_features.csv`, not `running_up_preflight.csv`, and this
    file had the wrong one until it was checked against the machine that holds
    the data. A restated path is a second source of truth that fails at the
    worst moment -- after a several-minute engine pass has already run.
    """
    from common.running_up_preflight import build_parser
    for a in build_parser()._actions:
        if a.dest == "csv":
            return a.default
    return "var/reports/running_up_features.csv"


FEATURES_CSV = _preflight_csv_default()

# Every one of these is a number the pre-flight PRINTED, on a pass that could
# not see a P&L. Registration §1.
CEILS = (0.033, 0.050, 0.083, 0.100, 0.150)
# PRE-RUN amendment A: the matched comparator and the reported floor need ONE
# ceiling to sit on, and the sweep scores five. 0.083 is the middle of the
# swept range and the one value appearing in BOTH of the pre-flight's printed
# tables. Chosen for that and fixed here, before any cell has a number.
ANCHOR = 0.083
# Reported and never scored (§5.1): the floor of MC5's U, the bottom of decile
# 2. "Don't buy while it is dropping" -- worth about four percentage points
# where the ceiling is worth thirty-three.
MC5_FLOOR = -0.018

TRAIL_PCT = 5.0        # for the §5.2 reported block only; never a parameter here


def _name(eng: str, ceil: float) -> str:
    return f"{eng.upper()}-c{int(round(ceil * 1000)):03d}"


BOOKS: list[tuple] = []
for _eng in ("mcl", "mc5"):
    BOOKS.append((_eng.upper(), _eng, None))
    for _c in CEILS:
        BOOKS.append((_name(_eng, _c), _eng, ("ceil", _c)))
    BOOKS.append((f"{_eng.upper()}-dist", _eng, ("dist", ANCHOR)))
BOOKS.append(("MC5-floor", "mc5", ("band", ANCHOR, MC5_FLOOR)))
BOOKS = tuple(BOOKS)

PAIRED = tuple((eng.upper(), _name(eng, c)) for eng in ("mcl", "mc5") for c in CEILS)
REPORTED = (("MCL", "MCL-dist"), ("MC5", "MC5-dist"), ("MC5", "MC5-floor"))


# --- the solve ----------------------------------------------------------------------

def read_features(path: str) -> dict[str, list[dict]]:
    """book -> rows of {symbol, date, entry_et, ret_5m, dist_from_high, bars_held}."""
    out: dict[str, list[dict]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["book"], []).append(r)
    return out


def _f(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x


def solve_distance(rows: list[dict], ceil: float) -> tuple[float, int, int]:
    """D such that `dist_from_high >= D` ALONE refuses as close as possible to
    the number of entries `ret_5m <= ceil` refuses.

    Returns (D, refused_by_ceiling, refused_by_distance).

    IT IS DISTANCE **INSTEAD OF** EXTENSION, NOT ON TOP OF IT -- and the first
    version of this function got that wrong in a way worth recording. It solved
    D for `ret_5m <= ceil AND dist_from_high >= D`, which is a SUPERSET of the
    ceiling: the pair can only ever refuse MORE, so the closest match to the
    ceiling's own count is always D = -inf, i.e. no distance condition at all.
    The solve returned a perfect match and the comparison was vacuous -- a
    control whose output is indistinguishable from the failure it detects, §4's
    recurring shape, caught by a test that asserted D landed among the data.

    Two rules spending the same abstention budget on DIFFERENT trades is the
    H-S6 arrangement and the only one that can answer the question: at the same
    budget, does `dist_from_high` pick better trades to refuse than `ret_5m`?

    SOLVED AGAINST A CONSTRAINT, NEVER CHOSEN. The count comes from the
    incumbent rule's behaviour; no P&L is read here and none is available --
    the features file has no money in it, by the pre-flight's own design.

    Ties go to the LOOSER D -- the one refusing fewer -- so a tie can never be
    broken in the comparator's favour by abstaining more.
    """
    r5 = np.array([_f(r["ret_5m"]) for r in rows])
    dfh = np.array([_f(r["dist_from_high"]) for r in rows])
    n = len(rows)
    # A NaN feature cannot satisfy `<=` or `>=`, so it is ADMITTED by both
    # rules -- the gate refuses on evidence, never on its absence.
    target = n - int((~(r5 > ceil)).sum())
    if target <= 0:
        return float("-inf"), target, 0

    cands = np.unique(dfh[~np.isnan(dfh)])
    best, best_n, best_gap = float("-inf"), 0, target
    for d in np.concatenate([[float("-inf")], cands]):
        refused = n - int((~(dfh < d)).sum())
        gap = abs(refused - target)
        if gap < best_gap or (gap == best_gap and d < best):
            best, best_n, best_gap = float(d), refused, gap
    return best, target, best_n


# --- the gate -----------------------------------------------------------------------

def gate_for(df: pd.DataFrame, spec, dist: float | None) -> pd.Series:
    """A boolean Series on `df`'s 1-minute index: True where an entry is allowed.

    NaN is ALLOWED, by the same rule as the solve: too little history to know
    whether the name has run is not evidence that it has.
    """
    kind = spec[0]
    if kind == "dist":
        # The comparator: distance INSTEAD of extension, at a matched budget.
        # ret_5m is not read here at all -- that is what makes the two books
        # different allocations of one budget rather than nested rules.
        return (~(RU.dist_series(df) < dist)).astype(bool)
    r5 = RU.ret_series(df, back=5)
    ok = ~(r5 > spec[1])
    if kind == "band":
        ok &= ~(r5 < spec[2])
    return ok.astype(bool)


def stamp_on(gate: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """The 1-minute gate carried onto whatever index the engine trades.

    For MC5 that is the 5-minute label, which takes the value at the label's own
    minute -- i.e. from bars before the 5-minute bar STARTED. Up to five minutes
    more conservative than necessary and in the safe direction, the same
    convention H-B3 used and MC5's own point-in-time floor uses.
    """
    return gate.reindex(index, method="ffill").fillna(False).astype(bool)


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
           "refused": {g: [] for _, g in PAIRED + REPORTED},
           "binding": {g: [0, 0, Counter()] for _, g in PAIRED + REPORTED},
           "onebar": {name: [0, 0] for name, _, _ in BOOKS},
           "trail": {"MCL": [], "MC5": []}}

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
            for name, eng, spec in BOOKS:
                mod, extra = engines[eng]
                gate = None
                if spec is not None:
                    g = gate_for(df, spec, dists.get(name))
                    gate = stamp_on(g, idx5 if eng == "mc5" else df.index)
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
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
            ob = res["onebar"][name]
            ob[0] += sum(1 for t in trades if getattr(t, "bars_held", 0) <= 1)
            ob[1] += len(trades)

        # §5.2, the reported trail block -- read off the BASELINE books only,
        # so it does not depend on any gate being right.
        for base in ("MCL", "MC5"):
            for t in got[base]:
                # `entry_price` / `exit_price` -- the Trade OBJECT's attributes.
                # `entry_px` / `exit_px` are the keys `gate_study.trade_row`
                # puts in its dict, and reaching for those here is what broke
                # the first smoke run. The two vocabularies sit one line apart
                # in this loop, so a test pins the object's names.
                if getattr(t, "bars_held", 0) <= 1 and t.entry_price:
                    res["trail"][base].append(
                        (float(t.exit_price) / float(t.entry_price) - 1.0) * 100.0)

        # Binding and refusal, counted against each baseline's own entries.
        for name, eng, spec in BOOKS:
            if spec is None:
                continue
            base = "MCL" if eng == "mcl" else "MC5"
            if name not in res["binding"]:
                continue
            g = gate_for(df, spec, dists.get(name))
            b = res["binding"][name]
            for t in got[base]:
                ts = pd.Timestamp(f"{day} {t.entry_time}", tz=ET) \
                    if isinstance(t.entry_time, str) else t.entry_time
                allowed = bool(g.reindex([ts], method="ffill").fillna(True).iloc[0])
                b[1] += 1
                b[0] += 1                      # the gate can bind on every entry
                b[2][int(allowed)] += 1
                if not allowed:
                    res["refused"][name].append(G.trade_row(t, s, day, 0))
    return day, res, ""


# --- the blocks this study adds -----------------------------------------------------

def mechanism_block(onebar: dict) -> list[str]:
    """§7: the gate's whole claim is that it removes trades that die on the next
    bar. A cell whose one-bar share does not FALL did not operate as claimed,
    whatever its P&L says."""
    L = ["THE MECHANISM, READ BACK AS A MEASUREMENT (§7)", "",
         "  The claim is that refusing the chase removes trades that die on the",
         "  next bar. That is observable: the one-bar SHARE should fall. A cell",
         "  that does not lower it did not operate as claimed and may not be",
         "  described as removing chases.", ""]
    for base in ("MCL", "MC5"):
        b = onebar.get(base, [0, 0])
        base_share = 100.0 * b[0] / b[1] if b[1] else float("nan")
        L.append(f"  {base}")
        L.append(f"    {base:<14} {base_share:5.1f}%   ({b[0]:,} of {b[1]:,})")
        for name, eng, spec in BOOKS:
            if spec is None or eng.upper() != base:
                continue
            o = onebar.get(name, [0, 0])
            if not o[1]:
                L.append(f"    {name:<14}    n/a   (no trades)")
                continue
            share = 100.0 * o[0] / o[1]
            tag = "<- fewer" if share < base_share - 0.05 else (
                "<- no change" if share <= base_share + 0.05 else "<- MORE")
            L.append(f"    {name:<14} {share:5.1f}%   ({o[0]:,} of {o[1]:,})  "
                     f"{share - base_share:+5.1f}pp  {tag}")
        L.append("")
    return L


def marginal_block(books: dict) -> list[str]:
    """What each REFUSED trade was worth. §4 of the index, added 2026-09-18 from
    H-E2: when a rule moves the denominator, the average moves for two reasons
    and only one of them is selection."""
    L = ["WHAT EACH REFUSED TRADE WAS WORTH (the marginal trade)", "",
         "  (tot(cell) - tot(base)) / (n(cell) - n(base)). A gate refusing",
         "  trades WORSE than the book's average is selecting; one refusing",
         "  trades better than it is abstaining into its own average.", ""]
    for base in ("MCL", "MC5"):
        rows = books.get(base, [])
        n0, t0 = len(rows), sum(float(r["net"]) - G.MEASURED_FRICTION for r in rows)
        L.append(f"  {base}  base {n0:,} trades, {t0 / n0:+.2f}/trade"
                 if n0 else f"  {base}  base empty")
        for name, eng, spec in BOOKS:
            if spec is None or eng.upper() != base:
                continue
            rs = books.get(name, [])
            n1 = len(rs)
            t1 = sum(float(r["net"]) - G.MEASURED_FRICTION for r in rs)
            if n1 == n0:
                L.append(f"    {name:<14} removed 0 -- the gate never bound")
                continue
            L.append(f"    {name:<14} {n1:>6,} trades  {n1 - n0:+6,}  "
                     f"per trade {t1 / n1 if n1 else float('nan'):+7.2f}   "
                     f"MARGINAL {(t1 - t0) / (n1 - n0):+7.2f}")
        L.append("")
    return L


def trail_block(trail: dict) -> list[str]:
    """§5.2, REPORTED AND NEVER SCORED. The leading alternative explanation is
    not an entry story: a name that just ran 11% in five minutes is more
    volatile, and a FIXED 5% trail is then more likely to be hit by noise. If
    the one-bar exits cluster AT the trail, these are not bad entries -- they
    are a stop too tight for the volatility at entry, and the next registration
    is a volatility-scaled trail rather than a gate that throws trades away."""
    L = ["REPORTED, NEVER SCORED (§5.2): WHERE THE ONE-BAR EXITS LANDED", "",
         f"  exit / entry - 1, for baseline trades held one bar. The trail sits",
         f"  at -{TRAIL_PCT:.0f}%. Clustered AT it = a stop too tight for the",
         "  volatility. Well BELOW it = a real reversal the gate might avoid.", ""]
    for base in ("MCL", "MC5"):
        v = np.array([x for x in trail.get(base, []) if not math.isnan(x)])
        if not len(v):
            L += [f"  {base:<5} no one-bar trades", ""]
            continue
        at = 100.0 * float(np.mean(np.abs(v + TRAIL_PCT) <= 0.5))
        below = 100.0 * float(np.mean(v < -TRAIL_PCT - 0.5))
        L += [f"  {base:<5} n {len(v):,}   median {np.median(v):+.2f}%   "
              f"p10 {np.percentile(v, 10):+.2f}%   p90 {np.percentile(v, 90):+.2f}%",
              f"        within 0.5pp of the trail  {at:5.1f}%      "
              f"more than 0.5pp below it  {below:5.1f}%", ""]
    L += ["  This decides which registration comes next. It does not decide",
          "  this one.", ""]
    return L


def solve_block(dists: dict, solved: dict) -> list[str]:
    L = ["THE SECOND CONDITION, AT A MATCHED ABSTENTION BUDGET (§4)", "",
         "  `dist_from_high` separates almost nothing alone -- AUC 0.494 (MCL)",
         "  and 0.443 (MC5) against a rand control at 0.526 / 0.505, where",
         "  ret_5m reads 0.751 / 0.636. So it is tested at the SAME BUDGET and",
         "  INSTEAD of the ceiling, never on top of it: D solved so that",
         f"  dist_from_high >= D alone refuses the COUNT ret_5m <= {ANCHOR} refuses.",
         "  A pair ANDed onto the ceiling would be a superset of it, its closest",
         "  match would always be 'no distance condition', and the comparison",
         "  would be vacuous. D never comes from a P&L.", ""]
    for name, info in solved.items():
        d = dists.get(name)
        L.append(f"  {name:<10} D {d:+.4f}   ceiling refuses {info[0]:,}   "
                 f"pair refuses {info[1]:,}   gap {abs(info[1] - info[0]):,}")
    L += ["", "  If the distance book does not beat the ceiling book per trade at",
          "  this budget, `near the session high` adds nothing that `not",
          "  extended` does not already carry, and the 3.3% two-condition cell",
          "  is ret_5m wearing a second knob.", ""]
    return L


def population_refusal(books: dict, feats: dict) -> list[str]:
    """§5's rule: a study reading another study's output must refuse a mismatch
    rather than absorb it. The solve took its population from the features
    file; if this run's baselines are not that population, D was solved on a
    different book and the comparison is void."""
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
                     f"{len(there - here):,} only there -- D was solved on a "
                     f"different population and the §4 comparison is VOID")
    return ["THE SOLVE'S POPULATION, CHECKED AFTER THE RUN", ""] + L + [""]


# --- cli ----------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--features", default=FEATURES_CSV,
                   help="the pre-flight's features CSV; the solve's population")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/chase_gate.txt")
    p.add_argument("--csv", default="var/reports/chase_gate_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()

    if not Path(a.features).exists():
        sys.exit(f"the features file {a.features} does not exist. It is written "
                 f"by:\n    python -m common.running_up_preflight --jobs 8\n"
                 "and this study solves its matched comparator's threshold on "
                 "that population, so it is refused rather than run without it.")
    feats = read_features(a.features)
    dists, solved = {}, {}
    for eng in ("mcl", "mc5"):
        base = eng.upper()
        d, target, got_n = solve_distance(feats.get(base, []), ANCHOR)
        dists[f"{base}-dist"] = d
        solved[f"{base}-dist"] = (target, got_n)

    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    tasks = [(p, d, u, dists) for p, d, u in tasks]
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "chase_gate")

    books = {name: [] for name, _, _ in BOOKS}
    refused = {g: [] for _, g in PAIRED + REPORTED}
    binding = {g: [0, 0, Counter()] for _, g in PAIRED + REPORTED}
    onebar = {name: [0, 0] for name, _, _ in BOOKS}
    trail = {"MCL": [], "MC5": []}
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
            onebar[name][0] += r["onebar"][name][0]
            onebar[name][1] += r["onebar"][name][1]
        for name in refused:
            refused[name] += r["refused"][name]
            b, rb = binding[name], r["binding"][name]
            b[0] += rb[0]
            b[1] += rb[1]
            b[2].update(rb[2])
        for base in trail:
            trail[base] += r["trail"][base]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    binding_t = {k: (v[0], v[1], dict(v[2])) for k, v in binding.items()}
    preamble = (population_refusal(books, feats) + solve_block(dists, solved))
    body = G.render(
        "H-P1: REFUSE THE ENTRY WHEN THE NAME HAS ALREADY RUN",
        REGISTERED, books, PAIRED, REPORTED, symdays, errors, run_days,
        elapsed, jobs, refused, binding_t, error_days, preamble=preamble,
        universe=a.pairs, dataset=a.dataset)
    body += mechanism_block(onebar) + marginal_block(books) + trail_block(trail)
    emit("\n".join(body), a.out,
         header=f"common.chase_gate pairs={a.pairs} dataset={a.dataset} "
                f"sessions={len(run_days)} symbol_days={symdays} cut={cut} "
                f"qty={QTY} anchor={ANCHOR} registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "ceils": list(CEILS), "anchor": ANCHOR,
                  "dist_solved": {k: (None if v == float("-inf") else v)
                                  for k, v in dists.items()}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
