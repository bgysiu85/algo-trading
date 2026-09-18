#!/usr/bin/env python3
r"""Do any "running up" features separate the one-bar trades from the rest?

    python -m common.running_up_preflight --jobs 8

A PRE-FLIGHT, NOT A STUDY. There is no registration behind this file because
there is no rule in it: no threshold, no gate, no verdict, and NO P&L
ANYWHERE. It answers one descriptive question and then stops.

WHY IT EXISTS
-------------
`one_bar_sizing_20260918.txt`: MC5's 2,412 one-bar trades lose (31.95) each
and are 139% of its net; the other 4,050 trades are +5.36 at $4.26 and +0.70
at $8.92. 2,283 of those 2,412 exits are `trailing_stop` -- entered, went
straight against the position, the 5% trail fired on the very next bar. That
is the failure Warrior's "Running Up" scanner is meant to prevent: do not buy
a name that is not actually moving.

But `bars_held` is an OUTCOME, not knowable at entry, and PROGRAM_INDEX §4 is
explicit that a comparison between two outcome-dependent quantities is
circular. So the question this pass asks is the only honest form of it:

    at the entry bar, using only closed bars, does any feature tell the
    trades that turn out to last one bar apart from the ones that do not?

If nothing separates, there is no scanner worth building and one cheap pass
said so. If something does, its DISTRIBUTION -- printed here -- is where the
threshold comes from in the registration that follows. §5: look at the
distribution of the thing a threshold will cut before registering the
threshold.

WHY THERE IS NO P&L IN THE OUTPUT
---------------------------------
A table of per-trade P&L by threshold would let a threshold be chosen for its
P&L, which is a search wearing a table's clothes -- the thing H-S6 §2 was
written to prevent one level up. Separation is measured against the outcome
label alone. The money comes later, once, in a registered gate study scored
against `gate_study.abstention` like every other gate here.

READS THE EXISTING TRADES CSV. The entries are exactly the ones already
measured, so no engine runs and the books cannot drift. One pass over the
target-day slices only -- no warm-up sessions are needed, because every
feature is restricted to its own session.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from common import gate_study as G
from common import running_up as RU
from common.report_io import emit

TRADES = "var/reports/session_scenarios_trades.csv"
BOOKS = ("MCL", "MC5")
ONE_BAR = 1                      # bars_held <= this is the group being predicted


# --- inputs -----------------------------------------------------------------

def load_entries(path: Path) -> dict[str, list[dict]]:
    """{date: [entry, ...]} for the two plain books, ignoring the floored ones."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] not in BOOKS:
                continue
            by_day[r["date"]].append({"book": r["book"], "symbol": r["symbol"],
                                      "date": r["date"], "entry_et": r["entry_et"],
                                      "bars_held": int(r["bars_held"])})
    return dict(by_day)


def load_meta(path: Path) -> dict:
    p = path.with_name(path.stem + "_meta.json")
    return json.loads(p.read_text(encoding="utf-8"))


def input_refusal(meta: dict, pairs: str, dataset: str) -> str | None:
    """The features must be computed on the tape the trades were taken on.

    A BASIC-tape CSV against ITCH slices would compute every burst from bars
    the entries never saw, and the report would still print an ordinary table.
    The same refusal `luck_vs_edge` applies to its own inputs.
    """
    def base(x): return str(x).replace("\\", "/").rsplit("/", 1)[-1]
    if meta.get("dataset") != dataset:
        return (f"the trades CSV was written on {meta.get('dataset')!r} and --dataset "
                f"is {dataset!r}; features must come from the tape the entries did")
    if base(meta.get("pairs", "")) != base(pairs):
        return (f"the trades CSV was written on universe {base(meta.get('pairs',''))!r} "
                f"and --pairs is {base(pairs)!r}; they must be the same file")
    return None


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session's entries, each with its features. Module-level, picklable."""
    import pandas as pd
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame

    paths, day, entries = args
    if not entries:
        return day, [], ""
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                                   # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, [], ""
    frame = build_frame(parts, day)

    out = []
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_symbol[e["symbol"]].append(e)
    for symbol, rows in by_symbol.items():
        df = frame[frame["symbol"] == symbol]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        for e in rows:
            ts = pd.Timestamp(f"{e['date']} {e['entry_et']}", tz=RU.ET)
            f = RU.features(df, ts, seed_key=f"{e['symbol']}{e['date']}{e['entry_et']}")
            out.append({**e, **f})
    return day, out, ""


