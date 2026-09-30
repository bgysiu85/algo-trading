#!/usr/bin/env python3
"""MFLAG-v1 holdout (REGISTERED_macro_flag_v1.md sec 6). Ledger holdout_macro_flag.json, spent once, and only
by a book that passed all eight sec 4 criteria on training.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.macro_flag.holdout --status
"""
from strategy.futbt.holdout import Holdout, HoldoutRefused  # noqa: F401

H = Holdout("MFLAG-v1", "holdout_macro_flag.json", "MFLAG-v1", "REGISTERED_macro_flag_v1.md")
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
