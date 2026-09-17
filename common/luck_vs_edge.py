#!/usr/bin/env python3
r"""Part A -- luck or edge? MCL and MC5 by session regime on the point-in-time books.

    python -m common.luck_vs_edge --jobs 8

Registered in docs/research/REGISTERED_luck_vs_edge.md before this file
existed. No engine runs: the books are the baselines `first_entry_skip`
wrote; the labels are the daily archive's regime (same-day and lagged), the
07:00 reading `cold_veto` wrote, and a trend-day flag computed here from the
archive slices -- the leader's pre-market move among the point-in-time names,
first printed open to last close before 09:30, >= TREND_X.

PER SESSION MEANS OVER ALL SESSIONS IN THE BUCKET, traded or not. A regime
question is about the opportunity set, and a session the strategy sat out
is part of the answer: a bucket where the strategy never trades and never
loses is worth exactly zero, and dividing by traded sessions only would hide
that. Per traded session is printed beside it, labelled.

THE READING (registration §3): does the strategy make money on the sessions
that pay -- same-day hot, and trend days -- in both halves and after dropping
the bucket's best three sessions? If not, no regime gate rescues it. If so,
what share of sessions would have to be hot to break even, against the share
that were?
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from datetime import date as _date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.entry_shares import MEASURED_FRICTION, QTY
from common.first_entry_skip import FRICTIONS, money
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_luck_vs_edge.md"
PAIRS = "var/state/screen_pairs_pit.json"
TRADES = "var/reports/first_entry_skip_trades.csv"
READINGS = "var/reports/cold_veto_readings.csv"
TREND_X = 0.50                        # §1: the leader held +50% into the open
SESSION_END = dtime(9, 30)
DROP = 3
MIN_SESSIONS_PER_BUCKET = DROP + 2    # as regime_study
BOOKS = ("MCL", "MC5")
SAME_ORDER = ("hot", "mixed", "cold")
LAG_ORDER = ("hot", "mixed", "cold")
TREND_ORDER = ("trend", "not")
READ_ORDER = ("warm", "cold", "count", "inert")


# --- inputs ----------------------------------------------------------------------

def load_books(path: Path) -> dict[str, list[dict]]:
    books: dict[str, list[dict]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["net"] = float(r["net"])
            books[r["book"]].append(r)
    return dict(books)


def load_meta(csv_path: Path) -> dict:
    p = csv_path.with_name(csv_path.stem + "_meta.json")
    return json.loads(p.read_text(encoding="utf-8"))


def load_readings(path: Path) -> dict[str, str]:
    """date -> kind from cold_veto's readings file; {} when absent."""
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["date"]: r["kind"] for r in csv.DictReader(fh)}


# --- the trend-day flag -------------------------------------------------------------

def leader_move(frame: pd.DataFrame, universe: list[dict], day: _date) -> float | None:
    """Max over the point-in-time names of (last close before 09:30 / first
    printed open of the session - 1). None when no name printed."""
    local = frame.index.tz_convert(ET)
    pre = frame[(local.date == day) & (local.time < SESSION_END)]
    best = None
    for rec in universe:
        df = pre[pre["symbol"] == rec["symbol"]]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        o = float(df["open"].iloc[0])
        if o <= 0:
            continue
        mv = float(df["close"].iloc[-1]) / o - 1.0
        best = mv if best is None else max(best, mv)
    return best


