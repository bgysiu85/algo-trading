#!/usr/bin/env python3
"""The W16 session-baselines holdout: 2024-01-02 onward, locked, spent once,
by exactly one of the six scored cells. Board W16-0003 subitem 3, gate G3.
REGISTERED_w16_session_baselines.md sec 8.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.holdout --status
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.holdout --spend B2-ES

WHY W16 CUTS ITS OWN LEDGER
------------------------------------------------------------------------
Same reasoning as strategy/htf/holdout.py's own docstring: this is a
separate registration on a separate market series (ES/NQ 1-minute bars, not
CL 1-hour, not TSMOM's or TL-v0's daily ones), so reusing any other study's
ledger would make one study's spend look like another's when none of the
underlying data or code is shared. REFUSED_CUT_NAMES below lists every
ledger this module has been told, by name, is not its own.

WHY THE CANDIDATE IS "B1-ES" ETC., NOT JUST "B1"
------------------------------------------------------------------------
Sec 8: "Spent once, by ONE CELL" -- and sec 9 scores six cells (B1, B2, B3 x
ES, NQ) independently. Unlike HTF-Ben's holdout (spent by one candidate name
covering two scenarios together, in one call), W16's six cells are never
required to spend together -- exactly one of the six passes or the holdout
goes unspent, and "which one" is itself part of what gets decided (sec 8:
"If more than one passes, Ben chooses which ... If he leaves it to Claude,
the cell with the highest training net per trade at L2 spends it"). So the
candidate string names a (baseline, market) PAIR, and only one of the six
valid pair-strings is ever accepted, once, ever.

WHAT THIS DOES NOT PROTECT
------------------------------------------------------------------------
Same limits as strategy/htf/holdout.py: nothing here stops a caller loading
the raw ES/NQ archive directly and reading bars from 2024-01-02 onward. The
defence is that the backtest runner (strategy.w16.runner) takes its dates
through `split_dates` and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Registered in docs/research/REGISTERED_w16_session_baselines.md sec 8,
# BEFORE any backtest engine code for W16 existed. Changing it is a new
# registration, not an edit.
LOCK_FROM = "2024-01-02"

# Own ledger -- see module docstring for why this cannot be another study's.
LEDGER_PATH = ROOT / "holdout_w16_sb.json"

BASELINES = ("B1", "B2", "B3")
MARKETS = ("ES", "NQ")
ALLOWED_CANDIDATES = frozenset(f"{b}-{m}" for b in BASELINES for m in MARKETS)

# Cut files this module refuses to be handed, by name (sec 8: "refused by
# name from every other line's ledger"), so a runner that reaches for the
# wrong holdout gets a refusal instead of a quiet mismatch.
REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",              # equity (common/holdout.py)
    "holdout_spy.json",                                         # SPY intraday (common/spy_intraday.py)
    "holdout_h60.json",                                         # H60
    "tsmom_holdout_spent.json",                                 # TSMOM
    "tl_v0_holdout_spent.json",                                 # TL-v0
    "holdout_htf_ben.json", "holdout_htf_ben_v1.json",          # HTF-Ben v0/v1
    "holdout_htf_ben_v2.json",                                  # HTF-Ben v2
}


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
            f"{name} is not W16's holdout. W16 cuts its own at "
            f"strategy.w16.holdout.LOCK_FROM ({LOCK_FROM}); see "
            "REGISTERED_w16_session_baselines.md sec 8.")


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
        "note": ("The W16 session-baselines holdout is spent. Any further "
                 "figure quoted from 2024-01-02 onward, for any of the six "
                 "cells (B1/B2/B3 x ES/NQ) or any control or grid neighbour, "
                 "is in-sample and is not a holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken). THE
    ONE IMPLEMENTATION the backtest runner must call.

    Default is the TRAINING side. `dates` is any iterable of date-like
    strings or date-like objects, str()-able to "YYYY-MM-DD" or "YYYY-MM"."""
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
            f"{candidate!r} cannot spend the W16 holdout. Only one of "
            f"{sorted(ALLOWED_CANDIDATES)} may (sec 9's six scored cells); "
            "no control, no grid neighbour, no reported-only variant can.")

    prior = read_ledger()
    if prior:
        raise HoldoutRefused(
            f"the W16 holdout was already spent by {prior['candidate']!r} "
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
    ap = argparse.ArgumentParser(description="The W16 session-baselines holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help=f"record the holdout as spent by this cell (one of {sorted(ALLOWED_CANDIDATES)})")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"W16 holdout: LOCKED from {LOCK_FROM} (REGISTERED_w16_session_baselines.md sec 8)")
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
