#!/usr/bin/env python3
r"""Two pre-market change thresholds, the same engines, one report.

    python -m common.change_threshold --baseline var/state/screen_pairs_pit_itch_p50.json \
        --variant var/state/screen_pairs_pit_itch_chg50.json --dataset XNAS.ITCH

WHAT THIS IS NOT, AND IT IS THE REASON THE MODULE EXISTS
--------------------------------------------------------
Raising the screen's `premarket_change` clause is NOT a gate on a book. The
three gates of 2026-09-17 (H-B1, H-B3, H-B4) took the published universe and
refused some of its entry bars, so the gated book was a SUBSET of the
baseline's trades and `gate_study` could read the difference directly.

A screen threshold changes the UNIVERSE, and that is a different object:

  1. A symbol-day that never reaches the new threshold disappears entirely,
     with every trade on it.
  2. A symbol-day that reaches 20% at 05:10 and 50% at 07:40 SURVIVES with a
     later entry floor -- so its trades are not the baseline's trades. Bars
     the baseline was already in a position for become live signals
     (`PROGRAM_INDEX` §4, "signal-ordinal is not book-ordinal").

So the variant book is not a subset, and a reading that assumes it is will
be wrong in the direction that flatters the tighter screen. What still holds
is the reading that killed the three gates: on a book whose average trade
loses, ANY rule that removes trades improves every total-based figure. The
verdict is therefore `gate_study.verdict` -- per trade with a margin of one
round trip, against the abstention control -- and the extra blocks here
(what the screen dropped, how far the floor moved, how many entries are new)
are the cost side, printed and not read into the verdict.

DENOMINATOR. Deltas are divided by the BASELINE's symbol-day count, because
the question is what the change does to the whole programme, and the tighter
screen's own symbol-day count is smaller by construction. Levels are printed
against each book's own count in THE BOOKS.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from common.entry_shares import MEASURED_FRICTION, QTY
from common.first_entry_skip import (book_block, key, money, net, per_trade, trade_row)
from common.gate_study import build_tasks, jobs_from, run_sessions, verdict_block
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_change_threshold.md"

# (book label suffix, engine). Order is the order printed.
ENGINES = (("MCL", "mcl"), ("MC5", "mc5"))


def run_day(args: tuple) -> tuple:
    """One session, both engines, one universe. Picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for _, name in ENGINES}
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

    res = {"books": {label: [] for label, _ in ENGINES},
           "symdays": 0, "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        # ALL OR NONE, as in first_entry_skip: a symbol-day that raises in one
        # engine is dropped from both, or the books stop covering the same
        # opportunities.
        try:
            got = {}
            for label, eng in ENGINES:
                mod, extra = engines[eng]
                got[label] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                  not_before=floor, **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for label, trades in got.items():
            res["books"][label] += [trade_row(t, rec["symbol"], day, k)
                                    for k, t in enumerate(trades, 1)]
    return day, res, ""


# --- the universe side ------------------------------------------------------------

def universe_rows(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def symday_index(rows) -> dict[tuple, dict]:
    return {(r["symbol"], r["date"]): r for r in rows}


def floor_shift_minutes(a: dict, b: dict) -> float:
    """How much later b's entry floor is than a's, in minutes."""
    ta = pd.Timestamp(a["first_seen"]).tz_convert(ET)
    tb = pd.Timestamp(b["first_seen"]).tz_convert(ET)
    return (tb - ta).total_seconds() / 60.0


def universe_block(bname: str, vname: str, brows, vrows) -> list[str]:
    bi, vi = symday_index(brows), symday_index(vrows)
    kept = sorted(set(bi) & set(vi))
    dropped = sorted(set(bi) - set(vi))
    added = sorted(set(vi) - set(bi))
    shifts = [floor_shift_minutes(bi[k], vi[k]) for k in kept]
    later = [s for s in shifts if s > 0]
    ser = pd.Series(shifts) if shifts else pd.Series(dtype=float)
    L = [f"THE UNIVERSE: {vname} against {bname}", "",
         f"  {bname:<12} symbol-days {len(bi):>7,}   sessions {len({d for _, d in bi}):>4,}",
         f"  {vname:<12} symbol-days {len(vi):>7,}   sessions {len({d for _, d in vi}):>4,}",
         f"  kept {len(kept):,}   dropped {len(dropped):,} "
         f"({100.0 * len(dropped) / len(bi) if bi else 0:.1f}% of {bname})   "
         f"added {len(added):,}", ""]
    if added:
        L += ["  *** ADDED symbol-days: a TIGHTER screen cannot add names. If this is",
              "      non-zero the two runs did not screen the same sessions. ***", ""]
    L += ["  ENTRY FLOOR on the symbol-days both keep (minutes later under "
          f"{vname}):",
          f"    moved later {len(later):,} of {len(kept):,} "
          f"({100.0 * len(later) / len(kept) if kept else 0:.1f}%)"]
    if len(ser):
        L += [f"    median {ser.median():.0f}   p90 {ser.quantile(0.9):.0f}   "
              f"max {ser.max():.0f}",
              "",
              "    A later floor is not a smaller book. It removes the early",
              "    entries and turns bars the baseline was mid-trade on into",
              "    live signals, so the variant's trades are NOT a subset."]
    L += [""]
    return L


def dropped_block(bname: str, vname: str, base_rows, brows, vrows) -> list[str]:
    """What the baseline earned on the symbol-days the tighter screen removed.

    Printed for the cost, not read into the verdict: on a losing book the
    trades removed are mostly losses, which is exactly what the abstention
    control exists to price."""
    f = MEASURED_FRICTION
    gone = set(symday_index(brows)) - set(symday_index(vrows))
    rows = [r for r in base_rows if (r["symbol"], r["date"]) in gone]
    losers = [r for r in rows if r["net"] - f <= 0]
    winners = [r for r in rows if r["net"] - f > 0]
    return [f"WHAT {vname} DROPPED OF {bname} (trades on symbol-days the tighter screen removed)", "",
            f"  symbol-days removed {len(gone):>6,}",
            f"  trades on them      {len(rows):>6,}   net {money(net(rows, f)):>12}"
            f"   per trade {money(per_trade(rows, f)):>8}",
            f"    losses avoided    {len(losers):>6,}   {money(net(losers, f)):>12}",
            f"    winners lost      {len(winners):>6,}   {money(net(winners, f)):>12}", ""]


def survivor_block(bname: str, vname: str, base_rows, var_rows) -> list[str]:
    """How much of the variant's book is literally the baseline's trades."""
    f = MEASURED_FRICTION
    bkeys = {key(r) for r in base_rows}
    same = [r for r in var_rows if key(r) in bkeys]
    fresh = [r for r in var_rows if key(r) not in bkeys]
    return [f"HOW MUCH OF {vname} IS {bname} (identical symbol/date/entry/ordinal)", "",
            f"  shared  {len(same):>6,} of {len(var_rows):,} "
            f"({100.0 * len(same) / len(var_rows) if var_rows else 0:.1f}%)"
            f"   per trade {money(per_trade(same, f)):>8}",
            f"  new     {len(fresh):>6,}"
            f"   per trade {money(per_trade(fresh, f)):>8}",
            "",
            "  Agreement between two different trade sets is not replication",
            "  (PROGRAM_INDEX §4). A low share here is the reason this is a",
            "  universe study and not a gate study.", ""]


def decomposition_block(bname: str, vname: str, base_rows, var_rows, vrows) -> list[str]:
    """Why the variant lands where it does: SELECTION against the CLOCK.

    Partition the baseline's book by the variant's universe, then by whether
    the variant's later entry floor still admits the trade:

        @baseline               the whole book
      - symbol-days dropped     names the tighter screen never surfaces
      = names the screen keeps  SELECTION, and it is look-ahead: knowing at
                                04:10 that a name will reach the threshold
                                later is not knowable at 04:10
      - lost to the floor       trades on those names that happen before the
                                name clears the tighter clause -- THE COST OF
                                WAITING
      + new after the floor     entries the later floor creates, because bars
                                the baseline was mid-position on become
                                signals
      = @variant                the book that could actually be traded

    The middle row is NOT TRADEABLE and is printed for attribution only.
    """
    f = MEASURED_FRICTION
    kept_days = {(r["symbol"], r["date"]) for r in vrows}
    on_kept = [r for r in base_rows if (r["symbol"], r["date"]) in kept_days]
    gone = [r for r in base_rows if (r["symbol"], r["date"]) not in kept_days]
    vk = {key(r) for r in var_rows}
    bk = {key(r) for r in base_rows}
    floor_out = [r for r in on_kept if key(r) not in vk]
    fresh = [r for r in var_rows if key(r) not in bk]

    def row(label, rows, note=""):
        return (f"  {label:<26} {len(rows):>6,} {money(net(rows, f)):>13}"
                f" {money(per_trade(rows, f)):>10}   {note}")

    return [f"SELECTION AGAINST THE CLOCK: {vname} decomposed out of {bname}", "",
            f"  {'':26} {'trades':>6} {'net':>13} {'per trade':>10}",
            row(f"{bname} whole book", base_rows),
            row("- symbol-days dropped", gone),
            row("= names the screen keeps", on_kept,
                f"SELECTION {per_trade(on_kept, f) - per_trade(base_rows, f):+.2f}/trade"),
            row("- lost to the floor", floor_out, "THE COST OF WAITING"),
            row("+ new after the floor", fresh),
            row(f"= {vname} whole book", var_rows,
                f"NET {per_trade(var_rows, f) - per_trade(base_rows, f):+.2f}/trade"),
            "",
            "  'names the screen keeps' is NOT A TRADEABLE ARM. It prices the",
            "  name list alone, at the baseline's entry floor, which requires",
            "  knowing before the fact that a name will clear the tighter",
            "  clause later in the morning. It is printed to attribute the",
            "  result, never as a candidate.", ""]


# --- the report -------------------------------------------------------------------

def render(books: dict, uni: dict, labels: dict, symdays: dict, errors: int,
           days: list[str], cut: str, elapsed: float, jobs: int,
           error_days: list | None = None) -> list[str]:
    b, v = labels["base"], labels["var"]
    L = [f"THE PRE-MARKET CHANGE THRESHOLD: {v}% AGAINST {b}%", "",
         f"  registered  {REGISTERED}",
         f"  baseline universe  {labels['base_pairs']}",
         f"  variant  universe  {labels['var_pairs']}",
         f"  {len(days):,} sessions in the baseline   halves cut at {cut}",
         f"  symbol-days  {b}%: {symdays['base']:,}   {v}%: {symdays['var']:,}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)",
         "",
         "  DELTAS ARE PER BASELINE SYMBOL-DAY. The variant's own symbol-day",
         f"  count is smaller by construction, so dividing by it would price a",
         "  smaller programme as a better one.", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from BOTH books:"]
        L += [f"    {e}" for e in (error_days or [])[:20]]
        L += [""]
    L += universe_block(f"chg>={b}%", f"chg>={v}%", uni["base"], uni["var"])
    L += ["THE BOOKS", ""]
    for name, rows in books.items():
        own = symdays["var"] if name.endswith(f"@{v}") else symdays["base"]
        L += book_block(name, rows, cut, own)
    for label, _ in ENGINES:
        bn, vn = f"{label}@{b}", f"{label}@{v}"
        L += decomposition_block(bn, vn, books[bn], books[vn], uni["var"])
        L += survivor_block(bn, vn, books[bn], books[vn])
        L += dropped_block(bn, vn, books[bn], uni["base"], uni["var"])
        L += verdict_block(bn, vn, books[bn], books[vn], cut, symdays["base"])
    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT A CAP MODEL. Each symbol-day runs alone; live, 29% of buy",
          "    attempts were refused by the concurrency cap and a tighter",
          "    screen frees slots this cannot price.",
          "  NOT THE LIVE SCREEN. tv_screener.PREMARKET_CHANGE_MIN is unchanged;",
          "    this measured a threshold, it did not ship one.",
          "  NOT A SEARCH. One threshold decides; any ladder printed beside this",
          "    report is descriptive and was declared as such before the run.", ""]
    return L


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--baseline", default="var/state/screen_pairs_pit_itch_p50.json")
    p.add_argument("--variant", required=True)
    p.add_argument("--base-label", default="20")
    p.add_argument("--var-label", default="50")
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.ITCH")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--cache", default=None, metavar="JSONL",
                   help="append-only per-session cache; a run that does not "
                        "finish is resumed by repeating the same command")
    p.add_argument("--budget", type=float, default=None,
                   help="seconds of session work per call, with --cache")
    p.add_argument("--out", default="var/reports/change_threshold.txt")
    p.add_argument("--csv", default="var/reports/change_threshold_trades.csv")
    return p


def cache_load(path: str | None, arm: str) -> dict:
    """Sessions already run for this arm, keyed by day.

    The runner this is driven from cannot hold a process open for longer than
    a couple of minutes, so a full pass is made out of several. The cache is
    append-only JSONL, one line per session per arm, and a resumed run is
    bit-identical to an unbroken one because `run_day` reads one session and
    the day order is restored by `sorted()` before anything is summed.
    """
    if not path or not Path(path).exists():
        return {}
    got: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec["arm"] == arm:
                got[rec["day"]] = rec["res"]
    return got


def cache_append(path: str, arm: str, day: str, res: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"arm": arm, "day": day, "res": res}) + "\n")


