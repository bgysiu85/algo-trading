#!/usr/bin/env python3
r"""The shared half of every "take the signal only if ..." study.

A gate study runs the published MCL and MC5 engines over the point-in-time
universe with `entry_gate` set from some rule, alongside the ungated
baselines, and reads the gated book against its baseline under the five
readings fixed in docs/research/REGISTERED_range_rank.md §3 (the first gate
registration, whose readings later gates inherit unless their own
registration says otherwise):

  1. delta per trade >= MIN_MARGIN AND delta per symbol-day > 0; a sign
     disagreement is a REFUSAL
  2. both halves, both denominators, > 0
  3. drop-top-3 on the level and on the delta
  4. the symbol-cluster bootstrap on the delta, >= BOOT_MIN_P
  5. THE ABSTENTION CONTROL: the same number of trades removed from the
     baseline at random, 2,000 seeded draws; the gate's per-trade delta must
     beat the draws' 95th percentile

Reading 5 exists because of H-B1 (first_entry_skip): on a book whose average
trade loses, readings that are built from totals -- per symbol-day, the
delta after dropping its best days, a bootstrap on the delta -- all pass for
any rule that removes trades, and did, at P = 1.000, for a rule that moved
per trade by +$0.03. Random removal is the null for "trades less"; a gate
that cannot beat it is declining trades, not selecting names.

Everything here is arithmetic and rendering over rows of the shape
`first_entry_skip.trade_row` produces; the study module owns `run_day`
(which builds the gate) and the CLI, and hands its books to `render`.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, pct, share_above_zero
from common.entry_shares import MEASURED_FRICTION, PUBLISHED_TRADES, QTY
from common.first_entry_skip import (DROP, FRICTIONS, TOP, book_block, by_symbol_day,
                                     delta_by_symbol, deltas_by_symbol_day, drop_top,
                                     drop_top_delta, halves, key, money, net, new_entries,
                                     per_trade, top_absent, trade_row)
from common.report_io import emit

MIN_MARGIN = MEASURED_FRICTION      # reading 1: one round trip of friction
ABSTENTION_DRAWS = 2000
ABSTENTION_Q = 0.95

__all__ = ["trade_row", "key", "abstention", "verdict", "verdict_block", "refused_block",
           "binding_block", "render", "write_csv", "write_meta", "run_sessions"]


# --- the abstention control ------------------------------------------------------

def abstention(base, k: int, symdays: int, f: float = MEASURED_FRICTION,
               draws: int = ABSTENTION_DRAWS, seed: int = SEED) -> dict:
    """Remove k of the baseline's trades uniformly at random, `draws` times.

    Returns the per-trade and per-symbol-day deltas' quantiles. Per trade,
    random removal is centred near zero and the 95th percentile is the bar a
    gate must clear to be called selection. Per symbol-day, random removal
    on a losing book is reliably POSITIVE -- that number is the abstention
    share of any gate's headline."""
    nets = np.array([r["net"] - f for r in base], dtype=float)
    n = len(nets)
    if n == 0 or k <= 0 or k >= n:
        return {"k": k, "n": n, "per_trade": {}, "per_symday": {}, "valid": False}
    rng = np.random.default_rng(seed)
    base_pt = nets.mean()
    total = nets.sum()
    d_pt, d_sd = np.empty(draws), np.empty(draws)
    for i in range(draws):
        idx = rng.choice(n, size=k, replace=False)
        removed = nets[idx].sum()
        d_pt[i] = (total - removed) / (n - k) - base_pt
        d_sd[i] = -removed / symdays if symdays else 0.0
    q = lambda a, p: float(np.quantile(a, p))                       # noqa: E731
    return {"k": k, "n": n, "valid": True,
            "per_trade": {"p05": q(d_pt, .05), "p50": q(d_pt, .5), "p95": q(d_pt, ABSTENTION_Q)},
            "per_symday": {"p05": q(d_sd, .05), "p50": q(d_sd, .5), "p95": q(d_sd, .95)}}


