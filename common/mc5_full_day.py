#!/usr/bin/env python3
r"""MC5 extended to 04:00-20:00 ET, on the point-in-time universe.

    python -m common.mc5_full_day --jobs 8

Registered in docs/research/REGISTERED_mc5_full_day.md (amendments A-C) before
this file existed. Four books from one pass per session:

    A    04:00-09:30, PRE-MARKET frames, v2 universe   the published book, a
                                                       reconciliation only
    A'   04:00-09:30, FULL-DAY frames,   v2 universe   THE SCORED CONTROL
    B    04:00-20:00, FULL-DAY frames,   v2 universe   frozen: only names the
                                                       screen found by 09:30
    C    04:00-20:00, FULL-DAY frames,   DAY universe  the running screen --
                                                       the primary arm

A and A' differ only in warm-up (amendment C): the published runs warm up on
the prior PRE-MARKET slice, and a full-day arm cannot. MACD is an EMA with
unbounded memory, so the two books are not trade-for-trade equal and the gap
between them prices the warm-up, not the strategy.

THE SCORED READING IS C's ENTRIES AT OR AFTER 09:30 (§4). They are the trades
the extension ADDS; the rest of C is A' with a later flatten. Everything is
reported by block (PRE / RTH / POST by entry time) plus CARRIED -- the
pre-market entries whose exit moved off 09:30.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date as _date, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, pct, share_above_zero
from common.entry_shares import MEASURED_FRICTION, QTY
from common.first_entry_skip import (FRICTIONS, delta_by_symbol, drop_top, halves, key,
                                     money, net, per_trade, trade_row)
from common.report_io import emit

ET = ZoneInfo("America/New_York")
REGISTERED = "docs/research/REGISTERED_mc5_full_day.md"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DAY_PAIRS = "var/state/screen_pairs_pit_itch_day.json"
DATASET = "XNAS.ITCH"
DAY_END = dtime(20, 0)
DROP_N = 5                       # §4: drop-top-5 symbols on the added trades
BLOCK_EDGES = (("PRE", "04:00", "09:30"), ("RTH", "09:30", "16:00"),
               ("POST", "16:00", "20:00"))

# The published v2 baseline this run must reproduce (screen_itch_v2 RESULT, via
# REGISTERED_giveback_cap.md A1): MC5 6,462 trades at (8.57)/trade, $4.26.
PUBLISHED = {PAIRS: (6462, -8.57)}

ARMS = ("A", "A2", "B", "C")
LABEL = {"A": "A  published frames, 09:30", "A2": "A' full-day frames, 09:30",
         "B": "B  full day, frozen universe", "C": "C  full day, running screen"}


# --- one session ------------------------------------------------------------------

def block_of(entry_et: str) -> str:
    for name, lo, hi in BLOCK_EDGES:
        if lo <= entry_et < hi:
            return name
    return "OUT"


def engine_arms(M, pre_df, day_df, d, floor) -> dict[str, list]:
    """The three universe-A arms for one symbol-day, in one place so the
    window each arm runs in is testable without an archive.

    A  published frames, the module's own 09:30 (session_end=None -- the
       bit-identical path, so the published book is reproduced and not merely
       approximated by passing 09:30 back in).
    A' the same rule on the full-day frames: the scored control.
    B  the full-day frames to 20:00.
    """
    return {"A": M.backtest_session(pre_df, d, ET, entry_shares=QTY, not_before=floor),
            "A2": M.backtest_session(day_df, d, ET, entry_shares=QTY, not_before=floor),
            "B": M.backtest_session(day_df, d, ET, entry_shares=QTY, not_before=floor,
                                    session_end=DAY_END)}


def run_day(args: tuple) -> tuple:
    """One session, all four arms. Picklable."""
    import pandas as pd
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.screen_day import BLOCKS
    from strategy.mc5 import mc5 as M

    pre_paths, day_paths, day, universe, day_universe = args
    want = {r["symbol"] for r in universe} | {r["symbol"] for r in day_universe}

    def load(paths):
        parts = []
        for p in paths:
            try:
                f = read_dbn(Path(p))
            except Exception as e:                          # noqa: BLE001
                return None, f"unreadable ({type(e).__name__}: {e})"
            if not f.empty:
                # Filtered HERE, before anything is concatenated: a regular-hours
                # slice is the whole tape, and holding several of them per worker
                # is the difference between a run that fits in memory and one
                # that does not.
                parts.append(f[f["symbol"].isin(want)])
        if not parts:
            return None, ""
        return pd.concat(parts).sort_index(), ""

    pre_frame, err = load(pre_paths)
    if err:
        return day, None, err
    day_frame, err = load(day_paths)
    if err:
        return day, None, err
    if pre_frame is None or day_frame is None:
        return day, None, ""

    d = _date.fromisoformat(day)
    res = {"books": {a: [] for a in ARMS}, "symdays": 0, "errors": 0, "error_days": []}
    day_floor = {r["symbol"]: r for r in day_universe}

    for rec in universe:
        sym = rec["symbol"]
        if not rec.get("first_seen"):
            continue
        pre_df = pre_frame[pre_frame["symbol"] == sym].sort_index(kind="mergesort")
        day_df = day_frame[day_frame["symbol"] == sym].sort_index(kind="mergesort")
        if pre_df.empty or day_df.empty:
            continue
        floor = first_seen_time(rec)
        try:
            got = engine_arms(M, pre_df, day_df, d, floor)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{sym} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for arm, trades in got.items():
            res["books"][arm] += [trade_row(t, sym, day, k) for k, t in enumerate(trades, 1)]

    # ARM C runs the DAY universe, which is a different set of names: every name
    # the running screen surfaced, each floored at its own first_seen.
    for rec in day_universe:
        sym = rec["symbol"]
        if not rec.get("first_seen"):
            continue
        df = day_frame[day_frame["symbol"] == sym].sort_index(kind="mergesort")
        if df.empty:
            continue
        try:
            trades = M.backtest_session(df, d, ET, entry_shares=QTY,
                                        not_before=first_seen_time(rec),
                                        session_end=DAY_END)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"C {sym} {day}: {type(e).__name__}: {e}")
            continue
        res["books"]["C"] += [trade_row(t, sym, day, k) for k, t in enumerate(trades, 1)]
    res["c_symdays"] = len(day_floor)
    return day, res, ""


# --- arithmetic --------------------------------------------------------------------

def added(rows) -> list[dict]:
    """§4: the trades the extension adds -- entries at or after 09:30."""
    return [r for r in rows if r["entry_et"] >= "09:30"]


def carried(base, ext) -> list[tuple[dict, dict]]:
    """Pre-market entries present in both books, paired. Their entry is the same
    and their exit may not be: the 09:30 flatten is gone in the extended book."""
    b = {key(r): r for r in base if r["entry_et"] < "09:30"}
    return [(b[key(r)], r) for r in ext if r["entry_et"] < "09:30" and key(r) in b]


def by_block(rows) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(block_of(r["entry_et"]), []).append(r)
    return out


def drop_top_symbols(rows, f: float, n: int = DROP_N) -> float:
    """Net after removing the n SYMBOLS that contributed most."""
    by: dict[str, float] = {}
    for r in rows:
        by[r["symbol"]] = by.get(r["symbol"], 0.0) + (r["net"] - f)
    return sum(sorted(by.values(), reverse=True)[n:])


def session_median(rows, f: float, sessions: int | None = None) -> float:
    """Median session P/L over the sessions that HAVE an added trade, unless
    `sessions` is given -- then every session run counts, zero-filled.

    Both are printed. The scored one is the traded-session median (§4 item 5):
    a zero-filled median answers "does the extension trade on most days",
    which is a different question and, on a rule that trades on a minority of
    sessions, is 0.00 whatever the trades did."""
    import statistics
    by: dict[str, float] = {}
    for r in rows:
        by[r["date"]] = by.get(r["date"], 0.0) + (r["net"] - f)
    if not by:
        return 0.0
    vals = list(by.values())
    if sessions is not None and sessions > len(vals):
        vals += [0.0] * (sessions - len(vals))
    return statistics.median(vals)


def verdict(add: list[dict], cut: str, baseline_ok: bool,
            sessions: int | None = None) -> tuple[str, str, dict]:
    """REGISTERED §4, on the ADDED trades. Nothing here may change after a run."""
    f = MEASURED_FRICTION
    n: dict = {}
    n["n"] = len(add)
    n["per_trade"] = per_trade(add, f)
    n["net"] = net(add, f)
    a, b = halves(add, cut)
    n["halves"] = (per_trade(a, f), per_trade(b, f), len(a), len(b))
    n["drop5"] = drop_top_symbols(add, f)
    boot = cluster_bootstrap({s: v for s, v in
                              delta_by_symbol({(r["symbol"], i): r["net"] - f
                                               for i, r in enumerate(add)}).items()})
    n["boot_p"] = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    n["boot_lo"] = pct(boot["totals"], 0.025) if boot["totals"] else 0.0
    n["boot_hi"] = pct(boot["totals"], 0.975) if boot["totals"] else 0.0
    n["n_syms"] = boot["n_syms"]
    n["median"] = session_median(add, f)
    n["median_all"] = session_median(add, f, sessions)
    n["sessions_traded"] = len({r["date"] for r in add})

    if not baseline_ok:
        return "NO VERDICT", "arm A does not reproduce the published figure (amendment C)", n
    if not add:
        return "NOTHING", "the extension added no trades at all", n
    if not (a and b):
        return "NOTHING", "a half is empty", n
    failed = []
    if not n["per_trade"] > 0:
        failed.append(f"1 (per trade {money(n['per_trade'])} at $4.26)")
    if not (n["halves"][0] > 0 and n["halves"][1] > 0):
        failed.append("2 (both halves positive)")
    if not n["drop5"] > 0:
        failed.append(f"3 (drop-top-{DROP_N} symbols {money(n['drop5'])})")
    if not n["boot_p"] >= BOOT_MIN_P:
        failed.append(f"4 (cluster bootstrap P={n['boot_p']:.3f} < {BOOT_MIN_P})")
    if not n["median"] > 0:
        failed.append(f"5 (session median {money(n['median'])})")
    if failed:
        return "NOTHING", "fails " + "; ".join(failed), n
    return "PASSES", "all five readings on the added trades", n


def baseline_check(rows, expect) -> tuple[bool, str]:
    if expect is None:
        return False, "no published figure for this universe (pass --expect)"
    n, pt = expect
    got = per_trade(rows, MEASURED_FRICTION)
    ok = len(rows) == n and abs(got - pt) < 0.005
    return ok, (f"{len(rows):,} trades, {money(got)}/trade against published {n:,}, "
                f"{money(pt)} -- " + ("matches" if ok else "*** DOES NOT MATCH ***"))


# --- report --------------------------------------------------------------------

def book_block(name: str, rows, cut: str, symdays: int) -> list[str]:
    f = MEASURED_FRICTION
    L = [f"  {LABEL.get(name, name)}"]
    for lab, fl in FRICTIONS:
        L.append(f"    at {lab:<6} trades {len(rows):>6,}   net {money(net(rows, fl)):>12}"
                 f"   per trade {money(per_trade(rows, fl)):>8}"
                 f"   per symbol-day {money(net(rows, fl) / symdays if symdays else 0):>7}")
    blocks = by_block(rows)
    L.append("    by entry block @ $4.26   " + "   ".join(
        f"{b} {len(blocks.get(b, [])):,} {money(per_trade(blocks.get(b, []), f))}/t"
        for b, _lo, _hi in BLOCK_EDGES))
    reasons: dict[str, int] = {}
    for r in rows:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    L += ["    exits: " + "   ".join(f"{k} {v:,}" for k, v in sorted(reasons.items())), ""]
    return L


def render(books, symdays, c_symdays, cut, sessions, elapsed, jobs, a, expect,
           errors, error_days) -> list[str]:
    f = MEASURED_FRICTION
    ok, why = baseline_check(books["A"], expect)
    L = ["MC5 EXTENDED TO 04:00-20:00", "",
         f"  registered  {REGISTERED} (amendments A-C)",
         f"  dataset {a.dataset}   universe {a.pairs}   day universe {a.day_pairs}",
         f"  {sessions} sessions   {symdays:,} symbol-days (A/A'/B)   "
         f"{c_symdays:,} (C)   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", "",
         "THE RECONCILIATION (amendment C)", "",
         f"  arm A: {why}", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped:"]
        L += [f"    {e}" for e in (error_days or [])[:10]] + [""]
    L += ["THE BOOKS", ""]
    for arm in ARMS:
        L += book_block(arm, books[arm], cut,
                        c_symdays if arm == "C" else symdays)

    L += ["WARM-UP, PRICED (A' against A -- not a finding about the strategy)", "",
          f"  per trade {per_trade(books['A2'], f) - per_trade(books['A'], f):+.2f}"
          f"   trades {len(books['A2']):,} against {len(books['A']):,}", ""]

    for arm in ("B", "C"):
        add = added(books[arm])
        tag, why2, n = verdict(add, cut, ok, sessions)
        head = ("THE VERDICT: C's added trades (registered §4)" if arm == "C"
                else "ARM B's added trades -- reported, not scored")
        L += [head, "",
              f"  1. {n['n']:,} added trades   per trade {money(n['per_trade'])}"
              f"   net {money(n['net'])}",
              f"  2. halves   early {n['halves'][2]:,} {money(n['halves'][0])}/t"
              f"   late {n['halves'][3]:,} {money(n['halves'][1])}/t",
              f"  3. drop-top-{DROP_N} symbols {money(n['drop5'])}",
              f"  4. cluster bootstrap P(total > 0) = {n['boot_p']:.3f} "
              f"[{money(n['boot_lo'])}, {money(n['boot_hi'])}] over {n['n_syms']:,} symbols"
              f"  (RESAMPLES {RESAMPLES}, SEED {SEED})",
              f"  5. session median {money(n['median'])} over the "
              f"{n['sessions_traded']:,} session(s) with an added trade"
              f"   (zero-filled over all {sessions:,}: {money(n['median_all'])})",
              "", f"  {tag if arm == 'C' else 'REPORTED'}: {why2}", ""]

    for arm in ("B", "C"):
        pairs = carried(books["A2"], books[arm])
        delta = sum((x["net"] - f) - (b["net"] - f) for b, x in pairs)
        moved = sum(1 for b, x in pairs if x["exit_et"] != b["exit_et"])
        L += [f"CARRIED TRADES: {arm} against A' -- reported, not scored", "",
              f"  {len(pairs):,} pre-market entries in both books; {moved:,} exited at a "
              f"different time once 09:30 stopped flattening",
              f"  P/L change {money(delta)}", ""]

    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been spent.",
          "  NOT A CAP MODEL. Each symbol-day runs alone; live, 29% of buy attempts",
          "  were refused by the concurrency cap.",
          "  NOT A LIVE PARITY RUN. The trader still stops at 09:30 and has no",
          "  RTH/POST screen; this is a backtest of the rule, nothing more.",
          "  NOT A MEASURED RTH THRESHOLD. The screen's volume clause after 09:30",
          "  carries the 09:30 capture (amendment B).", ""]
    return L


# --- cli ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--day-pairs", default=DAY_PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--expect", default=None, help='e.g. "6462:-8.57"')
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/mc5_full_day.txt")
    p.add_argument("--csv", default="var/reports/mc5_full_day_trades.csv")
    return p


CSV_COLS = ["arm", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
            "exit_px", "reason", "bars_held", "net"]


def write_csv(path: str, books: dict) -> None:
    import csv
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for arm in ARMS:
            for r in books[arm]:
                w.writerow(dict(r, arm=arm))


def load_pairs(path: Path) -> dict[str, list[dict]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["date"], []).append(r)
    return out


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    from common.pit_strategy import WARMUP_SESSIONS
    from common.screen_day import BLOCKS, complete, day_slices
    from common.screen_sim import window_slices

    a = build_parser().parse_args(argv)
    if a.dataset != DATASET:
        raise SystemExit(f"REFUSED: registered on {DATASET}; got {a.dataset}")
    expect = None
    if a.expect:
        n, pt = a.expect.split(":")
        expect = (int(n), float(pt))
    else:
        expect = PUBLISHED.get(Path(a.pairs).as_posix())

    archive = Path(a.archive) if a.archive else default_archive()
    universe = load_pairs(Path(a.pairs))
    day_universe = load_pairs(Path(a.day_pairs))
    pre = {p.name[:10]: p for p in window_slices(archive, a.dataset)}
    got = day_slices(archive, a.dataset)
    full, _partial = complete(got)
    days = sorted(set(universe) & set(full) & set(pre))
    if a.limit:
        days = days[:a.limit]
        expect = None                    # a partial run cannot reproduce a full baseline
    if not days:
        raise SystemExit("no session has the universe, the pre-market slice and all "
                         "three full-day slices")

    tasks = []
    for k, day in enumerate(days):
        first = max(0, k - WARMUP_SESSIONS)
        warm = days[first:k + 1]
        tasks.append(([str(pre[d]) for d in warm],
                      [str(got[d][s]) for d in warm for *_r, s in BLOCKS],
                      day, universe[day], day_universe.get(day, [])))

    jobs = (os.cpu_count() or 1) if a.jobs == 0 else max(1, a.jobs)
    print(f"mc5_full_day: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
    t0 = time.time()
    got_res: dict[str, dict] = {}
    if jobs == 1:
        it = map(run_day, tasks)
    else:
        from concurrent.futures import ProcessPoolExecutor
        ex = ProcessPoolExecutor(max_workers=jobs)
        it = ex.map(run_day, tasks, chunksize=1)
    for k, (day, res, err) in enumerate(it, 1):
        if err:
            print(f"  ! {day}: {err}", flush=True)
        if res is not None:
            got_res[day] = res
        if k % 10 == 0:
            print(f"  ... {k:,} of {len(tasks):,}  ({time.time() - t0:.0f}s)", flush=True)
    if jobs != 1:
        ex.shutdown()

    books = {arm: [] for arm in ARMS}
    symdays = c_symdays = errors = 0
    error_days: list[str] = []
    run_days = sorted(got_res)
    for day in run_days:
        r = got_res[day]
        for arm in books:
            books[arm] += r["books"][arm]
        symdays += r["symdays"]
        c_symdays += r.get("c_symdays", 0)
        errors += r["errors"]
        error_days += r["error_days"]
    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")

    emit("\n".join(render(books, symdays, c_symdays, cut, len(run_days),
                          time.time() - t0, jobs, a, expect, errors, error_days)),
         a.out, header=f"common.mc5_full_day pairs={a.pairs} day_pairs={a.day_pairs} "
                       f"dataset={a.dataset} sessions={len(run_days)} "
                       f"symbol_days={symdays} qty={QTY}")
    write_csv(a.csv, books)
    Path(a.csv).with_name(Path(a.csv).stem + "_meta.json").write_text(
        json.dumps({"sessions": run_days, "symbol_days": symdays, "c_symbol_days": c_symdays,
                    "pairs": a.pairs, "day_pairs": a.day_pairs, "dataset": a.dataset,
                    "qty": QTY, "cut": cut, "timestamps": "ET", "registered": REGISTERED},
                   indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
