#!/usr/bin/env python3
r"""H-B1 -- skip the first entry of each symbol-day, on the point-in-time universe.

    python -m common.first_entry_skip --jobs 8

Registered in docs/research/REGISTERED_first_entry_skip.md before this file
existed. Four books from one `run_day` per session: MCL and MC5 as published
(`skip_entries=0`) and each with `skip_entries=1` -- the SIGNAL-ORDINAL form,
in which the first entry the engine would have taken is passed over and the
engine then runs free, so the skipped book can contain entries the baseline
never took. That form decides. The ACCOUNTING form -- the baseline book minus
each symbol-day's first trade, which is how the live table that motivated
this was built -- is printed beside it and read for nothing.

SAME TAPE, SAME PROCESS, SAME SETTINGS, as pullback_break: one run over the
point-in-time universe, the same warm-up frames, the same `first_seen` floor,
100 shares, the published configurations. Outcome per trade is the engine's
`net` (commission in) less a round-trip friction; $4.26 is measured and is the
one the verdict reads.

HALVES are cut ONCE, at the median session of the sessions run, and every
book is split on that date. PER SYMBOL-DAY divides by the symbol-days the run
covered, the same number for every book -- a rule that trades less must not
be allowed to shrink its own denominator.

The CSV this writes carries every timestamp column with `_et` in its name,
and `common/time_of_day.py` reads it for the block table registered in §4 of
the same document.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

from common.breadth import BOOT_MIN_P, RESAMPLES, SEED, cluster_bootstrap, pct, share_above_zero
from common.entry_shares import MEASURED_FRICTION, PUBLISHED_TRADES, QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
FRICTIONS = (("$1.00", 1.00), ("$4.26", 4.26), ("$8.92", 8.92))
PAIRS = "var/state/screen_pairs_pit.json"
REGISTERED = "docs/research/REGISTERED_first_entry_skip.md"
DROP = 3                     # §3 item 3: drop-top-3, on the level and on the delta
TOP = 10                     # §3: how many of the baseline's top-10 the rule removes
SKIP = 1                     # §1: the rule

# (book name, engine, skip_entries). Order is the order printed.
BOOKS = (("MCL", "mcl", 0), ("MCL-skip1", "mcl", SKIP),
         ("MC5", "mc5", 0), ("MC5-skip1", "mc5", SKIP))
PAIRED = (("MCL", "MCL-skip1"), ("MC5", "MC5-skip1"))


# --- the tape ---------------------------------------------------------------

def _et(ts) -> str:
    import pandas as pd
    return pd.Timestamp(ts).tz_convert(ET).strftime("%H:%M")


def trade_row(t, symbol: str, day: str, ordinal: int) -> dict:
    """One trade; `ordinal` is its 1-based entry order within the symbol-day
    IN THIS BOOK, which is not the same ordinal as in another book."""
    return {"symbol": symbol, "date": day, "ordinal": ordinal, "net": float(t.net),
            "entry_et": _et(t.entry_time), "entry_px": float(t.entry_price),
            "exit_et": _et(t.exit_time), "exit_px": float(t.exit_price),
            "reason": t.reason, "bars_held": int(t.bars_held)}


def run_day(args: tuple) -> tuple:
    """One session, all four books. Picklable."""
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
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

    res = {"books": {name: [] for name, _, _ in BOOKS},
           "symdays": 0, "errors": 0, "error_days": []}
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        # ALL OR NONE. A symbol-day that raises in any book is dropped from
        # every book, or the books stop covering the same opportunities.
        try:
            got = {}
            for name, eng, skip in BOOKS:
                mod, extra = engines[eng]
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, skip_entries=skip,
                                                 **extra)
        except Exception as e:                              # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{rec['symbol']} {day}: {type(e).__name__}: {e}")
            continue
        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [trade_row(t, rec["symbol"], day, k)
                                   for k, t in enumerate(trades, 1)]
    return day, res, ""


# --- arithmetic -------------------------------------------------------------

def net(rows, f: float) -> float:
    return sum(r["net"] - f for r in rows)


def per_trade(rows, f: float) -> float:
    return net(rows, f) / len(rows) if rows else 0.0


def halves(rows, cut: str) -> tuple[list, list]:
    return ([r for r in rows if r["date"] < cut], [r for r in rows if r["date"] >= cut])


def drop_top(rows, f: float, n: int = DROP) -> float:
    """Net after dropping the n best TRADES."""
    vals = sorted((r["net"] - f for r in rows), reverse=True)
    return sum(vals[n:])


def key(r: dict) -> tuple:
    return (r["symbol"], r["date"], r["entry_et"])


def by_symbol_day(rows, f: float) -> dict[tuple, float]:
    out: dict[tuple, float] = {}
    for r in rows:
        k = (r["symbol"], r["date"])
        out[k] = out.get(k, 0.0) + (r["net"] - f)
    return out


def deltas_by_symbol_day(base, skip, f: float) -> dict[tuple, float]:
    """skip net minus base net, per symbol-day, over the UNION of symbol-days
    either book traded. A day one book traded and the other did not is a
    delta of the traded book's whole net, signed accordingly."""
    b, s = by_symbol_day(base, f), by_symbol_day(skip, f)
    return {k: s.get(k, 0.0) - b.get(k, 0.0) for k in set(b) | set(s)}