def read_leader(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    paths, day, universe = args
    try:
        f = read_dbn(Path(paths[-1]))
    except Exception as e:                              # noqa: BLE001
        return day, None, f"unreadable ({type(e).__name__}: {e})"
    if f.empty or Path(paths[-1]).name[:10] != day:
        return day, None, ""
    return day, {"leader": leader_move(f, universe, _date.fromisoformat(day))}, ""


def trend_labels(moves: dict[str, float | None], x: float = TREND_X) -> dict[str, str]:
    return {d: ("trend" if m is not None and m >= x else "not") for d, m in moves.items()}


# --- the regime labels ----------------------------------------------------------------

def regime_labels(archive: Path, dataset: str) -> tuple[dict[str, str], dict[str, str], int]:
    """(same-day, lagged, median symbols per session). Refuses a thin archive."""
    import sys
    from common import regime as RG
    from common.dbn_io import daily_frame
    from common.regime_study import check_universe
    daily = daily_frame(archive, dataset)
    med, refusal = check_universe(daily)
    if refusal:
        sys.exit(f"REFUSING TO RUN: {refusal}. A regime is a property of the market.")
    feats = RG.series(daily)
    same = RG.classify(feats)
    return same, RG.lagged(same), med


# --- arithmetic ---------------------------------------------------------------------------

def session_nets(rows: list[dict], f: float) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        out[r["date"]] += r["net"] - f
    return dict(out)


def bucket(rows: list[dict], sessions: list[str], cut: str, f: float = MEASURED_FRICTION) -> dict:
    """Every number §2 asks for, for the trades in `rows` over the sessions
    in `sessions` (ALL sessions of the bucket, traded or not)."""
    sset = set(sessions)
    sel = [r for r in rows if r["date"] in sset]
    nets = session_nets(sel, f)
    per_session_all = (sum(nets.values()) / len(sessions)) if sessions else 0.0
    traded = sorted(nets)
    vals = [nets[d] for d in traded]
    early = [nets[d] for d in traded if d < cut]
    late = [nets[d] for d in traded if d >= cut]
    n_early = sum(1 for d in sessions if d < cut)
    n_late = sum(1 for d in sessions if d >= cut)
    return {
        "sessions": len(sessions), "traded": len(traded), "trades": len(sel),
        "net": {lab: sum(r["net"] - fr for r in sel) for lab, fr in FRICTIONS},
        "per_trade": (sum(r["net"] - f for r in sel) / len(sel)) if sel else 0.0,
        "per_session": per_session_all,
        "per_traded": (sum(vals) / len(vals)) if vals else 0.0,
        "positive": (sum(1 for v in vals if v > 0) / len(vals)) if vals else 0.0,
        "median": statistics.median(vals) if vals else 0.0,
        "drop3": sum(sorted(vals, reverse=True)[DROP:]) / len(sessions) if sessions else 0.0,
        "early": (sum(early) / n_early) if n_early else 0.0,
        "late": (sum(late) / n_late) if n_late else 0.0,
        "n_early": n_early, "n_late": n_late,
        "thin": len(sessions) < MIN_SESSIONS_PER_BUCKET,
    }


def breakeven(h: float, lo: float) -> float | None:
    """The hot-day share at which f*h + (1-f)*lo = 0; None unless h > 0 > lo."""
    if h > 0 > lo:
        return -lo / (h - lo)
    return None


def reading(rows: list[dict], labels: dict[str, str], pay: str, sessions: list[str],
            cut: str) -> dict:
    """§3 on one strategy and one labelling: `pay` is the paying bucket."""
    covered = [d for d in sessions if d in labels]
    hot = [d for d in covered if labels[d] == pay]
    rest = [d for d in covered if labels[d] != pay]
    b_hot = bucket(rows, hot, cut)
    b_rest = bucket(rows, rest, cut)
    h, lo = b_hot["per_session"], b_rest["per_session"]
    edge = (not b_hot["thin"]) and h > 0 and b_hot["early"] > 0 and b_hot["late"] > 0 and b_hot["drop3"] > 0
    fstar = breakeven(h, lo)
    f = len(hot) / len(covered) if covered else 0.0
    return {"pay": pay, "hot": b_hot, "rest": b_rest, "h": h, "l": lo, "edge": edge,
            "fstar": fstar, "f": f, "n_covered": len(covered),
            "dropped_trades": sum(1 for r in rows if r["date"] not in labels)}


# --- report -----------------------------------------------------------------------------

def table(name: str, rows: list[dict], labels: dict[str, str], order, sessions: list[str],
          cut: str) -> list[str]:
    by = defaultdict(list)
    for d in sessions:
        if d in labels:
            by[labels[d]].append(d)
    dropped = sum(1 for r in rows if r["date"] not in labels)
    L = [f"  {name}" + (f"   ({dropped:,} trade(s) on unlabelled dates dropped, not bucketed)" if dropped else ""),
         f"  {'bucket':<8}{'sessions':>9}{'traded':>7}{'trades':>7}{'net $1.00':>12}{'net $4.26':>12}{'net $8.92':>12}"
         f"{'per/t':>8}{'per/sess':>10}{'per/trd':>9}{'pos%':>6}{'med':>9}{'drop3/s':>9}{'early/s':>9}{'late/s':>9}"]
    for k in order:
        s = by.get(k, [])
        b = bucket(rows, s, cut)
        if b["thin"]:
            L.append(f"  {k:<8}{b['sessions']:>9,}   n/a (fewer than {MIN_SESSIONS_PER_BUCKET} sessions)")
            continue
        L.append(f"  {k:<8}{b['sessions']:>9,}{b['traded']:>7,}{b['trades']:>7,}"
                 f"{money(b['net']['$1.00']):>12}{money(b['net']['$4.26']):>12}{money(b['net']['$8.92']):>12}"
                 f"{money(b['per_trade']):>8}{money(b['per_session']):>10}{money(b['per_traded']):>9}"
                 f"{100 * b['positive']:>6.1f}{money(b['median']):>9}{money(b['drop3']):>9}"
                 f"{money(b['early']):>9}{money(b['late']):>9}")
    L.append("")
    return L


def reading_block(name: str, lab_name: str, r: dict) -> list[str]:
    b = r["hot"]
    L = [f"THE READING: {name} on {lab_name}'s '{r['pay']}' bucket ($4.26, per session over ALL sessions in the bucket)", ""]
    if b["thin"]:
        return L + [f"  n/a -- {b['sessions']} session(s) in the bucket", ""]
    L += [f"  1. H = {money(r['h'])} per session over {b['sessions']:,} sessions   halves {money(b['early'])} / {money(b['late'])}"
          f"   drop-top-{DROP} sessions {money(b['drop3'])}",
          f"     -> {'EDGE ON THE PAYING SESSIONS' if r['edge'] else 'NO EDGE EVEN ON THE PAYING SESSIONS'}"
          + ("" if r["edge"] else " -- no regime gate, however good, rescues this book")]
    if r["edge"]:
        L.append(f"  2. L = {money(r['l'])} per session over the other {r['rest']['sessions']:,}   "
                 f"break-even hot share f* = {100 * r['fstar']:.1f}%   observed f = {100 * r['f']:.1f}%   "
                 + ("-> LUCK: paid on the hot days, not often enough" if r["fstar"] is not None and r["fstar"] > r["f"]
                    else "-> *** f* <= f while the book is negative: arithmetic defect, do not read ***"))
    else:
        L.append(f"  2. not read (reading 1 failed); for context L = {money(r['l'])} per session, observed hot share {100 * r['f']:.1f}%")
    L.append("")
    return L


def render(books: dict, meta: dict, same: dict, lag: dict, trend: dict, moves: dict,
           readings: dict, med_universe: int, elapsed: float, jobs: int) -> list[str]:
    sessions = list(meta["sessions"])
    cut = meta["cut"]
    L = ["PART A: LUCK OR EDGE? MCL AND MC5 BY SESSION REGIME ON THE POINT-IN-TIME BOOKS", "",
         f"  registered  {REGISTERED}",
         f"  {len(sessions):,} sessions   {meta['symbol_days']:,} symbol-days   halves cut at {cut}   "
         f"{QTY} shares   friction per round trip",
         f"  regime from the daily archive: median {med_universe:,} symbols per session",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s) (the trend flag; nothing else re-ran)", ""]
    mv = [m for m in moves.values() if m is not None]
    if mv:
        q = np.quantile(mv, [.1, .25, .5, .75, .9])
        L += ["THE TREND-DAY FLAG (registration §1: leader's move from first open to last close before 09:30)", "",
              f"  leader move: p10 {100 * q[0]:+.0f}%  p25 {100 * q[1]:+.0f}%  median {100 * q[2]:+.0f}%  "
              f"p75 {100 * q[3]:+.0f}%  p90 {100 * q[4]:+.0f}%   threshold {100 * TREND_X:.0f}%",
              f"  trend days {sum(1 for d in sessions if trend.get(d) == 'trend'):,} of {len(sessions):,}", ""]
    same_n = {k: sum(1 for d in sessions if same.get(d) == k) for k in SAME_ORDER}
    L += ["SESSIONS BY LABEL", "",
          "  same-day regime (the ceiling): " + "  ".join(f"{k} {v:,}" for k, v in same_n.items())
          + f"  unlabelled {sum(1 for d in sessions if d not in same):,}",
          "  lagged regime (actionable):    " + "  ".join(f"{k} {sum(1 for d in sessions if lag.get(d) == k):,}" for k in LAG_ORDER),
          "  07:00 reading (H-B4):          " + ("  ".join(f"{k} {sum(1 for d in sessions if readings.get(d) == k):,}" for k in READ_ORDER)
                                                  if readings else "not available (cold_veto_readings.csv absent)"), ""]
    for name in BOOKS:
        rows = books.get(name, [])
        L += [f"BY SAME-DAY REGIME -- THE CEILING, not knowable at 04:00", ""]
        L += table(name, rows, same, SAME_ORDER, sessions, cut)
        L += [f"BY LAGGED REGIME -- yesterday's reading, actionable", ""]
        L += table(name, rows, lag, LAG_ORDER, sessions, cut)
        L += [f"BY TREND DAY -- leader held >= {100 * TREND_X:.0f}% into the open (known at 09:30, not before)", ""]
        L += table(name, rows, trend, TREND_ORDER, sessions, cut)
        if readings:
            L += [f"BY THE 07:00 READING -- H-B4's proxy, actionable at 07:00", ""]
            L += table(name, rows, readings, READ_ORDER, sessions, cut)
        L += reading_block(name, "same-day regime", reading(rows, same, "hot", sessions, cut))
        L += reading_block(name, "trend day", reading(rows, trend, "trend", sessions, cut))
    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. MCL was fitted on this calendar.",
          "  NOT A GATE. The same-day and trend labels are known after the fact; the lagged",
          "  and 07:00 tables are what a gate would have seen and are read elsewhere.",
          "  NOT A3. The live 09-09..09-16 sessions are not in the archive (registration §4).", ""]
    return L


