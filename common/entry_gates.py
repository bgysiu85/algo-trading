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
SCHEMA = "cbbo-1s"          # quote source, fixed in REGISTERED_spread_gate.md §3
# cbbo-1s emits a consolidated snapshot every second by construction, so a
# quote should exist within a second or two of any bar-close timestamp.
# 5s (not quote_fill.py's 1,800s, which matches sparse trade PRINTS against
# a per-date tbbo/tcbbo tape) keeps a stale quote from silently standing in
# across a real gap in coverage.
TOLERANCE_S = 5
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


def quote_window_path(archive: Path, day: str, symbol: str) -> Path:
    """Where step 3's pull put this symbol-day's quotes.

    Mirrors common.quote_price.window_path exactly -- ONE FILE PER
    (day, symbol), not the per-calendar-date archive that
    common.friction_quotes.quotes_for_date reads (that layout belongs to a
    different pull, common/quote_fill.py's tcbbo trade-with-quote tape, and
    does not apply to the window pull done for this registration).
    """
    return archive / DATASET / SCHEMA / "windows" / day / f"{symbol}.dbn.zst"


def load_quote_window(archive: Path, day: str, symbol: str) -> pd.DataFrame:
    """This symbol-day's real top-of-book quotes, sorted by time.

    Empty (not an error) when the window file is absent or has no rows --
    that is a legitimate "no quote" case, handled by compute_spread as
    np.nan and by make_gate as a refusal. A PRESENT file with the wrong
    columns is not: that means the cbbo-1s schema's field names do not
    match what this function assumes, which is a mapping bug, not a
    missing-quote fact about the market -- so it raises instead of
    silently returning nothing, the same discipline
    common.friction_quotes.quotes_for_date already applies to tcbbo.
    """
    from common.dbn_io import read_dbn

    p = quote_window_path(archive, day, symbol)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=["ts", "bid", "ask"])
    out = read_dbn(p)
    if out.empty:
        return pd.DataFrame(columns=["ts", "bid", "ask"])
    out = out.reset_index()
    tcol = "ts_recv" if "ts_recv" in out.columns else "ts_event"
    keep = [tcol, "bid_px_00", "ask_px_00"]
    missing = [c for c in keep if c not in out.columns]
    if missing:
        raise ValueError(
            f"{p.name}: cbbo-1s window is missing {missing}. Columns "
            f"present: {sorted(out.columns)}. This is the first real read "
            "of this schema's output by entry_gates.py -- if the field "
            "names differ from the tcbbo/cmbp-1 shape "
            "common.friction_quotes.quotes_for_date already parses, this "
            "loader needs updating to match, not a silent empty return."
        )
    out = out[keep].rename(
        columns={tcol: "ts", "bid_px_00": "bid", "ask_px_00": "ask"})
    out = out[(out["bid"] > 0) & (out["ask"] > 0) & (out["ask"] >= out["bid"])]
    out["ts"] = pd.to_datetime(out["ts"], utc=True)
    # A record with a valid priced bid/ask but a null/unparseable timestamp
    # is not a mapping bug (columns and prices are fine) -- merge_asof
    # cannot join on a null key on either side, so drop it here and let the
    # bar it would have matched fall through to compute_spread's np.nan /
    # make_gate's refusal, same as a bar with no quote in the window at all.
    out = out.dropna(subset=["ts"])
    return out.sort_values("ts").reset_index(drop=True)


def compute_spread(df: pd.DataFrame, quotes: pd.DataFrame) -> np.ndarray:
    """Bid-ask spread % at each of df's bar timestamps, from real quotes.

    spread% = (ask - bid) / mid, taken from the quote standing at or before
    each bar's own timestamp (direction="backward", the same "last record
    at or before the close IS the quote at the close" rule
    common/quote_price.py registers for how the window itself was priced),
    within TOLERANCE_S. A bar with no quote inside that tolerance -- an
    empty `quotes` frame, or a gap wider than TOLERANCE_S -- reads np.nan,
    which make_gate treats as a refusal, never as an allow.

    Returns a numpy array aligned with df's index (one value per bar).
    """
    bars = pd.DataFrame({"ts": pd.to_datetime(df.index, utc=True)})
    if quotes.empty:
        return np.full(len(bars), np.nan)

    q = quotes.copy()
    q["mid"] = (q["bid"] + q["ask"]) / 2.0
    q["spread_pct"] = (q["ask"] - q["bid"]) / q["mid"]

    m = pd.merge_asof(
        bars.reset_index().sort_values("ts"),
        q[["ts", "spread_pct"]].sort_values("ts"),
        on="ts", direction="backward",
        tolerance=pd.Timedelta(seconds=TOLERANCE_S),
    ).sort_values("index")
    return m["spread_pct"].to_numpy()


def make_gate(spec: tuple | None, spread_arr: np.ndarray, index: pd.Index) -> pd.Series:
    """Generate a gate Series (True = allow entry, False = refuse).

    Every sibling gate in this codebase (chase_gate.stamp_on, pullback_cell's
    gate, dist_from_high_gate) hands the engines a pd.Series indexed like the
    bar frame, because strategy/mc5/mc5.py and strategy/mcl/mcl.py both do
    ``entry_gate.reindex(sig.index, fill_value=False)`` on whatever they are
    given -- a bare ndarray has no .reindex and raises AttributeError deep
    inside the engine, on every session, which is what a bare-array return
    here actually did on the first real run (2026-09-24).

    Args:
        spec: tuple like ("spread", 0.02), or None for baseline
        spread_arr: pre-computed spread % array (may contain np.nan for
            missing quotes), positionally aligned with `index`
        index: the bar frame's own index (df.index) that spread_arr lines
            up with -- this becomes the returned Series' index so the
            engines' own .reindex(sig.index, ...) call lines it up correctly.

    Returns:
        Boolean pd.Series, indexed by `index`: True to allow entry, False to
        refuse.
    """
    if spec is None:
        # Baseline: allow all entries
        return pd.Series(np.ones(len(spread_arr), dtype=bool), index=index)

    kind = spec[0]

    if kind == "spread":
        threshold = spec[1]
        # Refuse if:
        #   - spread is missing (np.nan), OR
        #   - spread >= threshold
        # Allow only if spread exists AND is below threshold
        result = (spread_arr < threshold) & ~np.isnan(spread_arr)
        return pd.Series(result, index=index)

    else:
        raise ValueError(f"Unknown gate spec: {kind}")


def run_day(args: tuple) -> tuple:
    """Run one session across all gated and baseline books.

    Args:
        args: (paths list, day str, universe list, archive Path)

    Returns:
        (day, result dict, error string)
    """
    from common.dbn_io import read_dbn
    from common.pit_h0 import first_seen_time
    from common.pit_strategy import build_frame, engine

    paths, day, universe, archive = args
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

        # Compute spread once per symbol-day, from step 3's real quote pull
        quotes = load_quote_window(archive, day, rec["symbol"])
        spread_arr = compute_spread(df, quotes)

        # ALL OR NONE: if any book raises, drop from all
        try:
            got = {}
            for name, eng, spec in BOOKS:
                mod, extra = engines[eng]
                gate_mask = make_gate(spec, spread_arr, df.index)
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
    # Same archive root serves the ohlcv-1m bars (build_tasks, above) and the
    # cbbo-1s quote windows step 3 pulled (load_quote_window) -- one archive,
    # two dataset/schema subtrees under it. Thread it into each task so
    # run_day can read a symbol-day's quotes without a second CLI argument.
    tasks = [(pp, d, u, archive) for pp, d, u in tasks]
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
