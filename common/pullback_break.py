#!/usr/bin/env python3
r"""MCL-PB v2 against MCL -- a swing high, two red bars, buy the break.

    python -m common.pullback_break --jobs 8

Registered in docs/research/REGISTERED_pullback_break_v2.md before this
version ran (v1, REGISTERED_pullback_break.md, returned NOTHING). The verdict
rule below is §3 of that document, verbatim in code, read on the primary cell.
Three cells -- no target, 10c, 25c -- are the values Ben named, all printed,
none chosen from the table.

SAME TAPE, SAME PROCESS, SAME SETTINGS. Both books come out of one `run_day`
per session, over the same point-in-time universe, the same warm-up frames
(`pit_strategy.build_frame`), the same `first_seen` floor, 100 shares, and
MCL's published configuration (`pit_strategy.engine("mcl")`). The exit is
MCL's own engine in both -- `strategy/mcl/pullback_break.py` hands it each
trigger rather than re-implementing it.

OUTCOME. Per trade: the engine's `net` (IBKR tiered commission included) less a
round-trip friction. $4.26 is the measured figure and the one the verdict reads;
$1.00 and $8.92 are printed beside it.

HALVES are cut ONCE, at the median session of the sessions run, and both books
are split on that same date. `entry_shares.split` cuts each book at the median
of its own trade dates, which would compare the two strategies over different
halves.
"""
from __future__ import annotations

import argparse
import os
import statistics
import time
from collections import Counter
from datetime import date as _date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.entry_shares import MEASURED_FRICTION, PUBLISHED_TRADES, QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))
PAIRS = "var/state/screen_pairs_pit.json"
DROP = 5
PRE_CUT = dtime(7, 0)          # Ben's "before 7am ET"

MCL_NAME, PB_NAME = "MCL", "MCL-PB"
# (name, target_cents). The first is the primary cell the verdict is read on.
CELLS = (("PB2", None), ("PB2-10c", 0.10), ("PB2-25c", 0.25))
OUTCOMES = ("triggered", "band_refused", "refused_macd", "refused_busy",
            "expired", "window")


# --- the tape ---------------------------------------------------------------

def _et(ts) -> str:
    import pandas as pd
    return pd.Timestamp(ts).tz_convert(ET).strftime("%H:%M")


def trade_row(t, symbol: str, day: str, setup=None, index=None) -> dict:
    """One trade. With `setup` (and the signals frame's `index`), the MCL-PB
    rows also carry the level, its top and its arming bar -- the coordinates
    someone needs to find the trade on a chart."""
    import pandas as pd
    et = pd.Timestamp(t.entry_time).tz_convert(ET)
    r = {"symbol": symbol, "date": day, "net": float(t.net),
         "entry_px": float(t.entry_price), "entry_et": et.strftime("%H:%M"),
         "pre07": et.time() < PRE_CUT, "reason": t.reason,
         "bars_held": int(t.bars_held),
         "exit_et": _et(t.exit_time), "exit_px": float(t.exit_price)}
    if setup is not None:
        r["level"] = float(setup.peak)
        r["reds"] = int(setup.reds)
        if index is not None:
            r["top_et"] = _et(index[setup.peak_i])
            r["armed_et"] = _et(index[setup.armed_at])
    return r


