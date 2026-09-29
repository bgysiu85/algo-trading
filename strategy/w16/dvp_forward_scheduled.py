#!/usr/bin/env python3
"""Unattended wrapper for the Windows Task Scheduler job that runs W16-0014's
weekly forward scorer with nobody watching. Runs strategy.w16.dvp_forward
--confirm, and if the ledger changed, commits and pushes it -- the two steps
every OTHER W16 script leaves to Ben by hand, made safe to automate here
because this one touches a single small append-only file
(w16_dvp_forward_ledger.json), spending is capped every run at
strategy.w16.dvp_forward.MAX_COST, and the whole weekly cycle is idempotent
(a missed week, or two runs in one week, changes nothing extra).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_forward_scheduled

NOT for a manual/interactive run -- for that, run strategy.w16.dvp_forward
yourself and commit the result by hand (W16-0014 subitem 2's own commands).
This wrapper exists only for Task Scheduler, where nobody is at the keyboard
to read its output, so everything it does is ALSO appended to
`D:\\Trading\\Claude outputs\\w16_0014_weekly_log.txt` -- open that file to see
what the last several runs actually did, rather than digging through Task
Scheduler's own history.

THE 1PASSWORD TRAP
------------------
If DATABENTO_API_KEY is set to an `op://...` reference (common.secrets_util's
SECOND resolution source), resolving it shells out to `op read`, which needs
either an authenticated, non-interactive 1Password CLI
(OP_SERVICE_ACCOUNT_TOKEN) or a live unlock prompt someone answers --
common.secrets_util's own module docstring: "a lazy re-resolve blocks the
process on a GUI unlock prompt." Task Scheduler runs with nobody there to
answer one. A scheduled run that hangs or fails at the credential step means
THIS, not a bug in this wrapper: either set OP_SERVICE_ACCOUNT_TOKEN in the
task's own environment, or set DATABENTO_API_KEY directly to the literal key
(the module's FIRST resolution source, which needs no 1Password call at
all). See the handover for both options; test one real scheduled run by hand
(Task Scheduler's own "Run" button) before trusting the Saturday schedule.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from strategy.w16 import dvp_forward as F

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = Path("D:/Trading/Claude outputs/w16_0014_weekly_log.txt")
LEDGER_NAME = "w16_dvp_forward_ledger.json"


def _git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _log(fh, msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    fh.write(line + "\n")
    fh.flush()


def main(argv=None) -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        _log(fh, "=== scheduled run starting ===")
        try:
            rc = F.main(["--confirm"])
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
            _log(fh, f"dvp_forward aborted: {e}")
        _log(fh, f"dvp_forward exit code: {rc}")

        status = _git(["status", "--porcelain", "--", LEDGER_NAME])
        if status.returncode != 0:
            _log(fh, f"git status failed: {status.stderr.strip()}")
            _log(fh, "=== scheduled run finished (git status failed) ===\n")
            return 1
        if not status.stdout.strip():
            _log(fh, "ledger unchanged -- nothing to commit")
            _log(fh, "=== scheduled run finished ===\n")
            return rc

        add = _git(["add", LEDGER_NAME])
        if add.returncode != 0:
            _log(fh, f"git add failed: {add.stderr.strip()}")
            _log(fh, "=== scheduled run finished (git add failed) ===\n")
            return 1
        commit = _git(["commit", "-m",
                       f"W16-0014: forward ledger update "
                       f"({datetime.now().date().isoformat()}, scheduled)"])
        _log(fh, f"commit: rc={commit.returncode} {(commit.stdout + commit.stderr).strip()}")
        if commit.returncode != 0:
            _log(fh, "=== scheduled run finished (commit failed) ===\n")
            return 1
        push = _git(["push"])
        _log(fh, f"push: rc={push.returncode} {(push.stdout + push.stderr).strip()}")
        _log(fh, "=== scheduled run finished ===\n")
        if push.returncode != 0:
            return 1
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
