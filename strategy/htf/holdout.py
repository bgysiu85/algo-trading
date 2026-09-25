#!/usr/bin/env python3
"""The HTF-Ben holdout: 2022-01-01 onward, locked, spent once, by v0 (B and
A-2H together) only. W15-0004 step 5 (gate G3).

    python -m strategy.htf.holdout --status
    python -m strategy.htf.holdout --spend v0     # only candidate that can

WHY HTF-BEN CUTS ITS OWN, AND WHY IT IS THE SAME DATE AS TSMOM'S / TL-V0'S /
H60'S
-----------------------------------------------------------------------------
REGISTERED_htf_ben_v0.md section 6: "2022-01-01 onward is locked (training =
2010-06-06 -> 2021-12-31, the same cut as TSMOM and TL-v0), with its own cut
file and ledger (holdout_htf_ben.json); the TSMOM, TL-v0, H60 and equity
holdout files are refused by name." The reasoning behind the shared date is
each study's own (2022 is trend-following's best year of the decade, per
REGISTERED_tsmom.md section 6) but HTF-Ben is a separate registration on a
separate market series (CL 1-hour bars, not TSMOM's/TL-v0's daily ones), so it
gets its own ledger -- exactly the reasoning common/tl_v0_holdout.py's module
docstring gives for not reusing common/tsmom_holdout.py's ledger, one more
time: reusing any other study's ledger would make one study's spend look like
another's when none of the underlying data or code is shared.

WHY ONLY v0 CAN SPEND IT, AND WHY B AND A-2H MUST SPEND IT TOGETHER
-----------------------------------------------------------------------------
REGISTERED_htf_ben_v0.md section 6, verbatim: "Spent once, by v0, B (4-hour)
and A-2H together in that one spend." Unlike TL-v0's holdout (one candidate
name, one scenario), HTF-Ben registers two scenarios that both run on the same
locked dates (B on the 4-hour entry chart, A-2H on the 2-hour), and section 4
scores them "separately and reported side by side" -- but section 6 requires
the ONE holdout spend to cover both at once, not a first spend for B today and
a second, separately-decided spend for A-2H tomorrow. So split_dates's `spend`
path here requires an explicit `scenarios` argument that must equal exactly
{"B", "A-2H"} (both, no more, no fewer) -- a caller cannot spend it for one
scenario alone, and cannot spend it under any name split across two calls.
v0-TL, v0-1H, A-1H, A-4H and every control (C1/C2/C3) are reported neighbours
and section 2.6 / section 4 explicitly bar them from spending the holdout, so
only the literal candidate string "v0" is accepted, on the same pattern as
common/tl_v0_holdout.py's ALLOWED_CANDIDATE = "v0-rev".

WHAT "SPENT ONCE" MEANS HERE, AND WHAT IT CANNOT MEAN
-----------------------------------------------------------------------------
Same limits as common/tl_v0_holdout.py, common/tsmom_holdout.py and, before
them, common/holdout.py: this does not detect a casual read of the archive
files directly. What it does: the locked side is returned ONLY by
split_dates(..., spend=True), that call REFUSES unless candidate == "v0" and
scenarios == {"B", "A-2H"}, it REFUSES a second spend once the ledger exists,
and it writes the ledger in the same call that hands the data over. The
ledger is TRACKED at the repo root (not gitignored var/), so spending it is a
commit, on Ben's machine and in every clone.

WHAT THIS DOES NOT PROTECT
-----------------------------------------------------------------------------
Nothing stops a study loading the raw CL.c.0 1-hour archive directly and
reading bars from 2022 onward. The defence is that the step-7 backtest runner
takes its dates through split_dates and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Registered in docs/research/REGISTERED_htf_ben_v0.md section 6, the same
# calendar date as TSMOM's and TL-v0's, BEFORE any backtest engine code for
# HTF-Ben existed. Changing it is a new registration, not an edit.
LOCK_FROM = "2022-01-01"

# Own ledger -- see module docstring for why this cannot be another study's.
LEDGER_PATH = ROOT / "holdout_htf_ben.json"

# Section 6: "Spent once, by v0 ... only." v0-TL, v0-1H and the controls
# (C1/C2/C3) are reported neighbours and section 4 explicitly bars them from
# spending the holdout in this registration.
ALLOWED_CANDIDATE = "v0"

# Section 6: "B (4-hour) and A-2H together in that one spend" -- not one
# scenario now and the other later, and not a superset/subset of these two.
REQUIRED_SCENARIOS = frozenset({"B", "A-2H"})

# Cut files this module refuses to be handed, by name, so an HTF-Ben runner
# that reaches for the wrong holdout gets a refusal instead of a quiet
# mismatch. common/holdout.py's screened-equity cut: a symbol-day list, not
# futures dates. common/tsmom_holdout.py's and common/tl_v0_holdout.py's own
# ledgers, and strategy/h60/holdout.py's: each a different registration's
# spend, not this one's.
REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",             # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                                # TSMOM
    "tl_v0_holdout_spent.json",                                 # TL-v0
    "holdout_h60_spent.json",                                   # H60
}


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    """A comparable date string. HTF-Ben runs on hourly/daily bars, so
    callers already pass full YYYY-MM-DD dates in the ordinary case; a bare
    YYYY-MM is still padded to its first day for the same reason
    common/tsmom_holdout.py and common/tl_v0_holdout.py pad one -- an
    unpadded "2022-01" sorts before "2022-01-01" as a string and would land
    on the training side of the boundary it names.
    """
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":          # YYYY-MM
        return d + "-01"
    return d


def is_locked(day) -> bool:
    return _normalise(day) >= LOCK_FROM


def load_for(path) -> None:
    """Refuse the equity, TSMOM, TL-v0 and H60 cut files by name. See module
    docstring."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not HTF-Ben's holdout. HTF-Ben cuts its own at "
            "strategy.htf.holdout.LOCK_FROM "
            f"({LOCK_FROM}); see REGISTERED_htf_ben_v0.md section 6."
        )


