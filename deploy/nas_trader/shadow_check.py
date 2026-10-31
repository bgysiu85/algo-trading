"""Read-only evidence collector for the NAS shadow run (W10-0013 sub 8).

Logs in to the NAS over SSH as `claude` (key login), reads the session lock, the fills files, load and memory, appends
one snapshot line to Claude outputs/shadow_run_log.jsonl and prints a verdict on the pass rule: PASS_SESSIONS weekday
sessions with a session_open row, no stale heartbeat in session, no ERROR/REJECT rows. Writes nothing on the NAS.

    .venv\\Scripts\\python.exe deploy\\nas_trader\\shadow_check.py
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOST = "claude@192.168.1.109"
KEY = Path(r"D:\Trading\Claude outputs\.ssh\nas_claude_ed25519")
VAR = "/volume1/trader-data/var"
LOG = Path(r"D:\Trading\Claude outputs\shadow_run_log.jsonl")
PASS_SESSIONS = 3
FIRST_DAY = "20261101"  # sessions before release 666a822 ran without the feed (dry skipped it); they do not count
STALE_S = 120  # the lock counts as dead after 120 s (CLAUDE.md)

REMOTE = (
    f"echo @@LOCK; cat {VAR}/state/session.lock; echo; "
    f"echo @@LOAD; cat /proc/loadavg; grep -E '^(MemTotal|MemAvailable)' /proc/meminfo; "
    f"echo @@WATCH; grep -c -v -E '^[[:space:]]*(#|$)' {VAR}/watchlist.txt; ls {VAR}/archive | tail -5; "
    f"echo @@FILLS; for f in {VAR}/fills/*.csv; do echo \"##FILE $(basename $f)\"; cat \"$f\"; done"
)


def ssh() -> str:
    cmd = ["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, REMOTE]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        sys.exit(f"ssh failed ({out.returncode}): {out.stderr.strip()[-300:]}")
    return out.stdout


def sections(text: str) -> dict[str, str]:
    parts, cur = {}, None
    for line in text.splitlines(keepends=True):
        if line.startswith("@@"):
            cur = line.strip()[2:]
            parts[cur] = ""
        elif cur:
            parts[cur] += line
    return parts


def fills_summary(block: str) -> dict[str, dict]:
    files: dict[str, str] = {}
    name = None
    for line in block.splitlines(keepends=True):
        if line.startswith("##FILE "):
            name = line.split(" ", 1)[1].strip()
            files[name] = ""
        elif name:
            files[name] += line
    summary = {}
    for name, body in files.items():
        rows = list(csv.DictReader(io.StringIO(body)))
        day = name.rsplit("_", 1)[-1].removesuffix(".csv")
        summary[day] = {
            "rows": len(rows),
            "session_open": sum(r["action"] == "CONFIG" and r["reason"] == "session_open" for r in rows),
            "signals": sum(r["action"] in ("BUY", "SELL", "ENTRY", "EXIT") for r in rows),
            "rejects": sum(r["action"] != "CONFIG" and (bool(r["reject_reason"]) or "REJECT" in r["status"].upper())
                           for r in rows),
            "errors": sum("ERROR" in r["status"].upper() for r in rows),
        }
    return summary


def main() -> int:
    s = sections(ssh())
    lock = json.loads(s["LOCK"])
    age = time.time() - lock["heartbeat_epoch"]
    load = s["LOAD"].split()
    mem = {k.rstrip(":"): int(v) // 1024 for k, v in (l.split()[:2] for l in s["LOAD"].splitlines()[1:])}
    fills = fills_summary(s["FILLS"])
    watch = s["WATCH"].split()
    watch_lines = int(watch[0]) if watch else 0
    snap = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": lock["mode"], "strategy": lock["strategy"], "version": lock["version"],
        "started_at": lock["started_at"], "heartbeat_age_s": round(age, 1),
        "watchlist_lines": watch_lines, "archive_tail": watch[1:],
        "load1": float(load[0]), "mem_avail_mb": mem.get("MemAvailable"), "fills": fills,
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snap) + "\n")

    weekday_sessions = [d for d, v in fills.items()
                        if v["session_open"] and d >= FIRST_DAY and datetime.strptime(d, "%Y%m%d").weekday() < 5]
    problems = []
    if lock["mode"] != "dry":
        problems.append(f"mode is {lock['mode']}, not dry")
    if age > STALE_S:
        problems.append(f"heartbeat {age:.0f}s old (dead after {STALE_S}s)")
    if age <= STALE_S and watch_lines == 0:
        problems.append("in session with an empty watchlist: the feed is not filling it (sessions do not count)")
    for d, v in fills.items():
        if v["errors"] or v["rejects"]:
            problems.append(f"{d}: {v['errors']} error / {v['rejects']} reject rows")

    print(f"lock: {lock['mode']} {lock['strategy']} {lock['version']} started {lock['started_at']}, heartbeat {age:.0f}s ago")
    print(f"watchlist lines now: {watch_lines}; archive tail: {watch[1:]}")
    print(f"load {load[0]}, MemAvailable {mem.get('MemAvailable')} MB")
    for d in sorted(fills):
        print(f"  {d}: {fills[d]}")
    print(f"weekday sessions with session_open: {len(weekday_sessions)} of {PASS_SESSIONS} -> {sorted(weekday_sessions)}")
    for p in problems:
        print("PROBLEM:", p)
    done = len(weekday_sessions) >= PASS_SESSIONS and not problems
    print("VERDICT:", "PASS" if done else "NOT YET" if not problems else "PROBLEMS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
