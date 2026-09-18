#!/usr/bin/env python3
r"""H-E2 -- does LESS confirmation enter earlier, and does earlier pay?

    python -m common.entry_sweep --jobs 8

Registered in docs/research/REGISTERED_entry_sweep.md, committed before this
file existed and before either engine had a parameter for the swept constants.

WHY
---
`running_up_preflight_RESULT_20260918.md` measured what kills these books:
entries taken after a large recent move die immediately. MCL's five entry
clauses are ALL confirmations, and two of them put the entry on the spike bar
-- `MACD > 0`, which cannot be true until the move is established, and
`VOL_MULTIPLE = 3.0`, which demands the surge bar itself. The lateness is not
a filter problem; it is the signal. `mcl.py`'s own comment says neither clause
has been tested alone, because V9 dropped both at once and collapsed 81%.

THREE FAMILIES, ONE CONSTANT EACH (§2 of the registration). Every other
constant stays at its published value -- that separation is the entire point.

WHY THIS READS MORE CLEANLY THAN EVERY GATE BEFORE IT
-----------------------------------------------------
Every entry rule this project has tested REMOVED trades, and on a losing book
abstention improves the total by construction (§4). Most of these cells go the
other way: a looser threshold takes MORE trades, so a per-trade improvement
cannot be manufactured by trading less. The cells that TIGHTEN carry
`gate_study.abstention` anyway, and a cell that fails it is not a pass however
it reads otherwise.

THE MECHANISM IS READ BACK AS A MEASUREMENT (§5)
------------------------------------------------
The claim is that looser confirmation enters EARLIER IN THE MOVE. That is
directly observable, so every cell prints the median five-minute return at
entry -- the same quantity the pre-flight measured. A looser cell that does
not lower it did not operate as claimed, whatever its P&L says.
"""
from __future__ import annotations

import argparse
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from common import gate_study as G
from common import running_up as RU
from common.entry_shares import MEASURED_FRICTION, QTY
from common.first_entry_skip import (FRICTIONS, halves, net, per_trade,
                                     population_lines, trade_row)
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
REGISTERED = "docs/research/REGISTERED_entry_sweep.md"
DROP_N = 5                       # §4: total net after dropping the top 5 trades
EARLIER_BY = 0.002               # 0.2pp of median ret_5m counts as a move

# (cell name, engine, kwargs). The BASE of each family is marked below.
# §2: one constant per family, every other constant at its published value.
F1 = (("MCL", "mcl", {}),
      ("MCL macd>0 OFF", "mcl", {"require_macd_pos": False}))
F2 = (("MCL vol 1.5", "mcl", {"vol_multiple": 1.5}),
      ("MCL vol 2.0", "mcl", {"vol_multiple": 2.0}),
      ("MCL vol 2.5", "mcl", {"vol_multiple": 2.5}),
      ("MCL", "mcl", {}),                                   # base, 3.0
      ("MCL vol 4.0", "mcl", {"vol_multiple": 4.0}))
F3 = (("MC5 roc 1.0", "mc5", {"entry_rsi_roc": 1.0}),
      ("MC5 roc 2.5", "mc5", {"entry_rsi_roc": 2.5}),
      ("MC5", "mc5", {}),                                   # base, 5.0
      ("MC5 roc 7.5", "mc5", {"entry_rsi_roc": 7.5}),
      ("MC5 roc 10.0", "mc5", {"entry_rsi_roc": 10.0}))

FAMILIES = (
    ("F1  MCL, the MACD > 0 clause", F1, "MCL", False),     # no boundary: 2 values
    ("F2  MCL, the volume surge multiple", F2, "MCL", True),
    ("F3  MC5, the RSI rate-of-change threshold", F3, "MC5", True),
)

# Every distinct book, once -- the bases appear in more than one family and
# must not be run twice, or the two copies could drift on a float sum.
BOOKS: tuple = tuple({n: (n, e, k) for fam in (F1, F2, F3) for n, e, k in fam}.values())


