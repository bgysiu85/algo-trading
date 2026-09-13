#!/usr/bin/env python3
"""How much of the screen's 20x does a trivial filter already buy?

    python -m common.universe_lift
    python -m common.universe_lift --cutoff 05:00 --cell 8x15

THE CLAIM THIS EXISTS TO ATTACK
--------------------------------
`run_signal` measured a run rate of 0.108% across the whole premarket pull and
2.179% across the screened names, and I reported that as "the screen is a 20.2x
filter". That comparison is against EVERY NAME IN THE PULL -- roughly 705
symbol-days a session, most of which nobody would ever consider trading. So the
honest reading is "20x better than picking at random from the archive", which is
a much lower bar than "20x better than an obvious alternative".

If sorting on premarket dollar volume and taking the top twenty already buys
most of that, then the screen's MARGINAL contribution is small and the headline
has to be restated. That is the question here, and it is a check on my own
result rather than a new search.

RANKED WITHIN THE SESSION, WHICH IS HOW A WATCHLIST IS BUILT
-------------------------------------------------------------
A fixed threshold ("over $1M traded") is a different instrument on a quiet day
than on a busy one. Real watchlists are "today's most active twenty", so every
criterion here is ranked WITHIN each session and the top N taken -- the same
shape as the decision it is standing in for.

THE LOOK-AHEAD TRAP, WHICH IS THE WHOLE DIFFICULTY
----------------------------------------------------
Filtering on a session's full dollar volume and then counting that session's
runs is circular: a name that ran has high dollar volume BECAUSE it ran. The
number would be enormous and worthless.

So there is a hard wall at the cutoff. Every criterion is computed from bars at
or before it, every run is counted only if it STARTS after it, and a test
replaces all post-cutoff bars with noise and asserts no criterion moves.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.report_io import emit
from common.run_census import (MAX_PRICE, MIN_PRICE, runs_in)
from common.run_signal import parse_cell
from strategy.mcl.mcl import TRAIL_PCT as MCL_TRAIL

ET = ZoneInfo("America/New_York")

# Fixed here before any result was seen. Each is something a watchlist could
# actually be sorted on at the cutoff, and each is a plain function of the bars
# up to it.
CRITERIA = {
    "dollar_vol": "price x cumulative volume so far, in $. The obvious one.",
    "volume": "cumulative share volume so far.",
    "bars_traded": "minutes that printed a trade so far. A liveness measure "
                   "that ignores size entirely.",
    "range_pct": "mean(high-low)/close so far, in percent. Volatility already "
                 "showing.",
    "gap_pct": "close at the cutoff vs the PRIOR session's last close, in "
               "percent. What a gap scanner sorts on.",
    "price": "price at the cutoff. Not a plausible sort on its own -- it is "
             "here as a control, because a criterion that separates nothing "
             "should look like this one.",
}

TOP_N = [5, 10, 20, 50, 100, 250]
MIN_BARS_BEFORE = 20      # too thin a pre-cutoff window to rank on
MIN_BARS_AFTER = 30       # too little session left for the outcome to mean much


def cutoff_index(local: pd.DatetimeIndex, hh: int, mm: int) -> int:
    """Number of bars at or before the cutoff. The wall: features may read
    [:k], outcomes may only start at or after k."""
    mins = np.array([t.hour * 60 + t.minute for t in local])
    return int(np.searchsorted(mins, hh * 60 + mm, side="right"))


def measure(df: pd.DataFrame, k: int, prior_close: float | None) -> dict | None:
    """Every criterion, from bars [:k] only."""
    if k < MIN_BARS_BEFORE:
        return None
    pre = df.iloc[:k]
    close = pre["close"].to_numpy(dtype=float)
    vol = pre["volume"].to_numpy(dtype=float)
    high = pre["high"].to_numpy(dtype=float)
    low = pre["low"].to_numpy(dtype=float)
    last = float(close[-1])
    if not np.isfinite(close).all() or last < MIN_PRICE or last > MAX_PRICE:
        return None
    cum_vol = float(vol.sum())
    rng = float(np.nanmean((high - low) / np.where(close == 0, np.nan, close)))
    return {
        "dollar_vol": last * cum_vol,
        "volume": cum_vol,
        "bars_traded": float((vol > 0).sum()),
        "range_pct": rng * 100.0,
        "gap_pct": ((last / prior_close - 1.0) * 100.0
                    if prior_close else float("nan")),
        "price": last,
    }


def outcome(df: pd.DataFrame, k: int, cell: tuple[float, int],
            adverse: float) -> tuple[int, int]:
    """(runs starting at or after the cutoff, eligible bars after it).

    The run may FINISH wherever it finishes; only the start is walled.
    """
    # SLICED AT THE CUTOFF, not filtered after the fact. `runs_in` walks
    # greedily so that one move counts once, and that walk starts wherever the
    # array starts: given the whole frame it could open a run a bar or two
    # BEFORE the cutoff and skip past the very window we are measuring. A test
    # with the jump at bar 75 and the cutoff at 61 found exactly that -- the
    # run was opened at bar 60 and the post-cutoff count came back zero.
    close = df["close"].to_numpy(dtype=float)[k:]
    low = df["low"].to_numpy(dtype=float)[k:]
    r, n = cell
    if len(close) - n <= 0:
        return 0, 0
    found = runs_in(close, low, adverse, [r], [n])[(r, n)]
    return len(found), len(close) - n


def rank_and_slice(rows: list[dict], crit: str) -> dict[int, tuple[int, int]]:
    """{top_n: (runs, bars)} for one session, ranked on one criterion.

    Descending, because every criterion here is "more of this is more
    interesting" -- `price` included, which is why it is a control rather than
    a candidate.
    """
    usable = [r for r in rows if r[crit] == r[crit]]
    usable.sort(key=lambda r: r[crit], reverse=True)
    out = {}
    for n in TOP_N:
        sel = usable[:n]
        out[n] = (sum(r["runs"] for r in sel), sum(r["bars"] for r in sel))
    return out


def render(totals: dict, base: tuple[int, int], sessions: int, sym_days: int,
           skips: dict, cutoff: str, cell: tuple[float, int], adverse: float,
           elapsed: float) -> list[str]:
    r, n = cell
    b_runs, b_bars = base
    b_rate = (b_runs / b_bars * 100.0) if b_bars else float("nan")
    L = ["HOW MUCH OF THE SCREEN'S LIFT DOES A TRIVIAL SORT ALREADY BUY?", "",
         f"  a run = close rises {r:.0f}% within {n} bars, never having dipped "
         f"{adverse:.1f}% first",
         f"  cutoff {cutoff} ET: criteria read bars AT OR BEFORE it, runs are "
         "counted only",
         "  if they START after it",
         f"  {sym_days:,} symbol-day(s) over {sessions:,} session(s)",
         f"  elapsed {elapsed:.1f}s", ""]
    if skips:
        L += [f"  {sum(skips.values()):,} symbol-day(s) NOT used, by reason:"]
        for why, k in sorted(skips.items(), key=lambda x: -x[1]):
            L.append(f"      {k:>8,}  {why}")
        L.append("")
    if not b_bars:
        return L + ["NOTHING TO RANK", "", "  No usable symbol-days.", ""]

    L += ["THE BASELINE  (every name that passed the filters above)", "",
          f"  {'runs after the cutoff':<30}{b_runs:>12,}",
          f"  {'eligible bars after it':<30}{b_bars:>12,}",
          f"  {'run rate':<30}{b_rate:>11.3f}%", "",
          "  Every lift below is against THIS number, not against the figure",
          "  in the earlier report: that one used the whole session, this one",
          "  only the part after the cutoff.", ""]

    L += ["RUN RATE BY CRITERION AND WATCHLIST SIZE", "",
          "  ranked within each session, top N taken. The rate is runs over",
          "  eligible bars pooled across sessions.", ""]
    head = "  " + "criterion".ljust(16) + "".join(f"{f'top {t}':>12}"
                                                  for t in TOP_N)
    L += [head, "  " + "-" * (16 + 12 * len(TOP_N))]
    for crit in CRITERIA:
        row = "  " + crit.ljust(16)
        for t in TOP_N:
            runs, bars = totals[crit][t]
            row += f"{(runs / bars * 100.0) if bars else float('nan'):>11.3f}%"
        L.append(row)

    L += ["", "  THE SAME, AS A MULTIPLE OF THE BASELINE", ""]
    L += [head, "  " + "-" * (16 + 12 * len(TOP_N))]
    for crit in CRITERIA:
        row = "  " + crit.ljust(16)
        for t in TOP_N:
            runs, bars = totals[crit][t]
            rate = (runs / bars * 100.0) if bars else float("nan")
            row += f"{rate / b_rate if b_rate else float('nan'):>11.2f}x"
        L.append(row)

    L += ["", "", "WHAT EACH CRITERION IS", ""]
    for crit, desc in CRITERIA.items():
        L += [f"  {crit}", f"    {desc}", ""]

    L += ["HOW TO READ THIS", "",
          "  The question is NOT which criterion wins. It is how much of the",
          "  20.2x reported for the screen is available from a sort anyone",
          "  would think of in a minute. If `dollar_vol` at top 20 reaches",
          "  most of the way there, then the screen's marginal contribution is",
          "  small and my earlier headline was measuring the archive's long",
          "  tail rather than the screen's skill.",
          "",
          "  `price` is the control. It is not a plausible watchlist sort, so",
          "  whatever lift it shows is roughly what this method produces from",
          "  nothing -- read every other row against it, not against 1.00x.",
          "",
          "  A criterion can win here and still be untradeable: this counts",
          "  whether a run STARTED, never whether it could have been caught or",
          "  what it would have paid.",
          "",
          "WHAT THIS IS NOT", "",
          "  Not the screen itself. The real screen uses inputs this does not",
          "  have, and its `prior_close` is the one with the known defect. This",
          "  measures what a NAIVE sort achieves, to put a floor under the",
          "  comparison -- it cannot say the screen is better than its floor,",
          "  only whether the floor is already high.",
          "",
          "  Not out of sample. `var/state/holdout.json` is NOT touched.",
          "",
          "  Not free of survivorship in the pull: a name the universe fetch",
          "  never included is invisible here, however it would have ranked."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--cutoff", default="05:00",
                   help="ET wall between what a criterion may read and what "
                        "counts as an outcome.")
    p.add_argument("--cell", default="8x15")
    p.add_argument("--adverse", type=float, default=float(MCL_TRAIL))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    import time
    from common.databento_fetch import default_archive
    from common.dbn_io import read_dbn
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    cell = parse_cell(a.cell)
    try:
        hh, mm = int(a.cutoff[:2]), int(a.cutoff[-2:])
    except ValueError:
        sys.exit(f"--cutoff wants HH:MM, got {a.cutoff!r}")

    archive = Path(a.archive) if a.archive else default_archive()
    slices = window_slices(archive, a.dataset)
    if not slices:
        sys.exit(f"no 04:00-09:30 window slices under "
                 f"{archive}/{a.dataset}/ohlcv-1m.")
    if a.limit:
        slices = slices[-a.limit:]

    totals = {c: {t: [0, 0] for t in TOP_N} for c in CRITERIA}
    base = [0, 0]
    skips: dict[str, int] = {}
    sym_days = 0
    days: set[str] = set()
    prev_close: dict[str, float] = {}
    t0 = time.time()

    for k_slice, path in enumerate(slices, 1):
        day = date_of(path)
        frame = read_dbn(path)
        el = time.time() - t0
        eta = (len(slices) - k_slice) / (k_slice / el) / 60.0 if el else 0.0
        print(f"  [{k_slice:>4}/{len(slices)}] {day}  {base[0]:>7,} runs  "
              f"{el / 60:>5.1f} min elapsed  ~{eta:>5.1f} min left", flush=True)
        if frame.empty:
            continue
        days.add(day)
        rows, cur_close = [], {}
        for sym, df in frame.groupby("symbol"):
            sym = str(sym)
            df = df.sort_index()
            sym_days += 1
            cur_close[sym] = float(df["close"].iloc[-1])
            local = df.index.tz_convert(ET)
            k = cutoff_index(local, hh, mm)
            if k < MIN_BARS_BEFORE:
                skips["too few bars before the cutoff"] = skips.get(
                    "too few bars before the cutoff", 0) + 1
                continue
            if len(df) - k < MIN_BARS_AFTER:
                skips["too little session after the cutoff"] = skips.get(
                    "too little session after the cutoff", 0) + 1
                continue
            m = measure(df, k, prev_close.get(sym))
            if m is None:
                skips["unusable price or bars"] = skips.get(
                    "unusable price or bars", 0) + 1
                continue
            runs, bars = outcome(df, k, cell, a.adverse)
            if not bars:
                skips["no eligible bars after the cutoff"] = skips.get(
                    "no eligible bars after the cutoff", 0) + 1
                continue
            m.update(runs=runs, bars=bars, symbol=sym)
            rows.append(m)
            base[0] += runs
            base[1] += bars
        prev_close = cur_close
        for crit in CRITERIA:
            got = rank_and_slice(rows, crit)
            for t, (runs, bars) in got.items():
                totals[crit][t][0] += runs
                totals[crit][t][1] += bars

    if not base[1]:
        sys.exit(f"no usable symbol-days in {sym_days:,} examined.")

    out = a.out or "var/reports/universe_lift.txt"
    emit("\n".join(render({c: {t: tuple(v) for t, v in d.items()}
                           for c, d in totals.items()},
                          tuple(base), len(days), sym_days, skips,
                          a.cutoff, cell, a.adverse, time.time() - t0)),
         out, header=f"common.universe_lift  cutoff={a.cutoff} "
                     f"cell={a.cell} adverse={a.adverse:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
