#!/usr/bin/env python3
"""Ben's real fills against MCL's rules, on the same symbol-days.

    python -m common.manual_vs_strategy var/flex/*.csv
    python -m common.manual_vs_strategy var/flex/*.csv --csv var/reports/vs.csv

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT
--------------------------------------------------
It does NOT answer "would the algo have beaten me". It cannot: the discretionary
trader picked both the SYMBOL and the MOMENT, while the strategy is handed the
symbol for free and only has to choose the moment. Every symbol-day here was
selected by Ben, so the comparison starts by giving MCL his stock-picking and
then asks whether its execution was better.

The question it does answer is still worth asking, and it is the one a live
decision actually turns on:

    Given that he decided to trade this name on this day, would the rules have
    handled it better than his hands did?

Read it as a test of EXECUTION, not of selection. If MCL loses even with the
picks handed to it, the rules are not rescuing the picks. If it wins, the honest
next question -- which this does not touch -- is whether a scanner could have
produced the same picks without him.

WHY POSITION SIZE IS MATCHED AND NOT ASSUMED
--------------------------------------------
His trades ran from 1 share to 4,000; MCL ships at a flat 100. Comparing dollars
across that gap measures position size, not decisions, and would flatter
whichever side happened to be bigger. So two runs are reported:

    mcl_100      the shipped configuration, flat 100 shares
    mcl_matched  the same rules at HIS peak position for that day

mcl_matched is the like-for-like number. mcl_100 is what the rest of the
project's figures are quoted at, and is kept so this can be read against them.

A SYMBOL-DAY WHERE MCL NEVER TRIGGERS SCORES ZERO, NOT "EXCLUDED"
-----------------------------------------------------------------
Not taking a trade is a decision with a P/L of exactly $0, and on a set where
the human lost money it is frequently the winning one. Dropping those rows would
be the single easiest way to make this report say something false, so the
headline includes them and the traded-only subset is reported separately.

The price band does its own filtering here: ENFORCE_PRICE_BAND means MCL simply
refuses the 174 symbol-days with fills outside $2-20, which lands them in the
zero bucket automatically.
"""
from __future__ import annotations

import argparse
import csv as csvmod
import random
import statistics as st
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from common import flex
from common.analysis import load_sessions, LIVE
from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")


@dataclass
class Row:
    symbol: str
    date: str
    ben_net: float
    ben_execs: int
    ben_max_pos: int
    in_band: bool
    mcl_100: float
    mcl_matched: float
    mcl_trades: int

    @property
    def delta_100(self) -> float:
        return self.mcl_100 - self.ben_net

    @property
    def delta_matched(self) -> float:
        return self.mcl_matched - self.ben_net


def _run_mcl(df, date_str, shares: int | None) -> tuple[float, int]:
    """Shipped MCL on one session. Returns (net, trade count).

    Everything is the live configuration: apex off, MACD>0 on, 5% trail, IBKR
    Tiered commissions, honest gap fills, peak seeded from the entry price.
    Nothing here is swept -- a comparison that tuned the strategy against the
    thing it is being compared to would be worthless.
    """
    from datetime import datetime
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    trades = S.backtest_session(
        df, d, ET,
        trail_pct=S.TRAIL_PCT,
        commission_plan=S.COMMISSION_PLAN,
        entry_shares=shares,
        **LIVE,
    )
    return sum(t.net for t in trades), len(trades)


def build(flex_paths, cache_root: Path) -> tuple[list[Row], dict]:
    execs = flex.load_many(flex_paths)
    flex.measure_offsets(execs)
    days = flex.symbol_days(execs)

    sessions = {(sym, date): df for sym, date, df in load_sessions(cache_root)}

    rows: list[Row] = []
    for key, sd in sorted(days.items()):
        df = sessions.get(key)
        if df is None:
            continue
        n100, c100 = _run_mcl(df, sd.date, None)
        nmat, _ = _run_mcl(df, sd.date, max(1, sd.max_position))
        rows.append(Row(
            symbol=sd.symbol, date=sd.date, ben_net=sd.net_pnl,
            ben_execs=sd.executions, ben_max_pos=sd.max_position,
            in_band=sd.in_band, mcl_100=n100, mcl_matched=nmat,
            mcl_trades=c100,
        ))

    coverage = {
        "flex_symbol_days": len(days),
        "with_bars": len(rows),
        "missing_bars": len(days) - len(rows),
    }
    return rows, coverage