def run_day(args: tuple) -> tuple:
    """One session: both books and every MCL-PB setup outcome. Picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    from strategy.mcl import pullback_break as PB

    paths, day, universe = args
    mod, extra = engine("mcl")
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                              # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    d = _date.fromisoformat(day)

    res = {"mcl": [], "pb": {name: [] for name, _ in CELLS},
           "setups": Counter(), "levels_per_symday": [], "symdays": 0, "errors": 0}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        # ALL OR NONE. A symbol-day that raises in any cell is dropped from
        # every book, or the books stop covering the same opportunities.
        try:
            base = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                        not_before=floor, **extra)
            dets = {name: PB.backtest_session_detail(df, d, ET, entry_shares=QTY,
                                                     not_before=floor,
                                                     target_cents=tc, **extra)
                    for name, tc in CELLS}
        except Exception:                                   # noqa: BLE001
            res["errors"] += 1
            continue
        res["symdays"] += 1
        res["mcl"] += [trade_row(t, rec["symbol"], day) for t in base]
        primary = dets[CELLS[0][0]]
        res["setups"].update(st.outcome for st in primary.setups)
        res["levels_per_symday"].append(len(primary.setups))
        for name, det in dets.items():
            for st in det.setups:
                if st.trade is not None:
                    res["pb"][name].append(trade_row(st.trade, rec["symbol"], day,
                                                     st, det.index))
    return day, res, ""


# --- arithmetic -------------------------------------------------------------

def net(rows, f: float) -> float:
    return sum(r["net"] - f for r in rows)


def per_trade(rows, f: float) -> float:
    return net(rows, f) / len(rows) if rows else 0.0


def halves(rows, cut: str) -> tuple[list, list]:
    return ([r for r in rows if r["date"] < cut], [r for r in rows if r["date"] >= cut])


def drop_top(rows, f: float, n: int = DROP) -> float:
    vals = sorted((r["net"] - f for r in rows), reverse=True)
    return sum(vals[n:])


def verdict(pb, mcl, cut: str) -> tuple[str, str]:
    """REGISTERED §3. Nothing here may change after a run."""
    f = MEASURED_FRICTION
    pa, pb2 = halves(pb, cut)
    ma, mb = halves(mcl, cut)
    if not pa or not pb2:
        return "NOTHING", "MCL-PB has an empty half"
    if per_trade(pa, f) > 0 and per_trade(pb2, f) > 0 and drop_top(pb, f) > 0:
        return "CLEARS", "positive per trade in both halves and after dropping the top 5"
    better_avg = per_trade(pa, f) > per_trade(ma, f) and per_trade(pb2, f) > per_trade(mb, f)
    better_tot = net(pa, f) > net(ma, f) and net(pb2, f) > net(mb, f)
    if better_avg and better_tot:
        return "IMPROVES", ("beats MCL per trade AND in total in both halves, "
                            "and still does not clear -- a direction, not an edge")
    why = []
    if not better_avg:
        why.append("does not beat MCL per trade in both halves")
    if not better_tot:
        why.append("does not beat MCL's total in both halves")
    return "NOTHING", "; ".join(why)


def pre07_holds(pb, mcl, cut: str) -> tuple[bool, str]:
    f = MEASURED_FRICTION
    p = [r for r in pb if r["pre07"]]
    m = [r for r in mcl if r["pre07"]]
    pa, pb2 = halves(p, cut)
    ma, mb = halves(m, cut)
    if not (pa and pb2 and ma and mb):
        return False, "a pre-07:00 half is empty in one of the books"
    ok = per_trade(pa, f) > per_trade(ma, f) and per_trade(pb2, f) > per_trade(mb, f)
    return ok, (f"halves {per_trade(pa, f):+.2f} vs {per_trade(ma, f):+.2f}, "
                f"{per_trade(pb2, f):+.2f} vs {per_trade(mb, f):+.2f}")


# --- report -----------------------------------------------------------------

def money(x: float) -> str:
    """Negatives bracketed, as every report here prints them."""
    return f"({abs(x):,.2f})" if x < 0 else f"{x:,.2f}"


def book_block(name: str, rows, cut: str, symdays: int) -> list[str]:
    L = [f"  {name}"]
    for lab, f in FRICTIONS:
        L.append(f"    at {lab:<6} trades {len(rows):>6,}   net {money(net(rows, f)):>12}"
                 f"   per trade {money(per_trade(rows, f)):>8}"
                 f"   per symbol-day {money(net(rows, f) / symdays if symdays else 0):>7}")
    a, b = halves(rows, cut)
    f = MEASURED_FRICTION
    wins = sum(1 for r in rows if r["net"] - f > 0)
    L += [f"    halves @ $4.26    early {len(a):>5,} {money(per_trade(a, f)):>8}/t "
          f"{money(net(a, f)):>11}   late {len(b):>5,} {money(per_trade(b, f)):>8}/t "
          f"{money(net(b, f)):>11}",
          f"    drop top {DROP} @ $4.26  {money(drop_top(rows, f)):>11}"
          f"   win rate {100 * wins / len(rows) if rows else 0:.1f}%", ""]
    return L


def cohort_table(mcl, pb, cut: str) -> list[str]:
    f = MEASURED_FRICTION
    L = ["BY ENTRY TIME (ET) -- Ben's claim is about the first row", "",
         f"  {'cohort':<14}{'book':<8}{'trades':>7}{'per trade':>11}{'net':>12}"
         f"{'early/t':>10}{'late/t':>10}", ""]
    for lab, sel in (("before 07:00", lambda r: r["pre07"]),
                     ("07:00-09:30", lambda r: not r["pre07"])):
        for name, rows in ((MCL_NAME, mcl), (PB_NAME, pb)):
            s = [r for r in rows if sel(r)]
            a, b = halves(s, cut)
            L.append(f"  {lab:<14}{name:<8}{len(s):>7,}{money(per_trade(s, f)):>11}"
                     f"{money(net(s, f)):>12}{money(per_trade(a, f)):>10}"
                     f"{money(per_trade(b, f)):>10}")
        L.append("")
    return L


def render(mcl, pbs: dict, setups: Counter, levels_per_symday: list, symdays: int,
           errors: int, days: list[str], elapsed: float, jobs: int) -> list[str]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    primary = CELLS[0][0]
    pb = pbs[primary]
    L = ["MCL-PB v2: A SWING HIGH, TWO RED BARS, BUY THE BREAK", "",
         "  registered  docs/research/REGISTERED_pullback_break_v2.md",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY book", ""]

    pub = PUBLISHED_TRADES.get("mcl")
    L += ["POPULATION CHECK", "", f"  MCL trades here     {len(mcl):,}"]
    if pub is not None:
        ok = len(mcl) == pub
        L.append(f"  published count     {pub:,}   " + ("matches" if ok else "*** DOES NOT MATCH ***"))
        if not ok:
            L += ["", "  A DIFFERENT BOOK FROM THE PUBLISHED ONE. The comparison below is",
                  "  still like-for-like (same run), but do not quote MCL's line as the",
                  "  published figure until this reconciles."]
    L += [""]

    total = sum(setups.values())
    L += [f"WHAT HAPPENED TO EVERY LEVEL ({primary}, the exits do not change this)", ""]
    for k in OUTCOMES:
        v = setups.get(k, 0)
        L.append(f"  {k:<14}{v:>8,}   {100 * v / total if total else 0:5.1f}%")
    L += [f"  {'levels':<14}{total:>8,}"]
    if levels_per_symday:
        L.append(f"  per symbol-day: median {statistics.median(levels_per_symday):.0f}, "
                 f"max {max(levels_per_symday)}")
    L += ["",
          "  refused_busy = the level was crossed while a position was already",
          "  open, before first_seen, or on the final bar. MCL's signal plays no",
          "  part in this rule, so it fires without MCL's filter.", ""]

    L += ["THE BOOKS", ""]
    L += book_block(MCL_NAME, mcl, cut, symdays)
    for name, _tc in CELLS:
        L += book_block(name, pbs[name], cut, symdays)
    for name, _tc in CELLS:
        rows = pbs[name]
        mix = Counter(r["reason"] for r in rows)
        L.append(f"  {name} exits: " + ", ".join(f"{k} {v:,}" for k, v in mix.most_common()))
    L += [""]
    L += cohort_table(mcl, pb, cut)

    tag, why = verdict(pb, mcl, cut)
    held, pwhy = pre07_holds(pb, mcl, cut)
    L += [f"THE VERDICT (registered §3, $4.26, read on {primary})", "",
          f"  {tag}: {why}",
          f"  PRE-07 {'HOLDS' if held else 'DOES NOT HOLD'}: {pwhy}", ""]
    for name, _tc in CELLS[1:]:
        t2, w2 = verdict(pbs[name], mcl, cut)
        L.append(f"  {name} would read {t2}: {w2}  -- reported, not registered")
    L += [""]
    if tag == "CLEARS":
        L += ["  A candidate for the holdout, under its own registration. Not a rule to ship.", ""]

    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT A QUEUE MODEL. A buy-stop is assumed filled at max(level, open)",
          "  plus a tick the moment the bar trades through; a target is assumed",
          "  filled at its price the moment the bar's high reaches it. On a thin",
          "  pre-market book neither is guaranteed.",
          "  NOT A SEARCH. The verdict is read on one cell. The target cells are",
          "  the two values Ben named; a better-looking cell is a direction.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/pullback_break_mcl.txt")
    p.add_argument("--csv", default="var/reports/pullback_break_trades.csv")
    return p


def write_csv(path: str, mcl, pbs: dict) -> None:
    import csv
    cols = ["book", "symbol", "date", "top_et", "level", "reds", "armed_et",
            "entry_et", "entry_px", "exit_et", "exit_px", "reason", "bars_held",
            "net", "pre07"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for name, rows in [(MCL_NAME, mcl)] + list(pbs.items()):
            for r in rows:
                w.writerow(dict(r, book=name))


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_h0 import load_pit
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_sim import date_of, window_slices

    a = build_parser().parse_args(argv)
    by_date = load_pit(Path(a.pairs))
    archive = Path(a.archive) if a.archive else default_archive()
    slices = {date_of(p): p for p in window_slices(archive, a.dataset)}
    days = sorted(by_date)
    if a.limit:
        days = days[:a.limit]
    have = [d for d in days if d in slices]

    tasks = []
    for k, day in enumerate(have):
        first = max(0, k - WARMUP_SESSIONS)
        tasks.append(([str(slices[d]) for d in have[first:k + 1]], day, by_date[day]))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"pullback_break: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
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

    # DAY ORDER, not completion order -- float sums must not move with --jobs.
    mcl, pbs, setups, lps, symdays, errors = [], {n: [] for n, _ in CELLS}, Counter(), [], 0, 0
    run_days = sorted(got)
    for day in run_days:
        r = got[day]
        mcl += r["mcl"]
        for name in pbs:
            pbs[name] += r["pb"][name]
        setups.update(r["setups"])
        lps += r["levels_per_symday"]
        symdays += r["symdays"]
        errors += r["errors"]

    emit("\n".join(render(mcl, pbs, setups, lps, symdays, errors, run_days,
                          time.time() - t0, jobs)), a.out)
    write_csv(a.csv, mcl, pbs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
