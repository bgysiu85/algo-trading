#!/usr/bin/env python3
"""Does the TAPE change the answer? Two caches, the same symbol-days.

    python -m common.tape_compare --a bar_cache_xnas --b bar_cache_db
    python -m common.tape_compare --a bar_cache_xnas --b bar_cache

THE QUESTION, AND WHY IT IS NOW URGENT
---------------------------------------
`PROGRAM_INDEX.md` §7 item 2 has asked for this since 2026-09-08, as an MC5
question. On 2026-09-11 it became an MCL question, which is a different level
of urgent, because two measurements of the same strategy disagree by 10x:

    leak_control, screened universe   2,408 trades   -$1,270   -$0.53/trade
    ladder_study, bar_cache_xnas      4,481 trades  -$23,394   -$5.22/trade

Until that gap is attributed, "should MCL trade at all" has no honest answer,
and every level (as opposed to comparison) measured this week is unsafe to
quote.

WHAT A TAPE IS, AND WHAT TRF MEANS
-----------------------------------
A US equity trades on many venues. An execution on an exchange prints on that
exchange's own feed. An execution OFF exchange -- a dark pool, a wholesaler
internalising retail flow -- does not; it is reported to a FINRA **Trade
Reporting Facility**, and the TRF print carries it onto the consolidated tape.
There are two TRFs, operated with Nasdaq and NYSE.

So a single-exchange feed is a SAMPLE of the tape, and the three caches here
are three different samples (`sizing_and_capacity.md` §3, measured against the
EQUS.SUMMARY consolidated daily bar):

    bar_cache_db    EQUS.MINI      p50 0.048   ~5% of consolidated volume
    bar_cache_xnas  XNAS.BASIC     p50 0.552   Nasdaq executions + Nasdaq's TRF
    bar_cache       IB             p50 0.831   and SPLIT-ADJUSTED

"TRF-inclusive" is not "consolidated": Nasdaq's feed carries Nasdaq's TRF, not
NYSE's, and no ARCA or Cboe prints at all.

THE TWO EFFECTS, WHICH ARE DIFFERENT AND BOTH MEASURED HERE
------------------------------------------------------------
**COVERAGE.** A thinner tape sees fewer prints. Its minute bar has less volume
and a NARROWER high-low range, because an extreme needs a print to make it. A
trailing stop is an intrabar test against the low, so a narrower range means
the trail is hit LESS often and LATER. That is a mechanical bias on every exit.

**TIMING.** TRF prints are reported by the executing broker, not the venue, and
the reporting rules allow a delay. A trade that happened at 07:31:59 can print
at 07:32:04 and land in the NEXT minute's bar. So the two tapes can disagree
about WHICH minute a price extreme belongs to even where they agree it
happened. That moves an entry or an exit by a bar without changing anything
real, and on a 5% trail a bar is enough to change the exit price.

Coverage is measured by the volume and range ratios; timing is measured by the
entry- and exit-time deltas on PAIRED trades.

THE CONFOUND THAT WOULD MAKE THIS MEANINGLESS
----------------------------------------------
**The two caches are not the same universe.** bar_cache_xnas holds 27,776
symbol-days; the screened run covered 21,407. Comparing those two populations
would measure the universe and report it as the tape -- and it would look
exactly like a tape effect.

So everything here runs on the INTERSECTION, matched on (symbol, date), and the
report leads with how many days each cache holds and how many matched. If the
overlap is small there is no comparison to make and the module says so instead
of printing a table.

THE SECOND TRAP, AND IT IS SILENT
----------------------------------
`bar_cache` is IB data and **SPLIT-ADJUSTED**; the Databento caches are RAW. On
any name that split, the two disagree about every price by the split factor --
which is not a tape difference, it is a units difference, and it would swamp
the measurement while looking like an enormous coverage effect.

`split_suspect()` flags a matched symbol-day whose median price ratio sits far
from 1.0, those days are EXCLUDED, and the count is printed. A silent exclusion
would be its own defect, so the number is reported next to the result.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.analysis import LIVE, MEASURED_FRICTION, load_sessions
from common.report_io import emit
from strategy.mcl import mcl as MCL

ET = ZoneInfo("America/New_York")
QTY = 100

# A matched symbol-day whose median close ratio leaves this band is a split or
# a data error, not a tape difference. Wide on purpose: real tape differences
# in the CLOSE of a minute are sub-1%, and anything near a 2:1 or 1:10 split is
# orders of magnitude outside it. The band only has to separate "different
# venues" from "different units".
SPLIT_BAND = (0.90, 1.10)

# Below this many matched symbol-days there is nothing to compare. Set at the
# same place the other studies set their floor: fewer than this and one name
# moves every median.
MIN_MATCHED = 30

# Two trades on the same symbol-day are THE SAME TRADE if their entries sit
# within this many minutes. Wider than a TRF reporting delay (seconds) and
# narrower than a second setup, so a pairing failure means the tapes really did
# take different trades rather than the same one a bar apart.
PAIR_WINDOW_MIN = 15


def index_by_pair(sessions) -> dict:
    return {(s, d): df for s, d, df in sessions}


def aligned(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """The minutes present in BOTH frames, with both sides' columns.

    An inner join on the timestamp. Minutes present in only one tape are
    counted separately rather than filled: a minute with no print is not a
    minute with zero volume, and averaging a fabricated zero into the volume
    ratio would understate the thinner tape's coverage.
    """
    keep = ["open", "high", "low", "close", "volume"]
    return a[keep].join(b[keep], how="inner", lsuffix="_a", rsuffix="_b")


def split_suspect(j: pd.DataFrame) -> bool:
    """Does this symbol-day look like a units mismatch rather than a tape one?"""
    if j.empty:
        return False
    ratio = (j["close_a"] / j["close_b"].replace(0, pd.NA)).dropna()
    if ratio.empty:
        return False
    med = float(ratio.median())
    return not (SPLIT_BAND[0] <= med <= SPLIT_BAND[1])


def bar_stats(j: pd.DataFrame) -> dict | None:
    """Coverage, on one symbol-day's shared minutes."""
    if j.empty:
        return None
    vol_b = j["volume_b"].replace(0, pd.NA)
    vr = (j["volume_a"] / vol_b).dropna()
    # Range as a FRACTION of the close, so the two sides are comparable across
    # a $2 name and a $19 one.
    rng_a = ((j["high_a"] - j["low_a"]) / j["close_a"].replace(0, pd.NA)).dropna()
    rng_b = ((j["high_b"] - j["low_b"]) / j["close_b"].replace(0, pd.NA)).dropna()
    return {
        "minutes": len(j),
        "vol_ratio": float(vr.median()) if len(vr) else float("nan"),
        "range_a": float(rng_a.median()) if len(rng_a) else float("nan"),
        "range_b": float(rng_b.median()) if len(rng_b) else float("nan"),
    }


