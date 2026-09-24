#!/usr/bin/env python3
r"""H-C1 -- the entry-count cap: no 4th-or-later entry per strategy per symbol-day.

    python -m common.entry_cap
    python -m common.entry_cap --csv var/reports/dist_from_high_gate_trades.csv --out var/reports/entry_cap.txt

Registered in docs/research/REGISTERED_entry_cap.md (commit ecf93a5) before
this file existed. W03-0008.

NO NEW SIMULATION, AND THAT IS EXACT, NOT AN APPROXIMATION. Both published
engines are causal and hold one position per symbol at a time, so trade k of
a symbol-day depends only on bars up to its own exit. A rule that refuses
every entry after the Nth cannot change trades 1..N and leaves nothing after
them: the capped book IS the baseline with every trade of in-book ordinal > N
removed. Unlike H-B1 there is no cascade, and the report prints the count of
capped-book entries absent from the baseline, which must be zero.

The books are the ungated MCL and MC5 baselines written by
common.dist_from_high_gate on 2026-09-23 over screen_pairs_pit_itch_v2.json /
XNAS.ITCH (6,411 symbol-days, 550 sessions). The population check stops the
run unless they count 3,908 and 6,462 (registration §2).

Readings: common.gate_study.verdict, the five inherited from
REGISTERED_range_rank §3, unchanged. Reported beside, not scored: the
POSITIONAL control (same symbol-days, same count removed, random positions),
removed vs kept, the ordinal table, entry time of day of removed vs kept.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from common.breadth import SEED
from common.entry_shares import MEASURED_FRICTION
from common.first_entry_skip import (FRICTIONS, TOP, book_block, money, net, per_trade,
                                     population_lines)
from common.gate_study import ABSTENTION_DRAWS, ABSTENTION_Q, verdict, verdict_block
from common.report_io import emit

REGISTERED = "docs/research/REGISTERED_entry_cap.md"
SOURCE = "var/reports/dist_from_high_gate_trades.csv"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
EXPECT = {"MCL": 3_908, "MC5": 6_462}      # §2: the published v2 baselines, or stop
PRIMARY = 3                                # §1: no 4th entry
SCORED = (PRIMARY, 2, 4)                   # §3: primary, then the two boundaries
REPORTED = (1,)                            # §3: reported, not scored
STRATS = ("MCL", "MC5")
LATE = "08:00"                             # §4: the time-of-day row's split


# --- the books ----------------------------------------------------------------------

def load_books(path: str | Path, names=STRATS) -> dict[str, list[dict]]:
    """The named baseline books from a gate_study trades CSV, in file order."""
    books: dict[str, list[dict]] = {n: [] for n in names}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] in books:
                books[r["book"]].append({
                    "symbol": r["symbol"], "date": r["date"], "ordinal": int(r["ordinal"]),
                    "entry_et": r["entry_et"], "entry_px": float(r["entry_px"]),
                    "exit_et": r["exit_et"], "exit_px": float(r["exit_px"]),
                    "reason": r["reason"], "bars_held": int(r["bars_held"]),
                    "net": float(r["net"])})
    return books


def check_ordinals(rows) -> list[str]:
    """Every symbol-day's ordinals must run 1..n with no gap or repeat, or the
    cap-by-ordinal is not the cap-by-count the registration describes."""
    by: dict[tuple, list[int]] = {}
    for r in rows:
        by.setdefault((r["symbol"], r["date"]), []).append(r["ordinal"])
    bad = [k for k, v in by.items() if sorted(v) != list(range(1, len(v) + 1))]
    return [f"{s} {d}" for s, d in bad]


def cap(rows, max_entries: int) -> tuple[list, list]:
    """(kept, removed): the capped book, and the baseline trades the cap refuses."""
    kept = [r for r in rows if r["ordinal"] <= max_entries]
    removed = [r for r in rows if r["ordinal"] > max_entries]
    return kept, removed


# --- the positional control (reported, not scored) -----------------------------------

def positional(base, max_entries: int, f: float = MEASURED_FRICTION,
               draws: int = ABSTENTION_DRAWS, seed: int = SEED) -> dict:
    """For every symbol-day the cap touches, remove the SAME NUMBER of trades
    from that SAME symbol-day at random positions. Returns the quantiles of the
    resulting delta per remaining trade. Beating reading 5 says 'better than
    trading less'; beating this says 'late entries in a busy name are worse
    than any entries in a busy name'."""
    by: dict[tuple, list[float]] = {}
    for r in base:
        by.setdefault((r["symbol"], r["date"]), []).append(r["net"] - f)
    n = len(base)
    total = sum(v for vals in by.values() for v in vals)
    k = sum(max(0, len(v) - max_entries) for v in by.values())
    if n == 0 or k == 0 or k >= n:
        return {"valid": False, "k": k, "n": n}
    rng = np.random.default_rng(seed)
    removed = np.zeros(draws)
    touched = 0
    for key_ in sorted(by):                     # sorted: the draw order does not move with dict order
        vals = np.asarray(by[key_], dtype=float)
        r = len(vals) - max_entries
        if r <= 0:
            continue
        touched += 1
        idx = rng.random((draws, len(vals))).argsort(axis=1)[:, :r]
        removed += vals[idx].sum(axis=1)
    d_pt = (total - removed) / (n - k) - total / n
    q = lambda p: float(np.quantile(d_pt, p))                         # noqa: E731
    return {"valid": True, "k": k, "n": n, "touched": touched,
            "p05": q(.05), "p50": q(.5), "p95": q(ABSTENTION_Q)}


