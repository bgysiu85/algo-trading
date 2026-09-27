#!/usr/bin/env python3
"""G2 -- W16 session-baselines pre-flight (training side, NO P&L). Board
W16-0003 subitem 3, REGISTERED_w16_session_baselines.md sec 0 (gate G2) and
sec 6.2.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.preflight

WHAT THIS ANSWERS, AND WHY IT NEVER IMPORTS strategy.w16.costs.pnl_dollars
OR .trade_cost: are there enough sessions and entries to read anything, and
what does a stop or an opening range cost in DOLLARS (a point-distance times
strategy.w16.costs.POINT_VALUE -- a risk-sizing conversion, not a booked
profit or loss), before a single trade's P&L exists anywhere. Sec 6.2:
"training side only, no P&L. ... The runner refuses P&L in this mode." This
module's only import from strategy.w16.costs is POINT_VALUE (a fixed $/point
table); it does not import pnl_dollars or trade_cost, so there is no
function in this file *capable* of producing a P&L figure, not merely a flag
that could be flipped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import holdout as H
from strategy.w16 import sessions as S
from strategy.w16 import signals as SIG
from strategy.w16.costs import FULL_TO_MICRO, POINT_VALUE

MIN_TRADES = 300
ROOTS = ("ES", "NQ")
BASELINES = ("B1", "B2", "B3")


def load_root_bars(archive, root: str) -> pd.DataFrame:
    """ES/NQ 1-minute bars, held_id attached, sorted -- reuses G1's own file
    layout (strategy.w16.fetch.bar_path) so pre-flight reads the exact bars
    G1 already validated, nothing re-fetched or re-shaped."""
    from common.dbn_io import read_dbn
    from strategy.w16.fetch import bar_path
    p = bar_path(Path(archive), root, "ohlcv-1m")
    raw = read_dbn(p)
    df = raw[raw["symbol"] == f"{root}.v.0"].copy() if "symbol" in raw.columns else raw.copy()
    if "instrument_id" in df.columns and "held_id" not in df.columns:
        df = df.rename(columns={"instrument_id": "held_id"})
    return df.sort_index()


def session_frames(df_1m: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{date_str: that date's RTH-windowed, sorted bars} for every calendar
    date present in df_1m (early-close-aware via strategy.w16.sessions)."""
    out = {}
    for date_str, day in S.split_by_session(df_1m):
        out[date_str] = day[S.session_window_mask(day, date_str)].sort_index()
    return out


