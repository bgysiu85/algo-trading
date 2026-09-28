#!/usr/bin/env python3
"""The W16 DVP-v0 holdout: 2024-01-02 onward, locked, spent once, by the
single candidate "DVP-NQ". Board W16-0006, gate G3.
REGISTERED_w16_drift_vwap.md sec 8.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_holdout --status
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_holdout --spend DVP-NQ

WHY DVP-v0 CUTS ITS OWN LEDGER, SEPARATE FROM strategy.w16.holdout's
------------------------------------------------------------------------
sec 8: "Same dates as SB-v0, but its own ledger, holdout_w16_dvp.json. It
is refused by name from every other line's ledger, including SB-v0's
holdout_w16_sb.json ... Two hypotheses on the same dates each get one look
through their own ledger." DVP-v0 and SB-v0 (strategy.w16.holdout) share
the W16-0003 engine and the same ES/NQ 1-minute archive and the same
2024-01-02 lock date, but they are two separate registrations (W16-0006
vs W16-0003) scoring different rules -- spending one must never look like
spending the other, and a runner that reached for holdout_w16_sb.json by
mistake (or vice versa) needs to be refused, not quietly given the wrong
ledger. This module mirrors strategy.w16.holdout's own API 1:1
(split_dates/is_locked/describe/main --status/--spend) so a caller already
familiar with SB-v0's holdout needs nothing new to use this one.

ONE CANDIDATE ONLY, UNLIKE SB-v0's SIX
------------------------------------------------------------------------
SB-v0 scores six cells (three baselines x two markets) and lets any ONE of
them spend its holdout. DVP-v0 registers exactly one scored cell (sec 1:
"Conti's drift-VWAP pullback on NQ ... Scored: NQ only") -- so
ALLOWED_CANDIDATES here is the single string "DVP-NQ", not a set built
from a baseline/market cross product. ES (sec 3.6) is reported only and
can never spend this holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from strategy.w16 import holdout as SB_HOLDOUT

ROOT = Path(__file__).resolve().parents[2]

# Registered in REGISTERED_w16_drift_vwap.md sec 8, same date as SB-v0's
# own LOCK_FROM -- BEFORE any DVP-v0 backtest code existed. Changing it is
# a new registration, not an edit.
LOCK_FROM = "2024-01-02"

# Own ledger -- see module docstring for why this cannot be SB-v0's.
LEDGER_PATH = ROOT / "holdout_w16_dvp.json"

CANDIDATE = "DVP-NQ"
# DVP-v1 (REGISTERED_w16_drift_vwap_v1.md, Ben's W16-0010 decision "B", 2026-09-28):
# Conti's literal rule, out-of-sample, spends this same window -- still ONCE:
# whichever candidate spends first, the other is refused by the ledger check.
CANDIDATE_V1 = "DVP-v1-NQ"
ALLOWED_CANDIDATES = frozenset({CANDIDATE, CANDIDATE_V1})

# Cut files this module refuses to be handed, by name (sec 8: "refused by
# name from every other line's ledger"). Built from strategy.w16.holdout's
# own REFUSED_CUT_NAMES (every OTHER study's ledger already knows about)
# plus that module's own SB-v0 ledger name -- so a runner that reaches for
# the wrong holdout anywhere in the project gets a refusal, not a quiet
# mismatch, and a name added to either module's list going forward does
# not have to be duplicated by hand in the other.
_OWN_NAME = "holdout_w16_dvp.json"
REFUSED_CUT_NAMES = frozenset(
    (SB_HOLDOUT.REFUSED_CUT_NAMES | {SB_HOLDOUT.LEDGER_PATH.name}) - {_OWN_NAME})


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
            f"{name} is not DVP-v0's holdout. DVP-v0 cuts its own at "
            f"strategy.w16.dvp_holdout.LOCK_FROM ({LOCK_FROM}); see "
            "REGISTERED_w16_drift_vwap.md sec 8.")


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
        "note": ("The W16 DVP-v0 holdout is spent. Any further figure "
                 "quoted from 2024-01-02 onward, for DVP-NQ or any of its "
                 "controls, grid neighbours or reported variants, is "
                 "in-sample and is not a holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken). THE
    ONE IMPLEMENTATION strategy.w16.dvp_runner must call.

    Default is the TRAINING side. `dates` is any iterable of date-like
    strings or date-like objects, str()-able to "YYYY-MM-DD" or "YYYY-MM".
    `limit` is refused unconditionally (sec 12: "Reading the holdout with
    --limit, any narrowing flag ... is registered as NOT to be done")."""
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
            "spending the holdout requires a candidate name -- only "
            f"{sorted(ALLOWED_CANDIDATES)} (sec 8: 'Spent once ... only if "
            "it passes sec 9'), and an unnamed spend cannot be recorded as "
            "having happened.")

    if candidate not in ALLOWED_CANDIDATES:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the DVP-v0 holdout. Only "
            f"{sorted(ALLOWED_CANDIDATES)} may (sec 1: 'Scored: NQ only'); "
            "no control, no grid neighbour, no reported-only variant, and "
            "no other market can.")

    prior = read_ledger()
    if prior:
        raise HoldoutRefused(
            f"the DVP-v0 holdout was already spent by {prior['candidate']!r} "
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
    ap = argparse.ArgumentParser(description="The W16 DVP-v0 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help=f"record the holdout as spent by this candidate ({CANDIDATE})")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"DVP-v0 holdout: LOCKED from {LOCK_FROM} (REGISTERED_w16_drift_vwap.md sec 8)")
    print(f"ledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['candidate']!r} at {rec['spent_at']} ({rec['n_locked_days']} days)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")

    if a.spend:
        if a.spend not in ALLOWED_CANDIDATES:
            print(f"\nREFUSED: only {sorted(ALLOWED_CANDIDATES)} may spend this holdout; {a.spend!r} cannot.")
            return 2
        if rec:
            print(f"\nREFUSED: already spent by {rec['candidate']!r}.")
            return 2
        print(f"\nRecording {a.spend!r} as the candidate that spends it. This is a one-way door. Commit the ledger.")
        _write_ledger(a.spend, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
