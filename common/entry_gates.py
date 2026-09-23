#!/usr/bin/env python3
r"""Entry gates study: spread gate and thin-bar volume gate.

    python -m common.entry_gates --jobs 8

Registered in docs/research/REGISTERED_entry_gates.md before this file existed.

GATES
-----
1. Spread gate: refuse entry when quoted bid-ask spread >= 2.0%.
   - Live evidence: 13 trades, -$601.87 net, -$46.30 per trade.
   - Backtest uses high-low / close as spread surrogate from ohlcv-1m.

2. Signal-bar volume gate: refuse entry when signal bar volume < 2,000 shares.
   - Live evidence: 12 trades, -$214.48 net, -$17.87 per trade.
   - Backtest measures volume from ohlcv-1m directly.

Both gates are applied AFTER the signal, BEFORE the order, on entries only.
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
REGISTERED = "docs/research/REGISTERED_entry_gates.md"

# Gate thresholds (registered PRE-RUN)
SPREAD_THRESHOLD = 0.02  # 2.0%
VOLUME_THRESHOLD = 2000  # shares, 1-minute bar

# Book naming: baseline + each gate + both together
BOOKS = (
    ("MCL", "mcl", None),
    ("MCL-spread", "mcl", ("spread", SPREAD_THRESHOLD)),
    ("MCL-volume", "mcl", ("volume", VOLUME_THRESHOLD)),
    ("MCL-both", "mcl", ("both", SPREAD_THRESHOLD, VOLUME_THRESHOLD)),
    ("MC5", "mc5", None),
    ("MC5-spread", "mc5", ("spread", SPREAD_THRESHOLD)),
    ("MC5-volume", "mc5", ("volume", VOLUME_THRESHOLD)),
    ("MC5-both", "mc5", ("both", SPREAD_THRESHOLD, VOLUME_THRESHOLD)),
)

PAIRED = (
    ("MCL", "MCL-spread"),
    ("MCL", "MCL-volume"),
    ("MCL", "MCL-both"),
    ("MC5", "MC5-spread"),
    ("MC5", "MC5-volume"),
    ("MC5", "MC5-both"),
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
    """Compute bid-ask spread % from high-low / close.
    
    On point-in-time ohlcv-1m data, the spread is estimated as:
    spread% = (high - low) / close
    
    This approximates the quoted spread from bar open to close
    (includes execution slippage, not pure quotes).
    
    Returns a numpy array aligned with df's index.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    # Spread as (high - low) / close; clip at 0 for degenerate bars
    spread = ((high - low) / close).fillna(0).clip(lower=0).values
    return spread


def compute_volume(df: pd.DataFrame) -> np.ndarray:
    """Extract volume from ohlcv-1m data.
    
    Returns a numpy array of volumes aligned with df's index.
    """
    vol = df["volume"].astype(float).fillna(0).values
    return vol


def make_gate(spec: tuple | None, spread_arr: np.ndarray, vol_arr: np.ndarray) -> np.ndarray:
    """Generate a gate array (True = allow entry, False = refuse).
    
    Args:
        spec: tuple like ("spread", 0.02) or ("volume", 2000) or ("both", 0.02, 2000)
        spread_arr: pre-computed spread % array
        vol_arr: pre-computed volume array
    
    Returns:
        Boolean numpy array: True to allow entry, False to refuse.
    """
    if spec is None:
        # Baseline: allow all
        return np.ones(len(spread_arr), dtype=bool)
    
    kind = spec[0]
    
    if kind == "spread":
        threshold = spec[1]
        # Refuse if spread >= threshold
        return spread_arr < threshold
    
    elif kind == "volume":
        threshold = spec[1]
        # Refuse if volume < threshold
        return vol_arr >= threshold
    
    elif kind == "both":
        spread_thresh = spec[1]
        volume_thresh = spec[2]
        # Refuse if EITHER gate fires (AND of both allows)
        spread_gate = (spread_arr < spread_thresh)
        volume_gate = (vol_arr >= volume_thresh)
        return (spread_gate & volume_gate)
    
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
        
        # Compute gates once per symbol-day
        spread_arr = compute_spread(df)
        vol_arr = compute_volume(df)
        
        # ALL OR NONE: if any book raises, drop from all
        try:
            got = {}
            for name, eng, spec in BOOKS:
                mod, extra = engines[eng]
                gate_mask = make_gate(spec, spread_arr, vol_arr)
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
    from common.db_load import load_archive
    
    archive = load_archive(Path("var/data"))
    tasks, by_date = G.build_tasks(PAIRS, archive, DATASET, args.limit)
    jobs = G.jobs_from(args.jobs)
    
    print(f"Entry gates study: {len(tasks)} sessions, {jobs} workers")
    print(f"  Spread threshold: {SPREAD_THRESHOLD:.1%}")
    print(f"  Volume threshold: {VOLUME_THRESHOLD:,} shares")
    
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
        "ENTRY GATES STUDY: SPREAD AND VOLUME",
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
            f"Spread gate: refuse if spread >= {SPREAD_THRESHOLD:.1%}",
            f"Volume gate: refuse if 1-minute bar volume < {VOLUME_THRESHOLD:,} shares",
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
            "volume_threshold": VOLUME_THRESHOLD,
            "dataset": DATASET,
            "pairs": PAIRS,
        },
    )


if __name__ == "__main__":
    main()