def collect(pairs_path: str, archive, dataset: str, limit, jobs: int, label: str,
            cache: str | None = None, arm: str = "", budget: float | None = None):
    tasks, _ = build_tasks(pairs_path, archive, dataset, limit)
    done = cache_load(cache, arm)
    todo = [t for t in tasks if t[1] not in done]
    if cache and todo:
        if budget is not None:
            t0 = time.time()
            kept = []
            for t in todo:
                if time.time() - t0 > budget:
                    break
                day, res, err = run_day(t)
                if err:
                    print(f"  ! {day}: {err}", flush=True)
                if res is not None:
                    cache_append(cache, arm, day, res)
                    done[day] = res
                kept.append(t)
            left = len(todo) - len(kept)
            print(f"{label}: {len(kept):,} run this call, {left:,} left", flush=True)
            if left:
                raise SystemExit(f"INCOMPLETE: {left:,} session(s) of {label} remain. "
                                 f"Run the same command again.")
        else:
            got, _ = run_sessions(run_day, todo, jobs, label)
            for day, res in got.items():
                cache_append(cache, arm, day, res)
                done[day] = res
    got, elapsed = (done, 0.0) if cache else run_sessions(run_day, tasks, jobs, label)
    books = {name: [] for name, _ in ENGINES}
    symdays = errors = 0
    error_days: list[str] = []
    for day in sorted(got):
        res = got[day]
        symdays += res["symdays"]
        errors += res["errors"]
        error_days += res["error_days"]
        for name in books:
            books[name] += res["books"][name]
    return books, symdays, errors, error_days, sorted(got), elapsed


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    from common.databento_fetch import default_archive
    archive = Path(a.archive) if a.archive else default_archive()
    jobs = jobs_from(a.jobs)
    t0 = time.time()

    vb, vsd, verr, ved, _, _ = collect(a.variant, archive, a.dataset, a.limit,
                                       jobs, f"variant chg>={a.var_label}%",
                                       a.cache, f"var{a.var_label}", a.budget)
    bb, bsd, berr, bed, bdays, _ = collect(a.baseline, archive, a.dataset, a.limit,
                                           jobs, f"baseline chg>={a.base_label}%",
                                           a.cache, f"base{a.base_label}", a.budget)
    elapsed = time.time() - t0

    books = {}
    for label, _ in ENGINES:
        books[f"{label}@{a.base_label}"] = bb[label]
        books[f"{label}@{a.var_label}"] = vb[label]
    # ONE cut for both books, taken from the baseline's sessions. Two books
    # cut at their own medians are not two halves of the same calendar.
    cut = bdays[len(bdays) // 2] if len(bdays) >= 2 else (bdays[0] if bdays else "")
    uni = {"base": universe_rows(a.baseline), "var": universe_rows(a.variant)}
    labels = {"base": a.base_label, "var": a.var_label,
              "base_pairs": a.baseline, "var_pairs": a.variant}
    lines = render(books, uni, labels, {"base": bsd, "var": vsd}, berr + verr,
                   bdays, cut, elapsed, jobs, bed + ved)
    emit("\n".join(lines), a.out)

    from common.gate_study import write_csv, write_meta
    write_csv(a.csv, books)
    write_meta(a.csv, bdays, bsd, cut, {"baseline": a.baseline, "variant": a.variant,
                                        "base_label": a.base_label,
                                        "var_label": a.var_label,
                                        "variant_symbol_days": vsd})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
