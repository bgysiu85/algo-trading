#!/usr/bin/env python3
"""The HTF-Ben v1 holdout: a THREE-way split (training / holdout / seen),
its own ledger, spent once, by v1 on B alone. W15-0011, REGISTERED_htf_ben_v1
.md section 6 (gate G3).

    python -m strategy.htf.v1_holdout --status
    python -m strategy.htf.v1_holdout --spend v1      # only candidate that can

WHY v1 CUTS ITS OWN, DIFFERENT FROM v0's
-----------------------------------------------------------------------------
strategy/htf/holdout.py (v0's) is a TWO-way split: training vs. everything
from 2022-01-01 onward, locked as one block, spent once by v0 on B and A-2H
TOGETHER. v1 is a separate registration (REGISTERED_htf_ben_v1.md section 6)
with a THREE-way split instead:

  - training: 2010-06-06 -> 2021-12-31 (same start as v0 -- unchanged)
  - holdout:  2022-01-03 through the session ending 2025-09-22 -- v1's own
    cut, spent once, by v1, on scenario B ALONE (not B+A-2H together -- v1
    only scores B; A-2H is reported, not scored, per section 4)
  - seen:     2025-09-23 onward (the W15-0008 trade-map period, Ben's
    annotations, his NinjaTrader paper trades) -- "Never scored; reported
    only" (section 3). Looking at it is fine; scoring or ranking against it
    is not, so it is never gated behind a spend the way the holdout is.

Section 6, verbatim: "v0's ledger holdout_htf_ben.json is closed unspent: v0
failed training (W15-0004), so it never qualified to spend it. Its file is
kept and refused by name, like every other line's." So v1's own
REFUSED_CUT_NAMES carries v0's holdout ledger name in addition to the
cross-study names v0's own module already refused (equity, TSMOM, TL-v0,
H60) -- a v1 runner hitting for the wrong file gets a refusal, not a quiet
mismatch, whichever of those five other studies' ledgers it might have been
handed.

WHY ONLY v1 CAN SPEND IT, AND WHY IT IS B ALONE
-----------------------------------------------------------------------------
Section 6: "Spent once, by v1 on B, 1 MCL, mid friction, the same nine
criteria." Unlike v0's holdout (spent on B and A-2H together, since v0
scored both scenarios), v1's registration (section 4) scores B only -- A-2H
is reported alongside it but never ranked or scored -- so the one holdout
spend covers B alone; a caller cannot spend it for A-2H, and cannot spend it
under any name split across two calls. v1-curl, v1-F1, v1-F2, v1-X (the
ablations, section 2.4) and every control (C1/C2/C3) are reported neighbours
and section 2.4 / section 4 explicitly bar them from spending the holdout,
so only the literal candidate string "v1" is accepted -- same pattern as
holdout.py's ALLOWED_CANDIDATE = "v0".

WHAT "SPENT ONCE" MEANS HERE, AND WHAT IT CANNOT MEAN
-----------------------------------------------------------------------------
Same limits as holdout.py, common/tl_v0_holdout.py, common/tsmom_holdout.py
and common/holdout.py: this does not detect a casual read of the archive
files directly. What it does: the holdout side is returned ONLY by
split_dates(..., spend=True), that call REFUSES unless candidate == "v1" and
scenarios == {"B"}, it REFUSES a second spend once the ledger exists, and it
writes the ledger in the same call that hands the data over. The ledger is
TRACKED at the repo root (not gitignored var/), so spending it is a commit,
on Ben's machine and in every clone.

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

# Registered in docs/research/REGISTERED_htf_ben_v1.md section 6, BEFORE any
# holdout-spend or scoring code ran against it. Changing either boundary is
# a new registration, not an edit.
HOLDOUT_START = "2022-01-03"   # training ends the day before this
SEEN_START = "2025-09-23"      # holdout ends the day before this

# Own ledger -- see module docstring for why this cannot be v0's or any
# other study's.
LEDGER_PATH = ROOT / "holdout_htf_ben_v1.json"

# Section 6: "Spent once, by v1 ... only." The ablations (v1-curl/v1-F1/
# v1-F2/v1-X) and the controls (C1/C2/C3) are reported neighbours and
# section 4 explicitly bars them from spending the holdout in this
# registration.
ALLOWED_CANDIDATE = "v1"

# Section 6: "by v1 on B" -- not B and A-2H together like v0, and not A-2H
# alone (A-2H is reported, never scored, section 4).
REQUIRED_SCENARIOS = frozenset({"B"})

# Cut files this module refuses to be handed, by name -- v0's own holdout
# ledger (section 6: "kept and refused by name, like every other line's")
# plus every cross-study ledger v0's own holdout.py already refused, so a
# v1 runner that reaches for the wrong holdout gets a refusal instead of a
# quiet mismatch.
REFUSED_CUT_NAMES = {
    "holdout.json", "holdout_pairs_2026H2.json",   # equity (common/holdout.py)
    "tsmom_holdout_spent.json",                     # TSMOM
    "tl_v0_holdout_spent.json",                     # TL-v0
    "holdout_h60_spent.json",                       # H60
    "holdout_htf_ben.json",                         # v0 -- closed unspent, section 6
}


class HoldoutRefused(SystemExit):
    """Raised as a SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    """A comparable date string, same padding rule as holdout.py's own
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
    """True for anything NOT training -- holdout or seen alike. Mirrors
    holdout.py's own is_locked so the default (non-spend) path below excludes
    both off-limits buckets with the one check, exactly as v0's does for its
    single locked block."""
    return _normalise(day) >= HOLDOUT_START


def load_for(path) -> None:
    """Refuse the equity, TSMOM, TL-v0, H60 and v0-HTF-Ben cut files by
    name. See module docstring."""
    name = Path(path).name
    if name in REFUSED_CUT_NAMES:
        raise HoldoutRefused(
            f"{name} is not v1's holdout. v1 cuts its own at "
            "strategy.htf.v1_holdout.HOLDOUT_START "
            f"({HOLDOUT_START}); see REGISTERED_htf_ben_v1.md section 6."
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
        "note": ("The HTF-Ben v1 holdout is spent. Any further figure "
                 f"quoted from {HOLDOUT_START} through the day before "
                 f"{SEEN_START}, for v1 on B (or any ablation, chart or "
                 "control), is in-sample and is not a holdout result, "
                 "whatever it is called. The seen window "
                 f"({SEEN_START} onward) is never scored regardless."),
    }
    LEDGER_PATH.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def split_dates(dates, *, spend: bool = False, candidate: str | None = None,
                 scenarios=None, limit: int | None = None):
    """(dates to use, how many were set aside, which side was taken).

    THE ONE IMPLEMENTATION the step-7 backtest runner must call for the
    training/holdout gate; a test asserts that, same reasoning as
    holdout.py's own module docstring -- a runner written without calling
    the one implementation would read the holdout slice while printing an
    ordinary number.

    Default (spend=False) is the TRAINING side: everything before
    HOLDOUT_START, which excludes the seen window too (is_locked covers
    both) -- so a caller that forgets the seen window exists still never
    gets it back as "training". `dates` is any iterable of date-like
    strings ("2019-03-29", a bare "2019-03", or anything str()-able to one
    of those) or datetime.date/pd.Timestamp objects.

    The SEEN window is never returned here, spend or no spend -- see
    seen_dates() below, which is ungated (section 6: "never scored; reported
    only", so looking at it needs no spend, only never scoring against it).
    """
    dates = [str(d) for d in dates]

    if limit is not None:
        # `--limit` and its relatives are how a locked set gets read "just to
        # check the loader" -- refused on both sides, per section 6.
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed holdout set is "
            "not the holdout, and a narrowed training set silently changes "
            "the sample every criterion in REGISTERED_htf_ben_v1.md section "
            "4 is read on.")

    if not spend:
        keep = [d for d in dates if is_training(d)]
        return keep, len(dates) - len(keep), f"training, before {HOLDOUT_START}"

    if not candidate:
        raise HoldoutRefused(
            "spending the holdout requires a candidate name. It is spent "
            "ONCE, by v1 ONLY, on B alone (REGISTERED_htf_ben_v1.md section "
            "6), and an unnamed spend cannot be recorded as having "
            "happened.")

    if candidate != ALLOWED_CANDIDATE:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the v1 holdout. Section 6: "
            f"\"Spent once, by {ALLOWED_CANDIDATE} on B ... only.\" The "
            "ablations (v1-curl/v1-F1/v1-F2/v1-X) and the controls "
            "(C1/C2/C3) are reported neighbours and cannot spend the "
            "holdout in this registration (section 4).")

    scen = frozenset(scenarios) if scenarios is not None else frozenset()
    if scen != REQUIRED_SCENARIOS:
        raise HoldoutRefused(
            "spending the v1 holdout requires scenarios={'B'} alone "
            f"(section 6); got {sorted(scen)!r}. A-2H is reported, never "
            "scored (section 4), and cannot spend the holdout either alone "
            "or alongside B.")

    prior = read_ledger()
    if prior and prior.get("candidate") != candidate:
        # Unreachable while ALLOWED_CANDIDATE is a single fixed name, but
        # kept for the same reason holdout.py keeps the equivalent check: if
        # the allowed-candidate rule is ever loosened, this is the backstop
        # that still refuses a second, different spend.
        raise HoldoutRefused(
            f"the v1 holdout was already spent by {prior['candidate']!r} "
            f"at {prior['spent_at']}. It is spent once. {candidate!r} "
            f"cannot have it.\nDelete {LEDGER_PATH.name} only if you intend "
            "that deletion to appear in a commit and be defended.")

    keep = [d for d in dates if is_holdout(d)]
    if not prior:
        _write_ledger(candidate, scen, len(keep))
    return keep, len(dates) - len(keep), f"HOLDOUT, from {HOLDOUT_START} to before {SEEN_START}"


def seen_dates(dates, *, limit: int | None = None) -> list[str]:
    """The seen window (2025-09-23 onward), ungated -- section 6: "Never
    scored; reported only." No spend, no ledger, no candidate check: looking
    at it is fine, the discipline is entirely on never scoring or ranking
    against it (section 3/4), which this module cannot enforce by itself any
    more than split_dates's own training/holdout gate can stop a direct
    archive read -- see module docstring's WHAT THIS DOES NOT PROTECT. Still
    refuses `--limit`, same reasoning as split_dates: a narrowed seen window
    is not the seen window."""
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
        # REGISTERED_htf_ben_v1.md section 3 (as v0): split at the median
        # trade date of the TRAINING side only, so locking the holdout/seen
        # windows does not move it as the archive grows.
        "both_halves_split": train[len(train) // 2] if train else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The HTF-Ben v1 holdout: status and spend.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--spend", metavar="CANDIDATE",
                    help="record the holdout as spent by this candidate "
                         f"(only {ALLOWED_CANDIDATE!r} is accepted, and it "
                         "spends B alone)")
    a = ap.parse_args(argv)

    rec = read_ledger()
    print(f"HTF-Ben v1 holdout: training before {HOLDOUT_START}, HOLDOUT "
          f"{HOLDOUT_START} to before {SEEN_START}, SEEN from {SEEN_START} "
          f"(REGISTERED_htf_ben_v1.md section 6)\nledger: {LEDGER_PATH}")
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
