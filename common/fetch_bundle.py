#!/usr/bin/env python3
"""Find the bundle that was just downloaded, and fetch it.

    python -m common.fetch_bundle            # find, verify, fetch, merge
    python -m common.fetch_bundle --no-merge # stop after the fetch
    python -m common.fetch_bundle --file D:\\somewhere\\x.bundle

WHY THIS EXISTS
---------------
Work is built and tested in a cloud sandbox that cannot push, so it arrives as
a git bundle downloaded from the chat. The command to take it in is then

    git fetch <wherever the browser put it> main

and that path is the problem. It has been guessed wrong twice -- once as
Downloads when the file was elsewhere, once as var\\ when it was still in the
chat -- and each time the error was `does not appear to be a git repository`,
which reads like the bundle is corrupt rather than absent. A wrong path is the
single most common way this handover fails, and it fails in a way that looks
like something worse.

So nobody types the path. This looks in the usual places, takes the NEWEST
matching bundle, says which file it chose and how old it is, and verifies the
bundle against this repo before fetching -- because `git bundle verify` is the
step that distinguishes "corrupt download" from "wrong file" from "this bundle
needs commits you do not have".
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PATTERN = "algo-trading-*.bundle"

# "Claude outputs" first: it is where files from a Claude session are put, it
# is already gitignored, and it is inside the repo so the path is short. Both
# spellings are listed because Windows does not care about the case and Linux
# does; duplicates collapse in candidates(). The rest are fallbacks so a
# bundle downloaded by hand is still found rather than reported missing.
SEARCH = ["Claude outputs", "claude outputs",
          "~/Downloads", "~/Desktop", "~/Documents", ".", "var"]


def candidates(extra=(), search=None) -> list[Path]:
    """Newest first, de-duplicated.

    `search` exists so a test can name the ONLY directories to look in. Without
    it every test ran against whatever bundles happened to be on the machine:
    six passed in an empty sandbox and failed on Ben's, where 25 real bundles
    live in the directories this searches by design.
    """
    seen, out = set(), []
    for d in list(extra) + (SEARCH if search is None else list(search)):
        p = Path(d).expanduser()
        if not p.is_dir():
            continue
        for f in p.glob(PATTERN):
            r = f.resolve()
            if r not in seen:
                seen.add(r)
                out.append(r)
    return sorted(out, key=lambda f: f.stat().st_mtime, reverse=True)


def age(path: Path) -> str:
    mins = (time.time() - path.stat().st_mtime) / 60
    if mins < 90:
        return f"{mins:.0f} minutes old"
    if mins < 60 * 48:
        return f"{mins/60:.1f} hours old"
    return f"{mins/60/24:.1f} days old"


def git(*args, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], text=True, capture_output=True, **kw)


def dirty() -> list[str]:
    r = git("status", "--porcelain")
    return [l for l in r.stdout.splitlines() if l.strip()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--file", help="skip the search and use this bundle")
    ap.add_argument("--dir", action="append", default=[],
                    help="also look here (repeatable)")
    ap.add_argument("--only", action="store_true",
                    help="look ONLY in --dir, not the usual places")
    ap.add_argument("--ref", default="main")
    ap.add_argument("--no-merge", action="store_true",
                    help="fetch into FETCH_HEAD and stop")
    a = ap.parse_args(argv)

    if a.file:
        chosen = Path(a.file).expanduser().resolve()
        if not chosen.exists():
            print(f"{chosen} does not exist")
            return 1
        found = [chosen]
    else:
        where = [] if a.only else SEARCH
        found = candidates(a.dir, search=where)
        if not found:
            print(f"No {PATTERN} found in:")
            for d in list(a.dir) + where:
                print(f"  {Path(d).expanduser()}")
            print("\nDownload the bundle from the chat first, or pass --file.")
            return 1
        chosen = found[0]

    print(f"bundle   {chosen}")
    print(f"         {chosen.stat().st_size/1e6:.2f} MB, {age(chosen)}")
    if len(found) > 1:
        print(f"         ({len(found)-1} older bundle(s) ignored)")

    # VERIFY BEFORE FETCH. This is the step that tells the three failures
    # apart: a truncated download, a bundle for a different repo, and a bundle
    # whose base commits are missing here. Fetch alone reports all three the
    # same way.
    v = git("bundle", "verify", str(chosen))
    if v.returncode != 0:
        print("\nthe bundle did not verify against this repo:\n")
        print((v.stderr or v.stdout).strip())
        print("\n  'needs these commits' means an EARLIER bundle was skipped.")
        print("  Anything else usually means the download was incomplete.")
        return 1

    f = git("fetch", str(chosen), a.ref)
    if f.returncode != 0:
        print("\nfetch failed:\n" + (f.stderr or f.stdout).strip())
        return 1
    print(f"\nfetched {a.ref} -> FETCH_HEAD")

    if a.no_merge:
        print("\n  git merge FETCH_HEAD")
        return 0

    # A merge onto uncommitted work fails halfway and leaves a state that
    # needs git knowledge to get out of. Refuse instead, and say what to do.
    d = dirty()
    if d:
        print("\nNOT merging: you have uncommitted changes.\n")
        for line in d[:10]:
            print(f"  {line}")
        if len(d) > 10:
            print(f"  ... and {len(d)-10} more")
        print("\n  Commit or stash them, then:  git merge FETCH_HEAD")
        return 1

    m = git("merge", "FETCH_HEAD")
    print(m.stdout.strip() or m.stderr.strip())
    if m.returncode != 0:
        return 1
    print("\nNow run:  python -m pytest tests/ -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
