#!/usr/bin/env python3
r"""common/exec_cost.py -- the shared per-leg friction module (W03-0013).

Ben's decision on W03-0005 (2026-09-28, board W03-0013): **R1 leg-by-leg
pricing replaces the flat $8.92/round-trip as the honest cost level**
(PROGRAM_INDEX rule 6). This module is the one place that pricing lives, so
every study and strategy that needs "the honest cost" reads the same number
instead of carrying its own copy of the flat-friction tuple.

WHAT THIS PROVIDES
-------------------
- `current()`: the live per-leg bps table (mean cost, positive = worse),
  loaded from `var/state/exec_cost_r1.json` -- a measured, refreshable file,
  not a hardcoded constant, so a re-measurement updates every caller with no
  code change.
- `leg_cost_dollars(leg, ref_price, qty)` / `round_trip_cost_dollars(...)`:
  price a trade the R1 way, from the same reference prices W03-0005 used
  (ENTRY from the signal close, TRAIL from the stop level, WCLOSE from the
  exit quote).
- `flat_equivalent_bps(exit_leg=...)`: entry + one exit leg, pooled, for a
  caller that still wants a single number for a report header or a legacy
  `FRICTIONS`-style tuple. This is NOT a replacement for pricing each trade
  leg by leg where the exit reason is known -- it exists only so a caller that
  cannot yet tell which leg exited (see "What this does not do yet") can
  still move off the flat $8.92 onto a measured number.
- `describe()`: one line for a report header, e.g.
  "R1 leg-by-leg pricing (ENTRY (5.4) / TRAIL 140.7 / WCLOSE 95.9 bps,
  measured 2026-09-09 -> 2026-09-25, 13 sessions)".

REFRESH -- re-measure as sessions accumulate
----------------------------------------------
    python -m common.exec_cost --refresh

Re-runs the exact measurement W03-0005 used (`exec_cost_legs.classify` /
`leg_row` / `load_legs` / `means_by_leg` / `resolve_e` -- imported, not
copied) over every live session in `var/fills`, bootstraps a 95% CI per leg,
and writes a new `var/state/exec_cost_r1.json` if anything changed. The
previous state is kept in the file's own `history` list -- nothing is
overwritten silently, so `current()` can always be traced back to the run
that produced it. The registered minimum sample size is still
`exec_cost_legs.MIN_N` (=15 live fills); a leg that has not reached it stops
the refresh with the same message `resolve_e` gives W03-0005 -- there is no
silent fallback to a stale or invented number.

By default the refresh covers every session on disk (`FIRST` fixed at
2026-09-09, per A.2; `--first` overrides it for a deliberately narrower
window). `--last` defaults to the most recent session in `var/fills`, so
running this again next month picks up whatever sessions have accumulated
since, with no date to edit by hand.

WHAT THIS DOES NOT DO YET
----------------------------
This module prices a *known* leg. Wiring it into a specific study or into
the live trader's own reporting (replacing a `FRICTIONS = (("$1.00", 1.00),
("$4.26", 4.26), ("$8.92", 8.92))` tuple with per-leg pricing) is follow-up
work, tracked per-caller on the board under W03-0013 -- each of those call
sites prices a *book* of trades whose exit-reason mix has to be read off the
trade record, which is a change to that study's own P&L loop, not to this
module. `exec_cost_legs.py` itself remains research-only and is not imported
by the trader (PROGRAM_INDEX rule 4/6 do not change how orders are placed).
"""
from __future__ import annotations

import argparse
import json
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from common import exec_cost_legs as _L

STATE_PATH = Path("var/state/exec_cost_r1.json")
LEGS = _L.LEGS                       # ("ENTRY", "TRAIL", "WCLOSE")
SOURCE = ("W03-0005 (docs/research/REGISTERED_exec_cost.md); "
          "refreshed by `python -m common.exec_cost --refresh`")


# ================================================================================
# Reading the current state
# ================================================================================

def current(path: str | Path = STATE_PATH) -> dict:
    """The current per-leg pricing state. Raises if it has never been measured
    -- there is no built-in fallback number, because a made-up "honest" figure
    is the exact thing this module exists to replace."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} does not exist -- run `python -m common.exec_cost --refresh` "
            "once (needs var/fills to hold live sessions), or see "
            "docs/research/REGISTERED_exec_cost.md / W03-0005 for the measured "
            "constants this file should start from."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def leg_bps(leg: str, state: dict | None = None) -> float:
    if leg not in LEGS:
        raise ValueError(f"unknown leg {leg!r}, expected one of {LEGS}")
    return (state or current())["legs"][leg]["mean_bps"]


def leg_cost_dollars(leg: str, ref_price: float, qty: float,
                      state: dict | None = None) -> float:
    """Positive = worse, same sign convention as exec_cost_legs. `ref_price`
    is the leg's own reference (ENTRY: signal close; TRAIL: the stop level;
    WCLOSE: the exit quote), never the fill price -- pricing FROM the fill
    would just reproduce the fill."""
    return ref_price * float(qty) * leg_bps(leg, state) / 10_000.0


def round_trip_cost_dollars(entry_ref: float, exit_ref: float, qty: float,
                             exit_leg: str = "TRAIL",
                             state: dict | None = None) -> float:
    """ENTRY plus whichever exit leg actually happened. `exit_leg` is
    "TRAIL" or "WCLOSE" -- pass the trade's own exit reason, not a guess."""
    state = state or current()
    return (leg_cost_dollars("ENTRY", entry_ref, qty, state)
            + leg_cost_dollars(exit_leg, exit_ref, qty, state))


