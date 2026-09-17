#!/usr/bin/env python3
"""The RTH bars the point-in-time ORB run needs, fetched without losing any.

    python -m strategy.orb.pit_bars plan               # writes the pairs file
    python -m strategy.orb.pit_bars plan --write-manifest
    python -m common.databento_fetch --dataset XNAS.BASIC --schemas ohlcv-1m \
        --pairs var/state/orb_pit_fetch_pairs.json              # estimate
    python -m strategy.orb.pit_bars verify             # after the fetch

WHY THIS EXISTS
---------------
`REGISTERED_orb_pit.md` found 2,537 of the 6,170 PIT symbol-days with no file
in `bar_cache_xnas`. `common.bar_cache_build` wrote none of them: the XNAS.BASIC
minute archive is in the DAILY layout, where `<date>.dbn.zst` holds only the
symbols some earlier fetch asked for on that date (the survivors and rejects),
and the PIT names that were not survivors were never requested. Their only
bars on disk are the 04:00-09:30 all-symbol slices, which stop before ORB's
range begins.

So the bars have to be bought, and `common.databento_fetch` is the tool. Used
naively it does damage in two ways, both silent:

  1. IT REPLACES THE DAY'S FILE. A fetch for the missing PIT symbols on
     2025-03-07 writes `2025-03-07.dbn.zst` holding THOSE symbols -- and the
     survivor symbols that were in it are gone. `bar_cache_xnas` would keep its
     existing csv files, so nothing would break today; the archive, which is
     the source of truth, would have lost them for every later rebuild.

  2. IT SKIPS FILES WITH NO RECORDED SYMBOL LIST. `covered()` treats a file
     with no manifest symbols as covering everything (deliberately -- see its
     docstring). 98 of the 529 dates this touches are like that, so their PIT
     names would be "already on disk", nothing would be fetched, and the cache
     build would count them as empty again.

This module removes both. For every date with a missing PIT symbol-day it
reads the symbols the existing file ACTUALLY holds (from the DBN metadata, not
the manifest -- the two agreed on all 431 dates that have both, checked
2026-09-17), and writes a pairs file asking for that set PLUS the missing
names. The fetch then replaces each file with a strict superset of itself.
`--write-manifest` records the file-read symbol lists for the unverified dates
so `covered()` decides on facts. `verify` re-reads every touched file after
the fetch and refuses if any symbol present before is absent after.

It lives under strategy/orb/ because it serves one registered run; the two
defects in databento_fetch it works around are recorded, not fixed here.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATASET = "XNAS.BASIC"
SCHEMA = "ohlcv-1m"
PIT_PAIRS = Path("var/state/screen_pairs_pit.json")
CACHE = Path("bar_cache_xnas/3d_to_2000")
FETCH_PAIRS = Path("var/state/orb_pit_fetch_pairs.json")
SNAPSHOT = Path("var/state/orb_pit_fetch_snapshot.json")


def dbn_symbols(path: Path) -> set[str]:
    """Symbols a DBN file was requested for, read from its metadata only."""
    import databento as db
    return set(db.DBNStore.from_file(path).symbols or [])


def missing_by_date(pairs: list[dict], cache: Path) -> dict[str, set[str]]:
    have = {p.name for p in cache.glob("*.csv.gz")} if cache.is_dir() else set()
    out: dict[str, set[str]] = defaultdict(set)
    for r in pairs:
        if f"{r['symbol']}_{r['date']}.csv.gz" not in have:
            out[r["date"]].add(r["symbol"])
    return dict(out)


def plan(missing: dict[str, set[str]], day_file, read_symbols) -> dict:
    """{date: {"before": [...], "request": [...]}} for every date to fetch.

    `day_file(date) -> Path` and `read_symbols(path) -> set` are injected so
    the rule can be tested without a DBN file. `before` is empty when no file
    exists yet. The request is before | missing, so it can never be narrower
    than what the file already holds -- asserted, not assumed.
    """
    out = {}
    for day in sorted(missing):
        f = day_file(day)
        before = read_symbols(f) if f.exists() else set()
        request = before | missing[day]
        assert before <= request
        out[day] = {"before": sorted(before), "request": sorted(request),
                    "added": sorted(missing[day] - before)}
    return out


def pairs_of(p: dict) -> list[dict]:
    return [{"symbol": s, "date": d} for d, e in sorted(p.items())
            for s in e["request"]]


def manifest_backfill(manifest: dict, p: dict) -> dict:
    """Symbol lists for touched dates whose manifest row has none.

    Written from the file's own metadata, and marked as such. A row that
    already has a list is left alone: it agreed with the file on every date
    checked, and overwriting a record with a re-derivation of itself only
    adds a way to be wrong.
    """
    ent = {}
    for day, e in p.items():
        key = f"{SCHEMA}/{day}"
        row = manifest.get(key)
        if row is None or "symbols" in row or not e["before"]:
            continue
        new = dict(row)
        new.pop("symbols_unverified", None)
        new["symbols"] = e["before"]
        new["symbols_from_file_metadata"] = True
        ent[key] = new
    return ent


def verify(snapshot: dict, day_file, read_symbols) -> dict:
    """After the fetch: every touched file must hold everything it held before
    and every name it was asked to add."""
    lost, unfetched, absent = {}, {}, []
    for day, e in sorted(snapshot.items()):
        f = day_file(day)
        if not f.exists():
            absent.append(day)
            continue
        now = read_symbols(f)
        if set(e["before"]) - now:
            lost[day] = sorted(set(e["before"]) - now)
        if set(e["added"]) - now:
            unfetched[day] = sorted(set(e["added"]) - now)
    return {"lost": lost, "unfetched": unfetched, "absent": absent}


def _day_file(archive: Path):
    return lambda day: archive / DATASET / SCHEMA / f"{day}.dbn.zst"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("plan", "verify"))
    ap.add_argument("--archive", default=None)
    ap.add_argument("--pairs", default=str(PIT_PAIRS))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(FETCH_PAIRS))
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    ap.add_argument("--write-manifest", action="store_true",
                    help="record file-read symbol lists for unverified dates "
                         "(a timestamped backup of manifest.json is kept)")
    a = ap.parse_args(argv)

    if a.archive:
        archive = Path(a.archive)
    else:
        from common.databento_fetch import default_archive
        archive = default_archive()
    day_file = _day_file(archive)

    if a.action == "verify":
        snap = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))
        r = verify(snap, day_file, dbn_symbols)
        print(f"{len(snap)} dates checked")
        print(f"  files absent                 {len(r['absent'])}")
        print(f"  dates missing an added name  {len(r['unfetched'])}")
        print(f"  DATES THAT LOST A SYMBOL     {len(r['lost'])}")
        for d, s in list(r["lost"].items())[:10]:
            print(f"    {d}  {', '.join(s[:8])}")
        if r["lost"]:
            print("\nREFUSED: the fetch removed symbols from the archive. Do "
                  "not build the cache; re-fetch those dates with the "
                  "snapshot's request lists.")
            return 1
        print("\nNothing lost. Next: common.bar_cache_build for the PIT pairs.")
        return 0

    pairs = json.loads(Path(a.pairs).read_text(encoding="utf-8"))
    miss = missing_by_date(pairs, Path(a.cache))
    p = plan(miss, day_file, dbn_symbols)
    n_add = sum(len(e["added"]) for e in p.values())
    n_keep = sum(len(e["before"]) for e in p.values())
    new_files = sum(1 for e in p.values() if not e["before"])

    manifest_file = archive / DATASET / "manifest.json"
    manifest = (json.loads(manifest_file.read_text(encoding="utf-8"))
                if manifest_file.exists() else {})
    backfill = manifest_backfill(manifest, p)

    Path(a.out).write_text(json.dumps(pairs_of(p), indent=1), encoding="utf-8")
    Path(a.snapshot).write_text(json.dumps(p, indent=1), encoding="utf-8")
    print(f"PIT symbol-days with no cache file  {sum(map(len, miss.values())):,}")
    print(f"dates to fetch                      {len(p):,}  "
          f"({new_files} with no file yet)")
    print(f"symbols re-requested to keep        {n_keep:,}")
    print(f"symbols added                       {n_add:,}")
    print(f"unverified manifest rows            {len(backfill):,}")
    print(f"wrote {a.out}  and  {a.snapshot}")

    if backfill and not a.write_manifest:
        print("\nNOT READY: those manifest rows have no symbol list, so "
              "databento_fetch would skip their dates. Re-run with "
              "--write-manifest.")
        return 1
    if backfill:
        bak = manifest_file.with_name(
            f"manifest.{datetime.now():%Y%m%d_%H%M%S}.bak.json")
        shutil.copy2(manifest_file, bak)
        manifest.update(backfill)
        manifest_file.write_text(
            json.dumps(dict(sorted(manifest.items())), indent=1),
            encoding="utf-8")
        print(f"manifest: {len(backfill)} rows given their file's symbols "
              f"(backup {bak.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
