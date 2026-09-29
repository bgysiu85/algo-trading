#!/usr/bin/env python3
"""The W16 BB-v0 holdout: 2024-01-02 onward, locked, spent once, by exactly
one of the six scored cells {ABD-NQ, SSS-NQ, TMB-NQ, CRT-NQ, NRS-ES, NRS-NQ}.
Board W16-0008, gate G3. docs/research/REGISTERED_w16_bar_batch.md sec 8.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.bb_holdout --status
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.bb_holdout --spend NRS-NQ

WHY BB-v0 CUTS ITS OWN LEDGER, SEPARATE FROM EVERY OTHER W16 LINE'S
------------------------------------------------------------------------
sec 8: "Same dates as SB-v0 and DVP, but its own ledger, holdout_w16_bb.json.
... Spent once, by one cell." This mirrors strategy.w16.holdout's (SB-v0)
and strategy.w16.dvp_holdout's (DVP-v0/v1) own API 1:1 (split_dates/
is_locked/describe/main --status/--spend) so a caller already familiar
with either needs nothing new to use this one -- and REFUSED_CUT_NAMES is
built the same way dvp_holdout.py builds its own: from SB-v0's own refused
set (which a prior edit there already keeps in sync with every OTHER
study's ledger, DVP's included) plus SB-v0's and DVP's own ledger names,
minus this module's own name -- so a name added to any of those three
lists going forward does not have to be hand-duplicated here.

SIX CANDIDATES, LIKE SB-v0's SIX, UNLIKE DVP-v0's ONE
------------------------------------------------------------------------
sec 9 scores six cells (ABD-NQ, SSS-NQ, TMB-NQ, CRT-NQ, NRS-ES, NRS-NQ) --
so ALLOWED_CANDIDATES is that six-way set, not a single string. Every ES
variant except NRS-ES (ABD-ES, SSS-ES, TMB-ES, CRT-ES) is reported only
(sec 1: "The ES versions of the first four are reported only") and can
never spend this holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from strategy.w16 import dvp_holdout as DVP_HOLDOUT
from strategy.w16 import holdout as SB_HOLDOUT

ROOT = Path(__file__).resolve().parents[2]

# Registered in REGISTERED_w16_bar_batch.md sec 8, same lock date as SB-v0's
# and DVP's own LOCK_FROM -- BEFORE any BB-v0 backtest code existed.
# Changing it is a new registration, not an edit.
LOCK_FROM = "2024-01-02"

# Own ledger -- see module docstring for why this cannot be another study's.
LEDGER_PATH = ROOT / "holdout_w16_bb.json"

CANDIDATES = ("ABD-NQ", "SSS-NQ", "TMB-NQ", "CRT-NQ", "NRS-ES", "NRS-NQ")
ALLOWED_CANDIDATES = frozenset(CANDIDATES)

# Cut files this module refuses to be handed, by name (sec 8: "refused by
# name from every other line's ledger"). Built from SB-v0's own refused set
# (already kept in sync with every OTHER study, DVP included) plus SB-v0's
# and DVP's own ledger names, minus this module's own name.
_OWN_NAME = "holdout_w16_bb.json"
REFUSED_CUT_NAMES = frozenset(
    (SB_HOLDOUT.REFUSED_CUT_NAMES | {SB_HOLDOUT.LEDGER_PATH.name, DVP_HOLDOUT.LEDGER_PATH.name})
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
    """Refuse every other line's cut file by name. See module docstring."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not BB-v0's holdout. BB-v0 cuts its own at "
            f"strategy.w16.bb_holdout.LOCK_FROM ({LOCK_FROM}); see "
            "REGISTERED_w16_bar_batch.md sec 8.")


def read_ledger() -> dict | None:
    if not LEDGER_PATH.exists():
        return None
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _write_ledger(candidate: str, n_locked: int) -> dict:
    rec = {
        "candidate": candidate,
        "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lock_from": LOCK_FROM,
        "n_locked_days": n_locked,
        "note": ("The W16 BB-v0 holdout is spent. Any further figure quoted "
                 "from 2024-01-02 onward, for any of the six cells (ABD-NQ/"
                 "SSS-NQ/TMB-NQ/CRT-NQ/NRS-ES/NRS-NQ) or any control, grid "
                 "neighbour or reported variant, is in-sample and is not a "
                 "holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken). THE
    ONE IMPLEMENTATION strategy.w16.bb_runner must call.

    Default is the TRAINING side. `dates` is any iterable of date-like
    strings or date-like objects, str()-able to "YYYY-MM-DD" or "YYYY-MM".
    `limit` is refused unconditionally (sec 12: "Reading the holdout ...
    with --limit, or any narrowing flag ... is registered as NOT to be
    done")."""
    dates = [str(d) for d in dates]

    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is "
            "not the holdout, and a narrowed training set silently changes "
            "the sample every criterion in sec 9 is read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name -- one of "
            f"{sorted(ALLOWED_CANDIDATES)} (sec 8: 'spent once, by one "
            "cell'), and an unnamed spend cannot be recorded as having happened.")

    if candidate not in ALLOWED_CANDIDATES:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the BB-v0 holdout. Only one of "
            f"{sorted(ALLOWED_CANDIDATES)} may (sec 9's six scored cells); "
            "no control, no grid neighbour, no reported-only variant "
            "(including ABD-ES/SSS-ES/TMB-ES/CRT-ES) can.")

    prior = read_ledger()
    if prior:
        raise HoldoutRefused(
            f"the BB-v0 holdout was already spent by {prior['candidate']!r} "
            f"at {prior['spent_at']}. It is spent once. {candidate!r} cannot "
            f"have it.\nDelete {LEDGER_PATH.name} only if you intend that "
            "deletion to appear in a commit and be defended.")

    keep = [d for d in dates if is_locked(d)]
    _write_ledger(candidate, len(keep))
    return keep, len(dates) - len(keep), f"LOCKED, from {LOCK_FROM}"


def describe(dates) -> dict:
    dates = sorted(str(d) for d in dates)
    train = [d for d in dates if not is_locked(d)]
    lock = [d for d in dates if is_locked(d)]
    return {
        "lock_from": LOCK_FROM, "n_total": len(dates),
        "n_train": len(train), "n_locked": len(lock),
        "train_first": train[0] if train else None,
        "train_last": train[-1] if train else None,
        "locked_first": lock[0] if lock else None,
        "locked_last": lock[-1] if lock else None,
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The W16 BB-v0 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help=f"record the holdout as spent by this cell (one of {sorted(ALLOWED_CANDIDATES)})")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"BB-v0 holdout: LOCKED from {LOCK_FROM} (REGISTERED_w16_bar_batch.md sec 8)")
    print(f"ledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['candidate']!r} at {rec['spent_at']} ({rec['n_locked_days']} days)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")

    if a.spend:
        if a.spend not in ALLOWED_CANDIDATES:
            print(f"\nREFUSED: only one of {sorted(ALLOWED_CANDIDATES)} may spend this holdout; {a.spend!r} cannot.")
            return 2
        if rec:
            print(f"\nREFUSED: already spent by {rec['candidate']!r}.")
            return 2
        print(f"\nRecording {a.spend!r} as the cell that spends it. This is a one-way door. Commit the ledger.")
        _write_ledger(a.spend, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