def _pct(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def run_b1(frames: dict[str, pd.DataFrame], market: str, train_dates: set[str]) -> dict:
    counts = {"sessions": 0, "skipped": 0, "no_trigger": 0, "voided": 0, "entries": 0}
    by_year: dict[int, dict] = {}
    micro = FULL_TO_MICRO[market]
    for date_str in sorted(train_dates):
        if date_str not in frames:
            continue
        counts["sessions"] += 1
        res = SIG.orb_session(frames[date_str], date_str, market=market)
        if res["skipped"]:
            counts["skipped"] += 1
            continue
        trade = res["trade"]
        if trade is None:
            counts["no_trigger"] += 1
            continue
        year = int(date_str[:4])
        by_year.setdefault(year, {"range_width_usd": [], "stop_dist_usd": [], "entries": 0, "voided": 0})
        if trade.get("voided"):
            counts["voided"] += 1
            by_year[year]["voided"] += 1
            continue
        counts["entries"] += 1
        by_year[year]["entries"] += 1
        by_year[year]["range_width_usd"].append(res["range_width"] * POINT_VALUE[micro])
        by_year[year]["stop_dist_usd"].append(trade["stop_dist"] * POINT_VALUE[micro])

    per_year = {}
    all_range, all_stop = [], []
    for y, d in sorted(by_year.items()):
        all_range += d["range_width_usd"]
        all_stop += d["stop_dist_usd"]
        per_year[y] = {"entries": d["entries"], "voided": d["voided"],
                       "range_width_usd_median": _pct(d["range_width_usd"], 50),
                       "range_width_usd_p90": _pct(d["range_width_usd"], 90),
                       "stop_dist_usd_median": _pct(d["stop_dist_usd"], 50),
                       "stop_dist_usd_p90": _pct(d["stop_dist_usd"], 90)}
    totals = dict(counts)
    totals["range_width_usd_median"] = _pct(all_range, 50)
    totals["range_width_usd_p90"] = _pct(all_range, 90)
    totals["range_width_usd_max"] = max(all_range) if all_range else None
    totals["stop_dist_usd_median"] = _pct(all_stop, 50)
    totals["stop_dist_usd_p90"] = _pct(all_stop, 90)
    totals["stop_dist_usd_max"] = max(all_stop) if all_stop else None
    totals["underpowered"] = counts["entries"] < MIN_TRADES
    return {"per_year": per_year, "totals": totals}


def run_b2(frames: dict[str, pd.DataFrame], market: str, train_days: list[str]) -> dict:
    counts = {"pairs": 0, "skipped": 0, "voided_roll": 0, "entries": 0}
    by_year: dict[int, dict] = {}
    for a, b in zip(train_days, train_days[1:]):
        if a not in frames or b not in frames:
            counts["skipped"] += 1
            continue
        counts["pairs"] += 1
        res = SIG.overnight_trade(frames[a], frames[b], a, b, market=market)
        if res["skipped"]:
            counts["skipped"] += 1
            continue
        year = int(a[:4])
        by_year.setdefault(year, {"entries": 0, "voided": 0})
        if res["trade"]["voided"]:
            counts["voided_roll"] += 1
            by_year[year]["voided"] += 1
            continue
        counts["entries"] += 1
        by_year[year]["entries"] += 1
    per_year = {y: dict(d) for y, d in sorted(by_year.items())}
    totals = dict(counts)
    totals["underpowered"] = counts["entries"] < MIN_TRADES
    return {"per_year": per_year, "totals": totals}


def run_b3(frames: dict[str, pd.DataFrame], market: str, train_dates: set[str]) -> dict:
    counts = {"sessions": 0, "skipped": 0, "entries": 0, "voided": 0}
    by_year: dict[int, dict] = {}
    flips_per_day = []
    for date_str in sorted(train_dates):
        if date_str not in frames:
            continue
        counts["sessions"] += 1
        res = SIG.vwap_flip_session(frames[date_str], date_str, market=market)
        if res["skipped"]:
            counts["skipped"] += 1
            continue
        flips_per_day.append(res["n_flips"])
        trades = SIG.pair_b3_legs(res["legs"])
        year = int(date_str[:4])
        by_year.setdefault(year, {"entries": 0, "voided": 0})
        for tr in trades:
            if tr.get("voided"):
                counts["voided"] += 1
                by_year[year]["voided"] += 1
            else:
                counts["entries"] += 1
                by_year[year]["entries"] += 1
    per_year = {y: dict(d) for y, d in sorted(by_year.items())}
    totals = dict(counts)
    totals["flips_per_day_median"] = _pct(flips_per_day, 50)
    totals["flips_per_day_p90"] = _pct(flips_per_day, 90)
    totals["flips_per_day_max"] = max(flips_per_day) if flips_per_day else None
    totals["underpowered"] = counts["entries"] < MIN_TRADES
    return {"per_year": per_year, "totals": totals}


def run(archive) -> dict:
    report: dict = {"baselines": {}}
    for market in ROOTS:
        df_1m = load_root_bars(archive, market)
        frames = session_frames(df_1m)
        all_dates = sorted(frames.keys())
        train_dates, n_locked, _ = H.split_dates(all_dates)
        train_dates_set = set(train_dates)
        report["baselines"].setdefault("B1", {})[market] = run_b1(frames, market, train_dates_set)
        report["baselines"].setdefault("B2", {})[market] = run_b2(frames, market, train_dates)
        report["baselines"].setdefault("B3", {})[market] = run_b3(frames, market, train_dates_set)
    underpowered = {f"{b}-{m}": report["baselines"][b][m]["totals"]["underpowered"]
                    for b in BASELINES for m in ROOTS}
    report["underpowered_cells"] = underpowered
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G2: W16 session-baselines pre-flight (no P&L).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run(archive)
    print("G2 -- W16 session-baselines pre-flight (training side, no P&L)\n")
    for b in BASELINES:
        for m in ROOTS:
            t = report["baselines"][b][m]["totals"]
            flag = " [<300, NOT READ]" if t["underpowered"] else ""
            print(f"{b:3s} {m:2s}  entries={t.get('entries', 0):5d}{flag}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