def drop_top_delta(d: dict[tuple, float], n: int = DROP) -> float:
    """Delta after dropping the n symbol-days that helped the rule most."""
    vals = sorted(d.values(), reverse=True)
    return sum(vals[n:])


def delta_by_symbol(d: dict[tuple, float]) -> dict[str, list[float]]:
    """Per symbol, the LIST of its symbol-day deltas -- never pre-summed, or
    the symbol-cluster bootstrap becomes a symbol-total one (breadth.py)."""
    out: dict[str, list[float]] = {}
    for (sym, _day), v in d.items():
        out.setdefault(sym, []).append(v)
    return out


def accounting(base) -> tuple[list, list]:
    """The live table's construction: the baseline minus each symbol-day's
    first trade. Returns (kept, removed). Read for nothing (§1)."""
    kept, removed = [], []
    for r in base:
        (removed if r["ordinal"] == 1 else kept).append(r)
    return kept, removed


def top_absent(base, skip, f: float, n: int = TOP) -> tuple[int, list]:
    """How many of the baseline's n best trades at f are absent from the skip
    book, keyed (symbol, date, entry time). Under the signal-ordinal form a
    baseline trade can reappear at a shifted entry; that is not counted as
    present, and the caveat is printed beside the number."""
    top = sorted(base, key=lambda r: r["net"] - f, reverse=True)[:n]
    have = {key(r) for r in skip}
    gone = [r for r in top if key(r) not in have]
    return len(gone), gone


def new_entries(base, skip) -> int:
    """Skip-book entries the baseline does not contain. Zero across the whole
    run would mean the signal-ordinal form did not run (§5)."""
    have = {key(r) for r in base}
    return sum(1 for r in skip if key(r) not in have)


def verdict(base, skip, cut: str, symdays: int) -> tuple[str, str, dict]:
    """REGISTERED §3. Nothing here may change after a run. Returns
    (PASSES | NOTHING | REFUSED, why, the numbers it read)."""
    f = MEASURED_FRICTION
    n = {}
    n["d_per_trade"] = per_trade(skip, f) - per_trade(base, f)
    n["d_per_symday"] = (net(skip, f) - net(base, f)) / symdays if symdays else 0.0
    ba, bb = halves(base, cut)
    sa, sb = halves(skip, cut)
    n["early"] = (per_trade(sa, f) - per_trade(ba, f),
                  (net(sa, f) - net(ba, f)) / symdays if symdays else 0.0)
    n["late"] = (per_trade(sb, f) - per_trade(bb, f),
                 (net(sb, f) - net(bb, f)) / symdays if symdays else 0.0)
    n["drop_level"] = (drop_top(skip, f), drop_top(base, f))
    d = deltas_by_symbol_day(base, skip, f)
    n["drop_delta"] = drop_top_delta(d)
    boot = cluster_bootstrap(delta_by_symbol(d))
    n["boot_p"] = share_above_zero(boot["totals"]) if boot["totals"] else 0.0
    n["boot_lo"] = pct(boot["totals"], 0.025) if boot["totals"] else 0.0
    n["boot_hi"] = pct(boot["totals"], 0.975) if boot["totals"] else 0.0
    n["n_syms"] = boot["n_syms"]

    if not (ba and bb and sa and sb):
        return "NOTHING", "a half is empty in one of the books", n
    # Item 1 first, and a sign disagreement is a refusal, not a partial pass.
    if (n["d_per_trade"] > 0) != (n["d_per_symday"] > 0):
        return "REFUSED", (f"the two denominators disagree: per trade {n['d_per_trade']:+.2f}, "
                           f"per symbol-day {n['d_per_symday']:+.2f}"), n
    failed = []
    if not (n["d_per_trade"] > 0 and n["d_per_symday"] > 0):
        failed.append("1 (both denominators improve)")
    if not all(x > 0 for x in n["early"] + n["late"]):
        failed.append("2 (both halves, both denominators)")
    if not (n["drop_level"][0] > n["drop_level"][1] and n["drop_delta"] > 0):
        failed.append(f"3 (drop-top-{DROP} on the level and on the delta)")
    if not n["boot_p"] >= BOOT_MIN_P:
        failed.append(f"4 (cluster bootstrap on the delta, P={n['boot_p']:.3f} < {BOOT_MIN_P})")
    if failed:
        return "NOTHING", "fails " + "; ".join(failed), n
    return "PASSES", "all four readings, at $4.26", n


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


