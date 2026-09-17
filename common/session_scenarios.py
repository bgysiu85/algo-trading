#!/usr/bin/env python3
r"""The five scenarios of 2026-09-17, from ONE pass over the point-in-time tape.

    python -m common.session_scenarios --pairs var\state\screen_pairs_pit_itch_v2.json ^
        --dataset XNAS.ITCH --jobs 8

    1  a $5 entry floor on a $2-20 watchlist          REGISTERED_price_floor.md
    2  stop the SESSION after a 50% give-back          REGISTERED_giveback_cap.md
    3  stop the STRATEGY after a 50% give-back         the same, scope=strategy
    4  1 and 2 together
    5  1 and 3 together

ONE ENGINE PASS, FOUR BOOKS. The floor has to go through the engine -- refusing
an entry leaves the strategy flat and later bars become live signals, the
signal-ordinal cascade -- so MCL, MCL at $5, MC5 and MC5 at $5 are produced
together over the same frames. The give-back cap does NOT have to: once it
trips nothing more is entered that session, so no refused entry can free a
later signal and the kept set is exactly the trades entered before the trip.
That makes scenarios 2-5 an exact post-pass over books already in memory
(`common/session_stop.py` says why at length), which is the difference between
one pass over the tape and five.

WHICH BAR EACH SCENARIO IS SCORED ON, because they are not the same:

  scenario 1     the gate standard -- Delta per trade with the $4.26 margin
                 against `gate_study.abstention`. REGISTERED_price_floor §4.
  scenarios 2-5  H-S4's six readings, whose reading 1 is "> 0" with no margin
                 and whose control is the random cut. The margin comparison is
                 printed beside it and labelled (amendment A6), so a pass on
                 "> 0" that fails the margin cannot be quoted as the stronger
                 claim afterwards.

  4 and 5 are compositions and get no extra multiplicity (A7). Each is read
  TWICE and both lines are printed: against the baseline, which is the whole
  change, and against scenario 1, which is what the cap adds on top of the
  floor. The second is the one that says whether the combination is doing
  anything the floor was not already doing.
"""
from __future__ import annotations

import argparse
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common import session_stop as SS
from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, share_above_zero
from common.entry_shares import MEASURED_FRICTION, QTY, published_mcl_trades
from common.first_entry_skip import (DROP, FRICTIONS, book_block, by_symbol_day,
                                     delta_by_symbol, deltas_by_symbol_day,
                                     drop_top_delta, halves, money, net,
                                     per_trade, population_lines, trade_row)
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
REG_FLOOR = "docs/research/REGISTERED_price_floor.md"
REG_CAP = "docs/research/REGISTERED_giveback_cap.md"

PRICE_FLOOR = 5.00               # H-S5 §3: the primary cell, the threshold named
STRATEGIES = ("mcl", "mc5")      # LIVE_STRATEGIES; VW9 is rejected, ORB is RTH

# (book, engine, price_min). The floored books are the only ones needing the tape.
BOOKS = (("MCL", "mcl", None), ("MCL-pf5", "mcl", PRICE_FLOOR),
         ("MC5", "mc5", None), ("MC5-pf5", "mc5", PRICE_FLOOR))
BASE_OF = {"MCL": "MCL", "MCL-pf5": "MCL", "MC5": "MC5", "MC5-pf5": "MC5"}


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session, all four engine books. Module-level and picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in STRATEGIES}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                               # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    res = {"books": {name: [] for name, _, _ in BOOKS},
           "symdays": 0, "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        # ALL OR NONE, as every other point-in-time study: a symbol-day that
        # raises in any book is dropped from every book, or the books stop
        # covering the same opportunities and the denominators diverge.
        try:
            got = {}
            for name, eng, pmin in BOOKS:
                mod, extra = engines[eng]
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, price_min=pmin,
                                                 **extra)
        except Exception as e:                               # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [trade_row(t, rec["symbol"], day, k)
                                   for k, t in enumerate(trades, 1)]
    return day, res, ""


# --- the scenarios ----------------------------------------------------------

def tagged(books: dict, names) -> list[dict]:
    """The rows of several books, each carrying its own book name, as the cap
    needs them: SESSION scope pools strategies and has to know which is which."""
    out = []
    for n in names:
        out += [dict(r, book=n) for r in books[n]]
    return out


def split_by_book(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["book"], []).append(r)
    return out


