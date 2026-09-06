#!/usr/bin/env python3
"""What Ben's fills actually cost, measured against the quote at the time.

    python -m common.friction_quotes var/flex/*.csv
    python -m common.friction_quotes var/flex/*.csv --csv-out var/reports/fills.csv

WHY THIS IS THE HIGHEST-VALUE MEASUREMENT AVAILABLE
----------------------------------------------------
PROGRAM_INDEX section 7 item 1: re-measuring friction is the top open item in
the project, and it has been stuck because there are TWO measured trailing-stop
exits. Everything downstream rests on estimates taken from a session that was
81% apex exits, for a configuration that now produces ~95% trailing exits --
"the estimate answers a question the strategy no longer asks."

The tbbo archive changes that. tbbo is every trade with the prevailing bid and
ask attached, so for all 559 symbol-days Ben traded there is a quote at the
instant of each of his 18,621 fills. That turns three separate assumptions into
measurements:

  * LIMIT_CROSS_BPS = 20, and the 37-43 bps effective cross derived from it
  * the buy/sell asymmetry, currently resting on one session
  * and the one that matters most -- what a software-managed stop would really
    have filled at in pre-market, which is the fiction underneath MCL's entire
    measured edge

HOW A FILL IS PRICED
--------------------
For each execution: take the last tbbo record for that symbol at or before the
fill timestamp, and read its bid and ask. That is the prevailing quote as the
tape saw it. Then, with adverse always POSITIVE, matching the convention
already used in this project:

    BUY   slip_vs_touch = fill - ask      (paid above the offer)
    SELL  slip_vs_touch = bid  - fill     (sold below the bid)
    both  slip_vs_mid   = |fill - mid| signed the same way

A negative number is price improvement, and it is real: 2026-09-03's
measurement had buys favourable at -$0.0164/share.

FOUR THINGS THAT WOULD MAKE THIS WRONG, AND WHAT IS DONE ABOUT EACH
--------------------------------------------------------------------
1. TIMESTAMP PRECISION. Flex stamps to the second in the account's report
   timezone; tbbo is nanosecond UTC. A fill is matched to the last quote at or
   before its second, and matches older than --tolerance (default 60s) are
   dropped rather than used. A stale quote is worse than no quote: it produces
   a slippage figure that looks precise and measures nothing.

2. EQUS.MINI IS A PARTIAL, ANONYMISED TAPE. Its BBO is Databento's blend of
   component venues, NOT the NBBO. Ben's fills went to ARCA, NASDAQ, DARK,
   DRCTEDGE, MEMX, PEARL and IBKRATS; some of those venues are not in MINI at
   all. So the measured spread is a good estimate and not the official one, and
   a fill can legitimately print outside this BBO without anything being wrong.
   Reported as a caveat on every run, not buried here.

3. HIS FILLS ARE NOT MCL'S. These are discretionary, hotkey-driven orders --
   OrderReference says "Hotkey" -- at his chosen moments. They bound what is
   achievable on this universe at these hours; they do not measure what MCL's
   marketable limits would get. That distinction has to survive into whatever
   quotes this number.

4. DEGRADED DAYS. Four days in the archive are flagged degraded by Databento.
   Fills on those days are counted separately and excluded from the headline.

WHAT THIS DOES NOT DO
---------------------
It does not model a stop fill. Section 5 reports the pre-market spread
distribution, which is the input to that question, but turning it into a fill
model is a separate job with its own assumptions.
"""
from __future__ import annotations

import argparse
import csv as csvmod
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common import flex
from common.dbn_io import read_dbn
from common.report_io import emit

ARCHIVE_DEFAULT = "databento"
DATASET_DEFAULT = "EQUS.MINI"
ET = ZoneInfo("America/New_York")


def fills_frame(execs, zone: str) -> pd.DataFrame:
    """Executions as a UTC-stamped frame. Rows with no usable time are dropped."""
    rows = []
    for e in execs:
        if not e.time_known:
            continue
        ts = e.dt_raw.replace(tzinfo=ZoneInfo(zone)).astimezone(ZoneInfo("UTC"))
        rows.append((e.symbol, e.trade_date, pd.Timestamp(ts), e.side,
                     abs(e.price), abs(e.qty), e.commission, e.et_minute))
    df = pd.DataFrame(rows, columns=["symbol", "date", "ts", "side", "price",
                                     "qty", "commission", "et_minute"])
    return df.sort_values("ts").reset_index(drop=True)


