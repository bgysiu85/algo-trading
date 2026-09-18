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
        if "book" not in row:
            # The rows the engines produce carry no book name -- `tagged()` in
            # session_scenarios is what stamps it. Under strategy scope an
            # untagged row cannot be attributed, and a KeyError three frames
            # down says nothing about why.
            raise KeyError("strategy scope needs a 'book' on every row; these "
                           "are untagged engine rows (see session_scenarios.tagged)")
        return (row["date"], row["book"])
    raise ValueError(f"scope must be one of {SCOPES}, not {scope!r}")


def _sweep(rows: list[dict], decide, *, scope: str, f: float) -> tuple[list, list, dict]:
    """The forward sweep both session rules are made of.

    `decide(realised, peak) -> bool` is asked once after each exit lands, in
    exit order, and the first True stops entries for the rest of that key.
    The give-back passes its arm-and-ratio test here; the flat stop (H-S6)
    passes an absolute drawdown. Nothing else differs between them, and that
    is the point of the comparison registered in REGISTERED_stop_compare.md:
    two rules spending the same abstention budget through the same machinery.

    Returns (kept, removed, info), where info carries EVERY key -- fired or
    not -- with its final peak, so a caller can read "armed" off the peak
    without the sweep knowing what arming means.
    """
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[_key(r, scope)].append(r)

    kept, removed, info = [], [], {}
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
                if tripped_at is None and decide(realised, peak):
                    tripped_at = pending[p]["exit_et"]
                p += 1
            if tripped_at is not None:
                removed.append(row)
                n_removed += 1
            else:
                kept.append(row)
        info[key] = {"at": tripped_at, "peak": peak,
                     "removed": n_removed, "n": len(group)}
    return kept, removed, info


def apply_cap(rows: list[dict], giveback: float | None, *, scope: str = "session",
              arm: float = ARM, f: float = MEASURED_FRICTION) -> dict:
    """The give-back cap. Returns kept rows, removed rows and per-key fire info.

    `rows` need `date`, `book`, `entry_et`, `exit_et`, `net`. Times are the ET
    strings the trade CSVs carry, which sort lexically in clock order within a
    date -- the same property `time_of_day` relies on.

    giveback=None returns every row, untouched and in input order.
    """
    if giveback is None:
        return {"kept": list(rows), "removed": [], "fired": {}, "armed": set(),
                "giveback": None, "scope": scope, "arm": arm, "f": f}

    def decide(realised: float, peak: float) -> bool:
        return peak >= arm and realised <= giveback * peak

    kept, removed, info = _sweep(rows, decide, scope=scope, f=f)
    # `peak` is a running max, so a key that ever armed still shows it at the
    # end -- reading it off the final peak is the same set, one pass later.
    armed = {k for k, v in info.items() if v["peak"] >= arm}
    fired = {k: v for k, v in info.items() if v["at"] is not None}
    return {"kept": kept, "removed": removed, "fired": fired, "armed": armed,
            "giveback": giveback, "scope": scope, "arm": arm, "f": f}


# --- H-S6: the flat daily stop, and its solved threshold --------------------

def flat_stop(rows: list[dict], stop: float | None, *, scope: str = "session",
              f: float = MEASURED_FRICTION) -> dict:
    """The DAILY LOSS STOP, registered as the comparator in
    REGISTERED_stop_compare.md §1:

        if realised <= -STOP: no further ENTRIES this key

    No arm, no peak, no ratio -- an absolute drawdown from zero. The two rules
    are genuinely different rather than reparametrisations: a session that goes
    +200 then back to +50 trips the give-back and never trips this; a session
    that goes straight to -150 trips this and can never trip the give-back,
    which needs a $40 peak first.

    `stop` is a POSITIVE dollar drawdown. None returns every row untouched.
    """
    if stop is None:
        return {"kept": list(rows), "removed": [], "fired": {}, "armed": set(),
                "stop": None, "scope": scope, "f": f}
    if stop <= 0:
        # A stop of zero fires on the first cent lost and a negative one fires
        # before the session opens. Neither is the rule, and silently accepting
        # one would put a rule in the report under this function's name.
        raise ValueError(f"stop must be a positive drawdown in dollars, not {stop!r}")

    kept, removed, info = _sweep(rows, lambda realised, peak: realised <= -stop,
                                 scope=scope, f=f)
    fired = {k: v for k, v in info.items() if v["at"] is not None}
    return {"kept": kept, "removed": removed, "fired": fired,
            # A flat stop has no arm: every key is eligible from its first
            # trade. `armed` is every key, so the reported armed/fired ratio
            # means the same thing in both tables.
            "armed": set(info), "stop": stop, "scope": scope, "f": f}


