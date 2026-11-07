"""Read-only GO / NO-GO before flipping the NAS trader to TRADER_MODE=paper (W10-0013 sub 9).

    .venv\\Scripts\\python.exe deploy\\nas_trader\\cutover_preflight.py

It places no order and logs in to nothing. It checks, over SSH as `claude` and on this PC:
  1. the shadow run passed (shadow_check.py verdict PASS);
  2. the NAS .env is mode 600 (its contents, TRADER_MODE included, are unreadable to `claude` by design);
  3. the NAS trader release is the one you expect (--expect-commit), and the lock is still dry (the flip has not happened);
  4. the ProArt has no IB Gateway / TWS process and nothing listening on the IB ports (one paper username = one session);
  5. the PC scheduled tasks that read and pull the NAS data exist.
Exit 0 = GO, 1 = NO-GO.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
HOST = "claude@192.168.1.109"
KEY = Path(r"D:\Trading\Claude outputs\.ssh\nas_claude_ed25519")
IB_PORTS = (4001, 4002, 7496, 7497)
IB_PROCESSES = ("ibgateway", "ibcalpha", "tws")
TASKS = ("Algo - pull NAS var", "Algo - shadow check")


def decide(checks: list[tuple[str, bool, str]]) -> bool:
    """GO only when every check passed."""
    return bool(checks) and all(ok for _, ok, _ in checks)


def parse_verdict(text: str) -> str:
    m = re.search(r"^VERDICT:\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else "UNKNOWN"


def _ssh(cmd: str) -> str:
    r = subprocess.run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", HOST, cmd],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-200:] or f"ssh exit {r.returncode}")
    return r.stdout


def _ps(cmd: str) -> str:
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def run(expect_commit: str | None) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    out = subprocess.run([PY, str(HERE / "shadow_check.py")], capture_output=True, text=True, timeout=120).stdout
    v = parse_verdict(out)
    checks.append(("shadow run passed", v == "PASS", f"shadow_check verdict {v}"))

    try:
        mode = _ssh("stat -c %a /volume1/docker/trader/.env").strip()
        checks.append((".env mode 600", mode == "600", f"mode {mode}"))
        try:
            lock = json.loads(_ssh("cat /volume1/trader-data/var/state/session.lock"))
        except RuntimeError as e:
            # No lock file is the normal state outside a session (the trader removes it when it stops).
            if "No such file" not in str(e):
                raise
            checks.append(("NAS lock still dry", True, "no session.lock: the trader is not in session"))
        else:
            checks.append(("NAS lock still dry", lock.get("mode") == "dry", f"lock mode {lock.get('mode')}"))
        if expect_commit:
            rel = json.loads(_ssh("cat /volume1/docker/trader/app/RELEASE.json"))
            checks.append(("release commit", rel.get("commit") == expect_commit and rel.get("dirty") is False,
                           f"NAS on {rel.get('commit')} dirty={rel.get('dirty')}, expected {expect_commit}"))
    except Exception as e:  # noqa: BLE001
        checks.append(("NAS reachable", False, f"{type(e).__name__}: {e}"))

    procs = _ps("Get-Process | Where-Object { $_.ProcessName -match '" + "|".join(IB_PROCESSES) +
                "' } | Select-Object -ExpandProperty ProcessName")
    checks.append(("no IB Gateway/TWS on the ProArt", not procs, procs or "none running"))
    ports = _ps("Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in "
                + ",".join(map(str, IB_PORTS)) + " } | Select-Object -ExpandProperty LocalPort")
    checks.append(("no IB port listening on the ProArt", not ports, ports.replace("\n", ",") or "none"))

    for t in TASKS:
        have = _ps(f"(Get-ScheduledTask -TaskName '{t}' -ErrorAction SilentlyContinue).State")
        checks.append((f"task '{t}'", bool(have), have or "missing"))
    return checks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-commit", help="commit the NAS release should be on (e.g. 666a822)")
    a = ap.parse_args()
    checks = run(a.expect_commit)
    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'NO'}] {name}: {detail}")
    go = decide(checks)
    print("GO: the flip is safe to do" if go else "NO-GO: fix the lines marked NO first")
    print("Not checked (unreadable by design): TRADER_MODE in the NAS .env. Read the first line of the trader log.")
    return 0 if go else 1


if __name__ == "__main__":
    sys.exit(main())
