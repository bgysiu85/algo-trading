#!/usr/bin/env python3
"""What is actually inside EQUS.SUMMARY statistics, and is a scoped pull worth it?

    python -m common.statistics_probe --from-pairs var/state/screen_pairs.json
    python -m common.statistics_probe --symbols AAPL TSLA --day 2026-08-04

WHY THIS EXISTS
---------------
The overnight plan wanted EQUS.SUMMARY statistics for the whole universe. Two
independent estimates agree that is ~2.4 TB uncompressed, so it is out of the
default run. But "too big" is not the same as "worthless", and the reason
string that justified it originally claimed the schema carries "consolidated
volume normalised on every trade" -- written from memory, never checked, and
almost certainly wrong.

Standard's L0 tier is free and the subscription is being cancelled this month.
So the question worth answering before it lapses is not "2.4 TB, yes or no" but:

    what is in this schema, and what would it cost SCOPED to the symbol-days a
    strategy would actually trade?

That is a question about kilobytes. This tool asks it.

WHAT IT MEASURES, AND THE ONE NUMBER THAT DECIDES
--------------------------------------------------
Bytes per symbol-day. Everything else follows: the screened universe is ~12,000
symbol-days, so a scoped pull is that figure times 12,000. If it comes out in
the hundreds of MB it is worth taking before the plan ends; if it comes out in
the hundreds of GB it is the universe-wide job wearing a smaller hat.

It also reports which stat_types are present and how often, because a schema
full of MWCB circuit-breaker levels and auction collars is worth much less here
than one carrying official closing prices and cleared volume -- and I am not
going to assert which it is a second time without looking.

DEFENSIVE DECODING, DELIBERATELY
---------------------------------
This is written without ever having seen a statistics record from this dataset.
So it reports the column names it actually got, tolerates missing columns, and
prints raw stat_type integers when the enum does not know them, rather than
assuming a shape and dying halfway. A probe that crashes tells you nothing; a
probe that says "here is what came back, including the parts I did not expect"
tells you everything. The output is the measurement -- not this docstring.

COST
----
Estimated before anything downloads, and refused above --max-cost (default
$0.10). L0 should be $0.0000; the guard is a tripwire for a mis-specified
query, not a budget.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from common.databento_fetch import _key, _scrub
from common.report_io import emit

OUT_DEFAULT = Path("var/probe")
SCREENED_SYMBOL_DAYS = 12_128     # screener_simulation.md: the scoped-pull target


def stat_type_name(value) -> str:
    """Name a stat_type, falling back to the raw integer.

    databento_dbn.StatType is not iterable and its membership changes between
    versions, so this looks up by attribute rather than building a table -- and
    an unknown code is reported as a number rather than dropped. A stat_type
    this build has never heard of is a finding, not an error.
    """
    try:
        from databento_dbn import StatType
    except ImportError:
        return str(value)
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return str(value)
    for attr in dir(StatType):
        if not attr.isupper():
            continue
        try:
            if int(getattr(StatType, attr)) == iv:
                return f"{attr} ({iv})"
        except (TypeError, ValueError):
            continue
    return f"UNKNOWN ({iv})"


def pick_symbols(pairs_file: Path, n: int, *, not_before: str = "",
                 not_after: str = "") -> tuple[str, list[str]]:
    """The busiest screened date INSIDE the dataset's range, and n symbols.

    Sampling real candidates rather than picking liquid names by hand matters:
    MCL trades sub-$20 small caps, and whether an exchange publishes statistics
    for those is exactly the thing in question. AAPL would answer a question
    nobody asked.

    The range filter is not decoration. The screened list starts 2023-03-28,
    from EQUS.MINI; EQUS.SUMMARY only begins 2024-07-01. The busiest day in the
    list is therefore quite likely to be one this dataset has never heard of,
    and the request would fail with a range error that reads like a broken tool
    rather than a mis-chosen day.
    """
    rows = json.load(open(pairs_file))
    if not_before:
        rows = [r for r in rows if r["date"] >= not_before]
    if not_after:
        rows = [r for r in rows if r["date"] <= not_after]
    by_day = Counter(r["date"] for r in rows)
    if not by_day:
        window = f" within {not_before or '-inf'}..{not_after or '+inf'}"
        sys.exit(f"{pairs_file} holds no pairs{window}")
    day, _ = by_day.most_common(1)[0]
    syms = sorted({r["symbol"] for r in rows if r["date"] == day})[:n]
    return day, syms


def dataset_range(client, dataset: str) -> tuple[str, str]:
    """First and last date the account can query. Free metadata call."""
    r = client.metadata.get_dataset_range(dataset)
    start = str(r.get("start", r.get("start_date", "")))[:10]
    end = str(r.get("end", r.get("end_date", "")))[:10]
    return start, end


def estimate_report(dataset: str, schema: str, day: str, symbols,
                    lo: str, hi: str, est: int, usd: float) -> str:
    """What the estimate pass found, as a file rather than as scrollback.

    An estimate that decides whether to download is a measurement, and a
    measurement that exists only in a terminal has to be copied by hand.
    """
    per = est / max(len(symbols), 1)
    return "\n".join([
        "EQUS.SUMMARY STATISTICS -- SCOPED PROBE (ESTIMATE ONLY)", "",
        f"  dataset           {dataset} {schema}",
        f"  dataset covers    {lo} .. {hi}",
        f"  day chosen        {day}",
        f"  symbols           {len(symbols)}  ({', '.join(symbols)})",
        f"  estimated bytes   {est:,}",
        f"  estimated cost    ${usd:.4f}",
        "",
        f"  per symbol-day    {per:,.0f} bytes",
        f"  x {SCREENED_SYMBOL_DAYS:,} screened  "
        f"{per * SCREENED_SYMBOL_DAYS / 1e6:,.1f} MB",
        "",
        "  Billable size is UNCOMPRESSED and is what a scoped pull would be",
        "  charged on. Compare against 2,365,013 MB for the universe-wide job.",
    ])


def summarise(df, day: str, symbols, nbytes: int) -> list[str]:
    """Turn a decoded statistics frame into the report.

    Kept separate from the fetch so it can be tested without a network call or
    an API key -- the arithmetic that decides this (bytes per symbol-day, and
    what that means at 12,128 of them) is the part worth pinning.
    """
    lines = [
        "EQUS.SUMMARY STATISTICS -- SCOPED PROBE", "",
        f"  day               {day}",
        f"  symbols requested {len(symbols)}  ({', '.join(symbols)})",
        f"  bytes on the wire {nbytes:,}",
        f"  records returned  {len(df):,}",
        "",
    ]

    if len(df) == 0:
        lines += [
            "NOTHING CAME BACK.",
            "",
            "  That is a result, not a failure: it means this dataset publishes",
            "  no statistics for these symbols on this day. Before concluding",
            "  the schema is empty for small caps, re-run with --symbols on a",
            "  large-cap name -- if that is also empty the dataset does not",
            "  carry the schema in any useful form, and the 2.4 TB question is",
            "  closed for good.",
        ]
        return lines

    lines += ["  columns returned  " + ", ".join(map(str, df.columns)), ""]

    per_symbol_day = nbytes / max(len(symbols), 1)
    scoped_mb = per_symbol_day * SCREENED_SYMBOL_DAYS / 1e6
    lines += [
        "THE NUMBER THAT DECIDES", "",
        f"  bytes per symbol-day        {per_symbol_day:,.0f}",
        f"  x {SCREENED_SYMBOL_DAYS:,} screened symbol-days  "
        f"{scoped_mb:,.1f} MB",
        "",
        "  Compare against 2,365,013 MB for the universe-wide job. If this is",
        "  in the hundreds of MB it is worth taking before the plan lapses.",
        "",
    ]

    if "stat_type" in df.columns:
        counts = Counter(df["stat_type"])
        lines += ["WHAT IS IN IT", "",
                  f"  {'stat_type':<34} {'records':>9}  {'symbols':>8}"]
        lines.append("  " + "-" * 54)
        for st, n in counts.most_common():
            if "symbol" in df.columns:
                nsym = df.loc[df["stat_type"] == st, "symbol"].nunique()
            else:
                nsym = 0
            lines.append(f"  {stat_type_name(st):<34} {n:>9,}  {nsym:>8}")
    else:
        lines += ["WHAT IS IN IT", "",
                  "  no stat_type column -- report the columns above and decode",
                  "  by hand before drawing any conclusion from this run."]

    if "symbol" in df.columns:
        nsym = df["symbol"].nunique()
        lines += ["", f"  distinct symbols mapped     {nsym} of {len(symbols)}"]
        if nsym == 0:
            lines += [
                "  SYMBOLS DID NOT MAP. Every figure above that is broken down",
                "  by symbol is meaningless -- this is the same failure that",
                "  once produced '864 symbol-days, 0 distinct symbols' and an",
                "  exit code of 0. Do not read the per-symbol columns.",
            ]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="What is inside the statistics schema?")
    ap.add_argument("--dataset", default="EQUS.SUMMARY")
    ap.add_argument("--schema", default="statistics")
    ap.add_argument("--from-pairs", help="sample symbols from a pair list")
    ap.add_argument("--symbols", nargs="+", help="explicit symbols instead")
    ap.add_argument("--n", type=int, default=5, help="how many to sample")
    ap.add_argument("--day", help="the day to pull (default: from the pair list)")
    ap.add_argument("--max-cost", type=float, default=0.10,
                    help="refuse above this; L0 should be $0.0000")
    ap.add_argument("--out", default=str(OUT_DEFAULT),
                    help="where the raw file lands. NOT the archive: a one-off "
                         "probe must not leave an unmanifested day in it")
    ap.add_argument("--report", default="var/reports/statistics_probe.txt")
    ap.add_argument("--confirm", action="store_true",
                    help="actually download; without it this only estimates")
    a = ap.parse_args(argv)

    if not a.from_pairs and not a.symbols:
        sys.exit("give --from-pairs or --symbols")
    if a.symbols and not a.day:
        sys.exit("--symbols needs --day")

    try:
        import databento as db
    except ImportError:
        sys.exit("pip install databento")

    client = db.Historical(_key())

    # Free, and it decides whether the day we are about to ask for exists.
    try:
        lo, hi = dataset_range(client, a.dataset)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"get_dataset_range failed: {_scrub(e)}")
    print(f"{a.dataset} covers {lo} .. {hi}")

    if a.from_pairs:
        day, symbols = pick_symbols(Path(a.from_pairs), a.n,
                                    not_before=lo, not_after=hi)
        if a.day:
            day = a.day
    else:
        symbols, day = a.symbols, a.day

    if not (lo <= day <= hi):
        sys.exit(f"{day} is outside {a.dataset}'s range {lo}..{hi}. "
                 "Pick a day inside it, or drop --day and let the pair list "
                 "choose one.")
    end = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    kw = dict(dataset=a.dataset, schema=a.schema, symbols=symbols,
              stype_in="raw_symbol", start=day, end=end)

    try:
        usd = float(client.metadata.get_cost(**kw))
        est = int(client.metadata.get_billable_size(**kw))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"estimate failed: {_scrub(e)}")

    if usd > a.max_cost:
        emit(estimate_report(a.dataset, a.schema, day, symbols, lo, hi, est, usd)
             + f"\n\nABORTED: ${usd:.4f} exceeds --max-cost ${a.max_cost:.2f}",
             a.report, header="common.statistics_probe -- aborted on cost")
        return 1
    if not a.confirm:
        # The estimate IS a finding: it is the number that decides whether to
        # download at all. The first version printed it and returned, which put
        # it in scrollback -- the same mistake as the size probe, made again in
        # the next tool along.
        emit(estimate_report(a.dataset, a.schema, day, symbols, lo, hi, est, usd)
             + "\n\nDry run. Re-run with --confirm to download.",
             a.report, header="common.statistics_probe -- estimate only")
        return 0
    print(f"{a.dataset} {a.schema}  {day}  {len(symbols)} symbol(s)")
    print(f"  estimated {est:,} bytes, ${usd:.4f}")

    out = Path(a.out) / f"{a.dataset}_{a.schema}_{day}.dbn.zst"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        store = client.timeseries.get_range(**kw)
        store.to_file(str(out))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"download failed: {_scrub(e)}")

    nbytes = out.stat().st_size
    try:
        df = store.to_df()
    except Exception as e:  # noqa: BLE001
        # Decoding is where an unexpected record shape bites, and the bytes are
        # already on disk and paid for. Say what failed and where the file is
        # rather than losing both.
        emit(f"EQUS.SUMMARY STATISTICS -- SCOPED PROBE\n\n"
             f"  downloaded {nbytes:,} bytes to {out}\n"
             f"  DECODE FAILED: {_scrub(e)}\n\n"
             f"  The file is on disk and cost nothing further to keep. Decode it\n"
             f"  by hand before concluding anything about the schema.",
             a.report, header="common.statistics_probe -- decode failed")
        return 1

    emit("\n".join(summarise(df, day, symbols, nbytes)), a.report,
         header=f"common.statistics_probe  {a.dataset} {a.schema}  raw file: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
