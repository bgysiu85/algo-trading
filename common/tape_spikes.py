#!/usr/bin/env python3
r"""Where XNAS.BASIC's minute bars carry prices nobody could have traded at.

    python -m common.tape_spikes --jobs 8
    python -m common.tape_spikes --jobs 8 --ib-cache bar_cache/3d_to_2000   # cross-check vs IB bars

WHAT WAS SEEN, 2026-09-16
-------------------------
MCL-PB v2 bought ALTS on 2025-08-11 at 19.76 at 08:35 and was stopped at 9.49
one minute later. The bars: from 08:00 the open and close sit at 8.6-9.5 while
the HIGH prints 16-20 and the LOW 6.5-6.8, bar after bar, and the 08:00 bar
alone carries 1.16m shares against 20-90k a minute before it. SLGB 2025-10-27,
same shape: closes 3.2, highs 12.0, lows 2.08, a 1.3m-share 08:00 bar. Across
2025-08-11, 60 such bars, 58 of them in the 08:00 hour; 1,162 of 1,771 names
printed an 08:00 bar over ten times their 07:xx median volume.

08:00 ET is when FINRA's trade reporting facility opens for the day, and
trades done off-exchange overnight or reported late land on the tape then,
stamped with the minute they were REPORTED in. A minute OHLCV bar cannot tell
a reported trade from an executed one, so the bar's high, low and volume are
contaminated while its open and close, which are set by the first and last
prints, mostly are not.

`premarket_hypotheses_results_20260908.md` §1 named exactly this check --
"whether XNAS.BASIC's minute ranges are widened by late-reported TRF prints
landing in the wrong minute, which would trigger trails a real-time trader
would not have seen" -- and it was never run. This is that check.

WHAT THIS MEASURES, AND WHAT IT DECIDES
---------------------------------------
A SPIKE BAR: high above SPIKE_UP x max(open, close), or low below
min(open, close) / SPIKE_UP. A real bar can do that; a bar that does it at
08:0x while its neighbours do not, on hundreds of names at once, cannot.

  1. Spike bars by minute of day and by month -- the shape and the extent.
  2. The 08:00 volume dump: names whose 08:00 bar is > DUMP_MULT x their
     07:xx median, by month.
  3. Attribution to MCL's published book: trades whose entry bar is a spike
     bar (a 3x volume clause fires on a reporting dump), whose exit bar is a
     spike bar (a trail hit by a low that was a late print), and their P/L.
  4. Optionally the same symbol-days on IB's bar cache, which is a different
     feed: if IB's bars for the same minutes do not spike, the prints are the
     feed's, not the market's.

It decides nothing on its own. A cleaning rule -- which prints to drop, or
which minutes to distrust -- is a registration, and this report is the
measurement it has to be written against.
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

ET = ZoneInfo("America/New_York")
SPIKE_UP = 1.25          # a high 25% over both open and close, or a low 20% under
DUMP_MULT = 10.0         # 08:00 volume over ten times the 07:xx median
PAIRS = "var/state/screen_pairs_pit.json"


def spike_mask(df: pd.DataFrame) -> pd.Series:
    oc_hi = np.maximum(df["open"], df["close"])
    oc_lo = np.minimum(df["open"], df["close"])
    return (df["high"] > SPIKE_UP * oc_hi) | (df["low"] * SPIKE_UP < oc_lo)


def run_day(args: tuple) -> tuple:
    """One session: spike bars on the whole slice, the dump census, and MCL's
    trades on the PIT universe marked by whether they touched a spike bar."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, ib_cache = args
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

    today = parts[-1][1]
    loc = today.index.tz_convert(ET)
    sp = spike_mask(today)
    res = {"bars": int(len(today)), "spikes": int(sp.sum()),
           "by_minute": Counter(loc[sp.to_numpy()].strftime("%H:%M")),
           "by_hour": Counter(loc[sp.to_numpy()].hour),
           "symbols": int(today["symbol"].nunique()),
           "symbols_spiking": int(today.loc[sp, "symbol"].nunique()),
           "spike_syms_0800": 0, "dump": 0, "dump_of": 0,
           "mcl": [], "ib": None}
    # The 08:00 volume dump.
    hh = loc.strftime("%H:%M")
    v7 = today[loc.hour == 7].groupby("symbol")["volume"].median()
    v8 = today[hh == "08:00"].groupby("symbol")["volume"].first()
    j = pd.concat([v7.rename("m"), v8.rename("v")], axis=1).dropna()
    res["dump_of"] = int(len(j))
    res["dump"] = int((j["v"] > DUMP_MULT * j["m"]).sum())
    res["spike_syms_0800"] = int(today.loc[sp & (loc.hour == 8), "symbol"].nunique())

    # MCL's published book on the PIT universe, marked.
    frame = build_frame(parts, day)
    mod, extra = engine("mcl")
    d = _date.fromisoformat(day)
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        try:
            trades = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                          not_before=first_seen_time(rec), **extra)
        except Exception:                                   # noqa: BLE001
            continue
        if not trades:
            continue
        m = spike_mask(df)
        for t in trades:
            e = pd.Timestamp(t.entry_time); x = pd.Timestamp(t.exit_time)
            res["mcl"].append({
                "symbol": rec["symbol"], "date": day, "net": float(t.net),
                "entry_spike": bool(m.get(e, False)), "exit_spike": bool(m.get(x, False)),
                "entry_hour": int(e.tz_convert(ET).hour), "reason": t.reason})

    # Cross-check against IB's cache for the same symbol-days, where present.
    if ib_cache:
        from common.cache_io import load_cached_bars
        rows = []
        for rec in universe:
            ib = load_cached_bars(Path(ib_cache), rec["symbol"], day)
            if ib is None or ib.empty:
                continue
            ibl = ib.index.tz_convert(ET)
            ib_day = ib[(ibl.date == d) & (ibl.hour >= 4) & ((ibl.hour < 9) | ((ibl.hour == 9) & (ibl.minute < 30)))]
            xn = today[today["symbol"] == rec["symbol"]]
            if ib_day.empty or xn.empty:
                continue
            rows.append({"symbol": rec["symbol"], "ib_bars": int(len(ib_day)),
                         "ib_spikes": int(spike_mask(ib_day).sum()),
                         "xn_bars": int(len(xn)), "xn_spikes": int(spike_mask(xn).sum())})
        res["ib"] = rows
    return day, res, ""


