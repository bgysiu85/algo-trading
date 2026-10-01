#!/usr/bin/env python3
"""The label file: append-only, one row per decision, written and fsynced after every decision (sec 5, gate G4).

    labels_chartmark_clone.csv  columns = spec.LABEL_COLUMNS  (registered columns + 'seq', I7)

An UNDO row removes the decision at its `seq`; only the decision just made can be undone, once, in the session that made
it. The fit uses the last non-UNDO row per seq; the FIRST label of a candidate (a non-repeat row) is the one fitted."""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.qorder import Item


class LabelError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class LabelStore:
    def __init__(self, path: Path, items: list[Item], sitting_id: str):
        self.path, self.items, self.sitting_id = Path(path), items, sitting_id
        self.effective: list[dict] = []          # decisions by seq, a prefix 0..m-1
        self._undo_ok = False
        self._load()

    # ---------------------------------------------------------------- load / validate
    def _load(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open("r", encoding="utf-8", newline="") as fh:
            rd = csv.DictReader(fh)
            if rd.fieldnames != S.LABEL_COLUMNS:
                raise LabelError(f"{self.path}: header {rd.fieldnames} != {S.LABEL_COLUMNS} -- refusing to append.")
            rows = list(rd)
        for r in rows:
            seq = int(r["seq"])
            if not 0 <= seq < len(self.items):
                raise LabelError(f"label row with seq {seq} outside the schedule ({len(self.items)} items)")
            it = self.items[seq]
            if (r["candidate_id"], int(r["queue_pos"]), r["is_repeat"] == "1") != (it.candidate_id, it.queue_pos, it.is_repeat):
                raise LabelError(f"label row seq {seq} does not match the queue/schedule -- the queue changed under the labels.")
            if r["label"] == "UNDO":
                if not self.effective or int(self.effective[-1]["seq"]) != seq:
                    raise LabelError(f"UNDO for seq {seq} that is not the latest decision")
                self.effective.pop()
            elif r["label"] in ("TAKE", "SKIP"):
                if seq != len(self.effective):
                    raise LabelError(f"label rows out of order at seq {seq} (expected {len(self.effective)})")
                self.effective.append(r)
            else:
                raise LabelError(f"unknown label {r['label']!r}")

    # ---------------------------------------------------------------- state
    @property
    def next_seq(self) -> int:
        return len(self.effective)

    @property
    def done(self) -> bool:
        return self.next_seq >= len(self.items)

    @property
    def can_undo(self) -> bool:
        return self._undo_ok and bool(self.effective)

    def progress(self) -> dict:
        firsts = [r for r in self.effective if r["is_repeat"] != "1"]
        uniq = len(firsts)
        takes = sum(r["label"] == "TAKE" for r in firsts)
        enough = (uniq >= S.MIN_UNIQUE and takes >= S.MIN_TAKES) or uniq >= S.MAX_UNIQUE
        return dict(unique=uniq, takes=takes, skips=uniq - takes, min_unique=S.MIN_UNIQUE, min_takes=S.MIN_TAKES,
                    max_unique=S.MAX_UNIQUE, enough=enough, done=self.done,
                    repeats=len(self.effective) - uniq)

    # ---------------------------------------------------------------- write
    def _append(self, row: dict) -> None:
        new = not self.path.exists() or self.path.stat().st_size == 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=S.LABEL_COLUMNS, lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(row)
            fh.flush()
            os.fsync(fh.fileno())

    def _row(self, it: Item, label: str, **kw) -> dict:
        return dict(candidate_id=it.candidate_id, queue_pos=it.queue_pos, is_repeat="1" if it.is_repeat else "0",
                    label=label, skip_reason=kw.get("skip_reason", ""), take_reason=kw.get("take_reason", ""),
                    note=kw.get("note", ""), confidence=kw.get("confidence", ""), ms_to_decide=kw.get("ms", ""),
                    sitting_id=self.sitting_id, labelled_at_utc=_now(), seq=it.seq)

    def add(self, seq: int, label: str, *, skip_reason: str = "", take_reason: str = "", note: str = "",
            confidence: str = "", ms: int | None = None) -> dict:
        if seq != self.next_seq or self.done:
            raise LabelError(f"seq {seq} is not the candidate on screen (expected {self.next_seq})")
        if label not in ("TAKE", "SKIP"):
            raise LabelError(f"label must be TAKE or SKIP, got {label!r}")
        if label == "SKIP":
            if skip_reason not in S.SKIP_REASONS:
                raise LabelError("a skip needs a reason 1-7")
            if take_reason:
                raise LabelError("a skip cannot carry a take reason")
            if skip_reason == "7" and not note.strip():
                raise LabelError("reason 7 (Other) needs a few words")
        else:
            if skip_reason:
                raise LabelError("a take cannot carry a skip reason")
            if take_reason and take_reason not in S.TAKE_REASONS:
                raise LabelError("take reason must be A-D")
        if confidence not in ("", "1", "2", "3"):
            raise LabelError("confidence must be 1, 2 or 3")
        note = " ".join(note.split())[:200]
        row = self._row(self.items[seq], label, skip_reason=skip_reason, take_reason=take_reason, note=note,
                        confidence=confidence, ms=("" if ms is None else int(ms)))
        self._append(row)
        self.effective.append({k: str(v) for k, v in row.items()})
        self._undo_ok = True
        return row

    def undo(self) -> dict:
        if not self.can_undo:
            raise LabelError("nothing to undo (only the decision just made, once)")
        last = self.effective[-1]
        it = self.items[int(last["seq"])]
        row = self._row(it, "UNDO")
        self._append(row)
        self.effective.pop()
        self._undo_ok = False
        return row


def new_sitting_id() -> str:
    return "S" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
