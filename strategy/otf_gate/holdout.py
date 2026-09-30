#!/usr/bin/env python3
"""OTF-G v1 holdout (REGISTERED_otf_gate.md sec 6). Ledger holdout_otf_gate.json, keys per host, each spent once,
and only by a host that passed all six sec 4 criteria on training.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.otf_gate.holdout --status
"""
from strategy.otf_gate.ledger import HostWindow, HoldoutRefused, Ledger  # noqa: F401

H = Ledger("OTF-G", "holdout_otf_gate.json", "REGISTERED_otf_gate.md", {
    "H-A": HostWindow("OTF-G/H-A", train_end="2021-12-31", holdout_from="2022-01-03",
                      spend_to="2025-09-22", seen_from="2025-09-23"),
    "H-B": HostWindow("OTF-G/H-B", train_end="2023-12-29", holdout_from="2024-01-02"),
})
LEDGER_PATH, split_dates, classify, is_locked, load_for, describe, seen_dates = (
    H.ledger_path, H.split_dates, H.classify, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
