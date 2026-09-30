#!/usr/bin/env python3
"""The TL-v2 holdout (REGISTERED_tl_v2.md sec 6, gate G3). Board: W15-0030.

    training   2010-06 -> 2021-12-31
    holdout    2022-01-03 -> 2025-09-22, ledger holdout_tl_v2.json, SPENT ONCE, by "TL-v2"
               (daily, ensemble, mid friction) only if all ten criteria pass with criterion 6 at p99
    seen       2025-09-23 onward: reported only, labelled "seen -- not evidence", never scored

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.tl_v2.holdout --status

One implementation (strategy/futbt/holdout.py), the same API and refusals as the other 2026 lines:
refuses --limit and every narrowing flag, refuses every other line's ledger by name (TL-v0, TL-bounce,
TL-v1, TSMOM, HTF-Ben, W16, CRUDELE, BREIT, MFLAG, CHARTMARK, ...), refuses a second spend, and
refuses any candidate but "TL-v2" and any verdict but "PASS". The variants (TL-v2 + S/R, N = 20, each
pivot size alone) and the controls cannot spend it (sec 2.3).

TL-v1's ledger (tl_v1_holdout_spent.json) is CLOSED-UNSPENT in the same commit as this file
(common/tl_v1_holdout.py refuses to spend it), so the 2022-2025 window cannot be spent twice.

What this does NOT protect: nothing stops code loading the archive directly and reading dates from
2022 onward. The defence is that every runner takes its dates through split_dates and a test asserts
that; strategy.tl_v0.bars cuts 2022-01-01 onward before any bar is built and is what the training
runs and the pre-flight use.
"""
from strategy.futbt.holdout import Holdout, HoldoutRefused  # noqa: F401

H = Holdout("TL-v2", "holdout_tl_v2.json", "TL-v2", "REGISTERED_tl_v2.md")
LOCK_FROM, LEDGER_PATH = H.lock_from, H.ledger_path
split_dates, is_locked, load_for, describe, seen_dates = (
    H.split_dates, H.is_locked, H.load_for, H.describe, H.seen_dates)

if __name__ == "__main__":
    raise SystemExit(H.main())
