#!/usr/bin/env python3
"""BREIT-CAP primary (daily, 12 markets) holdout (REGISTERED_breit_cap.md sec 6). Ledger
holdout_breit_cap.json; spent once, and only by a book that passed sec 4 on training.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.breit_cap.holdout --status
"""
from strategy.futbt.holdout import Holdout, HoldoutRefused  # noqa: F401

H = Holdout("BREIT-CAP", "holdout_breit_cap.json", "BREIT-CAP", "REGISTERED_breit_cap.md")
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
