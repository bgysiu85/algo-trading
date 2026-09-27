#!/usr/bin/env python3
r"""Time-cap study: max hold time, with and without the slot cap (W03-0004).

    python -m common.time_cap_study --jobs 8
    python -m common.time_cap_study --limit 10 --jobs 4      # dry run

Registered in docs/research/REGISTERED_time_cap.md before this file existed.
Read that first: the grid, the primary cell, the two scopes, the tie rules and
the decision rule are all fixed there, not here.

WHAT RUNS
---------
The W03-0002 book: point-in-time universe `var/state/screen_pairs_pit.json`,
XNAS.BASIC one-minute bars, MCL (LIVE config) and MC5 (defaults) through
`common.pit_strategy.engine`, entry floor = `first_seen`, 100 shares,
tiered commission, $4.26 friction per round trip.

For every time cap in GRID_MIN (minutes; MCL N bars, MC5 N/5 bars), five arms:

    free          no slot cap -- every symbol-day alone (ARM 1)
    strategy      3 slots per book, MCL and MC5 each (ARM 2, live since 09-23)
    account       3 slots shared by both books      (ARM 2, live until 09-22)
    strategy-rev  as strategy, simultaneous entries in REVERSE universe order
    account-rev   as account,  simultaneous entries in REVERSE universe order

The universe file lists each date's names in `first_seen` order, so the
forward order is "earliest on the watchlist first". MCL always goes before
MC5 at the same moment (the --strategy MCL+MC5 order in the trader).

The slot walk is common/slot_book.py; see its docstring for exactly how a
refused entry is handled (the leg re-runs with that one bar blocked).

OUTPUTS
-------
    var/reports/time_cap.txt              the report (also copied to Claude outputs)
    var/reports/time_cap_trades.csv       every trade, every arm, every cell
    var/reports/time_cap_refusals.csv     every refused entry
    var/reports/time_cap_meta.json        sessions, split date, settings
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import date as _date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import slot_book as SB
from common.entry_shares import MEASURED_FRICTION, QTY
from common.slot_book import Leg

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
DATASET = "XNAS.BASIC"
REGISTERED = "docs/research/REGISTERED_time_cap.md"

GRID_MIN = (None, 5, 10, 15, 30, 60, 120)     # REGISTERED §2
PRIMARY = 30                                  # REGISTERED §2
EDGES = (5, 120)                              # REGISTERED §4.5 boundary check
SLOTS = 3
BOOKS = ("MCL", "MC5")
# name -> (slot cap, scope, reverse tie order)
ARMS = {
    "free": (None, "strategy", False),
    "strategy": (SLOTS, "strategy", False),
    "account": (SLOTS, "account", False),
    "strategy-rev": (SLOTS, "strategy", True),
    "account-rev": (SLOTS, "account", True),
}
ARM2_LIVE = "strategy"
BOOT_N = 5000
BOOT_SEED = 20260927
DROP_DAYS = 3
LIVE_REFUSALS = "09-21: 35 · 09-22: 5 (shared 3)   09-23: 2 · 09-24: 0 · 09-25: 0 (3 per strategy)"
OUT_TXT_COPY = "Claude outputs/w03_0004_time_cap_raw_{stamp}.txt"

TRADE_COLS = ["arm", "cap", "book", "symbol", "date", "entry_et", "exit_et",
              "entry_px", "exit_px", "reason", "bars_held", "hold_min",
              "gross", "commission", "net"]
REFUSAL_COLS = ["arm", "cap", "book", "symbol", "date", "bar_et", "would_net",
                "held_by"]


def cap_label(cap) -> str:
    return "none" if cap is None else str(cap)


def hold_bars(book: str, cap_min: int | None) -> int | None:
    """Minutes -> the book's own bars. Every grid value divides by 5."""
    if cap_min is None:
        return None
    L = SB.BAR_MINUTES[book]
    if cap_min % L:
        raise ValueError(f"{cap_min} min is not a whole number of {book} bars")
    return cap_min // L


def _et(ts) -> str:
    return pd.Timestamp(ts).tz_convert(ET).strftime("%H:%M")


