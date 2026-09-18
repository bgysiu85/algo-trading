#!/usr/bin/env python3
r"""H-S6 -- does the give-back's SHAPE beat a flat daily stop that removes the
same number of trades?

    python -m common.stop_compare

Registered in docs/research/REGISTERED_stop_compare.md, committed in 4ce32d3
before this file existed.

WHY THIS RUNS BEFORE THE HOLDOUT
--------------------------------
`session_scenarios_RESULT_20260918.md` reports MC5's 50% give-back cap clearing
all six of H-S4's readings under both scopes at every friction level -- the
first rule in this project to do that -- and §6 of that registration says a
pass is not adoptable on its own. What H-S4 established is that the cap beats a
RANDOM cut in the sessions it fires on. What it never asked is whether the
peak-relative shape beats the simplest rule in the same family: an absolute
drawdown from zero -- the DAILY LOSS STOP, wanted since 2026-09-12 and never
run. (It is cited as "PROGRAM_INDEX §7 item 11" in REGISTERED_giveback_cap and
in the first draft of this file's own registration; that number is stale in
both, and §0 of REGISTERED_stop_compare.md says so. The rule is named, never
numbered, from here.)

If a flat stop captures the same 78 cents, the peak-relative rule is an
ornament and the two practitioners' 50% is a number without a mechanism. The
holdout is spent once, and this decides which rule it is spent on.

NO SECOND PASS OVER THE TAPE. Both rules are exact post-passes over a finished
book (`session_stop._sweep` says why at length), so this reads the same
`session_scenarios_trades.csv` the H-S4 pass was measured on. The books are
identical by construction, which is the point: nothing here can differ because
the tape was read twice.

THE THRESHOLD IS SOLVED, NEVER CHOSEN (§2). A flat stop has a free parameter
and the give-back does not, so comparing them at an arbitrary $STOP would be a
search wearing a comparison's clothes. For each (strategy, scope, friction)
cell the STOP is solved to remove as close as possible to the same number of
trades the give-back removed. Both rules then spend the same abstention budget
on the same book and only WHICH trades they spend it on differs. FLAT-40,
FLAT-100 and FLAT-200 are printed so the trade-off between threshold and
removal count is visible; §3 says they are never scored and may never be quoted
as the comparator afterwards.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from common import session_stop as SS
from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, share_above_zero
from common.entry_shares import MEASURED_FRICTION
from common.first_entry_skip import (FRICTIONS, deltas_by_symbol_day, money, net,
                                     per_trade)
from common.report_io import emit
from common.session_scenarios import delta_by_session, split_by_book, tagged

REGISTERED = "docs/research/REGISTERED_stop_compare.md"
TRADES = "var/reports/session_scenarios_trades.csv"

PLAIN = ("MCL", "MC5")           # the books H-S4 passed on; 4 and 5 read NOTHING
FIXED = (40.0, 100.0, 200.0)     # §3: reported, never scored
# §4: the two levels H-S4 §7 requires. $1.00 is printed and is not part of any
# verdict -- the measured friction is $4.26 and the honest one is nearer $8.92.
SCORED_AT = ("$4.26", "$8.92")


# --- inputs -----------------------------------------------------------------

def load_books(path: Path) -> dict[str, list[dict]]:
    books: dict[str, list[dict]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["net"] = float(r["net"])
            books[r["book"]].append(r)
    return dict(books)


def load_meta(path: Path) -> dict:
    p = path.with_name(path.stem + "_meta.json")
    return json.loads(p.read_text(encoding="utf-8"))


def input_refusal(meta: dict, books: dict) -> str | None:
    """The incumbent has to be the rule H-S4 actually passed on.

    This file compares a solved flat stop against GB-50 at ARM $40. A trades
    CSV written with different constants describes a different incumbent, and
    the report would still print an ordinary-looking table with "the give-back"
    at the top of it. Refused rather than warned about -- the same rule
    `luck_vs_edge.input_refusal` applies to its own three inputs.
    """
    missing = [b for b in PLAIN if not books.get(b)]
    if missing:
        return (f"the trades CSV has no {', '.join(missing)} book; point --trades at the "
                f"CSV common.session_scenarios wrote (it carries MCL, MCL-pf5, MC5, MC5-pf5)")
    for k, want in (("giveback", SS.GIVEBACK), ("arm", SS.ARM)):
        got = meta.get(k)
        if got is None:
            return (f"the trades CSV's meta does not record {k!r}; it was not written by "
                    f"common.session_scenarios and the incumbent cannot be identified")
        if float(got) != float(want):
            return (f"the trades CSV was written with {k}={got} and this compares against "
                    f"{k}={want}; H-S4 passed on the second, so the first is a different "
                    f"incumbent under the same name")
    return None


# --- one cell ---------------------------------------------------------------

def fired_sessions(res: dict) -> set:
    """The DATE each fire happened on, whatever the scope's key shape -- the
    two scopes key differently and the overlap is read across both."""
    return {k[0] for k in res["fired"]}


def cell(rows: list[dict], strat: str, scope: str, f: float) -> dict:
    """One (strategy, scope, friction) cell: the give-back, the solved flat
    stop matched to its removal count on THIS strategy, and the difference."""
    base = split_by_book(rows).get(strat, [])
    give = SS.apply_cap(rows, SS.GIVEBACK, scope=scope, f=f)
    g_kept = split_by_book(give["kept"]).get(strat, [])
    target = len(base) - len(g_kept)

    out = {"strat": strat, "scope": scope, "f": f, "n_base": len(base),
           "give": give, "g_kept": g_kept, "target": target,
           "d_give": per_trade(g_kept, f) - per_trade(base, f),
           "fixed": []}
    for s in FIXED:
        res = SS.flat_stop(rows, s, scope=scope, f=f)
        kept = split_by_book(res["kept"]).get(strat, [])
        out["fixed"].append({"stop": s, "removed": len(base) - len(kept),
                             "d": per_trade(kept, f) - per_trade(base, f),
                             "sessions": len(res["fired"])})
    if target <= 0:
        # The give-back removed nothing from this strategy in this cell, so
        # there is no budget to match and nothing to compare. Reported as
        # such rather than scored against a stop solved for zero.
        out["solved"] = {"valid": False}
        return out

    sol = SS.solve_stop(rows, target, scope=scope, f=f, of_book=strat)
    out["solved"] = sol
    if not sol["valid"]:
        return out
    flat = SS.flat_stop(rows, sol["stop"], scope=scope, f=f)
    f_kept = split_by_book(flat["kept"]).get(strat, [])
    out["flat"] = flat
    out["f_kept"] = f_kept
    out["d_flat"] = per_trade(f_kept, f) - per_trade(base, f)
    out["diff"] = out["d_give"] - out["d_flat"]

    # §4's bootstrap: the DIFFERENCE between the two gated books, per
    # symbol-day, clustered BY SESSION -- the unit both rules act on, and the
    # same cluster H-S4 reading 5 was corrected to use. The statistic is the
    # resampled TOTAL, which is what `cluster_bootstrap` resamples; the
    # per-trade figures above are the ones §4 orders, and the report prints
    # both rather than letting one stand for the other.
    d = deltas_by_symbol_day(f_kept, g_kept, f)
    boot = cluster_bootstrap(delta_by_session(d), RESAMPLES, SEED)
    out["boot_p"] = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    out["boot_n"] = boot["n_syms"]
    out["total_diff"] = net(g_kept, f) - net(f_kept, f)

    g_days, f_days = fired_sessions(give), fired_sessions(flat)
    out["days"] = {"give": len(g_days), "flat": len(f_days),
                   "both": len(g_days & f_days), "give_only": len(g_days - f_days),
                   "flat_only": len(f_days - g_days)}
    g_rm = [r for r in give["removed"] if r.get("book") == strat]
    f_rm = [r for r in flat["removed"] if r.get("book") == strat]
    out["removed_pt"] = {"give": per_trade(g_rm, f), "flat": per_trade(f_rm, f),
                         "give_n": len(g_rm), "flat_n": len(f_rm)}
    out["clock"] = {"give": SS.fire_clock(give), "flat": SS.fire_clock(flat)}
    return out


def cell_lines(c: dict) -> list[str]:
    L = [f"  {c['strat']}  scope {c['scope']}   {c['n_base']:,} trades in the book"]
    s = c["solved"]
    if not s.get("valid"):
        L.append(f"    the give-back removed {c['target']} {c['strat']} trade(s) here"
                 " -- no budget to match, nothing to compare")
        return L + [""]
    L += [f"    give-back GB-50, arm {money(SS.ARM)}:  removed {c['target']:,}"
          f"   D_give {c['d_give']:+.2f} per remaining trade",
          f"    FLAT-MATCHED, STOP solved to that count:  ${s['stop']:,.2f}"
          f"   removed {s['removed']:,} of a target {s['target']:,}"
          f"   D_flat {c['d_flat']:+.2f}",
          f"      (solved over {s['candidates']:,} achievable depths in "
          f"{s['evaluations']} evaluations; ties go to the larger stop)",
          f"    DIFFERENCE  D_give - D_flat = {c['diff']:+.2f} per trade"
          f"   (totals: {money(c['total_diff'])} over the book)",
          f"    bootstrap of the difference, BY SESSION, {RESAMPLES:,} resamples:"
          f"  P(total > 0) = {c['boot_p']:.3f}  over {c['boot_n']:,} sessions",
          f"    sessions fired on: give-back {c['days']['give']:,}, flat {c['days']['flat']:,},"
          f" both {c['days']['both']:,}, give-back only {c['days']['give_only']:,},"
          f" flat only {c['days']['flat_only']:,}",
          f"    removed per trade: give-back {money(c['removed_pt']['give'])}"
          f" over {c['removed_pt']['give_n']:,}, flat {money(c['removed_pt']['flat'])}"
          f" over {c['removed_pt']['flat_n']:,}"]
    for who in ("give", "flat"):
        clock = c["clock"][who]
        if clock:
            L.append(f"    fire time (ET hour), {who}: "
                     + "  ".join(f"{k} {v}" for k, v in clock.items()))
    L.append("      (H-S4 §5's worry -- the time-of-day filter under another name --"
             " applies to a flat stop at least as much)")
    L.append("    [REPORTED, NEVER SCORED -- §3] fixed stops: "
             + "   ".join(f"FLAT-{int(x['stop'])} removed {x['removed']:,} "
                          f"D {x['d']:+.2f}" for x in c["fixed"]))
    L.append("      (a best cell among these is not a result and is not adoptable;"
             " the comparator is FLAT-MATCHED, fixed before the run)")
    return L + [""]


# --- the verdict ------------------------------------------------------------

def verdict(cells: dict[str, dict]) -> tuple[str, list[str]]:
    """§4, at $4.26 and $8.92. `cells` is {friction label: cell}.

    SURVIVES   D_give > D_flat and the bootstrap >= 0.95 at BOTH levels
    NOTHING    D_flat >= D_give at EITHER level
    UNDECIDED  anything else -- and the holdout is not spent on either rule
    """
    scored = [cells[k] for k in SCORED_AT if k in cells]
    usable = [c for c in scored if c["solved"].get("valid")]
    if len(usable) < len(SCORED_AT):
        return "UNDECIDED", ["not both scored frictions produced a matched stop"]
    if any(c["d_flat"] >= c["d_give"] for c in usable):
        why = ["  ".join(f"{k}: D_give {cells[k]['d_give']:+.2f} vs D_flat "
                         f"{cells[k]['d_flat']:+.2f}" for k in SCORED_AT)]
        return "THE SHAPE ADDS NOTHING", why
    short = [k for k in SCORED_AT if cells[k]["boot_p"] < BOOT_MIN_P]
    why = ["  ".join(f"{k}: difference {cells[k]['diff']:+.2f}, P = "
                     f"{cells[k]['boot_p']:.3f}" for k in SCORED_AT)]
    if short:
        return "UNDECIDED", why + [f"  the bootstrap is short of {BOOT_MIN_P:.2f} at "
                                   + ", ".join(short)]
    return "THE SHAPE SURVIVES", why


def render(books: dict, meta: dict, trades: str) -> list[str]:
    rows_all = tagged(books, PLAIN)
    L = ["DOES THE GIVE-BACK'S SHAPE BEAT A FLAT DAILY STOP? (H-S6)", "",
         f"  registered  {REGISTERED}",
         f"  trades      {trades}  -- the SAME book H-S4 passed on, not a second pass",
         f"  universe    {meta.get('pairs')}   bars {meta.get('dataset')}",
         f"  {len(meta.get('sessions', [])):,} sessions   "
         f"{meta.get('symbol_days', 0):,} symbol-days   "
         f"incumbent GB-{int(SS.GIVEBACK * 100)} at arm {money(SS.ARM)}",
         "  books read: " + "  ".join(f"{b} {len(books[b]):,}" for b in PLAIN), "",
         "  THE COMPARATOR'S THRESHOLD IS SOLVED, NOT CHOSEN (§2): per cell, the",
         "  STOP that removes as close as possible to the number of trades the",
         "  give-back removed. The count comes from the give-back's behaviour and",
         "  never from either rule's P&L, so no stop is selected for performing well.",
         ""]

    by_cell: dict[tuple, dict] = {}
    for label, f in FRICTIONS:
        L += ["=" * 70, f"AT {label} A ROUND TRIP", ""]
        for scope in SS.SCOPES:
            for strat in PLAIN:
                c = cell(rows_all, strat, scope, f)
                by_cell[(strat, scope, label)] = c
                L += cell_lines(c)

    L += ["=" * 70, "THE REGISTERED VERDICT (§4), READ AT $4.26 AND $8.92", ""]
    for scope in SS.SCOPES:
        for strat in PLAIN:
            cells = {lab: by_cell[(strat, scope, lab)] for lab, _ in FRICTIONS}
            tag, why = verdict(cells)
            L += [f"  {strat}  scope {scope}:  {tag}"] + [f"    {w}" for w in why] + [""]

    L += ["", "HOW TO READ A PASS AND A FAIL", "",
          "  THE SHAPE SURVIVES means the peak-relative rule beats a flat stop",
          "  spending the same abstention budget -- and nothing more. Both rules",
          "  still only remove trades from a book that loses per trade.",
          "  THE SHAPE ADDS NOTHING means H-S4's pass measured 'stopping on a bad",
          "  day helps' and not 'the 50% give-back helps'. The flat stop is then",
          "  the simpler rule -- no arm, no ratio, no peak to track live -- and it",
          "  is the one that should be registered instead.", "",
          "WHAT THIS DOES NOT DECIDE", "",
          "  NOTHING SHIPS FROM THIS RUN. holdout.json stays shut; this decides",
          "  WHICH rule is worth the one holdout spend, not the spend itself.",
          "  The live parity requirement in H-S4 §6 stands for whichever survives:",
          "  the live trader must compute `realised` exactly as the backtest does",
          "  before a session-level rule goes near a live session.",
          "  NOT A CAP MODEL. Each symbol-day runs alone and a stop frees",
          "  concurrency slots this cannot price (PROGRAM_INDEX §7 item 15)."]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=TRADES)
    p.add_argument("--out", default="var/reports/stop_compare.txt")
    return p


def main(argv=None) -> int:
    import sys
    a = build_parser().parse_args(argv)
    path = Path(a.trades)
    books = load_books(path)
    meta = load_meta(path)
    refusal = input_refusal(meta, books)
    if refusal:
        sys.exit(f"REFUSING TO RUN: {refusal}")
    emit("\n".join(render(books, meta, a.trades)), a.out,
         header=f"common.stop_compare trades={a.trades} giveback={SS.GIVEBACK} "
                f"arm={SS.ARM} friction={MEASURED_FRICTION} registered={REGISTERED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