# --- the reading ------------------------------------------------------------

def split(rows: list[dict], book: str) -> tuple[list[dict], list[dict]]:
    bk = [r for r in rows if r["book"] == book]
    one = [r for r in bk if r["bars_held"] <= ONE_BAR]
    rest = [r for r in bk if r["bars_held"] > ONE_BAR]
    return one, rest


def col(rows: list[dict], name: str) -> np.ndarray:
    return np.array([r.get(name, float("nan")) for r in rows], dtype=float)


def feature_block(one: list[dict], rest: list[dict]) -> tuple[list[str], list]:
    L = [f"  {'feature':<20}{'n':>8}{'median 1-bar':>15}{'median rest':>14}"
         f"{'AUC':>8}{'sep':>7}  direction",
         f"  {'-' * 78}"]
    scored = []
    for name in RU.FEATURES:
        a, b = col(one, name), col(rest, name)
        n = int((~np.isnan(a)).sum() + (~np.isnan(b)).sum())
        if n == 0:
            continue
        au = RU.auc(a, b)
        if au != au:
            continue
        med_a = float(np.nanmedian(a)) if (~np.isnan(a)).any() else float("nan")
        med_b = float(np.nanmedian(b)) if (~np.isnan(b)).any() else float("nan")
        sep = abs(au - 0.5)
        # AUC is P(a one-bar trade scores above a surviving one). Above 0.5
        # means a HIGH value marks the trade to avoid, which for a "running
        # up" feature would be the opposite of the hypothesis -- so the
        # direction is spelled out rather than left to the reader.
        d = ("higher -> MORE one-bar (against the hypothesis)" if au > 0.5
             else "higher -> FEWER one-bar (as hypothesised)")
        tag = "  <- control" if name in ("rand", "minutes_since_0400") else ""
        L.append(f"  {name:<20}{n:>8,}{med_a:>15.4f}{med_b:>14.4f}"
                 f"{au:>8.3f}{sep:>7.3f}  {d}{tag}")
        scored.append((sep, name, au))
    L += ["",
          "  AUC 0.500 is a feature that knows nothing. `rand` is the null and must",
          "  land there; `minutes_since_0400` is the time-of-day confound, which is a",
          "  CLOSED question here -- if it separates and the momentum features do not,",
          "  the momentum features are a clock in disguise."]
    return L, scored


def distribution_block(rows: list[dict], names) -> list[str]:
    """The deciles a later registration must pick its threshold from."""
    L = [f"  {'feature':<20}" + "".join(f"{f'p{q*10}':>10}" for q in range(1, 10))]
    for name in names:
        d = RU.deciles(col(rows, name))
        if not d:
            continue
        L.append(f"  {name:<20}" + "".join(f"{v:>10.3f}" for v in d))
    return L


def bind_block(one: list[dict], rest: list[dict], name: str) -> list[str]:
    allv = col(one + rest, name)
    cuts = RU.deciles(allv)
    if not cuts:
        return []
    L = [f"  {name}: a `{name} >= cut` gate would KEEP",
         f"    {'cut':>10}{'of 1-bar':>12}{'of the rest':>14}{'difference':>13}"]
    for cut, kh, kc in RU.bind_table(col(one, name), col(rest, name), cuts):
        L.append(f"    {cut:>10.3f}{kh:>11.1%}{kc:>13.1%}{kc - kh:>12.1%}")
    L.append("    (a useless feature keeps the same share of both, and the last")
    L.append("     column is zero all the way down)")
    return L + [""]


