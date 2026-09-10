#!/usr/bin/env python3
"""Advisory lock marking a live IB session, so a backtest cannot run into one.

WHY THIS EXISTS
---------------
IB allows roughly 60 historical-data requests per 10 minutes, and the cap is
ACCOUNT-WIDE: a backtest started while the paper trader is running competes
with it for the same budget. IB signals exhaustion by returning empty lists
rather than errors, so both sides fail silently -- the backtest records
phantom NO_DATA, and the trader goes blind without saying so. That is not
hypothetical: an unpaced qualification loop lost 337 of 407 pairs on
2026-09-03 and read as missing history rather than throttling.

WHAT REPLACED WHAT
------------------
The old guard matched the literal string "mcl_paper_trader" in process
command lines. That worked only while exactly one script could hold a
session, and it broke the moment every mode launched through one main.py --
every process then shows "main.py" and the substring means nothing. It also
silently defeated itself if the file were ever renamed, which is why the
rename was deferred until this file existed.

STALE LOCKS
-----------
A crashed session leaves the file behind. If that blocked backtests forever
the guard would be worse than none, so a lock whose process is gone, or which
is older than MAX_AGE_H, is treated as stale and removed. The liveness check
deliberately does NOT use os.kill(pid, 0): on Windows os.kill TERMINATES the
target for any signal other than CTRL_C/CTRL_BREAK, so the obvious POSIX
idiom would kill the very session it is checking for.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOCK_PATH = Path("var/state/session.lock")

# ONE WRITER FOR THE WATCHLIST, 2026-09-10.
#
# common/tv_feed.py and brokers/ibkr/scanner.py both write var/watchlist.txt.
# Until now that rule existed only as a sentence in each file's header -- "Run
# one or the other, never both, or they overwrite each other every few
# seconds" -- and nothing enforced it. Two writers do not error: they take
# turns, the trader sees the watchlist flip between two answers every few
# seconds, and names appear and vanish for no visible reason.
#
# It became load-bearing when main.py gained --mode paper starting the feed
# itself: the obvious mistake is now to run the combined command AND leave
# run_tv_feed.ps1 up in the other terminal, which is exactly the shape a person
# repeats out of habit.
#
# Same file format, same staleness rules, same Windows-safe liveness check --
# every function here already takes `path`.
WRITER_LOCK_PATH = Path("var/state/watchlist_writer.lock")

MAX_AGE_H = 24.0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if k.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)                     # POSIX only -- signal 0 just probes
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                         # exists, owned by someone else
    return True


def read(path: Path = LOCK_PATH) -> dict | None:
    """Raw contents of the lock file, or None if absent/unreadable."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def active(path: Path = LOCK_PATH) -> dict | None:
    """The lock if a LIVE session holds it, else None.

    Removes the file as a side effect when it is stale, so one call both
    answers the question and cleans up.
    """
    info = read(path)
    if info is None:
        return None

    stale_because = None
    if not _pid_alive(int(info.get("pid", -1))):
        stale_because = f"pid {info.get('pid')} is not running"
    else:
        age_h = (time.time() - float(info.get("started_epoch", 0))) / 3600.0
        if age_h > MAX_AGE_H:
            stale_because = f"lock is {age_h:.1f}h old (max {MAX_AGE_H:.0f}h)"

    if stale_because:
        try:
            Path(path).unlink()
        except OSError:
            pass
        info["stale_reason"] = stale_because
        info["stale"] = True
        return None
    return info


def describe(info: dict) -> str:
    return (f"{info.get('mode')} session for strategy "
            f"{info.get('strategy')} (pid {info.get('pid')}, started "
            f"{info.get('started_at')})")


@contextmanager
def held(mode: str, strategy: str, path: Path = LOCK_PATH, **extra):
    """Hold the lock for the duration of a live session.

    Removes it on the way out even if the body raised, so a Ctrl-C does not
    leave a lock that blocks tonight's scheduled backtest.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    info = {
        "mode": mode,
        "strategy": strategy,
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "started_epoch": time.time(),
        **extra,
    }
    path.write_text(json.dumps(info, indent=2))
    try:
        yield info
    finally:
        try:
            current = read(path)
            if current and current.get("pid") == os.getpid():
                path.unlink()
        except OSError:
            pass
