#!/usr/bin/env python3
r"""H-B4 -- no new entries after 07:00 on a session that reads cold at 07:00.

    python -m common.cold_veto --jobs 8

Registered in docs/research/REGISTERED_cold_veto.md before this file existed.
Four books from one pass per session -- MCL, MCL-veto, MC5, MC5-veto -- with
the veto as `entry_gate`: True on every session bar before 07:00 ET, False
from 07:00 on a cold session. The five readings are `gate_study`'s.

THE 07:00 READING (registration §1). Over the point-in-time names surfaced
by 07:00 that printed a bar before it: how many (`n_visible`), the leader's
pre-market move from the session's first open to its high before 07:00
(`lead`), and the share of those names whose last price before 07:00 holds
less than RETAIN_MIN of their own move (`round_trip`). Percentile-ranked
against PRIOR sessions only, averaged, and cut at the prior sessions' lower
tercile -- computed once per session in pass 1, then handed to pass 2 as a
flag. Fewer than MIN_NAMES visible reads cold without rating.

TWO PASSES, because a session's cut depends on the sessions before it and
the books run in parallel. Pass 1 reads each session's own slice (no warm-up)
and returns three numbers; the labels are then derived in date order and
written beside the report; pass 2 runs the engines with the flag.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date as _date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.entry_shares import QTY
from common.range_rank import SESSION_MINUTES, first_seen_minute, minute_of
from common.regime import MIN_NAMES, RETAIN_MIN
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
REGISTERED = "docs/research/REGISTERED_cold_veto.md"
VETO_FROM = dtime(7, 0)
VETO_MINUTE = (VETO_FROM.hour - 4) * 60 + VETO_FROM.minute     # 180
MIN_HISTORY = 60                       # rated prior sessions before a composite cut exists
BOOKS = (("MCL", "mcl", False), ("MCL-veto", "mcl", True),
         ("MC5", "mc5", False), ("MC5-veto", "mc5", True))
PAIRED = (("MCL", "MCL-veto"), ("MC5", "MC5-veto"))
REPORTED = ()


# --- pass 1: the reading ------------------------------------------------------------

def reading(frame: pd.DataFrame, universe: list[dict], day: _date) -> dict:
    """The three components for one session, from bars strictly before 07:00
    of the visible names. `frame` is the session's own slice."""
    local = frame.index.tz_convert(ET)
    pre = frame[(local.date == day) & (local.time < VETO_FROM)]
    gains, retained = [], []
    for rec in universe:
        if not rec.get("first_seen") or first_seen_minute(rec) > VETO_MINUTE:
            continue
        df = pre[pre["symbol"] == rec["symbol"]]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        o = float(df["open"].iloc[0])
        h = float(df["high"].max())
        last = float(df["close"].iloc[-1])
        if o <= 0:
            continue
        gains.append(h / o - 1.0)
        if h > o:
            retained.append(min(max((last - o) / (h - o), 0.0), 1.0))
    n = len(gains)
    return {"n_visible": n,
            "lead": max(gains) if gains else 0.0,
            "round_trip": float(np.mean([r < RETAIN_MIN for r in retained])) if retained else 0.0}


def read_session(args: tuple) -> tuple:
    """Picklable pass-1 worker: (day, reading, err)."""
    from common.dbn_io import read_dbn
    paths, day, universe = args
    try:
        f = read_dbn(Path(paths[-1]))
    except Exception as e:                              # noqa: BLE001
        return day, None, f"unreadable ({type(e).__name__}: {e})"
    if f.empty or Path(paths[-1]).name[:10] != day:
        return day, None, ""
    return day, reading(f, universe, _date.fromisoformat(day)), ""


def pct_rank(value: float, prior: list[float]) -> float:
    """Share of prior values <= value. Nothing about today in the denominator."""
    return float(np.mean([p <= value for p in prior])) if prior else 0.0


def is_cold(comp: float, prior_comp: list[float]) -> tuple[bool, float]:
    """Cold iff the composite is at or below the prior sessions' lower
    tercile -- `<=`, as `regime.classify` cuts, so a tie at the cut is cold."""
    cut = float(np.quantile(prior_comp, 1 / 3))
    return comp <= cut, cut


def label_sessions(readings: dict[str, dict]) -> dict[str, dict]:
    """Date order. Each session against the sessions before it only.

    kind: 'count' (fewer than MIN_NAMES visible -> cold, no rating needed),
    'inert' (rated, but fewer than MIN_HISTORY prior composites to cut),
    'cold' or 'warm' (rated and cut). `composite` is in [0, 1] or None."""
    out = {}
    prior = {"n_visible": [], "lead": [], "held": []}
    prior_comp: list[float] = []
    for day in sorted(readings):
        r = readings[day]
        if r["n_visible"] < MIN_NAMES:
            out[day] = {"kind": "count", "cold": True, "composite": None, **r}
            continue
        held = -r["round_trip"]
        comp = None
        if prior["n_visible"]:
            comp = float(np.mean([pct_rank(r["n_visible"], prior["n_visible"]),
                                  pct_rank(r["lead"], prior["lead"]),
                                  pct_rank(held, prior["held"])]))
        if comp is None or len(prior_comp) < MIN_HISTORY:
            out[day] = {"kind": "inert", "cold": False, "composite": comp, **r}
        else:
            cold, cut = is_cold(comp, prior_comp)
            out[day] = {"kind": "cold" if cold else "warm", "cold": cold,
                        "composite": comp, "cut": cut, **r}
        prior["n_visible"].append(r["n_visible"])
        prior["lead"].append(r["lead"])
        prior["held"].append(held)
        if comp is not None:
            prior_comp.append(comp)
    return out