def trade_row(arm, cap, leg: Leg, day: str, t) -> dict:
    hold = (pd.Timestamp(t.exit_time) - pd.Timestamp(t.entry_time)).total_seconds() / 60
    return {"arm": arm, "cap": cap_label(cap), "book": leg.book,
            "symbol": leg.symbol, "date": day,
            "entry_et": _et(t.entry_time), "exit_et": _et(t.exit_time),
            "entry_px": float(t.entry_price), "exit_px": float(t.exit_price),
            "reason": t.reason, "bars_held": int(t.bars_held),
            "hold_min": round(hold, 1), "gross": float(t.gross),
            "commission": float(t.commission), "net": float(t.net)}


# --- one date: pure, testable ---------------------------------------------------

def bar_index(book: str, mod, df: pd.DataFrame) -> pd.Index:
    """The index the book's engine trades on -- where an entry_gate must live."""
    if book == "MC5":
        return (df if mod._looks_5m(df) else mod.to_5m(df)).index
    return df.index


def run_symbols(day: str, frames: list[tuple[str, pd.DataFrame, object]],
                engines: dict, grid=GRID_MIN, arms=ARMS) -> dict:
    """Every arm and cell for one date.

    `frames`: (symbol, one-minute frame with warm-up, entry floor) in universe
    order. `engines`: {"MCL": (module, kwargs), "MC5": (module, kwargs)}.

    ALL OR NONE, as in entry_gates: a symbol whose engine raises in ANY cell is
    dropped from EVERY arm and cell, so every comparison is over the same
    symbol-days. Returns {"trades": [...], "refusals": [...], "symdays": n,
    "errors": [...]}.
    """
    d = _date.fromisoformat(day)
    res = {"trades": [], "refusals": [], "symdays": 0, "errors": []}
    idx: dict[Leg, pd.Index] = {}
    info: dict[str, tuple] = {}
    caches: dict = {cap: {} for cap in grid}

    def runner(cap):
        def run_leg(leg: Leg, blocked: frozenset):
            mod, extra = engines[leg.book]
            df, floor = info[leg.symbol]
            return mod.backtest_session(
                df, d, ET, entry_shares=QTY, not_before=floor,
                entry_gate=SB.gate_for(idx[leg], blocked),
                max_hold_bars=hold_bars(leg.book, cap), **extra)
        return run_leg

    kept = []
    for sym, df, floor in frames:
        info[sym] = (df, floor)
        try:
            pre = {}
            for book in BOOKS:
                leg = Leg(book, sym)
                idx[leg] = bar_index(book, engines[book][0], df)
                if idx[leg].has_duplicates:
                    # The engines reindex an entry_gate onto this index and
                    # raise on duplicate labels -- but only once a bar is
                    # BLOCKED, i.e. mid-walk. Refuse the symbol up front so it
                    # is dropped from every arm, not half of them.
                    raise ValueError("duplicate bar labels (entry_gate cannot be applied)")
                for cap in grid:
                    pre[(cap, leg)] = runner(cap)(leg, frozenset())
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"{sym} {day}: {type(e).__name__}: {e}")
            continue
        for (cap, leg), tr in pre.items():
            caches[cap][(leg, frozenset())] = tr
        kept.append(sym)
    res["symdays"] = len(kept)

    for arm, (slots, scope, rev) in arms.items():
        syms = list(reversed(kept)) if rev else kept
        order = [Leg(b, s) for b in BOOKS for s in syms]
        for cap in grid:
            trades, refusals = SB.walk(order, runner(cap), slots, scope,
                                       cache=caches[cap])
            for leg in order:
                res["trades"] += [trade_row(arm, cap, leg, day, t)
                                  for t in trades[leg]]
            res["refusals"] += [{
                "arm": arm, "cap": cap_label(cap), "book": r.leg.book,
                "symbol": r.leg.symbol, "date": day, "bar_et": _et(r.bar),
                "would_net": float(r.trade.net),
                "held_by": " ".join(f"{b}:{s}" for b, s in r.open_legs)}
                for r in refusals]
    return res


