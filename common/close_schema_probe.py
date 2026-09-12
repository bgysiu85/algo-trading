#!/usr/bin/env python3
"""Does this dataset already publish the official close, so we need not rebuild it?

    python -m common.close_schema_probe
    python -m common.close_schema_probe --dataset EQUS.MINI

WHY THIS COMES BEFORE THE TRADES PROBE
---------------------------------------
The agreed next step was to pull the `trades` schema around 16:00 and pick out
the closing cross by its trade condition, because minute OHLCV cannot tell a
cross from any other print. That reasoning is sound and it skipped a question:
**is the official close already published as its own field?**

Databento's schema list includes two that would answer directly:

    ohlcv-eod     an END-OF-DAY bar, which is not the same object as ohlcv-1d.
                  If its close is the regular-session close, the repair is a
                  one-schema swap -- a DAILY-sized pull, not 2 GB of minutes,
                  and it drops straight into prior_closes() with no
                  reconstruction and no cross-detection at all.

    statistics    carries StatType.CLOSE_PRICE and StatType.UNCROSSING_PRICE.
                  An uncrossing price IS the auction print, published as a
                  number rather than inferred from a bar.

Either would be both cheaper and more exact than reconstructing from trades, so
spending the trades pull without checking costs money to get a worse answer.

WHAT THIS DOES AND DOES NOT DO
-------------------------------
It asks the API which schemas the dataset offers and prices the candidate pulls.
It does NOT download anything and it does NOT decide that a schema is correct:
a schema named `ohlcv-eod` might still aggregate the extended session, and the
only thing that settles that is scoring it against the truth table in
`regular_close`. This narrows what to pull. It does not validate what comes back.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

WANT = {
    "ohlcv-eod": "an end-of-day bar distinct from ohlcv-1d -- if its close is "
                 "the REGULAR close this is a daily-sized pull and the whole "
                 "minute reconstruction is unnecessary",
    "statistics": "carries CLOSE_PRICE and UNCROSSING_PRICE -- the auction "
                  "print as a published number rather than an inference",
    "trades": "every print, with conditions. The fallback, and the most "
              "expensive of the three",
    "ohlcv-1m": "what we already pulled; listed so the comparison is visible",
    "ohlcv-1d": "what prior_closes() reads today, and what is wrong",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--start", default="2026-09-08")
    p.add_argument("--end", default="2026-09-12")
    p.add_argument("--window", default="15:55-16:05",
                   help="only used to price the intraday candidates")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import _key, _scrub, require_databento

    db = require_databento()
    client = db.Historical(_key())

    print(f"{a.dataset}   {a.start} -> {a.end}\n")
    try:
        have = sorted(client.metadata.list_schemas(dataset=a.dataset))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"could not list schemas: {_scrub(e)}")

    print("SCHEMAS THIS DATASET OFFERS\n")
    for s in have:
        note = WANT.get(s, "")
        star = " <-" if s in WANT else "   "
        print(f"  {s:<14}{star} {note}")

    print("\nTHE ONES THAT COULD ANSWER THE CLOSE QUESTION\n")
    hits = [s for s in ("ohlcv-eod", "statistics", "trades") if s in have]
    if not hits:
        print("  none of ohlcv-eod / statistics / trades is available here.")
        print("  The minute reconstruction is the only route on this dataset.")
        return 0

    # Price each candidate over the SAME range, so the comparison is a
    # comparison. A daily schema is priced whole-day; the intraday ones only
    # over the window, which is how they would actually be pulled.
    print(f"  {'schema':<14}{'billable':>12}{'cost':>10}   how it would be pulled")
    for s in hits:
        kw = dict(dataset=a.dataset, schema=s, symbols="ALL_SYMBOLS",
                  stype_in="raw_symbol", start=a.start, end=a.end)
        how = "whole days"
        try:
            c = float(client.metadata.get_cost(**kw))
            b = int(client.metadata.get_billable_size(**kw))
        except Exception as e:  # noqa: BLE001
            print(f"  {s:<14}{'ESTIMATE FAILED':>22}   {_scrub(e)}")
            continue
        print(f"  {s:<14}{b / 1e6:>10.1f} MB{c:>10.4f}   {how}")

    print("\nWHAT TO DO WITH THIS\n")
    if "ohlcv-eod" in have:
        print("  ohlcv-eod exists. Pull it for these five sessions and score it")
        print("  against the same truth table BEFORE pulling trades:\n")
        print(f"    python -m common.databento_universe --dataset {a.dataset} \\")
        print(f"        --schema ohlcv-eod --start {a.start} --end {a.end}")
        print(f"    python -m common.regular_close --dataset {a.dataset} --eod\n")
        print("  If its close reproduces the truth rows, the repair is a")
        print("  DAILY pull over 552 sessions rather than ~2 GB of minutes,")
        print("  and prior_closes() changes by one schema name.\n")
    if "statistics" in have:
        print("  statistics exists and carries UNCROSSING_PRICE, which is the")
        print("  auction print itself. Second choice only because it needs a")
        print("  stat-type filter and ohlcv-eod, if correct, needs nothing.\n")
    print("  NEITHER IS VALIDATED BY BEING AVAILABLE. A schema called")
    print("  `ohlcv-eod` may still aggregate the extended session -- that is")
    print("  exactly the mistake ohlcv-1d already made. Score it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
