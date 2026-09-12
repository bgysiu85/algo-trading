#!/usr/bin/env python3
"""Is `prior_close` the previous regular close, or the wrong row?

    python -m common.prior_close_check
    python -m common.prior_close_check --names 2026-09-11:ACVA,2026-09-10:RML

THE LEAD THIS CHASES
---------------------
`screen_miss` found 15 of 16 missed names failing the CHANGE clause, and four of
them failing it in a way no threshold explains:

    2026-09-11  ACVA     0.76%   on 23,007,608 shares
    2026-09-10  RML      0.00%
    2026-09-10  IRD     (1.27)%
    2026-09-09  WYHG    (4.28)%

Every one of these was on a PREMARKET GAINERS watchlist -- names up 20% or more
-- and the tape is plainly not blind to them. So the numerator is not the
suspect:

    premarket_change = (premarket_close / prior_close - 1) * 100

RML at exactly 0.00% is the tell. A change of precisely zero is what comes out
when the "prior" close and the current print are THE SAME BAR.

WHAT THIS MODULE REFUSES TO DO
-------------------------------
It does not decide that the alignment is wrong. `daily_frame` derives `date`
from the UTC stamp deliberately -- daily bars are stamped at UTC midnight and
converting to ET would move a session backwards -- and that reasoning may well
be right. A module that set out to confirm a hypothesis it had already named
would find it.

So this prints the evidence and lets the rows answer:

  1. The daily closes AROUND the date, so the shape of the series is visible.
  2. Which of those rows `prior_closes()` actually selected.
  3. The premarket tape's own first and last print on the target date, from a
     DIFFERENT file (the 04:00-09:30 window slice) than the daily bar.
  4. **Which baseline would have to be true** for the live screen's >= 20%
     claim to hold -- computed against every nearby daily close. If one row
     consistently satisfies it and it is not the row in use, the offset is
     named by the data rather than by me. If NO row satisfies it, the defect is
     not an offset at all and the `prior_close` hypothesis is dead too.

(4) is the part that can falsify the hypothesis, which is why it is here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit
from common.screen_at import ScreenConfig
from common.screen_sim import date_of, prior_closes, window_slices

# The four from `screen_miss.txt`, 2026-09-12. Explicit rather than re-derived:
# this is a named lead about named rows, and re-running the miss detection here
# would couple a correctness check to the thing it is checking.
DEFAULT_NAMES = [("2026-09-11", "ACVA"), ("2026-09-10", "RML"),
                 ("2026-09-10", "IRD"), ("2026-09-09", "WYHG"),
                 ("2026-09-09", "RML"), ("2026-09-10", "BIAF")]

AROUND = 4          # daily rows either side of the target date
LIVE_CLAIM = 20.0   # what being on the watchlist asserts


def parse_names(spec: str) -> list[tuple[str, str]]:
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            sys.exit(f"--names wants date:SYMBOL pairs, got {part!r}")
        d, s = part.split(":", 1)
        out.append((d.strip(), s.strip().upper()))
    return out


def tape_prints(path: Path, symbol: str) -> dict:
    """First and last premarket print for one symbol, from the window slice."""
    from common.dbn_io import read_dbn
    bars = read_dbn(path)
    rows = bars[bars["symbol"] == symbol] if not bars.empty else bars
    if rows.empty:
        return {}
    rows = rows.sort_index(kind="mergesort")
    return {"first": float(rows["close"].iloc[0]),
            "last": float(rows["close"].iloc[-1]),
            "high": float(rows["high"].max()) if "high" in rows else float("nan"),
            "bars": int(len(rows))}


def examine(daily: pd.DataFrame, pc: pd.DataFrame, slices: dict[str, Path],
            date: str, symbol: str) -> dict:
    sym = daily[daily["symbol"] == symbol].sort_values("date")
    rec: dict = {"date": date, "symbol": symbol, "rows": [], "used": None,
                 "tape": {}, "satisfies": []}
    if sym.empty:
        rec["note"] = "no daily bars for this symbol at all"
        return rec

    dates = list(sym["date"])
    if date in dates:
        i = dates.index(date)
        lo, hi = max(0, i - AROUND), min(len(dates), i + AROUND + 1)
    else:
        # The target date has no daily row -- itself a finding, and the window
        # around it is taken from where it WOULD have sat.
        rec["note"] = "no daily row on the target date"
        after = [j for j, d in enumerate(dates) if d > date]
        i = after[0] if after else len(dates) - 1
        lo, hi = max(0, i - AROUND), min(len(dates), i + AROUND + 1)

    rec["rows"] = [{"date": r.date, "close": float(r.close),
                    "high": float(getattr(r, "high", float("nan"))),
                    "low": float(getattr(r, "low", float("nan"))),
                    "volume": float(getattr(r, "volume", float("nan"))),
                    "target": r.date == date}
                   for r in sym.iloc[lo:hi].itertuples()]

    hit = pc[(pc["symbol"] == symbol) & (pc["date"] == date)]
    if not hit.empty:
        rec["used"] = float(hit["prior_close"].iloc[0])

    path = slices.get(date)
    if path is not None:
        rec["tape"] = tape_prints(path, symbol)

    # (4) Which baseline would make the live claim true? Measured against the
    # tape's own HIGH, the most generous premarket print available -- if even
    # that cannot reach +20% off a row, no entry rule could have.
    peak = rec["tape"].get("high")
    if peak is not None and peak == peak:
        for r in rec["rows"]:
            if r["close"] > 0:
                ch = (peak / r["close"] - 1.0) * 100.0
                r["change_from"] = ch
                if ch >= LIVE_CLAIM:
                    rec["satisfies"].append(r["date"])
    return rec


def render(recs: list[dict], cfg: ScreenConfig) -> list[str]:
    L = ["IS `prior_close` THE PREVIOUS REGULAR CLOSE?", "",
         f"  {len(recs)} name(s) the live screen surfaced and the simulation",
         f"  scored below +{cfg.change_min:.0f}% -- four of them at or below zero.",
         "",
         "  premarket_change = (premarket_close / prior_close - 1) * 100",
         "  A baseline is 'consistent' if the tape's own premarket HIGH clears",
         f"  +{LIVE_CLAIM:.0f}% off it, which is what the watchlist asserts.", ""]

    for r in recs:
        L += ["", f"{r['symbol']}  {r['date']}", ""]
        if r.get("note"):
            L.append(f"  NOTE: {r['note']}")
        t = r["tape"]
        if t:
            L.append(f"  premarket tape: {t['bars']:,} bars, first "
                     f"{acct(t['first'], 1).strip()}, high "
                     f"{acct(t['high'], 1).strip()}, last "
                     f"{acct(t['last'], 1).strip()}")
        else:
            L.append("  premarket tape: no bars in the window slice")
        used = r["used"]
        L.append(f"  prior_close in use: "
                 f"{'none -- dropped before any clause' if used is None else acct(used, 1).strip()}")
        L += ["", f"    {'daily date':<14}{'high':>9}{'low':>9}{'close':>10}"
                   f"{'off high':>11}   ",
              ]
        for row in r["rows"]:
            ch = row.get("change_from")
            mark = []
            if row["target"]:
                mark.append("<- TARGET DATE's own bar")
            if used is not None and abs(row["close"] - used) < 1e-9:
                mark.append("<- THE ROW IN USE")
            if ch is not None and ch >= LIVE_CLAIM:
                mark.append(f"consistent with +{LIVE_CLAIM:.0f}%")
            chs = acct(ch, 10) + "%" if ch is not None else f"{'-':>11}"
            hi = (acct(row["high"], 9) if row.get("high") == row.get("high")
                  else f"{'-':>9}")
            lo_ = (acct(row["low"], 9) if row.get("low") == row.get("low")
                   else f"{'-':>9}")
            L.append(f"    {row['date']:<14}{hi}{lo_}{acct(row['close'], 10)}"
                     f"{chs}   " + "  ".join(mark))

        if not r["satisfies"]:
            L += ["", "    NO nearby daily close makes the live claim true. An",
                  "    offset does not explain this name."]
        elif used is not None and r["satisfies"] == [
                next((x["date"] for x in r["rows"]
                      if abs(x["close"] - used) < 1e-9), None)]:
            L += ["", "    The row in use is the only consistent one. This name",
                  "    does not support the offset hypothesis."]
        else:
            L += ["", "    Consistent baseline(s): " + ", ".join(r["satisfies"])]

    L += ["", "", "THE DAILY RANGE IS PRINTED FOR ONE REASON", "",
          "  `tape_conflict` found ZERO contradictions between the minute",
          "  slices and the daily bars over 3,406,462 symbol-days. Our two",
          "  files agree with each other and disagree with the market, which",
          "  rules out a corrupt file and leaves one source being wrong the",
          "  same way everywhere.",
          "",
          "  The candidate: Databento's ohlcv-1d aggregates the WHOLE feed,",
          "  so its close is the last print of the extended day (20:00 ET),",
          "  while TradingView's premarket_change divides by the official",
          "  16:00 REGULAR close. A name that runs after hours then carries",
          "  an inflated prior_close here, which DEFLATES its computed",
          "  premarket change -- one-directionally, which is exactly the 16",
          "  missed against 2 sim-only that `screen_validate` found.",
          "",
          "  THE ROW THAT DECIDES IT is ACVA 2026-09-10. The market traded",
          "  o 7.36 h 7.39 l 7.00 c 7.22 that session. If the bar below",
          "  shows a HIGH near 10.46 -- a level the regular session never",
          "  reached -- our daily bar covers hours TradingView's does not,",
          "  and the defect is named. If it shows h 7.39, the bar is simply",
          "  wrong and this is a different problem.", "",
          "HOW TO READ THIS", "",
          "  If the consistent baseline is the SAME row for every name and it",
          "  is not the row in use, the offset is named and the fix is a",
          "  correctness fix -- no pre-registration, because it is not a",
          "  threshold change.",
          "",
          "  If the consistent rows disagree with each other, or there are",
          "  none, `prior_close` is NOT the defect and the CHANGE failures",
          "  have another cause. That outcome retires this lead.",
          "",
          "WHAT THIS IS NOT", "",
          "  Not a correction. Nothing here rewrites a baseline.",
          "",
          "  Not TradingView's arithmetic. Their premarket_change is computed",
          "  on their consolidation from their own prior close; agreement here",
          "  would be evidence, not proof, and disagreement likewise.",
          "",
          "  The premarket HIGH is used as the most generous numerator",
          "  available. It is NOT what the screen uses -- the screen reads the",
          "  last close at each tick. A baseline this test calls inconsistent",
          "  is therefore inconsistent under any tick the screen could have",
          "  taken; one it calls consistent may still not have screened."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC")
    p.add_argument("--names", default=None,
                   help="comma-separated date:SYMBOL, e.g. 2026-09-11:ACVA")
    p.add_argument("--out", default="var/reports/prior_close_check.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame

    archive = Path(a.archive) if a.archive else default_archive()
    names = parse_names(a.names) if a.names else DEFAULT_NAMES

    daily = daily_frame(archive, a.daily_dataset)
    if daily.empty:
        sys.exit("the daily archive is empty -- run "
                 "`python -m common.databento_universe --daily` first")
    pc = prior_closes(daily)
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}

    recs = [examine(daily, pc, slices, d, s) for d, s in names]
    emit("\n".join(render(recs, ScreenConfig())), a.out,
         header=f"common.prior_close_check  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
