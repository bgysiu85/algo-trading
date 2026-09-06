#!/usr/bin/env python3
"""Turn the Databento minute archive into bar_cache files the engines read.

    python -m common.bar_cache_build --pairs var/state/screen_pairs.json
    python -m common.bar_cache_build --pairs a.json b.json --confirm

WHY A SEPARATE CACHE ROOT, AND NOT bar_cache/
----------------------------------------------
`bar_cache/3d_to_2000/` holds IB bars. IB history is SPLIT-ADJUSTED; Databento
is raw. On any name that has since split the two disagree completely -- that is
the whole reason for moving, and it is also why they must never share a
directory.

A mixed cache would not fail. `load_sessions()` would read both, the backtest
would run, and the result would be part adjusted and part raw with nothing
saying which trades came from where. That is the exact shape of failure this
project keeps hitting: a plausible number out of a broken input.

So output goes to its own root (`bar_cache_db/` by default), a SOURCE.txt
records what produced it, and writing into a directory whose SOURCE.txt is
missing or disagrees is REFUSED. A run is then entirely one basis or entirely
the other, and which one is on disk beside the bars.

WHAT A FILE CONTAINS
--------------------
The engines expect a superset per symbol-day: N trading sessions ending at
20:00 ET on the named date, 04:00-20:00 each. `cache_io` slices each strategy's
own window out of it (MCL takes 2 sessions ending 09:30; VW9 takes 1 ending
20:00), so the superset must be built to the widest shape and sliced later --
never trimmed here.

"N sessions" means TRADING sessions, not calendar days. The calendar is derived
from the daily archive's distinct dates rather than guessed from weekdays,
because a guess is wrong on every market holiday and the error shows up as a
short warm-up rather than as an exception.

THREE CONVENTIONS CARRIED THROUGH
---------------------------------
* `ts_event` is the interval START. The IB cache uses the same convention, so
  the two are comparable in that respect at least -- do not "fix" either.
* Prices are RAW. Figures from this cache will not reconcile with older
  IB-based ones on any split name. That is correct.
* No bar exists for a minute with no trade. A thin pre-market is a sparse
  index, not zero-volume rows. Nothing here fills gaps: inventing a bar would
  invent a price the market never made.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.databento_fetch import default_archive
from common.dbn_io import read_dbn
from common.report_io import emit

ET = ZoneInfo("America/New_York")
OUT_DEFAULT = Path("bar_cache_db")
WINDOW_DIR = "3d_to_2000"          # matches the IB cache's naming
SESSIONS = 3                        # the shared superset depth
SESSION_START = (4, 0)              # 04:00 ET
SESSION_END = (20, 0)               # 20:00 ET, exclusive
SOURCE_NAME = "SOURCE.txt"


def load_pairs(paths) -> list[tuple[str, str]]:
    out = set()
    for p in paths:
        for row in json.load(open(p)):
            out.add((row["symbol"], row["date"]))
    return sorted(out)


def trading_calendar(archive: Path, dataset: str) -> list[str]:
    """Session dates, taken from the daily archive rather than assumed.

    Guessing weekdays is wrong on every market holiday, and the resulting
    window is short by a session -- which downstream reads as "too short for
    full warm-up" and silently drops the symbol-day.
    """
    d = archive / dataset / "ohlcv-1d"
    dates: set[str] = set()
    for f in sorted(d.glob("*.dbn.zst")):
        df = read_dbn(f)
        if df.empty:
            continue
        dates.update(df.index.strftime("%Y-%m-%d"))
    return sorted(dates)


def window_for(calendar: list[str], date: str, sessions: int) -> list[str]:
    """The `sessions` trading dates ending at `date` inclusive."""
    try:
        i = calendar.index(date)
    except ValueError:
        return []
    lo = i - sessions + 1
    if lo < 0:
        return []
    return calendar[lo:i + 1]


def slice_window(df: pd.DataFrame, dates: list[str]) -> pd.DataFrame:
    """Bars inside 04:00-20:00 ET on each of `dates`, concatenated in order."""
    if df.empty or not dates:
        return df.iloc[0:0]
    et = df.index.tz_convert(ET)
    day = et.strftime("%Y-%m-%d")
    minute = et.hour * 60 + et.minute
    keep = (pd.Series(day, index=df.index).isin(dates).to_numpy()
            & (minute >= SESSION_START[0] * 60 + SESSION_START[1])
            & (minute < SESSION_END[0] * 60 + SESSION_END[1]))
    return df[keep]


def cache_path(root: Path, symbol: str, date: str) -> Path:
    return root / WINDOW_DIR / f"{symbol}_{date}.csv.gz"


def write_bars(path: Path, df: pd.DataFrame) -> int:
    """One symbol-day superset, in the shape load_sessions() expects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out.index.name = "timestamp"
    with gzip.open(path, "wt", newline="", encoding="utf-8") as fh:
        out.to_csv(fh)
    return len(out)


