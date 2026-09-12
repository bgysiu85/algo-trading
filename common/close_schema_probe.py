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
from common.report_io import emit

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
    p.add_argument("--out", default="var/reports/close_schema_probe.txt",
                   help="every other module in this project writes its result "
                        "to a file; this one printed to the terminal and cost "
                        "a round trip getting the output back.")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import _key, _scrub, require_databento

    db = require_databento()
    client = db.Historical(_key())

    L = ["WHICH SCHEMAS COULD ANSWER THE CLOSE QUESTION?", "",
         f"  {a.dataset}   {a.start} -> {a.end}",
         "  nothing is downloaded by this module", ""]
    try:
        have = sorted(client.metadata.list_schemas(dataset=a.dataset))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"could not list schemas: {_scrub(e)}")

    L += ["SCHEMAS THIS DATASET OFFERS", ""]
    for name in have:
        note = WANT.get(name, "")
        star = " <-" if name in WANT else "   "
        L.append(f"  {name:<14}{star} {note}")

    L += ["", "THE ONES THAT COULD ANSWER THE CLOSE QUESTION", ""]
    hits = [x for x in ("ohlcv-eod", "statistics", "trades") if x in have]
    if not hits:
        L += ["  none of ohlcv-eod / statistics / trades is available here.",
              "  The minute reconstruction is the only route on this dataset."]
        emit("\n".join(L), a.out, header=f"common.close_schema_probe  "
                                        f"dataset={a.dataset}")
        return 0

    # Price each candidate over the SAME range, so the comparison is a
    # comparison. A daily schema is priced whole-day; the intraday ones only
    # over the window, which is how they would actually be pulled.
    L.append(f"  {'schema':<14}{'billable':>12}{'cost':>10}   "
             "how it would be pulled")
    for name in hits:
        kw = dict(dataset=a.dataset, schema=name, symbols="ALL_SYMBOLS",
                  stype_in="raw_symbol", start=a.start, end=a.end)
        try:
            c = float(client.metadata.get_cost(**kw))
            b = int(client.metadata.get_billable_size(**kw))
        except Exception as e:  # noqa: BLE001
            L.append(f"  {name:<14}{'ESTIMATE FAILED':>22}   {_scrub(e)}")
            continue
        L.append(f"  {name:<14}{b / 1e6:>10.1f} MB{c:>10.4f}   whole days")

    L += ["", "WHAT TO DO WITH THIS", ""]
    if "ohlcv-eod" in have:
        L += ["  ohlcv-eod exists. Pull it for these sessions and score it",
              "  against the same truth table BEFORE pulling trades:", "",
              f"    python -m common.databento_universe "
              f"--dataset {a.dataset} \\",
              f"        --schema ohlcv-eod --start {a.start} --end {a.end}",
              f"    python -m common.regular_close "
              f"--dataset {a.dataset} --eod", "",
              "  If its close reproduces the truth rows, the repair is a",
              "  DAILY pull over 552 sessions rather than ~2 GB of minutes,",
              "  and prior_closes() changes by one schema name.", ""]
    if "statistics" in have:
        L += ["  statistics exists and carries UNCROSSING_PRICE, which is the",
              "  auction print itself. Second choice only because it needs a",
              "  stat-type filter, and ohlcv-eod -- if correct -- needs",
              "  nothing at all.", ""]
    L += ["  NEITHER IS VALIDATED BY BEING AVAILABLE. A schema called",
          "  `ohlcv-eod` may still aggregate the extended session -- that is",
          "  exactly the mistake ohlcv-1d already made, and it is the whole",
          "  defect under repair. Score it before trusting it."]
    emit("\n".join(L), a.out,
         header=f"common.close_schema_probe  dataset={a.dataset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
