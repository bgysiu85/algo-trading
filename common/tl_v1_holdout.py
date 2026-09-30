#!/usr/bin/env python3
"""The TL-v1 holdout: 2022-01-03 through the session ending 2025-09-22,
locked, spent once, by TL-v1 (daily, ensemble, mid friction, the ten
criteria) only. REGISTERED_tl_v1.md sec 6. Board: W15-0019 (G4).

    python -m common.tl_v1_holdout --status
    python -m common.tl_v1_holdout --spend TL-v1

WHY TL-V1 CUTS ITS OWN, SEPARATE FROM TL-v0's AND TL-BOUNCE's
-----------------------------------------------------------------
Same reasoning as common/tl_bounce_holdout.py's own docstring (which gives
the same reasoning relative to common/tl_v0_holdout.py): TL-v1 is a
separate registration built on TL-v0-rev's exits and reusing TL-v0's daily
archive, so a shared ledger would make one study's spend look like
another's. Three lines (TL-v0, TL-bounce, TL-v1) on the same daily/4H CL
data, three separate locks, three separate ledgers. sec 6 also notes TL-v1's
holdout OVERLAPS TL-v0's (both 2022-01-03 -> 2025-09-22): that is expected
and handled at the REPORTING layer (both results are shown together if both
candidates qualify to spend, sec 6, last bullet) -- it is not a reason to
share the ledger file; a shared file would still only tell you ONE of the
two studies spent, not both.

WHY 2022-01-03, NOT 2022-01-01 (as common/tl_v0_holdout.py already explains
for its own boundary, and common/tl_bounce_holdout.py repeats for its own
session-dated series)
-----------------------------------------------------------------------------
sec 6, verbatim: "Holdout: sessions from 2022-01-03 through 2025-09-22."
2022-01-01 was a Saturday (no CME session); 2022-01-03 (Monday) is the
first session date the registration actually names. TL-v1 trades the SAME
daily archive as TL-v0 (sec 2.1: "as TL-v0"), so this boundary happens to
match common.tl_v0_holdout.LOCK_FROM exactly -- but this module does not
import it from there, for the same reason tl_bounce_holdout.py doesn't:
each study's own registration is what fixes its own date, and an import
would make a future edit to one silently move the other.

WHY ONLY "TL-v1" CAN SPEND IT
----------------------------------
sec 6: "Spent once, by TL-v1 (daily, ensemble, mid friction, the ten
criteria)." The sec 2.5 reported variants (TL-v1-A+, TL-v1-A3, TL-v1
2-touch, per-sleeve-alone, the CL 4-hour variant) and the C1-C3 controls
"cannot spend the holdout" by that section's own header -- so, as in
tl_bounce_holdout.py, the allowed candidate string is the study's own name,
not a ruleset choice.

WHAT "SPENT ONCE" MEANS, AND WHAT IT DOES NOT PROTECT
----------------------------------------------------------
Identical contract to common/tl_v0_holdout.py and common/tl_bounce_holdout.py:
split_dates(..., spend=True) is the one gate; it refuses any candidate but
"TL-v1", refuses a second spend, and writes the ledger in the same call
that hands the locked dates over. The ledger is tracked at the repo root
(not gitignored var/), so spending it is a commit. Nothing here stops a
study reading strategy/tl_v0/bars.py's loaders directly for 2022-onward
dates -- the defence is that the backtest runner (W15-0020) is required to
route every date list through split_dates, and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Registered in docs/research/REGISTERED_tl_v1.md section 6, before any
# TL-v1 backtest code existed. Changing it is a new registration.
LOCK_FROM = "2022-01-03"

LEDGER_PATH = ROOT / "tl_v1_holdout_spent.json"

# sec 6: "Spent once, by TL-v1 ... only." Not a ruleset choice -- the study
# itself is the one candidate (as TL-bounce, unlike TL-v0's v0/v0-rev pair).
ALLOWED_CANDIDATE = "TL-v1"

REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",          # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                             # TSMOM's own ledger
    "tl_v0_holdout_spent.json",                             # TL-v0's own ledger (sibling study)
    "tl_bounce_holdout_spent.json",                          # TL-bounce's own ledger (sibling study)
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
            f"{name} is not TL-v1's holdout. TL-v1 cuts its own at "
            "common.tl_v1_holdout.LOCK_FROM "
            f"({LOCK_FROM}); see REGISTERED_tl_v1.md section 6."
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
        "note": ("The TL-v1 holdout is spent. Any further figure quoted "
                 "from 2022-01-03 onward is in-sample for this candidate and "
                 "is not a holdout result, whatever it is called. It "
                 "overlaps TL-v0's own holdout window -- see sec 6: if both "
                 "candidates qualify to spend, both results are reported "
                 "together, and neither is chosen after seeing the other."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def _closed_message(rec: dict) -> str:
    return (f"the TL-v1 holdout is CLOSED-UNSPENT ({rec.get('closed_by', '?')}, "
            f"{rec.get('closed_at', '?')}): it can no longer be spent by anyone. The 2022-01-03 -> "
            "2025-09-22 window belongs to TL-v2's own ledger (holdout_tl_v2.json; "
            "REGISTERED_tl_v2.md section 6) so it is never spent twice. Delete "
            f"{LEDGER_PATH.name} only if you intend that deletion to appear in a commit and be defended.")


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).
    Default is the TRAINING side. Identical contract to
    common/tl_v0_holdout.split_dates and common/tl_bounce_holdout.split_dates."""
    dates = [str(d) for d in dates]

    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not "
            "the holdout, and a narrowed training set silently changes the "
            "sample every criterion in REGISTERED_tl_v1.md section 4 is "
            "read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent "
            f"ONCE, by {ALLOWED_CANDIDATE!r} ONLY (REGISTERED_tl_v1.md "
            "section 6), and an unnamed spend cannot be recorded as having "
            "happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the TL-v1 holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} ... only.\" The reported "
            "variants and controls (section 2.5, section 3) cannot spend it "
            "under any name.")

    prior = read_ledger()
    if prior and prior.get("closed_unspent"):
        raise HoldoutRefused(_closed_message(prior))
    if prior and prior.get("candidate") != candidate:
        raise HoldoutRefused(
            f"the TL-v1 holdout was already spent by {prior['candidate']!r} "
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
    ap = argparse.ArgumentParser(description="The TL-v1 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help=f"record the holdout as spent (only {ALLOWED_CANDIDATE!r} is accepted)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"TL-v1 holdout: LOCKED from {LOCK_FROM} "
          f"(REGISTERED_tl_v1.md section 6)\nledger: {LEDGER_PATH}")
    if rec and rec.get("closed_unspent"):
        print("  CLOSED-UNSPENT (never spent, and no longer spendable)")
        print(f"  {_closed_message(rec)}")
        return 2 if a.spend else 0
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
