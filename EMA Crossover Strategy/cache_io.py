#!/usr/bin/env python3
"""
Pair-list and bar-cache I/O shared between data_ib.py (writes the cache, and
needs ib_async) and vw9_setup_counts.py (only ever reads it, and must not
need ib_async -- it's pure offline analysis over whatever data_ib.py already
pulled). Splitting this out keeps the analysis script runnable anywhere
pandas is, including for testing this module itself with synthetic bars.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_pairs(path: Path) -> list[dict]:
    """US equities only -- same filter as ../MCL Strategy/mcl_backtest.py's
    load_pairs, kept identical so the two projects never quietly diverge on
    which symbols count as tradeable."""
    pairs = json.loads(Path(path).read_text())
    out = []
    for p in pairs:
        sym = str(p["symbol"]).upper().strip()
        if "." in sym or not sym.isalpha():
            continue
        out.append({"symbol": sym, "date": p["date"]})
    return out


def cache_path(cache_dir: Path, symbol: str, date_str: str) -> Path:
    return Path(cache_dir) / f"{symbol}_{date_str}.csv"


def load_cached_bars(cache_dir: Path, symbol: str, date_str: str) -> pd.DataFrame | None:
    """Previously-fetched 1-minute bars for one pair, or None if data_ib.py
    never fetched them (or fetched them as NOT_QUALIFIED / NO_DATA -- check
    data_pull_state.json in the same directory for why)."""
    path = cache_path(cache_dir, symbol, date_str)
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df