# --- cli ----------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=TRADES)
    p.add_argument("--readings", default=READINGS)
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/luck_vs_edge.txt")
    p.add_argument("--labels-csv", default="var/reports/luck_vs_edge_labels.csv")
    return p


def write_labels(path: Path, sessions, same, lag, trend, moves, readings) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "same_day", "lagged", "trend", "leader_move", "reading_0700"])
        for d in sessions:
            m = moves.get(d)
            w.writerow([d, same.get(d, ""), lag.get(d, ""), trend.get(d, ""),
                        "" if m is None else f"{m:.4f}", readings.get(d, "")])


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    trades_path = Path(a.trades)
    books = load_books(trades_path)
    meta = load_meta(trades_path)
    readings = load_readings(Path(a.readings))
    same, lag, med = regime_labels(archive, a.dataset)

    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, None)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(read_leader, [(p[-1:], d, u) for p, d, u in tasks], jobs, "luck_vs_edge trend flag")
    moves = {d: (r["leader"] if r else None) for d, r in got.items()}
    trend = trend_labels(moves)

    Path(a.labels_csv).parent.mkdir(parents=True, exist_ok=True)
    write_labels(Path(a.labels_csv), meta["sessions"], same, lag, trend, moves, readings)
    emit("\n".join(render(books, meta, same, lag, trend, moves, readings, med, elapsed, jobs)),
         a.out, header=f"common.luck_vs_edge trades={a.trades} readings={a.readings} dataset={a.dataset} "
                       f"sessions={len(meta['sessions'])} cut={meta['cut']} trend_x={TREND_X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
