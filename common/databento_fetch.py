#!/usr/bin/env python3
"""Pull symbol-days from Databento into a permanent local archive.

    set DATABENTO_API_KEY=...            (PowerShell: $env:DATABENTO_API_KEY="...")

    python -m common.databento_fetch --pairs var/state/flex_pairs_all.json \
        --before 2025-09-06 --schemas tbbo ohlcv-1m           # estimate only
    python -m common.databento_fetch ... --confirm            # actually spend

    python -m common.databento_fetch --pairs var/state/flex_pairs_all.json \
        --missing-from-cache --schemas ohlcv-1m --confirm

WHY AN ARCHIVE AND NOT A CACHE
-------------------------------
Databento bills on RETRIEVAL. Once a file is on disk it is free to read forever,
and the plan's history depth stops mattering for it. That distinction is not
academic: Standard carries only ONE YEAR of L1 (trades, tbbo, bbo, mbp-1) and
the window ROLLS. Ben's trade history starts 2025-06-04, so the quotes for his
earliest sessions are already outside it and everything else is on a clock.
Data captured while it is in-plan stays usable after it leaves; data not
captured has to be bought back at a price that is not obviously affordable.

So this writes to a durable archive that is never garbage-collected, and it
SKIPS anything already on disk. Re-running it is free by construction. The
bar_cache/ tree remains a derived artefact; this is the source of truth.

SPENDING GUARDS, BECAUSE THE FIRST QUOTE WAS OFF BY FIVE ORDERS OF MAGNITUDE
----------------------------------------------------------------------------
The same date range priced at over $1,500 with symbols="ALL_SYMBOLS" and under
one cent scoped to the two tickers actually wanted. A tool that can spend money
on a mis-specified query needs to say the number before it spends it, so:

  * every run estimates first and prints the total,
  * nothing is downloaded without --confirm,
  * and --max-cost (default $5) aborts rather than proceeding, so a typo in a
    symbol list fails closed instead of expensively.

THE KEY IS NEVER AN ARGUMENT AND IS NEVER PRINTED
--------------------------------------------------
Read from DATABENTO_API_KEY only. PROGRAM_INDEX section 1: API keys never appear
in chat. They also should not appear in shell history, which a --key flag would
guarantee. Errors from the client are scrubbed for the same reason a token once
leaked out of common/notify.py's exception handler.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ARCHIVE_DEFAULT = Path("databento")
CACHE_DEFAULT = Path("bar_cache/3d_to_2000")

# Warm-up matters: MCL needs two sessions ending 09:30, so a symbol-day cannot
# be fetched as a single calendar day. Pull a window that comfortably covers
# the superset the cache is built from and let the slicing happen downstream.
LOOKBACK_DAYS = 5


def _scrub(text: str) -> str:
    """Never let a key reach a log, however it got into an exception."""
    return re.sub(r"(db-)?[A-Za-z0-9]{20,}", "<redacted>", str(text))


def _key() -> str:
    k = os.environ.get("DATABENTO_API_KEY", "").strip()
    if not k:
        sys.exit("DATABENTO_API_KEY is not set. In PowerShell:\n"
                 '  $env:DATABENTO_API_KEY = "your key"')
    return k


def load_pairs(path: Path) -> list[tuple[str, str]]:
    data = json.load(open(path))
    return sorted({(p["symbol"], p["date"]) for p in data})


def filter_pairs(pairs, *, before=None, after=None, missing_from_cache=None):
    out = list(pairs)
    if before:
        out = [p for p in out if p[1] < before]
    if after:
        out = [p for p in out if p[1] >= after]
    if missing_from_cache is not None:
        have = {f.name[: -len(".csv.gz")]
                for f in Path(missing_from_cache).glob("*.csv.gz")}
        out = [p for p in out if f"{p[0]}_{p[1]}" not in have]
    return out


def group_by_date(pairs) -> dict[str, list[str]]:
    g: dict[str, list[str]] = defaultdict(list)
    for sym, d in pairs:
        g[d].append(sym)
    return {d: sorted(set(s)) for d, s in sorted(g.items())}


def archive_path(root: Path, dataset: str, schema: str, day: str) -> Path:
    return root / dataset / schema / f"{day}.dbn.zst"


def plan(client, groups, dataset, schemas, root, lookback):
    """Estimate every request. Returns (jobs, total_usd, total_bytes)."""
    jobs, usd, nbytes = [], 0.0, 0
    for day, syms in groups.items():
        start = (date.fromisoformat(day) - timedelta(days=lookback)).isoformat()
        end = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        for schema in schemas:
            out = archive_path(root, dataset, schema, day)
            if out.exists():
                jobs.append((day, syms, schema, start, end, out, 0.0, 0, True))
                continue
            kw = dict(dataset=dataset, schema=schema, symbols=syms,
                      stype_in="raw_symbol", start=start, end=end)
            try:
                c = float(client.metadata.get_cost(**kw))
                b = int(client.metadata.get_billable_size(**kw))
            except Exception as e:  # noqa: BLE001
                print(f"  {day} {schema:9} ESTIMATE FAILED: {_scrub(e)}")
                continue
            usd += c
            nbytes += b
            jobs.append((day, syms, schema, start, end, out, c, b, False))
    return jobs, usd, nbytes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch symbol-days into a local archive")
    ap.add_argument("--pairs", required=True, help="pair list JSON")
    ap.add_argument("--dataset", default="EQUS.ALL")
    ap.add_argument("--schemas", nargs="+", default=["ohlcv-1m"])
    ap.add_argument("--archive", default=str(ARCHIVE_DEFAULT))
    ap.add_argument("--before", help="only pairs with date < this")
    ap.add_argument("--after", help="only pairs with date >= this")
    ap.add_argument("--missing-from-cache", nargs="?", const=str(CACHE_DEFAULT),
                    help="only pairs with no bar in the cache")
    ap.add_argument("--lookback", type=int, default=LOOKBACK_DAYS,
                    help="calendar days of warm-up to pull before each date")
    ap.add_argument("--max-cost", type=float, default=5.00,
                    help="abort if the estimate exceeds this (USD)")
    ap.add_argument("--confirm", action="store_true",
                    help="actually download; without it this only estimates")
    a = ap.parse_args(argv)

    try:
        import databento as db
    except ImportError:
        sys.exit("pip install databento")

    pairs = filter_pairs(load_pairs(Path(a.pairs)), before=a.before, after=a.after,
                         missing_from_cache=a.missing_from_cache)
    if not pairs:
        print("nothing to fetch after filtering")
        return 0
    groups = group_by_date(pairs)
    root = Path(a.archive)

    print(f"{len(pairs)} symbol-days over {len(groups)} dates, "
          f"{len({s for s, _ in pairs})} symbols")
    print(f"dataset {a.dataset}   schemas {a.schemas}   archive {root}/\n")

    client = db.Historical(_key())
    jobs, usd, nbytes = plan(client, groups, a.dataset, a.schemas, root, a.lookback)

    todo = [j for j in jobs if not j[8]]
    have = [j for j in jobs if j[8]]
    for day, syms, schema, *_rest, out, c, b, skip in sorted(jobs):
        if skip:
            continue
        print(f"  {day}  {schema:9} {len(syms):>3} sym  {b/1e6:>8.2f} MB  ${c:>7.4f}")

    print(f"\nalready on disk, skipped : {len(have)}")
    print(f"to download              : {len(todo)}")
    print(f"ESTIMATED SIZE           : {nbytes/1e6:,.1f} MB")
    print(f"ESTIMATED COST           : ${usd:,.4f}")

    if not todo:
        return 0
    if usd > a.max_cost:
        sys.exit(f"\nABORTED: ${usd:,.2f} exceeds --max-cost ${a.max_cost:,.2f}. "
                 "Narrow the request or raise the limit deliberately.")
    if not a.confirm:
        print("\nDry run. Re-run with --confirm to download.")
        return 0

    print()
    written = 0
    for day, syms, schema, start, end, out, _c, _b, _skip in sorted(todo):
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".partial")
        try:
            client.timeseries.get_range(
                dataset=a.dataset, schema=schema, symbols=syms,
                stype_in="raw_symbol", start=start, end=end, path=str(tmp))
        except Exception as e:  # noqa: BLE001
            print(f"  {day} {schema:9} FAILED: {_scrub(e)}")
            tmp.unlink(missing_ok=True)
            continue
        # Rename only on success, so an interrupted run never leaves a truncated
        # file that a later --confirm would skip as "already on disk".
        tmp.replace(out)
        written += 1
        print(f"  {day}  {schema:9} -> {out}  ({out.stat().st_size/1e6:.2f} MB)")

    print(f"\nwrote {written} file(s) to {root}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