# --- the verdict -----------------------------------------------------------------

def verdict(base, gated, cut: str, symdays: int) -> tuple[str, str, dict]:
    """REGISTERED_range_rank §3, five readings. (PASSES | NOTHING | REFUSED, why, numbers)."""
    f = MEASURED_FRICTION
    n = {}
    n["d_per_trade"] = per_trade(gated, f) - per_trade(base, f)
    n["d_per_symday"] = (net(gated, f) - net(base, f)) / symdays if symdays else 0.0
    ba, bb = halves(base, cut)
    ga, gb = halves(gated, cut)
    n["early"] = (per_trade(ga, f) - per_trade(ba, f),
                  (net(ga, f) - net(ba, f)) / symdays if symdays else 0.0)
    n["late"] = (per_trade(gb, f) - per_trade(bb, f),
                 (net(gb, f) - net(bb, f)) / symdays if symdays else 0.0)
    n["drop_level"] = (drop_top(gated, f), drop_top(base, f))
    d = deltas_by_symbol_day(base, gated, f)
    n["drop_delta"] = drop_top_delta(d)
    boot = cluster_bootstrap(delta_by_symbol(d))
    n["boot_p"] = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    n["boot_lo"] = pct(boot["totals"], 0.025) if boot["totals"] else 0.0
    n["boot_hi"] = pct(boot["totals"], 0.975) if boot["totals"] else 0.0
    n["n_syms"] = boot["n_syms"]
    n["removed"] = max(0, len(base) - len(gated))
    n["abst"] = abstention(base, n["removed"], symdays, f)

    if not (ba and bb and ga and gb):
        return "NOTHING", "a half is empty in one of the books", n
    if (n["d_per_trade"] > 0) != (n["d_per_symday"] > 0):
        return "REFUSED", (f"the two denominators disagree: per trade {n['d_per_trade']:+.2f}, "
                           f"per symbol-day {n['d_per_symday']:+.2f}"), n
    failed = []
    if not (n["d_per_trade"] >= MIN_MARGIN and n["d_per_symday"] > 0):
        failed.append(f"1 (per trade >= {MIN_MARGIN:.2f} and per symbol-day > 0)")
    if not all(x > 0 for x in n["early"] + n["late"]):
        failed.append("2 (both halves, both denominators)")
    if not (n["drop_level"][0] > n["drop_level"][1] and n["drop_delta"] > 0):
        failed.append(f"3 (drop-top-{DROP} on the level and on the delta)")
    if not n["boot_p"] >= BOOT_MIN_P:
        failed.append(f"4 (cluster bootstrap on the delta, P={n['boot_p']:.3f} < {BOOT_MIN_P})")
    a = n["abst"]
    if not a["valid"]:
        failed.append("5 (abstention control not computable: nothing removed, or everything)")
    elif not n["d_per_trade"] > a["per_trade"]["p95"]:
        failed.append(f"5 (abstention control: per trade {n['d_per_trade']:+.2f} does not beat "
                      f"random removal's p95 {a['per_trade']['p95']:+.2f})")
    if failed:
        return "NOTHING", "fails " + "; ".join(failed), n
    return "PASSES", "all five readings, at $4.26", n


# --- report blocks ---------------------------------------------------------------

