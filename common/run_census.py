#!/usr/bin/env python3
"""How often does the tape do what TNON did at 07:35, and how much is in it?

    python -m common.run_census --source archive
    python -m common.run_census --source cache --limit 80

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT
---------------------------------------------------
Ben's 2026-09-13 reframe: stop patching MCL, look at the MOVE -- TNON 07:34 to
07:47, +11.7% in thirteen minutes -- and ask whether a strategy can be built to
capture that kind of thing.

Before anyone writes a condition, there is a prior question with no strategy in
it at all: HOW OFTEN DOES THAT SHAPE OCCUR, and how much is in one? If runs are
everywhere, catching them is not the problem and the false positives are. If
they are rare, the universe may be too small to support a strategy no matter
how good the signal. Those two worlds need different work, and the fork is
cheap to measure.

So this module counts. It does not signal, it does not enter, and it cannot be
traded.

THIS IS AN ORACLE, AND THE BIG NUMBER IS A CEILING
---------------------------------------------------
Every run here is found by looking FORWARD from a bar. That is look-ahead by
construction -- it is the point -- and it means the dollar figure this prints
is what a trader with tomorrow's tape would make, not what any rule would make.
Same bound-not-threshold reasoning as `mfe_exit`: a ceiling needs no parameter
chosen after the fact, and a real strategy's job is to be compared against it.

Read the ceiling as "this is the most that could ever be here", and then the
base rate -- runs per thousand bars -- as the thing any entry signal has to
beat. A signal that fires on 5% of bars chasing a shape that starts on 0.5% of
them is 90% wrong before anyone looks at an indicator.

NO CELL IS CHOSEN
-----------------
A run needs a size (R), a deadline (N bars) and a tolerance for the dip on the
way (A). Picking one triple after seeing the counts is how a measurement turns
into a fitted parameter, so the whole grid is swept and EVERY cell is printed,
including the ones that say nothing. The A default is read off MCL's own trail
rather than chosen here, because a move that dips further than the trail would
have stopped a real position out before it ran.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_fmt import acct
from common.report_io import emit
from strategy.mcl.mcl import TRAIL_PCT as MCL_TRAIL

ET = ZoneInfo("America/New_York")

# The grid. TNON's own move (+11.7% in 13 bars) sits inside it but is not a
# cell -- seeding the grid on the one case that prompted the question would
# make every count downstream a restatement of that case.
R_PCTS = [3.0, 5.0, 8.0, 12.0]        # size of the move, percent
N_BARS = [5, 10, 15, 30]              # deadline, minutes
A_PCT = float(MCL_TRAIL)              # dip tolerated on the way, percent

MIN_PRICE = 1.00                      # below this the tick is the move
# Above this it is not a stock, it is a reverse split. These names dilute and
# reverse-split repeatedly, and the tape is adjusted BACKWARDS: HUBC 2026-06-03
# is served at $207,533 a share, DSY at $13,884, SMX at $48,254. The screen
# picked them at their real price at the time -- a $2 stock -- so the PERCENT
# moves are sound and every DOLLAR is a fiction. Without this bound the first
# run of this census reported a $54,313,602 ceiling, of which one symbol
# supplied the bulk. 12 of 374 cached symbol-days trip it.
MAX_PRICE = 1_000.00
MIN_BARS = 40                         # a session too short to census


def runs_in(close: np.ndarray, low: np.ndarray, a_pct: float,
            r_pcts: list[float], n_bars: list[int]) -> dict:
    """Non-overlapping runs per (R, N) cell, for one symbol-day.

    Returns {(r, n): [(start_index, k, realised_ratio), ...]}.

    A run STARTS at bar t and COMPLETES at t+k when close[t+k] is at least
    R above close[t], provided no low between t+1 and t+k dipped more than A
    below close[t]. The dip guard is what keeps this honest: without it the
    census would count moves that any stop would have been taken out of, and
    the ceiling would be a number no position could ever have held.
    """
    n = len(close)
    nmax = max(n_bars)
    floor = close * (1.0 - a_pct / 100.0)

    alive = np.ones(n, dtype=bool)
    hit = {r: np.zeros(n, dtype=bool) for r in r_pcts}
    firstk = {r: np.zeros(n, dtype=np.int32) for r in r_pcts}
    ratio_at = {r: np.zeros(n, dtype=float) for r in r_pcts}
    snap: dict[tuple[float, int], np.ndarray] = {}

    for k in range(1, nmax + 1):
        m = n - k                       # bars with a t+k to look at
        if m <= 0:
            for r in r_pcts:
                for nb in n_bars:
                    if nb >= k:
                        snap.setdefault((r, nb), hit[r].copy())
            break
        alive[:m] &= low[k:] >= floor[:m]
        alive[m:] = False
        ratio = np.zeros(n)
        ratio[:m] = close[k:] / close[:m]
        for r in r_pcts:
            new = (~hit[r]) & alive & (ratio >= 1.0 + r / 100.0)
            hit[r] |= new
            firstk[r][new] = k
            ratio_at[r][new] = ratio[new]
        for nb in n_bars:
            if nb == k:
                for r in r_pcts:
                    snap[(r, nb)] = hit[r].copy()

    out: dict[tuple[float, int], list] = {}
    for r in r_pcts:
        for nb in n_bars:
            h = snap.get((r, nb))
            if h is None:
                out[(r, nb)] = []
                continue
            # Greedy non-overlap: one eleven-percent move is ONE run, not the
            # thirteen overlapping ones its every bar would otherwise start.
            picked, t = [], 0
            idx = np.flatnonzero(h)
            for t0 in idx:
                if t0 < t:
                    continue
                k = int(firstk[r][t0])
                picked.append((int(t0), k, float(ratio_at[r][t0])))
                t = t0 + k + 1
            out[(r, nb)] = picked
    return out


def census_frame(df: pd.DataFrame, symbol: str, date_str: str,
                 a_pct: float) -> tuple[dict, int, str]:
    """(cell -> list of run dicts, eligible bar count, skip reason).

    The reason is returned rather than swallowed: "too short" and "the price is
    a reverse-split artifact" are different facts about the archive, and only
    one of them is fixed by pulling more data.
    """
    if len(df) < MIN_BARS:
        return {}, 0, "short"
    close = df["close"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    if not np.isfinite(close).all():
        return {}, 0, "nan"
    if close.min() < MIN_PRICE:
        return {}, 0, "under $1"
    if close.max() > MAX_PRICE:
        return {}, 0, "reverse-split price"
    local = df.index.tz_convert(ET)
    found = runs_in(close, low, a_pct, R_PCTS, N_BARS)
    out = {}
    for cell, picked in found.items():
        rows = []
        for t0, k, ratio in picked:
            rows.append({
                "symbol": symbol, "date": date_str,
                "et": f"{local[t0].hour:02d}:{local[t0].minute:02d}",
                "mins": local[t0].hour * 60 + local[t0].minute - 240,
                "price": close[t0], "k": k,
                "pct": (ratio - 1.0) * 100.0,
                "move": (close[t0 + k] - close[t0]) * 100.0,   # per 100 shares
            })
        out[cell] = rows
    return out, len(close), ""


def pct(vals, p):
    return float(np.percentile(vals, p)) if len(vals) else float("nan")


def render(cells: dict, bars: int, sessions: int, sym_days: int,
           skips: dict[str, int] | int, source: str, a_pct: float,
           elapsed: float) -> list[str]:
    L = ["HOW OFTEN DOES THE TAPE RUN, AND HOW MUCH IS IN IT?", "",
         f"  source: {source}   window 04:00-09:30 ET",
         f"  {sym_days:,} symbol-day(s) over {sessions:,} session(s)",
         f"  {bars:,} bars censused",
         f"  dip tolerated on the way: {a_pct:.1f}%  (MCL's own trail, not a "
         "number chosen here)",
         f"  elapsed {elapsed:.1f}s", ""]
    if isinstance(skips, int):
        skips = {"skipped": skips} if skips else {}
    if skips:
        L += [f"  {sum(skips.values()):,} symbol-day(s) NOT censused, by reason:"]
        for why, k in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"      {k:>6,}  {why}")
        L += ["", "  `reverse-split price` is a DATA defect, not a thin name: the",
              "  tape is adjusted backwards, so a $2 stock that later did a",
              "  1-for-100 arrives at $200 and its dollars are fiction while its",
              "  percentages are sound. Excluded rather than silently priced.", ""]
    if not bars:
        return L + ["NOTHING TO COUNT", "", "  No usable bars.", ""]

    L += ["THE GRID  (every cell, none chosen)", "",
          "  a run = close rises R% within N bars, having never dipped "
          f"{a_pct:.1f}% first", ""]
    head = "  " + "R \\ N".ljust(10) + "".join(f"{n:>14}" for n in N_BARS)
    L += [head, "  " + "-" * (10 + 14 * len(N_BARS))]
    for r in R_PCTS:
        row = f"  {r:>5.1f}%".ljust(12)
        for nb in N_BARS:
            row += f"{len(cells[(r, nb)]):>14,}"
        L.append(row)
    L += ["", "  the same counts as RUNS PER SESSION", ""]
    L += [head, "  " + "-" * (10 + 14 * len(N_BARS))]
    for r in R_PCTS:
        row = f"  {r:>5.1f}%".ljust(12)
        for nb in N_BARS:
            row += f"{len(cells[(r, nb)]) / max(sessions, 1):>14.2f}"
        L.append(row)

    L += ["", "", "THE BASE RATE  (what any entry signal has to beat)", "",
          "  runs per 1,000 bars censused. A signal firing on 5% of bars to",
          "  catch a shape that starts on 0.5% of them is 90% wrong before",
          "  anyone looks at an indicator.", ""]
    L += [head, "  " + "-" * (10 + 14 * len(N_BARS))]
    for r in R_PCTS:
        row = f"  {r:>5.1f}%".ljust(12)
        for nb in N_BARS:
            row += f"{len(cells[(r, nb)]) / bars * 1000.0:>14.2f}"
        L.append(row)

    L += ["", "", "WHAT IS IN ONE RUN  (per 100 shares, at the run's own price)",
          "", "  the ORACLE's gross: entered at the start bar's close, sold at",
          "  the completing bar's close, with the future known. No friction, no",
          "  slippage, no concurrency, and no rule that could have found it.", ""]
    L += ["  " + "cell".ljust(14) + "runs".rjust(9) + "median".rjust(11)
          + "p75".rjust(11) + "median k".rjust(11) + "CEILING total".rjust(16)]
    L += ["  " + "-" * 72]
    for r in R_PCTS:
        for nb in N_BARS:
            rows = cells[(r, nb)]
            if not rows:
                L.append("  " + f"{r:.0f}% in {nb}".ljust(14)
                         + f"{0:>9,}" + "n/a".rjust(11))
                continue
            mv = [x["move"] for x in rows]
            ks = [x["k"] for x in rows]
            L.append("  " + f"{r:.0f}% in {nb}".ljust(14)
                     + f"{len(rows):>9,}"
                     + acct(pct(mv, 50), 11) + acct(pct(mv, 75), 11)
                     + f"{pct(ks, 50):>11.0f}" + acct(sum(mv), 16))

    L += ["", "", "HOW TOP-HEAVY IS THAT CEILING?", "",
          "  share of each cell's total carried by its biggest runs. A total is",
          "  the wrong summary for a distribution this skewed: if a twentieth of",
          "  the runs carry half the money, then no rule that catches the",
          "  TYPICAL run gets anything like the headline -- it has to catch the",
          "  specific few, which is a much harder thing and a different one.", ""]
    L += ["  " + "cell".ljust(14) + "top 1%".rjust(10) + "top 5%".rjust(10)
          + "top 25%".rjust(10) + "median x n".rjust(16)]
    L += ["  " + "-" * 62]
    for r in R_PCTS:
        for nb in N_BARS:
            rows = cells[(r, nb)]
            if not rows:
                continue
            mv = sorted((x["move"] for x in rows), reverse=True)
            tot = sum(mv)
            if tot <= 0:
                continue
            def share(frac):
                k = max(1, int(len(mv) * frac))
                return sum(mv[:k]) / tot * 100.0
            L.append("  " + f"{r:.0f}% in {nb}".ljust(14)
                     + f"{share(0.01):>9.1f}%" + f"{share(0.05):>9.1f}%"
                     + f"{share(0.25):>9.1f}%"
                     + acct(pct(mv, 50) * len(mv), 16))

    # One cell gets its time-of-day profile: the one nearest TNON's own move,
    # named as such so the choice is visible rather than implied.
    ref = (8.0, 15)
    rows = cells.get(ref, [])
    if rows:
        L += ["", "", f"WHEN THEY START  (the {ref[0]:.0f}% in {ref[1]} cell, "
              "nearest TNON's own", "  +11.7% in 13 -- shown because it is "
              "nearest, not because it is best)", ""]
        edges = [(0, 60), (60, 120), (120, 180), (180, 240), (240, 300),
                 (300, 330)]
        for lo, hi in edges:
            sel = [x for x in rows if lo <= x["mins"] < hi]
            h0, h1 = 4 + lo // 60, 4 + hi // 60
            m0, m1 = lo % 60, hi % 60
            lab = f"{h0:02d}:{m0:02d}-{h1:02d}:{m1:02d} ET"
            bar = "#" * int(round(len(sel) / max(len(rows), 1) * 40))
            L.append(f"  {lab:<16}{len(sel):>7,}  {bar}")

    L += ["", "", "WHAT THIS IS NOT", "",
          "  NOT A STRATEGY, and not a backtest of one. Every run here was",
          "  found by reading the bars AFTER the start. The dollar column is",
          "  an oracle's -- the most that could ever be taken out of this",
          "  window -- and exists to be divided into, not reported as a result.",
          "",
          "  Not a claim that any of it is reachable. Nothing here says a rule",
          "  can find these bars in advance; that is the NEXT question, and it",
          "  is answered by comparing the run starts against the bars that look",
          "  like run starts and do not run. Without that denominator any",
          "  condition derived from these rows is fitted to them.",
          "",
          "  Not a chosen cell. The whole grid is printed. Picking the cell",
          "  with the best-looking number after seeing this table is the same",
          "  selection the feature study refused, one level up.",
          "",
          "  Not free of the universe. These are the symbols the screen already",
          "  selected, on the sessions that were pulled -- a run in a name the",
          "  screen never surfaced is invisible here."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--source", default="archive", choices=["archive", "cache"])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--cache", default="bar_cache")
    p.add_argument("--pairs", default="var/state/traded_pairs.json")
    p.add_argument("--adverse", type=float, default=A_PCT,
                   help="dip tolerated on the way, percent. Defaults to MCL's "
                        "trail; changing it is a different census and the "
                        "report says which was used.")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    cells = {(r, n): [] for r in R_PCTS for n in N_BARS}
    bars = 0
    skips: dict[str, int] = {}
    days: set[str] = set()
    sym_days = 0
    t0 = time.time()

    if a.source == "archive":
        from common.databento_fetch import default_archive
        from common.dbn_io import read_dbn
        from common.screen_sim import date_of, window_slices

        archive = Path(a.archive) if a.archive else default_archive()
        slices = window_slices(archive, a.dataset)
        if not slices:
            sys.exit(f"no 04:00-09:30 window slices under "
                     f"{archive}/{a.dataset}/ohlcv-1m.")
        if a.limit:
            slices = slices[-a.limit:]
        for k_slice, path in enumerate(slices, 1):
            day = date_of(path)
            frame = read_dbn(path)
            el = time.time() - t0
            eta = (len(slices) - k_slice) / (k_slice / el) / 60.0 if el else 0.0
            print(f"  [{k_slice:>4}/{len(slices)}] {day}  {bars:>12,} bars  "
                  f"{el / 60:>5.1f} min elapsed  ~{eta:>5.1f} min left",
                  flush=True)
            if frame.empty:
                continue
            days.add(day)
            for sym, df in frame.groupby("symbol"):
                df = df.sort_index()
                got, n, why = census_frame(df, str(sym), day, a.adverse)
                sym_days += 1
                if not n:
                    skips[why] = skips.get(why, 0) + 1
                    continue
                bars += n
                for cell, rows in got.items():
                    cells[cell].extend(rows)
    else:
        from common.cache_io import (SHARED_DURATION, SHARED_END_HHMM,
                                     load_cached_bars, load_pairs, window_dir)
        pairs = load_pairs(Path(a.pairs))
        if a.limit:
            pairs = pairs[:a.limit]
        cache = window_dir(Path(a.cache), SHARED_DURATION, SHARED_END_HHMM)
        for p in pairs:
            df = load_cached_bars(cache, p["symbol"], p["date"])
            sym_days += 1
            if df is None or df.empty:
                skips["no bars"] = skips.get("no bars", 0) + 1
                continue
            df.index = (df.index.tz_localize("UTC") if df.index.tz is None
                        else df.index.tz_convert("UTC"))
            df = df.sort_index()
            local = df.index.tz_convert(ET)
            day = datetime.strptime(p["date"], "%Y-%m-%d").date()
            keep = [(t.date() == day and (4 * 60) <= t.hour * 60 + t.minute
                     < (9 * 60 + 30)) for t in local]
            df = df[keep]
            got, n, why = census_frame(df, p["symbol"], p["date"], a.adverse)
            if not n:
                skips[why] = skips.get(why, 0) + 1
                continue
            days.add(p["date"])
            bars += n
            for cell, rows in got.items():
                cells[cell].extend(rows)

    out = a.out or "var/reports/run_census.txt"
    emit("\n".join(render(cells, bars, len(days), sym_days, skips,
                          a.source, a.adverse, time.time() - t0)),
         out, header=f"common.run_census  source={a.source} "
                     f"adverse={a.adverse:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
