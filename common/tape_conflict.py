#!/usr/bin/env python3
"""Do the 1-minute window slices and the daily bars describe the same tape?

    python -m common.tape_conflict
    python -m common.tape_conflict --sample 60      # fewer sessions, faster

THE DEFECT THIS COUNTS
-----------------------
Three names checked against TradingView by hand on 2026-09-12:

    ACVA  our 09-10 close 10.38   the market's  7.22   +43.8%
    ISPC  our 09-08 pm close 2.11 the day's HIGH 1.94  +8.8%
    TPET  our 09-09 close  1.86   the market's  1.81   +2.8%

TPET is the one that shows why this matters. Every `premarket_change` the
simulated screen computes divides by `prior_close`, so a 2.8% error in the
divisor moved TPET from +20.4% (screens, clears the threshold) to 17.20%
(dropped). Three hand checks establish that the closes CAN be wrong and by how
much. They say nothing about how often, and across 550 sessions "how often" is
the only number that decides whether any screen result stands.

WHY THIS NEEDS NO EXTERNAL SOURCE
----------------------------------
ISPC's failure is visible without TradingView: a premarket print at 2.11 on a
day whose own daily bar tops out at 1.94 is **our two files contradicting each
other**. One of them is wrong and no third party is required to say so.

So the test is an identity that must hold for every symbol-date the archive
carries both ways:

    daily_low <= every premarket print <= daily_high

A daily bar covers the whole session, and Databento's ohlcv-1d aggregates the
same feed the 1-minute bars come from. Pre-market prints are inside the day.
If a print sits outside its own day's range, the two files disagree about that
symbol-date and every figure derived from either is suspect for it.

WHAT A VIOLATION DOES **NOT** IDENTIFY
---------------------------------------
It says the pair disagrees. It does not say which file is wrong, and this
module does not guess -- `screen_miss` and the hand checks point at the daily
bar, but a corrupt minute slice would produce the identical signature. Naming
a culprit here would be an inference dressed as a measurement.

It is also not a measure of agreement with the market. Two files can agree
with each other and both be wrong; the hand-checked ACVA row is exactly that
case if its premarket prints happen to sit inside a wrong daily range. **So a
clean result here does not clear the archive** -- it only bounds this one
detectable class, and the report says so rather than letting a zero read as
"the data is fine".

THE THRESHOLD IS PRE-REGISTERED (2026-09-12), BEFORE THE FIRST RUN
-------------------------------------------------------------------
A print one cent outside a range is a rounding artefact, not a defect, and a
report that counted those would drown the real ones:

    TOLERANCE   0.5% of the daily range, or one cent, whichever is larger.

    < 1% of symbol-days affected    a sporadic data fault; name them, fix
                                    them, the screen results stand.
    1-10%                           material; every screen figure carries it
                                    and must be re-stated after a repair.
    > 10%                           the archive does not support a screen
                                    simulation at all until it is rebuilt.

Bands are read off the affected share of symbol-days, not of sessions: a
session with one bad name is not a bad session.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from common.report_fmt import acct
from common.report_io import emit
from common.screen_sim import date_of, window_slices

TOL_FRAC = 0.005          # of the daily range
TOL_MIN = 0.01            # one cent
SPORADIC, MATERIAL = 0.01, 0.10


def tolerance(hi: float, lo: float) -> float:
    return max(TOL_MIN, TOL_FRAC * max(hi - lo, 0.0))


def conflicts(bars: pd.DataFrame, daily: pd.DataFrame) -> list[dict]:
    """Premarket prints outside their own date's daily range.

    Compared on the minute bars' own high and low, not the close: a print is a
    print whether or not it happened to end a minute, and checking closes only
    would miss a spike that the screen's cumulative volume still counted.
    """
    if bars.empty or daily.empty:
        return []
    g = bars.groupby("symbol").agg(pm_high=("high", "max"),
                                   pm_low=("low", "min"),
                                   bars=("close", "size"))
    d = daily.set_index("symbol")[["high", "low", "close"]]
    j = g.join(d, how="inner", rsuffix="_d")
    if j.empty:
        return []
    out = []
    for sym, r in j.iterrows():
        tol = tolerance(float(r["high"]), float(r["low"]))
        # Rounded to a tenth of a cent BEFORE comparing. Prices are cents, and
        # 1.95 - 1.94 is 0.010000000000000009 in binary floating point, which
        # made a gap of exactly one cent exceed a tolerance of exactly one
        # cent. A threshold that rejects the value it was set to is the same
        # defect class this module is counting.
        over = round(float(r["pm_high"]) - float(r["high"]), 6)
        under = round(float(r["low"]) - float(r["pm_low"]), 6)
        if over <= tol and under <= tol:
            continue
        # The larger breach decides the row's direction, so one row is never
        # counted twice and the worst side is the one reported.
        if over >= under:
            kind, gap, ref = "ABOVE the day's high", over, float(r["high"])
        else:
            kind, gap, ref = "BELOW the day's low", under, float(r["low"])
        out.append({"symbol": sym, "kind": kind, "gap": gap, "ref": ref,
                    "pm_high": float(r["pm_high"]), "pm_low": float(r["pm_low"]),
                    "daily_high": float(r["high"]), "daily_low": float(r["low"]),
                    "daily_close": float(r["close"]), "bars": int(r["bars"]),
                    "pct": (gap / ref * 100.0) if ref else float("nan")})
    return out


def render(rows: list[dict], n_sd: int, n_sessions: int, n_skipped: int,
           elapsed: float) -> list[str]:
    share = (len(rows) / n_sd) if n_sd else 0.0
    L = ["DO THE MINUTE SLICES AND THE DAILY BARS AGREE?", "",
         f"  {n_sd:,} symbol-day(s) carried by BOTH files, over "
         f"{n_sessions} session(s)",
         f"  test: daily_low <= every premarket print <= daily_high",
         f"  tolerance: {TOL_FRAC:.1%} of the daily range, min "
         f"{TOL_MIN:.2f}",
         f"  elapsed {elapsed:.1f}s", ""]
    if n_skipped:
        L += [f"  {n_skipped} session(s) had a slice but no daily bars and "
              "were not tested", ""]

    L += ["RESULT", "",
          f"  {len(rows):,} symbol-day(s) in conflict  "
          f"({acct(share * 100, 6)}% of those testable)", ""]

    if not rows:
        L += ["  No print fell outside its own day's range.", "",
              "  THIS DOES NOT CLEAR THE ARCHIVE. Two files can agree with",
              "  each other and both be wrong, and this test cannot see that.",
              "  ACVA's 09-10 close was wrong by 44% against the market; if",
              "  its premarket prints sat inside that wrong range, this test",
              "  would pass it. A zero here bounds ONE detectable class.", ""]
        return L

    worst = sorted(rows, key=lambda r: -r["pct"])[:20]
    L += ["THE TWENTY WIDEST", "",
          f"  {'date':<12}{'symbol':<8}{'pm high':>9}{'pm low':>9}"
          f"{'day high':>10}{'day low':>9}{'gap':>9}{'gap %':>9}   where"]
    for r in worst:
        L.append(f"  {r['date']:<12}{r['symbol']:<8}{acct(r['pm_high'], 9)}"
                 f"{acct(r['pm_low'], 9)}{acct(r['daily_high'], 10)}"
                 f"{acct(r['daily_low'], 9)}{acct(r['gap'], 9)}"
                 f"{acct(r['pct'], 8)}%   {r['kind']}")

    above = sum(1 for r in rows if r["kind"].startswith("ABOVE"))
    L += ["", "DIRECTION", "",
          f"  {above:,} above the day's high",
          f"  {len(rows) - above:,} below the day's low", "",
          "  A one-sided split is itself evidence. Prints running ABOVE the",
          "  daily high is what a daily bar covering the WRONG DAY looks like",
          "  when the name gapped; a symmetric split looks more like noise in",
          "  either file.", ""]

    band = ("SPORADIC" if share < SPORADIC
            else "MATERIAL" if share < MATERIAL
            else "THE ARCHIVE DOES NOT SUPPORT A SCREEN SIMULATION")
    L += ["VERDICT", "", f"  {share:.2%} of testable symbol-days -> {band}", ""]
    if band == "SPORADIC":
        L += ["  A sporadic data fault. Name them, repair them, and the screen",
              "  results stand once they are re-run.", ""]
    elif band == "MATERIAL":
        L += ["  Every screen figure carries this and must be re-stated after",
              "  a repair -- including the 58% agreement, which was measured",
              "  on these closes.", ""]
    else:
        L += ["  Rebuild before any screen result is quoted again.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a verdict on WHICH file is wrong. The pair disagrees; a",
          "  corrupt minute slice produces the same signature as a wrong",
          "  daily bar, and naming one here would be inference dressed as",
          "  measurement.",
          "",
          "  Not a measure of agreement with the market. Two files can agree",
          "  with each other and both be wrong. The hand-checked ACVA row is",
          "  that case if its prints sit inside a wrong daily range.",
          "",
          "  Not a repair. Nothing here rewrites a bar."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--daily-dataset", default="XNAS.BASIC")
    p.add_argument("--sample", type=int, default=0,
                   help="test only the most recent N sessions (0 = all)")
    p.add_argument("--out", default="var/reports/tape_conflict.txt")
    return p


def main(argv=None) -> int:
    import time
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    from common.dbn_io import daily_frame, read_dbn

    archive = Path(a.archive) if a.archive else default_archive()
    daily = daily_frame(archive, a.daily_dataset)
    if daily.empty:
        sys.exit("the daily archive is empty -- run "
                 "`python -m common.databento_universe --daily` first")
    by_date = {d: g for d, g in daily.groupby("date")}

    slices = window_slices(archive, a.dataset)
    if a.sample:
        slices = slices[-a.sample:]
    if not slices:
        sys.exit("no window slices in the archive")

    t0 = time.time()
    rows, n_sd, skipped = [], 0, 0
    for p in slices:
        day = date_of(p)
        d = by_date.get(day)
        if d is None:
            skipped += 1
            continue
        bars = read_dbn(p)
        if bars.empty:
            continue
        n_sd += bars["symbol"].nunique()
        for r in conflicts(bars, d):
            r["date"] = day
            rows.append(r)

    emit("\n".join(render(rows, n_sd, len(slices) - skipped, skipped,
                          time.time() - t0)),
         a.out, header=f"common.tape_conflict  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