def verdict_block(bname: str, sname: str, base, skip, cut: str, symdays: int) -> list[str]:
    f = MEASURED_FRICTION
    tag, why, n = verdict(base, skip, cut, symdays)
    gone, gone_rows = top_absent(base, skip, f)
    fresh = new_entries(base, skip)
    L = [f"THE VERDICT: {sname} against {bname} (registered §3, $4.26)", "",
         f"  1. per trade {n['d_per_trade']:+.2f}   per symbol-day {n['d_per_symday']:+.2f}",
         f"  2. early half  per trade {n['early'][0]:+.2f}  per symbol-day {n['early'][1]:+.2f}"
         f"     late half  per trade {n['late'][0]:+.2f}  per symbol-day {n['late'][1]:+.2f}",
         f"  3. drop-top-{DROP} level  {sname} {money(n['drop_level'][0])}  "
         f"{bname} {money(n['drop_level'][1])}     drop-top-{DROP} delta {money(n['drop_delta'])}",
         f"  4. cluster bootstrap on the delta  P(total > 0) = {n['boot_p']:.3f}  "
         f"[{money(n['boot_lo'])}, {money(n['boot_hi'])}]  over {n['n_syms']:,} symbols  "
         f"(RESAMPLES {RESAMPLES}, SEED {SEED})",
         "",
         f"  {tag}: {why}", "",
         f"  cost: {gone} of {bname}'s top-{TOP} trades at $4.26 are absent from {sname}",
         ]
    for r in gone_rows:
        L.append(f"    {r['symbol']:<6} {r['date']}  {r['entry_et']} ET  {money(r['net'] - f):>10}")
    L += [f"  (a baseline trade re-entered at a shifted bar counts as absent; that is the",
          f"   signal-ordinal form, not a loss of the name)",
          f"  cascade: {fresh:,} {sname} entries the baseline does not contain "
          + ("-- ZERO MEANS THE SIGNAL-ORDINAL FORM DID NOT RUN (§5)" if fresh == 0 else ""),
          ""]
    return L


def accounting_block(bname: str, base, cut: str, symdays: int) -> list[str]:
    """§1: the live table's construction, printed and not read."""
    f = MEASURED_FRICTION
    kept, removed = accounting(base)
    losers = [r for r in removed if r["net"] - f <= 0]
    winners = [r for r in removed if r["net"] - f > 0]
    top = sorted(base, key=lambda r: r["net"] - f, reverse=True)[:TOP]
    top_removed = sum(1 for r in top if r["ordinal"] == 1)
    L = [f"THE ACCOUNTING FORM: {bname} minus each symbol-day's first trade -- NOT READ", "",
         f"  first trades removed  {len(removed):>6,}   net {money(net(removed, f)):>12}"
         f"   per trade {money(per_trade(removed, f)):>8}",
         f"    losses avoided      {len(losers):>6,}   {money(net(losers, f)):>12}",
         f"    winners lost        {len(winners):>6,}   {money(net(winners, f)):>12}",
         f"  later trades kept     {len(kept):>6,}   net {money(net(kept, f)):>12}"
         f"   per trade {money(per_trade(kept, f)):>8}"
         f"   per symbol-day {money(net(kept, f) / symdays if symdays else 0):>7}",
         f"  top-{TOP} of {bname} that were first trades: {top_removed} (exact under this form)",
         "",
         "  This is how the live 09-09..09-16 table was built. A later trade exists",
         "  only because the name kept signalling after the first, which is partly",
         "  conditioned on the move continuing; the gap between this block and the",
         "  verdict above is that circularity, measured.", ""]
    return L


