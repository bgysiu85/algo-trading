#!/usr/bin/env python3
"""Read the Databento archive into pandas, once, in one place.

Everything downstream of common/databento_fetch.py and
common/databento_universe.py comes through here, so the conventions that bite
are handled once rather than rediscovered per consumer.

THREE CONVENTIONS THAT SILENTLY CHANGE RESULTS
-----------------------------------------------
1. ts_event is the interval START. A bar stamped 09:30 covers 09:30:00-09:30:59.
   Treating it as the end shifts every bar one interval and every entry with it.
   The existing bar_cache follows the same convention, so mixing the two is only
   safe because both are starts -- do not "fix" one of them.

2. Prices are RAW. Databento does not split- or dividend-adjust. That is the
   point (IB's adjusted history put VW9 into positions at $4,152/share), but it
   means a figure computed here will NOT reconcile with an older IB-based one on
   any name that has since split. That is the correction working, not a bug.

3. No bar is emitted for an interval with no trade. A thin pre-market is a
   sparse index, not a run of zero-volume rows. Any code that assumes a
   contiguous minute index will silently mis-align; reindex explicitly if you
   need one.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_dbn(path: str | Path) -> pd.DataFrame:
    """One .dbn / .dbn.zst file as a DataFrame, UTC-indexed on ts_event.

    map_symbols=True resolves instrument_id back to the ticker. Without it every
    frame is keyed by an integer that is only meaningful inside one dataset and
    changes across listing events.
    """
    import databento as db

    df = db.DBNStore.from_file(str(path)).to_df(map_symbols=True)
    if df.empty:
        return df
    if df.index.name != "ts_event" and "ts_event" in df.columns:
        df = df.set_index("ts_event")
    df.index = (df.index.tz_localize("UTC") if df.index.tz is None
                else df.index.tz_convert("UTC"))
    return df.sort_index()


def read_many(paths) -> pd.DataFrame:
    """Concatenate an archive's files. Empty frames are skipped, not errors --
    a legitimately empty day (holiday, no qualifying trades) must not abort a
    multi-year load."""
    frames = [f for f in (read_dbn(p) for p in sorted(paths)) if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames).sort_index()


def daily_frame(archive: str | Path, dataset: str) -> pd.DataFrame:
    """Every ohlcv-1d bar in the archive, as symbol / date / OHLCV.

    Returns a plain frame rather than an index so the screen can be written as
    ordinary groupby arithmetic. `date` is the ET session date: daily bars are
    stamped at UTC midnight, so converting the timestamp to ET would move a
    session into the previous day.
    """
    d = Path(archive) / dataset / "ohlcv-1d"
    if not d.exists():
        return pd.DataFrame()
    df = read_many(d.glob("*.dbn*"))
    if df.empty:
        return df
    out = df.reset_index()
    out["date"] = out["ts_event"].dt.strftime("%Y-%m-%d")
    keep = ["symbol", "date", "open", "high", "low", "close", "volume"]
    out = out[[c for c in keep if c in out.columns]]
    # One symbol can appear twice on a date if the archive was chunked with
    # overlapping windows. Summing volume and taking first/last would be wrong;
    # the archive is written non-overlapping, so a duplicate means a bug --
    # drop it loudly rather than silently double-counting.
    dupes = out.duplicated(["symbol", "date"]).sum()
    if dupes:
        print(f"  WARNING: {dupes} duplicate symbol-date rows in the daily "
              "archive -- chunks overlap. Keeping the first of each.")
        out = out.drop_duplicates(["symbol", "date"], keep="first")
    return out.sort_values(["symbol", "date"]).reset_index(drop=True)
