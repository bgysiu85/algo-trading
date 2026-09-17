#!/usr/bin/env python3
r"""H-S4 -- the session give-back cap, as a forward sweep over a finished book.

Registered in docs/research/REGISTERED_giveback_cap.md (research chat's §0-7,
build chat's amendment A) before this file existed.

THE RULE, from §1:

    For each session, walking the closed trades in time order:
        realised = cumulative realised P&L so far, net of friction
        peak     = running max of realised
        armed    = peak >= ARM
        if armed and realised <= GIVEBACK * peak:
            no further ENTRIES this session

Open positions ride their normal exits, so a trade already open when the trip
fires still books its own P&L. GIVEBACK=None is bit-identical.

WHY THIS IS A POST-PASS AND NOT AN ENGINE CHANGE, AND WHY THAT IS EXACT
----------------------------------------------------------------------
Every other entry rule here (skip_entries, entry_gate, the price floor) has to
go through the engine, because refusing an entry leaves the strategy flat and
LATER BARS BECOME LIVE SIGNALS -- the signal-ordinal cascade. This rule does
not have that problem, and the reason is worth stating rather than assuming:
once the cap trips, NOTHING is entered for the rest of the session. A refused
entry cannot free a later signal, because every later signal is refused too.

So the kept set is exactly the baseline's trades whose entry precedes the trip,
and the trip itself is computed only from trades that closed before it -- all
of which are kept. The sweep is a fixed point, not an approximation, and it
runs off a trades CSV in milliseconds instead of a second pass over the tape.

The one thing this DOES share with every other rule on a losing book: removing
trades improves the total by construction. §2 of the registration exists for
that, and `random_cut` below is the control it demands.

SCOPE (amendment A2). Two different rules, both scored:

    session   one accumulator across every strategy; the trip stops all of them
    strategy  one accumulator per strategy; the trip stops only that one

FRICTION (amendment A5). `realised` is net of friction, so the trip point moves
with it. Every function here takes `f` and the caller recomputes per level; a
cap computed once at $4.26 and re-priced at $8.92 would be a different rule
reported under this one's name.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from common.breadth import SEED
from common.entry_shares import MEASURED_FRICTION

# §1: the arm, fixed in the registration at one average winner rounded down,
# so it cannot be chosen after seeing results. Per 100 shares, in dollars.
ARM = 40.0
GIVEBACK = 0.50                  # §3: the primary cell
CUT_DRAWS = 10_000               # amendment A4: the scored control's draws
SCOPES = ("session", "strategy")


def _key(row: dict, scope: str) -> tuple:
    """What one accumulator covers. `session` pools every strategy on a date;
    `strategy` keeps one per (date, strategy)."""
    if scope == "session":
        return (row["date"],)
    if scope == "strategy":
        return (row["date"], row["book"])
    raise ValueError(f"scope must be one of {SCOPES}, not {scope!r}")


def apply_cap(rows: list[dict], giveback: float | None, *, scope: str = "session",
              arm: float = ARM, f: float = MEASURED_FRICTION) -> dict:
    """The forward sweep. Returns kept rows, removed rows and per-key fire info.

    `rows` need `date`, `book`, `entry_et`, `exit_et`, `net`. Times are the ET
    strings the trade CSVs carry, which sort lexically in clock order within a
    date -- the same property `time_of_day` relies on.

    giveback=None returns every row, untouched and in input order.
    """
    if giveback is None:
        return {"kept": list(rows), "removed": [], "fired": {}, "armed": set(),
                "giveback": None, "scope": scope, "arm": arm, "f": f}

    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[_key(r, scope)].append(r)

    kept, removed, fired, armed = [], [], {}, set()
    for key, group in by_key.items():
        # Entry order decides WHICH trade is judged next; exit order decides
        # WHEN its P&L lands. A trade entered before the trip is kept even if
        # it exits long after -- §1's "open positions ride their normal exits".
        pending = sorted(group, key=lambda r: (r["exit_et"], r["entry_et"]))
        realised = peak = 0.0
        tripped_at = None
        p = n_removed = 0
        for row in sorted(group, key=lambda r: (r["entry_et"], r["exit_et"])):
            # Land every exit that happened before this entry, then decide.
            while p < len(pending) and pending[p]["exit_et"] <= row["entry_et"]:
                realised += float(pending[p]["net"]) - f
                peak = max(peak, realised)
                if peak >= arm:
                    armed.add(key)
                    if realised <= giveback * peak and tripped_at is None:
                        tripped_at = pending[p]["exit_et"]
                p += 1
            if tripped_at is not None:
                removed.append(row)
                n_removed += 1
            else:
                kept.append(row)
        if tripped_at is not None:
            fired[key] = {"at": tripped_at, "peak": peak,
                          "removed": n_removed, "n": len(group)}
    return {"kept": kept, "removed": removed, "fired": fired, "armed": armed,
            "giveback": giveback, "scope": scope, "arm": arm, "f": f}


def per_trade(rows: list[dict], f: float) -> float:
    if not rows:
        return 0.0
    return float(np.mean([float(r["net"]) - f for r in rows]))


def total(rows: list[dict], f: float) -> float:
    return float(sum(float(r["net"]) - f for r in rows))


def random_cut(rows: list[dict], fired_keys, scope: str, f: float,
               draws: int = CUT_DRAWS, seed: int = SEED) -> dict:
    """THE SCORED CONTROL (amendment A4): a random cut in the same sessions.

    For each key the cap fired on, draw a cut point uniformly over that key's
    own trades in entry order and drop everything after it. Matches the SHAPE
    (a tail) and the SESSION; deliberately does NOT match the count, because a
    tail of length k has exactly one position and the registration's "same
    number ... at a random stop point" cannot hold as written.

    Returns the delta distribution AND the mean number of trades removed, which
    the verdict must print: if the control removes more than the cap, the test
    is conservative; if fewer, it is not, and the reading has to say so.
    """
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[_key(r, scope)].append(r)
    groups = [sorted(by_key[k], key=lambda r: (r["entry_et"], r["exit_et"]))
              for k in fired_keys if k in by_key and len(by_key[k]) > 1]
    nets_all = np.array([float(r["net"]) - f for r in rows], dtype=float)
    n_all = len(nets_all)
    if not groups or n_all == 0:
        return {"valid": False, "draws": 0}
    base_pt = nets_all.mean()
    grand = nets_all.sum()

    arrs = [np.array([float(r["net"]) - f for r in g], dtype=float) for g in groups]
    rng = np.random.default_rng(seed)
    d_pt = np.empty(draws)
    n_rm = np.empty(draws)
    for i in range(draws):
        removed_sum = 0.0
        removed_n = 0
        for a in arrs:
            # cut in [1, len(a)-1]: at least one trade kept and one removed,
            # so a "control" that removes nothing cannot dilute the band.
            c = rng.integers(1, len(a))
            removed_sum += a[c:].sum()
            removed_n += len(a) - c
        d_pt[i] = ((grand - removed_sum) / (n_all - removed_n) - base_pt
                   if n_all - removed_n > 0 else 0.0)
        n_rm[i] = removed_n
    q = lambda a, p: float(np.quantile(a, p))                        # noqa: E731
    return {"valid": True, "draws": draws, "keys": len(groups),
            "per_trade": {"p05": q(d_pt, .05), "p50": q(d_pt, .5),
                          "p95": q(d_pt, .95)},
            "removed": {"mean": float(n_rm.mean()), "p05": q(n_rm, .05),
                        "p95": q(n_rm, .95)}}


def fire_clock(res: dict) -> dict[str, int]:
    """Fire time by ET hour -- §4's check that this is not the time-of-day
    filter under another name."""
    out: dict[str, int] = defaultdict(int)
    for info in res["fired"].values():
        # "YYYY-MM-DD HH:MM[:SS]" -> "HH:00". Slicing from the left takes the
        # YEAR, which reads as a plausible hour and is wrong every time.
        stamp = str(info["at"])
        hh = stamp.split(" ")[-1][:2] if " " in stamp else stamp[:2]
        out[f"{hh}:00"] += 1
    return dict(sorted(out.items()))