def render(books: dict, symdays: int, errors: int, days: list[str], elapsed: float,
           jobs: int, error_days: list | None = None) -> list[str]:
    cut = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
    L = ["H-B1: SKIP THE FIRST ENTRY OF EACH SYMBOL-DAY", "",
         f"  registered  {REGISTERED}",
         f"  {len(days):,} sessions   {symdays:,} symbol-days   halves cut at {cut}",
         f"  {QTY} shares   commission in, friction per round trip   "
         f"elapsed {elapsed:.1f}s on {jobs} worker(s)", ""]
    if errors:
        L += [f"  {errors:,} symbol-day(s) raised and were dropped from EVERY book:"]
        L += [f"    {e}" for e in (error_days or [])[:20]]
        L += [""]

    mcl = books["MCL"]
    pub = PUBLISHED_TRADES.get("mcl")
    L += ["POPULATION CHECK", "", f"  MCL trades here     {len(mcl):,}"]
    if pub is not None:
        ok = len(mcl) == pub
        L.append(f"  published count     {pub:,}   " + ("matches" if ok else "*** DOES NOT MATCH ***"))
        if not ok:
            L += ["", "  A DIFFERENT BOOK FROM THE PUBLISHED ONE. The comparisons below are",
                  "  still like-for-like (same run), but do not quote MCL's line as the",
                  "  published figure until this reconciles."]
    L += [""]

    L += ["THE BOOKS", ""]
    for name, _eng, _skip in BOOKS:
        L += book_block(name, books[name], cut, symdays)

    for bname, sname in PAIRED:
        L += verdict_block(bname, sname, books[bname], books[sname], cut, symdays)
    for bname, _sname in PAIRED:
        L += accounting_block(bname, books[bname], cut, symdays)

    L += ["WHAT THIS IS NOT", "",
          "  NOT OUT OF SAMPLE. holdout.json has not been touched.",
          "  NOT THE LIVE TABLE. The 134 live trades motivated the registration and",
          "  are used for nothing here.",
          "  NOT A CAP MODEL. Each symbol-day runs alone; a skipped entry's freed slot",
          "  is not in these numbers (registration §6).",
          "  NOT A SEARCH. One rule, one skip, read on the signal-ordinal form; the",
          "  variant named in §1 was not run.", ""]
    return L


# --- cli --------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default="XNAS.BASIC")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/first_entry_skip.txt")
    p.add_argument("--csv", default="var/reports/first_entry_skip_trades.csv")
    return p


CSV_COLS = ["book", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
            "exit_px", "reason", "bars_held", "net"]


def write_csv(path: str, books: dict) -> None:
    import csv
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for name, _eng, _skip in BOOKS:
            for r in books[name]:
                w.writerow(dict(r, book=name))


def meta_path(csv_path: str) -> Path:
    return Path(csv_path).with_name(Path(csv_path).stem + "_meta.json")


def write_meta(csv_path: str, days: list[str], symdays: int, cut: str, a) -> None:
    """The run's frame, so a reader of the CSV (time_of_day) cuts halves on
    the SAME date and divides by the SAME symbol-days rather than deriving
    its own from the trades it happens to see."""
    m = {"sessions": days, "symbol_days": symdays, "cut": cut, "pairs": a.pairs,
         "dataset": a.dataset, "qty": QTY, "timestamps": "ET",
         "registered": REGISTERED}
    meta_path(csv_path).write_text(json.dumps(m, indent=1), encoding="utf-8")


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
    print(f"first_entry_skip: {len(tasks):,} session(s) on {jobs} worker(s)", flush=True)
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
    emit("\n".join(render(books, symdays, errors, run_days, time.time() - t0, jobs, error_days)),
         a.out, header=f"common.first_entry_skip pairs={a.pairs} dataset={a.dataset} "
                       f"sessions={len(run_days)} symbol_days={symdays} cut={cut} qty={QTY}")
    write_csv(a.csv, books)
    write_meta(a.csv, run_days, symdays, cut, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