def render(rows: list[dict], days: list[str], elapsed: float, jobs: int,
           universe: str, dataset: str, trades: str, missing: int) -> list[str]:
    L = ["RUNNING UP -- A SEPARATION PRE-FLIGHT, NOT A STUDY", "",
         "  NO REGISTRATION, because there is no rule here: no threshold, no gate,",
         "  no verdict, and no P&L anywhere in this report. One descriptive",
         "  question, asked before any threshold is registered.", "",
         f"  trades      {trades}  -- the entries already measured, no engine run",
         f"  universe    {universe}   bars {dataset}",
         f"  {len(days):,} sessions   {len(rows):,} entries with features   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if missing:
        L += [f"  {missing:,} session(s) produced no rows (unreadable slice, or no",
              "  entry in this book that day)", ""]

    L += ["THE QUESTION", "",
          "  At the entry bar, using only bars that had CLOSED, does any feature",
          "  tell the trades that turn out to last one bar apart from the rest?",
          "  `bars_held` is an outcome; the features are not. That asymmetry is the",
          "  whole point -- a gate can only ever read the features.", ""]

    for book in BOOKS:
        one, rest = split(rows, book)
        if not one or not rest:
            L += [f"{'=' * 78}", f"{book}: not enough of one group to read", ""]
            continue
        L += [f"{'=' * 78}",
              f"{book}   {len(one) + len(rest):,} entries   "
              f"{len(one):,} one-bar ({len(one) / (len(one) + len(rest)):.1%})   "
              f"{len(rest):,} lasted longer", ""]
        block, scored = feature_block(one, rest)
        L += block + [""]
        L += ["  THE DISTRIBUTIONS -- where a registered threshold would have to come", "",
              *distribution_block(one + rest, RU.FEATURES), ""]
        top = [n for _, n, _ in sorted(scored, reverse=True)
               if n not in ("rand", "minutes_since_0400")][:3]
        if top:
            L += ["  WHAT A GATE ON THE THREE BEST-SEPARATING FEATURES WOULD BIND ON", ""]
            for name in top:
                L += bind_block(one, rest, name)

    L += ["", "HOW TO READ THIS", "",
          "  A feature is worth registering a gate on only if its AUC is meaningfully",
          "  off 0.500 AND `rand` sat on it. Separation alone is not an edge: it says",
          "  the feature knows something about which trades die immediately, not that",
          "  a gate on it survives the abstention control, the project's friction",
          "  margin, or the cluster bootstrap. Three entry gates have already read as random removal",
          "  on these books (H-B1, H-B3, H-B4); this pass is how the fourth avoids",
          "  being registered on a hunch.", "",
          "WHAT THIS IS NOT", "",
          "  NOT A RESULT. No rule, no threshold, no P&L, no verdict.",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT WARRIOR'S SCANNER. Their baseline is prior sessions at the same time",
          "  of day; this one is the session's own median, because the archive cannot",
          "  supply the former. No threshold from their screen transfers to these",
          "  numbers, and none has been copied.",
          "  NOT MINUTE-FAITHFUL TO THE ALERTS. Day Trade Dash fires several times",
          "  within seconds on one symbol, so its scanner reads ticks; this reads",
          "  1-minute bars and is an approximation of a sub-second signal."]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default="var/state/screen_pairs_pit_itch_v2.json")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--trades", default=TRADES)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/running_up_preflight.txt")
    p.add_argument("--csv", default="var/reports/running_up_features.csv")
    return p


def main(argv=None) -> int:
    import sys
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    tpath = Path(a.trades)
    meta = load_meta(tpath)
    refusal = input_refusal(meta, a.pairs, a.dataset)
    if refusal:
        sys.exit(f"REFUSING TO RUN: {refusal}")
    by_day = load_entries(tpath)

    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    # ONLY the target day's slice: every feature is restricted to its own
    # session, so the warm-up slices build_tasks supplies would be read and
    # discarded. This is what makes the pass minutes rather than an hour.
    tasks = [(p[-1:], d, by_day.get(d, [])) for p, d, _ in tasks]
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "running_up_preflight")

    # run_sessions drops a session whose run_day returned None, so `got` never
    # holds one -- a `is None` branch here could not fire. The sessions that
    # produced nothing are counted instead, which is the fact worth printing.
    days = sorted(got)
    rows = [x for d in days for x in got[d]]
    missing = len(tasks) - len(days)

    emit("\n".join(render(rows, days, elapsed, jobs, a.pairs, a.dataset, a.trades, missing)),
         a.out, header=f"common.running_up_preflight trades={a.trades} pairs={a.pairs} "
                       f"dataset={a.dataset} sessions={len(days)} entries={len(rows)} "
                       f"DESCRIPTIVE-NO-RULE-NO-PNL")
    if rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        cols = ["book", "symbol", "date", "entry_et", "bars_held", *RU.FEATURES]
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