def run_one(df, date_str) -> list:
    try:
        return MCL.backtest_session(
            df, datetime.strptime(date_str, "%Y-%m-%d").date(), ET,
            entry_shares=QTY, **LIVE)
    except Exception:                                       # noqa: BLE001
        return []


def pair_trades(ta, tb):
    """(paired, a_only, b_only) for one symbol-day.

    Greedy nearest-entry matching inside PAIR_WINDOW_MIN. A trade that finds no
    partner is reported as tape-only rather than dropped -- an unpaired trade is
    the most interesting kind, because it is a trade one tape took and the other
    did not.
    """
    left = list(tb)
    paired, a_only = [], []
    for x in ta:
        tx = pd.Timestamp(x.entry_time)
        best, best_d = None, None
        for y in left:
            d = abs((pd.Timestamp(y.entry_time) - tx).total_seconds()) / 60.0
            if d <= PAIR_WINDOW_MIN and (best_d is None or d < best_d):
                best, best_d = y, d
        if best is None:
            a_only.append(x)
        else:
            left.remove(best)
            paired.append((x, best, best_d))
    return paired, a_only, left


def med(vals):
    return statistics.median(vals) if vals else float("nan")


def net(t) -> float:
    return t.net - MEASURED_FRICTION


def collect(sa, sb):
    ia, ib = index_by_pair(sa), index_by_pair(sb)
    keys = sorted(set(ia) & set(ib))
    out = {
        "n_a": len(ia), "n_b": len(ib), "n_matched": len(keys),
        "splits": 0, "bars": [], "paired": [], "a_only": [], "b_only": [],
        "trades_a": 0, "trades_b": 0, "net_a": 0.0, "net_b": 0.0,
        "days_a": 0, "days_b": 0, "scored": 0,
        "minutes_a_only": 0, "minutes_b_only": 0, "minutes_shared": 0,
    }
    for sym, d in keys:
        a, b = ia[(sym, d)], ib[(sym, d)]
        j = aligned(a, b)
        if split_suspect(j):
            out["splits"] += 1
            continue
        out["scored"] += 1
        out["minutes_shared"] += len(j)
        out["minutes_a_only"] += len(a) - len(j)
        out["minutes_b_only"] += len(b) - len(j)
        bs = bar_stats(j)
        if bs:
            out["bars"].append(bs)

        ta, tb = run_one(a, d), run_one(b, d)
        out["trades_a"] += len(ta)
        out["trades_b"] += len(tb)
        out["net_a"] += sum(net(t) for t in ta)
        out["net_b"] += sum(net(t) for t in tb)
        out["days_a"] += 1 if ta else 0
        out["days_b"] += 1 if tb else 0

        p, ao, bo = pair_trades(ta, tb)
        out["paired"] += [(sym, d, x, y, gap) for x, y, gap in p]
        out["a_only"] += [(sym, d, t) for t in ao]
        out["b_only"] += [(sym, d, t) for t in bo]
    return out


