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
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from common.databento_fetch import _key, _scrub, require_databento
from common.report_io import emit

ET = ZoneInfo("America/New_York")

# The window this project cares about: Ben's trade history plus a fortnight of
# lookback for the relative-volume denominator.
WANT_START = "2025-05-20"
WANT_END = "2026-09-05"


def day_bounds(day: str, window: str | None = None) -> tuple[str, str]:
    """The [start, end) a size query should ask about.

    `window` is "HH:MM-HH:MM" in ET. It exists for the screener simulation,
    which needs only the PRE-MARKET slice -- 04:00 to the moment the screen
    runs. Pricing a whole day would overstate that by better than an order of
    magnitude and could talk us out of a pull we can comfortably afford.

    ET, not UTC, because every session boundary in this project is stated in ET
    and converting by hand is how a DST week ends up an hour out.
    """
    if not window:
        return day, (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    a, _, b = window.partition("-")
    if not b:
        sys.exit(f"--window {window!r} needs the form HH:MM-HH:MM, "
                 "e.g. 04:00-04:30")
    d = date.fromisoformat(day)

    def stamp(hhmm: str) -> str:
        h, _, m = hhmm.partition(":")
        return (datetime(d.year, d.month, d.day, int(h), int(m or 0),
                         tzinfo=ET)
                .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))

    return stamp(a), stamp(b)


def size_one_day(client, dataset: str, schema: str, day: str,
                 window: str | None = None) -> tuple[float, float]:
    """Billable MB and USD for one day, or one intraday window, of a
    dataset/schema. Metadata only -- get_billable_size and get_cost are both
    free, which is the whole point of asking before pulling."""
    start, end = day_bounds(day, window)
    kw = dict(dataset=dataset, schema=schema, symbols="ALL_SYMBOLS",
              stype_in="raw_symbol", start=start, end=end)
    mb = int(client.metadata.get_billable_size(**kw)) / 1e6
    usd = float(client.metadata.get_cost(**kw))
    return mb, usd


def parse_size_args(items) -> list[tuple[str, str]]:
    out = []
    for s in items:
        ds, sep, sc = s.partition(":")
        if not sep or not ds or not sc:
            sys.exit(f"--size {s!r} needs the form DATASET:SCHEMA, "
                     "e.g. EQUS.SUMMARY:statistics")
        out.append((ds.upper(), sc))
    return out


def probe_sizes(client, day: str, pairs, out=None,
                window: str | None = None) -> int:
    """Price one day of each dataset/schema, so a plan total can be checked.

    A whole-plan estimate is one number per job with nothing to compare it
    against. The overnight plan put EQUS.SUMMARY statistics at 2.4 TB -- 97.7%
    of everything -- and there is no way to tell an enormous-but-real schema
    from a bad estimate without a second measurement at a different scale.
    A single day is free to ask about and settles it.

    The result goes to a file as well as the terminal. The first version only
    printed, which put the figure this decision turns on in scrollback where it
    had to be copied back by hand -- the exact thing report_io exists to stop.
    """
    span = f"{day} {window} ET" if window else f"{day}, whole day"
    unit = "MB/win" if window else "MB/day"
    lines = [f"ONE-DAY SIZE PROBE  ({span}, whole universe, billable)", "",
             f"{'dataset / schema':<30} {unit:>12} {'USD':>10}"
             f"  {'x21 -> MB/month':>16}",
             "-" * 74]
    for dataset, schema in pairs:
        label = f"{dataset} {schema}"
        try:
            mb, usd = size_one_day(client, dataset, schema, day, window)
        except Exception as e:  # noqa: BLE001
            lines.append(f"{label:<30} FAILED: {_scrub(e)}")
            continue
        lines.append(f"{label:<30} {mb:>12,.1f} {usd:>10.4f} {mb*21:>16,.0f}")
    lines += ["",
              "Compare the month column against the same job in the overnight",
              "plan. A large disagreement means one of the two estimates is",
              "wrong, and neither should be acted on until that is settled."]
    emit("\n".join(lines), out,
         header=f"common.databento_probe --size  day={day}"
                + (f" window={window} ET" if window else ""))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List available Databento datasets")
    ap.add_argument("--schemas", action="store_true",
                    help="also list each dataset's schemas (slower)")
    ap.add_argument("--filter", default="", help="only datasets containing this")
    ap.add_argument("--size", nargs="+", metavar="DATASET:SCHEMA",
                    help="instead of listing, price ONE day of each of these")
    ap.add_argument("--window", default=None,
                    help="HH:MM-HH:MM in ET, e.g. 04:00-04:30. Prices only "
                         "that slice of the day -- what the screener "
                         "simulation actually needs")
    ap.add_argument("--day", default="2026-08-04",
                    help="the day --size prices (default: %(default)s)")
    ap.add_argument("--out", default="var/reports/databento_size_probe.txt",
                    help="where --size writes its report (default: %(default)s)")
    a = ap.parse_args(argv)

    db = require_databento()

    c = db.Historical(_key())

    if a.size:
        return probe_sizes(c, a.day, parse_size_args(a.size), a.out, a.window)

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
