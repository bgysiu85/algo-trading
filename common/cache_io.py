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


# --- shared superset window ------------------------------------------------
#
# The two consumers can be served from ONE fetch, halving the IB request
# budget when both need the same symbol/date. Two things make that safe, and
# neither is optional.
#
# 1. THE SUPERSET MUST ACTUALLY CONTAIN BOTH. "2 D" ending 20:00 is the
#    obvious guess and it is WRONG: it starts 10.5h after backtest.py's
#    window begins, losing the prior-day warm-up. "3 D" ending 20:00 is the
#    smallest that covers both.
#
# 2. EACH CONSUMER MUST SLICE BACK TO ITS OWN WINDOW. Handing a strategy a
#    longer frame changes its indicators ON THE IDENTICAL BARS, because EMA
#    has infinite memory -- measured at up to 58 RSI points on a 3000-bar
#    synthetic series. Caching a superset and passing it through unsliced
#    would silently revalue every backtest.
#
# Whether IB's "3 D" response really contains the same bars its "2 D"
# response would, including boundary handling, is an EMPIRICAL question about
# IB rather than arithmetic. common/probe_window.py answers it against the
# live API; until it has, leave SHARED_WINDOW off.

SHARED_DURATION = "3 D"
SHARED_END_HHMM = "2000"
SHARED_SESSIONS = 3


def check_sessions(df, end, want: int, tz="America/New_York") -> int:
    """Distinct trading sessions in `df` at or before `end`.

    Callers slice a superset down to their own window, and the one way that
    can go wrong is the superset not reaching back far enough -- a short IB
    response, or a symbol that simply has no history that far back. That
    would hand a strategy less warm-up than it asked for, changing its
    EMA-seeded indicators silently. Counting is cheap; raise rather than
    guess.
    """
    if df is None or df.empty:
        return 0
    local = df.index.tz_convert(tz)
    end_local = end.astimezone(local.tz) if hasattr(end, "astimezone") else end
    return len({d for d in local.date if d <= end_local.date()})


def slice_sessions(df: pd.DataFrame, end, n_sessions: int,
                   tz="America/New_York") -> pd.DataFrame:
    """The bars an IB `{n_sessions} D` request ending at `end` would return.

    IB counts TRADING SESSIONS, not calendar time. A probe against the live
    API on 2026-09-04 pinned the rule exactly:

        "N D" ending T on date D = the N-1 preceding trading sessions IN
        FULL, plus D's own session up to but EXCLUDING T.

    The arithmetic matched to the bar: a "2 D" request ending 09:30 returned
    1290 bars = 960 (a full 04:00-20:00 session) + 330 (04:00 to 09:30
    exclusive).

    The earlier calendar-based version of this function was wrong in both
    directions and silently so. From a Monday it subtracted three calendar
    days, landing on Friday 20:00 and dropping the entire Friday session --
    960 bars IB would have returned. From a Friday it reached back to
    Wednesday and added 630 bars IB would not have. Weekends and holidays are
    exactly where it broke.

    Sessions are taken from the dates PRESENT IN THE DATA rather than from a
    calendar, so market holidays and half-days need no special handling: a day
    the market was shut simply has no bars and is not a session.
    """
    if df.empty:
        return df
    local = df.index.tz_convert(tz)
    end_local = end.astimezone(local.tz) if hasattr(end, "astimezone") else end
    end_date, end_time = end_local.date(), end_local.time()

    dates = sorted({d for d in local.date if d <= end_date})
    if not dates:
        return df.iloc[:0]
    keep = set(dates[-n_sessions:])

    mask = [(d in keep) and not (d == end_date and tm >= end_time)
            for d, tm in zip(local.date, local.time)]
    return df[mask]