def quotes_for_date(archive: Path, dataset: str, date: str,
                    schema: str = "tbbo") -> pd.DataFrame:
    """The trade-with-quote records archived under this date's file.

    `schema` exists because the cross-check needs a different one. EQUS.MINI
    serves `tbbo`; XNAS.BASIC does not -- it publishes the CONSOLIDATED
    variants (cmbp-1, cbbo, tcbbo) and has no plain tbbo, because it carries
    quotes for Nasdaq only while its trades come from Nasdaq, PSX, BX and the
    FINRA TRFs. `tcbbo` is its equivalent record.

    The file is named for the symbol-day it was fetched for but SPANS the
    lookback window, so it holds several sessions. Nothing here filters by
    date: the asof match on timestamp is what selects, and filtering first
    would throw away the quotes immediately before an early fill.
    """
    p = archive / dataset / schema / f"{date}.dbn.zst"
    if not p.exists():
        return pd.DataFrame()
    df = read_dbn(p)
    if df.empty:
        return df
    out = df.reset_index()
    tcol = "ts_recv" if "ts_recv" in out.columns else "ts_event"
    keep = [tcol, "symbol", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00"]
    missing = [c for c in keep if c not in out.columns]
    if missing:
        raise ValueError(
            f"{p.name}: {schema} is missing {missing}. Columns present: "
            f"{sorted(out.columns)}. A schema whose quote columns are named "
            "differently needs mapping here rather than silently yielding no "
            "quotes.")
    out = out[keep].rename(columns={tcol: "ts", "bid_px_00": "bid",
                                    "ask_px_00": "ask", "bid_sz_00": "bid_sz",
                                    "ask_sz_00": "ask_sz"})
    out = out[(out["bid"] > 0) & (out["ask"] > 0) & (out["ask"] >= out["bid"])]
    return out.sort_values("ts").reset_index(drop=True)


def match(fills: pd.DataFrame, quotes: pd.DataFrame,
          tolerance_s: int = 60) -> pd.DataFrame:
    """Attach the last quote at or before each fill, per symbol.

    merge_asof with by="symbol" and direction="backward" is exactly the
    semantics wanted: the prevailing quote. The tolerance matters more than it
    looks -- on a thin pre-market name the previous trade can be twenty minutes
    old, and pricing a fill against a twenty-minute-old quote produces a number
    that is precise and meaningless.
    """
    if fills.empty or quotes.empty:
        return pd.DataFrame()
    # merge_asof refuses to join datetime64[us] against datetime64[ns] --
    # "incompatible merge keys". Flex times come from datetime objects and land
    # at microsecond resolution; DBN timestamps are nanosecond. Both are
    # correct and they will not merge, so normalise here rather than in one
    # caller and not another.
    f = fills.sort_values("ts").copy()
    q = quotes.sort_values("ts").copy()
    f["ts"] = f["ts"].astype("datetime64[ns, UTC]")
    q["ts"] = q["ts"].astype("datetime64[ns, UTC]")
    m = pd.merge_asof(
        f, q, on="ts", by="symbol", direction="backward",
        tolerance=pd.Timedelta(seconds=tolerance_s))
    m = m[m["bid"].notna()].copy()
    if m.empty:
        return m
    m["mid"] = (m["bid"] + m["ask"]) / 2.0
    m["spread"] = m["ask"] - m["bid"]
    m["spread_bps"] = m["spread"] / m["mid"] * 10_000
    buy = m["side"] == "BUY"
    # Adverse positive, both sides.
    m["slip_touch"] = pd.Series(
        [(p - a) if b else (bd - p)
         for p, a, bd, b in zip(m["price"], m["ask"], m["bid"], buy)],
        index=m.index)
    m["slip_mid"] = pd.Series(
        [(p - mi) if b else (mi - p)
         for p, mi, b in zip(m["price"], m["mid"], buy)], index=m.index)
    m["slip_mid_bps"] = m["slip_mid"] / m["mid"] * 10_000
    m["block"] = m["et_minute"].map(flex.block)
    return m


def build(flex_paths, archive: Path, dataset: str, tolerance_s: int,
          schema: str = "tbbo"):
    execs = flex.load_many(flex_paths)
    tz = flex.measure_offsets(execs)
    fills = fills_frame(execs, tz["chosen"])

    matched, per_date = [], {}
    for date, grp in fills.groupby("date"):
        q = quotes_for_date(archive, dataset, date, schema)
        if q.empty:
            per_date[date] = (len(grp), 0)
            continue
        m = match(grp, q, tolerance_s)
        per_date[date] = (len(grp), len(m))
        if not m.empty:
            matched.append(m)

    out = (pd.concat(matched).reset_index(drop=True) if matched
           else pd.DataFrame())
    return out, fills, per_date, tz


def _stats(s: pd.Series) -> str:
    s = s.dropna()
    if s.empty:
        return "no data"
    return (f"n {len(s):>6,}   median {s.median():>9.4f}   "
            f"mean {s.mean():>9.4f}   p90 {s.quantile(.9):>9.4f}")


def report(m: pd.DataFrame, fills: pd.DataFrame, per_date, tz, dataset: str) -> str:
    out, A = [], None
    out = []
    A = out.append

    tot = sum(v[0] for v in per_date.values())
    got = sum(v[1] for v in per_date.values())
    nodata = [d for d, v in per_date.items() if v[1] == 0]

    A("1. COVERAGE")
    A(f"  executions with a usable timestamp   {len(fills):,}")
    A(f"  priced against a quote               {got:,}  "
      f"({100*got/max(tot,1):.0f}%)")
    A(f"  dates with no quotes archived        {len(nodata)}")
    if nodata:
        A(f"    {', '.join(sorted(nodata)[:8])}"
          + (" ..." if len(nodata) > 8 else ""))
    A(f"  report timezone                      {tz['chosen']}")
    if m.empty:
        return "\n".join(out) + "\n\nNothing matched -- no quotes for these fills."

    A("")
    A("2. THE SPREAD HE WAS TRADING INTO")
    A(f"  spread, $/share    {_stats(m['spread'])}")
    A(f"  spread, bps        {_stats(m['spread_bps'])}")
    A("")
    A("  by session block:")
    for b in ("PRE", "RTH", "POST"):
        s = m[m["block"] == b]
        if s.empty:
            continue
        A(f"    {b:<5} n {len(s):>6,}   median spread "
          f"{s['spread'].median():>8.4f}  ({s['spread_bps'].median():>7.1f} bps)")

    A("")
    A("3. SLIPPAGE, ADVERSE POSITIVE")
    A("  vs the touch (buy: fill-ask, sell: bid-fill)")
    for side in ("BUY", "SELL"):
        s = m[m["side"] == side]
        A(f"    {side:<5} {_stats(s['slip_touch'])}")
    A("  vs the midpoint")
    for side in ("BUY", "SELL"):
        s = m[m["side"] == side]
        A(f"    {side:<5} {_stats(s['slip_mid'])}")
    A("  vs the midpoint, bps")
    for side in ("BUY", "SELL"):
        s = m[m["side"] == side]
        A(f"    {side:<5} {_stats(s['slip_mid_bps'])}")

    A("")
    A("4. AGAINST WHAT THE BACKTESTS ASSUME")
    med = m["slip_mid_bps"].median()
    A(f"  measured cross vs mid, median        {med:.1f} bps")
    A( "  trader.py LIMIT_CROSS_BPS            20.0 bps")
    A( "  documented effective cross           37-43 bps")
    A( "  (half-spread is the like-for-like comparison for a marketable limit:"
       f" median {m['spread_bps'].median()/2:.1f} bps)")

    A("")
    A("5. PRE-MARKET, WHICH IS WHERE THE FICTION IS")
    pre = m[m["block"] == "PRE"]
    if not pre.empty:
        A(f"  fills            {len(pre):,}")
        A(f"  spread bps       {_stats(pre['spread_bps'])}")
        A(f"  slip vs mid bps  {_stats(pre['slip_mid_bps'])}")
        A("  Outside RTH, IBKR takes Day Limit orders only -- every stop is")
        A("  software-managed and filled with a marketable limit. The spread")
        A("  above is what that limit has to cross. It is NOT yet a fill model.")

    A("")
    A("6. CAVEATS THAT TRAVEL WITH THESE NUMBERS")
    A(f"  * {dataset} is a partial, anonymised tape. Its BBO is Databento's")
    A("    blend of component venues, not the NBBO. Ben's fills went to ARCA,")
    A("    NASDAQ, DARK, DRCTEDGE, MEMX, PEARL and IBKRATS, and not all of")
    A("    those are in it. A fill can print outside this BBO legitimately.")
    A("  * These are DISCRETIONARY hotkey orders at his chosen moments. They")
    A("    bound what is achievable on this universe at these hours; they do")
    A("    not measure what MCL's marketable limits would get.")
    A("  * Flex stamps to the second, tbbo to the nanosecond. Each fill takes")
    A("    the last quote at or before its second, and stale matches beyond")
    A("    the tolerance are dropped rather than used.")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Price real fills against the quote")
    ap.add_argument("csv", nargs="+", help="IBKR Flex trade report(s)")
    ap.add_argument("--archive", default=ARCHIVE_DEFAULT)
    ap.add_argument("--dataset", default=DATASET_DEFAULT)
    ap.add_argument("--schema", default="tbbo",
                    help="tbbo for EQUS.MINI, tcbbo for XNAS.BASIC")
    ap.add_argument("--tolerance", type=int, default=60,
                    help="max seconds between quote and fill (default 60)")
    ap.add_argument("--csv-out", metavar="OUT.csv",
                    help="write the per-fill table")
    ap.add_argument("--out", metavar="OUT.txt", default=None,
                    help="default: var/reports/friction_<dataset>_<schema>.txt")
    a = ap.parse_args(argv)

    out = a.out or (f"var/reports/friction_{a.dataset.replace('.', '_')}"
                    f"_{a.schema}.txt")
    m, fills, per_date, tz = build(a.csv, Path(a.archive), a.dataset,
                                   a.tolerance, a.schema)
    emit(report(m, fills, per_date, tz, a.dataset), out,
         header=f"common.friction_quotes  dataset={a.dataset}"
                f"  schema={a.schema}  tolerance={a.tolerance}s")

    if a.csv_out and not m.empty:
        Path(a.csv_out).parent.mkdir(parents=True, exist_ok=True)
        m.to_csv(a.csv_out, index=False)
        print(f"wrote {a.csv_out}  ({len(m):,} priced fills)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
