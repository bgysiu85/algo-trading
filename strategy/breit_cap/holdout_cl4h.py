#!/usr/bin/env python3
"""BREIT-CAP CL 4-hour secondary book holdout (REGISTERED_breit_cap.md sec 2.5 and 6). Ledger
holdout_breit_cap_cl4h.json. It may spend its own holdout only if that book passed sec 4.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.breit_cap.holdout_cl4h --status
"""
from strategy.futbt.holdout import Holdout, HoldoutRefused  # noqa: F401

H = Holdout("BREIT-CAP CL4H", "holdout_breit_cap_cl4h.json", "BREIT-CAP-CL4H", "REGISTERED_breit_cap.md")
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
