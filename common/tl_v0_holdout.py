#!/usr/bin/env python3
"""The TL-v0 holdout: 2022-01-01 onward, locked, spent once, by v0-rev only.

    python -m common.tl_v0_holdout --status
    python -m common.tl_v0_holdout --spend v0-rev   # the only candidate that can

WHY TL-v0 CUTS ITS OWN, AND WHY IT IS THE SAME DATE AS TSMOM'S
-----------------------------------------------------------------
REGISTERED_tl_v0.md section 6: "2022-01-01 onward is locked, the same cut as
TSMOM, but TL-v0 writes and enforces its own cut file; the TSMOM and equity
holdout files are refused by name." TSMOM's TSMOM-specific reason for the
date (2022 is trend-following's best year of the decade) applies here
verbatim -- TL-v0 is also a trend-following method on the same markets -- but
the two studies are separate registrations, so TL-v0 gets its own ledger.
Reusing common/tsmom_holdout.py's ledger would make one study's spend look
like the other's: a TL-v0 backtest run after TSMOM already spent its holdout
would read TSMOM's ledger, see it spent, and either refuse a TL-v0 candidate
that has never actually spent anything, or (if the candidate name happened to
collide) look like it had already run when it had not. Two locks, one date,
never one ledger.

WHY ONLY v0-rev CAN SPEND IT
------------------------------
REGISTERED_tl_v0.md section 6, verbatim: "Spent once, by v0-rev only." v0-rev
is the registered holdout candidate (section 2.2); v0 is its reported
neighbour and "cannot spend the holdout in this registration" (section 4).
So unlike common/tsmom_holdout.py, which accepts whichever single candidate
name spends it first, this module refuses every candidate except the literal
string "v0-rev" -- a second study cannot even attempt to spend this holdout
under a different name, mis-typed or otherwise.

WHAT "SPENT ONCE" MEANS HERE, AND WHAT IT CANNOT MEAN
------------------------------------------------------
Same limits as common/tsmom_holdout.py and, before it, common/holdout.py: this
does not detect a casual read of the parquet/dbn files directly. What it
does: the locked side is returned ONLY by split_dates(..., spend=True), that
call REFUSES unless candidate == "v0-rev", it REFUSES a second spend once the
ledger exists, and it writes the ledger in the same call that hands the data
over. The ledger is TRACKED at the repo root (not gitignored var/), so
spending it is a commit, on Ben's machine and in every clone.

WHAT THIS DOES NOT PROTECT
---------------------------
Nothing stops a study loading common/tl_v0_data.py's held_series() directly
and reading dates from 2022 onward. The defence is that the step-4 backtest
runner takes its dates through split_dates and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Registered in docs/research/REGISTERED_tl_v0.md section 6, the same
# calendar date as TSMOM's, BEFORE any backtest code for TL-v0 existed.
# Changing it is a new registration, not an edit.
LOCK_FROM = "2022-01-01"

# Own ledger -- see module docstring for why this cannot be tsmom_holdout's.
LEDGER_PATH = ROOT / "tl_v0_holdout_spent.json"

# Section 6: "Spent once, by v0-rev only." Not "by whichever candidate asks
# first" (that is TSMOM's rule, common/tsmom_holdout.py) -- v0 is explicitly
# barred from spending this holdout at all (section 4).
ALLOWED_CANDIDATE = "v0-rev"

# Cut files this module refuses to be handed, by name, so a TL-v0 runner that
# reaches for the wrong holdout gets a refusal instead of a quiet mismatch.
# common/holdout.py's screened-equity cut: a symbol-day list, not futures
# dates, and would return "all (no committed cut)" for any date list handed
# to it. common/tsmom_holdout.py's own ledger and TSMOM's locked-months
# convention: a different registration's spend, not this one's.
REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",           # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                              # TSMOM's own ledger
}


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    """A comparable date string. TL-v0 runs on daily bars, so callers already
    pass full YYYY-MM-DD dates in the ordinary case; a bare YYYY-MM is still
    padded to its first day for the same reason common/tsmom_holdout.py pads
    one -- an unpadded "2022-01" sorts before "2022-01-01" as a string and
    would land on the training side of the boundary it names.
    """
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":          # YYYY-MM
        return d + "-01"
    return d


def is_locked(day) -> bool:
    return _normalise(day) >= LOCK_FROM


def load_for(path) -> None:
    """Refuse the equity and TSMOM cut files by name. See module docstring."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not TL-v0's holdout. TL-v0 cuts its own at "
            "common.tl_v0_holdout.LOCK_FROM "
            f"({LOCK_FROM}); see REGISTERED_tl_v0.md section 6."
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
        "note": ("The TL-v0 holdout is spent. Any further figure quoted from "
                 "2022-01-01 onward is in-sample for this candidate and is "
                 "not a holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                 limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).

    THE ONE IMPLEMENTATION the step-4 backtest runner must call; a test
    asserts that, on the same reasoning as common/tsmom_holdout.split_months
    -- two TSMOM studies were once written without calling the one
    implementation and would have read the locked slice while printing an
    ordinary number.

    Default is the TRAINING side. `dates` is any iterable of date-like
    strings ("2019-03-29", a bare "2019-03", or anything str()-able to one of
    those) or datetime.date/pd.Timestamp objects.
    """
    dates = [str(d) for d in dates]

    if limit is not None:
        # `--limit` and its relatives are how a locked set gets read "just to
        # check the loader" -- refused on both sides, per section 6.
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not "
            "the holdout, and a narrowed training set silently changes the "
            "sample every criterion in REGISTERED_tl_v0.md section 4 is read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent ONCE, "
            "by v0-rev ONLY (REGISTERED_tl_v0.md section 6), and an unnamed "
            "spend cannot be recorded as having happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the TL-v0 holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} only.\" v0 is scored "
            "against the same bar and reported, but cannot spend the holdout "
            "in this registration (section 4).")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        # Unreachable while ALLOWED_CANDIDATE is a single fixed name, but kept
        # for the same reason common/tsmom_holdout.py keeps the equivalent
        # check: if the allowed-candidate rule is ever loosened, this is the
        # backstop that still refuses a second, different spend.
        raise HoldoutRefused(
            f"the TL-v0 holdout was already spent by {prior['candidate']!r} at "
            f"{prior['spent_at']}. It is spent once. {candidate!r} cannot have "
            f"it.\nDelete {LEDGER_PATH.name} only if you intend that deletion "
            "to appear in a commit and be defended.")

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
        # REGISTERED_tl_v0.md section 3 item 2: "split at the median date of
        # the training sample, split not swept" -- over the TRAINING portion
        # only, so locking the holdout does not move it as the archive grows.
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The TL-v0 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help="record the holdout as spent by this candidate (only "
                         f"{ALLOWED_CANDIDATE!r} is accepted)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"TL-v0 holdout: LOCKED from {LOCK_FROM} "
          f"(REGISTERED_tl_v0.md section 6)\nledger: {LEDGER_PATH}")
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
