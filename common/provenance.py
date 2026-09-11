#!/usr/bin/env python3
"""WHICH code is running, and WHICH var/ it is writing to.

    python -m common.provenance            # what this tree is
    python -m common.provenance --expect-shared-var D:\\Trading\\var

WHY THIS EXISTS
---------------
Ben, 2026-09-11: a frozen PRODUCTION copy runs the sessions while development
continues in the working tree. That is the right shape, and it creates one
question the project could not previously answer and two ways to get hurt.

**The question: what was running last night?** A fill log records symbols,
prices and reasons. It has never recorded the CODE that produced them. With one
tree that was recoverable from the commit history and a date. With two trees it
is not: "MCL, apex off" describes a configuration that has had three different
meanings this week.

**Hazard 1 — TWO TREES, TWO LOCKS.** `session_lock.LOCK_PATH` is
`Path("var/state/session.lock")` -- RELATIVE, so it resolves against the
current working directory. Run production from `D:\\TradingProd` and
development from `D:\\Trading` and there are two lock files. The lock then
protects nothing: both processes can connect to the same IB account at once and
compete for its account-wide request budget, which is the exact failure the
lock was built to prevent.

The fix is one shared `var/`, via a Windows directory junction. But a junction
is a silent thing: if it is missing, or points somewhere else, or is replaced by
an ordinary folder during a copy, **everything keeps working and the protection
is gone**. That is a control whose failure is invisible -- the shape this
project keeps finding -- so it gets a check that resolves the path and says what
it actually found.

**Hazard 2 — A DIRTY PRODUCTION TREE.** The point of a frozen copy is that it
is frozen. An edit made in the wrong window is undetectable by reading the code,
because the code looks exactly like code. `dirty` answers it in one field.

WHAT THIS IS NOT
----------------
Not a deployment tool, and not a guard. It reports; it refuses nothing on its
own. `--expect-shared-var` exits non-zero so a wrapper CAN fail on it, but the
real protections remain where they were: the port allowlist and the DU-prefix
account check in `trader.main_async`, which cannot be bypassed from any entry
point.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# The repository this module belongs to -- anchored to THIS FILE and never to
# the working directory. That is the whole point: with two trees, a
# CWD-relative answer tells you where you typed the command, not which code is
# about to run.
TREE = Path(__file__).resolve().parents[1]

# var/, as the running process will actually resolve it. CWD-relative, exactly
# as session_lock and every report path resolve it, because the question is
# "where will this process write" and not "where does the code live".
def var_dir() -> Path:
    return Path("var").resolve()


@dataclass(frozen=True)
class Provenance:
    tree: str            # the code's own directory
    cwd: str             # where the command was typed
    commit: str          # short sha, or "" when git is unavailable
    described: str       # git describe --tags --always --dirty, or ""
    branch: str
    dirty: bool          # uncommitted changes in the tree
    var_path: str        # var/, fully resolved -- follows junctions
    var_exists: bool

    def as_line(self) -> str:
        """One line, for a log or a notification header."""
        bits = [self.described or self.commit or "no-git"]
        if self.dirty:
            bits.append("DIRTY")
        bits.append(f"tree={Path(self.tree).name}")
        bits.append(f"var={self.var_path}")
        return "  ".join(bits)


def _git(*args: str, cwd: Path) -> str:
    """A git field, or "" -- never an exception and never a prompt.

    A production copy may be a clone, a worktree, or a plain folder copy with
    no .git at all. All three are legitimate ways for Ben to have made it, so
    the absence of git is a reportable state and not an error. `check=False`
    plus a timeout so a broken or network-backed repo cannot hang a session
    start.
    """
    try:
        r = subprocess.run(("git", *args), cwd=str(cwd), timeout=10,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:                                       # noqa: BLE001
        return ""


def read(tree: Path | None = None) -> Provenance:
    t = Path(tree).resolve() if tree else TREE
    v = var_dir()
    # `git status --porcelain` is empty exactly when the tree is clean. An
    # unavailable git gives "" too, which would read as clean -- so dirty is
    # only asserted when git actually answered.
    have_git = bool(_git("rev-parse", "--git-dir", cwd=t))
    status = _git("status", "--porcelain", cwd=t) if have_git else ""
    return Provenance(
        tree=str(t),
        cwd=str(Path.cwd()),
        commit=_git("rev-parse", "--short", "HEAD", cwd=t),
        described=_git("describe", "--tags", "--always", "--dirty", cwd=t),
        branch=_git("rev-parse", "--abbrev-ref", "HEAD", cwd=t),
        dirty=bool(have_git and status),
        var_path=str(v),
        var_exists=v.exists(),
    )


def shared_var(expect: str | Path) -> tuple[bool, str]:
    """Does this process's var/ resolve to `expect`?

    Compared on the RESOLVED path, so a Windows directory junction or a symlink
    counts as shared -- which is the supported way to run two trees against one
    ledger. A string comparison of the configured paths would report a correct
    junction as a mismatch and a broken one as fine, i.e. exactly backwards.

    Case-insensitive, because Windows paths are and `D:\\Trading\\var` and
    `d:\\trading\\var` are the same directory.
    """
    want = Path(expect).resolve()
    got = var_dir()
    if not got.exists():
        return False, f"var/ does not exist at {got}"
    if not want.exists():
        return False, f"the expected shared var/ does not exist at {want}"
    if os.path.normcase(str(got)) != os.path.normcase(str(want)):
        return False, (f"var/ resolves to {got}, not {want} -- this tree has "
                       "its own var/, so it has its own session lock and its "
                       "own fill log")
    return True, f"var/ is shared: {got}"


def render(p: Provenance) -> list[str]:
    L = ["WHAT IS RUNNING", "",
         f"  tree          {p.tree}",
         f"  invoked from  {p.cwd}",
         f"  commit        {p.commit or '(no git in this tree)'}",
         f"  describes as  {p.described or '-'}",
         f"  branch        {p.branch or '-'}",
         f"  uncommitted   {'YES -- this tree is NOT frozen' if p.dirty else 'no'}",
         f"  var/ resolves {p.var_path}"
         + ("" if p.var_exists else "   (DOES NOT EXIST)"),
         ""]
    if p.dirty:
        L += ["  A production copy with uncommitted changes is not a",
              "  production copy. Whatever is different here exists on no",
              "  other machine and in no commit.", ""]
    return L


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--expect-shared-var", metavar="PATH", default=None,
                    help="fail unless var/ resolves to PATH. This is how the "
                         "junction that gives two trees ONE session lock gets "
                         "verified rather than assumed.")
    ap.add_argument("--line", action="store_true",
                    help="one line, for a log or a header")
    a = ap.parse_args(argv)

    p = read()
    if a.line:
        print(p.as_line())
    else:
        print("\n".join(render(p)))

    if a.expect_shared_var:
        ok, why = shared_var(a.expect_shared_var)
        print(("  OK   " if ok else "  WRONG  ") + why)
        if not ok:
            print("\n  Two trees with separate var/ directories have separate")
            print("  session locks. Nothing would stop two live sessions from")
            print("  running against the same IB account at once.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
