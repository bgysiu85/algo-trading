#!/usr/bin/env python3
r"""How much of XNAS.BASIC's pre-market volume does XNAS.ITCH carry?

    python -m common.tape_capture --jobs 8
    python -m common.tape_capture --limit 20        # a quick pass

Registered in docs/research/REGISTERED_screen_itch.md before it ran. This is
step 1 of rebuilding the point-in-time screen on the exchange-only tape, and it
exists because the screen's volume clause is an ABSOLUTE threshold scaled by a
capture ratio:

    volume_min_on_tape = 100,000 x capture

`screen_at.CAPTURE_P50 = 0.552` is XNAS.BASIC's measured share of the
consolidated DAILY bar. XNAS.ITCH is a strict subset of XNAS.BASIC (Nasdaq's
exchange prints without the FINRA/Nasdaq TRF -- the Trade Reporting Facility,
where off-exchange trades are printed), so its capture is lower, and running
`screen_sim --dataset XNAS.ITCH` at 0.552 would demand more real volume than
the live screen does and under-select by construction.

There is no XNAS.ITCH daily bar in the archive to repeat `capture_ratio`
against, and the screen does not read the daily bar anyway: it reads
cumulative pre-market volume at each tick. So this measures the quantity the
screen actually uses, on the two tapes already on disk:

    ratio(T) = ITCH cumulative volume 04:00->T  /  BASIC cumulative volume 04:00->T

for T in 07:00, 08:00, 09:00, 09:30, on every symbol-day, and CHAINS the
ITCH capture from BASIC's:

    capture_ITCH = CAPTURE_P50 x median ratio(09:30)

The chain inherits BASIC's own approximation (a daily ratio applied to the
pre-market) and adds one measured factor. It is stated as such in the report
and the registration; it is not presented as a consolidated-tape measurement.

WHY THE LADDER AND THE SPLIT ARE THE CHECK ON THE DIAGNOSIS
-----------------------------------------------------------
The 08:00 defect was diagnosed as TRF prints reported late: before 2026-03-30
the TRF opened at 08:00, so BASIC carried no off-exchange volume before 08:00
and all of it (including trades executed at 05:00) from 08:00. If that is
right, then BEFORE the cut ratio(07:00) is ~1.00 -- the two tapes are the same
tape until 08:00 -- and AFTER the cut it is materially below 1, while
ratio(09:30) is similar in both regimes because by 09:30 the same trades have
been printed either way. A ladder that does not show that shape says the
diagnosis was wrong, and the rebuild should stop.

WHICH NAMES
-----------
Three populations, because capture is not the same for every name:

    pit    the symbol-days in the point-in-time universe (screened on BASIC)
    band   every symbol-day whose BASIC 09:30 volume lies within 0.5x-5x of
           the scaled threshold -- the names the clause actually decides
    active every symbol-day with at least MIN_TAPE shares on BASIC by 09:30

The headline is `band`, because the threshold is what the number feeds.
`pit` is reported because it is what every downstream result was run on, and
`active` because a figure that only holds on the selected names is a figure
about the selection.

A ratio above 1.0 is a defect, not a finding -- a subset cannot exceed its
superset -- and is counted separately rather than averaged in, the same rule
`capture_ratio` applies.
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
from common.screen_at import CAPTURE_P50, ScreenConfig

ET = ZoneInfo("America/New_York")
A, B = "XNAS.BASIC", "XNAS.ITCH"
TRF_CUT = "2026-03-30"           # the day the TRF began opening at 04:00
CUTOFFS = ("07:00", "08:00", "09:00", "09:30")
HEADLINE = "09:30"
MIN_TAPE = 10_000                # BASIC shares by 09:30 to count as active
BAND = (0.5, 5.0)                # x the scaled threshold; the decisive names
PAIRS = "var/state/screen_pairs_pit.json"


def cutoff_utc(day: str, hhmm: str) -> pd.Timestamp:
    h, m = (int(x) for x in hhmm.split(":"))
    d = datetime.strptime(day, "%Y-%m-%d").date()
    return pd.Timestamp(datetime.combine(d, dtime(h, m), tzinfo=ET)).tz_convert("UTC")


def cumulative(df: pd.DataFrame, day: str) -> pd.DataFrame:
    """Per symbol, volume of the bars CLOSED by each cutoff.

    `ts_event` is the bar's start (dbn_io convention 1), so the bar stamped
    06:59 closes at 07:00 and counts; the bar stamped 07:00 does not. That is
    `screen_at`'s own rule and the one the screen is simulated under.
    """
    if df.empty:
        return pd.DataFrame(columns=list(CUTOFFS))
    out = {}
    for c in CUTOFFS:
        sel = df[df.index < cutoff_utc(day, c)]
        out[c] = sel.groupby("symbol")["volume"].sum()
    return pd.DataFrame(out).fillna(0.0)


def compare(a: pd.DataFrame, b: pd.DataFrame, day: str,
            universe: list[dict], vmin: int) -> pd.DataFrame:
    """One row per BASIC-active symbol: both tapes' cumulatives and the ratios."""
    ca = cumulative(a, day)
    cb = cumulative(b, day)
    ca = ca[ca[HEADLINE] >= MIN_TAPE]
    if ca.empty:
        return pd.DataFrame()
    cb = cb.reindex(ca.index).fillna(0.0)      # absent from ITCH = no exchange prints
    rows = pd.DataFrame({"date": day, "symbol": ca.index})
    pit = {u["symbol"] for u in universe}
    rows["in_pit"] = rows["symbol"].isin(pit).values
    lo, hi = BAND[0] * vmin, BAND[1] * vmin
    rows["in_band"] = ((ca[HEADLINE] >= lo) & (ca[HEADLINE] <= hi)).values
    for c in CUTOFFS:
        rows[f"a_{c}"] = ca[c].values
        rows[f"b_{c}"] = cb[c].values
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(ca[c].values > 0, cb[c].values / ca[c].values, np.nan)
        rows[f"r_{c}"] = r
    return rows