def scenario_books(books: dict, f: float, giveback: float = SS.GIVEBACK) -> dict:
    """Every scenario's books at ONE friction level.

    Amendment A5: `realised` is net of friction, so the trip moves with it and
    this is called once per level rather than computed at $4.26 and re-priced.
    """
    plain = ("MCL", "MC5")
    floored = ("MCL-pf5", "MC5-pf5")
    # EVERY scenario's books carry their book name, scenario 1 included. The
    # cap's output is stamped by `tagged()`, and a scenario 1 that was not
    # would be the one book of the five with a different shape -- which is
    # how the control ended up reading untagged rows in the first place.
    out = {"1": {"MCL": [dict(r, book="MCL-pf5") for r in books["MCL-pf5"]],
                 "MC5": [dict(r, book="MC5-pf5") for r in books["MC5-pf5"]]},
           "caps": {}}
    for tag, names, scope in (("2", plain, "session"), ("3", plain, "strategy"),
                              ("4", floored, "session"), ("5", floored, "strategy")):
        res = SS.apply_cap(tagged(books, names), giveback, scope=scope, f=f)
        kept = split_by_book(res["kept"])
        # Name the source book explicitly rather than falling through a chain of
        # .get defaults: a book that the cap emptied and a book that was never
        # in this scenario both come back as [], and only one of those is right.
        out[tag] = {"MCL": kept.get(names[0], []), "MC5": kept.get(names[1], [])}
        out["caps"][tag] = res
    return out


# --- the readings -----------------------------------------------------------

def cap_verdict(base: list[dict], gated: list[dict], cut: str, symdays: int,
                cap: dict, scope: str, f: float, book: str) -> tuple[str, list[str]]:
    """H-S4 §4's six readings, scored exactly as registered.

    Reading 1 is the registration's "> 0", with no margin. The project's
    $4.26 margin is computed and printed beside it under its own label
    (amendment A6) and is NOT part of the verdict.
    """
    d_pt = per_trade(gated, f) - per_trade(base, f)
    d_sd = (net(gated, f) - net(base, f)) / symdays if symdays else 0.0
    be, bl = halves(base, cut)
    ge, gl = halves(gated, cut)
    h_e = per_trade(ge, f) - per_trade(be, f)
    h_l = per_trade(gl, f) - per_trade(bl, f)
    deltas = deltas_by_symbol_day(base, gated, f)
    d3 = drop_top_delta(deltas, 3)
    d5 = drop_top_delta(deltas, 5)
    boot = cluster_bootstrap(delta_by_symbol(deltas), RESAMPLES, SEED)
    boot_p = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    # The control cuts THIS book's trades in the sessions the cap fired on, so
    # `base` has to carry the book name the cap keyed on -- the engines' rows
    # do not, which is what the 2026-09-17 smoke run died on.
    #
    # The fired keys are passed whole rather than filtered to this strategy.
    # A filter would be unreachable: `random_cut` looks each key up in the
    # rows it was given, and under strategy scope another strategy's key
    # cannot be there. A guard that cannot fire is noise that reads like
    # protection, and this project has removed two of those already.
    ctrl = SS.random_cut([dict(r, book=book) for r in base], list(cap["fired"]),
                         scope, f, SS.CUT_DRAWS, SEED)
    removed = len(base) - len(gated)

    r1 = d_pt > 0
    r2 = d_sd > 0 and (d_pt > 0) == (d_sd > 0)
    r3 = h_e > 0 and h_l > 0
    r4 = d3 > 0 and d5 > 0
    r5 = boot_p >= BOOT_MIN_P
    r6 = bool(ctrl.get("valid")) and d_pt > ctrl["per_trade"]["p95"]

    L = [f"  1. per remaining trade {d_pt:+.2f}   per symbol-day {d_sd:+.2f}"
         f"      [not scored: the project's $4.26 margin -> "
         f"{'clears' if d_pt >= MEASURED_FRICTION else 'does not clear'}]",
         f"  2. denominators agree: {'yes' if r2 else 'NO'}",
         f"  3. early half {h_e:+.2f}   late half {h_l:+.2f}",
         f"  4. drop-top-3 delta {money(d3)}   drop-top-5 delta {money(d5)}",
         f"  5. cluster bootstrap on the delta  P(total > 0) = {boot_p:.3f}"
         f"  over {boot['n_syms']:,} symbols",
         f"  6. random cut, same sessions: {SS.CUT_DRAWS:,} draws  "
         f"p05 {ctrl['per_trade']['p05']:+.2f}  p50 {ctrl['per_trade']['p50']:+.2f}  "
         f"p95 {ctrl['per_trade']['p95']:+.2f}   the cap {d_pt:+.2f}"
         if ctrl.get("valid") else "  6. random cut: NOT COMPUTABLE (no session with two trades fired)"]
    if ctrl.get("valid"):
        # A4: which way the count mismatch biases the test has to be stated,
        # not left for the reader to work out.
        cm = ctrl["removed"]["mean"]
        L.append(f"     trades removed: the cap {removed:,}, the control {cm:,.0f} on average"
                 f"  -> the control removes {'MORE, so this test is conservative' if cm > removed else 'FEWER, so this test is NOT conservative'}")
    failed = [n for n, ok in ((1, r1), (2, r2), (3, r3), (4, r4), (5, r5), (6, r6)) if not ok]
    tag = "PASSES" if not failed else "NOTHING"
    L.append(f"  {tag}" + ("" if not failed
                           else f": fails {', '.join(str(n) for n in failed)} of the six"))
    return tag, L


