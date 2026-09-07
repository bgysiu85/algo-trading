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

import json
from pathlib import Path

import pandas as pd


def symbology_path(path: str | Path) -> Path:
    """The archived instrument_id -> ticker mapping for one data file."""
    p = Path(path)
    return p.with_name(p.name.split(".")[0] + ".symbology.json")


def symbol_lookup(symbology_text: str, dates_needed) -> dict:
    """{(instrument_id, 'YYYY-MM-DD'): ticker} from an archived symbology file.

    A sidecar maps ticker -> intervals of {d0, d1, s}, where `s` is the
    instrument_id and the interval is [d0, d1). The map has to be keyed on the
    PAIR, not on the id alone: an instrument_id is only unique within its
    interval and ids are reused, so keying on the id would silently mislabel
    every row of a reused one -- a wrong ticker rather than a missing one.

    Only the dates actually present are expanded, which bounds a monthly chunk
    at roughly 11,500 tickers x 21 sessions rather than the whole history.
    """
    data = json.loads(symbology_text)
    result = data.get("result", data)
    want = sorted({str(d) for d in dates_needed})
    out: dict[tuple[int, str], str] = {}
    for ticker, intervals in result.items():
        if not isinstance(intervals, list):
            continue
        for iv in intervals:
            try:
                sid = int(iv["s"])
            except (KeyError, TypeError, ValueError):
                continue
            d0, d1 = iv.get("d0", ""), iv.get("d1", "")
            for day in want:
                if d0 <= day < d1:
                    out[(sid, day)] = ticker
    return out


def map_symbols_manually(df: pd.DataFrame, symbology_text: str) -> pd.DataFrame:
    """Resolve instrument_id -> ticker without databento's vectorised resolver.

    WHY THIS EXISTS
    ---------------
    `to_df(map_symbols=True)` dies on the full-universe MONTHLY chunks:

        TypeError: Cannot compare structured arrays unless they have a common
        dtype

    raised by `np.unique(query_array, axis=0)` inside
    `InstrumentMap.resolve_many`. That array is built from
    `np.asarray(dates, dtype='datetime64[D]')` applied to a tz-aware pandas
    Series, which does not cleanly downcast on this numpy/pandas pair.

    It is a version interaction, not a corrupt file -- the identical call
    succeeds on the 5 MB daily chunks and fails on the 390 MB minute ones. So
    the join is done here instead, from the archived sidecar, and is checked
    against the working path on a file where both run.
    """
    idx = df.index
    dates = (idx.tz_convert("UTC") if getattr(idx, "tz", None) else idx
             ).strftime("%Y-%m-%d")
    lut = symbol_lookup(symbology_text, set(dates))
    ids = df["instrument_id"].astype("int64").to_numpy()
    df = df.copy()
    df["symbol"] = [lut.get((int(i), d)) for i, d in zip(ids, dates)]
    return df


def read_dbn(path: str | Path, *, require_symbols: bool = True) -> pd.DataFrame:
    """One .dbn / .dbn.zst file as a DataFrame, UTC-indexed on ts_event.

    THE SYMBOLOGY TRAP
    ------------------
    A file pulled with symbols="ALL_SYMBOLS" carries NO symbol mapping in its
    metadata -- there is nothing to embed, because nothing was named in the
    request. `to_df(map_symbols=True)` on such a file does not fail: it returns
    every row with symbol=None.

    That is as bad as it gets. The first run of common.screen over 43 chunks and
    206,362 rows per month reported "864 symbol-days, 0 distinct symbols" and
    exited 0. The pipeline downstream de-duplicated on (symbol, date), collapsed
    a million rows to one per session, and produced a clean-looking report
    saying the screen selected nothing. Every figure in it was structurally
    zero, and nothing anywhere raised.

    So the mapping is archived beside the data at download time
    (<label>.symbology.json) and loaded here. If it is absent this raises --
    require_symbols=False is available for inspecting a raw file, and is not
    what any analysis should use.
    """
    from common.databento_fetch import require_databento

    db = require_databento()

    store = db.DBNStore.from_file(str(path))
    # A file pulled with an EXPLICIT symbol list carries its own mapping -- the
    # request named the symbols, so there was something to embed. Only an
    # ALL_SYMBOLS pull needs the sidecar. Demanding it unconditionally would
    # reject every scoped fetch (the tbbo archive, for one) for a problem it
    # does not have.
    embedded = bool((store.symbology or {}).get("mappings"))
    sym = symbology_path(path)
    if sym.exists():
        store.insert_symbology_json(sym.read_text(encoding="utf-8"))
    elif embedded:
        pass
    elif require_symbols:
        raise FileNotFoundError(
            f"{sym} is missing, so instrument_id cannot be resolved to tickers "
            f"and every row of {Path(path).name} would silently carry "
            "symbol=None. Backfill it with:\n"
            "  python -m common.databento_universe --resymbolize")

    sym_text = sym.read_text(encoding="utf-8") if sym.exists() else ""
    try:
        df = store.to_df(map_symbols=True)
    except TypeError as e:
        # databento's vectorised resolver fails on the large monthly chunks --
        # see map_symbols_manually. Narrow to that failure: any OTHER TypeError
        # is a real problem and must not be swallowed into a silent fallback.
        if "structured arrays" not in str(e):
            raise
        if not sym_text:
            raise RuntimeError(
                f"{Path(path).name}: databento's symbol resolver failed and "
                f"there is no {sym.name} to fall back on. Backfill it with "
                "python -m common.databento_universe --resymbolize") from e
        print(f"  {Path(path).name}: resolver failed, mapping symbols from "
              f"{sym.name}", flush=True)
        df = map_symbols_manually(store.to_df(map_symbols=False), sym_text)
    if df.empty:
        return df
    if require_symbols and "symbol" in df.columns and df["symbol"].isna().all():
        raise ValueError(
            f"{Path(path).name}: every symbol resolved to None even with a "
            "symbology file. Re-run --resymbolize; do not analyse this.")
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
    df = read_many(d.glob("*.dbn.zst"))
    if df.empty:
        return df
    out = df.reset_index()
    if "symbol" not in out.columns or out["symbol"].isna().all():
        raise ValueError(
            "The daily archive resolved no tickers. Run:\n"
            "  python -m common.databento_universe --resymbolize")
    out = out[out["symbol"].notna()]
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
