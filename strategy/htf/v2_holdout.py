#!/usr/bin/env python3
"""The HTF-Ben v2 holdout: a THREE-way split (training / holdout / seen),
its own ledger, spent once, by v2 on B alone. W15-0021, REGISTERED_htf_ben_v2
.md section 6 (gate G3).

    python -m strategy.htf.v2_holdout --status
    python -m strategy.htf.v2_holdout --spend v2      # only candidate that can

WHY v2 CUTS ITS OWN, DIFFERENT FROM v0's AND v1's
-----------------------------------------------------------------------------
Section 6: "v2 holdout: 2022-01-03 -> 2025-09-22, same window convention as
v1's, but its own cut file and ledger, holdout_htf_ben_v2.json, refused by
name from v0's, v1's, TSMOM's, TL-v0's, H60's and every other line's
ledger... Nothing about the dates is new -- no hypothesis on this line has
ever spent 2022+ data -- but the discipline of a fresh, separately-named
ledger for a fresh hypothesis is the same one v1 used against v0's file,
and is kept here for the same reason." So the boundary dates below are
IDENTICAL in value to v1_holdout.py's own (checked by value, not by
reference, in tests/strategy/htf/test_v2_holdout.py), and REFUSED_CUT_NAMES
carries v1's own ledger name in addition to every cross-study name v1's
module already refused (which itself carried v0's).

WHY ONLY v2 CAN SPEND IT, AND WHY IT IS B ALONE
-----------------------------------------------------------------------------
Section 6: "Spent once, by v2 on B, 1 MCL, mid friction, the same nine
criteria." v2 has no registered ablations (REGISTERED sec 2.4: "None") and
no scenario other than B (sec 2.3) -- so the allow-list here is even
narrower than v1's: no v2-flavoured variant name exists to also refuse,
only the other lines' own names (v0, v1, v1's ablations/controls).

WHAT "SPENT ONCE" MEANS HERE, AND WHAT IT CANNOT MEAN
-----------------------------------------------------------------------------
Same limits as v0's holdout.py and v1_holdout.py (see either module's own
docstring): the holdout side is returned ONLY by split_dates(...,
spend=True), that call REFUSES unless candidate == "v2" and scenarios ==
{"B"}, it REFUSES a second spend once the ledger exists, and it writes the
ledger in the same call that hands the data over. The ledger is TRACKED at
the repo root, not gitignored var/, so spending it is a commit, on Ben's
machine and in every clone.

WHAT THIS DOES NOT PROTECT
-----------------------------------------------------------------------------
Nothing stops a study loading the raw CL.c.0 1-hour archive directly and
reading bars from 2022-01-03 onward. The defence is that the step-7 backtest
runner takes its dates through split_dates and a test asserts that.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Registered in docs/research/REGISTERED_htf_ben_v2.md section 6, BEFORE any
# holdout-spend or scoring code ran against it. Same VALUES as v1's own
# (module docstring), but v2 keeps its own ledger regardless.
HOLDOUT_START = "2022-01-03"   # training ends the day before this
SEEN_START = "2025-09-23"      # holdout ends the day before this

# Own ledger -- see module docstring for why this cannot be v0's, v1's, or
# any other study's.
LEDGER_PATH = ROOT / "holdout_htf_ben_v2.json"

# Section 6: "Spent once, by v2 ... only." v2 has no ablations or controls
# of its own registered as candidates (sec 2.4: "None") -- the refusal list
# is the OTHER lines' names.
ALLOWED_CANDIDATE = "v2"

# Section 6: "by v2 on B" -- not B and A-2H together like v0, and not A-2H
# alone. v2 has no A-2H run at all (sec 2.3), so there is no scenario this
# could ambiguously mean besides B.
REQUIRED_SCENARIOS = frozenset({"B"})

# Cut files this module refuses to be handed, by name -- v1's own holdout
# ledger (section 6: "refused by name from v0's, v1's...") plus every
# cross-study ledger v1's own holdout.py already refused (which itself
# carried v0's), so a v2 runner that reaches for the wrong holdout gets a
# refusal instead of a quiet mismatch.
REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",   # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                     # TSMOM
    "tl_v0_holdout_spent.json",                     # TL-v0
    "holdout_h60_spent.json",                       # H60
    "holdout_htf_ben.json",                         # v0 -- closed unspent
    "holdout_htf_ben_v1.json",                      # v1 -- closed on criterion 5
}


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    """A comparable date string, same padding rule as v1_holdout.py's own
    _normalise: a bare YYYY-MM is padded to its first day so it does not
    sort before a full date that names the same boundary."""
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":          # YYYY-MM
        return d + "-01"
    return d


def is_training(day) -> bool:
    return _normalise(day) < HOLDOUT_START


def is_holdout(day) -> bool:
    d = _normalise(day)
    return HOLDOUT_START <= d < SEEN_START


def is_seen(day) -> bool:
    return _normalise(day) >= SEEN_START


def is_locked(day) -> bool:
    """True for anything NOT training -- holdout or seen alike."""
    return _normalise(day) >= HOLDOUT_START


def load_for(path) -> None:
    """Refuse the equity, TSMOM, TL-v0, H60, v0-HTF-Ben and v1-HTF-Ben cut
    files by name. See module docstring."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not v2's holdout. v2 cuts its own at "
            "strategy.htf.v2_holdout.HOLDOUT_START "
            f"({HOLDOUT_START}); see REGISTERED_htf_ben_v2.md section 6."
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
        "holdout_start": HOLDOUT_START,
        "seen_start": SEEN_START,
        "n_locked_days": n_locked,
        "note": ("The HTF-Ben v2 holdout is spent. Any further figure "
                 f"quoted from {HOLDOUT_START} through the day before "
                 f"{SEEN_START}, for v2 on B (or any control), is "
                 "in-sample and is not a holdout result, whatever it is "
                 "called. The seen window "
                 f"({SEEN_START} onward) is never scored regardless."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                 scenarios=None, limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).

    THE ONE IMPLEMENTATION the step-7 backtest runner must call for the
    training/holdout gate; a test asserts that, same reasoning as
    v1_holdout.py's own module docstring.

    Default (spend=False) is the TRAINING side: everything before
    HOLDOUT_START, which excludes the seen window too (is_locked covers
    both). `dates` is any iterable of date-like strings or
    datetime.date/pd.Timestamp objects.

    The SEEN window is never returned here, spend or no spend -- see
    seen_dates() below, which is ungated (section 6: "reported only, never
    scored", so looking at it needs no spend, only never scoring against
    it).
    """
    dates = [str(d) for d in dates]

    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed holdout set is "
            "not the holdout, and a narrowed training set silently changes "
            "the sample every criterion in REGISTERED_htf_ben_v2.md section "
            "4 is read on.")

    if not spend:
        keep = [d for d in dates if is_training(d)]
        return keep, len(dates) - len(keep), f"training, before {HOLDOUT_START}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent "
            "ONCE, by v2 ONLY, on B alone (REGISTERED_htf_ben_v2.md section "
            "6), and an unnamed spend cannot be recorded as having "
            "happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the v2 holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} on B ... only.\" No "
            "other line's name -- v0, v1, or any of v1's ablations/"
            "controls -- can spend v2's holdout in this registration.")

    scen = frozenset(scenarios) if scenarios is not None else frozenset()
    if scen != REQUIRED_SCENARIOS:
        raise HoldoutRefused(
            "spending the v2 holdout requires scenarios={'B'} alone "
            f"(section 6); got {sorted(scen)!r}. v2 has no other scenario "
            "registered (sec 2.3) and cannot spend the holdout under any "
            "other combination.")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        # Unreachable while ALLOWED_CANDIDATE is a single fixed name, but
        # kept for the same reason v1_holdout.py keeps the equivalent check.
        raise HoldoutRefused(
            f"the v2 holdout was already spent by {prior['candidate']!r} "
            f"at {prior['spent_at']}. It is spent once. {candidate!r} "
            f"cannot have it.\nDelete {LEDGER_PATH.name} only if you intend "
            "that deletion to appear in a commit and be defended.")

    keep = [d for d in dates if is_holdout(d)]
    if not prior:
        _write_ledger(candidate, scen, len(keep))
    return keep, len(dates) - len(keep), f"HOLDOUT, from {HOLDOUT_START} to before {SEEN_START}"


def seen_dates(dates, *, limit: int | None = None) -> list[str]:
    """The seen window (2025-09-23 onward), ungated -- section 6: "reported
    only, never scored." No spend, no ledger, no candidate check: looking
    at it is fine, the discipline is entirely on never scoring or ranking
    against it -- see module docstring's WHAT THIS DOES NOT PROTECT. Still
    refuses `--limit`, same reasoning as split_dates."""
    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on the seen window too: a narrowed seen "
            "window is not the seen window, even though it is never scored.")
    dates = [str(d) for d in dates]
    return [d for d in dates if is_seen(d)]


def describe(dates) -> dict:
    dates = sorted(str(d) for d in dates)
    train = [d for d in dates if is_training(d)]
    hold = [d for d in dates if is_holdout(d)]
    seen = [d for d in dates if is_seen(d)]
    return {
        "holdout_start": HOLDOUT_START,
        "seen_start": SEEN_START,
        "n_total": len(dates),
        "n_train": len(train),
        "n_holdout": len(hold),
        "n_seen": len(seen),
        "train_first": train[0] if train else None,
        "train_last": train[-1] if train else None,
        "holdout_first": hold[0] if hold else None,
        "holdout_last": hold[-1] if hold else None,
        "seen_first": seen[0] if seen else None,
        "seen_last": seen[-1] if seen else None,
        # REGISTERED_htf_ben_v2.md section 3 (as v0/v1): split at the median
        # trade date of the TRAINING side only, so locking the holdout/seen
        # windows does not move it as the archive grows.
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The HTF-Ben v2 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help="record the holdout as spent by this candidate "
                         f"(only {ALLOWED_CANDIDATE!r} is accepted, and it "
                         "spends B alone)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"HTF-Ben v2 holdout: training before {HOLDOUT_START}, HOLDOUT "
          f"{HOLDOUT_START} to before {SEEN_START}, SEEN from {SEEN_START} "
          f"(REGISTERED_htf_ben_v2.md section 6)\nledger: {LEDGER_PATH}")
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
        print(f"\nRecording {a.spend!r} (B alone) as the candidate that "
              "spends it.")
        print("This is a one-way door. Commit the ledger.")
        _write_ledger(a.spend, REQUIRED_SCENARIOS, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
