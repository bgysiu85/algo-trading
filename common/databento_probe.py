#!/usr/bin/env python3
"""Which Databento datasets does this account actually have, and over what dates?

    python -m common.databento_probe
    python -m common.databento_probe --schemas          # also list schemas

WHY THIS IS A SEPARATE TOOL
---------------------------
EQUS.ALL was picked from a catalogue page and it answered every request with
"available end of dataset EQUS.ALL ('1970-01-02')" -- an empty range, which is
what an unentitled or non-existent dataset looks like. That is not an error
about the query; it is the API saying the dataset holds nothing for this
account. Guessing a second name and a third would be the same mistake again.

So: ask the account what it has. list_datasets() is free, get_dataset_range()
is free, and between them they settle which dataset code to use and whether the
history reaches back far enough -- before any query that could cost money.

Same key handling as common.databento_fetch: DATABENTO_API_KEY only, never a
flag, and exceptions are scrubbed before printing.
"""
from __future__ import annotations

import argparse
import sys

from common.databento_fetch import _key, _scrub

# The window this project cares about: Ben's trade history plus a fortnight of
# lookback for the relative-volume denominator.
WANT_START = "2025-05-20"
WANT_END = "2026-09-05"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List available Databento datasets")
    ap.add_argument("--schemas", action="store_true",
                    help="also list each dataset's schemas (slower)")
    ap.add_argument("--filter", default="", help="only datasets containing this")
    a = ap.parse_args(argv)

    try:
        import databento as db
    except ImportError:
        sys.exit("pip install databento")

    c = db.Historical(_key())

    try:
        names = c.metadata.list_datasets()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"list_datasets failed: {_scrub(e)}")

    if a.filter:
        names = [n for n in names if a.filter.upper() in n.upper()]

    print(f"{len(names)} dataset(s) visible to this account\n")
    print(f"{'dataset':<22} {'start':<12} {'end':<12}  covers "
          f"{WANT_START}..{WANT_END}?")
    print("-" * 78)

    usable = []
    for n in sorted(names):
        try:
            r = c.metadata.get_dataset_range(n)
        except Exception as e:  # noqa: BLE001
            print(f"{n:<22} range failed: {_scrub(e)}")
            continue
        start = str(r.get("start", r.get("start_date", "")))[:10]
        end = str(r.get("end", r.get("end_date", "")))[:10]
        ok = bool(start) and start <= WANT_START and end >= WANT_END
        # An empty dataset reports the epoch. Call that out rather than letting
        # it read as a real but short range.
        empty = end <= "1970-01-03"
        mark = "EMPTY" if empty else ("yes" if ok else "partial")
        print(f"{n:<22} {start:<12} {end:<12}  {mark}")
        if ok and not empty:
            usable.append(n)

    print()
    if usable:
        print("USABLE for this project's date range:")
        for n in usable:
            print(f"  {n}")
        print("\nPass one of these as --dataset to common.databento_fetch.")
    else:
        print("No dataset covers the full range. Use the widest 'partial' one "
              "and narrow the date filter, or check the plan's entitlements.")

    if a.schemas:
        print()
        for n in usable or sorted(names):
            try:
                print(f"{n}: {', '.join(c.metadata.list_schemas(n))}")
            except Exception as e:  # noqa: BLE001
                print(f"{n}: schemas failed: {_scrub(e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
