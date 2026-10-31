"""W10-0013 subs 7 and 15: which NAS ports answer from the PC, on the home network and over Tailscale.

The W17-0024 checker (Trade Journal repo, tools/check_journal_internet.py) extended with the trader's ports and the
NAS's loopback-only services. Run on the ProArt (it is on both networks). It only opens and closes TCP connections; it
sends nothing, so it never logs in to anything, IBKR included.

    python deploy\\nas_trader\\check_nas_exposure.py
    python deploy\\nas_trader\\check_nas_exposure.py --lan 192.168.1.109 --tailnet 100.x.y.z --out "D:\\Trading\\Claude outputs\\nas_exposure.txt"

Why a tailnet address may matter: Synology's Tailscale runs in "userspace" mode, which hands every tailnet connection to
the NAS's own 127.0.0.1. So a service bound to 127.0.0.1 only (the Gateway VNC screens, DSM's Postgres, DNS control) is
reachable from every tailnet device. Sub 7 measured that on 2026-10-31 (100.79.212.23), and Ben uninstalled Tailscale
from the NAS the same day. So --tailnet is skipped by default; if Tailscale ever comes back, pass its address and every
MUST-BE-CLOSED port must be closed there too.

Exit code 0 = every must-be-closed port is closed on every address checked, 1 = at least one is open.
Standard library only.
"""
from __future__ import annotations

import argparse
import socket
import sys
from dataclasses import dataclass
from datetime import datetime

# Ports no device other than the NAS itself should reach. The 127.0.0.1-only ones are from `ss -tln` on the NAS
# (2026-10-31); re-list them there if DSM adds services.
MUST_BE_CLOSED = [
    (4001, "Gateway API live"), (4002, "Gateway API paper"), (4003, "Gateway relay live"), (4004, "Gateway relay paper"),
    (7496, "TWS live"), (7497, "TWS paper"),
    (5900, "recorder Gateway VNC screen (127.0.0.1 only)"), (5901, "trader Gateway VNC screen (127.0.0.1 only)"),
    (5432, "DSM's own Postgres (127.0.0.1 only)"), (953, "DNS server control, rndc (127.0.0.1 only)"),
    (512, "DSM internal (127.0.0.1 only)"), (161, "SNMP over TCP (127.0.0.1 only)"),
    (33300, "DSM internal (127.0.0.1 only)"), (33303, "DSM internal (127.0.0.1 only)"),
    (33304, "DSM internal (127.0.0.1 only)"),
    (8088, "old journal port"), (4180, "journal login container"),
    (8080, "portal relay container (sub 11; reached only through the tunnel)"),
    (1411, "Pocket ID container (sub 15; reached only through the tunnel)"),
    (6881, "qbittorrent BitTorrent"), (9865, "qbittorrent web UI"),
]
# Expected to answer; reported for the record, never a failure.
EXPECTED_OPEN = [(22, "SSH"), (445, "SMB file sharing"), (5000, "DSM http"), (5001, "DSM https")]


@dataclass
class Result:
    ok: bool
    name: str
    detail: str


def is_open(ip: str, port: int, timeout: float = 3.0) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, port)) == 0
    finally:
        s.close()


def check(label: str, ip: str, probe=is_open) -> list[Result]:
    out = []
    for port, why in MUST_BE_CLOSED:
        open_ = probe(ip, port)
        out.append(Result(not open_, f"{label} {ip}:{port} ({why})", "OPEN" if open_ else "closed"))
    for port, why in EXPECTED_OPEN:
        out.append(Result(True, f"{label} {ip}:{port} ({why}, expected)", "open" if probe(ip, port) else "closed"))
    return out


def report(results: list[Result]) -> str:
    lines = [f"W10-0013 sub 7 NAS exposure check - {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for r in results:
        lines.append(f"{'PASS' if r.ok else 'FAIL'}  {r.name}\n      {r.detail}")
    fails = sum(not r.ok for r in results)
    lines += ["", f"{len(results) - fails} passed, {fails} failed" + ("" if fails else "  -> ALL CHECKS PASSED")]
    return "\n".join(lines) + "\n"


def main(argv=None, probe=is_open) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--lan", default="192.168.1.109", help="the NAS's home-network address ('' = skip)")
    p.add_argument("--tailnet", default="", help="the NAS's Tailscale address, if it has one (default: skip)")
    p.add_argument("--out", help="write the report here as well")
    a = p.parse_args(argv)
    results: list[Result] = []
    for label, ip in (("home", a.lan), ("tailnet", a.tailnet)):
        if ip:
            results += check(label, ip, probe)
    text = report(results)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
