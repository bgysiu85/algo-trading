#!/usr/bin/env python3
"""The H60 holdout: the last 20% of sessions, cut once, spent once, by one
rule set chosen by an order fixed before any result. Gate G6.
W14-0003, REGISTERED_h60_v0.md §8.

    python -m strategy.h60.holdout --status
    python -m strategy.h60.holdout --cut          # once, from the bar cache

THE CUT
-------
`holdout_h60.json` (repo root, TRACKED -- cutting it is a commit) records
the first locked session, computed BY RULE from the session list the pull
produced: n_locked = ceil(0.20 x n_sessions), the latest n_locked sessions
by date. The date is not typed anywhere by hand. A second --cut refuses:
re-cutting after a near miss is registered as NOT to be done (§9).
Sessions after the file's last_session (a later top-up of the archive) are
also locked: they were never part of this study's training side.

THE SPEND
---------
Only the highest-priority rule set that passes every §7 criterion on the
training side may spend it (§8 order: MR, DON, TL, ORB, VW9, MC5, MCL). The
spend takes a verdict for ALL SEVEN -- a rule not run (MR-60 before amendment
A, TL-60 before G4) is a False -- and refuses any other candidate. The ledger
`holdout_h60_spent.json` is written in the same call that returns the locked
sessions.

WHAT IT REFUSES
---------------
`limit` and any narrowing on either side; another study's holdout file by
name; a spend with an incomplete verdict set; a second spend.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CUT_PATH = ROOT / "holdout_h60.json"
LEDGER_PATH = ROOT / "holdout_h60_spent.json"
HOLDOUT_FRACTION = 0.20

PRIORITY = ("MR-60", "DON-60", "TL-60", "ORB-60", "VW9-60", "MC5-60", "MCL-60")

REFUSED_NAMES = {"holdout.json", "holdout_spy.json", "holdout_swing.json",
                 "holdout_pairs_2026H2.json", "tl_v0_holdout_spent.json",
                 "tsmom_holdout_spent.json"}


class HoldoutRefused(SystemExit):
    """A SystemExit, so a runner cannot swallow it as an ordinary error."""


def _d(x) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def check_name(path: Path) -> None:
    if Path(path).name in REFUSED_NAMES:
        raise HoldoutRefused(f"{Path(path).name} is another study's holdout. H60 "
                             f"cuts and reads only {CUT_PATH.name} (§8).")


def compute_cut(sessions) -> dict:
    ses = sorted({_d(s) for s in sessions})
    if len(ses) < 10:
        raise HoldoutRefused(f"{len(ses)} sessions is not a sample to cut")
    n_locked = math.ceil(HOLDOUT_FRACTION * len(ses))
    first_locked = ses[len(ses) - n_locked]
    return {
        "rule": "last 20% of sessions in the pulled sample, by date "
                "(REGISTERED_h60_v0.md §8)",
        "n_sessions": len(ses), "n_locked": n_locked, "n_training": len(ses) - n_locked,
        "first_session": ses[0].isoformat(), "last_session": ses[-1].isoformat(),
        "last_training": ses[len(ses) - n_locked - 1].isoformat(),
        "first_locked": first_locked.isoformat(),
    }


def cut(sessions, path: Path | None = None) -> dict:
    """Write the cut. Refuses if one exists -- whatever it says."""
    path = Path(path) if path is not None else CUT_PATH
    check_name(path)
    if path.exists():
        raise HoldoutRefused(
            f"{path.name} already exists (first locked "
            f"{read(path)['first_locked']}). The H60 holdout is cut ONCE; "
            "re-cutting is registered as NOT to be done (§9). Delete it only "
            "in a commit you intend to defend.")
    rec = compute_cut(sessions)
    rec["cut_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return rec


def read(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else CUT_PATH
    check_name(path)
    if not path.exists():
        raise HoldoutRefused(f"{path.name} does not exist: cut the holdout "
                             "(python -m strategy.h60.holdout --cut) before any "
                             "training-side number is computed (gate G6).")
    return json.loads(path.read_text(encoding="utf-8"))


def is_locked(day, rec: dict) -> bool:
    d = _d(day)
    return d >= _d(rec["first_locked"]) or d > _d(rec["last_session"])


def split_sessions(sessions, *, path: Path | None = None, spend: bool = False,
                   candidate: str | None = None, verdicts: dict | None = None,
                   limit: int | None = None, ledger: Path | None = None):
    """(sessions to use, how many were set aside, which side). THE one
    implementation every H60 runner takes its sessions through. Default is
    the TRAINING side."""
    if limit is not None:
        raise HoldoutRefused(
            "limit is refused on a holdout split: a narrowed locked set is not "
            "the holdout, and a narrowed training set silently changes the "
            "sample every §7 criterion is read on.")
    rec = read(path)
    ses = sorted({_d(s) for s in sessions})
    if not spend:
        keep = [s for s in ses if not is_locked(s, rec)]
        return keep, len(ses) - len(keep), f"training, before {rec['first_locked']}"

    allowed = spend_candidate(verdicts)
    if candidate != allowed:
        raise HoldoutRefused(
            f"{candidate!r} cannot spend the H60 holdout. §8: it is spent by the "
            "highest-priority rule set that passes every §7 criterion, which on "
            f"these verdicts is {allowed!r}.")
    ledger = Path(ledger) if ledger else LEDGER_PATH
    if ledger.exists():
        prior = json.loads(ledger.read_text(encoding="utf-8"))
        raise HoldoutRefused(f"the H60 holdout was already spent by "
                             f"{prior['candidate']!r} at {prior['spent_at']}. "
                             "It is spent once.")
    keep = [s for s in ses if is_locked(s, rec)]
    ledger.write_text(json.dumps({
        "candidate": candidate,
        "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_locked": rec["first_locked"], "n_locked_sessions": len(keep),
        "verdicts": {k: bool(v) for k, v in verdicts.items()},
        "note": "The H60 holdout is spent. Any later figure from these sessions "
                "is in-sample for every rule set, whatever it is called.",
    }, indent=2) + "\n", encoding="utf-8")
    return keep, len(ses) - len(keep), f"LOCKED, from {rec['first_locked']}"


def spend_candidate(verdicts: dict | None) -> str:
    """The one rule set allowed to spend the holdout, from a complete verdict
    set (rule -> passed every §7 criterion on the training side)."""
    if verdicts is None or set(verdicts) != set(PRIORITY):
        missing = sorted(set(PRIORITY) - set(verdicts or {}))
        raise HoldoutRefused(f"a spend needs a verdict for all seven rule sets; "
                             f"missing {missing}. A rule not run is False.")
    for r in PRIORITY:
        if verdicts[r] is True:
            return r
    raise HoldoutRefused("no rule set passed every §7 criterion on the training "
                         "side: nothing may spend the holdout (§11's reading).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The H60 holdout: status and cut.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--cut", action="store_true",
                    help="cut from the bar cache's session list (once)")
    ap.add_argument("--archive", help="H60 archive root (default: "
                    "<shared Databento archive>/H60)")
    a = ap.parse_args(argv)
    if a.cut:
        from strategy.h60.run import session_list
        rec = cut(session_list(a.archive))
        print(json.dumps(rec, indent=2))
        print(f"\nWrote {CUT_PATH}. Commit it: the cut is now fixed.")
        return 0
    if CUT_PATH.exists():
        rec = read()
        print(f"H60 holdout: first locked {rec['first_locked']} "
              f"({rec['n_locked']} of {rec['n_sessions']} sessions)")
    else:
        print("H60 holdout: NOT CUT")
    if LEDGER_PATH.exists():
        led = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        print(f"  SPENT by {led['candidate']!r} at {led['spent_at']}")
    else:
        print("  UNSPENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