# --- the tape ---------------------------------------------------------------

def run_day(args: tuple) -> tuple:
    """One session, every cell. Module-level and picklable."""
    import pandas as pd

    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
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

    res = {"books": {n: [] for n, _, _ in BOOKS}, "symdays": 0,
           "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        # ALL OR NONE, as every point-in-time study here: a symbol-day that
        # raises in ANY cell is dropped from EVERY cell, or the cells stop
        # covering the same opportunities and the counts stop comparing.
        try:
            got = {}
            for name, eng, kw in BOOKS:
                mod, extra = engines[eng]
                # kw LAST so the swept value wins: engine("mcl") returns the
                # published LIVE config, which already contains
                # require_macd_pos=True. Merged the other way round, F1's
                # macd-off cell would silently be a second copy of the base --
                # or, with a bare **kw **extra, a duplicate-keyword TypeError
                # that the all-or-none handler would swallow into empty books.
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, **{**extra, **kw})
        except Exception as e:                               # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            for k, t in enumerate(trades, 1):
                row = trade_row(t, rec["symbol"], day, k)
                # §5: the mechanism, read back as a measurement. Computed from
                # the same frame the engine traded, on closed bars only.
                row["ret_5m"] = RU.ret_at(df, pd.Timestamp(f"{day} {row['entry_et']}",
                                                           tz=ET))
                res["books"][name].append(row)
    return day, res, ""


# --- reading a cell ---------------------------------------------------------

def drop_top(rows, f: float, n: int = DROP_N) -> float:
    vals = sorted((r["net"] - f for r in rows), reverse=True)
    return sum(vals[n:])


def one_bar_share(rows) -> float:
    if not rows:
        return float("nan")
    return sum(1 for r in rows if int(r.get("bars_held", 99)) <= 1) / len(rows)


def median_ret5(rows) -> float:
    v = [r["ret_5m"] for r in rows
         if r.get("ret_5m") is not None and r["ret_5m"] == r["ret_5m"]]
    return float(np.median(v)) if v else float("nan")


def verdict(base, cell, cut: str, symdays: int, f: float = MEASURED_FRICTION) -> tuple:
    """§4's three values, plus the denominator refusal and the abstention
    control on any cell that TIGHTENS."""
    n = {}
    n["per_trade"] = per_trade(cell, f)
    n["per_symday"] = net(cell, f) / symdays if symdays else 0.0
    be, bl = halves(base, cut)
    ce, cl = halves(cell, cut)
    n["d_pt"] = n["per_trade"] - per_trade(base, f)
    n["d_sd"] = n["per_symday"] - (net(base, f) / symdays if symdays else 0.0)
    n["drop5"] = drop_top(cell, f)
    n["abst"] = None

    # §3: a cell that trades LESS than its base is abstaining, and on a losing
    # book that flatters it by construction. Computed FIRST so it is printed
    # even when the cell is refused on another ground -- a refusal with no
    # control attached leaves the reader unable to tell abstention from a real
    # effect, which is the whole reason the control exists.
    removed = len(base) - len(cell)
    if removed > 0:
        n["abst"] = G.abstention(base, removed, symdays, f)

    if not (be and bl and ce and cl):
        return "NOTHING", "a half is empty", n
    # Both denominators, and a disagreement is a refusal -- everywhere here.
    if (n["d_pt"] > 0) != (n["d_sd"] > 0):
        return "REFUSED", (f"the denominators disagree: per trade {n['d_pt']:+.2f}, "
                           f"per symbol-day {n['d_sd']:+.2f}"), n
    if n["abst"] and n["abst"].get("valid") and n["d_pt"] <= n["abst"]["per_trade"]["p95"]:
        return "NOTHING", (f"tightens, and its {n['d_pt']:+.2f} sits inside random "
                           f"removal's p95 {n['abst']['per_trade']['p95']:+.2f}"), n

    if per_trade(ce, f) > 0 and per_trade(cl, f) > 0 and n["drop5"] > 0:
        return "CLEARS", "", n
    better_pt = (per_trade(ce, f) > per_trade(be, f)
                 and per_trade(cl, f) > per_trade(bl, f))
    better_tot = net(ce, f) > net(be, f) and net(cl, f) > net(bl, f)
    if better_pt and better_tot:
        return "IMPROVES", "beats the base per trade AND on total, in both halves", n
    why = []
    if not better_pt:
        why.append("not better per trade in both halves")
    if not better_tot:
        why.append("not better on total in both halves")
    return "NOTHING", "; ".join(why), n