def render(g, name_a, name_b) -> list[str]:
    L = [f"TAPE COMPARISON — {name_a} vs {name_b}", "",
         "  The same symbol-days, run through the same engine, on two tapes.",
         f"  net after tiered commission and ${MEASURED_FRICTION}/RT friction",
         "",
         "UNIVERSE — matched, never the union", "",
         f"  {name_a:<18}{g['n_a']:>9,} symbol-days",
         f"  {name_b:<18}{g['n_b']:>9,} symbol-days",
         f"  {'MATCHED':<18}{g['n_matched']:>9,}",
         f"  {'split/units skew':<18}{g['splits']:>9,}  excluded",
         f"  {'SCORED':<18}{g['scored']:>9,}", ""]

    if g["scored"] < MIN_MATCHED:
        return L + ["NO COMPARISON", "",
                    f"  Under {MIN_MATCHED} matched symbol-days. Whatever the",
                    "  two caches disagree about, it is not measurable here —",
                    "  and a difference between two populations this small",
                    "  would read exactly like a tape effect.", ""]

    vr = [b["vol_ratio"] for b in g["bars"] if b["vol_ratio"] == b["vol_ratio"]]
    ra = [b["range_a"] for b in g["bars"] if b["range_a"] == b["range_a"]]
    rb = [b["range_b"] for b in g["bars"] if b["range_b"] == b["range_b"]]
    L += ["COVERAGE — what the thinner tape does not see", "",
          f"  shared minutes          {g['minutes_shared']:>10,}",
          f"  {name_a} only           {g['minutes_a_only']:>10,}",
          f"  {name_b} only           {g['minutes_b_only']:>10,}",
          f"  volume ratio a/b, median {med(vr):>9.3f}",
          f"  minute range /close, {name_a:<10}{med(ra):>9.4f}",
          f"  minute range /close, {name_b:<10}{med(rb):>9.4f}", ""]
    if med(rb) == med(rb) and med(rb) > 0 and med(ra) == med(ra):
        r = med(ra) / med(rb)
        wider, thinner = (name_a, name_b) if r > 1 else (name_b, name_a)
        L += [f"  {name_a}'s median minute range is {r:.2f}x {name_b}'s.",
              "",
              "  A trailing stop is an intrabar test against the low, so the",
              f"  tape with the WIDER range ({wider}) trips it sooner. Note",
              "  the direction is measured, not assumed: a tape can be thinner",
              "  overall and still have wider bars, because the minutes it",
              "  misses entirely are the QUIET ones and the ones it keeps are",
              "  the active ones. Compare the minutes-only-on-one-side counts",
              "  above before reading the range as coverage.", ""]
    elif med(rb) == 0.0:
        L += [f"  {name_b}'s MEDIAN MINUTE HAS NO RANGE AT ALL — high equals",
              "  low. That is a tape thin enough that a typical minute is a",
              "  single print, and every intrabar rule, the trail included, is",
              "  running against a degenerate bar rather than a range.", ""]

    pa = g["net_a"] / g["trades_a"] if g["trades_a"] else 0.0
    pb = g["net_b"] / g["trades_b"] if g["trades_b"] else 0.0
    L += ["THE STRATEGY, on the matched days", "",
          f"  {'tape':<18}{'trades':>8}{'days traded':>13}{'net':>11}{'per':>8}",
          f"  {name_a:<18}{g['trades_a']:>8}{g['days_a']:>13}"
          f"${g['net_a']:>10,.0f}${pa:>7.2f}",
          f"  {name_b:<18}{g['trades_b']:>8}{g['days_b']:>13}"
          f"${g['net_b']:>10,.0f}${pb:>7.2f}", ""]

    n_p, n_a, n_b = len(g["paired"]), len(g["a_only"]), len(g["b_only"])
    total = n_p + n_a + n_b
    L += ["TRADE BY TRADE — did the two tapes take the same trades?", "",
          f"  {f'paired (within {PAIR_WINDOW_MIN} min)':<24}{n_p:>6}"
          f"   {100.0 * n_p / total if total else 0:>5.1f}%",
          f"  {name_a + ' only':<24}{n_a:>6}"
          f"   {100.0 * n_a / total if total else 0:>5.1f}%",
          f"  {name_b + ' only':<24}{n_b:>6}"
          f"   {100.0 * n_b / total if total else 0:>5.1f}%", ""]

    agree = None
    if n_p:
        gaps = [gap for _, _, _, _, gap in g["paired"]]
        dnet = [net(x) - net(y) for _, _, x, y, _ in g["paired"]]
        dbars = [x.bars_held - y.bars_held for _, _, x, y, _ in g["paired"]]
        same = sum(1 for _, _, x, y, _ in g["paired"] if x.reason == y.reason)
        # A MEDIAN OF ZERO CANNOT TELL "all identical" FROM "large offsetting
        # differences". The first version printed only medians, and on the
        # xnas-vs-IB run that read as perfect agreement on trades that had
        # never been checked for spread. Mean and a tail share, always.
        mean_d = sum(dnet) / n_p
        differ = sum(1 for d in dnet if abs(d) > 1.0)
        agree = (differ / n_p < 0.10 and abs(mean_d) < 1.0
                 and same / n_p > 0.95)
        L += ["  ON THE PAIRED TRADES — same setup, two tapes", "",
              f"    entry gap, median            {med(gaps):>8.1f} min",
              f"    same exit reason             {100.0 * same / n_p:>8.1f}%",
              f"    bars held, median a - b      {med(dbars):>8.1f}",
              f"    net per trade, median a - b  ${med(dnet):>7.2f}",
              f"    net per trade, MEAN a - b    ${mean_d:>7.2f}",
              f"    differ by over $1            "
              f"{100.0 * differ / n_p:>8.1f}%", ""]
        if med(gaps) > 1.0:
            L += ["    THE ENTRIES DO NOT LINE UP. A median gap over a minute",
                  "    is not a reporting delay — the two tapes are arming on",
                  "    different bars, and every downstream difference follows",
                  "    from that rather than from the exit.", ""]

    L += ["WHAT THIS DECIDES", ""]
    if total and n_p / total < 0.5:
        L += ["  FEWER THAN HALF THE TRADES PAIR. The two tapes are not running",
              "  the same strategy on the same days — they are selecting",
              "  different trades. A per-trade P/L measured on one of them does",
              "  not describe the other, and the 10x gap between the screened",
              "  and xnas runs is a TAPE artefact rather than a property of",
              "  MCL.", ""]
    elif abs(pa - pb) > 2.0 and agree:
        # THE MISATTRIBUTION THE FIRST RUN MADE. xnas-vs-IB printed "that is
        # the EXITS" directly beneath a paired block showing a $0.00 median
        # delta, 100% the same exit reason and a 0.0-bar difference. The
        # paired trades ended IDENTICALLY; the whole gap came from the 98 and
        # 93 trades the two tapes did not share. Attributing to the exits
        # there was a plausible sentence about the wrong mechanism.
        L += [f"  The per-trade result differs by ${abs(pa - pb):.2f}, and the",
              "  trades the two tapes SHARE end identically — see the paired",
              "  block above. So this is not the exits. It is SELECTION: the",
              f"  {n_a + n_b} trades only one tape took are carrying the whole",
              "  difference, and which tape you hold decides which trades the",
              "  strategy takes at all.", ""]
    elif abs(pa - pb) > 2.0:
        L += [f"  The trades largely pair, and the per-trade result still",
              f"  differs by ${abs(pa - pb):.2f}. The paired trades also differ,",
              "  so this is the EXITS: the same entries, held on two tapes,",
              "  ending differently. Read the coverage block.", ""]
    else:
        L += ["  The two tapes agree, on the matched days, to within $2 a",
              "  trade. Whatever separates the screened run from the xnas run,",
              "  it is NOT the tape — look at the universe and the date range",
              "  instead.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  Not a statement about which tape is right. IBKR fills against the",
          "  consolidated tape, so neither cache here is what the live path",
          "  sees; the IB cache is closest at a measured 0.831.",
          "",
          "  Not an impact model, and not a fill model. Two tapes disagreeing",
          "  about a minute's low says the backtest's exit price is uncertain",
          "  by that much; it does not say what a real order would have got.",
          "",
          "  Not a correction. Nothing here rescales anything — the ratios are",
          "  printed and the arithmetic is left to the reader, the same rule",
          "  `sizing_and_capacity.md` §3 applies to capacity."]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--a", default="bar_cache_xnas")
    p.add_argument("--b", default="bar_cache_db")
    p.add_argument("--out", default="var/reports/tape_compare.txt")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.a == a.b:
        sys.exit("--a and --b are the same cache; there is nothing to compare")
    sa = load_sessions(Path(a.a))
    sb = load_sessions(Path(a.b))
    g = collect(sa, sb)
    emit("\n".join(render(g, a.a, a.b)), a.out,
         header=f"common.tape_compare  a={a.a}  b={a.b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
