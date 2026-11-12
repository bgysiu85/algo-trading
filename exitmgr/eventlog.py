#!/usr/bin/env python3
"""Append-only JSON-lines event log of the live exit manager (REGISTERED_exit_cmp.md sec 14 rail 14).

Every fill seen, every order sent / modified / cancelled (or, in dry mode, that WOULD have been sent) with the reason and
the numbers behind it, every refusal by a rail, every alert, latencies, and at start the version hash of the code and the
config. This file is the evidence for sub 6. There is deliberately no method that rewrites or truncates it: each record is
appended with its own open/flush/fsync, so a crash loses at most the line being written.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from exitmgr.timeutil import iso, ny, utcnow

PKG = Path(__file__).resolve().parent


def code_hash() -> str:
    """SHA-256 over the manager's own source files (exitmgr/*.py, sorted by name), first 16 hex digits."""
    h = hashlib.sha256()
    for p in sorted(PKG.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


class EventLog:
    def __init__(self, path, clock=utcnow, echo=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.echo = echo                      # callable(str) for alerts (stdout in the container); None = silent

    def write(self, kind: str, **fields) -> dict:
        now = self.clock()
        rec = {"ts": iso(now), "ny": ny(now).strftime("%Y-%m-%d %H:%M:%S"), "kind": kind}
        rec.update(fields)
        line = json.dumps(rec, default=str, ensure_ascii=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        return rec

    def alert(self, code: str, msg: str, **fields) -> dict:
        rec = self.write("alert", code=code, msg=msg, **fields)
        if self.echo is not None:
            self.echo(f"ALERT {code}: {msg}")
        return rec


def read_events(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
