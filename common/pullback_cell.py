#!/usr/bin/env python3
r"""H-P2 -- the pullback cell: take the entry only when the name is at its
session high AND has not just run.

    python -m common.pullback_cell --jobs 8

Registered in docs/research/REGISTERED_pullback_cell.md (f77a59f), committed
before this file existed.

THE RULE, AS REGISTERED
-----------------------
At the close of the signal bar: `dist_from_high >= -D` AND `ret_5m <= C`, with
D = 5% and C = +3%, one pair for both books, fixed from the pre-flight grid's
printed terciles (-4.3% / -6.9% and +3.6% / +1.1%) and never from a P&L. A NaN
feature does NOT admit the entry: this is a positive selection, the opposite
of H-P1's refusal, so the absence of evidence is not the state asked for.

Delivered through the engines' `entry_gate` hook -- the DEPLOYED form, in
which a refused entry leaves the engine flat and later bars fire as the rule
says. The book-ordinal reading (the baseline's own entries classified by the
gate at their entry bar) is printed beside it and never scored.

REPORTED, NEVER SCORED (registration §1): each half of the conjunction alone
at the same thresholds, and the cell one step tighter (3%, +1%) and one step
looser (10%, +5%). The fence is in the registration; a better cell among them
is a direction for a new registration, never a promotion.

The five readings are `gate_study`'s, unchanged from REGISTERED_range_rank §3.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common import running_up as RU
from common.entry_shares import QTY
from common.first_entry_skip import FRICTIONS, per_trade
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
DATASET = "XNAS.ITCH"
REGISTERED = "docs/research/REGISTERED_pullback_cell.md"

D_NEAR = 0.05          # within 5% of the session high
C_CALM = 0.03          # five-minute return at most +3%
TIGHT = (0.03, 0.01)   # reported neighbour, one step in
LOOSE = (0.10, 0.05)   # reported neighbour, one step out
LIVE_SLOTS = 3         # the concurrency cap, for the trades-per-session line only

# (book name, engine, spec). spec None = the baseline.
#   ("cell", D, C)  the registered rule       ("dist", D)  the distance half alone
#   ("calm", C)     the calm half alone
BOOKS: tuple = tuple(
    b for eng in ("mcl", "mc5") for b in (
        (eng.upper(), eng, None),
        (f"{eng.upper()}-cell", eng, ("cell", D_NEAR, C_CALM)),
        (f"{eng.upper()}-dist", eng, ("dist", D_NEAR)),
        (f"{eng.upper()}-calm", eng, ("calm", C_CALM)),
        (f"{eng.upper()}-tight", eng, ("cell",) + TIGHT),
        (f"{eng.upper()}-loose", eng, ("cell",) + LOOSE),
    ))
PAIRED = (("MCL", "MCL-cell"), ("MC5", "MC5-cell"))
REPORTED = tuple((eng.upper(), f"{eng.upper()}-{k}") for eng in ("mcl", "mc5")
                 for k in ("dist", "calm", "tight", "loose"))
GATED = tuple(g for _, g in PAIRED + REPORTED)


# --- the gate -------------------------------------------------------------------

def gate_for(df: pd.DataFrame, spec) -> pd.Series:
    """A boolean Series on `df`'s 1-minute index: True where an entry is allowed.

    NaN NEVER admits (registration §1): `>=` and `<=` against NaN are False and
    stay False -- there is no `~(x < d)` inversion here, which is what made
    H-P1's gate admit on missing evidence.
    """
    kind = spec[0]
    if kind == "dist":
        return (RU.dist_series(df) >= -spec[1]).fillna(False).astype(bool)
    if kind == "calm":
        return (RU.ret_series(df, back=5) <= spec[1]).fillna(False).astype(bool)
    near = (RU.dist_series(df) >= -spec[1]).fillna(False)
    calm = (RU.ret_series(df, back=5) <= spec[2]).fillna(False)
    return (near & calm).astype(bool)


def nan_only(df: pd.DataFrame, spec) -> pd.Series:
    """True where the CELL would refuse for a missing feature alone -- i.e. the
    features that exist would have admitted. Printed, so a gate that binds on
    thin history is not mistaken for one binding on the state it names."""
    dist = RU.dist_series(df)
    r5 = RU.ret_series(df, back=5)
    missing = dist.isna() | r5.isna()
    near_ok = (dist >= -spec[1]) | dist.isna()
    calm_ok = (r5 <= spec[2]) | r5.isna()
    return (missing & near_ok & calm_ok).astype(bool)


def stamp_on(gate: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """The 1-minute gate carried onto whatever index the engine trades. For MC5
    that is the 5-minute label, forward-filled -- the H-B3 / H-P1 convention,
    up to five minutes conservative in the safe direction."""
    return gate.reindex(index, method="ffill").fillna(False).astype(bool)


# --- one session ----------------------------------------------------------------

def _blank() -> dict:
    return {"books": {name: [] for name, _, _ in BOOKS}, "symdays": 0, "errors": 0,
            "error_days": [],
            "refused": {g: [] for g in GATED},
            "binding": {g: [0, 0, Counter()] for g in GATED},
            "nan_only": {g: 0 for g in GATED},
            "onebar": {name: [0, 0] for name, _, _ in BOOKS},
            "sessions_with_trade": {name: set() for name, _, _ in BOOKS}}


def run_universe(frame: pd.DataFrame, day: str, universe: list[dict], engines: dict,
                 idx5_of=None) -> dict:
    """Every book on every symbol-day of one session. `engines[eng] = (module,
    extra)`; `idx5_of(df)` gives the 5-minute index for MC5 (defaulting to the
    real resampler). Pure enough to test with fake engines."""
    from common.pit_h0 import first_seen_time
    if idx5_of is None:
        from strategy.mc5 import mc5
        idx5_of = lambda df: mc5.to_5m(df).index                 # noqa: E731

    d = _date.fromisoformat(day)
    res = _blank()
    for rec in universe:
        if not rec.get("first_seen"):
            continue
        s = rec["symbol"]
        df = frame[frame["symbol"] == s]
        if df.empty:
            continue
        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)
        try:
            idx5 = idx5_of(df)
            gates = {}
            got = {}
            for name, eng, spec in BOOKS:
                mod, extra = engines[eng]
                gate = None
                if spec is not None:
                    g = gate_for(df, spec)
                    gates[name] = g
                    gate = stamp_on(g, idx5 if eng == "mc5" else df.index)
                got[name] = mod.backtest_session(df, d, ET, entry_shares=QTY,
                                                 not_before=floor, entry_gate=gate,
                                                 **extra)
        except Exception as e:                                  # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(f"{s} {day}: {type(e).__name__}: {e}")
            continue

        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [G.trade_row(t, s, day, k) for k, t in enumerate(trades, 1)]
            ob = res["onebar"][name]
            ob[0] += sum(1 for t in trades if getattr(t, "bars_held", 0) <= 1)
            ob[1] += len(trades)
            if trades:
                res["sessions_with_trade"][name].add(day)

        # The book-ordinal reading: each BASELINE entry, classified by the gate
        # at its own entry bar. Printed and never scored.
        for name, eng, spec in BOOKS:
            if spec is None:
                continue
            base = eng.upper()
            g = gates[name]
            nan_g = nan_only(df, spec) if spec[0] == "cell" else None
            b = res["binding"][name]
            for t in got[base]:
                ts = (pd.Timestamp(f"{day} {t.entry_time}", tz=ET)
                      if isinstance(t.entry_time, str) else pd.Timestamp(t.entry_time))
                allowed = bool(g.reindex([ts], method="ffill").fillna(False).iloc[0])
                b[0] += 1
                b[1] += 1
                b[2][int(allowed)] += 1
                if not allowed:
                    res["refused"][name].append(G.trade_row(t, s, day, 0))
                    if nan_g is not None and bool(
                            nan_g.reindex([ts], method="ffill").fillna(False).iloc[0]):
                        res["nan_only"][name] += 1
    return res


def run_day(args: tuple) -> tuple:
    """One session, every book. Module-level and picklable."""
    from common.dbn_io import read_dbn
    from common.pit_strategy import build_frame, engine

    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
    parts = []
    for pth in paths:
        try:
            f = read_dbn(Path(pth))
        except Exception as e:                                  # noqa: BLE001
            return day, None, f"unreadable ({type(e).__name__}: {e})"
        if not f.empty:
            parts.append((Path(pth).name[:10], f))
    if not parts or parts[-1][0] != day:
        return day, None, ""
    frame = build_frame(parts, day)
    return day, run_universe(frame, day, universe, engines), ""


# --- the blocks this study adds -------------------------------------------------

def _pt(rows, f: float) -> float:
    return per_trade(rows, f)


def mechanism_block(onebar: dict) -> list[str]:
    """§2: the cell was chosen for its one-bar rate (3.3% / 15.5% on the
    pre-flight). A deployed gate whose kept book does not read under 6% / 22%
    is not selecting that cell, whatever its P&L says."""
    bars = {"MCL": 0.06, "MC5": 0.22}
    L = ["THE MECHANISM, READ BACK AS A MEASUREMENT (§2)", "",
         "  The cell was chosen because its entries die on the next bar a quarter",
         "  as often. The kept book's one-bar share must read under 6% (MCL) /",
         "  22% (MC5) -- registration §2 -- or the deployed gate is not selecting",
         "  the cell the pre-flight measured, and the result says so first.", ""]
    for base in ("MCL", "MC5"):
        b = onebar.get(base, [0, 0])
        bs = 100.0 * b[0] / b[1] if b[1] else float("nan")
        L.append(f"  {base}")
        L.append(f"    {base:<11} {bs:5.1f}%   ({b[0]:,} of {b[1]:,})")
        for name, eng, spec in BOOKS:
            if spec is None or eng.upper() != base:
                continue
            o = onebar.get(name, [0, 0])
            if not o[1]:
                L.append(f"    {name:<11}    n/a   (no trades)")
                continue
            share = 100.0 * o[0] / o[1]
            tag = ""
            if name.endswith("-cell"):
                tag = "   <- HOLDS" if share <= 100 * bars[base] else "   <- FAILS the mechanism bar"
            L.append(f"    {name:<11} {share:5.1f}%   ({o[0]:,} of {o[1]:,})  {share - bs:+5.1f}pp{tag}")
        L.append("")
    return L


def marginal_block(books: dict) -> list[str]:
    """What each REFUSED trade was worth, and the kept book's ABSOLUTE per trade
    at all three frictions -- the number the ceiling is about."""
    L = ["WHAT EACH REFUSED TRADE WAS WORTH, AND WHAT THE KEPT BOOK IS WORTH", "",
         "  marginal = (tot(cell) - tot(base)) / (n(cell) - n(base)) at $4.26. A gate",
         "  refusing trades WORSE than the book's average is selecting; one refusing",
         "  trades better than it is abstaining into its own average. The kept",
         "  book's own per trade is printed at all three frictions.", ""]
    hdr = "  book          trades   removed   marginal   " + "  ".join(f"{lab:>9}" for lab, _ in FRICTIONS)
    for base in ("MCL", "MC5"):
        rows = books.get(base, [])
        n0, t0 = len(rows), sum(float(r["net"]) - G.MEASURED_FRICTION for r in rows)
        L += [f"  {base}", hdr]
        L.append(f"  {base:<12} {n0:>7,}         -          -   "
                 + "  ".join(f"{_pt(rows, fv):>+9.2f}" for _, fv in FRICTIONS))
        for name, eng, spec in BOOKS:
            if spec is None or eng.upper() != base:
                continue
            rs = books.get(name, [])
            n1 = len(rs)
            t1 = sum(float(r["net"]) - G.MEASURED_FRICTION for r in rs)
            marg = (t1 - t0) / (n1 - n0) if n1 != n0 else float("nan")
            L.append(f"  {name:<12} {n1:>7,}  {n1 - n0:>+8,}  {marg:>+9.2f}   "
                     + "  ".join(f"{_pt(rs, fv):>+9.2f}" if n1 else f"{'n/a':>9}"
                                 for _, fv in FRICTIONS))
        L.append("")
    return L


def deploy_block(books: dict, sessions_with_trade: dict, n_sessions: int,
                 nan_only: dict, binding: dict) -> list[str]:
    """§2: trades per session against the live cap, and the NaN-only refusals."""
    L = ["WHAT THE KEPT BOOK LOOKS LIKE TO A TRADER (§2)", "",
         f"  {n_sessions:,} sessions in the run; the live trader has {LIVE_SLOTS} slots.", "",
         "  book          trades   trades/session   sessions with a trade   NaN-only refusals"]
    for name, eng, spec in BOOKS:
        rows = books.get(name, [])
        sw = len(sessions_with_trade.get(name, ()))
        per = len(rows) / n_sessions if n_sessions else float("nan")
        nan_s = ""
        if spec is not None and spec[0] == "cell":
            b = binding.get(name, (0, 0, {}))
            refused = b[2].get(0, 0) if isinstance(b[2], dict) else 0
            k = nan_only.get(name, 0)
            nan_s = (f"{k:,} of {refused:,} refused ({100.0 * k / refused:.1f}%)"
                     if refused else "-")
        L.append(f"  {name:<12} {len(rows):>7,}   {per:>14.2f}   {sw:>10,} of {n_sessions:<8,}   {nan_s}")
    L.append("")
    return L


def parts_block(books: dict, cut: str, symdays: int) -> list[str]:
    """§3 P6: the conjunction against its parts, per trade at $4.26 -- reported."""
    L = ["THE CONJUNCTION AGAINST ITS PARTS (P6, reported)", "",
         "  per-trade delta against the baseline at $4.26, and random removal's p95",
         "  at each book's own removal count. If the cell does not beat the distance",
         "  half alone on MCL, the calm condition adds nothing (registration §3).", ""]
    for base in ("MCL", "MC5"):
        b = books[base]
        L.append(f"  {base}")
        for suffix in ("dist", "calm", "cell", "tight", "loose"):
            name = f"{base}-{suffix}"
            g = books[name]
            d = _pt(g, G.MEASURED_FRICTION) - _pt(b, G.MEASURED_FRICTION) if g else float("nan")
            a = G.abstention(b, max(0, len(b) - len(g)), symdays)
            p95 = a["per_trade"]["p95"] if a["valid"] else float("nan")
            L.append(f"    {name:<11} n {len(g):>6,}   per trade {d:>+7.2f}   random p95 {p95:>+6.2f}"
                     + ("   beats" if d == d and p95 == p95 and d > p95 else ""))
        L.append("")
    return L


# --- main -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--archive", default=None)
    p.add_argument("--dataset", default=DATASET)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--jobs", type=int, default=0)
    p.add_argument("--out", default="var/reports/pullback_cell.txt")
    p.add_argument("--csv", default="var/reports/pullback_cell_trades.csv")
    return p


def main(argv=None) -> int:
    from common.databento_fetch import default_archive
    a = build_parser().parse_args(argv)
    archive = Path(a.archive) if a.archive else default_archive()
    tasks, _ = G.build_tasks(a.pairs, archive, a.dataset, a.limit)
    jobs = G.jobs_from(a.jobs)
    got, elapsed = G.run_sessions(run_day, tasks, jobs, "pullback_cell")

    agg = _blank()
    symdays, errors, error_days = 0, 0, []
    run_days = sorted(got)                 # DAY ORDER: float sums must not move with --jobs
    for day in run_days:
        r = got[day]
        for name in agg["books"]:
            agg["books"][name] += r["books"][name]
            agg["onebar"][name][0] += r["onebar"][name][0]
            agg["onebar"][name][1] += r["onebar"][name][1]
            agg["sessions_with_trade"][name] |= r["sessions_with_trade"][name]
        for g in GATED:
            agg["refused"][g] += r["refused"][g]
            b, rb = agg["binding"][g], r["binding"][g]
            b[0] += rb[0]
            b[1] += rb[1]
            b[2].update(rb[2])
            agg["nan_only"][g] += r["nan_only"][g]
        symdays += r["symdays"]
        errors += r["errors"]
        error_days += r["error_days"]

    books = agg["books"]
    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    binding_t = {k: (v[0], v[1], dict(v[2])) for k, v in agg["binding"].items()}
    body = G.render(
        "H-P2: THE PULLBACK CELL -- AT THE SESSION HIGH AND NOT EXTENDED",
        REGISTERED, books, PAIRED, REPORTED, symdays, errors, run_days, elapsed, jobs,
        agg["refused"], binding_t, error_days,
        preamble=[f"  rule: dist_from_high >= -{D_NEAR:.0%} AND ret_5m <= +{C_CALM:.0%}; NaN never admits.",
                  f"  reported: each half alone; the cell at ({TIGHT[0]:.0%}, +{TIGHT[1]:.0%}) and "
                  f"({LOOSE[0]:.0%}, +{LOOSE[1]:.0%}). Never scored.", ""],
        universe=a.pairs, dataset=a.dataset,
        binding_kw={"what": "every baseline entry, classified by the gate at its entry bar (book-ordinal, not scored)",
                    "detail_label": "1 = admitted, 0 = refused"})
    body += (mechanism_block(agg["onebar"]) + marginal_block(books)
             + deploy_block(books, agg["sessions_with_trade"], len(run_days), agg["nan_only"], binding_t)
             + parts_block(books, cut, symdays))
    emit("\n".join(body), a.out,
         header=f"common.pullback_cell pairs={a.pairs} dataset={a.dataset} sessions={len(run_days)} "
                f"symbol_days={symdays} cut={cut} qty={QTY} D={D_NEAR} C={C_CALM} registered={REGISTERED}")
    G.write_csv(a.csv, books)
    G.write_meta(a.csv, run_days, symdays, cut,
                 {"pairs": a.pairs, "dataset": a.dataset, "registered": REGISTERED,
                  "D": D_NEAR, "C": C_CALM, "tight": list(TIGHT), "loose": list(LOOSE)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