def stop_candidates(rows: list[dict], *, scope: str, f: float) -> list[float]:
    """Every drawdown depth at which a flat stop could trip on this book.

    The rule only ever fires at an exit, so the achievable thresholds are the
    negated realised balances at each exit -- nothing between two of them
    changes which trades are removed. Enumerating them makes the solve exact
    rather than a grid search that can land between two counts.

    "Deep enough never to fire" is deliberately NOT in this set. It is always
    available in principle and would be picked whenever the target is small,
    and a comparator that removes nothing scores D_flat = 0 -- handing the
    give-back a win by default on the cells where the comparison matters most.
    Excluding it is the choice against the incumbent, which is the direction
    this file has to err in.
    """
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[_key(r, scope)].append(r)
    out: set[float] = set()
    for group in by_key.values():
        realised = 0.0
        for row in sorted(group, key=lambda r: (r["exit_et"], r["entry_et"])):
            realised += float(row["net"]) - f
            if realised < 0:
                out.add(round(-realised, 6))
    return sorted(out)


def solve_stop(rows: list[dict], target: int, *, scope: str = "session",
               f: float = MEASURED_FRICTION, of_book: str | None = None) -> dict:
    """REGISTERED_stop_compare §2: the threshold is SOLVED, never chosen.

    Find the `STOP` whose flat rule removes as close as possible to `target`
    trades -- the number the give-back removed on the same book. Both rules
    then spend the same abstention budget and only WHICH trades they spend it
    on differs. The count comes from the give-back's behaviour and never from
    either rule's P&L, so no stop is ever selected for performing well.

    Removal count is non-increasing in `STOP` (a deeper stop trips later or
    never, per key, hence in the sum), so the candidate list is searched by
    bisection rather than swept. Ties in |count - target| go to the LARGER
    stop, which is the rule that removes fewer trades -- fixed here, before
    the run, so the tie-break cannot become a choice made on results.

    `of_book` counts only that book's removals. The registered cell is
    (strategy, scope, friction), and under SESSION scope one pooled stop
    removes from both strategies at once; matching on the pooled total would
    leave the strategy actually being read unmatched, which is the one thing
    §2 says must not happen.
    """
    cands = stop_candidates(rows, scope=scope, f=f)
    if not cands or target <= 0:
        return {"valid": False, "stop": None, "removed": 0, "target": target,
                "candidates": len(cands), "evaluations": 0}

    seen: dict[float, int] = {}

    def count(s: float) -> int:
        if s not in seen:
            gone = flat_stop(rows, s, scope=scope, f=f)["removed"]
            seen[s] = (len(gone) if of_book is None
                       else sum(1 for r in gone if r.get("book") == of_book))
        return seen[s]

    # The smallest candidate whose count is <= target. Everything below it
    # removes more, everything above removes the same or fewer.
    lo, hi = 0, len(cands) - 1
    if count(cands[hi]) > target:
        best = cands[hi]                      # even the deepest stop overshoots
    else:
        while lo < hi:
            mid = (lo + hi) // 2
            if count(cands[mid]) <= target:
                hi = mid
            else:
                lo = mid + 1
        best = cands[lo]
        if lo > 0:
            # The neighbour below removes MORE than the target; it wins only
            # if it is strictly closer, so a tie keeps the larger stop.
            under, over = cands[lo], cands[lo - 1]
            if abs(count(over) - target) < abs(count(under) - target):
                best = over
    return {"valid": True, "stop": best, "removed": count(best), "target": target,
            "of_book": of_book, "candidates": len(cands), "evaluations": len(seen)}


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
