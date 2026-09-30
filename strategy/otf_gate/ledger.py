#!/usr/bin/env python3
"""One implementation of the W15-0025 holdout ledgers (OTF-G: holdout_otf_gate.json, VA80: holdout_va80.json).

REGISTERED_otf_gate.md sec 6 / REGISTERED_va80.md sec 6:

  OTF-G  H-A   training ..2021-12-31   holdout 2022-01-03 .. 2025-09-22   seen 2025-09-23.. (never scored)
         H-B   training ..2023-12-29   holdout 2024-01-02 .. end of the owned 1-min data
  VA80   ES    training ..2023-12-29   holdout 2024-01-02 .. end of the owned 1-min data

Each ledger is its own file with its own lock ("keys per host"), spent once per host, and only by a host that
passed every sec 4 criterion on training (the caller must say verdict="PASS"; it is written into the ledger).
Every other line's ledger is REFUSED BY NAME (load_for), including the sibling W15-0025 ledger. The code
refuses `limit` and every narrowing keyword: a narrowed sample is not the registered sample.

Training is `day <= train_end`. Days after train_end and before holdout_from (weekends, the New Year gap) are
"gap": they are neither training nor holdout and no runner uses them.

What this does NOT protect: nothing stops code loading the archive directly. The defence is that every runner
takes its dates through `split_dates` and a test asserts it (tests/strategy/otf_gate, tests/strategy/va80).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from strategy.futbt.holdout import OTHER_LINES as _FUTBT_OTHER, OWN_LEDGERS as _FUTBT_OWN
from strategy.w16 import holdout as _W16

ROOT = Path(__file__).resolve().parents[2]

# Every ledger file name this program knows, by name. The two W15-0025 files are listed here so each
# refuses the other; anything a later line adds must be added to its own module and to this set.
EXTRA_LINES = frozenset({
    "holdout_otf_gate.json", "holdout_va80.json", "holdout_w16_sb.json", "holdout_w16_dvp.json",
    "holdout_w16_bb.json",
})


class HoldoutRefused(SystemExit):
    """SystemExit so a runner cannot swallow it as a value error."""


def _day(x) -> str:
    d = str(x)[:10]
    if len(d) == 7 and d[4] == "-":
        d += "-01"
    return d


@dataclass(frozen=True)
class HostWindow:
    candidate: str
    train_end: str                  # last training day, inclusive
    holdout_from: str               # first holdout day (registered)
    spend_to: str | None = None     # last holdout day; None = end of the owned data
    seen_from: str | None = None    # reported only, never scored


class Ledger:
    def __init__(self, label: str, ledger_name: str, registration: str, hosts: dict[str, HostWindow],
                 root: Path = ROOT):
        self.label, self.ledger_name, self.registration, self.hosts = label, ledger_name, registration, hosts
        self.ledger_path = Path(root) / ledger_name
        all_names = set(_FUTBT_OTHER) | set(_FUTBT_OWN) | set(_W16.REFUSED_CUT_NAMES) | set(EXTRA_LINES)
        all_names.add(_W16.LEDGER_PATH.name)
        self.refused = frozenset(all_names - {ledger_name})

    # --- classification -------------------------------------------------
    def window(self, host: str) -> HostWindow:
        if host not in self.hosts:
            raise HoldoutRefused(f"{host!r} is not a {self.label} host; hosts are {sorted(self.hosts)}.")
        return self.hosts[host]

    def classify(self, host: str, day) -> str:
        w, d = self.window(host), _day(day)
        if d <= w.train_end:
            return "train"
        if d < w.holdout_from:
            return "gap"
        if w.seen_from and d >= w.seen_from:
            return "seen"
        if w.spend_to and d > w.spend_to:
            return "after"
        return "holdout"

    def is_locked(self, host: str, day) -> bool:
        return self.classify(host, day) != "train"

    def load_for(self, path) -> None:
        name = Path(path).name
        if name in self.refused:
            raise HoldoutRefused(f"{name} is not the {self.label} holdout ({self.ledger_name}); "
                                 f"see {self.registration} sec 6.")

    # --- ledger file ------------------------------------------------------
    def read_ledger(self) -> dict:
        if not self.ledger_path.exists():
            return {}
        return json.loads(self.ledger_path.read_text(encoding="utf-8"))

    def _write(self, host: str, n_locked: int) -> dict:
        w = self.window(host)
        led = self.read_ledger()
        led[host] = {"candidate": w.candidate, "verdict": "PASS",
                     "spent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "train_end": w.train_end, "holdout_from": w.holdout_from, "holdout_to": w.spend_to,
                     "n_locked_days": n_locked,
                     "note": (f"The {self.label} {host} holdout is spent. Any further figure quoted from "
                              f"{w.holdout_from} onward for this host, or any control, grid neighbour or reported "
                              "variant of it, is in-sample and not a holdout result, whatever it is called.")}
        self.ledger_path.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")
        return led[host]

    # --- the one split ------------------------------------------------------
    def split_dates(self, host: str, dates, *, spend: bool = False, candidate: str | None = None,
                    limit=None, verdict: str | None = None, **narrowing):
        """(dates to use, how many were set aside, which side). Default = TRAINING for `host`."""
        w = self.window(host)
        dates = [str(d) for d in dates]
        if limit is not None or narrowing:
            raise HoldoutRefused("limit / narrowing flags are refused on a holdout split: a narrowed sample "
                                 f"is not the registered sample ({self.registration} sec 6).")
        if not spend:
            keep = [d for d in dates if _day(d) <= w.train_end]
            return keep, len(dates) - len(keep), f"training, through {w.train_end}"
        if candidate != w.candidate:
            raise HoldoutRefused(f"{candidate!r} cannot spend the {self.label} {host} holdout; only "
                                 f"{w.candidate!r} (sec 6).")
        if verdict != "PASS":
            raise HoldoutRefused("the holdout is spent only by a host that passed every sec 4 criterion on "
                                 "training: pass verdict='PASS' to say so (it is written into the ledger).")
        prior = self.read_ledger().get(host)
        if prior:
            raise HoldoutRefused(f"the {self.label} {host} holdout was already spent by {prior['candidate']!r} "
                                 f"at {prior['spent_at']}. It is spent once. Delete the {host} key of "
                                 f"{self.ledger_name} only if you intend that deletion to appear in a commit "
                                 "and be defended.")
        keep = [d for d in dates if self.classify(host, d) == "holdout"]
        self._write(host, len(keep))
        return keep, len(dates) - len(keep), f"LOCKED holdout {w.holdout_from}..{w.spend_to or 'end of data'}"

    def seen_dates(self, host: str, dates):
        """The seen window: reported only, never scored. Label it in every output."""
        return [str(d) for d in dates if self.classify(host, d) == "seen"], "seen -- not evidence"

    def describe(self, host: str, dates) -> dict:
        dates = sorted(str(d) for d in dates)
        train = [d for d in dates if self.classify(host, d) == "train"]
        return {"train_end": self.window(host).train_end, "n_total": len(dates), "n_train": len(train),
                "n_locked": len(dates) - len(train), "train_first": train[0] if train else None,
                "train_last": train[-1] if train else None,
                "both_halves_split": train[len(train) // 2] if train else None}

    def main(self, argv=None) -> int:
        ap = argparse.ArgumentParser(description=f"The {self.label} holdout: status and spend.")
        ap.add_argument("--status", action="store_true")
        ap.add_argument("--spend", metavar="HOST")
        ap.add_argument("--training-passed", action="store_true",
                        help="state that this host passed every sec 4 criterion on training (required to spend)")
        a = ap.parse_args(argv)
        led = self.read_ledger()
        print(f"{self.label} holdout ledger: {self.ledger_path}  ({self.registration} sec 6)")
        for h, w in self.hosts.items():
            print(f"  {h}: training through {w.train_end}; holdout {w.holdout_from} .. {w.spend_to or 'end of data'}"
                  + (f"; seen from {w.seen_from} (never scored)" if w.seen_from else ""))
            print("    SPENT by %r at %s" % (led[h]["candidate"], led[h]["spent_at"]) if h in led else "    UNSPENT")
        if a.spend:
            if a.spend not in self.hosts:
                print(f"\nREFUSED: {a.spend!r} is not a host of this ledger ({sorted(self.hosts)}).")
                return 2
            if a.spend in led:
                print("\nalready spent; nothing to do.")
                return 0
            if not a.training_passed:
                print("\nREFUSED: --training-passed is required (sec 6: only a host that passed every sec 4 criterion).")
                return 2
            print("\nRecording the spend. This is a one-way door. Commit the ledger.")
            self._write(a.spend, 0)
        return 0
