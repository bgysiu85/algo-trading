#!/usr/bin/env python3
"""W15-0037's Task Scheduler wrapper: runs strategy.chartmark_v2.forward --confirm unattended, then commits and pushes the ledger
(forward_chartmark_v2.json) only if it changed. Same pattern as strategy.w16.dvp_forward_scheduled. Safe to run more often than weekly:
a day already on disk is never re-bought and a recorded trade is never re-scored.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.chartmark_v2.forward_scheduled

Everything it does is also appended to D:\\Trading\\Claude outputs\\w15_0037_weekly_log.txt. Exit code 3 = a registered early stop fired
in this run (FAILED FORWARD); 1 = a refusal (freeze, regression, read-back, cost ceiling) or a git problem: read the log.

THE 1PASSWORD TRAP (same as W16-0014): if DATABENTO_API_KEY is an op:// reference, resolving it needs an unlocked 1Password CLI, which a
scheduled run has nobody to unlock. Set OP_SERVICE_ACCOUNT_TOKEN in the task's environment or set DATABENTO_API_KEY to the literal key,
and test one real run with the Task Scheduler "Run" button before trusting the schedule.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from strategy.chartmark_v2 import forward as F

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = Path("D:/Trading/Claude outputs/w15_0037_weekly_log.txt")
LEDGER_NAME = "forward_chartmark_v2.json"


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
            _log(fh, f"forward scorer aborted: {e}")
        _log(fh, f"forward scorer exit code: {rc}")

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
        commit = _git(["commit", "-m", f"W15-0037: forward ledger update ({datetime.now().date().isoformat()}, scheduled)"])
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