def run_day(args: tuple) -> tuple:
    from common.dbn_io import read_dbn
    pa, pb, day, universe, vmin = args
    try:
        a = read_dbn(Path(pa))
        b = read_dbn(Path(pb))
    except Exception as e:                                  # noqa: BLE001
        return day, None, f"unreadable ({type(e).__name__}: {e})"
    return day, compare(a, b, day, universe, vmin), ""


# --- report -----------------------------------------------------------------

def q(v, p):
    v = v[~np.isnan(v)]
    return float(np.quantile(v, p)) if len(v) else float("nan")


def dist(rows: pd.DataFrame, col: str) -> dict:
    v = rows[col].to_numpy(dtype=float)
    ok = v[~np.isnan(v)]
    return {"n": int(len(ok)), "over_1": int((ok > 1.0 + 1e-9).sum()),
            "p10": q(ok, .10), "p50": q(ok, .50), "p90": q(ok, .90)}


def fmt(d: dict) -> str:
    if d["n"] == 0:
        return f"{'-':>8}{'-':>8}{'-':>8}{'':>9}"
    return (f"{d['p10']:>8.3f}{d['p50']:>8.3f}{d['p90']:>8.3f}"
            f"  n={d['n']:,}" + (f"  >1: {d['over_1']}" if d["over_1"] else ""))


