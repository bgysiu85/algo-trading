#!/usr/bin/env python3
r"""H-T1 -- does the signal bar's ABSOLUTE volume separate anything?

    python -m common.thin_tape --jobs 8

Registered in docs/research/REGISTERED_thin_tape.md before this file existed.

BEN, on the two MC5 AEHL trades of 2026-09-18: "simply should not have
happened. there were no volume to support any trades." Signal-bar volume 2,003
shares and 634 shares, on five-minute bars -- about two shares a second.

WHY THIS HAS NEVER BEEN ASKED. Every volume feature this project has measured
is a RATIO. `running_up.rvol_1m` and `rvol_5m` divide by the session's own
median; MCL's `c_vol` is a multiple of the previous bar and `c_floor` a
fraction of a trailing average; MC5 has no volume clause at all. A ratio cannot
see an empty tape, because the denominator is empty too -- DAIC entered on
2,037 shares against a previous bar of 593, passed both of MCL's clauses, and
lost (27.37). Three times nothing is nothing.

THE SCREEN GATES THE DAY; NOTHING GATES THE BAR. Every symbol-day in the books
cleared pre-market volume >= 100,000 scaled by the capture ladder, so these are
not dead names. What was dead was the one bar the signal was read on.

A PRE-FLIGHT, NOT A GATE
------------------------
No threshold, no verdict, no P&L -- tests/common/test_thin_tape.py enforces it.
Separation is measured against the outcome label alone; the money comes later,
once, in a registered gate study scored against `gate_study.abstention`. A
feature that separates can still refuse the better half of a bad book, which is
what H-P1 found the day before this was written.

THE GRAIN, AND WHY IT IS NOT THE TAPE'S
---------------------------------------
`running_up_preflight` builds a 1-MINUTE frame and reads `vol[-1]` for both
books, so for MC5 -- which acts on five-minute bars -- it would read one fifth
of the quantity Ben is objecting about, with nothing looking wrong. That is
H-R1's defect of 2026-09-18 exactly, one day old.

So the volume is read off the ENGINE'S OWN BAR: the frame is resampled with the
engine's own resampler at the grain `rebound.engine_bar_minutes` reports for
that symbol-day, and the signal bar is then a bar of that frame rather than a
slice of the tape. Whether each entry stamp actually lands on that frame is
CHECKED AND PRINTED (§3.2), because a stamp convention that is off by one
bucket would shift every reading by a bar and look entirely ordinary.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

from common import gate_study as G
from common import running_up as RU
from common.entry_shares import QTY
from common.indicators import resample_bars
from common.rebound import engine_bar_minutes
from common.report_io import emit

ET = RU.ET
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_thin_tape.md"

BOOKS = (("MCL", "mcl"), ("MC5", "mc5"))
ONE_BAR = 1
TRAIL_REASON = "trailing_stop"

# The two new features, and neither is divided by anything.
VOL_BAR = "vol_bar"        # the signal bar itself, in shares
VOL_5BAR = "vol_5bar"      # that bar and the four before it
ABSOLUTE = (VOL_BAR, VOL_5BAR)

# The controls already in `running_up`, carried over unchanged so the AUCs here
# are comparable with the ones it published: `rand` is the crc32-seeded null
# and must land on 0.500, `minutes_since_0400` is the time-of-day confound.
CONTROLS = ("rand", "minutes_since_0400")

# §4's registered bar, fixed before the numbers existed. Printed with the
# readings rather than applied silently -- a decision rule nobody applies is
# decoration, and one applied out of sight is a verdict pretending to be a fact.
AUC_BAR = 0.60
MONOTONE_DECILES = 5


def signal_volume(df: pd.DataFrame, ts, bar_minutes: int) -> tuple[float, float, bool]:
    """(volume of the signal bar, of it plus the four before it, stamp landed).

    The frame is resampled with the ENGINE'S resampler first, so the bar this
    reads is the bar the engine read -- not `bar_minutes` worth of tape ending
    wherever the stamp happens to fall. `bar_minutes == 1` skips the resample
    and is bit-identical to reading the tape.

    The third value says whether `ts` is actually ON the resampled index. It is
    returned rather than assumed because an off-by-one-bucket stamp convention
    would move every reading by one bar and produce numbers that look fine.
    """
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        raise ValueError(f"signal_volume needs a tz-aware timestamp, got {ts!r}; "
                         "stamp it in ET before calling")
    bars = df if int(bar_minutes) <= 1 else resample_bars(df, int(bar_minutes))
    landed = bool(len(bars.index) and (bars.index == ts).any())
    hist = bars[bars.index <= ts]
    if hist.empty:
        return float("nan"), float("nan"), landed
    vol = hist["volume"].to_numpy(dtype=float)
    five = float(vol[-5:].sum()) if len(vol) >= 5 else float("nan")
    return float(vol[-1]), five, landed


# --- one session ------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session's entries, each with its absolute volumes. Picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
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

    res = {"rows": [], "symdays": 0, "errors": 0, "error_days": []}
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
            got = {}
            for name, eng in BOOKS:
                mod, extra = engines[eng]
                got[name] = (mod, mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                       not_before=floor, **extra))
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, (mod, trades) in got.items():
            bm = engine_bar_minutes(mod, df)
            for t in trades:
                ts = pd.Timestamp(t.entry_time)
                v1, v5, landed = signal_volume(df, ts, bm)
                # The controls come from `running_up` unchanged, at the tape's
                # grain, because neither depends on the bar size: `rand` is a
                # seeded draw and the clock is the clock.
                f = RU.features(df, ts, seed_key=f"{s}{day}{ts.isoformat()}")
                res["rows"].append({
                    "book": name, "symbol": s, "date": day,
                    "entry_et": ts.tz_convert(ET).strftime("%H:%M"),
                    "bar_min": int(bm), "on_grid": bool(landed),
                    "bars_held": int(t.bars_held), "reason": t.reason,
                    VOL_BAR: v1, VOL_5BAR: v5,
                    **{k: f.get(k, float("nan")) for k in CONTROLS},
                })
    return day, res, ""


# --- reading ----------------------------------------------------------------

def col(rows: list[dict], name: str) -> np.ndarray:
    return np.array([r.get(name, float("nan")) for r in rows], dtype=float)


def split(rows: list[dict], book: str) -> tuple[list[dict], list[dict]]:
    bk = [r for r in rows if r["book"] == book]
    return ([r for r in bk if r["bars_held"] <= ONE_BAR],
            [r for r in bk if r["bars_held"] > ONE_BAR])


def grid_block(rows: list[dict]) -> list[str]:
    """SCORED. Every entry stamp must land on the engine's own resampled index.

    If it does not, the bar this pass calls "the signal bar" is not the bar the
    engine read, every number below is shifted by one bucket, and nothing else
    in the report would show it.
    """
    L = ["STAMP CHECK: IS THE SIGNAL BAR THE BAR THE ENGINE READ?", "",
         "  The volume is read off the engine's own resampled frame. This asks",
         "  whether each entry's timestamp is actually a bar of that frame.", ""]
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name]
        if not b:
            L += [f"  {name}   no trades", ""]
            continue
        off = [r for r in b if not r["on_grid"]]
        L.append(f"  {name}   {len(b):,} entries   "
                 + (f"{len(off):,} NOT ON THE ENGINE'S GRID -- every reading "
                    f"below is shifted for those" if off
                    else "all on the engine's grid"))
        L += [f"      {r['symbol']:<6} {r['date']}  {r['entry_et']} ET  "
              f"{r['bar_min']}-minute" for r in off[:5]]
    L.append("")
    return L


def auc_block(rows: list[dict], label: str, note: str) -> tuple[list[str], dict]:
    L = [label, "", note, "",
         f"  {'feature':<22}{'n 1-bar':>10}{'n rest':>10}"
         f"{'median 1-bar':>15}{'median rest':>14}{'AUC':>8}",
         f"  {'-' * 79}"]
    got: dict[str, float] = {}
    for name, _ in BOOKS:
        one, rest = split(rows, name)
        if not one or not rest:
            L += [f"  {name}   not enough of one group to read", ""]
            continue
        L.append(f"  {name}")
        for feat in ABSOLUTE + CONTROLS:
            a, b = col(one, feat), col(rest, feat)
            au = RU.auc(a, b)
            if au != au:
                continue
            ma = float(np.nanmedian(a)) if (~np.isnan(a)).any() else float("nan")
            mb = float(np.nanmedian(b)) if (~np.isnan(b)).any() else float("nan")
            tag = "  <- control" if feat in CONTROLS else ""
            L.append(f"    {feat:<20}{len(one):>10,}{len(rest):>10,}"
                     f"{ma:>15,.0f}{mb:>14,.0f}{au:>8.3f}{tag}")
            got[f"{name}:{feat}"] = au
        L.append("")
    L += ["  AUC 0.500 is a feature that knows nothing, and `rand` must land",
          "  there. Below 0.500 means a LOW value marks the trade that dies,",
          "  which is the direction a volume floor would need.", ""]
    return L, got


def decile_block(rows: list[dict]) -> tuple[list[str], dict]:
    """The shape a threshold would have to express, and §5's rule: look at the
    distribution of the thing a threshold will cut before registering it."""
    L = ["THE SHAPE: ONE-BAR SHARE BY SIGNAL-BAR VOLUME DECILE", "",
         "  Deciles of `vol_bar` within each book, in shares. A floor can only",
         "  express a MONOTONE relationship, so this is the reading that says",
         "  whether one is expressible at all.", ""]
    falls: dict[str, list[bool]] = {}
    for name, _ in BOOKS:
        b = [r for r in rows if r["book"] == name]
        v = col(b, VOL_BAR)
        ok = ~np.isnan(v)
        if ok.sum() < 20:
            L += [f"  {name}   not enough rows to decile", ""]
            continue
        cuts = np.percentile(v[ok], np.arange(10, 100, 10))
        edges = [-np.inf, *cuts, np.inf]
        L.append(f"  {name}   {int(ok.sum()):,} entries")
        L.append(f"    {'decile':<10}{'volume range (shares)':>28}"
                 f"{'n':>9}{'one-bar share':>16}")
        shares = []
        for i in range(10):
            lo, hi = edges[i], edges[i + 1]
            sel = [r for r in b if r[VOL_BAR] == r[VOL_BAR]
                   and lo < r[VOL_BAR] <= hi]
            if not sel:
                continue
            s = 100.0 * sum(1 for r in sel if r["bars_held"] <= ONE_BAR) / len(sel)
            shares.append(s)
            lo_s = "0" if i == 0 else f"{lo:,.0f}"
            hi_s = "+" if i == 9 else f"{hi:,.0f}"
            L.append(f"    {i + 1:<10}{lo_s + ' - ' + hi_s:>28}"
                     f"{len(sel):>9,}{s:>15.1f}%")
        # Monotone in the direction a floor needs: the one-bar share FALLING as
        # volume rises, across the bottom deciles. A floor only has to be right
        # about the bottom.
        falls[name] = [shares[i + 1] <= shares[i]
                       for i in range(min(MONOTONE_DECILES, len(shares)) - 1)]
        L.append("")
    return L, falls


def rule_block(aucs: dict, falls: dict) -> list[str]:
    """§4's decision rule, printed with the two quantities it reads. Stated as
    facts; the registration is what turns them into a decision."""
    L = ["THE REGISTERED DECISION RULE (§4), AND WHAT IT READS", "",
         f"  A volume gate is registered only if AUC <= {1 - AUC_BAR:.2f} or "
         f">= {AUC_BAR:.2f} on at",
         "  least one book, with the other not inverted, AND the one-bar share",
         f"  falls across at least the bottom {MONOTONE_DECILES} deciles.", ""]
    for name, _ in BOOKS:
        a = aucs.get(f"{name}:{VOL_BAR}")
        if a is None:
            L.append(f"  {name}   no AUC to read")
            continue
        sep = abs(a - 0.5)
        L.append(f"  {name}   AUC {a:.3f}   separation {sep:.3f}   "
                 f"{'clears' if sep >= AUC_BAR - 0.5 else 'short of'} "
                 f"the registered {AUC_BAR:.2f}")
        f = falls.get(name)
        if f is not None:
            steps = "".join("v" if x else "^" for x in f)
            L.append(f"        bottom {len(f) + 1} deciles, step by step: {steps}"
                     f"   ({'falls throughout' if all(f) else 'not monotone'})")
    L += ["", "  Printed, not applied. The registration is what decides, and it",
          "  was written before these numbers existed.", ""]
    return L


def mcl_clause_block(rows: list[dict]) -> list[str]:
    """§3.3(5) -- the DAIC question generalised. Every MCL entry passed `c_vol`
    (3x the previous bar) and `c_floor` (half the trailing average). How many of
    them were on a bar that was, in absolute terms, nearly empty?"""
    L = ["\"THREE TIMES NOTHING\": MCL ENTRIES BY ABSOLUTE VOLUME", "",
         "  Every MCL entry below passed BOTH of its relative volume clauses.",
         "  The question is how many did so on a bar with almost nothing in it.",
         "  Counts against the pooled distribution; no threshold is named.", ""]
    b = [r for r in rows if r["book"] == "MCL"]
    v = col(b, VOL_BAR)
    ok = v[~np.isnan(v)]
    if len(ok) < 20:
        return L + ["  not enough rows to read", ""]
    for q in (1, 5, 10, 25, 50):
        cut = float(np.percentile(ok, q))
        n = int((ok <= cut).sum())
        L.append(f"    p{q:<3} = {cut:>12,.0f} shares    {n:>6,} entries at or below"
                 f"   ({100.0 * n / len(ok):5.1f}%)")
    L += ["",
          f"    median MCL signal bar: {float(np.median(ok)):,.0f} shares", ""]
    return L


def render(rows, days, symdays, elapsed, jobs, pairs, dataset, errors,
           error_days) -> list[str]:
    L = ["THIN TAPE: DOES THE SIGNAL BAR'S ABSOLUTE VOLUME SEPARATE ANYTHING?", "",
         f"  registered  {REGISTERED}",
         f"  universe    {pairs}   bars {dataset}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   "
         f"{len(rows):,} entries",
         f"  elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "  DESCRIPTIVE: no rule, no threshold, no verdict, no P&L.", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped:"]
        L += [f"    {e}" for e in error_days[:10]] + [""]

    L += ["POPULATION CHECK", ""]
    for name, _ in BOOKS:
        L.append(f"  {name} entries here   "
                 f"{sum(1 for r in rows if r['book'] == name):,}")
    L += G.population_lines(sum(1 for r in rows if r["book"] == "MCL"), pairs)
    L += [""]

    L += grid_block(rows)

    main, aucs = auc_block(
        rows, "SEPARATION AGAINST THE ONE-BAR LABEL",
        "  P(a one-bar trade scores above a surviving one), ties counted as\n"
        "  half. The same label `running_up_preflight` scored, so these are\n"
        "  directly comparable with its published AUCs -- ret_5m 0.751 / 0.636,\n"
        "  rand 0.526 / 0.505, the clock 0.528.")
    L += main

    shape, falls = decile_block(rows)
    L += shape

    L += rule_block(aucs, falls)

    L += mcl_clause_block(rows)

    trail = [r for r in rows
             if not (r["bars_held"] <= ONE_BAR and r["reason"] != TRAIL_REASON)]
    sub, _ = auc_block(
        trail, "REPORTED, NEVER SCORED: AGAINST THE ONE-BAR TRAILING-STOP CUT",
        "  H-R1's sharper population -- one-bar exits that were the trailing\n"
        "  stop firing, against everything that survived a bar. A different\n"
        "  label from the one §4's rule reads, so it is printed and not read\n"
        "  into the decision.")
    L += sub

    L += ["WHAT THIS IS NOT", "",
          "  NOT A GATE, AND NOT A PRICE ON ONE. Separation is not money: a",
          "  feature can separate and still refuse the better half of a bad",
          "  book, which is what the chase gate did the day before this ran.",
          "  The money comes later, once, in a registered gate study scored",
          "  against an abstention control.",
          "  NOT KNOWABLE-AT-ENTRY THROUGHOUT. The FEATURE is knowable at",
          "  entry; the LABEL is not. That is the only honest form of the",
          "  question and it is the form the Running Up pre-flight used.",
          "  NOT A VERDICT ON THE LIVE CASES. AEHL and DAIC happened and cost",
          "  what they cost. This asks whether a rule could have seen them",
          "  coming without refusing better trades alongside.",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/thin_tape.txt")
    p.add_argument("--csv", default="var/reports/thin_tape_entries.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "thin_tape")

    rows, symdays, errors, error_days = [], 0, 0, []
    days = sorted(got)
    for day in days:
        r = got[day]
        rows += r["rows"]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    emit("\n".join(render(rows, days, symdays, elapsed, jobs, a.pairs,
                          a.dataset, errors, error_days)), a.out,
         header=f"common.thin_tape pairs={a.pairs} dataset={a.dataset} "
                f"sessions={len(days)} entries={len(rows)} "
                f"DESCRIPTIVE-NO-RULE-NO-PNL registered={REGISTERED}")
    if rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()),
                               extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
