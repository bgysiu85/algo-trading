#!/usr/bin/env python3
r"""W10-0013 sub 11: the portal relay's .env lines, taken from the files the Fly relay was set up from. Prints no secret.

    python deploy\nas_trader\make_relay_env.py --check                # names + 8-char fingerprints only
    python deploy\nas_trader\make_relay_env.py | ssh ... "tr -d '\r' >> /volume1/docker/trader/.env"   # the lines themselves

Reads (D:\Trading UI by default): var/auth.env (OIDC client, session secret, allowed subjects), var/neon.env (history
database URL) and var/agent_token.txt (the trader's agent token). Writes KEY=VALUE lines to stdout in bytes with LF line
ends, so the NAS file gets no carriage returns. A value with a $, quote, backslash or space is refused: docker compose would
read it as something else in a .env file. Nothing is sent anywhere by this script; the pipe in the guide does that.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

DEFAULT_ROOT = Path(r"D:\Trading UI")
# (output name, source file, source key). The token is written under the trader's own name; the relay reads the same value.
MAP = [
    ("RELAY_OIDC_ISSUER", "auth.env", "OIDC_ISSUER"),
    ("RELAY_OIDC_CLIENT_ID", "auth.env", "OIDC_CLIENT_ID"),
    ("RELAY_OIDC_CLIENT_SECRET", "auth.env", "OIDC_CLIENT_SECRET"),
    ("RELAY_SESSION_SECRET", "auth.env", "SESSION_SECRET"),
    ("RELAY_ALLOWED_SUBJECTS", "auth.env", "ALLOWED_SUBJECTS"),
    ("RELAY_DATABASE_URL", "neon.env", "DATABASE_URL"),
    ("UI_AGENT_TOKEN", "agent_token.txt", None),
]
REQUIRED = {"RELAY_OIDC_ISSUER", "RELAY_OIDC_CLIENT_ID", "RELAY_OIDC_CLIENT_SECRET", "RELAY_SESSION_SECRET", "UI_AGENT_TOKEN"}
BAD = set("$\"'\\ \t\r\n`")


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def collect(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """([(NAME, value)], problems)."""
    var = root / "var"
    files = {"auth.env": read_env_file(var / "auth.env"), "neon.env": read_env_file(var / "neon.env")}
    token = var / "agent_token.txt"
    out, problems = [], []
    for name, fname, key in MAP:
        value = token.read_text(encoding="utf-8").strip() if key is None and token.exists() else \
            files.get(fname, {}).get(key or "", "")
        if not value:
            if name in REQUIRED:
                problems.append(f"{name}: missing ({fname}{'' if key is None else ' ' + key})")
            continue
        if BAD & set(value):
            problems.append(f"{name}: contains a $, quote, backslash or space - set it by hand with nano")
            continue
        out.append((name, value))
    return out, problems


def main(argv=None, stdout=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=r"the Trading UI folder (default D:\Trading UI)")
    p.add_argument("--check", action="store_true", help="print names and fingerprints only")
    a = p.parse_args(argv)
    pairs, problems = collect(a.root)
    for msg in problems:
        print("PROBLEM", msg, file=sys.stderr)
    if problems:
        return 1
    if a.check:
        for name, value in pairs:
            print(f"{name}  {len(value)} chars  sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]}")
        return 0
    out = stdout if stdout is not None else sys.stdout.buffer
    for name, value in pairs:
        out.write(f"{name}={value}\n".encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
