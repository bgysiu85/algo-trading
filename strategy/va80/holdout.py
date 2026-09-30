#!/usr/bin/env python3
"""VA80 v1 holdout (REGISTERED_va80.md sec 6). Ledger holdout_va80.json, spent once, only on a seven-of-seven pass.
Same cut as W16 (2024-01-02 onward) but its OWN ledger; holdout_w16_sb.json and holdout_otf_gate.json are refused.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.va80.holdout --status
"""
from strategy.otf_gate.ledger import HostWindow, HoldoutRefused, Ledger  # noqa: F401

H = Ledger("VA80", "holdout_va80.json", "REGISTERED_va80.md", {
    "ES": HostWindow("VA80", train_end="2023-12-29", holdout_from="2024-01-02"),
})
LEDGER_PATH, split_dates, classify, is_locked, load_for, describe = (
    H.ledger_path, H.split_dates, H.classify, H.is_locked, H.load_for, H.describe)

if __name__ == "__main__":
    raise SystemExit(H.main())