# --- report -----------------------------------------------------------------

def money(x: float) -> str:
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def render(days: list[str], got: dict, elapsed: float, jobs: int, ib_cache) -> list[str]:
    tot_bars = sum(r["bars"] for r in got.values())
    tot_sp = sum(r["spikes"] for r in got.values())
    by_hour = Counter(); by_min = Counter(); by_month = defaultdict(lambda: [0, 0, 0, 0])
    for day, r in got.items():
        by_hour.update(r["by_hour"]); by_min.update(r["by_minute"])
        mth = by_month[day[:7]]
        mth[0] += r["spikes"]; mth[1] += r["bars"]; mth[2] += r["dump"]; mth[3] += r["dump_of"]
    L = ["WHERE THE TAPE PRINTS PRICES NOBODY TRADED AT -- XNAS.BASIC, 04:00-09:30", "",
         f"  {len(days):,} sessions   {tot_bars:,} bars   elapsed {elapsed:.1f}s on {jobs} worker(s)",
         f"  spike bar = high > {SPIKE_UP:.2f} x max(open, close), or low < min(open, close) / {SPIKE_UP:.2f}",
         f"  dump      = a name's 08:00 bar over {DUMP_MULT:.0f} x its 07:xx median volume", "",
         "SPIKE BARS BY HOUR (ET)", ""]
    for h in range(4, 10):
        n = by_hour.get(h, 0)
        L.append(f"  {h:02d}:00   {n:>8,}   {100 * n / tot_sp if tot_sp else 0:5.1f}%")
    L += [f"  total   {tot_sp:>8,}   = {100 * tot_sp / tot_bars if tot_bars else 0:.3f}% of bars", "",
          "  the ten worst minutes:"]
    for k, v in by_min.most_common(10):
        L.append(f"    {k}  {v:,}")
    L += ["", "BY MONTH -- spike bars per 100k bars, and the 08:00 dump", "",
          f"  {'month':<9}{'spikes/100k':>12}{'dump names':>12}{'of':>8}{'share':>8}"]
    for m in sorted(by_month):
        s, b, dmp, of = by_month[m]
        L.append(f"  {m:<9}{100_000 * s / b if b else 0:>12.1f}{dmp:>12,}{of:>8,}"
                 f"{100 * dmp / of if of else 0:>7.0f}%")
    L += [""]

    mcl = [t for r in got.values() for t in r["mcl"]]
    f = MEASURED_FRICTION
    def blk(name, rows):
        n = len(rows); s = sum(t["net"] - f for t in rows)
        return f"  {name:<44}{n:>7,}   {money(s / n if n else 0):>9}/t   {money(s):>13}"
    L += ["MCL'S PUBLISHED BOOK, MARKED (net at $4.26)", "",
          blk("all trades", mcl),
          blk("entry bar is a spike bar", [t for t in mcl if t["entry_spike"]]),
          blk("exit bar is a spike bar", [t for t in mcl if t["exit_spike"]]),
          blk("either", [t for t in mcl if t["entry_spike"] or t["exit_spike"]]),
          blk("neither", [t for t in mcl if not (t["entry_spike"] or t["exit_spike"])]),
          blk("neither, entered 08:00-08:59", [t for t in mcl if not (t["entry_spike"] or t["exit_spike"]) and t["entry_hour"] == 8]),
          blk("neither, entered other hours", [t for t in mcl if not (t["entry_spike"] or t["exit_spike"]) and t["entry_hour"] != 8]),
          "",
          "  A spike bar at the entry means the 3x volume clause fired on a reporting",
          "  dump; at the exit, that the trail was reached by a low that may never",
          "  have been a quote. 'Neither' is the book a real-time trader could have",
          "  had, on this definition -- and the definition is a threshold, not a",
          "  trade-condition flag, so it is a lower bound on the contamination.", ""]

    if ib_cache:
        rows = [x for r in got.values() if r["ib"] for x in r["ib"]]
        if rows:
            ibb = sum(x["ib_bars"] for x in rows); ibs = sum(x["ib_spikes"] for x in rows)
            xnb = sum(x["xn_bars"] for x in rows); xns = sum(x["xn_spikes"] for x in rows)
            L += ["THE SAME SYMBOL-DAYS ON IB'S BARS", "",
                  f"  {len(rows):,} symbol-days present in both caches",
                  f"  IB           {ibb:>10,} bars   {ibs:>7,} spike bars   {100_000 * ibs / ibb if ibb else 0:.1f} per 100k",
                  f"  XNAS.BASIC   {xnb:>10,} bars   {xns:>7,} spike bars   {100_000 * xns / xnb if xnb else 0:.1f} per 100k",
                  "", "  If IB's feed does not print the spikes on the same minutes, they are",
                  "  the feed's, not the market's.", ""]
        else:
            L += ["THE SAME SYMBOL-DAYS ON IB'S BARS", "", "  no overlap found", ""]

    L += ["WHAT THIS DECIDES", "",
          "  Nothing by itself. It measures the extent of a defect in the tape every",
          "  study since 2026-09-08 has run on. A cleaning rule is a registration:",
          "  state which bars or prints to distrust BEFORE re-running anything, then",
          "  re-run MCL as published and report both figures side by side.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--ib-cache", default=None, help="IB window dir, e.g. bar_cache/3d_to_2000")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/tape_spikes.txt")
    p.add_argument("--csv", default="var/reports/tape_spikes_mcl.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]
    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day, by_date[day], a.ib_cache))
    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"tape_spikes: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
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
    emit("\n".join(render(run_days, {d: got[d] for d in run_days}, time.time() - t0, jobs, a.ib_cache)), a.out)
    rows = [t for d in run_days for t in got[d]["mcl"]]
    Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.csv, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