# --------------------------------------------------------------------------

def _drop_top(vals, n):
    return sum(sorted(vals, reverse=True)[n:])


def _bootstrap(by_symbol: dict[str, float], n=10_000, seed=7):
    """Paired by SYMBOL, not by symbol-day.

    Two of Ben's days on the same ticker are not independent draws -- he was
    trading the same story, often the same setup. Resampling symbol-days would
    understate the interval. This is the same convention the rest of the
    project uses.
    """
    keys = list(by_symbol)
    if not keys:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    tot = []
    for _ in range(n):
        s = sum(by_symbol[rng.choice(keys)] for _ in keys)
        tot.append(s)
    tot.sort()
    lo = tot[int(0.025 * n)]
    hi = tot[int(0.975 * n)]
    p = sum(1 for x in tot if x > 0) / n
    return lo, hi, p


def tuning_overlap(rows: list[Row], pair_file="var/state/traded_pairs.json") -> int:
    """How many compared days MCL's parameters were CHOSEN on.

    This is the number that decides whether the comparison means anything.
    Apex-off, TRAIL_PCT=5 and REQUIRE_MACD_POSITIVE were all selected by
    sweeping the pairs in traded_pairs.json. Any day that appears in both sets
    is scored in-sample for MCL and out-of-sample for Ben, which biases the
    difference in MCL's favour by an amount nothing here can measure.
    """
    try:
        import json as _json
        train = {(p["symbol"], p["date"]) for p in _json.load(open(pair_file))}
    except Exception:  # noqa: BLE001
        return -1
    return sum(1 for r in rows if (r.symbol, r.date) in train)


