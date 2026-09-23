#!/usr/bin/env python3
r"""Would this name have ALERTED before it was ever traded -- a UNIVERSE preflight.

    python -m common.running_up_universe_preflight --jobs 8

W05-0006. `running_up_preflight_RESULT_20260918.md` closed the Running Up
idea as a GATE: every momentum feature separates the trades that die in one
bar from the rest in the WRONG direction, so filtering individual ENTRIES on
it keeps more losers. Untested is Ben's original framing -- a NAME SELECTOR:
would a Running-Up-like signal have picked this symbol for today's watchlist
BEFORE the strategy's own entry condition ever fired on it?

THE UNIVERSE GAP, MEASURED FIRST
---------------------------------
`var/state/screen_pairs_pit_itch_v2.json` is the point-in-time SCANNED
universe: 6,411 symbol-days. Only 3,903 of those ever produced a trade
(`session_scenarios_trades.csv`); 2,508 were on the watchlist and never
traded. THAT is the population a real name selector must be tested
against -- but `bar_cache_xnas` (built to feed the strategies that DID
trade) holds no bars for those 2,508 symbol-days, so "would this untraded
name have alerted" cannot be answered without a priced data pull (see the
RESULT doc, next steps). This preflight answers the half already paid for:
on the 3,903 symbol-days that DID trade, would a computable stand-in for the
alert have fired BEFORE the strategy's own first entry that day -- early
enough to be a usable pre-trade filter -- and how much warning would it give?

THE PROXY
---------
Warrior's Running Up: "climbing fast on a burst of volume." The only piece
already measured with a large AUC (0.751 on MCL, wrong direction,
`running_up_preflight_RESULT_20260918.md`) is `ret_5m` -- the five-minute
return, computed the same point-in-time-safe way as there
(`common.running_up.ret_series`: closed bars only, the session's own
history, 04:00 ET start). This preflight uses `ret_5m` ALONE as the proxy
"alert" signal; the volume-burst half (`rvol_5m`) is deferred, see the
RESULT doc's next steps. NO THRESHOLD IS CHOSEN HERE -- the population's own
deciles are printed (PROGRAM_INDEX §5: look at the distribution of the thing
a threshold will cut before registering the threshold), together with, at
each decile cut, what share of symbol-days would have cleared it BEFORE the
first entry, and how many minutes of warning that would have given.

DESCRIPTIVE ONLY. No threshold is registered, no P&L is computed, no gate
exists. Mirrors running_up_preflight's own rule: a pre-flight that measures
separation (here: coverage and lead time) is not allowed to price it.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from common import gate_study as G
from common import running_up as RU
from common.report_io import emit

TRADES = "var/reports/session_scenarios_trades.csv"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"


def load_first_entries(path: Path) -> dict[str, list[dict]]:
    """{date: [{symbol, date, first_et}, ...]} -- the EARLIEST entry per
    symbol-day across both books, since the watchlist question is per NAME,
    not per book."""
    best: dict[tuple[str, str], str] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["symbol"], r["date"])
            if key not in best or r["entry_et"] < best[key]:
                best[key] = r["entry_et"]
    by_day: dict[str, list[dict]] = defaultdict(list)
    for (symbol, date), et in best.items():
        by_day[date].append({"symbol": symbol, "date": date, "first_et": et})
    return dict(by_day)


def symbol_lead_time(df: pd.DataFrame, entry_ts: pd.Timestamp) -> dict:
    """Pre-entry peak of the proxy alert (ret_5m) for one symbol's bars, and
    how many bars/minutes of lead time it had before `entry_ts`.

    Pulled out of `run_day` so it is testable on a synthetic frame without
    mocking `read_dbn`/`build_frame` -- the same reason `ret_series` and
    `dist_series` in `running_up.py` are separate, tested functions.
    """
    out = {"pre_bars": 0, "peak_ret5m": float("nan"), "lag_min": float("nan")}
    if df.empty:
        return out
    df = df.sort_index(kind="mergesort")
    ret5 = RU.ret_series(df, back=5)
    local = df.index.tz_convert(RU.ET)
    day_date = entry_ts.tz_convert(RU.ET).date()
    pre_mask = ((local.date == day_date) & (local.time >= RU.SESSION_START)
                & (df.index < entry_ts))
    pre = ret5[pre_mask]
    n_pre = int(pre.notna().sum())
    out["pre_bars"] = n_pre
    if n_pre:
        idx_max = pre.idxmax()
        peak = float(pre.loc[idx_max])
        if peak == peak:
            out["peak_ret5m"] = peak
            out["lag_min"] = (entry_ts - idx_max).total_seconds() / 60.0
    return out


def run_day(args: tuple) -> tuple:
    """One session: `symbol_lead_time` for every symbol traded that day.
    Module-level, picklable."""
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
    for e in entries:
        df = frame[frame["symbol"] == e["symbol"]]
        entry_ts = pd.Timestamp(f"{e['date']} {e['first_et']}", tz=RU.ET)
        out.append({**e, **symbol_lead_time(df, entry_ts)})
    return day, out, ""


def render(rows: list[dict], days: list[str], elapsed: float, jobs: int,
           pairs: str, dataset: str, trades: str, missing: int,
           universe_total: int, traded_total: int) -> list[str]:
    L = ["RUNNING UP AS A UNIVERSE -- A COVERAGE/LEAD-TIME PRE-FLIGHT, NOT A STUDY", "",
         "  NO REGISTRATION, because there is no rule here: no threshold, no gate,",
         "  no verdict, and no P&L anywhere in this report.", "",
         f"  trades      {trades}",
         f"  pairs       {pairs}   bars {dataset}",
         f"  scanned universe (point-in-time): {universe_total:,} symbol-days",
         f"  of which traded (either book):    {traded_total:,} symbol-days",
         f"  NEVER traded (no bars available):  {universe_total - traded_total:,} symbol-days"
         "  -- the true universe-selector question is untested on these; see RESULT doc",
         f"  {len(days):,} sessions   {len(rows):,} traded symbol-days read   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if missing:
        L += [f"  {missing:,} session(s) produced no rows (unreadable slice)", ""]

    n = len(rows)
    pre_bars = np.array([r["pre_bars"] for r in rows], dtype=float)
    zero = int((pre_bars == 0).sum())
    L += ["THE ROOM A PRE-TRADE ALERT WOULD HAVE HAD", "",
          f"  {zero:,} of {n:,} traded symbol-days ({zero / n:.1%}) had ZERO closed bars",
          "  before the strategy's own first entry -- the name was bought on sight,",
          "  and no alert computed from closed bars could have fired first.",
          f"  distribution of pre-entry bar count (n={n:,}):"]
    for q in (10, 25, 50, 75, 90):
        L.append(f"    p{q:<3d} {np.percentile(pre_bars, q):.1f} bars")
    L.append("")

    elig = [r for r in rows if r["pre_bars"] > 0 and r["peak_ret5m"] == r["peak_ret5m"]]
    L += [f"AMONG THE {len(elig):,} SYMBOL-DAYS WITH AT LEAST ONE PRE-ENTRY BAR", "",
          "  the pre-entry PEAK of ret_5m (the proxy alert), and its deciles --",
          "  where a later registration would have to pick its cut from:", ""]
    peaks = np.array([r["peak_ret5m"] for r in elig], dtype=float)
    lags = np.array([r["lag_min"] for r in elig], dtype=float)
    cuts = RU.deciles(peaks)
    L.append(f"  {'p10':>8}{'p20':>8}{'p30':>8}{'p40':>8}{'p50':>8}{'p60':>8}"
              f"{'p70':>8}{'p80':>8}{'p90':>8}")
    L.append("  " + "".join(f"{c:>8.3f}" for c in cuts))
    L.append("")
    L += ["  AT EACH CUT: share of the eligible population that would have cleared it",
          "  (coverage), and how many symbol-days of the FULL traded universe that is",
          "  (ceiling), and the median minutes of lead time for the ones that clear it:",
          "", f"  {'cut':>8}{'coverage(elig)':>16}{'coverage(all)':>15}{'median lag(min)':>18}"]
    for cut in cuts:
        clears = peaks >= cut
        cov_elig = float(clears.mean()) if len(clears) else float("nan")
        cov_all = float(clears.sum()) / n if n else float("nan")
        lag = float(np.median(lags[clears])) if clears.any() else float("nan")
        L.append(f"  {cut:>8.3f}{cov_elig:>16.1%}{cov_all:>15.1%}{lag:>18.1f}")

    L += ["", "HOW TO READ THIS", "",
          "  'coverage(all)' is the honest ceiling: the share of EVERY traded symbol-day",
          "  a gate at this cut could ever keep, given how little pre-entry history most",
          "  names have. It is well below 'coverage(elig)' whenever many symbol-days have",
          "  zero pre-entry bars (see above) -- a real constraint on this idea, not a",
          "  modelling artifact.", "",
          "WHAT THIS IS NOT", "",
          "  NOT A RESULT. No rule, no threshold, no P&L, no verdict.",
          "  NOT THE UNIVERSE QUESTION IN FULL. Restricted to symbol-days that were",
          "  traded, because that is where bars exist; the 2,508 scanned-but-never-",
          "  traded symbol-days are untested here (see the RESULT doc's next steps).",
          "  NOT MINUTE-FAITHFUL TO THE ALERTS. 1-minute bars approximate a scanner",
          "  that fires on ticks.",
          "  NOT WARRIOR'S SCANNER. ret_5m alone; no rvol_5m, no threshold copied from",
          "  their screen."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--trades", default=TRADES)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/running_up_universe_preflight.txt")
    p.add_argument("--csv", default="var/reports/running_up_universe_features.csv")
    return p


def main(argv=None) -> int:
    import json
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    tpath = Path(a.trades)
    by_day = load_first_entries(tpath)

    universe_total = len(json.loads(Path(a.pairs).read_text(encoding="utf-8")))
    traded_total = sum(len(v) for v in by_day.values())

    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    tasks = [(p[-1:], d, by_day.get(d, [])) for p, d, _ in tasks]
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "running_up_universe_preflight")

    days = sorted(got)
    rows = [x for d in days for x in got[d]]
    missing = len(tasks) - len(days)

    emit("\n".join(render(rows, days, elapsed, jobs, a.pairs, a.dataset, a.trades, missing,
                           universe_total, traded_total)),
         a.out, header=f"common.running_up_universe_preflight trades={a.trades} "
                       f"pairs={a.pairs} dataset={a.dataset} sessions={len(days)} "
                       f"rows={len(rows)} DESCRIPTIVE-NO-RULE-NO-PNL")
    if rows:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        cols = ["symbol", "date", "first_et", "pre_bars", "peak_ret5m", "lag_min"]
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
