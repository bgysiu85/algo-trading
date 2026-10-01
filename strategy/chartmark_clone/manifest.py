#!/usr/bin/env python3
"""Candidate manifest: the 2,670 CHARTMARK-v1 long fills, each with the buy-stop level working at the decision bar.
REGISTERED_chartmark_clone.md sec 3.1, gates G2.

The manifest is built by RE-RUNNING the v1 engine, never by reading the trades CSV's outcome columns. The CSV is opened
for exactly one purpose -- to check the fill timestamps -- and only its `entry_t` column is read (read_entry_times)."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.chartmark import engine as E
from strategy.chartmark import spec as V1
from strategy.chartmark.data import Frame, Ind
from strategy.chartmark_clone import daily as DL
from strategy.chartmark_clone import spec as S

TS_FMT = "%Y-%m-%d %H:%M:%S"


class ManifestError(RuntimeError):
    pass


def read_entry_times(path: Path) -> list[str]:
    """The ONLY read of the v1 trades file: the `entry_t` column, nothing else."""
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh), None)
    if not header or "entry_t" not in header:
        raise ManifestError(f"{path}: no entry_t column")
    df = pd.read_csv(path, usecols=["entry_t"], dtype=str)
    return [str(x) for x in df["entry_t"].tolist()]


def fill_level(fr: Frame, trade, p: V1.Params) -> float:
    """The buy-stop level working for the fill bar, as the engine's order state held it at the close of the decision bar:
    the order is placed at placed_j and re-set at each later close, and can only rise (E2)."""
    e, j0 = trade.entry_j, trade.placed_j
    if j0 < 0 or j0 > e - 1:
        raise ManifestError(f"fill at bar {e} has no placed bar ({j0})")
    lv = -np.inf
    for s in range(j0, e):
        lv = max(lv, E._hh(fr.h, s, p.e1_lookback) + V1.TICK)
    return float(lv)


def build_manifest(fr: Frame, ind: Ind, trades: list, p: V1.Params = V1.BASE) -> tuple[pd.DataFrame, dict]:
    """One row per fill. Proves I2 for every fill; returns (frame, info)."""
    d = DL.build_daily(fr)
    ny = fr.ny
    rows = []
    warm = 0
    for tr in trades:
        e = tr.entry_j
        lvl = fill_level(fr, tr, p)
        if not (fr.h[e] >= lvl - 1e-9 and abs(max(lvl, fr.o[e]) - tr.entry_px) <= 1e-9):
            raise ManifestError(
                f"level check failed at fill bar {e}: level {lvl!r}, open {fr.o[e]!r}, high {fr.h[e]!r}, engine fill "
                f"{tr.entry_px!r} -- the reconstructed order level is not the engine's; stop, do not label.")
        t = e - 1
        warm += int(DL.f1_is_warmup(d, t))
        rows.append(dict(candidate_id=ny[e].tz_localize(None).strftime(TS_FMT),
                         decision_t=ny[t].tz_localize(None).strftime(TS_FMT), decision_idx=t, level=lvl,
                         year=int(ny[e].year), daily_trend=DL.f1_daily_trend(d, t)))
    m = pd.DataFrame(rows, columns=S.MANIFEST_COLUMNS)
    if m["candidate_id"].duplicated().any():
        raise ManifestError("duplicate candidate ids")
    info = dict(n=len(m), per_year={int(k): int(v) for k, v in sorted(Counter(m["year"]).items())},
                f1_warmup=warm, up=int((m["daily_trend"] == 1).sum()), down=int((m["daily_trend"] == -1).sum()))
    return m, info


def check_against_trades_csv(m: pd.DataFrame, csv_times: list[str]) -> None:
    """G2: the manifest holds exactly the fill timestamps of the v1 trades file (join on timestamp; mismatch = stop)."""
    a, b = set(m["candidate_id"]), set(csv_times)
    if len(csv_times) != len(b):
        raise ManifestError("duplicate entry_t values in the trades file")
    if a != b:
        only_m, only_c = sorted(a - b)[:5], sorted(b - a)[:5]
        raise ManifestError(f"manifest and trades file disagree: {len(a - b)} only in manifest (e.g. {only_m}), "
                            f"{len(b - a)} only in trades file (e.g. {only_c}) -- stop.")


def check_registered_counts(info: dict) -> None:
    if info["n"] != S.POOL_N or info["per_year"] != S.POOL_PER_YEAR:
        raise ManifestError(f"pool is {info['n']} fills {info['per_year']}; registered {S.POOL_N} {S.POOL_PER_YEAR} -- stop.")


def simulate_pool(fr: Frame, ind: Ind, p: V1.Params = V1.BASE) -> list:
    trades, _ = E.simulate(fr, ind, p)
    return trades
