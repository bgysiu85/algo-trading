#!/usr/bin/env python3
"""What is actually in the Databento archive, counted off the disk.

    python -m common.archive_inventory
    python -m common.archive_inventory --archive E:/Databento

WHY THIS IS NOT THE DOWNLOADER'S OWN SUMMARY
---------------------------------------------
The overnight run reported

    EQUS.SUMMARY statistics (pairs)    0 chunk(s)   ok

for a job whose plan said 548 chunks. That number comes from a regex looking
for "wrote N chunk" in the job's output, and the per-pair fetcher does not
print that phrase -- so `0` there means "the counter did not match", which is
indistinguishable in the report from "nothing downloaded". Those are opposite
conclusions, and a run cannot check itself: the summary is written by the same
code whose behaviour is in question.

So this counts files and bytes off the disk instead, which is the only account
that is not the downloader's own.

WHAT IT LOOKS FOR BEYOND COUNTS
--------------------------------
`.partial` files. Downloads land on a temporary name and are renamed only on
success, so a leftover `.partial` is an interrupted transfer -- invisible to a
file count, and the next run skips the day because... it does not, actually:
the real file is absent so it retries. The danger is the opposite one, a
`.partial` accumulating silently while free space drains. Either way, an
interrupted transfer is a thing worth naming rather than leaving on disk
unmentioned.

Zero-byte files get the same treatment: a file that exists but holds nothing
satisfies every "already on disk, skip it" check in the fetcher, and would be
skipped forever.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common.databento_fetch import default_archive
from common.report_io import emit

SUFFIX = ".dbn.zst"


def stem_date(path: Path) -> str:
    """The date or month a chunk covers, from its filename."""
    n = path.name
    return n[: -len(SUFFIX)] if n.endswith(SUFFIX) else path.stem


def scan(root: Path) -> tuple[list[dict], list[Path], list[Path]]:
    """Walk dataset/schema directories. Returns (rows, partials, empties)."""
    rows, partials, empties = [], [], []
    if not root.exists():
        return rows, partials, empties
    for dataset in sorted(p for p in root.iterdir() if p.is_dir()):
        for schema in sorted(p for p in dataset.iterdir() if p.is_dir()):
            files, nbytes = [], 0
            for f in sorted(schema.glob("*")):
                if f.name.endswith(".partial"):
                    partials.append(f)
                    continue
                if not f.name.endswith(SUFFIX):
                    continue
                size = f.stat().st_size
                if size == 0:
                    empties.append(f)
                    continue
                files.append(f)
                nbytes += size
            rows.append({
                "dataset": dataset.name,
                "schema": schema.name,
                "files": len(files),
                "bytes": nbytes,
                "first": stem_date(files[0]) if files else "",
                "last": stem_date(files[-1]) if files else "",
            })
    return rows, partials, empties


def render(root: Path, rows, partials, empties, free_gb: float) -> str:
    lines = [f"DATABENTO ARCHIVE INVENTORY  ({root})", "",
             f"  {'dataset':<16} {'schema':<12} {'files':>7} {'MB':>12} "
             f"{'first':<12} {'last':<12}",
             "  " + "-" * 74]
    tf = tb = 0
    for r in rows:
        mark = "   EMPTY" if r["files"] == 0 else ""
        lines.append(f"  {r['dataset']:<16} {r['schema']:<12} {r['files']:>7} "
                     f"{r['bytes']/1e6:>12,.1f} {r['first']:<12} {r['last']:<12}{mark}")
        tf += r["files"]
        tb += r["bytes"]
    lines += ["  " + "-" * 74,
              f"  {'TOTAL':<16} {'':<12} {tf:>7} {tb/1e6:>12,.1f}",
              "",
              f"  free space  {free_gb:,.1f} GB"]

    if partials:
        lines += ["", f"INTERRUPTED TRANSFERS ({len(partials)})", "",
                  "  Downloads rename only on success, so these are transfers "
                  "that died", "  mid-flight. Safe to delete; the next run "
                  "re-fetches the day.", ""]
        lines += [f"  {p}" for p in partials[:20]]
        if len(partials) > 20:
            lines.append(f"  ... and {len(partials) - 20} more")

    if empties:
        lines += ["", f"ZERO-BYTE FILES ({len(empties)})", "",
                  "  These satisfy every 'already on disk, skip it' check in "
                  "the fetcher", "  and would be skipped forever. Delete them "
                  "and re-run the pull.", ""]
        lines += [f"  {p}" for p in empties[:20]]
        if len(empties) > 20:
            lines.append(f"  ... and {len(empties) - 20} more")

    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Count what is in the archive")
    ap.add_argument("--archive", default=str(default_archive()))
    ap.add_argument("--report", default="var/reports/archive_inventory.txt")
    a = ap.parse_args(argv)

    root = Path(a.archive)
    if not root.exists():
        sys.exit(f"{root} does not exist. Check .databento_archive or pass "
                 "--archive.")
    rows, partials, empties = scan(root)
    free = shutil.disk_usage(root).free / 1e9
    emit(render(root, rows, partials, empties, free), a.report,
         header=f"common.archive_inventory  {root}")
    return 1 if (partials or empties) else 0


if __name__ == "__main__":
    sys.exit(main())