def family_block(title: str, cells, base_name: str, boundary: bool,
                 books: dict, cut: str, symdays: int) -> list[str]:
    base = books[base_name]
    L = [f"{'-' * 78}", title, "",
         f"  {'cell':<16}{'trades':>8}{'per trade':>11}{'per s-day':>11}"
         f"{'early':>9}{'late':>9}{'drop-5':>12}{'med ret5':>10}{'1-bar':>8}  verdict"]
    scored = []
    for name, _eng, _kw in cells:
        rows = books[name]
        f = MEASURED_FRICTION
        e, l = halves(rows, cut)
        if name == base_name:
            L.append(f"  {name + ' (base)':<16}{len(rows):>8,}{per_trade(rows, f):>11.2f}"
                     f"{net(rows, f) / symdays if symdays else 0:>11.2f}"
                     f"{per_trade(e, f):>9.2f}{per_trade(l, f):>9.2f}"
                     f"{drop_top(rows, f):>12,.0f}{median_ret5(rows):>10.2%}"
                     f"{one_bar_share(rows):>8.1%}  --")
            continue
        tag, why, n = verdict(base, rows, cut, symdays)
        L.append(f"  {name:<16}{len(rows):>8,}{per_trade(rows, f):>11.2f}"
                 f"{n['per_symday']:>11.2f}{per_trade(e, f):>9.2f}{per_trade(l, f):>9.2f}"
                 f"{n['drop5']:>12,.0f}{median_ret5(rows):>10.2%}"
                 f"{one_bar_share(rows):>8.1%}  {tag}")
        if why:
            L.append(f"  {'':<16}{why}")
        if n["abst"] and n["abst"].get("valid"):
            a = n["abst"]["per_trade"]
            L.append(f"  {'':<16}[tightens] random removal of {n['abst']['k']:,}: "
                     f"p05 {a['p05']:+.2f} p50 {a['p50']:+.2f} p95 {a['p95']:+.2f}"
                     f"   the cell {n['d_pt']:+.2f}")
        scored.append((n["d_pt"], name, tag))
    L.append("")

    if boundary and scored:
        best = max(scored)
        names = [c[0] for c in cells]
        edge = best[1] in (names[0], names[-1])
        L += [f"  boundary check: best cell is {best[1]} at {best[0]:+.2f} per trade"
              + ("  -> AT THE EDGE OF THE SWEPT RANGE" if edge else "  -> interior"),
              "  " + ("§4: an optimum on the edge of the box is being arbitraged, not"
                      " fitted." if edge else "the optimum is inside the box, as a fitted"
                      " one should be."),
              f"  THE FAMILY READS: {'UNDECIDED -- BOUNDARY' if edge else best[2]}", ""]
    elif not boundary:
        L += ["  no boundary check: §4 says a two-value family is all boundary, and"
              "  none is claimed.", ""]
    return L