# --- the gate ------------------------------------------------------------------------

def gate_series(cold: bool, index: pd.DatetimeIndex, day: _date) -> pd.Series:
    """True on session-day bars before 07:00; on a cold session False from
    07:00; bars off the session day are False (outside the session anyway)."""
    local = index.tz_convert(ET)
    on_day = np.asarray(local.date == day)
    before = np.asarray(local.time < VETO_FROM)
    vals = on_day & (before | (not cold))
    return pd.Series(vals, index=index)


# --- pass 2: the books ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    from strategy.mc5 import mc5

    paths, day, universe, cold = args
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
           "error_days": [], "refused": {name: [] for name, _, v in BOOKS if v},
           "binding": {name: [0, 0, Counter()] for name, _, v in BOOKS if v}}
    for rec in universe:
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            idx5 = mc5.to_5m(df).index
            got = {}
            for name, eng, veto in BOOKS:
                mod, extra = engines[eng]
                gate = None if not veto else gate_series(cold, idx5 if eng == "mc5" else df.index, d)
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, entry_gate=gate, **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [G.trade_row(t, s, day, k) for k, t in enumerate(trades, 1)]
        for name, eng, veto in BOOKS:
            if not veto:
                continue
            base_name = "MCL" if eng == "mcl" else "MC5"
            for t in got[base_name]:
                m = minute_of(t.entry_time)
                if not (0 <= m < SESSION_MINUTES):
                    continue
                b = res["binding"][name]
                b[1] += 1
                after = m >= VETO_MINUTE
                if after:
                    b[0] += 1
                b[2][("after 07:00 on a cold session" if cold else "after 07:00 on a warm session")
                     if after else "before 07:00"] += 1
                if after and cold:
                    res["refused"][name].append(G.trade_row(t, s, day, 0))
    return day, res, ""


# --- report -------------------------------------------------------------------------

def sessions_block(labels: dict[str, dict], run_days: list[str]) -> list[str]:
    kinds = Counter(labels[d]["kind"] for d in run_days if d in labels)
    missing = sum(1 for d in run_days if d not in labels)
    cold = sum(1 for d in run_days if labels.get(d, {}).get("cold"))
    L = ["THE 07:00 READING, BY SESSION (registration §1)", "",
         f"  sessions run {len(run_days):,}   vetoed (cold) {cold:,} ({100 * cold / len(run_days) if run_days else 0:.1f}%)",
         f"    cold by count (< {MIN_NAMES} names visible at 07:00)  {kinds.get('count', 0):,}",
         f"    cold by composite (<= prior lower tercile)          {kinds.get('cold', 0):,}",
         f"    warm                                                 {kinds.get('warm', 0):,}",
         f"    inert (rated, fewer than {MIN_HISTORY} prior composites) {kinds.get('inert', 0):,}"
         + (f"   unread {missing:,}" if missing else ""), ""]
    vis = [labels[d]["n_visible"] for d in run_days if d in labels]
    if vis:
        L += [f"  names visible at 07:00: median {np.median(vis):.0f}, p10 {np.quantile(vis, .1):.0f}, "
              f"p90 {np.quantile(vis, .9):.0f}", ""]
    return L


def write_readings(path: Path, labels: dict[str, dict]) -> None:
    cols = ["date", "kind", "cold", "composite", "cut", "n_visible", "lead", "round_trip"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in sorted(labels):
            w.writerow(dict(labels[d], date=d))


# --- cli ---------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/cold_veto.txt")
    p.add_argument("--csv", default="var/reports/cold_veto_trades.csv")
    p.add_argument("--readings", default="var/reports/cold_veto_readings.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)

    # Pass 1: the reading, one slice per session.
    got1, t1 = G.run_sessions(read_session, [(p[-1:], d, u) for p, d, u in tasks], jobs, "cold_veto pass 1")
    labels = label_sessions({d: r for d, r in got1.items() if r is not None})
    Path(a.readings).parent.mkdir(parents=True, exist_ok=True)
    write_readings(Path(a.readings), labels)

    # Pass 2: the books, with the flag.
    tasks2 = [(p, d, u, bool(labels.get(d, {}).get("cold", False))) for p, d, u in tasks]
    got, t2 = G.run_sessions(run_day, tasks2, jobs, "cold_veto pass 2")

    books = {name: [] for name, _, _ in BOOKS}
    refused = {name: [] for name, _, v in BOOKS if v}
    binding = {name: [0, 0, Counter()] for name, _, v in BOOKS if v}
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
    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    binding_t = {k: (v[0], v[1], dict(v[2])) for k, v in binding.items()}
    emit("\n".join(G.render("H-B4: NO NEW ENTRIES AFTER 07:00 ON A SESSION THAT READS COLD AT 07:00",
                            REGISTERED, books, PAIRED, REPORTED, symdays, errors, run_days,
                            t1 + t2, jobs, refused, binding_t, error_days,
                            preamble=sessions_block(labels, run_days),
                            binding_kw={"what": "entries at or after 07:00 are the only ones a clock veto can refuse",
                                        "detail_label": "baseline entries by clock and session"})),
         a.out, header=f"common.cold_veto pairs={a.pairs} dataset={a.dataset} sessions={len(run_days)} "
                       f"symbol_days={symdays} cut={cut} qty={QTY} veto_from={VETO_FROM:%H:%M}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "veto_from": f"{VETO_FROM:%H:%M}", "readings": a.readings})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