def flat_equivalent_bps(exit_leg: str = "TRAIL", state: dict | None = None) -> float:
    """A single blended number (ENTRY + one exit leg, pooled) for a caller
    that cannot yet split its trades by exit leg. Prefer
    `round_trip_cost_dollars` wherever the exit reason is known."""
    state = state or current()
    return leg_bps("ENTRY", state) + leg_bps(exit_leg, state)


def describe(state: dict | None = None) -> str:
    state = state or current()
    legs = state["legs"]
    sess = state["sessions"]

    def fmt(bps: float) -> str:
        return f"({abs(bps):.1f})" if bps < 0 else f"{bps:.1f}"

    return (f"R1 leg-by-leg pricing (ENTRY {fmt(legs['ENTRY']['mean_bps'])} / "
            f"TRAIL {fmt(legs['TRAIL']['mean_bps'])} / "
            f"WCLOSE {fmt(legs['WCLOSE']['mean_bps'])} bps, measured "
            f"{sess['first']} -> {sess['last']}, {sess['n_sessions']} sessions)")


# ================================================================================
# Refresh -- re-measure as sessions accumulate
# ================================================================================

def _bootstrap_ci(rows: list[dict], seed: int = _L.SEED,
                   nboot: int = _L.NBOOT) -> dict[str, tuple[float, float]]:
    boot = _L.bootstrap_e(rows, nboot=nboot, seed=seed)
    return {leg: (float(np.percentile(boot[leg], 2.5)),
                  float(np.percentile(boot[leg], 97.5)))
            for leg in LEGS}


def refresh(fills_dir: str | Path = _L.FILLS_DIR, first: str = _L.FIRST,
            last: str | None = None, state_path: str | Path = STATE_PATH,
            write: bool = True) -> dict:
    """Re-run the W03-0005 measurement over every session on disk between
    `first` and `last` (default: the most recent session found), and return
    the new state. Writes `state_path` (moving the previous state into
    `history`) unless `write=False`. Raises `SystemExit` -- via
    `exec_cost_legs.resolve_e` -- if a leg has fewer than the registered
    minimum of live fills, exactly as W03-0005's own run would."""
    fills_dir = Path(fills_dir)
    all_rows = _L.load_legs(fills_dir, first=first, last="9999-99-99")
    sessions = sorted({r["session"] for r in all_rows})
    if not sessions:
        raise RuntimeError(f"no live fills found under {fills_dir} from {first} on")
    last = last or sessions[-1]
    rows = [r for r in all_rows if r["session"] <= last]
    sessions = sorted({r["session"] for r in rows})

    means = _L.means_by_leg(rows)
    e, notes = _L.resolve_e(means)               # raises SystemExit below MIN_N
    ci = _bootstrap_ci(rows)

    state = {
        "version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sessions": {"first": sessions[0], "last": sessions[-1],
                     "n_sessions": len(sessions)},
        "min_n": _L.MIN_N,
        "legs": {
            leg: {"mean_bps": e[leg], "n": means[leg][1],
                  "ci95_bps": [ci[leg][0], ci[leg][1]]}
            for leg in LEGS
        },
        "notes": notes,
        "source": SOURCE,
        "history": [],
    }

    if write:
        p = Path(state_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            prev = json.loads(p.read_text(encoding="utf-8"))
            history = prev.pop("history", [])
            history.append(prev)
            state["history"] = history
        p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


# ================================================================================
# CLI
# ================================================================================

def _main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh", action="store_true",
                     help="re-measure from var/fills and update the state file")
    ap.add_argument("--fills-dir", default=_L.FILLS_DIR)
    ap.add_argument("--first", default=_L.FIRST)
    ap.add_argument("--last", default=None,
                     help="default: the most recent session in --fills-dir")
    ap.add_argument("--out", default=str(STATE_PATH))
    ap.add_argument("--dry-run", action="store_true",
                     help="compute and print, do not write the state file")
    ap.add_argument("--show", action="store_true",
                     help="print the current state and exit")
    args = ap.parse_args()

    if args.show or not args.refresh:
        state = current(args.out)
        print(describe(state))
        print(json.dumps(state, indent=2))
        return

    state = refresh(fills_dir=args.fills_dir, first=args.first, last=args.last,
                     state_path=args.out, write=not args.dry_run)
    print(("[DRY RUN] " if args.dry_run else "") + describe(state))
    for n in state["notes"]:
        print(f"  note: {n}")
    if not args.dry_run:
        print(f"wrote {args.out}")


if __name__ == "__main__":
    _main()