# --- description --------------------------------------------------------------------

def ordinal_table(rows, f: float = MEASURED_FRICTION) -> list[tuple]:
    """(label, trades, net, per trade, win %) for entry #1, #2, #3, #4, #5+."""
    out = []
    for lab, lo, hi in (("#1", 1, 1), ("#2", 2, 2), ("#3", 3, 3), ("#4", 4, 4), ("#5+", 5, 10 ** 9)):
        sub = [r for r in rows if lo <= r["ordinal"] <= hi]
        wins = sum(1 for r in sub if r["net"] - f > 0)
        out.append((lab, len(sub), net(sub, f), per_trade(sub, f),
                    100.0 * wins / len(sub) if sub else 0.0))
    return out


def time_of_day(rows) -> dict:
    """Median entry time (ET) and the share entered at or after LATE."""
    ts = sorted(r["entry_et"] for r in rows)
    if not ts:
        return {"n": 0, "median": "-", "late_share": 0.0}
    return {"n": len(ts), "median": ts[len(ts) // 2],
            "late_share": 100.0 * sum(1 for t in ts if t >= LATE) / len(ts)}


def late_split(rows, f: float = MEASURED_FRICTION) -> tuple[tuple, tuple]:
    """(before LATE, at/after LATE): (trades, per trade) each."""
    a = [r for r in rows if r["entry_et"] < LATE]
    b = [r for r in rows if r["entry_et"] >= LATE]
    return (len(a), per_trade(a, f)), (len(b), per_trade(b, f))


# --- report -------------------------------------------------------------------------

def cell_lines(strat: str, base, max_entries: int, cut: str, symdays: int,
               scored: bool) -> tuple[list[str], dict]:
    f = MEASURED_FRICTION
    gname = f"{strat}-cap{max_entries}"
    kept, removed = cap(base, max_entries)
    tag, why, n = verdict(base, kept, cut, symdays)
    pos = positional(base, max_entries)
    touched = len({(r["symbol"], r["date"]) for r in removed})
    L: list[str] = []
    if scored:
        L += verdict_block(strat, gname, base, kept, cut, symdays)
    else:
        L += [f"REPORTED, NOT SCORED: {gname} against {strat}", "",
              f"  would read {tag}: {why}",
              f"  per trade {n['d_per_trade']:+.2f}   per symbol-day {n['d_per_symday']:+.2f}   "
              f"boot P {n['boot_p']:.3f}", ""]
    L += [f"  WHAT THE CAP TOUCHED: {len(removed):,} of {len(base):,} trades removed "
          f"({100.0 * len(removed) / len(base) if base else 0:.1f}%) in {touched:,} of {symdays:,} symbol-days", ""]
    L += ["  REMOVED vs KEPT (the whole mechanism in one row)"]
    for lab, fr in FRICTIONS:
        L.append(f"    at {lab:<6} removed {len(removed):>5,} per trade {money(per_trade(removed, fr)):>8}"
                 f"   kept {len(kept):>5,} per trade {money(per_trade(kept, fr)):>8}"
                 f"   gap {per_trade(removed, fr) - per_trade(kept, fr):+.2f}")
    if pos["valid"]:
        beat = n["d_per_trade"] > pos["p95"]
        L += ["", f"  POSITIONAL CONTROL (reported, not scored): same {pos['touched']:,} symbol-days, "
                  f"same {pos['k']:,} trades removed, random positions, {ABSTENTION_DRAWS} draws",
              f"    per trade  random p05 {pos['p05']:+.2f}  p50 {pos['p50']:+.2f}  p95 {pos['p95']:+.2f}"
              f"   the cap {n['d_per_trade']:+.2f}   -> "
              + ("beats p95: late entries are worse than other entries in the same busy name-days"
                 if beat else "does NOT beat p95: no evidence late entries differ from other entries "
                              "in the same name-days")]
    tr, tk = time_of_day(removed), time_of_day(kept)
    (rb_n, rb_pt), (ra_n, ra_pt) = late_split(removed)
    (kb_n, kb_pt), (ka_n, ka_pt) = late_split(kept)
    L += ["", f"  TIME OF DAY (ET): removed median {tr['median']}, {tr['late_share']:.0f}% at/after {LATE}"
              f"   kept median {tk['median']}, {tk['late_share']:.0f}% at/after {LATE}",
          f"    before {LATE}: removed {rb_n:>5,} {money(rb_pt):>8}/t   kept {kb_n:>5,} {money(kb_pt):>8}/t",
          f"    from   {LATE}: removed {ra_n:>5,} {money(ra_pt):>8}/t   kept {ka_n:>5,} {money(ka_pt):>8}/t", ""]
    summary = {"strat": strat, "cap": max_entries, "tag": tag, "why": why,
               "d_per_trade": n["d_per_trade"], "d_per_symday": n["d_per_symday"],
               "removed": len(removed), "kept": len(kept), "touched": touched,
               "removed_pt": per_trade(removed, f), "kept_pt": per_trade(kept, f),
               "base_net": net(base, f), "cap_net": net(kept, f),
               "abst_p95": n["abst"]["per_trade"].get("p95") if n["abst"]["valid"] else None,
               "pos_p95": pos.get("p95"), "boot_p": n["boot_p"], "early": n["early"], "late": n["late"],
               "drop_level": n["drop_level"], "drop_delta": n["drop_delta"]}
    return L, summary


def render(books: dict, meta: dict, source: str) -> tuple[list[str], list[dict]]:
    cut, symdays = meta["cut"], meta["symbol_days"]
    f = MEASURED_FRICTION
    L = ["W03-0008 / H-C1: THE ENTRY-COUNT CAP -- NO 4TH-OR-LATER ENTRY PER STRATEGY PER SYMBOL-DAY", "",
         f"  registered  {REGISTERED} (commit ecf93a5, before this module existed)",
         f"  books       {source} (ungated baselines, no re-simulation -- exact, see §1)",
         f"  universe    {meta.get('pairs', PAIRS)}   bars {meta.get('dataset', '?')}",
         f"  {len(meta.get('sessions', [])):,} sessions   "
         f"{symdays:,} symbol-days   halves cut at {cut}",
         f"  100 shares   commission in, friction per round trip   verdict at $4.26", "",
         "POPULATION CHECK", ""]
    for s in STRATS:
        ok = len(books[s]) == EXPECT[s]
        L.append(f"  {s} trades here {len(books[s]):>6,}   registered {EXPECT[s]:,}   "
                 + ("matches" if ok else "*** DOES NOT MATCH ***"))
    L += population_lines(len(books["MCL"]), meta.get("pairs", PAIRS))
    for s in STRATS:
        bad = check_ordinals(books[s])
        L.append(f"  {s} ordinals run 1..n in every symbol-day: "
                 + ("yes" if not bad else f"*** NO, {len(bad)} symbol-days, e.g. {bad[:3]} ***"))
    L += ["", "THE ORDINAL TABLE (the live pre-read's cut, on the backtest books, $4.26)", ""]
    for s in STRATS:
        L.append(f"  {s}")
        for lab, nt, nn, pt, w in ordinal_table(books[s]):
            L.append(f"    entry {lab:<4} {nt:>6,} trades   net {money(nn):>12}   per trade {money(pt):>8}"
                     f"   winners {w:4.1f}%")
        L.append(f"    all        {len(books[s]):>6,} trades   net {money(net(books[s], f)):>12}"
                 f"   per trade {money(per_trade(books[s], f)):>8}")
        L.append("")
    L += ["THE BOOKS", ""]
    for s in STRATS:
        L += book_block(s, books[s], cut, symdays)
        for m in SCORED + REPORTED:
            L += book_block(f"{s}-cap{m}", cap(books[s], m)[0], cut, symdays)
    summaries = []
    for s in STRATS:
        L += ["=" * 100, f"{s}", "=" * 100, ""]
        for m in SCORED:
            lab = "PRIMARY" if m == PRIMARY else "BOUNDARY"
            L += [f"--- {s}-cap{m} ({lab}) ---", ""]
            lines, summ = cell_lines(s, books[s], m, cut, symdays, scored=True)
            L += lines
            summaries.append(summ)
        for m in REPORTED:
            lines, summ = cell_lines(s, books[s], m, cut, symdays, scored=False)
            L += lines
            summaries.append(summ)
    L += ["=" * 100, "SUMMARY ($4.26)", "=" * 100, ""]
    for x in summaries:
        L.append(f"  {x['strat']}-cap{x['cap']:<2} {x['tag']:<8} d/trade {x['d_per_trade']:+6.2f}  "
                 f"d/symday {x['d_per_symday']:+6.2f}  removed {x['removed']:>5,}  "
                 f"removed {money(x['removed_pt']):>8}/t vs kept {money(x['kept_pt']):>8}/t  "
                 f"random p95 {x['abst_p95'] if x['abst_p95'] is None else format(x['abst_p95'], '+.2f')}")
    L += ["", "WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT A CAP MODEL. Each symbol-day ran alone in the source books.",
          "  NOT A SEARCH. CAP-3 decides; CAP-2 and CAP-4 are boundaries; CAP-1 is reported only.", ""]
    return L, summaries


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=SOURCE)
    ap.add_argument("--out", default="var/reports/entry_cap.txt")
    ap.add_argument("--json", default="var/reports/entry_cap_summary.json")
    a = ap.parse_args(argv)
    meta_path = Path(a.csv).with_name(Path(a.csv).stem + "_meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    books = load_books(a.csv)
    if any(len(books[s]) != EXPECT[s] for s in STRATS):
        print("POPULATION CHECK FAILED -- " + ", ".join(f"{s} {len(books[s]):,} (registered {EXPECT[s]:,})"
                                                       for s in STRATS) + ". Stopping (registration §2).")
        return 2
    L, summaries = render(books, meta, a.csv)
    emit("\n".join(L), a.out, header=f"common.entry_cap csv={a.csv} registered={REGISTERED}")
    Path(a.json).write_text(json.dumps(summaries, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
