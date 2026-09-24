#!/usr/bin/env python3
"""H60 bars: 1-minute ITCH RTH bars -> the registered 60-minute grid.
W14-0003, REGISTERED_h60_v0.md §2.2.

THE TWO GRIDS, AND WHY NEITHER IS CHOSEN HERE
---------------------------------------------
    primary   09:30 10:30 11:30 12:30 13:30 14:30 (60 min) + 15:30 (30 min)
              -- the grid TradingView shows on a US stock's 60-minute chart
    fallback  09:30 (30 min) + 10:00 11:00 12:00 13:00 14:00 15:00 (60 min)
              -- §2.2's amendment-B grid, used if the G1 pricing put the RTH
                 1-minute pull above $50 or 25 GB billable

The W14-0002 pricing report (var/reports/h60_data_plan.txt, 2026-09-23) says
35.76 GB at $0.00 -- above the 25 GB line, so §2.2's rule reads FALLBACK, and
the 1-minute RTH pull was then made anyway. Which grid this study uses is a
PRE-RUN registration decision (amendment B), recorded BEFORE any bar is read.
Every entry point that reads real bars refuses while `GRID` is None. Amendment
B (2026-09-25, W14-0006, Ben: "A") set it to "primary". Both grids are built from the
same 1-minute files: a clock-hour bar resampled from ITCH 1-minute bars is the
same aggregation `ohlcv-1h` performs on the same prints.

CONVENTIONS THAT DECIDE RESULTS (PROGRAM_INDEX §5)
-------------------------------------------------
* `ts_event` is the interval START. A bar is labelled by its start and is
  KNOWABLE ONLY WHEN IT CLOSES; the first price a decision taken on it can be
  acted on is the next bar's open.
* A bucket with no 1-minute bar produces no row. Nothing is synthesised.
* Half-days end at 13:00 ET; the bar that straddles 13:00 simply ends early.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")

GRIDS = ("primary", "fallback")

# Set by amendment B (REGISTERED_h60_v0.md §2.2), in the same commit as the
# amendment text, BEFORE any bar is read. None refuses every real-data path.
# Amendment B, 2026-09-25 (W14-0006), Ben: "A" -- the primary grid stands.
GRID: str | None = "primary"

RTH_OPEN_MIN = 9 * 60 + 30          # 570
RTH_CLOSE_MIN = 16 * 60             # 960
BARS_PER_SESSION = 7                # both grids have seven slots

COLUMNS = ["symbol", "session", "bar", "t_open", "open", "high", "low",
           "close", "volume", "n_min"]


class GridNotChosen(SystemExit):
    """Raised before any real bar is read while amendment B is unrecorded."""


def require_grid(grid: str | None = None) -> str:
    g = GRID if grid is None else grid
    if g is None:
        raise GridNotChosen(
            "No bar grid is recorded. REGISTERED_h60_v0.md §2.2: the W14-0002 "
            "pricing (35.76 GB, $0) is above the 25 GB fallback line, so the "
            "grid must be fixed by PRE-RUN amendment B -- committed with "
            "strategy/h60/bars.py GRID set -- before any bar is read.")
    if g not in GRIDS:
        raise ValueError(f"unknown grid {g!r}; must be one of {GRIDS}")
    return g


def bucket_of(minute_of_day, grid: str):
    """Grid slot (0..6) of an ET minute-of-day in [09:30, 16:00).

    Works on scalars and numpy arrays. Minutes outside RTH are the caller's
    to drop; they are not clipped here, so a leak shows up as a bad slot.
    """
    m = np.asarray(minute_of_day)
    if grid == "primary":
        return (m - RTH_OPEN_MIN) // 60
    if grid == "fallback":
        return np.where(m < 600, 0, 1 + (m - 600) // 60)
    raise ValueError(f"unknown grid {grid!r}")


def slot_start_min(slot: int, grid: str) -> int:
    """ET minute-of-day at which a slot opens."""
    if grid == "primary":
        return RTH_OPEN_MIN + 60 * slot
    if grid == "fallback":
        return RTH_OPEN_MIN if slot == 0 else 600 + 60 * (slot - 1)
    raise ValueError(f"unknown grid {grid!r}")


def slot_end_min(slot: int, grid: str) -> int:
    """ET minute-of-day at which a FULL-DAY slot closes (16:00 caps the last)."""
    if grid == "primary":
        return min(RTH_OPEN_MIN + 60 * (slot + 1), RTH_CLOSE_MIN)
    if grid == "fallback":
        return 600 if slot == 0 else min(600 + 60 * slot, RTH_CLOSE_MIN)
    raise ValueError(f"unknown grid {grid!r}")


def half_hours(slot: int, grid: str) -> list[int]:
    """ET minute-of-day starts of the half-hours a slot covers -- the unit the
    G2 spread table is measured in (costs.py)."""
    a, b = slot_start_min(slot, grid), slot_end_min(slot, grid)
    return list(range(a, b, 30))


def resample_day(day: pd.DataFrame, grid: str) -> pd.DataFrame:
    """One session's 1-minute bars for many symbols -> the 60-minute grid.

    `day` has a tz-aware DatetimeIndex (ts_event = interval START) and columns
    symbol/open/high/low/close/volume. Rows outside 09:30-16:00 ET are dropped
    (the pull is RTH already; this is the belt). Returns COLUMNS, one row per
    (symbol, slot) that had at least one minute, sorted.
    """
    if day.empty:
        return pd.DataFrame(columns=COLUMNS)
    if day.index.tz is None:
        raise ValueError("1-minute index must be timezone-aware (UTC)")
    local = day.index.tz_convert(ET)
    minute = np.asarray(local.hour * 60 + local.minute)
    keep = (minute >= RTH_OPEN_MIN) & (minute < RTH_CLOSE_MIN)
    if not keep.any():
        return pd.DataFrame(columns=COLUMNS)
    d = day.loc[keep, ["symbol", "open", "high", "low", "close", "volume"]].copy()
    dates = pd.Index(local[keep].date)
    if dates.nunique() != 1:
        raise ValueError(f"resample_day got {dates.nunique()} sessions; one at a time")
    session = dates[0]
    d["slot"] = bucket_of(minute[keep], grid).astype(int)
    d["_t"] = d.index
    d = d.sort_values(["symbol", "_t"], kind="mergesort")
    g = d.groupby(["symbol", "slot"], sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(),
        "low": g["low"].min(), "close": g["close"].last(),
        "volume": g["volume"].sum(), "n_min": g["open"].size(),
    }).reset_index()
    out = out.rename(columns={"slot": "bar"})
    out["session"] = session
    starts = {s: slot_start_min(s, grid) for s in range(BARS_PER_SESSION)}
    base = pd.Timestamp(dt.datetime.combine(session, dt.time(0, 0)), tz=ET)
    out["t_open"] = [(base + pd.Timedelta(minutes=starts[b])).tz_convert("UTC")
                     for b in out["bar"]]
    return out[COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------
# the cache: one parquet per year, built once from the H60 archive
# --------------------------------------------------------------------------

def cache_dir(root: Path, grid: str) -> Path:
    return Path(root) / "bars_60m" / grid


def build_cache(rth_dir: Path, root: Path, grid: str | None = None, *,
                read=None, years: list[int] | None = None) -> dict:
    """Read every `<date>.dbn.zst` under `rth_dir` (data_plan.rth_root) and
    write `<root>/bars_60m/<grid>/<year>.parquet`. `read` is injectable for
    tests; the default is common.dbn_io.read_dbn."""
    grid = require_grid(grid)
    if read is None:
        from common.dbn_io import read_dbn as read
    files = sorted(Path(rth_dir).glob("*.dbn.zst"))
    by_year: dict[int, list[pd.DataFrame]] = {}
    empty = 0
    for f in files:
        day = dt.date.fromisoformat(f.name[:10])
        if years and day.year not in years:
            continue
        raw = read(f)
        if raw is None or raw.empty:
            empty += 1
            continue
        bars = resample_day(raw, grid)
        if bars.empty:
            empty += 1
            continue
        by_year.setdefault(day.year, []).append(bars)
    out = cache_dir(root, grid)
    out.mkdir(parents=True, exist_ok=True)
    written = {}
    for y, frames in sorted(by_year.items()):
        df = pd.concat(frames, ignore_index=True)
        p = out / f"{y}.parquet"
        df.to_parquet(p, index=False)
        written[y] = len(df)
    return {"files": len(files), "empty_days": empty, "rows_by_year": written,
            "dir": str(out)}


def load_cache(root: Path, grid: str | None = None) -> pd.DataFrame:
    grid = require_grid(grid)
    d = cache_dir(root, grid)
    parts = sorted(d.glob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no cached bars under {d}; run --build-cache")
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    return normalise(df)


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Types and order every consumer relies on."""
    df = df.copy()
    df["session"] = pd.to_datetime(df["session"]).dt.date
    df["bar"] = df["bar"].astype(int)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].astype(float)
    df["symbol"] = df["symbol"].astype(str)
    t = pd.to_datetime(df["t_open"])
    df["t_open"] = t.dt.tz_localize("UTC") if t.dt.tz is None else t.dt.tz_convert("UTC")
    return df.sort_values(["symbol", "session", "bar"], kind="mergesort").reset_index(drop=True)
