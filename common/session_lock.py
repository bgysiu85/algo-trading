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

HEARTBEAT, 2026-10-28 (W10-0013 sub 6)
--------------------------------------
A PID means nothing on another machine, and inside a container PIDs repeat on
every run. So the lock now also carries `host`, a per-session `token` and
`heartbeat_epoch`, which a background thread refreshes every HEARTBEAT_S
seconds. A lock WITH a heartbeat is alive while the heartbeat is under
HEARTBEAT_STALE_S old, wherever it is read from. That is what lets a PC tool
read the NAS trader's lock off a read-only share (active_anywhere): it can
tell "alive" from "left behind by a crash" without being able to ask the NAS
whether process 7 exists. A lock WITHOUT a heartbeat (written before this
change) keeps the old PID logic locally and is ignored when it is remote,
because nothing about it can be verified from here.

A crash now blocks backtests for at most HEARTBEAT_STALE_S (2 minutes), not
for a day. The clock comparison is across machines, so both need working NTP;
120 s against a 20 s refresh leaves room for several seconds of skew.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import uuid
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

HEARTBEAT_S = 20.0          # how often a live session refreshes its lock
HEARTBEAT_STALE_S = 120.0   # a heartbeat older than this means the session is gone

# Other machines' locks to honour, os.pathsep-separated (";" on Windows). The
# ProArt sets this to the NAS trader's lock on the read-only share so a backtest
# started on the PC refuses while the NAS trader is in session.
REMOTE_ENV = "SESSION_LOCK_REMOTE"


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
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _heartbeat_stale(info: dict, now: float | None = None) -> str | None:
    """Why a lock WITH a heartbeat is dead, or None if it is alive."""
    now = time.time() if now is None else now
    age = now - float(info.get("heartbeat_epoch", 0))
    if age > HEARTBEAT_STALE_S:
        return f"heartbeat is {age:.0f}s old (max {HEARTBEAT_STALE_S:.0f}s)"
    return None


def _stale_reason_local(info: dict) -> str | None:
    """Why a lock on THIS machine's disk is stale, or None if it is live."""
    if "heartbeat_epoch" in info:
        why = _heartbeat_stale(info)
        if why:
            return why
        # Same machine, process gone: no need to wait out the heartbeat. A
        # live pid proves nothing here (container pids repeat), only a dead one.
        if info.get("host") == socket.gethostname() and \
                not _pid_alive(int(info.get("pid", -1))):
            return f"pid {info.get('pid')} is not running"
        return None
    if not _pid_alive(int(info.get("pid", -1))):
        return f"pid {info.get('pid')} is not running"
    age_h = (time.time() - float(info.get("started_epoch", 0))) / 3600.0
    if age_h > MAX_AGE_H:
        return f"lock is {age_h:.1f}h old (max {MAX_AGE_H:.0f}h)"
    return None


def active(path: Path = LOCK_PATH) -> dict | None:
    """The lock if a LIVE session holds it, else None.

    Removes the file as a side effect when it is stale, so one call both
    answers the question and cleans up.
    """
    info = _read_settled(path, tries=4, pause=0.05)
    if info is None:
        return None

    stale_because = _stale_reason_local(info)
    if stale_because:
        try:
            Path(path).unlink()
        except OSError:
            pass
        info["stale_reason"] = stale_because
        info["stale"] = True
        return None
    return info


def _warn(msg: str) -> None:
    print(f"WARNING (session lock): {msg}", file=sys.stderr)


def _read_settled(path: Path, tries: int = 3, pause: float = 0.2) -> dict | None:
    """read(), retrying when the file exists but cannot be read right now.

    The heartbeat replaces the file every 20 s; on Windows a reader that opens it
    at that instant can get PermissionError, and across a share a read can come
    back short. Either would otherwise read as "no session" -- the answer that
    lets a backtest start.
    """
    for k in range(tries):
        info = read(path)
        if info is not None:
            return info
        if not Path(path).exists():
            return None
        time.sleep(pause)               # exists but unreadable: a partial read
    return None


def active_remote(path: Path) -> dict | None:
    """A live lock on another machine, read-only; None if absent or not provably live.

    Never deletes anything (the share is read-only, and a stale lock there is
    the owner's to clear). Fails OPEN: an unreachable share or a lock that
    cannot be verified is treated as no session, with a warning, because
    refusing every backtest whenever the NAS is switched off would be worse.
    """
    path = Path(path)
    try:
        if not path.parent.exists():
            _warn(f"cannot reach {path} -- the NAS lock was NOT checked. If the "
                  f"NAS trader is running, a backtest here can throttle it.")
            return None
    except OSError:
        _warn(f"cannot reach {path} -- the NAS lock was NOT checked.")
        return None
    info = _read_settled(path)
    if info is None:
        return None
    if "heartbeat_epoch" not in info:
        _warn(f"{path} has no heartbeat (written by an older release); it "
              f"cannot be verified from here and is ignored.")
        return None
    if _heartbeat_stale(info):
        return None
    info = dict(info)
    info["remote"] = str(path)
    return info


