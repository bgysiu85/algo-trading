#!/usr/bin/env python3
r"""XNAS.ITCH against the consolidated tape, by the clock -- the screen's capture, measured directly.

    python -m common.itch_capture --jobs 8
    python -m common.itch_capture --limit 20        # a quick pass

Registered in docs/research/REGISTERED_screen_itch_v2.md before it ran.

WHY THIS REPLACES THE CHAIN
---------------------------
`tape_capture` produced XNAS.ITCH's capture as 0.552 (XNAS.BASIC's share of the
consolidated DAILY bar) x 0.229 (ITCH's share of BASIC's pre-market volume at
09:30). One figure, applied at every tick of the session. But before 2026-03-30
the two tapes were the same tape until 08:00 -- ratio 1.000 at every decile --
so the chained threshold was a fifth of BASIC's on identical bars, and 2,902
names surfaced "earlier" on ITCH by construction
(`screen_itch_RESULT_20260917.md` §4).

The chain existed because there was no ITCH daily bar. There was never any
need for one: the archive carries EQUS.SUMMARY `statistics` for every session,
and `CLEARED_VOLUME` (stat_type 6) is the consolidated cumulative volume AT A
TIME -- `capture_intraday` already used it as a ladder for EQUS.MINI. So this
measures the quantity the screen needs with no BASIC in the loop:

    capture(t) = ITCH cumulative volume 04:00->t  /  consolidated CLEARED_VOLUME at t

for t every 30 minutes from 04:30 to 09:30, on each side of 2026-03-30.

Consolidated cleared volume at 07:00 before the cut does NOT contain the
off-exchange trades the TRF had not yet reported -- the SIP had not seen them
either, and neither had TradingView's `premarket_volume` column. That is the
point: the capture is against what the live screen would have been comparing
100,000 to at that minute, on that date, and nothing else.

WHICH NAMES
-----------
The band is now defined on the CONSOLIDATED figure -- names whose cleared
volume by 09:30 lies within 0.5x-5x of the live screen's 100,000 -- which is
the population the clause decides, stated in the units the clause is written
in. The point-in-time universe (screened on BASIC) and every active name are
reported beside it.

WHAT IS CHECKED ABOUT THE STATISTIC ITSELF
------------------------------------------
A cumulative statistic is only as fresh as its last publication. For every
cutoff the report prints how far behind the cutoff the statistic used actually
sits (median minutes), because a stat published hourly would make a 30-minute
ladder a fiction. A ratio above 1.0 is a defect of the join and is counted,
not averaged.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit
from common.tv_screener import PREMARKET_VOLUME_MIN

ET = ZoneInfo("America/New_York")
TAPE = "XNAS.ITCH"
STATS = "EQUS.SUMMARY"
CLEARED_VOLUME = 6                 # databento_dbn.StatType.CLEARED_VOLUME
TRF_CUT = "2026-03-30"
SESSION_START_MIN = 4 * 60
CUTOFFS = tuple(f"{m // 60:02d}:{m % 60:02d}" for m in range(4 * 60 + 30, 9 * 60 + 31, 30))
HEADLINE = "09:30"
MIN_CONS = 10_000                  # consolidated shares by 09:30 to count as active
BAND = (0.5, 5.0)                  # x the live threshold, on the consolidated figure
PAIRS = "var/state/screen_pairs_pit.json"


def minute_of(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def cutoff_utc(day: str, hhmm: str) -> pd.Timestamp:
    d = datetime.strptime(day, "%Y-%m-%d").date()
    return pd.Timestamp(datetime.combine(d, dtime(minute_of(hhmm) // 60, minute_of(hhmm) % 60),
                                         tzinfo=ET)).tz_convert("UTC")


def tape_cumulative(df: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per symbol, ITCH volume of the bars CLOSED by each cutoff (ts_event is
    the bar start, so `index < cutoff` is `ts_event + 60s <= cutoff`)."""
    if df.empty:
        return pd.DataFrame(columns=list(CUTOFFS))
    out = {c: df[df.index < cutoff_utc(day, c)].groupby("symbol")["volume"].sum()
           for c in CUTOFFS}
    return pd.DataFrame(out).fillna(0.0)


