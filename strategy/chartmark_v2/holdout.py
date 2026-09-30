#!/usr/bin/env python3
"""CHARTMARK-v2 holdout (sec 6 + Amendment 4.6). Ledger holdout_chartmark_v2.json, spent once, by the step-C winner only,
only on a nine-of-nine confirmation pass. Holdout = 2022-01-03 -> 2025-09-07; seen = 2025-09-08 on.
Two Avoid windows are excluded (v1 Amendment A.2)."""
from __future__ import annotations

import json

from strategy.futbt.holdout import Holdout, HoldoutRefused, _normalise  # noqa: F401

H = Holdout("CHARTMARK-v2", "holdout_chartmark_v2.json", "CHARTMARK-v2", "REGISTERED_chartmark_v2.md")
H.spend_to, H.seen_from = "2025-09-07", "2025-09-08"
EXCLUDED_WINDOWS = (("2025-02-19", "2025-03-04"), ("2025-06-22", "2025-07-03"))     # NY entry dates


def excluded(day) -> bool:
    d = _normalise(day)
    return any(a <= d <= b for a, b in EXCLUDED_WINDOWS)


_orig = H._write_ledger


def _write(n_locked: int) -> dict:
    rec = _orig(n_locked)
    rec["excluded_entry_windows"] = [list(w) for w in EXCLUDED_WINDOWS]
    H.ledger_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


H._write_ledger = _write
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, is_seen, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.is_seen, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