def read_ledger() -> dict | None:
    if not LEDGER_PATH.exists():
        return None
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def _write_ledger(candidate: str, scenarios, n_locked: int) -> dict:
    rec = {
        "candidate": candidate,
        "scenarios": sorted(scenarios),
        "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lock_from": LOCK_FROM,
        "n_locked_days": n_locked,
        "note": ("The HTF-Ben holdout is spent. Any further figure quoted "
                 "from 2022-01-01 onward, for v0 on B or A-2H (or any other "
                 "variant, chart or control), is in-sample and is not a "
                 "holdout result, whatever it is called."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                 scenarios=None, limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).

    THE ONE IMPLEMENTATION the step-7 backtest runner must call; a test
    asserts that, on the same reasoning as common/tsmom_holdout.split_months
    and common/tl_v0_holdout.split_dates -- a runner written without calling
    the one implementation would read the locked slice while printing an
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
            "limit is refused on a holdout split: a narrowed locked set is "
            "not the holdout, and a narrowed training set silently changes "
            "the sample every criterion in REGISTERED_htf_ben_v0.md section "
            "4 is read on.")

    if not spend:
        keep = [d for d in dates if not is_locked(d)]
        return keep, len(dates) - len(keep), f"training, before {LOCK_FROM}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent "
            "ONCE, by v0 ONLY, with B and A-2H together "
            "(REGISTERED_htf_ben_v0.md section 6), and an unnamed spend "
            "cannot be recorded as having happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the HTF-Ben holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} ... only.\" v0-TL, v0-1H "
            "and the controls (C1/C2/C3) are reported neighbours and cannot "
            "spend the holdout in this registration (section 4).")

    scen = frozenset(scenarios) if scenarios is not None else frozenset()
    if scen != REQUIRED_SCENARIOS:
        raise HoldoutRefused(
            "spending the HTF-Ben holdout requires scenarios={'B', 'A-2H'} "
            f"together, in one spend (section 6); got {sorted(scen)!r}. "
            "A-1H, A-4H and every other reported neighbour cannot spend it "
            "either, alone or alongside B/A-2H.")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        # Unreachable while ALLOWED_CANDIDATE is a single fixed name, but
        # kept for the same reason common/tl_v0_holdout.py and
        # common/tsmom_holdout.py keep the equivalent check: if the
        # allowed-candidate rule is ever loosened, this is the backstop that
        # still refuses a second, different spend.
        raise HoldoutRefused(
            f"the HTF-Ben holdout was already spent by {prior['candidate']!r} "
            f"at {prior['spent_at']}. It is spent once. {candidate!r} cannot "
            f"have it.\nDelete {LEDGER_PATH.name} only if you intend that "
            "deletion to appear in a commit and be defended.")

    keep = [d for d in dates if is_locked(d)]
    if not prior:
        _write_ledger(candidate, scen, len(keep))
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
        # REGISTERED_htf_ben_v0.md section 3 item 3: "both halves, split at
        # the median trade date of the training side (split, not swept)" --
        # over the TRAINING portion only, so locking the holdout does not
        # move it as the archive grows.
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The HTF-Ben holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help="record the holdout as spent by this candidate "
                         f"(only {ALLOWED_CANDIDATE!r} is accepted, and it "
                         "spends both B and A-2H together)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"HTF-Ben holdout: LOCKED from {LOCK_FROM} "
          f"(REGISTERED_htf_ben_v0.md section 6)\nledger: {LEDGER_PATH}")
    if rec:
        print(f"  SPENT by {rec['candidate']!r} "
              f"(scenarios={rec.get('scenarios')}) at {rec['spent_at']} "
              f"({rec['n_locked_days']} days)")
        print(f"  {rec['note']}")
    else:
        print("  UNSPENT")

    if a.spend:
        if a.spend != ALLOWED_CANDIDATE:
            print(f"\nREFUSED: only {ALLOWED_CANDIDATE!r} may spend this "
                  f"holdout (section 6); {a.spend!r} cannot.")
            return 2
        if rec and rec["candidate"] != a.spend:
            print(f"\nREFUSED: already spent by {rec['candidate']!r}.")
            return 2
        if rec:
            print(f"\nalready spent by {a.spend!r}; nothing to do.")
            return 0
        print(f"\nRecording {a.spend!r} (B and A-2H together) as the "
              "candidate that spends it.")
        print("This is a one-way door. Commit the ledger.")
        _write_ledger(a.spend, REQUIRED_SCENARIOS, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