def verdict_block(bname: str, gname: str, base, gated, cut: str, symdays: int) -> list[str]:
    f = MEASURED_FRICTION
    tag, why, n = verdict(base, gated, cut, symdays)
    gone, gone_rows = top_absent(base, gated, f)
    fresh = new_entries(base, gated)
    a = n["abst"]
    L = [f"THE VERDICT: {gname} against {bname} (registered readings 1-5, $4.26)", "",
         f"  1. per trade {n['d_per_trade']:+.2f} (margin {MIN_MARGIN:.2f})   per symbol-day {n['d_per_symday']:+.2f}",
         f"  2. early half  per trade {n['early'][0]:+.2f}  per symbol-day {n['early'][1]:+.2f}"
         f"     late half  per trade {n['late'][0]:+.2f}  per symbol-day {n['late'][1]:+.2f}",
         f"  3. drop-top-{DROP} level  {gname} {money(n['drop_level'][0])}  "
         f"{bname} {money(n['drop_level'][1])}     drop-top-{DROP} delta {money(n['drop_delta'])}",
         f"  4. cluster bootstrap on the delta  P(total > 0) = {n['boot_p']:.3f}  "
         f"[{money(n['boot_lo'])}, {money(n['boot_hi'])}]  over {n['n_syms']:,} symbols"]
    if a["valid"]:
        L += [f"  5. abstention control: {a['k']:,} of {a['n']:,} trades removed at random, "
              f"{ABSTENTION_DRAWS} draws",
              f"       per trade      random p05 {a['per_trade']['p05']:+.2f}  p50 {a['per_trade']['p50']:+.2f}  "
              f"p95 {a['per_trade']['p95']:+.2f}   the gate {n['d_per_trade']:+.2f}",
              f"       per symbol-day random p05 {a['per_symday']['p05']:+.2f}  p50 {a['per_symday']['p50']:+.2f}  "
              f"p95 {a['per_symday']['p95']:+.2f}   the gate {n['d_per_symday']:+.2f}"]
    else:
        L += [f"  5. abstention control not computable ({a['k']:,} removed of {a['n']:,})"]
    L += ["", f"  {tag}: {why}", "",
          f"  cost: {gone} of {bname}'s top-{TOP} trades at $4.26 are absent from {gname}"]
    for r in gone_rows:
        L.append(f"    {r['symbol']:<6} {r['date']}  {r['entry_et']} ET  {money(r['net'] - f):>10}")
    L += [f"  cascade: {fresh:,} {gname} entries the baseline does not contain", ""]
    return L


def refused_block(bname: str, gname: str, refused_rows) -> list[str]:
    """The baseline trades whose entry bar the gate refused -- exact, because
    the gate is a bar-level mask -- split into losses avoided and winners
    lost. Printed for the cost; the verdict does not read it."""
    f = MEASURED_FRICTION
    losers = [r for r in refused_rows if r["net"] - f <= 0]
    winners = [r for r in refused_rows if r["net"] - f > 0]
    return [f"WHAT {gname} REFUSED OF {bname} (exact: baseline trades whose entry bar the gate was False on)", "",
            f"  refused           {len(refused_rows):>6,}   net {money(net(refused_rows, f)):>12}"
            f"   per trade {money(per_trade(refused_rows, f)):>8}",
            f"    losses avoided  {len(losers):>6,}   {money(net(losers, f)):>12}",
            f"    winners lost    {len(winners):>6,}   {money(net(winners, f)):>12}", ""]


def binding_block(gname: str, could: int, total: int, visible: dict) -> list[str]:
    """A gate that never fires is indistinguishable from its absence. How
    many baseline entries had enough visible names for the gate to bind at
    all, and the distribution of visible-name counts at signal time."""
    share = 100.0 * could / total if total else 0.0
    L = [f"COULD {gname} HAVE BOUND? (visible point-in-time names at the baseline's entry minutes)", "",
         f"  baseline entries {total:,}   with enough names for the gate to bind {could:,} ({share:.1f}%)"
         + ("   *** NEVER -- THE GATE DID NOT RUN ***" if total and could == 0 else ""),
         "  visible names at signal:  " + "  ".join(f"{k}:{v:,}" for k, v in sorted(visible.items())[:15]), ""]
    return L


