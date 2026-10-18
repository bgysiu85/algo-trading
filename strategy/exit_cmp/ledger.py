#!/usr/bin/env python3
"""EXIT-CMP G7: the ledger and the one-run lock. W15-0053 sub 2. REGISTERED_exit_cmp.md sec 11-12.

Written by the pre-flight, BEFORE any outcome exists: the SHA-256 of the registration, of the frozen code (exitmgr/ and
strategy/exit_cmp/) and of the training frame. Parity (G2) and the outcome run both refuse to start if any of the three has
changed since. The outcome run writes `outcome_started` before it computes anything and refuses a second run;
`--retry-after-crash` is allowed only when a run started and never finished, and the crash is recorded."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from strategy.chartmark_clone.ledger import frame_content_sha256, git_commit, sha256_file
from strategy.exit_cmp import spec as S

REPO = Path(__file__).resolve().parents[2]
CODE_DIRS = ("exitmgr", "strategy/exit_cmp")


class LedgerError(RuntimeError):
    pass


def code_sha256(root: Path = REPO) -> str:
    """Hash of every .py file under the frozen code directories (line endings normalised, so a Windows checkout and a Linux one
    agree). Sorted by relative path."""
    h = hashlib.sha256()
    for d in CODE_DIRS:
        for p in sorted((Path(root) / d).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def path(out_dir: Path) -> Path:
    return Path(out_dir) / S.LEDGER_FILE


def read(out_dir: Path) -> dict:
    p = path(out_dir)
    if not p.exists():
        raise LedgerError(f"{p} is missing: run the pre-flight first (python -m strategy.exit_cmp.preflight).")
    return json.loads(p.read_text(encoding="utf-8"))


def _write(out_dir: Path, rec: dict) -> None:
    p = path(out_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create(out_dir: Path, *, fr, per_year: dict, n_entries: int, preflight_file: str, root: Path = REPO,
           rewrite: bool = False) -> dict:
    p = path(out_dir)
    if p.exists():
        old = read(out_dir)
        if not rewrite:
            raise LedgerError(f"{p} already exists. Run with --rewrite-ledger ONLY before the outcome run, e.g. after a "
                              "PRE-RUN amendment; it is refused once the outcome run has started.")
        if old.get("outcome_started"):
            raise LedgerError("the outcome run has started: the ledger is never rewritten.")
    rec = dict(study=S.STUDY, created_utc=_now(), git_commit=git_commit(root),
               registration_sha256=sha256_file(Path(root) / S.REGISTRATION), code_sha256=code_sha256(root),
               frame_content_sha256=frame_content_sha256(fr), n_frame_bars=fr.n, n_entries=n_entries, per_year=per_year,
               preflight_file=preflight_file, preflight_done=True, parity_ok=False, parity_utc=None,
               outcome_started=False, outcome_done=False, crashes=[])
    _write(out_dir, rec)
    return rec


def verify(out_dir: Path, fr=None, root: Path = REPO) -> dict:
    led = read(out_dir)
    if sha256_file(Path(root) / S.REGISTRATION) != led["registration_sha256"]:
        raise LedgerError("REGISTERED_exit_cmp.md has changed since the pre-flight wrote the ledger -- refusing.")
    if code_sha256(root) != led["code_sha256"]:
        raise LedgerError("exitmgr/ or strategy/exit_cmp/ has changed since the pre-flight (the code must be frozen before parity "
                          "and the outcome run) -- refusing. Before the outcome run only: re-run the pre-flight with --rewrite-ledger.")
    if fr is not None and frame_content_sha256(fr) != led["frame_content_sha256"]:
        raise LedgerError("the training frame no longer matches the ledger's SHA-256 -- refusing.")
    return led


def mark_parity(out_dir: Path) -> None:
    led = read(out_dir)
    led["parity_ok"], led["parity_utc"] = True, _now()
    _write(out_dir, led)


def begin_outcome(out_dir: Path, retry_after_crash: bool = False) -> dict:
    led = read(out_dir)
    if not led.get("preflight_done"):
        raise LedgerError("the pre-flight has not been recorded.")
    if not led.get("parity_ok"):
        raise LedgerError("G2 parity has not passed (python -m strategy.exit_cmp.parity) -- no outcome is read.")
    if led.get("outcome_done"):
        raise LedgerError("the outcome run is done: it is one run, never repeated (sec 11).")
    if led.get("outcome_started"):
        if not retry_after_crash:
            raise LedgerError("an outcome run started and did not finish. If it crashed, rerun with --retry-after-crash; "
                              "the crash is recorded.")
        led["crashes"].append(dict(utc=_now(), started_utc=led.get("outcome_started_utc")))
    led["outcome_started"], led["outcome_started_utc"] = True, _now()
    _write(out_dir, led)
    return led


def finish_outcome(out_dir: Path, result_files: list[str]) -> None:
    led = read(out_dir)
    led["outcome_done"], led["outcome_done_utc"], led["result_files"] = True, _now(), result_files
    _write(out_dir, led)
