#!/usr/bin/env python3
r"""W05-0019 -- Running Up universe, Tier-1 SCORED: drop whole symbol-days.

    python -m common.running_up_universe_gate

Registered in docs/research/REGISTERED_running_up_universe_scored.md before
this file existed. W05-0006's preflight measured coverage and lead time only
(no P&L); this scores the mask it proposed: a traded symbol-day is kept only
if it had a pre-entry bar (`pre_bars > 0`) and its pre-entry PEAK of `ret_5m`
cleared the cut. A symbol-day failing either loses every trade in it, in
BOTH books.

NO ENGINE RE-RUN. The mask never changes which bar an entry fires on -- it
only removes whole symbol-days -- so every "gated" trade is a bit-identical
row from the already-published book (`var/reports/session_scenarios_trades.csv`).
Because the mask only SUBTRACTS, `gated` is always a subset of `base`: the
"cascade" line `gate_study.verdict_block` prints is 0 for every cut here, by
construction, and that is expected -- it does not mean the mask failed to
run, the way a zero cascade would for `first_entry_skip`'s re-simulated form.

This module reads two files W05-0006 already produced
(`session_scenarios_trades.csv`, `running_up_universe_features.csv`) and
applies `gate_study`'s five criteria (`REGISTERED_range_rank.md` sec 3) to
each `(book, cut)` pair, for all nine cuts
`REGISTERED_running_up_universe_scored.md` sec 2 fixed before this file
existed.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from common import gate_study as G
from common.report_io import emit

TRADES_CSV = "var/reports/session_scenarios_trades.csv"
FEATURES_CSV = "var/reports/running_up_universe_features.csv"
PAIRS = "var/state/screen_pairs_pit_itch_v2.json"
REGISTERED = "docs/research/REGISTERED_running_up_universe_scored.md"
BOOKS_BASE = ("MCL", "MC5")

# REGISTERED_running_up_universe_scored.md sec 2: the preflight's own nine
# printed deciles of peak_ret5m (var/reports/running_up_universe_preflight.txt),
# fixed before this file existed. Not re-derived here, on purpose -- a
# recomputed decile would move quietly if the underlying tape ever changed.
CUTS: tuple[float, ...] = (0.045, 0.067, 0.089, 0.117, 0.148, 0.188, 0.243, 0.336, 0.542)


def _name(base: str, cut: float) -> str:
    return f"{base}-uc{int(round(cut * 1000)):03d}"


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# --- loading ------------------------------------------------------------

def load_trades(path: str) -> dict[str, list[dict]]:
    """book -> rows, restricted to the two published books this study reads."""
    out: dict[str, list[dict]] = {b: [] for b in BOOKS_BASE}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["book"] in out:
                out[r["book"]].append({**r, "net": _f(r["net"])})
    return out


def load_features(path: str) -> dict[tuple[str, str], dict]:
    """(symbol, date) -> {pre_bars, peak_ret5m} -- every traded symbol-day,
    read from W05-0006's own preflight output, restated nowhere else."""
    out: dict[tuple[str, str], dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[(r["symbol"], r["date"])] = {
                "pre_bars": int(r["pre_bars"]), "peak_ret5m": _f(r["peak_ret5m"])}
    return out


# --- the mask -------------------------------------------------------------

def keep_set(features: dict[tuple[str, str], dict], cut: float) -> set[tuple[str, str]]:
    """Symbol-days the mask KEEPS at this cut: a pre-entry bar existed and the
    pre-entry peak of ret_5m cleared it. `peak_ret5m` is NaN exactly when
    `pre_bars == 0` (the preflight's own convention), so `NaN >= cut` already
    excludes a zero-pre-bar day without a separate branch -- but `pre_bars > 0`
    is still checked explicitly, so a future features file that fills NaN
    differently cannot silently admit a bought-on-sight day."""
    return {k for k, v in features.items() if v["pre_bars"] > 0 and v["peak_ret5m"] >= cut}


def gate_book(rows: list[dict], keep: set[tuple[str, str]]) -> tuple[list[dict], list[dict]]:
    """(gated, refused). `refused` is exact: baseline rows whose symbol-day
    the mask dropped -- there is no bar-level ambiguity to approximate,
    unlike a per-entry gate's `refused_block`."""
    gated, refused = [], []
    for r in rows:
        (gated if (r["symbol"], r["date"]) in keep else refused).append(r)
    return gated, refused


def could_bind(rows: list[dict], features: dict[tuple[str, str], dict]) -> tuple[int, int, dict]:
    """The ceiling every cut in the sweep is bounded by, regardless of cut:
    how many of this book's baseline trades sit on a symbol-day the mask
    could EVER keep (pre_bars > 0). A trade on a symbol-day missing from
    `features` entirely is treated as pre_bars == 0 (could never be kept)."""
    total = len(rows)
    detail = {"0 pre-entry bars": 0, ">0 pre-entry bars": 0}
    could = 0
    for r in rows:
        f = features.get((r["symbol"], r["date"]), {"pre_bars": 0})
        if f["pre_bars"] > 0:
            could += 1
            detail[">0 pre-entry bars"] += 1
        else:
            detail["0 pre-entry bars"] += 1
    return could, total, detail


def symdays_of(rows: list[dict]) -> int:
    return len({(r["symbol"], r["date"]) for r in rows})


def days_of(rows: list[dict]) -> list[str]:
    return sorted({r["date"] for r in rows})


# --- report ---------------------------------------------------------------

def render(base_books: dict[str, list[dict]], features: dict, universe_symdays: int) -> list[str]:
    L = ["W05-0019: RUNNING UP UNIVERSE, TIER-1 SCORED -- DROP WHOLE SYMBOL-DAYS", "",
         f"  registered  {REGISTERED}",
         f"  trades      {TRADES_CSV}",
         f"  features    {FEATURES_CSV}",
         f"  universe    {PAIRS}   per-symbol-day denominator {universe_symdays:,} "
         f"(scanned PIT universe -- sec 5 caveat, not a fresh engine recount)",
         "  cascade is 0 below FOR EVERY CUT, BY CONSTRUCTION: a symbol-day mask only",
         "  REMOVES trades from the published book, it never shifts or adds an entry.", ""]

    for base in BOOKS_BASE:
        rows = base_books[base]
        days = days_of(rows)
        cut_date = days[len(days) // 2] if len(days) >= 2 else (days[0] if days else "")
        symdays = symdays_of(rows)
        L += [f"=== {base} ===  {len(rows):,} baseline trades over {symdays:,} traded "
              f"symbol-days   halves cut at {cut_date}", ""]
        L += G.book_block(base, rows, cut_date, universe_symdays)

        could, total, detail = could_bind(rows, features)
        for cut in CUTS:
            gname = _name(base, cut)
            gated, refused = gate_book(rows, keep_set(features, cut))
            L += G.binding_block(
                gname, could, total, detail,
                what="baseline trades whose symbol-day a pre-trade alert could ever have covered",
                detail_label="pre-entry bar coverage")
            L += G.book_block(gname, gated, cut_date, universe_symdays)
            L += G.verdict_block(base, gname, rows, gated, cut_date, universe_symdays)
            L += G.refused_block(base, gname, refused)

    L += ["WHAT THIS IS NOT", "",
          "  NOT A RE-RUN OF THE ENGINES. Trades are the already-published book; only",
          "  symbol-day membership changes.",
          "  NOT OUT OF SAMPLE. holdout.json untouched.",
          "  NOT TIER 2. The 2,508 scanned-never-traded symbol-days are still untested",
          "  (REGISTERED_running_up_universe.md sec 6).",
          "  NOT A SEARCH. All nine cuts were printed by the preflight before this file",
          "  existed; none is chosen after seeing a P&L.", ""]
    return L


CSV_COLS = ["book", "cut", "symbol", "date", "ordinal", "entry_et", "entry_px", "exit_et",
            "exit_px", "reason", "bars_held", "net"]


def write_csv(path: str, base_books: dict[str, list[dict]], features: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        for base in BOOKS_BASE:
            rows = base_books[base]
            for cut in CUTS:
                gated, _ = gate_book(rows, keep_set(features, cut))
                for r in gated:
                    w.writerow(dict(r, book=_name(base, cut), cut=cut))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--trades", default=TRADES_CSV)
    p.add_argument("--features", default=FEATURES_CSV)
    p.add_argument("--pairs", default=PAIRS)
    p.add_argument("--out", default="var/reports/running_up_universe_gate.txt")
    p.add_argument("--csv", default="var/reports/running_up_universe_gate_trades.csv")
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    t0 = time.time()
    base_books = load_trades(a.trades)
    features = load_features(a.features)
    universe_symdays = len(json.loads(Path(a.pairs).read_text(encoding="utf-8")))
    lines = render(base_books, features, universe_symdays)
    elapsed = time.time() - t0
    lines.append(f"  elapsed {elapsed:.2f}s (CSV arithmetic only, no engine run, no tape read)")
    emit("\n".join(lines), a.out,
         header=f"common.running_up_universe_gate trades={a.trades} features={a.features} "
                f"cuts={len(CUTS)} books={len(BOOKS_BASE)}")
    write_csv(a.csv, base_books, features)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
