#!/usr/bin/env python3
"""Capture through the session, not just at the close.

    python -m common.capture_intraday --limit 20        # a quick pass
    python -m common.capture_intraday                   # the full run

WHY THIS EXISTS
---------------
`capture_ratio` measured EQUS.MINI against the consolidated tape on the DAILY
total: median 4.7%, with 45% of the variation day-to-day within a symbol. That
is the right measurement for the dollar-volume floor, which is a daily figure.

It is the wrong measurement for anything that decides DURING a session. A
strategy reading "volume so far today" at 09:30 is not reading the daily total,
and there is no reason capture at 09:30 should match capture at 20:00 -- the
venues EQUS.MINI omits do not necessarily trade in the same proportion through
the day. Pre-market especially: a tape missing the off-exchange venues could
see almost nothing at 07:00 and a fifth of the volume by 16:00, or the reverse.

So this measures the same ratio at a LADDER of cutoffs, on both sides:

    EQUS.MINI  cumulative MINUTE volume  up to T
    ------------------------------------------- , for T in CUTOFFS
    EQUS.SUMMARY  CLEARED_VOLUME         at   T

Both legs are cumulative from 04:00, so each cutoff is a like-for-like
comparison of the same window on two tapes.

WHY MINUTE BARS AND NOT THE DAILY BAR
--------------------------------------
The daily bar gives one number for the whole session, so it cannot answer a
question about 09:30. `capture_ratio` could use it because it only ever asked
about the close; this cannot. That makes this the expensive pass -- 43 monthly
chunks of full-universe minute data -- so symbols are filtered before anything
is concatenated.

capture_ratio's session check established that EQUS.MINI's daily bar equals the
sum of its own minute bars over 04:00-20:00 at a median ratio of 1.0000. That
is what licenses using minute bars here and comparing the result against the
daily-based figure: the two are the same quantity at the last cutoff.
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common.capture_ratio import (ET, SESSION_START_MIN, cleared_by_cutoff,
                                  load_pairs, quantiles)
from common.databento_fetch import default_archive
from common.dbn_io import read_dbn
from common.report_io import emit

# Cutoffs in ET minutes past midnight. 09:30 and 16:00 are the session
# boundaries; 07:00 is the middle of pre-market, where a partial tape is most
# likely to behave differently; the rest trace the shape.
CUTOFFS = [
    (7 * 60, "07:00"),
    (9 * 60 + 30, "09:30"),
    (10 * 60, "10:00"),
    (11 * 60, "11:00"),
    (12 * 60, "12:00"),
    (16 * 60, "16:00"),
    (20 * 60, "20:00"),
]


def minute_cumulative(minute: pd.DataFrame, day: str, symbols) -> dict:
    """{symbol: {label: cumulative volume up to that cutoff}} for one day."""
    if minute.empty:
        return {}
    g = minute[(minute["_day"] == day) & (minute["symbol"].isin(symbols))]
    if g.empty:
        return {}
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for cut, label in CUTOFFS:
        w = g[(g["_min"] >= SESSION_START_MIN) & (g["_min"] < cut)]
        if w.empty:
            continue
        for sym, v in w.groupby("symbol")["volume"].sum().items():
            out[sym][label] = int(v)
    return out


def analyse(archive: Path, by_date, stats_dataset, mini_dataset, tick=10):
    rows, missing = [], 0
    months = defaultdict(list)
    for day in by_date:
        months[day[:7]].append(day)

    t0, done, total = time.time(), 0, len(by_date)
    for month in sorted(months):
        mf = archive / mini_dataset / "ohlcv-1m" / f"{month}.dbn.zst"
        if not mf.exists():
            missing += sum(len(by_date[d]) for d in months[month])
            done += len(months[month])
            continue

        wanted = {s for d in months[month] for s in by_date[d]}
        minute = read_dbn(mf)
        if minute.empty:
            done += len(months[month])
            continue
        # Filter BEFORE anything else. A full-universe month is ~3,000 symbols
        # of minute bars; the screened set for one month is a few hundred, and
        # carrying the rest through the groupby is most of the runtime.
        minute = minute[minute["symbol"].isin(wanted)]
        if minute.empty:
            done += len(months[month])
            continue
        et = minute.index.tz_convert(ET)
        minute = minute.assign(_day=et.strftime("%Y-%m-%d"),
                               _min=et.hour * 60 + et.minute)

        for day in sorted(months[month]):
            done += 1
            f = archive / stats_dataset / "statistics" / f"{day}.dbn.zst"
            if not f.exists():
                missing += len(by_date[day])
                continue
            try:
                stats = read_dbn(f, require_symbols=False)
            except Exception as e:  # noqa: BLE001
                print(f"  {day}: unreadable ({type(e).__name__}: {e})", flush=True)
                missing += len(by_date[day])
                continue

            cons = {label: cleared_by_cutoff(stats, cut) for cut, label in CUTOFFS}
            mini = minute_cumulative(minute, day, set(by_date[day]))

            for sym in by_date[day]:
                row = {"symbol": sym, "date": day}
                any_hit = False
                for _, label in CUTOFFS:
                    c = cons.get(label, {}).get(sym)
                    m = mini.get(sym, {}).get(label)
                    if not c or m is None:
                        continue
                    ratio = m / c
                    # A partial tape cannot exceed the consolidated one. Keep
                    # the row but leave this cutoff empty rather than dropping
                    # the whole symbol-day: one bad cutoff should not remove
                    # six good ones.
                    if ratio <= 1.0:
                        row[label] = ratio
                        any_hit = True
                if any_hit:
                    rows.append(row)
                else:
                    missing += 1

            if tick and (done % tick == 0 or done == total):
                el = (time.time() - t0) / 60
                print(f"  {done:>4}/{total} dates  {len(rows):,} rows  "
                      f"{el:.1f} min elapsed, "
                      f"~{el/done*(total-done):.1f} min left", flush=True)
    return rows, missing, (time.time() - t0) / 60


def render(rows, missing, elapsed_min) -> str:
    L = ["EQUS.MINI CAPTURE THROUGH THE SESSION", "",
         f"  symbol-days with data   {len(rows):,}",
         f"  unmatched               {missing:,}",
         f"  elapsed                 {elapsed_min:.1f} min", ""]
    if not rows:
        L += ["NO ROWS MATCHED. Check that the EQUS.MINI ohlcv-1m archive and",
              "the EQUS.SUMMARY statistics archive cover the same dates."]
        return "\n".join(L)

    L += ["CAPTURE BY CUTOFF  (cumulative from 04:00 ET on both sides)", "",
          f"  {'cutoff':<8} {'n':>7} {'p05':>8} {'p25':>8} {'median':>8} "
          f"{'p75':>8} {'p95':>8}", "  " + "-" * 60]
    meds = {}
    for _, label in CUTOFFS:
        vals = [r[label] for r in rows if r.get(label)]
        if not vals:
            L.append(f"  {label:<8} {0:>7}   (no data)")
            continue
        q = quantiles(vals)
        meds[label] = q[0.5]
        L.append(f"  {label:<8} {len(vals):>7} " + " ".join(
            f"{100*q[x]:>7.1f}%" for x in (0.05, 0.25, 0.5, 0.75, 0.95)))
    L.append("")

    if "09:30" in meds and "20:00" in meds:
        open_, close = meds["09:30"], meds["20:00"]
        L += ["WHAT THIS CHANGES", "",
              f"  median capture at 09:30   {100*open_:.1f}%",
              f"  median capture at 20:00   {100*close:.1f}%",
              f"  ratio                     {open_/close:.2f}x", ""]
        if open_ / close < 0.7:
            L += ["  CAPTURE IS WORSE EARLY. Any rule reading volume-so-far "
                  "before the open",
                  "  is on a THINNER tape than the daily figure implies, so the "
                  "daily-based",
                  "  4.7% understates the error at the decision point. A "
                  "pre-market volume",
                  "  gate is the most affected thing in the screen."]
        elif open_ / close > 1.4:
            L += ["  CAPTURE IS BETTER EARLY. The venues EQUS.MINI misses are "
                  "disproportionately",
                  "  active later in the session, so an early-session rule is "
                  "on firmer ground",
                  "  than the daily figure suggests."]
        else:
            L += ["  ROUGHLY FLAT through the session. The daily-based capture "
                  "figure carries",
                  "  over to intraday decision points, which is the "
                  "convenient outcome: it",
                  "  means capture_ratio's numbers apply where the screen "
                  "actually reads."]
        L.append("")

    L += ["  A cutoff's n is lower than the total wherever the consolidated",
          "  tape had published nothing by that time -- most often at 07:00 on",
          "  a thin name. Those are omitted, not zero-filled: a symbol with no",
          "  pre-market prints has no capture ratio, rather than one of 0%."]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capture at intraday cutoffs")
    ap.add_argument("--pairs", default="var/state/screen_pairs.json")
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--stats-dataset", default="EQUS.SUMMARY")
    ap.add_argument("--mini-dataset", default="EQUS.MINI")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", default="var/reports/capture_intraday.txt")
    ap.add_argument("--csv", default="var/reports/capture_intraday.csv")
    a = ap.parse_args(argv)

    archive = Path(a.archive)
    by_date = load_pairs(Path(a.pairs))
    have = {p.name[: -len(".dbn.zst")]
            for p in (archive / a.stats_dataset / "statistics").glob("*.dbn.zst")}
    by_date = {d: s for d, s in by_date.items() if d in have}
    if a.limit:
        by_date = dict(list(by_date.items())[: a.limit])
    if not by_date:
        sys.exit("no screened dates have a statistics file -- run the "
                 "overnight pull first.")

    print(f"{sum(len(v) for v in by_date.values()):,} symbol-days over "
          f"{len(by_date)} dates, {len(CUTOFFS)} cutoffs", flush=True)
    rows, missing, mins = analyse(archive, by_date, a.stats_dataset,
                                  a.mini_dataset)
    if rows:
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\nper-symbol-day rows written to {out}")

    emit(render(rows, missing, mins), a.report,
         header=f"common.capture_intraday  {a.stats_dataset} vs {a.mini_dataset}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