def report(rows: list[Row], coverage: dict) -> str:
    out = []
    A = out.append

    A("COVERAGE")
    A(f"  symbol-days in the trade log      {coverage['flex_symbol_days']:,}")
    A(f"  with bars in the cache            {coverage['with_bars']:,}")
    A(f"  MISSING BARS (not compared)       {coverage['missing_bars']:,}")
    if not rows:
        return "\n".join(out) + "\n\nNothing to compare."

    ben = sum(r.ben_net for r in rows)
    m100 = sum(r.mcl_100 for r in rows)
    mmat = sum(r.mcl_matched for r in rows)
    traded = [r for r in rows if r.mcl_trades]

    ov = tuning_overlap(rows)
    if ov > 0:
        A("")
        A("*** IN-SAMPLE WARNING ***")
        A(f"  {ov} of {len(rows)} compared days ({100*ov/len(rows):.0f}%) are days")
        A("  MCL's parameters were CHOSEN on. Apex-off, the 5% trail and MACD>0")
        A("  were all picked by sweeping these very symbol-days. Ben's fills were")
        A("  not fitted to anything. Every figure below therefore flatters MCL by")
        A("  an unknown amount, and at 100% overlap the comparison is not")
        A("  evidence -- it is the sweep result restated. Fetch bars for the days")
        A("  OUTSIDE traded_pairs.json and re-run before believing any of it.")

    A("")
    A(f"ON THE {len(rows)} SYMBOL-DAYS THAT HAVE BARS")
    A(f"  Ben, actual fills                 ${ben:>12,.2f}")
    A(f"  MCL, flat 100 shares              ${m100:>12,.2f}")
    A(f"  MCL, matched to his position      ${mmat:>12,.2f}   <-- like-for-like")
    A("")
    A(f"  difference (matched - Ben)        ${mmat-ben:>12,.2f}")
    A(f"  MCL took a trade on               {len(traded)} of {len(rows)} days"
      f"  ({100*len(traded)/len(rows):.0f}%)")
    A(f"  MCL stood aside on                {len(rows)-len(traded)} days"
      "  (scored $0, not excluded)")

    A("")
    A("PER SYMBOL-DAY, MATCHED SIZE")
    d = [r.delta_matched for r in rows]
    better = sum(1 for x in d if x > 0)
    A(f"  MCL better on                     {better} of {len(d)}"
      f"  ({100*better/len(d):.0f}%)")
    A(f"  median difference                 ${st.median(d):>12,.2f}")
    A(f"  mean difference                   ${sum(d)/len(d):>12,.2f}")
    for n in (1, 3, 5):
        A(f"  drop-top-{n} on the difference      ${_drop_top(d, n):>12,.2f}")

    by_sym: dict[str, float] = {}
    for r in rows:
        by_sym[r.symbol] = by_sym.get(r.symbol, 0.0) + r.delta_matched
    lo, hi, p = _bootstrap(by_sym)
    A(f"  paired bootstrap over {len(by_sym)} symbols")
    A(f"    95% CI                          [${lo:,.0f}, ${hi:,.0f}]")
    A(f"    P(MCL better than Ben) =        {100*p:.1f}%")

    A("")
    A("SPLIT BY PRICE BAND")
    for label, sel in (("in $2-20", True), ("outside", False)):
        s = [r for r in rows if r.in_band is sel]
        if not s:
            continue
        A(f"  {label:<10} {len(s):>4} days   Ben ${sum(r.ben_net for r in s):>10,.0f}"
          f"   MCL ${sum(r.mcl_matched for r in s):>10,.0f}")
    A("  NOTE: 'outside' means at least ONE of Ben's fills that day was outside")
    A("  $2-20. MCL judges the band on its ENTRY bar, so a name that started at")
    A("  $3 and ran to $25 is 'outside' here and still legitimately traded by")
    A("  MCL. The two labels answer different questions; this is not a band")
    A("  violation.")

    A("")
    A("WHERE MCL ACTUALLY TRADED")
    if traded:
        tb = sum(r.ben_net for r in traded)
        tm = sum(r.mcl_matched for r in traded)
        A(f"  {len(traded)} days   Ben ${tb:,.2f}   MCL ${tm:,.2f}"
          f"   diff ${tm-tb:,.2f}")
        A(f"  Ben's executions on those days: median "
          f"{st.median([r.ben_execs for r in traded]):.0f}"
          f"   MCL's trades: median {st.median([r.mcl_trades for r in traded]):.0f}")

    A("")
    A("TEN LARGEST DIFFERENCES (matched size)")
    for r in sorted(rows, key=lambda r: -abs(r.delta_matched))[:10]:
        A(f"  {r.symbol:<6} {r.date}  Ben ${r.ben_net:>9,.0f}"
          f"   MCL ${r.mcl_matched:>9,.0f}   diff ${r.delta_matched:>9,.0f}"
          f"   (his max {r.ben_max_pos} sh, {r.ben_execs} fills)")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Real fills vs MCL's rules")
    ap.add_argument("csv", nargs="+", help="IBKR Flex trade report(s)")
    ap.add_argument("--cache", default="bar_cache", help="bar cache root")
    ap.add_argument("--csv-out", metavar="OUT.csv", help="write the per-day table")
    a = ap.parse_args(argv)

    rows, cov = build(a.csv, Path(a.cache))
    print(report(rows, cov))

    if a.csv_out:
        Path(a.csv_out).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv_out, "w", newline="") as fh:
            w = csvmod.writer(fh)
            w.writerow(["symbol", "date", "ben_net", "ben_execs", "ben_max_pos",
                        "in_band", "mcl_100", "mcl_matched", "mcl_trades",
                        "delta_matched"])
            for r in rows:
                w.writerow([r.symbol, r.date, round(r.ben_net, 2), r.ben_execs,
                            r.ben_max_pos, int(r.in_band), round(r.mcl_100, 2),
                            round(r.mcl_matched, 2), r.mcl_trades,
                            round(r.delta_matched, 2)])
        print(f"\nwrote {a.csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