def run_day(task: tuple) -> tuple:
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe = task
    engines = {"MCL": engine("mcl"), "MC5": engine("mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:  # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    frames = []
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue
        frames.append((rec["symbol"], df.sort_index(kind="mergesort"),
                       first_seen_time(rec)))
    try:
        return day, run_symbols(day, frames, engines), ""
    except Exception as e:  # noqa: BLE001
        # A walk that fails part-way would leave arms scored over different
        # symbol-days. Drop the whole date from every arm and say so.
        return day, None, f"walk failed ({type(e).__name__}: {e})"


# --- scoring ----------------------------------------------------------------------

def score(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n": 0, "gross": 0.0, "comm": 0.0, "fric": 0.0, "net": 0.0,
                "wins": 0, "losses": 0, "per": 0.0}
    real = df["net"] - MEASURED_FRICTION
    return {"n": len(df), "gross": float(df["gross"].sum()),
            "comm": float(df["commission"].sum()),
            "fric": MEASURED_FRICTION * len(df), "net": float(real.sum()),
            "wins": int((real > 0).sum()), "losses": int((real <= 0).sum()),
            "per": float(real.mean())}


def day_net(df: pd.DataFrame, days: list[str]) -> pd.Series:
    s = (df["net"] - MEASURED_FRICTION).groupby(df["date"]).sum()
    return s.reindex(days, fill_value=0.0)


def controls(cell: pd.DataFrame, base: pd.DataFrame, days: list[str],
             split: str) -> dict:
    """The change (cell minus base) with the registered controls."""
    delta = day_net(cell, days) - day_net(base, days)
    early = float(delta[delta.index < split].sum())
    late = float(delta[delta.index >= split].sum())
    top = sorted((v for v in delta if v > 0), reverse=True)[:DROP_DAYS]
    # Day-level bootstrap: resample whole DATES, because trades on one date
    # share a tape and a slot book and are not independent of each other.
    vals = delta.to_numpy(dtype=float)
    n = len(vals)
    p_pos = 0.0
    if n:
        rng = np.random.default_rng(BOOT_SEED)
        sums = vals[rng.integers(0, n, size=(BOOT_N, n))].sum(axis=1)
        p_pos = float((sums > 0).mean())
    return {"total": float(delta.sum()), "early": early, "late": late,
            "dropped": float(delta.sum()) - sum(top), "p_pos": p_pos}


def paired(cell: pd.DataFrame, base: pd.DataFrame) -> dict:
    k = ["book", "symbol", "date", "entry_et"]
    m = base.merge(cell, on=k, suffixes=("_b", "_c"))
    d = m["net_c"] - m["net_b"]
    return {"n": len(m), "changed": int((d.abs() > 1e-9).sum()),
            "better": int((d > 1e-9).sum()), "worse": int((d < -1e-9).sum()),
            "total": float(d.sum()), "frame": m.assign(delta=d)}


def money(x: float, w: int = 11) -> str:
    """Dollars, negatives in brackets (Ben's standing rule)."""
    if abs(x) < 0.005:
        x = 0.0                     # no "(0.00)" from float noise
    s = f"{abs(x):,.2f}"
    return f"{('(' + s + ')') if x < 0 else s:>{w}}"


def verdict(ch: dict, best_cap, slot_value: float) -> tuple[bool, list[str]]:
    checks = [
        ("change above $0", ch["total"] > 0),
        ("above $0 in both halves", ch["early"] > 0 and ch["late"] > 0),
        (f"above $0 after dropping the {DROP_DAYS} best days", ch["dropped"] > 0),
        ("bootstrap P(change > 0) >= 0.95", ch["p_pos"] >= 0.95),
        ("best cell not at a grid edge", best_cap not in EDGES),
    ]
    ok = all(v for _, v in checks)
    lines = [f"    [{'PASS' if v else 'FAIL'}] {name}" for name, v in checks]
    if ok:
        lines.append("    -> PASSES. " + ("Argue it as a PORTFOLIO rule (slot value "
                     f"{money(slot_value, 0)} > 0)." if slot_value > 0 else
                     "Slot value is not positive: it is an EXIT rule and must also "
                     "pass the exit-mechanics concentration gates."))
    else:
        lines.append("    -> FAILS the registered rule. The time-cap lever closes; "
                     "further cap work moves to RANKING (PROGRAM_INDEX §7 item 4).")
    return ok, lines


def report(trades: pd.DataFrame, refusals: pd.DataFrame, days: list[str],
           symdays: int, errors: list[str], elapsed: float, jobs: int) -> list[str]:
    split = days[len(days) // 2] if days else ""
    L = ["TIME-CAP STUDY (W03-0004) -- with and without the slot cap (W03-0003)", "",
         f"  registered  {REGISTERED}",
         f"  universe    {PAIRS}   bars {DATASET} ohlcv-1m",
         f"  {len(days)} sessions   {symdays:,} symbol-days   halves cut at {split}",
         f"  {QTY} shares, tiered commission, ${MEASURED_FRICTION} friction per round trip",
         f"  elapsed {elapsed:.0f}s on {jobs} worker(s)",
         "  money: dollars, negatives in (brackets); net is after commission AND friction", ""]
    if errors:
        L.append(f"  {len(errors)} symbol-day(s)/date(s) dropped from EVERY arm:")
        L += [f"    {e}" for e in errors[:15]]
        if len(errors) > 15:
            L.append(f"    ... and {len(errors) - 15} more")
        L.append("")

    def cell(arm, cap):
        return trades[(trades.arm == arm) & (trades.cap == cap_label(cap))]

    def refs(arm, cap):
        if refusals.empty:
            return refusals
        return refusals[(refusals.arm == arm) & (refusals.cap == cap_label(cap))]

    # 1. the slot cap on its own
    L += ["=" * 88, "1. THE SLOT CAP ON ITS OWN (no time cap) -- W03-0003", "=" * 88]
    free0 = score(cell("free", None))
    L.append(f"  {'arm':<14}{'trades':>8}{'net':>13}{'vs free':>13}"
             f"{'refused':>9}{'days hit':>10}{'max/day':>9}")
    L.append(f"  {'free':<14}{free0['n']:>8,}{money(free0['net'], 13)}{'':>13}{'':>9}{'':>10}{'':>9}")
    for arm in ("strategy", "account", "strategy-rev", "account-rev"):
        s = score(cell(arm, None))
        r = refs(arm, None)
        per_day = r.groupby("date").size() if len(r) else pd.Series(dtype=int)
        L.append(f"  {arm:<14}{s['n']:>8,}{money(s['net'], 13)}"
                 f"{money(s['net'] - free0['net'], 13)}{len(r):>9,}"
                 f"{per_day.size:>10,}{(per_day.max() if len(per_day) else 0):>9}")
    L += ["", f"  Live SKIPPED_CONCURRENCY_CAP counts for comparison: {LIVE_REFUSALS}",
          "  A refusal is one signal bar turned away; a persistent signal is refused on",
          "  every bar until a slot frees, as live logs it.", ""]
    for arm in ("strategy", "account"):
        r = refs(arm, None)
        if len(r):
            per_day = r.groupby("date").size()
            L.append(f"  {arm}: refusals per affected day  median {per_day.median():.0f}"
                     f"  p90 {per_day.quantile(.9):.0f}   by book "
                     + ", ".join(f"{b} {int((r.book == b).sum()):,}" for b in BOOKS))
    L.append("")

    # 2-4. the grid, per arm
    changes = {}
    for arm, title in (("free", "2. ARM 1 -- NO SLOT CAP (each symbol-day alone)"),
                       ("strategy", "3. ARM 2 -- 3 SLOTS PER STRATEGY (live since 09-23)"),
                       ("account", "4. ARM 2 -- 3 SLOTS SHARED (live until 09-22)")):
        L += ["=" * 88, title, "=" * 88,
              f"  {'cap':>6}{'trades':>8}{'gross':>12}{'commiss.':>11}{'friction':>10}"
              f"{'net':>12}{'W/L':>12}{'change':>12}"
              + (f"{'slot val.':>11}{'refused':>9}" if arm != "free" else "")]
        base = score(cell(arm, None))
        for cap in GRID_MIN:
            s = score(cell(arm, cap))
            ch = s["net"] - base["net"]
            changes[(arm, cap)] = ch
            row = (f"  {cap_label(cap):>6}{s['n']:>8,}{money(s['gross'], 12)}"
                   f"{money(-s['comm'], 11)}{money(-s['fric'], 10)}{money(s['net'], 12)}"
                   f"{s['wins']:>6,}/{s['losses']:<5,}{money(ch, 12)}")
            if arm != "free":
                sv = ch - changes[("free", cap)]
                row += f"{money(sv, 11)}{len(refs(arm, cap)):>9,}"
            L.append(row + ("   <- primary" if cap == PRIMARY else ""))
        L.append("  by book, change vs no time cap:")
        for b in BOOKS:
            bb = score(cell(arm, None)[cell(arm, None).book == b])
            L.append(f"    {b}: " + "  ".join(
                f"{cap_label(c)}:{money(score(cell(arm, c)[cell(arm, c).book == b])['net'] - bb['net'], 0)}"
                for c in GRID_MIN if c is not None))
        L.append("")
    L.append("  change    = this cell's net minus the same arm with no time cap")
    L.append("  slot val. = ARM 2 change minus ARM 1 change at the same cap (REGISTERED §1)")
    L.append("")

    # 5. exits by reason at the primary cell
    L += ["=" * 88, f"5. EXITS BY REASON, {PRIMARY}-minute cap vs none", "=" * 88]
    for arm in ("free", ARM2_LIVE):
        for cap in (None, PRIMARY):
            c = cell(arm, cap)
            g = c.assign(real=c.net - MEASURED_FRICTION).groupby("reason")["real"].agg(["size", "sum"])
            L.append(f"  {arm} / cap {cap_label(cap)}: " + "   ".join(
                f"{k} {int(v['size']):,} {money(v['sum'], 0)}" for k, v in g.iterrows()))
    L.append("")

    # 6. paired
    L += ["=" * 88, "6. PAIRED (ARM 1): the same entry under both rules", "=" * 88]
    pr = paired(cell("free", PRIMARY), cell("free", None))
    L.append(f"  {PRIMARY} min: {pr['n']:,} entries in both; the cap changed {pr['changed']:,} "
             f"({pr['better']:,} better, {pr['worse']:,} worse); total {money(pr['total'], 0)}")
    for cap in GRID_MIN:
        if cap in (None, PRIMARY):
            continue
        p = paired(cell("free", cap), cell("free", None))
        L.append(f"  {cap:>3} min: changed {p['changed']:,} ({p['better']:,} better / "
                 f"{p['worse']:,} worse), total {money(p['total'], 0)}")
    L.append("")

    # 7. controls
    L += ["=" * 88, f"7. CONTROLS ON THE {PRIMARY}-MINUTE CHANGE", "=" * 88,
          f"  {'arm':<14}{'change':>12}{'early':>12}{'late':>12}{'drop 3 days':>13}{'P(>0)':>8}"]
    ctl = {}
    for arm in ARMS:
        ch = controls(cell(arm, PRIMARY), cell(arm, None), days, split)
        ctl[arm] = ch
        L.append(f"  {arm:<14}{money(ch['total'], 12)}{money(ch['early'], 12)}"
                 f"{money(ch['late'], 12)}{money(ch['dropped'], 13)}{ch['p_pos']:>8.3f}")
    L.append("")

    # 8. tie order
    L += ["=" * 88, "8. TIE-ORDER SENSITIVITY (forward vs reverse universe order)", "=" * 88]
    for scope in ("strategy", "account"):
        for cap in (None, PRIMARY):
            a, b = score(cell(scope, cap)), score(cell(scope + "-rev", cap))
            L.append(f"  {scope:<9} cap {cap_label(cap):>4}: net {money(a['net'], 0)} vs "
                     f"{money(b['net'], 0)}  (difference {money(b['net'] - a['net'], 0)})")
    L.append("")

    # 9. sample trades
    L += ["=" * 88, f"9. SAMPLE TRADES the {PRIMARY}-minute cap changed (ARM 1)", "=" * 88]
    m = pr["frame"]
    m = m[m["delta"].abs() > 1e-9]
    hdr = (f"  {'book':<5}{'symbol':<7}{'date':<11}{'in':>6}{'px in':>8}   "
           f"{'no cap: out':<12}{'net':>10}   {'capped: out':<12}{'net':>10}{'change':>11}")
    for label, part in (("helped most", m[m.delta > 0].nlargest(5, "delta")),
                        ("hurt most", m[m.delta < 0].nsmallest(5, "delta"))):
        L.append(f"  {label} ({QTY} shares each, net after costs):")
        if part.empty:
            L.append("    none")
            continue
        L.append(hdr)
        for _, r in part.iterrows():
            L.append(f"  {r.book:<5}{r.symbol:<7}{r.date:<11}{r.entry_et:>6}{r.entry_px_b:>8.2f}   "
                     f"{r.exit_et_b:>5} {r.exit_px_b:>6.2f}{money(r.net_b - MEASURED_FRICTION, 10)}   "
                     f"{r.exit_et_c:>5} {r.exit_px_c:>6.2f}{money(r.net_c - MEASURED_FRICTION, 10)}"
                     f"{money(r.delta, 11)}")
    L.append("")

    # 10. verdict
    L += ["=" * 88, "10. VERDICT (REGISTERED §4, primary cell, live scope = 3 per strategy)", "=" * 88]
    grid = [c for c in GRID_MIN if c is not None]
    best = max(grid, key=lambda c: changes[(ARM2_LIVE, c)])
    sv = changes[(ARM2_LIVE, PRIMARY)] - changes[("free", PRIMARY)]
    L.append(f"  best cell under {ARM2_LIVE}: {best} min (change {money(changes[(ARM2_LIVE, best)], 0)})")
    L.append(f"  slot value at {PRIMARY} min: {money(sv, 0)}")
    _, vl = verdict(ctl[ARM2_LIVE], best, sv)
    L += vl
    L.append("")
    return L


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jobs", type=int, default=8, help="parallel workers (0 = all cores)")
    p.add_argument("--limit", type=int, default=None, help="first N sessions only (dry run)")
    p.add_argument("--out", default="var/reports/time_cap.txt")
    a = p.parse_args(argv)

    from common import gate_study as G
    from common.databento_fetch import default_archive
    archive = default_archive()
    tasks, _ = G.build_tasks(PAIRS, archive, DATASET, a.limit)
    jobs = G.jobs_from(a.jobs)
    print(f"Time-cap study: {len(tasks)} sessions, {jobs} workers, "
          f"grid {[cap_label(c) for c in GRID_MIN]} min, arms {list(ARMS)}", flush=True)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "Time cap")

    days = sorted(got)
    trades, refusals, errors, symdays = [], [], [], 0
    for day in days:
        r = got[day]
        trades += r["trades"]
        refusals += r["refusals"]
        errors += r["errors"]
        symdays += r["symdays"]
    out = Path(a.out)
    write_csv(out.with_name("time_cap_trades.csv"), trades, TRADE_COLS)
    write_csv(out.with_name("time_cap_refusals.csv"), refusals, REFUSAL_COLS)
    tdf = pd.DataFrame(trades, columns=TRADE_COLS)
    rdf = pd.DataFrame(refusals, columns=REFUSAL_COLS)
    lines = report(tdf, rdf, days, symdays, errors, elapsed, jobs)
    stamp = datetime.now().strftime("%Y%m%d")
    text = "\n".join(lines) + "\n"
    out.write_text(text, encoding="utf-8")
    copy = Path(OUT_TXT_COPY.format(stamp=stamp))
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, copy)
    out.with_name("time_cap_meta.json").write_text(json.dumps({
        "registered": REGISTERED, "sessions": days, "symbol_days": symdays,
        "split": days[len(days) // 2] if days else "", "grid_min": list(map(cap_label, GRID_MIN)),
        "primary": PRIMARY, "slots": SLOTS, "arms": list(ARMS), "qty": QTY,
        "friction": MEASURED_FRICTION, "limit": a.limit, "errors": errors,
        "trades": len(trades), "refusals": len(refusals)}, indent=1), encoding="utf-8")
    print(text)
    print(f"  report   {out}\n  copy     {copy}\n  trades   {out.with_name('time_cap_trades.csv')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