def check_source(root: Path, dataset: str, schema: str) -> None:
    """Refuse to mix price bases in one directory.

    A cache holding both IB (split-adjusted) and Databento (raw) bars runs
    perfectly and produces a result that is part one and part the other, with
    nothing recording which trade came from where.
    """
    root.mkdir(parents=True, exist_ok=True)
    marker = root / SOURCE_NAME
    want = f"databento {dataset} {schema}"
    if marker.exists():
        got = marker.read_text(encoding="utf-8").splitlines()[0].strip()
        if got != want:
            sys.exit(f"{marker} says '{got}' but this run produces '{want}'. "
                     "Refusing to mix price bases in one cache root. Use a "
                     "different --out.")
        return
    existing = list((root / WINDOW_DIR).glob("*.csv.gz")) if (root / WINDOW_DIR).exists() else []
    if existing:
        sys.exit(f"{root/WINDOW_DIR} already holds {len(existing)} bar files "
                 f"and no {SOURCE_NAME}. That is almost certainly the "
                 "IB-derived cache, which is SPLIT-ADJUSTED where this is raw. "
                 "Refusing to write into it -- use a different --out.")
    marker.write_text(
        f"{want}\ngenerated {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}\n"
        "Prices are RAW (not split-adjusted). Do not mix with bar_cache/.\n",
        encoding="utf-8")


def build(pairs, archive: Path, dataset: str, out: Path, sessions: int,
          confirm: bool) -> dict:
    calendar = trading_calendar(archive, dataset)
    if not calendar:
        sys.exit(f"no daily bars under {archive/dataset}/ohlcv-1d -- the "
                 "trading calendar comes from there. Run "
                 "common.databento_universe first.")

    # Grouped by the month of the pair's DATE. The window reaches back up to
    # `sessions` trading days, so it can start in the PREVIOUS month -- the
    # previous chunk is therefore loaded alongside. A first version keyed on
    # every month the window touched and loaded one chunk at a time, which
    # meant a pair in the first days of a month never had its full window in
    # memory and was silently skipped in both passes. Roughly one pair in
    # twenty, with no error.
    by_month: dict[str, list] = defaultdict(list)
    windows: dict[tuple, list] = {}
    skipped_cal = []
    for sym, date in pairs:
        w = window_for(calendar, date, sessions)
        if not w:
            skipped_cal.append((sym, date))
            continue
        windows[(sym, date)] = w
        by_month[date[:7]].append((sym, date))

    stats = {"pairs": len(pairs), "no_window": len(skipped_cal),
             "written": 0, "empty": 0, "existing": 0, "short": 0,
             "months": len(by_month)}
    if not confirm:
        return stats

    for month in sorted(by_month):
        todo = [(s, d) for s, d in by_month[month]
                if not cache_path(out, s, d).exists()]
        stats["existing"] += len(by_month[month]) - len(todo)
        if not todo:
            print(f"  {month}: all present", flush=True)
            continue

        syms = {s for s, _ in todo}
        prev = _prev_month(month)
        frames = []
        for m in (prev, month):
            f = archive / dataset / "ohlcv-1m" / f"{m}.dbn.zst"
            if not f.exists():
                continue
            df = read_dbn(f)
            if not df.empty:
                frames.append(df[df["symbol"].isin(syms)])
        if not frames:
            print(f"  {month}: no chunks on disk, skipping {len(todo)}", flush=True)
            continue
        allbars = pd.concat(frames).sort_index()
        by_sym = {s: g for s, g in allbars.groupby("symbol", sort=False)}

        n = 0
        for sym, date in todo:
            g = by_sym.get(sym)
            if g is None:
                stats["empty"] += 1
                continue
            w = windows[(sym, date)]
            sl = slice_window(g, w)
            if sl.empty:
                stats["empty"] += 1
                continue
            # The superset must actually reach back to the first session in the
            # window. Writing a short file is worse than writing none: the
            # engine reads it, finds too little warm-up, and drops the
            # symbol-day -- which looks like the strategy having no signal.
            have = set(sl.index.tz_convert(ET).strftime("%Y-%m-%d"))
            if w[0] not in have:
                stats["short"] += 1
                continue
            write_bars(cache_path(out, sym, date), sl)
            stats["written"] += 1
            n += 1
        print(f"  {month}: {len(todo)} to do, wrote {n}", flush=True)
    return stats


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Databento minute bars -> bar_cache")
    ap.add_argument("--pairs", nargs="+", required=True)
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--dataset", default="EQUS.MINI")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--sessions", type=int, default=SESSIONS)
    ap.add_argument("--confirm", action="store_true",
                    help="actually write; without it this only plans")
    ap.add_argument("--report", default="var/reports/bar_cache_build.txt")
    a = ap.parse_args(argv)

    pairs = load_pairs(a.pairs)
    out = Path(a.out)
    if a.confirm:
        check_source(out, a.dataset, "ohlcv-1m")

    print(f"{len(pairs):,} symbol-days -> {out}/{WINDOW_DIR}/")
    st = build(pairs, Path(a.archive), a.dataset, out, a.sessions, a.confirm)

    lines = [
        "BAR CACHE BUILD", "",
        f"  source            {a.archive}/{a.dataset}/ohlcv-1m",
        f"  destination       {out}/{WINDOW_DIR}",
        f"  sessions per file {a.sessions}  (04:00-20:00 ET each)", "",
        f"  symbol-days requested   {st['pairs']:,}",
        f"  no window in calendar   {st['no_window']:,}"
        "   (too early for full warm-up)",
        f"  monthly chunks needed   {st['months']}",
    ]
    if a.confirm:
        lines += [
            f"  already on disk         {st['existing']:,}",
            f"  no bars in window       {st['empty']:,}",
            f"  window short of warm-up {st['short']:,}",
            f"  WRITTEN                 {st['written']:,}",
        ]
    else:
        lines.append("")
        lines.append("  Dry run. Re-run with --confirm to write.")
    emit("\n".join(lines), a.report,
         header=f"common.bar_cache_build  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