def mechanism_block(books: dict) -> list[str]:
    """§5. The claim is that looser confirmation enters EARLIER in the move."""
    L = [f"{'=' * 78}", "THE MECHANISM, READ BACK AS A MEASUREMENT (§5)", "",
         "  The claim is that a looser threshold enters earlier in the move. That is",
         "  observable: the median five-minute return AT ENTRY should FALL as the",
         "  threshold loosens. A cell that does not lower it did not operate as",
         "  claimed, whatever its P&L says, and may not be called 'entering earlier'.", ""]
    for title, cells, base_name, _b in FAMILIES:
        L.append(f"  {title}")
        base_r5 = median_ret5(books[base_name])
        for name, _e, _k in cells:
            r5 = median_ret5(books[name])
            d = r5 - base_r5
            mark = "" if name == base_name else (
                "   <- enters EARLIER" if d < -EARLIER_BY else
                ("   <- enters LATER" if d > EARLIER_BY else "   <- no change"))
            L.append(f"    {name:<16}{r5:>9.2%}{'' if name == base_name else f'{d:>+9.2%}'}"
                     f"{mark}")
        L.append("")
    return L


def render(books: dict, symdays: int, errors: int, days: list[str], elapsed: float,
           jobs: int, error_days, universe: str, dataset: str) -> list[str]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    L = ["THE ENTRY SWEEP: DOES LESS CONFIRMATION ENTER EARLIER, AND DOES EARLIER PAY?",
         "", f"  registered  {REGISTERED} (H-E2)",
         f"  universe    {universe}   bars {dataset}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   elapsed {elapsed:.1f}s on {jobs} worker(s)", "",
         "  ONE CONSTANT PER FAMILY, every other constant at its published value.",
         "  V9 dropped MACD > 0 and the 3x surge together and collapsed 81%; that is",
         "  why these are separated and why neither has ever been read alone.", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY cell:"]
        L += [f"    {e}" for e in (error_days or [])[:20]] + [""]

    L += ["POPULATION CHECK", "", f"  MCL base trades here   {len(books['MCL']):,}"]
    L += population_lines(len(books["MCL"]), universe) + [""]

    for title, cells, base_name, boundary in FAMILIES:
        L += family_block(title, cells, base_name, boundary, books, cut, symdays)

    L += mechanism_block(books)

    L += [f"{'=' * 78}", "AT THE OTHER TWO FRICTION LEVELS", "",
          f"  {'cell':<16}" + "".join(f"{lab:>12}" for lab, _ in FRICTIONS)]
    for name, _e, _k in BOOKS:
        L.append(f"  {name:<16}" + "".join(f"{per_trade(books[name], fv):>12.2f}"
                                           for _, fv in FRICTIONS))
    L += ["", "WHAT THIS IS NOT", "",
          "  NOTHING SHIPS. holdout.json has not been touched. A cell that CLEARS or",
          "  IMPROVES is a direction, not an edge, and needs its own registration.",
          "  NOT LIVE. REQUIRE_MACD_POSITIVE and VOL_MULTIPLE are read by signals(),",
          "  which the live evaluator calls, so changing either alters live behaviour",
          "  and needs the parity test the last four live/backtest splits earned. The",
          "  sweep passes its values to backtest_session only; evaluate_last_bar still",
          "  reads the constants, so this run cannot have moved the trader.",
          "  NOT THE SUB-MINUTE QUESTION. Entering earlier within the MOVE and earlier",
          "  within the BAR are different axes; the second needs data this project does",
          "  not own and must be priced before it is bought.",
          "  NOT A SEARCH. Three families, every value named in the registration before",
          "  any code existed, and the boundary check is scored."]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/entry_sweep.txt")
    p.add_argument("--csv", default="var/reports/entry_sweep_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "entry_sweep")

    # DAY ORDER, not completion order -- float sums must not move with --jobs.
    books = {n: [] for n, _, _ in BOOKS}
    symdays, errors, error_days = 0, 0, []
    days = sorted(got)
    for day in days:
        r = got[day]
        for name in books:
            books[name] += r["books"][name]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    emit("\n".join(render(books, symdays, errors, days, elapsed, jobs, error_days,
                          universe=a.pairs, dataset=a.dataset)),
         a.out, header=f"common.entry_sweep pairs={a.pairs} dataset={a.dataset} "
                       f"sessions={len(days)} symbol_days={symdays} cut={cut} qty={QTY} "
                       f"registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
