#!/usr/bin/env python3
"""Read the TSMOM archive (E:\\Databento\\GLBX.MDP3) into engine inputs.

Read-only. Never downloads; `common/tsmom_fetch.py` is the only module that can
spend money and nothing here imports it.

FOUR THINGS ABOUT THIS ARCHIVE THAT CHANGE RESULTS IF MISSED
-------------------------------------------------------------
1. THE DAILY BARS ARE UTC DAYS, NOT CME SESSIONS. ts_event is 00:00 UTC and a
   bar spans midnight to midnight UTC, so its close is the price at ~19:00/20:00
   ET in the evening session, not the settlement. And there is a bar stamped
   SUNDAY on most weeks (1,659 of them for ES): the first hour of Monday's
   Globex session, 17:00 CT Sunday to 00:00 UTC. Counted as a session it would
   add ~50 "trading days" a year, move every "five sessions before expiry" and
   inflate the 261-a-year annualisation's denominator. Sunday rows are DROPPED
   and the count is reported. Dropping them is exact for close-to-close
   returns: a close is a point in time, and removing an intermediate point
   leaves Friday-close to Monday-close intact. Found 2026-09-20, before any
   return was computed.

2. RAW SYMBOLS REPEAT EVERY DECADE. GCZ0 is December 2010 AND December 2020.
   The contract key here is `<raw_symbol>_<maturity_year>`.

3. INSTRUMENT IDS CAN BE REUSED. A bar's instrument_id is mapped to the
   contract carrying that id whose expiration is on or after the bar's date
   (the earliest such). Anything left over is reported as unmapped.

4. TWO PULLS, TWO END DATES. The first pull's bar files end 2026-09-17 and the
   top-up's (metals c.2-c.4, TN, MTN) 2026-09-18. Both are inside the locked
   holdout; the training side never sees the seam.

The dataset is READ from the manifest and anything but the registered one is
refused (REGISTERED_tsmom section 8).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.tsmom.engine import RootInputs
from strategy.tsmom.registry import ALL_ROOTS, DATASET

DEFAULT_ARCHIVE = Path(r"E:\Databento\GLBX.MDP3")
RATES_FACE_ROOTS = {"ZN", "TN"}   # unit_of_measure_qty is face value; point value = face/100


class ArchiveRefused(SystemExit):
    pass


def read_manifest(archive: Path) -> dict:
    p = Path(archive) / "manifest_tsmom.json"
    if not p.exists():
        raise ArchiveRefused(f"no manifest at {p}: an archive that cannot say what "
                             "it is is not read")
    m = json.loads(p.read_text(encoding="utf-8"))
    if m.get("dataset") != DATASET:
        raise ArchiveRefused(f"manifest dataset is {m.get('dataset')!r}; TSMOM is "
                             f"registered on {DATASET!r} only")
    return m


def _dbn_df(path: Path) -> pd.DataFrame:
    import databento as db            # imported here so the engine and its tests need no databento
    # from_file leaves the handle open (a ResourceWarning per file, ~2,500 of
    # them over the calendar); read the bytes and close the file here.
    with open(path, "rb") as fh:
        data = fh.read()
    return db.DBNStore.from_bytes(data).to_df()


def load_bars(archive: Path, root: str) -> tuple[pd.DataFrame, dict]:
    """All bar rows for a root (c.0..c.4), Sundays dropped. Returns the rows
    (date, instrument_id, close, volume, rank) and a note of what was dropped."""
    files = [Path(archive) / "ohlcv-1d" / f"{root}.dbn.zst"]
    extra = Path(archive) / "ohlcv-1d" / f"{root}.c2-c4.dbn.zst"
    if extra.exists():
        files.append(extra)
    frames = []
    for f in files:
        if not f.exists():
            raise ArchiveRefused(f"missing bar file {f}")
        d = _dbn_df(f).reset_index()
        frames.append(d)
    b = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(b["ts_event"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    if (ts != ts.dt.normalize()).any():
        raise ArchiveRefused(f"{root}: a daily bar not stamped at 00:00 UTC")
    b["date"] = ts.dt.normalize()
    b["rank"] = b["symbol"].str.extract(r"\.c\.(\d+)$")[0].astype(int)
    dow = b["date"].dt.dayofweek
    note = {"sunday_rows_dropped": int((dow == 6).sum()),
            "saturday_rows_dropped": int((dow == 5).sum()),
            "files": [f.name for f in files]}
    b = b[dow < 5]
    b = b[["date", "instrument_id", "close", "volume", "rank"]]
    dup = b.duplicated(["date", "instrument_id"], keep=False)
    if dup.any():
        d = b[dup].groupby(["date", "instrument_id"])["close"].nunique()
        if (d > 1).any():
            raise ArchiveRefused(f"{root}: one contract with two closes on one date:\n"
                                 f"{d[d > 1].head()}")
        b = b.drop_duplicates(["date", "instrument_id"])
    return b.sort_values(["date", "rank"]).reset_index(drop=True), note


def load_definitions(archive: Path, root: str) -> tuple[pd.DataFrame, list[str]]:
    """Every outright future seen in any monthly snapshot, one row per contract,
    and the list of expiration REVISIONS found.

    AN EXPIRATION CAN CHANGE AFTER LISTING. 6EM3 carried 2023-06-19 in every
    snapshot until 2021-12 and 2023-06-16 from 2022-01: Juneteenth became an
    exchange holiday and the last trading day moved. The value used is the one
    in the LATEST snapshot that lists the contract -- the one in force when it
    expired -- and every revision is reported, not absorbed. (Found by this
    loader's own refusal on the first real read, 2026-09-20.)
    """
    ddir = Path(archive) / "definition" / root
    files = sorted(ddir.glob("*.dbn.zst"))
    if not files:
        raise ArchiveRefused(f"no definition snapshots in {ddir}")
    keep = ["instrument_id", "raw_symbol", "expiration", "maturity_year",
            "maturity_month", "unit_of_measure_qty", "min_price_increment"]
    rows = []
    for f in files:
        d = _dbn_df(f)
        d = d[d["instrument_class"] == "F"][keep].copy()
        d["snapshot"] = f.name[:10]
        rows.append(d)
    c = pd.concat(rows, ignore_index=True)
    exp = pd.to_datetime(c["expiration"])
    if exp.dt.tz is not None:
        exp = exp.dt.tz_convert("UTC").dt.tz_localize(None)
    c["expiration"] = exp.dt.normalize()
    c["symbol"] = c["raw_symbol"] + "_" + c["maturity_year"].astype(int).astype(str)
    c = c.rename(columns={"maturity_year": "year", "maturity_month": "month"})
    revisions = []
    for sym, g in c.groupby("symbol"):
        if g["expiration"].nunique() > 1:
            seq = g.sort_values("snapshot").drop_duplicates("expiration")
            revisions.append(f"{sym}: " + " -> ".join(
                f"{e.date()} (from {s})" for e, s in zip(seq["expiration"], seq["snapshot"])))
    c = c.sort_values("snapshot").drop_duplicates(["symbol", "instrument_id"], keep="last")
    latest = c.groupby("symbol")["expiration"].transform("last")
    c["expiration"] = latest
    return c.drop(columns="snapshot").sort_values("expiration").reset_index(drop=True), revisions


def map_ids(bars: pd.DataFrame, contracts: pd.DataFrame) -> pd.Series:
    """Contract key for each bar row: the contract with this instrument_id whose
    expiration is on or after the bar's date. NaN = unmapped."""
    out = pd.Series(np.nan, index=bars.index, dtype=object)
    by_id = {k: g.sort_values("expiration") for k, g in contracts.groupby("instrument_id")}
    for iid, g in bars.groupby("instrument_id"):
        cands = by_id.get(iid)
        if cands is None:
            continue
        pos = np.searchsorted(cands["expiration"].values, g["date"].values, side="left")
        ok = pos < len(cands)
        sym = np.full(len(g), np.nan, dtype=object)
        sym[ok] = cands["symbol"].values[pos[ok]]
        out.loc[g.index] = sym
    return out


def point_value_check(root: str, contracts: pd.DataFrame) -> list[str]:
    """The registry's full-size point value against the definition's
    unit_of_measure_qty (face value / 100 for the rates contracts)."""
    reg = ALL_ROOTS[root].point_value
    q = contracts["unit_of_measure_qty"].dropna()
    q = q[q > 0].unique()          # some old snapshots carry 0 = not populated
    if len(q) == 0:
        return [f"{root}: no populated unit_of_measure_qty to check against"]
    implied = q / 100.0 if root in RATES_FACE_ROOTS else q
    return [f"{root}: registry point value {reg} vs definition {v}"
            for v in implied if not np.isclose(v, reg)]


def load_root(archive: Path, root: str) -> tuple[RootInputs, pd.Series, dict]:
    """Engine inputs for one root, plus the c.0 contract per session (for the
    AT-41 cross-check) and a load report."""
    bars, note = load_bars(archive, root)
    con, revisions = load_definitions(archive, root)
    bars["symbol"] = map_ids(bars, con)
    unmapped = int(bars["symbol"].isna().sum())
    note.update({"bar_rows": len(bars), "unmapped_rows": unmapped,
                 "unmapped_pct": 100.0 * unmapped / max(len(bars), 1),
                 "point_value_mismatch": point_value_check(root, con),
                 "expiration_revisions": revisions})
    b = bars.dropna(subset=["symbol"])
    prices = b.pivot(index="date", columns="symbol", values="close").sort_index()
    volumes = b.pivot(index="date", columns="symbol", values="volume").sort_index()
    c0 = b[b["rank"] == 0].set_index("date")["symbol"].sort_index()
    contracts = con[["symbol", "expiration", "year", "month", "instrument_id",
                     "unit_of_measure_qty"]].drop_duplicates("symbol")
    return RootInputs(contracts, prices, volumes), c0, note


def load_all(archive: Path = DEFAULT_ARCHIVE, roots=None):
    read_manifest(archive)
    roots = list(roots or ALL_ROOTS)
    return {r: load_root(archive, r) for r in roots}
