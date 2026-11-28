#!/usr/bin/env python3
"""The W16 OWA-v0 holdout: 2024-01-02 onward, locked, spent once, in one run,
for every cell that passes sec 10. Board W16-0040, gate G3.
docs/research/REGISTERED_w16_open_window.md sec 9.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.owa_holdout --status

OWN LEDGER, holdout_w16_owa.json, refused by name by every other W16 line's
ledger (SB, DVP, BB) and refusing theirs.

NO --spend HERE, UNLIKE THE OTHER W16 LEDGERS
------------------------------------------------------------------------
sec 9: "No cell is re-read, and no failed cell is ever read." Only the
runner knows which cells passed, because it computes the training result in
the same run, so spending happens only through
`strategy.w16.owa_runner --spend-holdout`. A command here that recorded a
spend for a named cell could record one for a cell that had failed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from strategy.w16 import bb_holdout as BB_HOLDOUT
from strategy.w16 import dvp_holdout as DVP_HOLDOUT
from strategy.w16 import holdout as SB_HOLDOUT

ROOT = Path(__file__).resolve().parents[2]

# Registered in REGISTERED_w16_open_window.md sec 9, before any OWA code.
# Changing it is a new registration, not an edit.
LOCK_FROM = "2024-01-02"
# Training runs load no bar dated this day or later (New York date): the
# strongest form of "no NQ intraday bar from 2024 on has been read".
TRAINING_DATA_BEFORE = "2024-01-01"

LEDGER_PATH = ROOT / "holdout_w16_owa.json"

CELLS = ("A-1H", "B-1H", "C-1H", "A-15", "B-15", "C-15")
ALLOWED_CANDIDATES = frozenset(CELLS)

_OWN_NAME = "holdout_w16_owa.json"
REFUSED_CUT_NAMES = frozenset(
    (set(SB_HOLDOUT.REFUSED_CUT_NAMES)
     | set(DVP_HOLDOUT.REFUSED_CUT_NAMES)
     | set(BB_HOLDOUT.REFUSED_CUT_NAMES)
     | {SB_HOLDOUT.LEDGER_PATH.name, DVP_HOLDOUT.LEDGER_PATH.name, BB_HOLDOUT.LEDGER_PATH.name})
    - {_OWN_NAME})


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":          # YYYY-MM
        return d + "-01"
    return d


def is_locked(day) -> bool:
    return _normalise(day) >= LOCK_FROM


def load_for(path) -> None:
    """Refuse every other line's cut file by name."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not OWA-v0's holdout. OWA-v0 cuts its own at "
            f"strategy.w16.owa_holdout.LOCK_FROM ({LOCK_FROM}); see "
            "REGISTERED_w16_open_window.md sec 9.")


def read_ledger() -> dict | None:
    if not LEDGER_PATH.exists():
        return None
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def refuse_if_spent() -> None:
    prior = read_ledger()
    if prior:
        raise HoldoutRefused(
            f"the OWA-v0 holdout was already spent by {prior['cells']} at "
            f"{prior['spent_at']}. It is spent once.\nDelete {LEDGER_PATH.name} only if "
            "you intend that deletion to appear in a commit and be defended.")


def _write_ledger(cells: list[str], n_locked: int) -> dict:
    rec = {
        "cells": cells,
        "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lock_from": LOCK_FROM,
        "n_locked_days": n_locked,
        "note": ("The W16 OWA-v0 holdout is spent. Any further figure quoted from "
                 "2024-01-02 onward for this line -- any cell, control, grid "
                 "neighbour or reported book -- is in-sample and is not a holdout "
                 "result, whatever it is called."),
    }
    with LEDGER_PATH.open("x", encoding="utf-8") as fh:       # "x": never overwrite
        fh.write(json.dumps(rec, indent=2) + "\n")
    return rec


def split_dates(dates, *, spend: bool = False, cells=None, limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken). THE ONE
    IMPLEMENTATION the OWA runner and pre-flight call. Default is the TRAINING
    side. Spending takes the list of ALL cells that passed training."""
    dates = [str(d) for d in dates]

    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not the "
            "holdout, and a narrowed training set silently changes the sample every "
            "criterion in sec 10 is read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if isinstance(cells, str) or not cells:
        raise HoldoutRefused(
            "spending the holdout requires the list of cells that passed sec 10 "
            f"(from {sorted(ALLOWED_CANDIDATES)}); with none passing it is not spent.")
    cells = list(cells)
    bad = [c for c in cells if c not in ALLOWED_CANDIDATES]
    if bad or len(set(cells)) != len(cells):
        raise HoldoutRefused(
            f"{cells} cannot spend the OWA-v0 holdout. Only the six scored cells "
            f"{sorted(ALLOWED_CANDIDATES)} may, each once; no reported book, control "
            "or grid neighbour can.")
    refuse_if_spent()
    keep = [d for d in dates if is_locked(d)]
    if not keep:
        raise HoldoutRefused("there are no locked dates in the data; nothing to spend on.")
    _write_ledger(cells, len(keep))
    return keep, len(dates) - len(keep), f"LOCKED, from {LOCK_FROM}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The W16 OWA-v0 holdout: status.")
    ap.add_argument("--status", action="store_true")
    ap.parse_args(argv)
    rec = read_ledger()
    print(f"OWA-v0 holdout: LOCKED from {LOCK_FROM} (REGISTERED_w16_open_window.md sec 9)")
    print(f"ledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['cells']} at {rec['spent_at']} ({rec['n_locked_days']} days)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
