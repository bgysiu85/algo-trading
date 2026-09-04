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
    """US equities only -- same filter as common/backtest.py's
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


# --- cache layout ----------------------------------------------------------
#
# Bars are cached per WINDOW, not just per symbol and date, because the two
# pulls in this repo are not interchangeable and neither is a superset of the
# other:
#
#   common/backtest.py  "2 D" ending 09:30 ET -- carries prior-day warm-up,
#                       stops at the open
#   common/data_ib.py   "1 D" ending 20:00 ET -- no prior day, runs to the
#                       post-market close
#
# Keyed on symbol+date alone, a frame fetched for one would be served to the
# other: a truncated session that looks like perfectly good data. That is the
# same failure shape as IB reporting throttling via empty lists, and it is
# the one this repo keeps paying for.
#
# The directory name is DERIVED from the request parameters rather than
# written by hand, so it cannot disagree with what is actually inside it, and
# a third window gets its own folder automatically.


def window_key(duration: str, end_hhmm: str) -> str:
    """('2 D', '0930') -> '2d_to_0930'."""
    return f"{duration.lower().replace(' ', '')}_to_{end_hhmm}"


def window_dir(root: Path, duration: str, end_hhmm: str) -> Path:
    return Path(root) / window_key(duration, end_hhmm)


def cache_path(cache_dir: Path, symbol: str, date_str: str) -> Path:
    """Gzipped, per section 5 of claude/repo_reorg_and_github_plan.md -- pandas
    reads and writes it by extension with no extra dependency."""
    return Path(cache_dir) / f"{symbol}_{date_str}.csv.gz"


def load_cached_bars(cache_dir: Path, symbol: str, date_str: str) -> pd.DataFrame | None:
    """Previously-fetched 1-minute bars for one pair, or None if they were
    never fetched (or fetched as NOT_QUALIFIED / NO_DATA -- check the pull
    state file in the same directory for why).

    cache_dir must be a WINDOW directory (see window_dir), not the cache
    root: bars are only interchangeable within one window.
    """
    path = cache_path(cache_dir, symbol, date_str)
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df
