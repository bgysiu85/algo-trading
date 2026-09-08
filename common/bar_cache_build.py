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


MONTHLY_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9].dbn.zst"
DAILY_GLOB = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].dbn.zst"


def archive_layout(d: Path) -> str:
    """Which of the two archive layouts is on disk: 'monthly', 'daily', 'none'.

    THE ARCHIVE HOLDS TWO LAYOUTS, and until 2026-09-08 this module only knew
    one of them:

      MONTHLY  2024-07.dbn.zst      common/overnight_pull.py. ALL_SYMBOLS, one
                                    calendar month, ~400 MB, with a
                                    .symbology.json sidecar beside it.
      DAILY    2024-07-08.dbn.zst   common/databento_fetch.py. Scoped to the
                                    symbols screened FOR THAT DATE, ~700 KB, no
                                    sidecar (a scoped request embeds its own
                                    mapping, so none is needed).

    Both are legitimate and both are on disk under E:\\Databento. Looking only
    for the monthly name meant a correctly-downloaded 515 MB XNAS.BASIC pull
    produced a cache of zero files, with a report showing every counter at zero
    -- the writer and the reader disagreed and nothing said so.

    They are NOT interchangeable inputs to the same loop, which is why this
    returns a layout rather than a file list. See _build_daily.

    Monthly wins where both exist: it is the full universe, where the daily
    files carry only the symbols each day's request named. Reading both would
    let a symbol's window be assembled from two different scopes.
    """
    if any(d.glob(MONTHLY_GLOB)):
        return "monthly"
    if any(d.glob(DAILY_GLOB)):
        return "daily"
    return "none"


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _write_pair(by_sym: dict, sym: str, date: str, window: list[str],
                out: Path, stats: dict) -> None:
    """Slice one symbol's window out of an already-loaded frame and write it."""
    g = by_sym.get(sym)
    if g is None:
        stats["empty"] += 1
        return
    sl = slice_window(g, window)
    if sl.empty:
        stats["empty"] += 1
        return
    # The superset must actually reach back to the first session in the window.
    # Writing a short file is worse than writing none: the engine reads it,
    # finds too little warm-up, and drops the symbol-day -- which looks like the
    # strategy having no signal.
    have = set(sl.index.tz_convert(ET).strftime("%Y-%m-%d"))
    if window[0] not in have:
        stats["short"] += 1
        return
    write_bars(cache_path(out, sym, date), sl)
    stats["written"] += 1


def _build_monthly(todo_by_chunk, windows, src: Path, out: Path,
                   stats: dict) -> dict:
    """Monthly chunks: load the pair's month and the one before it, together.

    The window reaches back up to `sessions` trading days, so it can start in
    the PREVIOUS month -- both chunks are therefore in memory at once. A first
    version keyed on every month the window touched and loaded one chunk at a
    time, which meant a pair in the first days of a month never had its full
    window in memory and was silently skipped in both passes. Roughly one pair
    in twenty, with no error.
    """
    for month in sorted(todo_by_chunk):
        todo = todo_by_chunk[month]
        syms = {s for s, _ in todo}
        prev = _prev_month(month)
        frames = []
        for m in (prev, month):
            f = src / f"{m}.dbn.zst"
            if not f.exists():
                continue
            df = read_dbn(f)
            if not df.empty:
                frames.append(df[df["symbol"].isin(syms)])
        if not frames:
            stats["no_source"] += len(todo)
            print(f"  {month}: NO SOURCE FILES on disk, skipping {len(todo)}",
                  flush=True)
            continue
        allbars = pd.concat(frames).sort_index()
        by_sym = {s: g for s, g in allbars.groupby("symbol", sort=False)}
        before = stats["written"]
        for sym, date in todo:
            _write_pair(by_sym, sym, date, windows[(sym, date)], out, stats)
        print(f"  {month}: {len(todo)} to do, wrote "
              f"{stats['written'] - before}", flush=True)
    return stats


def _build_daily(todo_by_chunk, windows, src: Path, out: Path,
                 stats: dict) -> dict:
    """Daily files: ONE file per pair-date, and it already holds the warm-up.

    `databento_fetch` names each file for the TARGET date but requests
    `--lookback` calendar days before it (5 by default), so 2024-07-08.dbn.zst
    spans roughly 2024-07-03 to 2024-07-09 for the symbols screened on the 8th.
    Everything a pair dated 2024-07-08 needs is inside that one file.

    That is why this cannot reuse the monthly loop. Grouping daily files by
    month and concatenating them would load each session five or six times over
    -- once from its own file and again from every later file whose lookback
    reaches it -- and `groupby("symbol")` would then hand `slice_window` a frame
    with each minute repeated. `write_bars` does not de-duplicate, so the cache
    would fill with plausible files carrying five copies of every bar. Volume
    sums would be 5x and nothing would raise. The month grouping is wrong for
    this layout, not merely slower.

    Five calendar days clears three TRADING sessions in every case the calendar
    produces, including a Tuesday after a Monday holiday (Thu, Fri, Tue) and the
    Christmas week. Where it does not, the window-start check in _write_pair
    counts the pair as short rather than writing a truncated superset.

    ONE KNOWN GAP, recorded rather than papered over: the fetch's end bound is
    midnight UTC on date+1, which is 20:00 ET under daylight time but 19:00 ET
    in winter. Files for winter dates therefore stop an hour before the 20:00
    session end. MCL (2 sessions to 09:30) and the ORB pre-flight (RTH) are
    unaffected; VW9's last post-market hour on those dates is not in the
    archive. Re-pulling with a wider end bound is the fix if that hour matters.
    """
    for day in sorted(todo_by_chunk):
        todo = todo_by_chunk[day]
        f = src / f"{day}.dbn.zst"
        if not f.exists():
            stats["no_source"] += len(todo)
            print(f"  {day}: NO SOURCE FILE, skipping {len(todo)}", flush=True)
            continue
        df = read_dbn(f)
        if df.empty:
            stats["no_source"] += len(todo)
            print(f"  {day}: source file is empty, skipping {len(todo)}",
                  flush=True)
            continue
        by_sym = {s: g for s, g in df.groupby("symbol", sort=False)}
        before = stats["written"]
        for sym, date in todo:
            _write_pair(by_sym, sym, date, windows[(sym, date)], out, stats)
        print(f"  {day}: {len(todo)} to do, wrote "
              f"{stats['written'] - before}", flush=True)
    return stats


