#!/usr/bin/env python3
"""Pack the exit manager (W15-0053) for the NAS: one tar that unpacks into /volume1/docker/trader/extras (W10-0022 part 10).

    python deploy/nas_trader/pack_exitmgr.py                  -> Claude outputs/w10_0022_exitmgr_nas.tar
    python deploy/nas_trader/pack_exitmgr.py --list           print the files and stop

What goes in: exitmgr/run_manager.py and every repo module it can reach by import (same crawler as build_release.py, so a
module added to the manager later is packed without editing this file), the __init__.py of each package, and
exitmgr_RELEASE.json (commit, dirty flag). Never .env, never tests. Files 0644 / folders 0755: the container runs as user 1000.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_release as br  # noqa: E402

REPO = br.REPO
ENTRY = "exitmgr.run_manager"
TOP = "extras"                                      # unpacked with: tar -xf X -C /volume1/docker/trader
DEFAULT_OUT = REPO / "Claude outputs" / "w10_0022_exitmgr_nas.tar"


def plan(repo: Path = REPO) -> dict[str, Path]:
    """{path inside extras/: source file}."""
    return dict(sorted((f.relative_to(repo).as_posix(), f) for f in br.closure(repo, ENTRY).values()))


def build(out: Path, repo: Path = REPO) -> dict:
    files = plan(repo)
    meta = br.manifest(list(files), repo)
    meta["entry"] = ENTRY
    with tarfile.open(out, "w") as tar:
        dirs = {"/".join(rel.split("/")[:i]) for rel in files for i in range(1, len(rel.split("/")))}
        br._entry(tar, TOP, None, 0o755, is_dir=True)
        for d in sorted(dirs):
            br._entry(tar, f"{TOP}/{d}", None, 0o755, is_dir=True)
        for rel, src in files.items():
            br._entry(tar, f"{TOP}/{rel}", src.read_bytes(), 0o644)
        br._entry(tar, f"{TOP}/exitmgr_RELEASE.json", (json.dumps(meta, indent=2) + "\n").encode("utf-8"), 0o644)
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    files = plan()
    if a.list:
        print("\n".join(files) + f"\n\n{len(files)} files")
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    meta = build(a.out)
    print(f"wrote {a.out}  ({meta['file_count']} files)  commit {meta['commit'] or '(none)'}  dirty={meta['dirty']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