def cap_block(tag: str, cap: dict, symdays: int) -> list[str]:
    """§4's reported-not-scored rows: where it armed, where it fired, what it
    removed, and the fire clock that says whether this is time-of-day again."""
    fired = cap["fired"]
    removed = cap["removed"]
    f = cap["f"]
    L = [f"  scope {cap['scope']}   give-back {cap['giveback']:.0%}   arm {money(cap['arm'])}",
         f"  armed {len(cap['armed']):,}   fired {len(fired):,}   "
         f"trades removed {len(removed):,} of {len(removed) + len(cap['kept']):,}"]
    if removed:
        L.append(f"  removed per trade {money(per_trade(removed, f))}   "
                 f"kept per trade {money(per_trade(cap['kept'], f))}")
    clock = SS.fire_clock(cap)
    if clock:
        L.append("  fire time (ET hour): " + "  ".join(f"{k} {v}" for k, v in clock.items()))
        L.append("    (§5: if the removed trades are worse only because they are late,"
                 " this is the time-of-day filter under another name -- and that is closed)")
    return L + [""]


def render(books: dict, symdays: int, errors: int, days: list[str], elapsed: float,
           jobs: int, error_days, universe: str, dataset: str) -> list[str]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    L = ["THE FIVE SCENARIOS: A $5 ENTRY FLOOR, AND THE 50% SESSION GIVE-BACK CAP", "",
         f"  registered  {REG_FLOOR} (scenario 1)",
         f"              {REG_CAP} (scenarios 2-5, + amendment A)",
         f"  universe    {universe}   bars {dataset}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY book:"]
        L += [f"    {e}" for e in (error_days or [])[:20]] + [""]

    L += ["POPULATION CHECK", "", f"  MCL trades here     {len(books['MCL']):,}"]
    L += population_lines(len(books["MCL"]), universe) + [""]

    for label, f in FRICTIONS:
        sc = scenario_books(books, f)
        L += [f"{'=' * 70}", f"AT {label} A ROUND TRIP", ""]
        L += ["THE BOOKS", ""]
        for strat in ("MCL", "MC5"):
            L += book_block(strat, books[strat], cut, symdays)
            for tag in ("1", "2", "3", "4", "5"):
                L += book_block(f"{strat}  scenario {tag}", sc[tag][strat], cut, symdays)

        L += [f"{'-' * 70}", "SCENARIO 1: a $5 entry floor", ""]
        for strat in ("MCL", "MC5"):
            # The DELTAS move with friction and are printed at each level. The
            # registered VERDICT does not: REGISTERED_price_floor §4 reads the
            # gate standard, whose margin is the measured $4.26, and
            # `gate_study.verdict` is that one implementation. Printing it
            # under all three headings would be the same verdict three times
            # over three different books -- so it is read once, below.
            d_pt = per_trade(sc["1"][strat], f) - per_trade(books[strat], f)
            d_sd = (net(sc["1"][strat], f) - net(books[strat], f)) / symdays if symdays else 0.0
            L += [f"  {strat}  per trade {d_pt:+.2f}   per symbol-day {d_sd:+.2f}"
                  f"   entries refused {len(books[strat]) - len(sc['1'][strat]):+,}"
                  f" (signal-ordinal: not a subset of the baseline)"]
        L += [""]

        for tag, name, comp in (
                ("2", "SCENARIO 2: stop the SESSION after a 50% give-back", None),
                ("3", "SCENARIO 3: stop the STRATEGY after a 50% give-back", None),
                ("4", "SCENARIO 4: the $5 floor AND the session cap", "1"),
                ("5", "SCENARIO 5: the $5 floor AND the strategy cap", "1")):
            L += [f"{'-' * 70}", name, ""]
            L += cap_block(tag, sc["caps"][tag], symdays)
            for strat in ("MCL", "MC5"):
                scope = sc["caps"][tag]["scope"]
                # The book the cap acted on -- the plain one for 2 and 3, the
                # floored one for 4 and 5. It is also what the control cuts.
                acted = strat if comp is None else f"{strat}-pf5"
                src = books[strat] if comp is None else sc[comp][strat]
                against = "the baseline" if comp is None else f"scenario {comp}"
                t, lines = cap_verdict(src, sc[tag][strat], cut, symdays,
                                       sc["caps"][tag], scope, f, acted)
                L += [f"  {strat} against {against} (H-S4's six readings)"
                      + ("" if comp is None
                         else " -- what the cap adds ON TOP OF the floor (A7),"
                              " and the SCORED reading for this scenario")] + lines + [""]
                if comp:
                    # The whole change, floor and cap together. DESCRIPTIVE: the
                    # delta carries the floor's contribution and the control cuts
                    # only the floored book, so scoring the six here would credit
                    # the cap with the floor's effect against a control that never
                    # saw it. The scored line is the one above.
                    d_pt = per_trade(sc[tag][strat], f) - per_trade(books[strat], f)
                    d_sd = ((net(sc[tag][strat], f) - net(books[strat], f)) / symdays
                            if symdays else 0.0)
                    L += [f"  {strat} against the baseline -- floor AND cap together."
                          f" DESCRIPTIVE, NOT SCORED",
                          f"    per trade {d_pt:+.2f}   per symbol-day {d_sd:+.2f}"
                          f"   trades {len(books[strat]):,} -> {len(sc[tag][strat]):,}",
                          "    (the delta carries the floor; the control above does"
                          " not, so the six are read against scenario 1)", ""]

    # SCENARIO 1'S REGISTERED VERDICT, read once at the measured friction.
    L += [f"{'=' * 70}",
          "SCENARIO 1, THE REGISTERED VERDICT (REGISTERED_price_floor §4)", "",
          f"  the gate standard at {money(MEASURED_FRICTION)}: margin, both denominators,",
          "  both halves, drop-top-3 on level and delta, cluster bootstrap, and the",
          "  abstention control -- the same six every B-series gate was read on.", ""]
    for strat in ("MCL", "MC5"):
        floored = {"MCL": books["MCL-pf5"], "MC5": books["MC5-pf5"]}[strat]
        t, why, n = G.verdict(books[strat], floored, cut, symdays)
        L += [f"  {strat}-pf5 against {strat}",
              f"    per trade {n['d_per_trade']:+.2f}   per symbol-day {n['d_per_symday']:+.2f}",
              f"    {t}" + (f": {why}" if why else ""), ""]

    L += ["", "WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT A CAP MODEL. Each symbol-day runs alone; the concurrency cap that",
          "  rejected 29% of live buy attempts is not modelled, and a give-back stop",
          "  frees slots this cannot price (PROGRAM_INDEX §7 item 15).",
          "  NOT LIVE. strategy_adapter's price_min is unchanged and the trader has",
          "  no give-back rule; shipping either is its own change with its own parity",
          "  test, which the last three live/backtest splits earned.",
          "  NOT A SEARCH. One floor, one give-back, both named before the run."]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/session_scenarios.txt")
    p.add_argument("--csv", default="var/reports/session_scenarios_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "session_scenarios")

    # DAY ORDER, not completion order -- float sums must not move with --jobs.
    books = {name: [] for name, _, _ in BOOKS}
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    emit("\n".join(render(books, symdays, errors, run_days, elapsed, jobs, error_days,
                          universe=a.pairs, dataset=a.dataset)),
         a.out, header=f"common.session_scenarios pairs={a.pairs} dataset={a.dataset} "
                       f"sessions={len(run_days)} symbol_days={symdays} cut={cut} "
                       f"qty={QTY} price_floor={PRICE_FLOOR} giveback={SS.GIVEBACK} arm={SS.ARM}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REG_CAP,
                  "price_floor": PRICE_FLOOR, "giveback": SS.GIVEBACK, "arm": SS.ARM})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