def build(pairs, archive: Path, dataset: str, out: Path, sessions: int,
          confirm: bool) -> dict:
    calendar = trading_calendar(archive, dataset)
    if not calendar:
        sys.exit(f"no daily bars under {archive/dataset}/ohlcv-1d -- the "
                 "trading calendar comes from there. Run "
                 "common.databento_universe first.")

    src = archive / dataset / "ohlcv-1m"
    layout = archive_layout(src)

    # The chunk key differs by layout: a month per monthly file, a date per
    # daily one. Both then walk the same per-pair writer.
    windows: dict[tuple, list] = {}
    by_chunk: dict[str, list] = defaultdict(list)
    skipped_cal = []
    for sym, date in pairs:
        w = window_for(calendar, date, sessions)
        if not w:
            skipped_cal.append((sym, date))
            continue
        windows[(sym, date)] = w
        by_chunk[date[:7] if layout != "daily" else date].append((sym, date))

    stats = {"pairs": len(pairs), "no_window": len(skipped_cal),
             "written": 0, "empty": 0, "existing": 0, "short": 0,
             "no_source": 0, "chunks": len(by_chunk), "layout": layout}
    if not confirm:
        return stats

    if layout == "none":
        # Not an exception: the dry run is allowed to plan against an archive
        # that has not been pulled yet. But a --confirm run that writes nothing
        # must say why in the counters, not just in a line of stdout.
        stats["no_source"] = sum(len(v) for v in by_chunk.values())
        print(f"  no ohlcv-1m files of either layout under {src}", flush=True)
        return stats

    todo_by_chunk: dict[str, list] = {}
    for chunk, entries in by_chunk.items():
        todo = [(s, d) for s, d in entries if not cache_path(out, s, d).exists()]
        stats["existing"] += len(entries) - len(todo)
        if todo:
            todo_by_chunk[chunk] = todo

    fn = _build_daily if layout == "daily" else _build_monthly
    return fn(todo_by_chunk, windows, src, out, stats)


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
        f"  archive layout          {st['layout']}",
        f"  source chunks to read   {st['chunks']:,}"
        f"   ({'dates' if st['layout'] == 'daily' else 'months'})",
    ]
    if a.confirm:
        lines += [
            f"  already on disk         {st['existing']:,}",
            f"  NO SOURCE FILE          {st['no_source']:,}",
            f"  no bars in window       {st['empty']:,}",
            f"  window short of warm-up {st['short']:,}",
            f"  WRITTEN                 {st['written']:,}",
        ]
        if st["layout"] == "none":
            lines += ["",
                      "  LAYOUT 'none' means there are no ohlcv-1m files of "
                      "EITHER layout under",
                      f"  {a.archive}/{a.dataset}/ohlcv-1m -- neither monthly "
                      "(2024-07.dbn.zst) nor",
                      "  daily (2024-07-08.dbn.zst). The pull did not land "
                      "where this expects it.",
                      "  Nothing was written.  Nothing was overwritten."]
        elif st["no_source"]:
            lines += ["",
                      "  NO SOURCE FILE counts symbol-days whose source chunk "
                      "is absent from the",
                      "  archive. Those chunks were never pulled, or were "
                      "pulled for a different",
                      "  dataset. Nothing was written for them."]
        if st["layout"] == "daily":
            lines += ["",
                      "  Daily layout: each file is named for its TARGET date "
                      "and carries the",
                      "  fetch's lookback days before it, so one file holds a "
                      "pair's whole window.",
                      "  Its end bound is midnight UTC, which is 19:00 ET in "
                      "winter -- files for",
                      "  winter dates stop an hour short of the 20:00 session "
                      "end. MCL and the ORB",
                      "  pre-flight do not reach that hour; VW9's last "
                      "post-market hour does."]
    else:
        lines.append("")
        lines.append("  Dry run. Re-run with --confirm to write.")
    emit("\n".join(lines), a.report,
         header=f"common.bar_cache_build  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
