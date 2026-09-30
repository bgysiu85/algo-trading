#!/usr/bin/env python3
"""One implementation of the W15-0022 holdouts (CRUDELE-3S, BREIT-CAP daily, BREIT-CAP CL 4H, MFLAG-v1).

REGISTERED_crudele_3s.md sec 6 / REGISTERED_breit_cap.md sec 6:
  training   2010-06 -> 2021-12-31
  holdout    2022-01-03 -> 2025-09-22, its own cut file and ledger, SPENT ONCE
  seen       2025-09-23 onward: reported only, labelled "seen -- not evidence", never scored
  the code refuses --limit and every narrowing flag; every other line's ledger is refused by name.

Same API and same refusals as strategy/w16/holdout.py (so a caller who knows that one needs nothing
new), built as a small class so the three ledgers cannot drift apart:

    strategy.crudele_3s.holdout   ledger holdout_crudele_3s.json       candidate "CRUDELE-3S"
    strategy.breit_cap.holdout    ledger holdout_breit_cap.json         candidate "BREIT-CAP"
    strategy.breit_cap.holdout_cl4h  ledger holdout_breit_cap_cl4h.json candidate "BREIT-CAP-CL4H"
    strategy.macro_flag.holdout      ledger holdout_macro_flag.json      candidate "MFLAG-v1"

"Only by a book that passed sec 4 on training": the CLI needs --training-passed, and the runner
that spends the holdout (a later item) must call split_dates(spend=True, candidate=..., verdict=
"PASS"). A caller cannot spend without writing the word PASS, which makes the claim explicit and
auditable in the ledger; it cannot verify the verdict itself (nothing here can).

What this does NOT protect: nothing stops code loading the archive directly and reading dates from
2022 onward. The defence is that every runner takes its dates through split_dates and a test
asserts that; the TL-v0 loader (strategy.tl_v0.bars) cuts 2022-01-01 onward before any bar is
built and is what the training runs use.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LOCK_FROM = "2022-01-01"            # registered 2022-01-03 first weekday session; the loader cut
SPEND_TO = "2025-09-22"
SEEN_FROM = "2025-09-23"

OWN_LEDGERS = ("holdout_crudele_3s.json", "holdout_breit_cap.json", "holdout_breit_cap_cl4h.json",
              "holdout_macro_flag.json", "holdout_chartmark_v1.json", "holdout_chartmark_short_v1.json",
              "holdout_chartmark_v2.json")

OTHER_LINES = frozenset({
    "holdout.json", "holdout_pairs_2026H2.json",
    "holdout_spy.json", "spy_holdout_spent.json",
    "holdout_h60.json", "holdout_h60_spent.json",
    "holdout_swing.json",
    "tsmom_holdout_spent.json", "tl_v0_holdout_spent.json", "tl_v1_holdout_spent.json",
    "tl_bounce_holdout_spent.json",
    "holdout_htf_ben.json", "holdout_htf_ben_v1.json", "holdout_htf_ben_v2.json",
    "holdout_w16_sb.json", "holdout_w16_dvp.json", "holdout_w16_bb.json",
})


class HoldoutRefused(SystemExit):
    """SystemExit so a runner cannot swallow it as a value error."""


def _normalise(day) -> str:
    d = str(day)[:10]
    if len(d) == 7 and d[4] == "-":
        return d + "-01"
    return d


class Holdout:
    def __init__(self, label: str, ledger_name: str, candidate: str, registration: str):
        assert ledger_name in OWN_LEDGERS
        self.label, self.candidate, self.registration = label, candidate, registration
        self.ledger_name = ledger_name
        self.ledger_path = ROOT / ledger_name
        self.lock_from, self.spend_to, self.seen_from = LOCK_FROM, SPEND_TO, SEEN_FROM
        self.refused = frozenset((OTHER_LINES | set(OWN_LEDGERS)) - {ledger_name})

    # --- classification -------------------------------------------------
    def is_locked(self, day) -> bool:
        return _normalise(day) >= self.lock_from

    def is_seen(self, day) -> bool:
        return _normalise(day) >= self.seen_from

    def load_for(self, path) -> None:
        name = Path(path).name
        if name in self.refused:
            raise HoldoutRefused(f"{name} is not the {self.label} holdout ({self.ledger_name}); "
                                 f"see {self.registration} sec 6.")

    def read_ledger(self):
        if not self.ledger_path.exists():
            return None
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def _write_ledger(self, n_locked: int) -> dict:
        rec = {"candidate": self.candidate, "verdict": "PASS",
               "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "lock_from": self.lock_from, "holdout_to": self.spend_to, "n_locked_days": n_locked,
               "note": (f"The {self.label} holdout is spent. Any further figure quoted from "
                        f"{self.lock_from} onward for this book or any control, grid neighbour or "
                        "reported variant is in-sample and not a holdout result, whatever it is called.")}
        self.ledger_path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        return rec

    # --- the one split --------------------------------------------------
    def split_dates(self, dates, *, spend: bool = False, candidate: str | None = None,
                    limit=None, verdict: str | None = None, **narrowing):
        """(dates to use, how many were set aside, which side). Default = TRAINING."""
        dates = [str(d) for d in dates]
        if limit is not None or narrowing:
            raise HoldoutRefused("limit / narrowing flags are refused on a holdout split: a narrowed "
                                 "sample is not the registered sample "
                                 f"({self.registration} sec 6).")
        if not spend:
            keep = [d for d in dates if not self.is_locked(d)]
            return keep, len(dates) - len(keep), f"training, before {self.lock_from}"
        if candidate != self.candidate:
            raise HoldoutRefused(f"{candidate!r} cannot spend the {self.label} holdout; only "
                                 f"{self.candidate!r} (sec 6).")
        if verdict != "PASS":
            raise HoldoutRefused("the holdout is spent only by a book that passed sec 4 on training: "
                                 "pass verdict='PASS' to say so (it is written into the ledger).")
        prior = self.read_ledger()
        if prior:
            raise HoldoutRefused(f"the {self.label} holdout was already spent by {prior['candidate']!r} "
                                 f"at {prior['spent_at']}. It is spent once. Delete {self.ledger_name} "
                                 "only if you intend that deletion to appear in a commit and be defended.")
        keep = [d for d in dates if self.lock_from <= _normalise(d) <= self.spend_to]
        self._write_ledger(len(keep))
        return keep, len(dates) - len(keep), f"LOCKED holdout {self.lock_from}..{self.spend_to}"

    def seen_dates(self, dates):
        """The seen window: reported only, never scored. Label it in every output."""
        keep = [str(d) for d in dates if self.is_seen(d)]
        return keep, "seen -- not evidence"

    def describe(self, dates) -> dict:
        dates = sorted(str(d) for d in dates)
        train = [d for d in dates if not self.is_locked(d)]
        return {"lock_from": self.lock_from, "n_total": len(dates), "n_train": len(train),
                "n_locked": len(dates) - len(train), "train_first": train[0] if train else None,
                "train_last": train[-1] if train else None,
                "both_halves_split": train[len(train) // 2] if train else None}

    def main(self, argv=None) -> int:
        ap = argparse.ArgumentParser(description=f"The {self.label} holdout: status and spend.")
        ap.add_argument("--status", action="store_true")
        ap.add_argument("--spend", metavar="CANDIDATE")
        ap.add_argument("--training-passed", action="store_true",
                        help="state that this book passed sec 4 on training (required to spend)")
        a = ap.parse_args(argv)
        rec = self.read_ledger()
        print(f"{self.label} holdout: LOCKED from {self.lock_from}, holdout to {self.spend_to} "
              f"({self.registration} sec 6)\nledger: {self.ledger_path}")
        print(f"  SPENT by {rec['candidate']!r} at {rec['spent_at']}" if rec else "  UNSPENT")
        if a.spend:
            if a.spend != self.candidate:
                print(f"\nREFUSED: only {self.candidate!r} may spend this holdout.")
                return 2
            if rec:
                print("\nalready spent; nothing to do.")
                return 0
            if not a.training_passed:
                print("\nREFUSED: --training-passed is required (sec 6: only a book that passed sec 4).")
                return 2
            print("\nRecording the spend. This is a one-way door. Commit the ledger.")
            self._write_ledger(0)
        return 0
