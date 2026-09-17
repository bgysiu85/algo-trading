#!/usr/bin/env python3
"""Price the TSMOM futures pull. ESTIMATE ONLY -- this module cannot spend.

    set DATABENTO_API_KEY=...        (PowerShell: $env:DATABENTO_API_KEY="...")

    python -m common.tsmom_data_price                 # the registered set
    python -m common.tsmom_data_price --with-tn       # + TN, for rates arm (b)
    python -m common.tsmom_data_price --roots ES GC   # a scoped re-price

WHY THIS IS A SEPARATE MODULE FROM common.databento_fetch
----------------------------------------------------------
`databento_fetch` is shaped for equities: it takes a list of (symbol, date)
pairs, groups them BY DATE, and writes one archive file per day. That is the
right shape for 6,564 symbol-days scattered across a year of pre-market windows.

It is the wrong shape for futures. A TSMOM pull is a dozen ROOTS over sixteen
years of continuous daily bars -- twelve range requests, not four thousand
day requests -- and it is symbol-scoped through the `parent` symbology
(`ES.FUT` resolves to every ES contract month) rather than through an explicit
ticker list. Forcing it through the day-grouping path would issue ~4,000
requests to build twelve files and would make the estimate meaningless.

THIS MODULE HAS NO DOWNLOAD PATH. NOT A GUARDED ONE.
-----------------------------------------------------
`PROGRAM_INDEX` section 1: a tool that can spend money states the number before
it spends it. `databento_fetch` satisfies that with an estimate plus --confirm.
This module goes further and satisfies it structurally: it imports
`metadata.get_cost` and `metadata.get_billable_size` and nothing else. There is
no `timeseries.get_range` call anywhere in the file, so there is no flag, typo
or merge that makes it spend. When the number has been confirmed, the pull is
written as its own module under its own registration.

--max-cost (default $5) still aborts, because an estimate that comes back large
is itself a signal that the request is mis-scoped -- which is how the $1,500
ALL_SYMBOLS quote was caught -- and printing it calmly next to a total invites
someone to run the pull anyway.

THE KEY IS NEVER AN ARGUMENT AND IS NEVER PRINTED
--------------------------------------------------
Read from DATABENTO_API_KEY only. A --key flag would put it in PowerShell
history. Client exceptions are scrubbed before they are shown, because a
Telegram token once leaked out of an exception handler in common/notify.py.

WHAT THE ANSWER IS EXPECTED TO BE, AND WHY IT IS STILL RUN
-----------------------------------------------------------
`ohlcv-1d`, `definition` and `statistics` are L0 schemas, and the $199/month
Standard plan includes 16+ years of L0. So this pull is expected to price at or
near $0.00, the way the XNAS.BASIC extension through 2026-09-17 did. "Expected"
is not a number, `get_cost()` is the only thing that knows Ben's plan, and the
key lives only on his machine -- so the estimate is run there and the figure is
what gets registered.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date

DATASET = "GLBX.MDP3"

# The instrument set of claude/tsmom_spec_20260917.md section 2.2 -- the FULL-SIZE
# roots. Signals are computed on these; the micros in the comments are the
# execution vehicle only, and most of them did not exist before 2019.
#
# NB: "MCL" in claude/diversifier_candidates_20260911.md section 5.1 means the
# micro crude oil future. In this project MCL is a strategy. Crude is CL here and
# in every TSMOM doc -- see handover section 2.1.
ROOTS: dict[str, str] = {
    "ES": "US large-cap equity      -> MES",
    "RTY": "US small-cap equity      -> M2K",
    "GC": "precious metal           -> MGC",
    "SI": "second precious metal    -> SIL",
    "HG": "base metal               -> MHG",
    "CL": "crude                    -> MCL",
    "NG": "natural gas              -> MNG",
    "6E": "EUR                      -> M6E",
    "6A": "AUD                      -> M6A",
    "6B": "GBP                      -> M6B",
    "6J": "JPY                      -> MJY",
    "ZN": "10-year rates            -> ZN full size (no price-quoted micro)",
}

# Rates arm (b) of spec section 2.3: signal from TN's own history, traded as MTN.
# Off by default -- arm (a) needs only ZN, which is already in ROOTS.
TN_ROOT = {"TN": "Ultra 10-year            -> MTN (arm (b) only)"}

SCHEMAS = ("ohlcv-1d", "definition")


def _scrub(text: str) -> str:
    """Remove anything that looks like a key from text before it is printed."""
    key = os.environ.get("DATABENTO_API_KEY") or ""
    out = str(text)
    if key:
        out = out.replace(key, "<DATABENTO_API_KEY>")
    return re.sub(r"\bdb-[A-Za-z0-9]{20,}\b", "<DATABENTO_API_KEY>", out)


def _key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise SystemExit(
            "DATABENTO_API_KEY is not set.\n"
            "  PowerShell:  $env:DATABENTO_API_KEY=\"db-...\"\n"
            "The key is read from the environment only -- never a command-line\n"
            "flag, which would put it in shell history (PROGRAM_INDEX section 1)."
        )
    return key


def require_databento():
    try:
        import databento  # noqa: F401
    except ImportError:
        raise SystemExit(
            "the databento package is not importable by THIS interpreter:\n"
            f"  {sys.executable}\n"
            "On Windows that is usually the system Python rather than the venv --\n"
            "a terminal can show (.venv) while `python` resolves elsewhere. Use:\n"
            "  D:\\Trading\\.venv\\Scripts\\python.exe -m common.tsmom_data_price"
        )
    import databento
    return databento


def available_range(client) -> tuple[str, str]:
    """The dataset's full history, asked for rather than assumed.

    GLBX.MDP3's start date is a fact about the vendor, not about this project,
    and hard-coding it would be a second source of truth that goes stale in
    silence (PROGRAM_INDEX section 4).
    """
    rng = client.metadata.get_dataset_range(dataset=DATASET)
    start = rng.get("start") or rng.get("start_date")
    end = rng.get("end") or rng.get("end_date")
    return str(start)[:10], str(end)[:10]


def price_one(client, root: str, schema: str, start: str, end: str):
    """Cost and billable size for one root, all contract months, one schema.

    `parent` symbology: "ES.FUT" resolves to every ES futures contract month,
    which is what a back-adjusted continuous series and a definition-driven roll
    calendar both need. An explicit expiry list would have to be maintained and
    would silently miss months.
    """
    kw = dict(dataset=DATASET, schema=schema, symbols=f"{root}.FUT",
              stype_in="parent", start=start, end=end)
    usd = float(client.metadata.get_cost(**kw))
    nbytes = int(client.metadata.get_billable_size(**kw))
    return usd, nbytes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Estimate the cost of the TSMOM futures pull. Cannot download.")
    ap.add_argument("--roots", nargs="+", metavar="ROOT",
                    help="price only these roots (default: the registered set)")
    ap.add_argument("--with-tn", action="store_true",
                    help="include TN (rates arm (b) of spec section 2.3)")
    ap.add_argument("--schemas", nargs="+", default=list(SCHEMAS))
    ap.add_argument("--start", help="override the start date (default: dataset start)")
    ap.add_argument("--end", help="override the end date (default: today)")
    ap.add_argument("--max-cost", type=float, default=5.0,
                    help="abort above this total, in USD (default 5.00)")
    a = ap.parse_args(argv)

    roots = dict(ROOTS)
    if a.with_tn:
        roots.update(TN_ROOT)
    if a.roots:
        unknown = [r for r in a.roots if r not in roots]
        if unknown:
            raise SystemExit(f"not in the registered set: {' '.join(unknown)}\n"
                             f"known: {' '.join(roots)}")
        roots = {r: roots[r] for r in a.roots}

    databento = require_databento()
    client = databento.Historical(_key())

    try:
        ds_start, ds_end = available_range(client)
    except Exception as e:                       # noqa: BLE001
        raise SystemExit(f"dataset range lookup failed: {_scrub(e)}")
    start = a.start or ds_start
    end = a.end or min(ds_end, date.today().isoformat())

    print(f"ESTIMATE ONLY -- this module has no download path.\n")
    print(f"dataset   {DATASET}")
    print(f"history   {ds_start} .. {ds_end}   (vendor's stated range)")
    print(f"pricing   {start} .. {end}")
    print(f"schemas   {' '.join(a.schemas)}")
    print(f"roots     {len(roots)}   symbology: parent (<ROOT>.FUT = all contract months)\n")

    width = max(len(s) for s in a.schemas)
    print(f"{'root':<6}{'schema':<{width + 2}}{'billable':>14}{'USD':>10}   note")
    total_usd, total_bytes = 0.0, 0
    failures = []
    for root, note in roots.items():
        for schema in a.schemas:
            try:
                usd, nbytes = price_one(client, root, schema, start, end)
            except Exception as e:               # noqa: BLE001
                failures.append((root, schema, _scrub(e)))
                print(f"{root:<6}{schema:<{width + 2}}{'FAILED':>14}{'':>10}   {_scrub(e)[:60]}")
                continue
            total_usd += usd
            total_bytes += nbytes
            shown = note if schema == a.schemas[0] else ""
            print(f"{root:<6}{schema:<{width + 2}}{nbytes:>14,}{usd:>10.2f}   {shown}")

    print(f"\n{'TOTAL':<6}{'':<{width + 2}}{total_bytes:>14,}{total_usd:>10.2f}"
          f"   ({total_bytes / 2**30:.3f} GiB uncompressed)")

    if failures:
        print(f"\n{len(failures)} lookup(s) FAILED -- the total above is a LOWER BOUND,")
        print("not the cost of the pull. Do not confirm a spend against it.")

    if total_usd > a.max_cost:
        print(f"\nABORT: ${total_usd:.2f} exceeds --max-cost ${a.max_cost:.2f}.")
        print("A large estimate usually means the request is mis-scoped, not that")
        print("the data is expensive -- the same range once priced at $1,500 with")
        print("symbols=ALL_SYMBOLS and under a cent scoped properly. Check the")
        print("roots and the date range before raising the ceiling.")
        return 2

    print("\nNothing has been downloaded and nothing has been charged.")
    print("Send this total to the TSMOM chat. The pull is written as its own")
    print("module, under its own registration, only after Ben confirms it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
