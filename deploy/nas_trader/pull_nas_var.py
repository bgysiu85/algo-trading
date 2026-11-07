#!/usr/bin/env python3
"""Copy the NAS trader's fills, archive and logs to this PC. One way, additive.

WHY A COPY AND NOT A LIVE SHARE
-------------------------------
The trader on the NAS writes var/fills/*.csv; everything on the ProArt that
reads fills (the journal, db_load, the desk) expects them on the ProArt's own
disk. Reading them across SMB each time would make every tool depend on the
NAS being awake, and a half-open share hangs rather than fails. A scheduled
copy keeps one local copy that always works, at the price of being up to one
interval behind. The LOCK is the exception and is read live (common/
session_lock.py, SESSION_LOCK_REMOTE), because a stale answer there is the
failure it exists to prevent.

WHAT IT WILL NOT DO
-------------------
* It never writes to the source (the share is read-only for this PC anyway).
* It never deletes anything at the destination. A file removed on the NAS
  stays here: the copy is a record, not a mirror that can lose history.
* It never overwrites var/fills. Files land in var/nas_mirror/ first. With
  --promote, fills missing from var/fills are copied across; a name that
  already exists there with different content is reported as a CONFLICT and
  left alone, because during the shadow run (W10-0013 sub 8) the PC and the
  NAS trader can both write mcl_fills_<same day>.csv and silently preferring
  either would corrupt the record of what was traded.

* --promote never copies a fills file written by a DRY session (a session_open
  CONFIG row saying dry_run=True, or any order row with a DRY status). Those
  files are shadow-run mechanics checks, not trades, and the journal and
  db_load read var/fills. They are listed as SKIPPED so nothing disappears
  silently. A day file that mixes dry and paper rows is skipped too: decide
  by hand which rows are the record. A file that cannot be read is skipped.

Exit codes: 0 done, 1 conflict(s) found with --promote, 2 source not reachable.
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time
from pathlib import Path

SOURCE_ENV = "NAS_TRADER_VAR"
DEFAULT_DIRS = ("fills", "archive", "logs")
MTIME_SLOP_S = 2.0          # SMB and NTFS round timestamps differently


def _needs_copy(src: Path, dst: Path) -> bool:
    if not dst.exists():
        return True
    s, d = src.stat(), dst.stat()
    return s.st_size != d.st_size or s.st_mtime > d.st_mtime + MTIME_SLOP_S


def _copy(src: Path, dst: Path) -> None:
    """Copy via a temp name so a reader never sees a half-written file."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    shutil.copyfile(src, tmp)
    shutil.copystat(src, tmp)
    os.replace(tmp, dst)


def sync_dir(src: Path, dst: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """Copy new or changed files src -> dst. Returns (copied, skipped, bytes)."""
    copied = skipped = nbytes = 0
    if not src.is_dir():
        return 0, 0, 0
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        if f.suffix == ".part" or f.name.endswith(".tmp"):
            continue
        target = dst / f.relative_to(src)
        if _needs_copy(f, target):
            if not dry_run:
                _copy(f, target)
            copied += 1
            nbytes += f.stat().st_size
        else:
            skipped += 1
    return copied, skipped, nbytes


def dry_session_reason(f: Path) -> str | None:
    """Why a fills file must not be promoted: "dry", "unreadable", or None to promote.

    A dry session writes a session_open CONFIG row containing dry_run=True and
    gives its order rows a DRY_* status. Either marker, anywhere in the file,
    keeps the whole file out of var/fills.
    """
    try:
        with f.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("status") or "").upper().startswith("DRY"):
                    return "dry"
                if row.get("action") == "CONFIG" and "dry_run=True" in " ".join(
                        v for v in row.values() if isinstance(v, str)):
                    return "dry"
    except (OSError, UnicodeDecodeError, csv.Error):
        return "unreadable"
    return None


def promote_fills(mirror_fills: Path, local_fills: Path, dry_run: bool = False,
                  skipped: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Copy mirror fills that var/fills lacks. Returns (promoted, conflicts).

    Dry-session and unreadable files are not copied and are not conflicts; their
    names go into `skipped` (as "name (dry)") when the caller passes a list.
    """
    promoted, conflicts = [], []
    if not mirror_fills.is_dir():
        return promoted, conflicts
    for f in sorted(p for p in mirror_fills.iterdir() if p.is_file() and p.suffix == ".csv"):
        why = dry_session_reason(f)
        if why:
            if skipped is not None:
                skipped.append(f"{f.name} ({why})")
            continue
        target = local_fills / f.name
        if not target.exists():
            if not dry_run:
                _copy(f, target)
            promoted.append(f.name)
        elif target.read_bytes() != f.read_bytes():
            conflicts.append(f.name)
    return promoted, conflicts


def run(source: Path, dest: Path, dirs=DEFAULT_DIRS, promote: bool = False,
        local_fills: Path = Path("var/fills"), dry_run: bool = False, out=print) -> int:
    source = Path(source)
    if not source.is_dir():
        out(f"CANNOT REACH {source} -- is the NAS awake and the share mapped? "
            f"Nothing was copied.")
        return 2
    out(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {source} -> {dest}"
        + ("  (dry run: nothing written)" if dry_run else ""))
    for d in dirs:
        c, s, b = sync_dir(source / d, Path(dest) / d, dry_run)
        out(f"  {d:<8} copied {c:>4}  unchanged {s:>4}  {b / 1024:.0f} KiB")
    rc = 0
    if promote:
        skipped: list[str] = []
        promoted, conflicts = promote_fills(Path(dest) / "fills", Path(local_fills), dry_run, skipped)
        out(f"  promote  {len(promoted)} new fill file(s) into {local_fills}"
            + (": " + ", ".join(promoted) if promoted else ""))
        if skipped:
            out(f"  SKIPPED  {len(skipped)} file(s) not promoted (dry session or unreadable): "
                + ", ".join(skipped))
        for name in conflicts:
            out(f"  CONFLICT {name}: {local_fills / name} exists and differs from the NAS copy. "
                f"Left alone. Decide which is the record before merging.")
            rc = 1
    return rc


def _tee(logfile: Path | None):
    """print() that also appends to `logfile`; a log that cannot be written never stops the copy."""
    def out(line: str) -> None:
        print(line)
        if logfile:
            try:
                logfile.parent.mkdir(parents=True, exist_ok=True)
                with logfile.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass
    return out


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", default=env.get(SOURCE_ENV),
                    help=f"the NAS var folder (default: ${SOURCE_ENV})")
    ap.add_argument("--dest", default="var/nas_mirror")
    ap.add_argument("--dirs", default=",".join(DEFAULT_DIRS))
    ap.add_argument("--promote", action="store_true",
                    help="also copy fills that var/fills lacks (never overwrites)")
    ap.add_argument("--local-fills", default="var/fills")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log", default="var/logs/pull_nas_var.log",
                    help="also append what was done here (a scheduled task has no console)")
    a = ap.parse_args(argv)
    if not a.source:
        print(f"no source: pass --source or set {SOURCE_ENV}", file=sys.stderr)
        return 2
    return run(Path(a.source), Path(a.dest), tuple(x for x in a.dirs.split(",") if x),
               a.promote, Path(a.local_fills), a.dry_run, out=_tee(Path(a.log) if a.log else None))


if __name__ == "__main__":
    sys.exit(main())
