#!/usr/bin/env python3
"""G7: the ledger. The queue's SHA-256 is written before the first label; the labelling tool refuses to start if the queue,
manifest or frame no longer match it. Later items append the label-file hash and the frozen-clone hash (sub 4 / sub 5)."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from strategy.chartmark.data import Frame, make_frame
from strategy.chartmark_clone import spec as S


class LedgerError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _frame_arrays(fr: Frame) -> dict[str, np.ndarray]:
    t = fr.t.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return dict(t=t, o=fr.o.astype("<f8"), h=fr.h.astype("<f8"), l=fr.l.astype("<f8"), c=fr.c.astype("<f8"),
                v=fr.v.astype("<f8"), roll_after=fr.roll_after.astype(np.uint8))


def frame_content_sha256(fr: Frame) -> str:
    h = hashlib.sha256()
    for k, a in _frame_arrays(fr).items():
        h.update(k.encode("ascii"))
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def save_frame_cache(fr: Frame, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **_frame_arrays(fr))


def load_frame_cache(path: Path) -> Frame:
    z = np.load(path)
    import pandas as pd
    t = pd.to_datetime(z["t"], unit="ns", utc=True)
    return make_frame(t, z["o"], z["h"], z["l"], z["c"], z["v"], z["roll_after"].astype(bool), "clone frame cache")


def git_commit(root: Path) -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write_ledger(out_dir: Path, *, fr: Frame, info: dict, n_queue: int, n_seq: int, repo_root: Path) -> dict:
    out_dir = Path(out_dir)
    path = out_dir / S.LEDGER_FILE
    if path.exists():
        raise LedgerError(f"{path} already exists: the queue is fixed once written; it is never rebuilt.")
    rec = dict(
        study=S.STUDY, created_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=git_commit(repo_root), n_candidates=n_queue, n_presentations=n_seq,
        per_year=info["per_year"], f1_up=info["up"], f1_down=info["down"], f1_warmup=info["f1_warmup"],
        queue_sha256=sha256_file(out_dir / S.QUEUE_FILE), manifest_sha256=sha256_file(out_dir / S.MANIFEST_FILE),
        frame_content_sha256=frame_content_sha256(fr), n_frame_bars=fr.n,
        queue_seed_words=S.QUEUE_SEED_WORDS, repeat_seed_word=S.REPEAT_SEED_WORD,
        files=dict(manifest=S.MANIFEST_FILE, queue=S.QUEUE_FILE, labels=S.LABELS_FILE),
        first_label_written=False, labels_sha256=None, clone_frozen_sha256=None, outcome_run_done=False)
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def read_ledger(out_dir: Path) -> dict:
    path = Path(out_dir) / S.LEDGER_FILE
    if not path.exists():
        raise LedgerError(f"{path} is missing: run the builder first (python -m strategy.chartmark_clone.build).")
    return json.loads(path.read_text(encoding="utf-8"))


def check_inputs(out_dir: Path, fr: Frame) -> dict:
    """The labelling tool's start-up check: queue, manifest and frame must equal what the ledger recorded."""
    led = read_ledger(out_dir)
    out_dir = Path(out_dir)
    if sha256_file(out_dir / S.QUEUE_FILE) != led["queue_sha256"]:
        raise LedgerError("the queue file no longer matches the ledger's SHA-256 -- refusing to start.")
    if sha256_file(out_dir / S.MANIFEST_FILE) != led["manifest_sha256"]:
        raise LedgerError("the manifest file no longer matches the ledger's SHA-256 -- refusing to start.")
    if frame_content_sha256(fr) != led["frame_content_sha256"]:
        raise LedgerError("the frame cache no longer matches the ledger's SHA-256 -- refusing to start.")
    return led


def mark_first_label(out_dir: Path) -> None:
    """Called once, when the first label row is written (idempotent)."""
    path = Path(out_dir) / S.LEDGER_FILE
    led = read_ledger(out_dir)
    if not led.get("first_label_written"):
        led["first_label_written"] = True
        led["first_label_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")


def mark_frozen(out_dir: Path, labels_sha256: str, clone_frozen_sha256: str) -> None:
    """Sub 4: record the label-file hash and the frozen-clone hash. Once; the labels are closed from then on."""
    path = Path(out_dir) / S.LEDGER_FILE
    led = read_ledger(out_dir)
    if led.get("clone_frozen_sha256") or led.get("labels_sha256"):
        raise LedgerError("the ledger already records a frozen clone: it is never overwritten.")
    led["labels_sha256"] = labels_sha256
    led["clone_frozen_sha256"] = clone_frozen_sha256
    led["frozen_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")


def check_labels_open(out_dir: Path) -> None:
    """The labelling tool's second start-up check: once the clone is frozen no further label may be written."""
    led = read_ledger(out_dir)
    if led.get("labels_sha256") or led.get("clone_frozen_sha256"):
        raise LedgerError("the labels are closed: the clone was fitted and frozen on them (ledger records "
                          "labels_sha256). A new label would make the frozen clone's inputs unreproducible.")