def populations(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {"pit": rows[rows["in_pit"]], "band": rows[rows["in_band"]],
            "active": rows}


def summary(rows: pd.DataFrame, vmin: int) -> dict:
    """Everything the report prints, as data, so the JSON is the report."""
    out = {"capture_basic": CAPTURE_P50, "threshold_on_basic": vmin,
           "headline_cutoff": HEADLINE, "trf_cut": TRF_CUT,
           "band": BAND, "min_tape": MIN_TAPE, "populations": {}}
    for name, pop in populations(rows).items():
        ent = {"all": {}, "before": {}, "after": {}}
        before, after = pop[pop["date"] < TRF_CUT], pop[pop["date"] >= TRF_CUT]
        for c in CUTOFFS:
            ent["all"][c] = dist(pop, f"r_{c}")
            ent["before"][c] = dist(before, f"r_{c}")
            ent["after"][c] = dist(after, f"r_{c}")
        out["populations"][name] = ent
    head = out["populations"]["band"]["all"][HEADLINE]
    out["ratio_headline"] = {k: head[k] for k in ("p10", "p50", "p90", "n")}
    out["capture_itch"] = {k: (round(CAPTURE_P50 * head[k], 3)
                               if head["n"] else None)
                           for k in ("p10", "p50", "p90")}
    return out


def render(s: dict, n_days: int, elapsed: float, jobs: int, out_json: str) -> list[str]:
    L = [f"{B} AGAINST {A} -- PRE-MARKET VOLUME, CUMULATIVE FROM 04:00", "",
         "  registered  docs/research/REGISTERED_screen_itch.md",
         f"  {n_days:,} sessions on both tapes   elapsed {elapsed:.1f}s on {jobs} worker(s)",
         f"  ratio = {B} / {A}, per symbol-day, bars closed by the cutoff",
         f"  active: >= {MIN_TAPE:,} {A} shares by {HEADLINE}   band: {BAND[0]:g}x-{BAND[1]:g}x "
         f"the scaled threshold ({s['threshold_on_basic']:,} on {A})", ""]
    for name, title in (("band", "THE BAND (the names the threshold decides) -- HEADLINE"),
                        ("pit", "THE POINT-IN-TIME UNIVERSE (screened on XNAS.BASIC)"),
                        ("active", "EVERY ACTIVE NAME")):
        ent = s["populations"][name]
        L += [title, "", f"  {'cutoff':<8}{'':<10}{'p10':>8}{'p50':>8}{'p90':>8}"]
        for c in CUTOFFS:
            L.append(f"  {c:<8}{'all':<10}{fmt(ent['all'][c])}")
            L.append(f"  {'':<8}{'before':<10}{fmt(ent['before'][c])}")
            L.append(f"  {'':<8}{'after':<10}{fmt(ent['after'][c])}")
        L.append("")
    b = s["populations"]["band"]
    r7b, r7a = b["before"]["07:00"]["p50"], b["after"]["07:00"]["p50"]
    r930b, r930a = b["before"][HEADLINE]["p50"], b["after"][HEADLINE]["p50"]
    L += ["THE SHAPE THE DIAGNOSIS PREDICTS", "",
          f"  07:00  before {r7b:.3f}   after {r7a:.3f}   (before ~1.00, after below it: the TRF opened at 08:00 until {TRF_CUT})",
          f"  {HEADLINE}  before {r930b:.3f}   after {r930a:.3f}   (similar: by {HEADLINE} the same trades have printed either way)",
          "  If the 07:00 line is flat across the cut, or the 09:30 line is not, the diagnosis is wrong and",
          "  the rebuild stops here.", ""]
    ci = s["capture_itch"]; rh = s["ratio_headline"]
    L += ["THE CHAINED CAPTURE", "",
          f"  {A} capture, measured on the consolidated daily bar   {CAPTURE_P50:.3f}",
          f"  x {B}/{A} at {HEADLINE}, band, all sessions   p10 {rh['p10']:.3f}  p50 {rh['p50']:.3f}  p90 {rh['p90']:.3f}",
          f"  = {B} capture                                     p10 {ci['p10']}  p50 {ci['p50']}  p90 {ci['p90']}",
          f"  scaled volume threshold on {B} at p50: {round(100_000 * ci['p50']) if ci['p50'] else '-'} shares",
          "",
          "  This is a chain, not a measurement against the consolidated tape: it inherits BASIC's",
          "  daily-ratio-applied-to-pre-market approximation and adds one measured factor. The p10/p90",
          "  band here is the ratio's spread only; stacking BASIC's own p10/p90 would be wider.", "",
          "THE RUNS THIS FEEDS", "",
          f"  written to {out_json}; screen_sim reads --capture, one run per figure:"]
    for k in ("p10", "p50", "p90"):
        if ci[k]:
            L.append(f"    python -m common.screen_sim --dataset {B} --capture {ci[k]} "
                     f"--out var/state/screen_pairs_pit_itch_{k}.json --report var/reports/screen_sim_itch_{k}.txt")
    L += ["  p50 is the universe pit_h0 and pit_strategy score; p10 and p90 are the sensitivity of its SIZE only.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/tape_capture.txt")
    p.add_argument("--json", default="var/reports/tape_capture.json")
    p.add_argument("--csv", default="var/reports/tape_capture.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    sa = {date_of(p): p for p in window_slices(archive, A)}
    sb = {date_of(p): p for p in window_slices(archive, B)}
    days = sorted(d for d in sa if d in sb)
    if a.limit:
        days = days[:a.limit]
    vmin = ScreenConfig().volume_min_on_tape
    print(f"tape_capture: {len(days):,} session(s) on both tapes; "
          f"{len([d for d in sa if d not in sb])} on {A} only", flush=True)
    tasks = [(str(sa[d]), str(sb[d]), d, by_date.get(d, []), vmin) for d in days]
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
    rows = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["date", "symbol", "in_pit", "in_band"] + [f"r_{c}" for c in CUTOFFS])
    s = summary(rows, vmin)
    s["sessions"] = len(days)
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(s, indent=1), encoding="utf-8")
    rows.to_csv(a.csv, index=False)
    emit("\n".join(render(s, len(days), time.time() - t0, jobs, a.json)), a.out,
         header=f"common.tape_capture  {A} vs {B}  pairs={a.pairs}"
                + (f"  LIMIT {a.limit}" if a.limit else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
