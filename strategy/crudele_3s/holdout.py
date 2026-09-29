#!/usr/bin/env python3
"""CRUDELE-3S holdout (REGISTERED_crudele_3s.md sec 6). Ledger holdout_crudele_3s.json, spent once by
the system (daily, 12 markets, mid friction, the ten criteria).

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.crudele_3s.holdout --status
"""
from strategy.futbt.holdout import Holdout, HoldoutRefused  # noqa: F401

H = Holdout("CRUDELE-3S", "holdout_crudele_3s.json", "CRUDELE-3S", "REGISTERED_crudele_3s.md")
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
