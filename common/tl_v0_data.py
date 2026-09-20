#!/usr/bin/env python3
"""Held-contract continuous series for TL-v0, on the owned GLBX daily archive.

Reuses common/dbn_io.py for the actual file reads (embedded symbology, UTC
index) so this does not grow a second .dbn reader. The held-contract logic
below is copied from claude/raw/tsmom_topup_readback_20260920.txt's `held()`,
which is the working, already-reviewed implementation of amendment C
(REGISTERED_tsmom.md sec 0.2) that this project already trusts for GC, SI,
HG, ZN and TN. TL-v0 registers the same instrument set (REGISTERED_tl_v0.md
sec 2.1 "Markets") and the same roll rule, so it is reused rather than
re-derived.

FRONT-MONTH ROOTS (ES, RTY, CL, NG, 6A, 6B, 6E, 6J) use Databento's own
`<root>.c.0` continuous label directly as "held". TSMOM's roll cross-check
(AT-41, REGISTERED_tsmom sec 0.1) already established that c.0's symbol-change
dates agree with the registered 5-trading-day-before-expiry rule for these
roots, so re-deriving it from `definition` here would just be checking a
check that has already passed.
"""
from __future__ import annotations
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from common.dbn_io import read_dbn
from common.tsmom_fetch import default_archive, DATASET

ARCHIVE = default_archive() / DATASET

# Amendment C active cycles (REGISTERED_tsmom.md sec 0.2), reused verbatim.
CYCLE = {"GC": [2, 4, 6, 8, 10, 12], "SI": [3, 5, 7, 9, 12],
         "HG": [3, 5, 7, 9, 12], "ZN": [3, 6, 9, 12], "TN": [3, 6, 9, 12]}
DEEPER = {"GC", "SI", "HG"}   # have a <root>.c2-c4.dbn.zst file


def load_bars(root: str) -> pd.DataFrame:
    """All ohlcv-1d bars for one root's continuous symbols, concatenated.

    Dedup is on (ts_event, symbol) together, NOT ts_event alone -- c.0 and
    c.1 share the same timestamps every session, and deduping on the
    timestamp alone silently discards half of every day's rows (found while
    building this module: CL came back at 2,560 daily bars against the
    manifest's 5,056; both continuous symbols share every ts_event).
    """
    files = [ARCHIVE / "ohlcv-1d" / f"{root}.dbn.zst"]
    deep = ARCHIVE / "ohlcv-1d" / f"{root}.c2-c4.dbn.zst"
    if root in DEEPER and deep.exists():
        files.append(deep)
    frames = [read_dbn(f) for f in files if f.exists()]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    key = df.index.to_series().astype(str) + "|" + df["symbol"].astype(str)
    df = df[~key.duplicated(keep="first")].sort_index()
    df["date"] = (df.index.tz_convert(None) if df.index.tz is not None
                  else df.index).normalize()
    return df


def load_maturities(root: str) -> dict:
    """instrument_id -> (year, month) from the definition archive."""
    out = {}
    for f in sorted(glob.glob(str(ARCHIVE / "definition" / root / "*.dbn.zst"))):
        d = read_dbn(f, require_symbols=False)
        d = d[d.instrument_class == "F"]
        for iid, y, mo in zip(d.instrument_id, d.maturity_year, d.maturity_month):
            out[int(iid)] = (int(y), int(mo))
    return out


def front_month_series(root: str) -> pd.DataFrame:
    bars = load_bars(root)
    if bars.empty:
        return pd.DataFrame()
    f = bars[bars["symbol"] == f"{root}.c.0"].copy()
    f = f.sort_values("date").drop_duplicates("date", keep="first")
    f = f[["date", "instrument_id", "open", "high", "low", "close", "volume"]]
    f["held_id"] = f["instrument_id"]
    return f.reset_index(drop=True)


def active_cycle_series(root: str) -> pd.DataFrame:
    """GC/SI/HG/ZN/TN: nearest active-cycle contract, held per Amendment C."""
    cyc = CYCLE[root]
    mat = load_maturities(root)
    bars = load_bars(root)
    if bars.empty:
        return pd.DataFrame()
    bars = bars.copy()
    bars["mat"] = bars["instrument_id"].map(lambda i: mat.get(int(i)))
    bars = bars[bars["mat"].notna()]
    sessions = sorted(bars["date"].unique())
    first = {}
    for s in sessions:
        first.setdefault((s.year, s.month), s)
    idx = {s: i for i, s in enumerate(sessions)}

    def held(t):
        y, m = t.year, t.month
        for k in range(0, 30):
            yy, mm = y + (m - 1 + k) // 12, (m - 1 + k) % 12 + 1
            if mm not in cyc:
                continue
            fs = first.get((yy, mm))
            if fs is None:
                return (yy, mm)
            if idx[t] < idx[fs] - 5:
                return (yy, mm)
        return None

    by_day: dict = {}
    for row in bars.itertuples():
        by_day.setdefault(row.date, {})[row.mat] = row

    out_rows = []
    for s in sessions:
        row = by_day.get(s, {}).get(held(s))
        if row is None:
            continue
        out_rows.append(dict(date=s, instrument_id=row.instrument_id,
                              open=row.open, high=row.high, low=row.low,
                              close=row.close, volume=row.volume, held_id=held(s)))
    return pd.DataFrame(out_rows)


def held_series(root: str, kind: str) -> pd.DataFrame:
    return front_month_series(root) if kind == "front" else active_cycle_series(root)


def back_adjust(df: pd.DataFrame) -> pd.DataFrame:
    """Difference-back-adjust a held-contract session frame.

    At each roll (held_id changes between consecutive sessions), the gap is
    the raw close-to-close difference the strategy's own chart shows on
    those two adjacent sessions. Offsets accumulate walking backward from
    the most recent (unadjusted) segment, so the current segment's prices
    are untouched -- the standard "back" in back-adjusted, and the
    registered "difference-back-adjusted" series (REGISTERED_tl_v0 sec 2.1;
    never ratio-adjusted, so CL's April 2020 negative print survives).
    """
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    change = df["held_id"] != df["held_id"].shift(1)
    change.iloc[0] = False
    roll_idx = df.index[change].tolist()
    gaps = [(i, df.loc[i, "close"] - df.loc[i - 1, "close"]) for i in roll_idx]
    adj = np.zeros(len(df))
    for i, gap in reversed(gaps):
        adj[:i] = adj[:i] + gap
    for c in ("open", "high", "low", "close"):
        df[c + "_adj"] = df[c] + adj
    df["adj_offset"] = adj
    df["n_rolls"] = len(roll_idx)
    return df