def remote_paths(env=None) -> list[Path]:
    raw = (os.environ if env is None else env).get(REMOTE_ENV, "")
    return [Path(p) for p in raw.split(os.pathsep) if p.strip()]


def active_anywhere(path: Path = LOCK_PATH, env=None) -> dict | None:
    """The live session on this machine, else on any machine in SESSION_LOCK_REMOTE.

    What backtest.py, probe_window.py and main.py ask: IB's request budget is
    account-wide, so a session on the NAS counts as much as one on this PC.
    """
    local = active(path)
    if local:
        return local
    for p in remote_paths(env):
        found = active_remote(p)
        if found:
            return found
    return None


def describe(info: dict) -> str:
    """What is holding the lock, including WHICH TREE since 2026-09-11.

    With a frozen production copy running sessions beside a development tree,
    "a live session is already running" is only half an answer -- the useful
    half is which directory it is running from, because that is what tells
    Ben whether to stop it or whether he is about to start a second one from
    the wrong window. `tree` is absent on locks written before this, so it is
    read defensively. Since 2026-10-28 it also says which MACHINE, and how
    fresh the heartbeat is, because "running on the NAS" is the usual answer
    now and the heartbeat age is what tells a live session from one that died
    a minute ago (it clears itself within HEARTBEAT_STALE_S).
    """
    base = (f"{info.get('mode')} session for strategy "
            f"{info.get('strategy')} (pid {info.get('pid')}, started "
            f"{info.get('started_at')})")
    host = info.get("host")
    if info.get("remote"):
        base += f"\n  on another machine ({host or 'unknown host'}), lock read from {info['remote']}"
    elif host:
        base += f"\n  on {host}"
    if "heartbeat_epoch" in info:
        age = max(0.0, time.time() - float(info["heartbeat_epoch"]))
        base += f"\n  last heartbeat {age:.0f}s ago (a session that died clears itself after {HEARTBEAT_STALE_S:.0f}s)"
    tree = info.get("tree")
    ver = info.get("version")
    if tree:
        base += f"\n  running from {tree}" + (f" at {ver}" if ver else "")
    return base


def _write_atomic(path: Path, info: dict) -> None:
    """Write beside, then rename over: a reader never sees half a lock."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(info, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _beat(path: Path, token: str, stop: threading.Event, every: float) -> None:
    """Refresh heartbeat_epoch until stopped or the lock stops being ours.

    Ownership is the per-session token, not the pid: container pids repeat, so
    a pid test would let this session refresh (and so resurrect) a lock a
    later session had taken over. If the file is gone or someone else's we
    stop quietly and never write it back. A failed write (a transient
    PermissionError on Windows while a reader has the file open) is retried
    next tick; the stale limit is six beats, so one miss costs nothing.
    """
    while not stop.wait(every):
        try:
            cur = read(path)
            if not cur or cur.get("token") != token:
                return
            cur["heartbeat_epoch"] = time.time()
            _write_atomic(path, cur)
        except OSError:
            continue


@contextmanager
def held(mode: str, strategy: str, path: Path = LOCK_PATH, **extra):
    """Hold the lock for the duration of a live session.

    Removes it on the way out even if the body raised, so a Ctrl-C does not
    leave a lock that blocks tonight's scheduled backtest. A daemon thread
    keeps heartbeat_epoch fresh while the body runs (see the module docstring).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    token = uuid.uuid4().hex
    info = {
        "mode": mode,
        "strategy": strategy,
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "token": token,
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "started_epoch": now,
        "heartbeat_epoch": now,
        **extra,
    }
    _write_atomic(path, info)
    stop = threading.Event()
    beat = threading.Thread(target=_beat, args=(path, token, stop, HEARTBEAT_S),
                            name="session-lock-heartbeat", daemon=True)
    beat.start()
    try:
        yield info
    finally:
        stop.set()
        beat.join(timeout=5)
        try:
            current = read(path)
            if current and current.get("token") == token:
                path.unlink()
        except OSError:
            pass


def main(argv=None, env=None) -> int:
    """`python -m common.session_lock` -- is any session live, here or on the NAS?

    Prints where it looked so an empty answer can be trusted: "no live session"
    after checking the NAS share is a different statement from the same words
    when SESSION_LOCK_REMOTE was never set.
    """
    env = os.environ if env is None else env
    remotes = remote_paths(env)
    print(f"this machine : {socket.gethostname()}   local lock: {LOCK_PATH}")
    if remotes:
        for p in remotes:
            print(f"also checking: {p}")
    else:
        print(f"also checking: nothing ({REMOTE_ENV} is not set, so a session on "
              f"another machine would NOT be seen)")
    found = active_anywhere(LOCK_PATH, env)
    if found:
        print("LIVE SESSION -- " + describe(found))
        return 1
    print("no live session")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
