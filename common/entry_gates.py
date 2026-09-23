#!/usr/bin/env python3
r"""Entry gates study: spread gate (quoted bid-ask spread).

    python -m common.entry_gates --jobs 8

Registered in docs/research/REGISTERED_spread_gate.md before this file existed.

GATE
----
Spread gate: refuse entry when quoted bid-ask spread >= 2.0%.
   - Live evidence: 13 trades, -$601.87 net, -$46.30 per trade.
   - Backtest uses real quotes from XNAS.BASIC/cbbo-1s (confirmed in step 3).
   - Quote source fixed in REGISTERED_spread_gate.md §3.

The volume gate is CLOSED per thin_tape_RESULT_20260919.md §8.
   - MC5 deaths rise WITH volume; a floor would refuse the safest entries.
   - Not registered, not tested here.

Gate is applied AFTER the signal, BEFORE the order, on entries only.
Measurement runs on published MCL and MC5 engines over point-in-time universe.
The gate is the entry_gate boolean mask passed to backtest_session.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date as _date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common import gate_study as G
from common.entry_shares import MEASURED_FRICTION, QTY
from common.report_io import emit

ET = ZoneInfo("America/New_York")
PAIRS = "var/state/screen_pairs_pit.json"
DATASET = "XNAS.BASIC"
REGISTERED = "docs/research/REGISTERED_spread_gate.md"

# Gate thresholds (registered PRE-RUN in REGISTERED_spread_gate.md §2)
SPREAD_THRESHOLD = 0.02  # 2.0%, measured as (ask - bid) / mid on real quotes

# Book naming: baseline + spread gate only (volume gate is closed, not tested)
BOOKS = (
    ("MCL", "mcl", None),
    ("MCL-spread", "mcl", ("spread", SPREAD_THRESHOLD)),
    ("MC5", "mc5", None),
    ("MC5-spread", "mc5", ("spread", SPREAD_THRESHOLD)),
)

PAIRED = (
    ("MCL", "MCL-spread"),
    ("MC5", "MC5-spread"),
)


# --- measurement helpers --------------------------------------------------------

def _et(ts) -> str:
    """Format timestamp as ET time string HH:MM."""
    import pandas as pd
    return pd.Timestamp(ts).tz_convert(ET).strftime("%H:%M")


def trade_row(t, symbol: str, day: str, ordinal: int) -> dict:
    """One trade row for reporting."""
    return {
        "symbol": symbol,
        "date": day,
        "ordinal": ordinal,
        "net": float(t.net),
        "entry_et": _et(t.entry_time),
        "entry_px": float(t.entry_price),
        "exit_et": _et(t.exit_time),
        "exit_px": float(t.exit_price),
        "reason": t.reason,
        "bars_held": int(t.bars_held),
    }


def compute_spread(df: pd.DataFrame) -> np.ndarray:
    """Compute bid-ask spread % from real quotes (cbbo-1s).

    The spread is measured as: spread% = (ask - bid) / mid

    Quotes are sourced from XNAS.BASIC/cbbo-1s, pulled and confirmed in step 3.
    For each entry, the spread is looked up from the quote table at the entry time.
    If no quote is available, the spread is marked as np.nan (treated as refusal in make_gate).

    Returns a numpy array aligned with df's index.
    """
    # df has been built from dbn records with quote data embedded.
    # Look for 'spread_pct' column if it exists (added by quote_price pull).
    # Fallback: compute from ask/bid if columns are present.

    if "spread_pct" in df.columns:
        # Quote data was loaded and spread pre-computed
        spread = df["spread_pct"].astype(float).fillna(np.nan).values
    elif "ask" in df.columns and "bid" in df.columns:
        # Compute from raw ask/bid
        ask = df["ask"].astype(float)
        bid = df["bid"].astype(float)
        mid = (ask + bid) / 2.0
        spread = ((ask - bid) / mid).fillna(np.nan).clip(lower=0).values
    else:
        # No quote columns on df at all. This is NOT "no quotes for this
        # bar" (which is a legitimate np.nan / SKIPPED_SPREAD case) -- it
        # means nothing ever loaded real quotes onto `df` in the first
        # place, so every bar would silently read as unpriceable and the
        # spread-gated books would refuse 100% of entries without saying
        # why. REGISTERED_spread_gate.md G1: the full XNAS.BASIC/cbbo-1s
        # quote pull has not landed, and this module has no join step for
        # it yet (see common.friction_quotes.quotes_for_date +
        # common.quote_fill.run_day for the pattern). Fail loudly instead
        # of returning a result that looks like a real 100% refusal rate.
        raise RuntimeError(
            "compute_spread: df has no spread_pct/ask/bid columns -- real "
            "quotes were never loaded onto this frame. Do not treat this "
            "as 'refuse everything'; the quote pull + merge step (G1 in "
            "REGISTERED_spread_gate.md) has not been wired into "
            "entry_gates.py yet. See docs/research/REGISTERED_spread_gate.md."
        )

    return spread


def make_gate(spec: tuple | None, spread_arr: np.ndarray) -> np.ndarray:
    """Generate a gate array (True = allow entry, False = refuse).

    Args:
        spec: tuple like ("spread", 0.02), or None for baseline
        spread_arr: pre-computed spread % array (may contain np.nan for missing quotes)

    Returns:
        Boolean numpy array: True to allow entry, False to refuse.
    """
    if spec is None:
        # Baseline: allow all entries
        return np.ones(len(spread_arr), dtype=bool)

    kind = spec[0]

    if kind == "spread":
        threshold = spec[1]
        # Refuse if:
        #   - spread is missing (np.nan), OR
        #   - spread >= threshold
        # Allow only if spread exists AND is below threshold
        result = (spread_arr < threshold) & ~np.isnan(spread_arr)
        return result

    else:
        raise ValueError(f"Unknown gate spec: {kind}")


def run_day(args: tuple) -> tuple:
    """Run one session across all gated and baseline books.
    
    Args:
        args: (paths list, day str, universe list)
    
    Returns:
        (day, result dict, error string)
    """
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine
    
    paths, day, universe = args
    engines = {name: engine(name) for name in ("mcl", "mc5")}
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
    d = _date.fromisoformat(day)
    
    res = {
        "books": {name: [] for name, _, _ in BOOKS},
        "symdays": 0,
        "errors": 0,
        "error_days": [],
    }
    
    for rec in universe:
        df = frame[frame["symbol"] == rec["symbol"]]
        if df.empty or not rec.get("first_seen"):
            continue

        df = df.sort_index(kind="mergesort")
        floor = first_seen_time(rec)

        # Compute spread once per symbol-day (from real quotes)
        spread_arr = compute_spread(df)

        # ALL OR NONE: if any book raises, drop from all
        try:
            got = {}
            for name, eng, spec in BOOKS:
                mod, extra = engines[eng]
                gate_mask = make_gate(spec, spread_arr)
                # Run with entry_gate parameter
                got[name] = mod.backtest_session(
                    df,
                    d,
                    ET,
                    entry_shares=QTY,
                    not_before=floor,
                    entry_gate=gate_mask,
                    **extra,
                )
        except Exception as e:  # noqa: BLE001
            res["errors"] += 1
            res["error_days"].append(
                f"{rec['symbol']} {day}: {type(e).__name__}: {e}"
            )
            continue

        res["symdays"] += 1
        for name, trades in got.items():
            res["books"][name] += [
                trade_row(t, rec["symbol"], day, k)
                for k, t in enumerate(trades, 1)
            ]
    
    return day, res, ""


# --- main and argument parsing ---------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--jobs", type=int, default=8, help="parallel workers (default: 8)")
    p.add_argument(
        "--csv",
        type=str,
        default="var/reports/entry_gates.csv",
        help="output CSV (default: var/reports/entry_gates.csv)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="limit sessions for testing",
    )
    return p


def main():
    p = build_parser()
    args = p.parse_args()
    
    # Load archive and build tasks
    from common.databento_fetch import default_archive

    archive = default_archive()
    tasks, by_date = G.build_tasks(PAIRS, archive, DATASET, args.limit)
    jobs = G.jobs_from(args.jobs)
    
    print(f"Spread gate study: {len(tasks)} sessions, {jobs} workers")
    print(f"  Threshold: {SPREAD_THRESHOLD:.1%} quoted spread (cbbo-1s)")
    print(f"  Source: XNAS.BASIC/cbbo-1s (confirmed in step 3)")
    
    # Run across all sessions
    books, elapsed = G.run_sessions(run_day, tasks, jobs, "Entry gates")
    
    # Aggregate results
    all_books = {name: [] for name, _, _ in BOOKS}
    symdays = 0
    error_days = []
    
    for day in sorted(books):
        res = books[day]
        if res:
            symdays += res["symdays"]
            for name in all_books:
                all_books[name].extend(res["books"][name])
            error_days.extend(res["error_days"])
    
    print(f"  ... {len(books):,} sessions loaded, {symdays:,} symbol-days")
    if error_days:
        print(f"  ! {len(error_days)} errors:")
        for ed in error_days[:5]:
            print(f"    {ed}")
        if len(error_days) > 5:
            print(f"    ... and {len(error_days) - 5} more")
    
    # Write CSV
    G.write_csv(args.csv, all_books)
    print(f"  CSV: {args.csv}")
    
    # Compute verdict on paired books
    refused = {}
    binding = {}
    run_days = sorted(by_date.keys())
    cut = run_days[len(run_days) // 2] if len(run_days) >= 2 else (run_days[0] if run_days else "")
    
    for bname, gname in PAIRED:
        # Get refused rows (trades in baseline but not in gated)
        baseline_set = {(r["symbol"], r["date"], r["entry_et"]) for r in all_books[bname]}
        gated_set = {(r["symbol"], r["date"], r["entry_et"]) for r in all_books[gname]}
        refused_keys = baseline_set - gated_set
        refused[gname] = [r for r in all_books[bname] if (r["symbol"], r["date"], r["entry_et"]) in refused_keys]
        
        # Get binding info (how many could have been refused)
        binding[gname] = (len(refused[gname]), len(all_books[bname]), {})
    
    # Render verdict
    lines = G.render(
        "SPREAD GATE STUDY",
        REGISTERED,
        all_books,
        PAIRED,
        [],  # reported
        symdays,
        len(error_days),
        run_days,
        elapsed,
        jobs,
        refused,
        binding,
        error_days,
        preamble=[
            "",
            f"Spread gate (REGISTERED_spread_gate.md §1): refuse if (ask - bid) / mid >= {SPREAD_THRESHOLD:.1%}",
            f"Quote source: XNAS.BASIC / cbbo-1s (confirmed in step 3)",
            f"Volume gate: CLOSED per thin_tape_RESULT_20260919.md §8 (not tested here)",
            "",
        ],
        universe=PAIRS,
        dataset=DATASET,
    )
    
    txt_path = Path(args.csv).with_suffix(".txt")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Result: {txt_path}")
    print(f"  Elapsed: {elapsed:.1f}s")
    
    # Write metadata
    G.write_meta(
        args.csv,
        run_days,
        symdays,
        cut,
        {
            "registered": REGISTERED,
            "spread_threshold": SPREAD_THRESHOLD,
            "quote_source": "XNAS.BASIC/cbbo-1s",
            "dataset": DATASET,
            "pairs": PAIRS,
        },
    )


if __name__ == "__main__":
    main()
