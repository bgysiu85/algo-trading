#!/usr/bin/env python3
"""The TL-bounce holdout: 2022-01-03 through the session ending 2025-09-22,
locked, spent once, by TL-bounce (4-hour, 1 MCL, mid friction, the nine
criteria) only. REGISTERED_tl_bounce.md sec 6.

    python -m common.tl_bounce_holdout --status
    python -m common.tl_bounce_holdout --spend TL-bounce

WHY TL-BOUNCE CUTS ITS OWN, SEPARATE FROM TL-v0'S
----------------------------------------------------
Same reasoning as common/tl_v0_holdout.py's own docstring: TL-bounce is a
separate registration on the same market and shares its line code with
TL-v0, so a shared ledger would make one study's spend look like the
other's (a TL-bounce run after TL-v0 already spent its holdout would either
be refused a spend that never happened, or -- if a candidate name collided
-- look like it had already run). Two lines, two locks, two ledgers.

WHY THE START DATE DIFFERS FROM TL-v0's (2022-01-03, not 2022-01-01)
------------------------------------------------------------------------
sec 6, verbatim: "Holdout: sessions from 2022-01-03 through the session
ending 2025-09-22." TL-bounce trades CL 4-hour SESSIONS, not calendar days;
2022-01-01 was a Saturday (no CME session), and 2022-01-03 (Monday) is the
first session date the registration actually names. Using TL-v0's
2022-01-01 boundary here would be silently wrong for a session-dated series
(it happens to coincide after normalisation for TL-v0's own daily-bar
dates, but is not what sec 6 says for TL-bounce) -- so this module does NOT
import LOCK_FROM from common/tl_v0_holdout.py, even though the two dates
are adjacent.

WHY ONLY "TL-bounce" CAN SPEND IT
-------------------------------------
Unlike TL-v0 (two ruleset candidates, v0 and v0-rev, of which only v0-rev
may spend), TL-bounce sec 1-4 registers exactly one candidate rule set (its
five sec 2.5 variants and the C1-C3 controls are fixed, reported, and
"cannot spend the holdout" by name, sec 2.5's own header) -- so the allowed
candidate string is the study's own name, not a ruleset choice.

WHAT "SPENT ONCE" MEANS, AND WHAT IT DOES NOT PROTECT
----------------------------------------------------------
Identical limits to common/tl_v0_holdout.py and common/holdout.py before it:
split_dates(..., spend=True) is the one gate; it refuses any candidate but
"TL-bounce", refuses a second spend, and writes the ledger in the same call
that hands the locked dates over. The ledger is tracked at the repo root
(not gitignored var/), so spending it is a commit. Nothing here stops a
study reading strategy/htf/bars.py's loaders directly for 2022-onward dates
-- the defence is that the backtest runner (W15-0016) is required to route
every date list through split_dates, and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Registered in docs/research/REGISTERED_tl_bounce.md section 6, before any
# TL-bounce backtest code existed. Changing it is a new registration.
LOCK_FROM = "2022-01-03"

LEDGER_PATH = ROOT / "tl_bounce_holdout_spent.json"

# sec 6: "Spent once, by TL-bounce ... only." Not a ruleset choice (unlike
# TL-v0's v0/v0-rev) -- the study itself is the one candidate.
ALLOWED_CANDIDATE = "TL-bounce"

REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",          # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                             # TSMOM's own ledger
    "tl_v0_holdout_spent.json",                             # TL-v0's own ledger (sibling study)
}


class HoldoutRefused(SystemExit):
    pass


def _normalise(day) -> str:
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":
        return d + "-01"
    return d


def is_locked(day) -> bool:
    return _normalise(day) >= LOCK_FROM


def load_for(path) -> None:
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not TL-bounce's holdout. TL-bounce cuts its own at "
            "common.tl_bounce_holdout.LOCK_FROM "
            f"({LOCK_FROM}); see REGISTERED_tl_bounce.md section 6."
        )


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
        "note": ("The TL-bounce holdout is spent. Any further figure quoted "
                 "from 2022-01-03 onward is in-sample for this candidate and "
                 "is not a holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).
    Default is the TRAINING side. See common/tl_v0_holdout.split_dates for
    the identical contract this mirrors."""
    dates = [str(d) for d in dates]

    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not "
            "the holdout, and a narrowed training set silently changes the "
            "sample every criterion in REGISTERED_tl_bounce.md section 4 is "
            "read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent "
            f"ONCE, by {ALLOWED_CANDIDATE!r} ONLY (REGISTERED_tl_bounce.md "
            "section 6), and an unnamed spend cannot be recorded as having "
            "happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the TL-bounce holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} ... only.\" The reported "
            "variants and controls (section 2.5) cannot spend it under any "
            "name.")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        raise HoldoutRefused(
            f"the TL-bounce holdout was already spent by {prior['candidate']!r} "
            f"at {prior['spent_at']}. It is spent once. {candidate!r} cannot "
            f"have it.\nDelete {LEDGER_PATH.name} only if you intend that "
            "deletion to appear in a commit and be defended.")

    keep = [d for d in dates if is_locked(d)]
    if not prior:
        _write_ledger(candidate, len(keep))
    return keep, len(dates) - len(keep), f"LOCKED, from {LOCK_FROM}"


def describe(dates) -> dict:
    dates = sorted(str(d) for d in dates)
    train = [d for d in dates if not is_locked(d)]
    lock = [d for d in dates if is_locked(d)]
    return {
        "lock_from": LOCK_FROM,
        "n_total": len(dates),
        "n_train": len(train),
        "n_locked": len(lock),
        "train_first": train[0] if train else None,
        "train_last": train[-1] if train else None,
        "locked_first": lock[0] if lock else None,
        "locked_last": lock[-1] if lock else None,
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The TL-bounce holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help=f"record the holdout as spent (only {ALLOWED_CANDIDATE!r} is accepted)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"TL-bounce holdout: LOCKED from {LOCK_FROM} "
          f"(REGISTERED_tl_bounce.md section 6)\nledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['candidate']!r} at {rec['spent_at']} "
              f"({rec['n_locked_days']} days)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")

    if a.spend:
        if a.spend != ALLOWED_CANDIDATE:
            print(f"\nREFUSED: only {ALLOWED_CANDIDATE!r} may spend this holdout "
                  f"(section 6); {a.spend!r} cannot.")
            return 2
        if rec and rec["candidate"] != a.spend:
            print(f"\nREFUSED: already spent by {rec['candidate']!r}.")
            return 2
        if rec:
            print(f"\nalready spent by {a.spend!r}; nothing to do.")
            return 0
        print(f"\nRecording {a.spend!r} as the candidate that spends it.")
        print("This is a one-way door. Commit the ledger.")
        _write_ledger(a.spend, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