def cleared_ladder(stats: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per symbol: consolidated cleared volume at each cutoff, and how many
    minutes before the cutoff the statistic used was published.

    Max at-or-before the cutoff, as `capture_ratio.cleared_by_cutoff` does;
    the publication time is that of the LAST row at or before the cutoff,
    which for a monotone series is the row carrying the max.
    """
    if stats.empty or "stat_type" not in stats.columns:
        return pd.DataFrame(columns=list(CUTOFFS)), pd.DataFrame(columns=list(CUTOFFS))
    cv = stats[stats["stat_type"] == CLEARED_VOLUME]
    if cv.empty or "symbol" not in cv.columns:
        return pd.DataFrame(columns=list(CUTOFFS)), pd.DataFrame(columns=list(CUTOFFS))
    times = pd.to_datetime(cv["ts_event"] if "ts_event" in cv.columns else cv.index.to_series(),
                           utc=True)
    et = times.dt.tz_convert(ET)
    mins = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    cv = cv.assign(_min=mins)
    cv = cv[cv["_min"] >= SESSION_START_MIN].sort_values("_min", kind="mergesort")
    vol, age = {}, {}
    for c in CUTOFFS:
        m = minute_of(c)
        w = cv[cv["_min"] < m]
        if w.empty:
            vol[c] = pd.Series(dtype=float); age[c] = pd.Series(dtype=float)
            continue
        g = w.groupby("symbol")
        vol[c] = g["quantity"].max().astype(float)
        age[c] = (m - g["_min"].max()).astype(float)
    return pd.DataFrame(vol), pd.DataFrame(age)


def compare(tape: pd.DataFrame, stats: pd.DataFrame, day: str,
            universe: list[dict]) -> pd.DataFrame:
    """One row per consolidated-active symbol: capture at each cutoff, and
    the statistic's age at each."""
    cons, age = cleared_ladder(stats)
    if cons.empty or HEADLINE not in cons.columns:
        return pd.DataFrame()
    cons = cons[cons[HEADLINE].fillna(0) >= MIN_CONS]
    if cons.empty:
        return pd.DataFrame()
    itch = tape_cumulative(tape, day).reindex(cons.index).fillna(0.0)
    age = age.reindex(cons.index)
    rows = pd.DataFrame({"date": day, "symbol": cons.index})
    pit = {u["symbol"] for u in universe}
    rows["in_pit"] = rows["symbol"].isin(pit).values
    lo, hi = BAND[0] * PREMARKET_VOLUME_MIN, BAND[1] * PREMARKET_VOLUME_MIN
    rows["in_band"] = ((cons[HEADLINE] >= lo) & (cons[HEADLINE] <= hi)).values
    for c in CUTOFFS:
        cv = cons[c].to_numpy(dtype=float) if c in cons.columns else np.full(len(cons), np.nan)
        iv = itch[c].to_numpy(dtype=float) if c in itch.columns else np.zeros(len(cons))
        rows[f"cons_{c}"] = cv
        rows[f"itch_{c}"] = iv
        with np.errstate(divide="ignore", invalid="ignore"):
            rows[f"r_{c}"] = np.where(cv > 0, iv / cv, np.nan)
        rows[f"age_{c}"] = age[c].to_numpy(dtype=float) if c in age.columns else np.nan
    return rows


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    tape_path, stats_path, day, universe = args
    try:
        tape = read_dbn(Path(tape_path))
        stats = read_dbn(Path(stats_path), require_symbols=False)
    except Exception as e:                                  # noqa: BLE001
        return day, None, f"unreadable ({type(e).__name__}: {e})"
    return day, compare(tape, stats, day, universe), ""


# --- report -----------------------------------------------------------------

def q(v, p):
    v = v[~np.isnan(v)]
    return float(np.quantile(v, p)) if len(v) else float("nan")


def dist(rows: pd.DataFrame, col: str) -> dict:
    v = rows[col].to_numpy(dtype=float) if col in rows.columns else np.array([])
    ok = v[~np.isnan(v)]
    return {"n": int(len(ok)), "over_1": int((ok > 1.0 + 1e-9).sum()),
            "p10": q(ok, .10), "p50": q(ok, .50), "p90": q(ok, .90)}


def fmt(d: dict) -> str:
    if d["n"] == 0:
        return f"{'-':>8}{'-':>8}{'-':>8}"
    return (f"{d['p10']:>8.3f}{d['p50']:>8.3f}{d['p90']:>8.3f}"
            f"  n={d['n']:,}" + (f"  >1: {d['over_1']}" if d["over_1"] else ""))


def populations(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {"band": rows[rows["in_band"]], "pit": rows[rows["in_pit"]], "active": rows}


def summary(rows: pd.DataFrame) -> dict:
    out = {"tape": TAPE, "stats": STATS, "trf_cut": TRF_CUT, "cutoffs": list(CUTOFFS),
           "band": BAND, "band_on": "consolidated", "min_cons": MIN_CONS,
           "populations": {}, "stat_age_min": {}}
    for name, pop in populations(rows).items():
        ent = {"all": {}, "before": {}, "after": {}}
        before, after = pop[pop["date"] < TRF_CUT], pop[pop["date"] >= TRF_CUT]
        for c in CUTOFFS:
            ent["all"][c] = dist(pop, f"r_{c}")
            ent["before"][c] = dist(before, f"r_{c}")
            ent["after"][c] = dist(after, f"r_{c}")
        out["populations"][name] = ent
    for c in CUTOFFS:
        d = dist(rows, f"age_{c}")
        out["stat_age_min"][c] = {"p50": d["p50"], "p90": d["p90"], "n": d["n"]}
    # THE LADDER screen_sim READS: band medians, per regime, keyed by ET
    # minute-of-day. A tick at minute m uses the step at the largest key <= m
    # (held from the left); a tick before the first key uses the first.
    band = out["populations"]["band"]
    out["ladder"] = {reg: {str(minute_of(c)): (None if band[reg][c]["n"] == 0
                                                else round(band[reg][c]["p50"], 4))
                           for c in CUTOFFS}
                     for reg in ("before", "after")}
    return out


def render(s: dict, n_days: int, missing_stats: int, elapsed: float, jobs: int,
           out_json: str) -> list[str]:
    L = [f"{TAPE} AGAINST THE CONSOLIDATED TAPE ({STATS} CLEARED_VOLUME), BY THE CLOCK", "",
         "  registered  docs/research/REGISTERED_screen_itch_v2.md",
         f"  {n_days:,} sessions   {missing_stats} without a statistics file   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)",
         f"  capture(t) = {TAPE} bars closed by t / consolidated cleared volume published by t",
         f"  active: >= {MIN_CONS:,} consolidated shares by {HEADLINE}   band: {BAND[0]:g}x-{BAND[1]:g}x "
         f"the live threshold ({PREMARKET_VOLUME_MIN:,}) on the consolidated figure", ""]
    for name, title in (("band", "THE BAND (names the clause decides, in its own units) -- THE LADDER"),
                        ("pit", "THE POINT-IN-TIME UNIVERSE (screened on XNAS.BASIC)"),
                        ("active", "EVERY ACTIVE NAME")):
        ent = s["populations"][name]
        L += [title, "", f"  {'cutoff':<8}{'':<10}{'p10':>8}{'p50':>8}{'p90':>8}"]
        for c in CUTOFFS:
            L.append(f"  {c:<8}{'before':<10}{fmt(ent['before'][c])}")
            L.append(f"  {'':<8}{'after':<10}{fmt(ent['after'][c])}")
        L.append("")
    L += ["HOW FRESH THE STATISTIC IS (minutes between the cutoff and the cleared-volume row used)", "",
          f"  {'cutoff':<8}{'p50':>8}{'p90':>8}{'n':>10}"]
    for c in CUTOFFS:
        a = s["stat_age_min"][c]
        L.append(f"  {c:<8}{a['p50']:>8.1f}{a['p90']:>8.1f}{a['n']:>10,}")
    L += ["", "  A ladder is only as fine as the statistic behind it. If p90 here approaches 30, the",
          "  30-minute steps are reading a stale number and the registration says so.", ""]
    b = s["populations"]["band"]
    L += ["THE SHAPE THE DIAGNOSIS PREDICTS, IN CONSOLIDATED UNITS", "",
          f"  before the cut, capture should be HIGH early (Nasdaq's share of exchange-only volume) and",
          f"  fall from 08:00 as the TRF's queue reaches the SIP; after the cut it should be flat.",
          f"  before: 07:00 {b['before']['07:00']['p50']:.3f}   08:30 {b['before']['08:30']['p50']:.3f}   "
          f"09:30 {b['before'][HEADLINE]['p50']:.3f}",
          f"  after:  07:00 {b['after']['07:00']['p50']:.3f}   08:30 {b['after']['08:30']['p50']:.3f}   "
          f"09:30 {b['after'][HEADLINE]['p50']:.3f}", "",
          "THE LADDER screen_sim READS", "",
          f"  written to {out_json} under \"ladder\"; run:",
          f"    python -m common.screen_sim --dataset {TAPE} --capture-ladder {out_json} "
          "--out var/state/screen_pairs_pit_itch_v2.json --report var/reports/screen_sim_itch_v2.txt", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/itch_capture.txt")
    p.add_argument("--json", default="var/reports/itch_capture.json")
    p.add_argument("--csv", default="var/reports/itch_capture.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, TAPE)}
    days = sorted(slices)
    if a.limit:
        days = days[:a.limit]
    stats_dir = archive / STATS / "statistics"
    tasks, missing = [], 0
    for d in days:
        f = stats_dir / f"{d}.dbn.zst"
        if not f.exists():
            missing += 1
            continue
        tasks.append((str(slices[d]), str(f), d, by_date.get(d, [])))
    if not tasks:
        raise SystemExit(f"no {STATS} statistics files under {stats_dir} for the {TAPE} sessions")
    print(f"itch_capture: {len(tasks):,} session(s); {missing} without statistics", flush=True)
    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    t0 = time.time()
    parts = []
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=2)
    for k, (day, rows, err) in enumerate(it, 1):
        if err:
            print(f"  ! {day}: {err}", flush=True)
        elif rows is not None and not rows.empty:
            parts.append(rows)
        if k % 50 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()
    cols = ["date", "symbol", "in_pit", "in_band"] + [f"r_{c}" for c in CUTOFFS] + [f"age_{c}" for c in CUTOFFS]
    rows = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    s = summary(rows)
    s["sessions"] = len(tasks)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(s, indent=1), encoding="utf-8")
    rows.to_csv(a.csv, index=False)
    emit("\n".join(render(s, len(tasks), missing, time.time() - t0, jobs, a.json)), a.out,
         header=f"common.itch_capture  {TAPE} vs {STATS}" + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
