#!/usr/bin/env python3
"""The TSMOM holdout: 2022-01-01 onward, locked, spent once, enforced here.

    python -m common.tsmom_holdout --status
    python -m common.tsmom_holdout --spend ensemble_k3_6_9_12    # one candidate, ever

WHY TSMOM CUTS ITS OWN, AND WHY IT IS A DATE
---------------------------------------------
`common/holdout.py` splits the SCREENED EQUITY universe by session count and
its `holdout.json` is a list of symbol-days. It does not describe futures and
must not be reused here -- `load_for` below refuses it by name, because the
quiet failure is a futures study calling the equity splitter, getting back
"all (no committed cut)" and reading the locked years while printing an
ordinary-looking number.

The equity cut is a FRACTION of sessions. This one is a fixed CALENDAR DATE,
because the registration already fixed it and gave the reason
(`docs/research/REGISTERED_tsmom.md` section 6):

    2022 is trend-following's best year of the decade. Locking it means the
    in-sample verdict cannot be carried by it, and that spending the holdout
    later is a real test rather than a victory lap.

A fraction would have moved that boundary every time the archive was extended,
which is the same class of defect as a threshold chosen after seeing a result.

WHAT "SPENT ONCE" MEANS HERE, AND WHAT IT CANNOT MEAN
------------------------------------------------------
`common/holdout.py`'s docstring is honest about a limit worth repeating: an
earlier draft promised a counter of reads against the locked set, nothing
incremented it, and the field was removed rather than shipped as decoration.

So this module does not claim to detect a casual read. What it does:

  * the locked side is returned ONLY by `split_months(..., spend=True)`,
  * that call REFUSES unless a candidate name is passed,
  * it REFUSES a second, different candidate once the ledger names one,
  * and it writes the ledger in the same call that hands the data over, so the
    record cannot lag the read.

The ledger is TRACKED at the repo root, not in gitignored var/, so spending it
appears in a diff on Ben's machine and in every clone. That is the control:
not that the code cannot be circumvented, but that circumventing it is a commit.

WHAT THIS DOES NOT PROTECT
---------------------------
Nothing stops a study loading the parquet files directly and reading 2022+.
The defence is that every TSMOM runner takes its dates through `split_months`
and a test asserts that -- the same fix `holdout.split_sessions` got after two
studies were written without it (`PROGRAM_INDEX` section 1).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Registered in docs/research/REGISTERED_tsmom.md section 6, BEFORE any data was
# bought and before any backtest code existed. Changing it is a new
# registration, not an edit.
LOCK_FROM = "2022-01-01"

# Tracked, at the repo root, on the same reasoning as holdout.json: a ledger in
# gitignored var/ can be deleted on one machine and nobody else ever knows.
LEDGER_PATH = ROOT / "tsmom_holdout_spent.json"

# The equity cut. Named here so it can be REFUSED rather than silently accepted.
EQUITY_CUT_NAMES = {"holdout.json", "holdout_pairs_2026H2.json"}


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    """A comparable date string, with a bare YYYY-MM padded to its first day.

    THE BUG THIS EXISTS FOR, found by its own test. The first version compared
    str(day)[:10] >= LOCK_FROM directly. For a bare month that is wrong at
    exactly one place -- the boundary:

        "2022-01" >= "2022-01-01"   ->   False

    because the shorter string sorts first. So January 2022, the first month of
    the holdout, was classified as TRAINING, and a monthly runner passing
    "2022-01" would have read the first month of the locked set while the label
    said "training, before 2022-01-01".

    The docstring originally claimed this was "the correct side of a January 1st
    boundary either way". It asserted the property instead of checking it,
    which is PROGRAM_INDEX section 5's own entry: a report must read its own
    inputs, not assert them.
    """
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":          # YYYY-MM
        return d + "-01"
    return d


def is_locked(day) -> bool:
    return _normalise(day) >= LOCK_FROM


def load_for(path) -> None:
    """Refuse the equity holdout by name.

    A futures study that reaches for `holdout.json` gets a cut over a universe
    of symbol-days that contains no futures at all. `holdout.split_sessions`
    would return everything with the label "all (no committed cut)", which is
    correct for ITS contract and catastrophic here: the locked years would be
    read and the label would look like a reassurance.
    """
    name = Path(path).name
    if name in EQUITY_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is the EQUITY holdout and does not describe futures. "
            "TSMOM cuts its own at common.tsmom_holdout.LOCK_FROM "
            f"({LOCK_FROM}); see REGISTERED_tsmom section 6."
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
        "n_locked_months": n_locked,
        "note": ("The TSMOM holdout is spent. Any further figure quoted from "
                 "2022-01-01 onward is in-sample for this candidate and is "
                 "not a holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_months(months, *, spend: bool = False, candidate: str | None = None,
                 limit: int | None = None):
    """(months to use, how many were set aside, which side was taken).

    THE ONE IMPLEMENTATION. Every TSMOM runner calls this; a test asserts it,
    because `holdout.split_sessions` had to be made the one implementation
    after two studies were written without it and would have read the locked
    slice while printing an ordinary number.

    Default is the TRAINING side. A holdout that can be read casually is not a
    holdout, so `spend=True` is the only path to the locked months and it
    demands a candidate name.

    `months` is any iterable of date-like strings ("2019-03", "2019-03-29",
    datetime.date). A bare YYYY-MM is padded to its first day before comparison
    -- see `_normalise`, which exists because not padding it put January 2022,
    the first month of the holdout, on the training side.
    """
    months = [str(m) for m in months]

    if limit is not None:
        # `--limit` and its relatives are how a locked set gets read "just to
        # check the loader". strategy/premkt/run.py refuses it on the equity
        # holdout for the same reason.
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not "
            "the holdout, and a narrowed training set silently changes the "
            "sample every criterion in REGISTERED_tsmom section 4 is read on.")

    if not spend:
        keep = [m for m in months if not is_locked(m)]
        return keep, len(months) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent ONCE, "
            "by ONE candidate (REGISTERED_tsmom section 6), and an unnamed "
            "spend cannot be recorded as having happened.")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        raise HoldoutRefused(
            f"the TSMOM holdout was already spent by {prior['candidate']!r} at "
            f"{prior['spent_at']}. It is spent once. {candidate!r} cannot have "
            f"it.\nDelete {LEDGER_PATH.name} only if you intend that deletion "
            "to appear in a commit and be defended.")

    keep = [m for m in months if is_locked(m)]
    if not prior:
        _write_ledger(candidate, len(keep))
    return keep, len(months) - len(keep), f"LOCKED, from {LOCK_FROM}"


def describe(months) -> dict:
    months = sorted(str(m) for m in months)
    train = [m for m in months if not is_locked(m)]
    lock = [m for m in months if is_locked(m)]
    return {
        "lock_from": LOCK_FROM,
        "n_total": len(months),
        "n_train": len(train),
        "n_locked": len(lock),
        "train_first": train[0] if train else None,
        "train_last": train[-1] if train else None,
        "locked_first": lock[0] if lock else None,
        "locked_last": lock[-1] if lock else None,
        # The both-halves split of REGISTERED_tsmom section 4 criterion 2, taken
        # over the TRAINING portion only so that locking the holdout does not
        # move it. Split point not swept: it is the median by construction.
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The TSMOM holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help="record the holdout as spent by this candidate")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"TSMOM holdout: LOCKED from {LOCK_FROM} "
          f"(REGISTERED_tsmom section 6)\nledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['candidate']!r} at {rec['spent_at']} "
              f"({rec['n_locked_months']} months)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")

    if a.spend:
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