def render(title: str, registered: str, books: dict, pairs, reported, symdays: int, errors: int,
           days: list[str], elapsed: float, jobs: int, refused: dict, binding: dict,
           error_days: list | None = None) -> list[str]:
    """`pairs`: (baseline, gated) read by the verdict; `reported`: (baseline,
    gated) printed as 'reported, not registered'. `refused[gated]` rows;
    `binding[gated] = (could, total, visible_counter)`."""
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    L = [title, "", f"  registered  {registered}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY book:"]
        L += [f"    {e}" for e in (error_days or [])[:20]]
        L += [""]
    mcl = books.get("MCL", [])
    pub = PUBLISHED_TRADES.get("mcl")
    L += ["POPULATION CHECK", "", f"  MCL trades here     {len(mcl):,}"]
    if pub is not None:
        ok = len(mcl) == pub
        L.append(f"  published count     {pub:,}   " + ("matches" if ok else "*** DOES NOT MATCH ***"))
    L += [""]
    L += ["THE BOOKS", ""]
    for name, rows in books.items():
        L += book_block(name, rows, cut, symdays)
    for bname, gname in pairs:
        L += binding_block(gname, *binding[gname])
        L += verdict_block(bname, gname, books[bname], books[gname], cut, symdays)
        L += refused_block(bname, gname, refused[gname])
    for bname, gname in reported:
        L += binding_block(gname, *binding[gname])
        tag, why, n = verdict(books[bname], books[gname], cut, symdays)
        a = n["abst"]
        L += [f"REPORTED, NOT REGISTERED: {gname} against {bname}", "",
              f"  would read {tag}: {why}",
              f"  per trade {n['d_per_trade']:+.2f}   per symbol-day {n['d_per_symday']:+.2f}   "
              f"boot P {n['boot_p']:.3f}   removed {n['removed']:,}"
              + (f"   random p95 per trade {a['per_trade']['p95']:+.2f}" if a["valid"] else ""), ""]
        L += refused_block(bname, gname, refused[gname])
    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT A CAP MODEL. Each symbol-day runs alone (registration §5).",
          "  NOT A SEARCH. One N decides; the reported cell was declared before the run.", ""]
    return L


# --- files -------------------------------------------------------------------------

CSV_COLS = ["book", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
            "exit_px", "reason", "bars_held", "net"]


def write_csv(path: str, books: dict) -> None:
    import csv
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for name, rows in books.items():
            for r in rows:
                w.writerow(dict(r, book=name))


def write_meta(csv_path: str, days: list[str], symdays: int, cut: str, extra: dict) -> None:
    m = {"sessions": days, "symbol_days": symdays, "cut": cut, "qty": QTY, "timestamps": "ET"}
    m.update(extra)
    p = Path(csv_path)
    p.with_name(p.stem + "_meta.json").write_text(json.dumps(m, indent=1), encoding="utf-8")


# --- the session loop, shared -----------------------------------------------------

def run_sessions(run_day, tasks: list, jobs: int, label: str) -> tuple[dict, float]:
    """Map `run_day` over the tasks, in parallel when jobs > 1, and return
    {day: result} plus the elapsed seconds. DAY ORDER is the caller's job:
    iterate `sorted(got)` so float sums do not move with --jobs."""
    print(f"{label}: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
    t0 = time.time()
    got: dict[str, dict] = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=2)
    for k, (day, res, err) in enumerate(it, 1):
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if res is not None:
            got[day] = res
        if k % 50 == 0:
            print(f"  ... {k:,} of {len(tasks):,}", flush=True)
    if jobs != 1:
        ex.shutdown()
    return got, time.time() - t0


def build_tasks(pairs_path: str, archive, dataset: str, limit: int | None) -> tuple[list, dict]:
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices
    by_date = load_pit(Path(pairs_path))
    slices = {date_of(p): p for p in window_slices(archive, dataset)}
    days = sorted(by_date)
    if limit:
        days = days[:limit]
    have = [d for d in days if d in slices]
    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day, by_date[day]))
    return tasks, by_date


def jobs_from(arg: int) -> int:
    return (os.cpu_count() or 1) if arg == 0 else max(1, arg)
