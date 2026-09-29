#!/usr/bin/env python3
"""BB-v0 backtest runner: G2 pre-flight (no P&L, incl. the sec 3.3 TMB
HP>50 calibration check), the six scored cells (ABD-NQ, SSS-NQ, TMB-NQ,
CRT-NQ, NRS-ES, NRS-NQ) at L1/L2/L3, sec 9's nine criteria at the 99%
bootstrap bar, the C-A1/C-S1/C-T1/C-C1/C-N1 controls (scored) plus
C-C2/C-N2/C-T2 (reported), the sec 7.3 neighbour grids, the sec 7.4
source-claims block, the worked-example checks, and full sec 4 reporting.
Board W16-0008 subitem 3. docs/research/REGISTERED_w16_bar_batch.md.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.bb_runner --preflight --out "D:\\Trading\\Claude outputs\\w16_0008_preflight.json"
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.bb_runner --backtest --skip-controls --skip-grid   # fast sanity pass
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.bb_runner --backtest --out "D:\\Trading\\Claude outputs\\w16_0008_backtest.json"

WHY THIS REUSES strategy.w16.runner.score_cell UNCHANGED (unlike
strategy.w16.dvp_runner's own dvp_score_cell)
------------------------------------------------------------------------
sec 9 #4: "Bootstrap by calendar month ... net > 0 in >= 99% ... raised
from 95% because six cells are scored." That IS runner.py's own
BOOTSTRAP_PASS_PCT (0.99, "raised from 95% for 6 scored cells") -- the
SAME multiplicity correction, for the SAME reason (six scored cells), not
a coincidence to re-derive. sec 9 #5 also wants a single p95 test per cell
(no B2-style AND condition), which is exactly what `score_cell` does when
`control_deterministic` is left at its default None. So `run_cell` below
calls `strategy.w16.runner.score_cell` directly, unmodified.

WHAT IS BUILT HERE
------------------------------------------------------------------------
Trade generation for all five rules (strategy.w16.bar_batch), cost/P&L at
L1/L2/L3 (strategy.w16.runner.price_all/summarize, reused unchanged), the
five sec 7.1 scored controls (C-A1/C-S1/C-T1/C-C1/C-N1) run for real at
N_CONTROL_DRAWS, three sec 7.2 reported controls (C-C2/C-N2/C-T2), the
sec 7.3 neighbour grids (9 cells per scored cell), a handful of sec 3.x
reported variants (ES for all four day-session rules, TMB's mirrored
short), the sec 7.4 source-claims block, the sec 6.1 pre-flight (incl.
the ONE calibration this registration allows: the TMB HP>50 share), and
the worked-example checks sec 7.4 asks the build to reproduce.

NOT BUILT (disclosed, not guessed at -- nothing in sec 9 depends on any
of these; see strategy.w16.bar_batch's own module docstring for the
trade-generation side of this same list): touch fills, CRT re-break
entry, NRS 5-candle/day-session/squeeze-bar-stop readings, SSS prior-
day-red filter, each CRT timeframe alone, CRT Mondays-included, ABD's
band-touches-vs-trade-through breakdown in the pre-flight. C-N2's fill
point differs from the real trade's own hour by construction (a later,
random minute); its ATR is recomputed at the hour the RANDOM fill lands
in, not carried over from the real squeeze bar -- documented at
`_c_n2_draw`, not silently assumed to match C-N1's convention.
"""
from __future__ import annotations

import argparse
import json
import time as _time
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import bar_batch as B
from strategy.w16 import bb_holdout as H
from strategy.w16 import controls as CTRL
from strategy.w16 import runner as R
from strategy.w16.costs import FULL_TO_MICRO, OVERNIGHT_MARGIN, POINT_VALUE
from strategy.w16.preflight import load_root_bars, session_frames
from strategy.w16.sessions import is_xnys_trading_day

LEVELS = R.LEVELS                        # ("L1", "L2", "L3")
SCORE_LEVEL = "L2"
MIN_TRADES = R.MIN_TRADES                # 300 -- same constant as SB-v0/DVP-v0
BOOTSTRAP_PASS_PCT = R.BOOTSTRAP_PASS_PCT  # 0.99 -- see module docstring: this IS sec 9 #4's own bar
N_CONTROL_DRAWS = CTRL.N_DRAWS            # 1000 (sec 7.1)
ACCOUNT_USD = R.ACCOUNT_USD

DAY_SESSION_RULES = ("ABD", "SSS", "TMB", "CRT")   # 09:30-16:00, flat 15:55
SCORED_DAY_MARKET = "NQ"
REPORTED_DAY_MARKET = "ES"
NRS_MARKETS = ("ES", "NQ")

SCORED_CELLS = ("ABD-NQ", "SSS-NQ", "TMB-NQ", "CRT-NQ", "NRS-ES", "NRS-NQ")

# sec 7.3 neighbour grids -- registered value bolded in the spec is the
# MIDDLE of each triple below, kept that way on purpose so grid[1] is
# always the registered cell.
GRID_ABD_ATR_MULT = (2.6, 3.1, 3.6)
GRID_ABD_SCALE = (0.75, 1.00, 1.25)          # applied to target_mult=2.0 AND stop_mult=1.5 together
GRID_SSS_WICK_MULT = (1.5, 2.0, 3.0)
GRID_SSS_HOLD_BARS = (1, 2, 3)
GRID_TMB_HP = (45.0, 50.0, 55.0)
GRID_TMB_AC = (-0.05, -0.10, -0.15)
GRID_CRT_RR = (1.2, 1.5, 1.8)
GRID_CRT_WINDOW_END = (dtime(11, 0), dtime(12, 0), dtime(13, 0))
GRID_NRS_CHANDELIER = (2.0, 3.0, 4.0)
GRID_NRS_SQUEEZE_LEN = (3, 4, 5)

# sec 7.4's worked examples: guards against the harness itself, not the
# rule passing/failing. ABD's is checked directly (arithmetic, no bars
# needed); TMB's HP/AC are structure-only (sec 7.4: "as structure only")
# and are exercised by tests/strategy/w16/test_bar_batch.py instead.
ABD_WORKED_ATR = 17.85
ABD_WORKED_TARGET_DIST = 35.75
ABD_WORKED_STOP_DIST = 26.75


# ---------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------

def trading_dates(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Sorted XNYS trading-day dates present in `frames` -- rules A-D's
    own calendar. Mirrors dvp_runner.trading_dates exactly (same reason:
    the ET-date grouping of the Globex archive also yields Sundays and
    exchange holidays)."""
    return [d for d in sorted(frames.keys()) if is_xnys_trading_day(d)]


def worked_example_check() -> dict:
    """sec 7.4: ABD's worked example (ATR 17.85 -> target 35.75 pts, stop
    26.75 pts), reproduced directly against the same rounding helper the
    real rule uses (round_distance_tick), so a harness bug in that helper
    trips this before it ever reaches a real trade."""
    atr = ABD_WORKED_ATR
    target_dist = B.round_distance_tick(2.0 * atr)
    stop_dist = B.round_distance_tick(1.5 * atr)
    return {
        "atr": atr,
        "computed_target_dist": target_dist, "expected_target_dist": ABD_WORKED_TARGET_DIST,
        "computed_stop_dist": stop_dist, "expected_stop_dist": ABD_WORKED_STOP_DIST,
        "target_ok": abs(target_dist - ABD_WORKED_TARGET_DIST) < 1e-9,
        "stop_ok": abs(stop_dist - ABD_WORKED_STOP_DIST) < 1e-9,
    }


# ---------------------------------------------------------------------
# pre-flight (G2, no P&L) -- sec 6.1
# ---------------------------------------------------------------------

def _pct(values, q: float):
    values = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.percentile(values, q)) if values else None


def _preflight_abd(frames, market, dates) -> dict:
    trades = B.generate_abd_trades(frames, market, dates)
    by_year: dict[int, dict] = {}
    stop_usd, target_usd = [], []
    micro = FULL_TO_MICRO[market]
    n_voided = 0
    for t in trades:
        y = int(t["date"][:4])
        by_year.setdefault(y, {"entries": 0, "voided": 0})
        if t.get("voided"):
            n_voided += 1
            by_year[y]["voided"] += 1
            continue
        by_year[y]["entries"] += 1
        stop_usd.append(t["stop_dist"] * POINT_VALUE[micro])
        target_usd.append(t["target_dist"] * POINT_VALUE[micro])
    n_entries = sum(v["entries"] for v in by_year.values())
    return {
        "n_sessions": len(dates), "n_entries": n_entries, "n_voided": n_voided,
        "by_year": {y: dict(v) for y, v in sorted(by_year.items())},
        "stop_dist_usd": {"median": _pct(stop_usd, 50), "p90": _pct(stop_usd, 90),
                          "max": max(stop_usd) if stop_usd else None},
        "target_dist_usd": {"median": _pct(target_usd, 50), "p90": _pct(target_usd, 90),
                            "max": max(target_usd) if target_usd else None},
        "underpowered_below_300": n_entries < MIN_TRADES,
    }


def _preflight_sss(frames, market, dates) -> dict:
    trades = B.generate_sss_trades(frames, market, dates)
    by_year: dict[int, dict] = {}
    n_voided = 0
    ranges_usd = []
    micro = FULL_TO_MICRO[market]
    for date_str in dates:
        day = frames.get(date_str)
        if day is None or day.empty:
            continue
        bars5 = B.resample_session_bars(day, 5)
        if not bars5.empty:
            rng = (bars5["high"] - bars5["low"]).median()
            if np.isfinite(rng):
                ranges_usd.append(float(rng) * POINT_VALUE[micro])
    for t in trades:
        y = int(t["date"][:4])
        by_year.setdefault(y, {"entries": 0, "voided": 0})
        if t.get("voided"):
            n_voided += 1
            by_year[y]["voided"] += 1
        else:
            by_year[y]["entries"] += 1
    n_entries = sum(v["entries"] for v in by_year.values())
    return {
        "n_sessions": len(dates), "n_entries": n_entries, "n_voided": n_voided,
        "patterns_per_day": (len(trades) / len(dates)) if dates else None,
        "by_year": {y: dict(v) for y, v in sorted(by_year.items())},
        "median_5min_bar_range_usd": _pct(ranges_usd, 50),
        "underpowered_below_300": n_entries < MIN_TRADES,
    }


def _preflight_tmb(frames, market, dates) -> dict:
    bars15 = B.build_day_session_series(frames, dates, 15)
    hp_share_over_50 = ac_share_le_neg10 = None
    hp_pctiles = ac_pctiles = {}
    if not bars15.empty:
        held = B._held_id(bars15)
        atr20 = B.wilder_atr(bars15, 20, held_id=held)
        returns = B.log_returns_roll_aware(bars15, held_id=held)
        hp = B.hurst_proxy(bars15, atr20)
        ac = B.autocorr_lag5(returns)
        hp_valid = hp[np.isfinite(hp)]
        ac_valid = ac[np.isfinite(ac)]
        if len(hp_valid):
            hp_share_over_50 = float((hp_valid > 50.0).mean())
            hp_pctiles = {q: _pct(hp_valid.tolist(), q) for q in (5, 25, 50, 75, 95)}
        if len(ac_valid):
            ac_share_le_neg10 = float((ac_valid <= -0.10).mean())
            ac_pctiles = {q: _pct(ac_valid.tolist(), q) for q in (5, 25, 50, 75, 95)}

    trades = B.generate_tmb_trades(frames, market, dates)
    by_year: dict[int, dict] = {}
    n_voided = 0
    for t in trades:
        y = int(t["date"][:4])
        by_year.setdefault(y, {"entries": 0, "voided": 0})
        if t.get("voided"):
            n_voided += 1
            by_year[y]["voided"] += 1
        else:
            by_year[y]["entries"] += 1
    n_entries = sum(v["entries"] for v in by_year.values())
    return {
        "n_sessions": len(dates), "n_entries": n_entries, "n_voided": n_voided,
        "by_year": {y: dict(v) for y, v in sorted(by_year.items())},
        "hp_pctiles": hp_pctiles, "ac_pctiles": ac_pctiles,
        "hp_over_50_share": hp_share_over_50,          # <-- sec 3.3 calibration check
        "ac_le_neg_0p10_share": ac_share_le_neg10,
        "calibration_amendment_needed": (hp_share_over_50 is not None and
                                         not (0.10 <= hp_share_over_50 <= 0.90)),
        "underpowered_below_300": n_entries < MIN_TRADES,
    }


def _preflight_crt(frames, market, dates) -> dict:
    trades = B.generate_crt_trades(frames, market, dates)
    by_year: dict[int, dict] = {}
    n_voided = n_no_trade_days = 0
    reward_usd = []
    stop_le_4_ticks = 0
    micro = FULL_TO_MICRO[market]
    traded_dates = {t["date"] for t in trades}
    n_candidate_days = len([d for d in dates if pd.Timestamp(d).dayofweek != 0])
    n_no_trade_days = n_candidate_days - len(traded_dates)
    for t in trades:
        y = int(t["date"][:4])
        by_year.setdefault(y, {"entries": 0, "voided": 0})
        if t.get("voided"):
            n_voided += 1
            by_year[y]["voided"] += 1
            continue
        by_year[y]["entries"] += 1
        reward_usd.append(t["reward"] * POINT_VALUE[micro])
        if t["stop_dist"] <= 4 * B.TICK:
            stop_le_4_ticks += 1
    n_entries = sum(v["entries"] for v in by_year.values())
    return {
        "n_candidate_sessions": n_candidate_days, "n_entries": n_entries, "n_voided": n_voided,
        "n_no_trade_days": n_no_trade_days,
        "by_year": {y: dict(v) for y, v in sorted(by_year.items())},
        "reward_usd": {"median": _pct(reward_usd, 50), "p10": _pct(reward_usd, 10),
                      "p90": _pct(reward_usd, 90)},
        "share_stop_le_4_ticks": (stop_le_4_ticks / n_entries) if n_entries else None,
        "underpowered_below_300": n_entries < MIN_TRADES,
    }


def _preflight_nrs(df_1m_full, market, cme_train_days) -> dict:
    pre = B._nrs_precompute(df_1m_full)
    trades = B.generate_nrs_trades(df_1m_full, market, cme_train_days, _pre=pre)
    by_year: dict[int, dict] = {}
    n_voided = 0
    stop_usd = []
    day_fills = overnight_fills = 0
    micro = FULL_TO_MICRO[market]
    squeeze_bars_total = int(np.sum(pre["h_ranges"] >= 0)) if pre else 0   # placeholder count; see note below
    for t in trades:
        y = int(t["date"][:4])
        by_year.setdefault(y, {"entries": 0, "voided": 0})
        if t.get("voided"):
            n_voided += 1
            by_year[y]["voided"] += 1
            continue
        by_year[y]["entries"] += 1
        fill_hour = pd.Timestamp(t["fill_time"]).hour
        if 9 <= fill_hour < 16:
            day_fills += 1
        else:
            overnight_fills += 1
        a0 = pre["h_atr"][pd.Index(pre["h_start_vals"]).get_indexer(
            [np.datetime64(t["squeeze_bar_time"])])[0]] if pre else None
        if a0 is not None and np.isfinite(a0):
            stop_usd.append(3.0 * float(a0) * POINT_VALUE[micro])
    n_entries = sum(v["entries"] for v in by_year.values())
    n_fills = day_fills + overnight_fills
    return {
        "n_cme_days": len(cme_train_days), "n_entries": n_entries, "n_voided": n_voided,
        "by_year": {y: dict(v) for y, v in sorted(by_year.items())},
        "share_fills_day_session": (day_fills / n_fills) if n_fills else None,
        "share_fills_overnight": (overnight_fills / n_fills) if n_fills else None,
        "initial_stop_usd": {"median": _pct(stop_usd, 50), "p90": _pct(stop_usd, 90),
                             "max": max(stop_usd) if stop_usd else None},
        "underpowered_below_300": n_entries < MIN_TRADES,
    }


def run_preflight(archive) -> dict:
    report: dict = {"cells": {}, "worked_example": worked_example_check()}
    for market in ("NQ", "ES"):
        df_1m = load_root_bars(archive, market)
        frames = session_frames(df_1m)
        day_dates = trading_dates(frames)
        report["cells"][f"ABD-{market}"] = _preflight_abd(frames, market, day_dates)
        report["cells"][f"SSS-{market}"] = _preflight_sss(frames, market, day_dates)
        report["cells"][f"TMB-{market}"] = _preflight_tmb(frames, market, day_dates)
        report["cells"][f"CRT-{market}"] = _preflight_crt(frames, market, day_dates)
        cme_days = B.nrs_cme_trading_days(df_1m)
        train_days, _, _ = H.split_dates(cme_days)
        report["cells"][f"NRS-{market}"] = _preflight_nrs(df_1m, market, train_days)
    report["underpowered_scored_cells"] = {
        c: report["cells"][c]["underpowered_below_300"] for c in SCORED_CELLS}
    return report


def _print_preflight_summary(report: dict) -> None:
    print("G2 -- W16 BB-v0 pre-flight (training side, no P&L)\n")
    we = report["worked_example"]
    print(f"worked example (ABD, sec 7.4): target_dist {we['computed_target_dist']} "
         f"(expect {we['expected_target_dist']}) ok={we['target_ok']}  "
         f"stop_dist {we['computed_stop_dist']} (expect {we['expected_stop_dist']}) ok={we['stop_ok']}")
    for cell, c in report["cells"].items():
        flag = " [<300, NOT READ]" if c["underpowered_below_300"] else ""
        print(f"{cell:8s}  entries={c['n_entries']:5d}  voided={c['n_voided']:4d}{flag}")
        if cell.startswith("TMB"):
            print(f"    HP>50 share={c['hp_over_50_share']}  "
                 f"AC<=-0.10 share={c['ac_le_neg_0p10_share']}  "
                 f"calibration amendment needed={c['calibration_amendment_needed']}")


# ---------------------------------------------------------------------
# trade generation dispatch, one call per (rule, market)
# ---------------------------------------------------------------------

def _generate(rule: str, frames_or_df1m, market: str, dates, **kwargs) -> list[dict]:
    if rule == "ABD":
        return B.generate_abd_trades(frames_or_df1m, market, dates, **kwargs)
    if rule == "SSS":
        return B.generate_sss_trades(frames_or_df1m, market, dates, **kwargs)
    if rule == "TMB":
        return B.generate_tmb_trades(frames_or_df1m, market, dates, **kwargs)
    if rule == "CRT":
        return B.generate_crt_trades(frames_or_df1m, market, dates, **kwargs)
    if rule == "NRS":
        return B.generate_nrs_trades(frames_or_df1m, market, dates, **kwargs)
    raise ValueError(f"unknown rule {rule!r}")


# ---------------------------------------------------------------------
# controls -- sec 7.1 (scored) and sec 7.2 (reported)
# ---------------------------------------------------------------------

def _abd_precompute(frames, dates) -> dict:
    bars5 = B.build_day_session_series(frames, dates, 5)
    held = B._held_id(bars5)
    atr5 = B.wilder_atr(bars5, 14, held_id=held)
    return {"bars5": bars5, "atr5": atr5, "b5_start": bars5.index.values}


def c_a1_draw(real_trades, frames, pre, draw_idx: int) -> list[dict]:
    """sec 7.1 C-A1: long at a uniformly random 1-min bar's open, 09:35-
    15:54, using the 5-min ATR(14) of the last COMPLETED 5-min bar before
    the fill (its window [start, start+5m) has fully elapsed by the fill
    minute -- NOT the bar the fill minute itself falls in). Market entry
    (costed as market_or_stop, unlike ABD's own limit entries)."""
    rng = CTRL.draw_rng(draw_idx)
    b5_start, atr5 = pre["b5_start"], pre["atr5"]
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        day1m = day1m.sort_index()
        naive1m = B._naive_et(day1m)
        t = naive1m.time
        candidates = np.where((t >= dtime(9, 35)) & (t <= dtime(15, 54)))[0]
        if len(candidates) == 0:
            continue
        fill_idx = int(candidates[int(rng.integers(0, len(candidates)))])
        fill_ts = day1m.index[fill_idx]
        fill_price = float(day1m["open"].iloc[fill_idx])

        j = np.searchsorted(b5_start, np.datetime64(fill_ts) - np.timedelta64(5, "m"), side="right") - 1
        if j < 0 or j >= len(atr5) or not np.isfinite(atr5[j]):
            continue
        a = float(atr5[j])
        target_dist = B.round_distance_tick(2.0 * a)
        stop_dist = B.round_distance_tick(1.5 * a)
        stop, target = fill_price - stop_dist, fill_price + target_dist
        exit_price, exit_reason, exit_ts, voided, tie = B._walk_1m_fixed(
            day1m, fill_ts, "long", stop, target, date_str)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-A1",
                   "draw": draw_idx, "direction": "long", "voided": voided,
                   "fill_time": str(fill_ts), "fill_price": fill_price,
                   "stop": stop, "target": target,
                   "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def c_s1_draw(real_trades, frames, draw_idx: int) -> list[dict]:
    """sec 7.1 C-S1: short at a uniformly random 5-min bar's open, 09:35-
    15:50, cover at the next 5-min bar's open."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        day = frames.get(date_str)
        if day is None or day.empty:
            continue
        bars5 = B.resample_session_bars(day, 5)
        if bars5.empty:
            continue
        naive = B._naive_et(bars5)
        t = naive.time
        candidates = np.where((t >= dtime(9, 35)) & (t <= dtime(15, 50)))[0]
        candidates = candidates[candidates < len(bars5) - 1]
        if len(candidates) == 0:
            continue
        j = int(candidates[int(rng.integers(0, len(candidates)))])
        held = B._held_id(bars5)
        fill_price = float(bars5["open"].iloc[j])
        exit_price = float(bars5["open"].iloc[j + 1])
        voided = bool(held[j] != held[j + 1])
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-S1",
                   "draw": draw_idx, "direction": "short", "voided": voided,
                   "fill_time": str(bars5.index[j]), "fill_price": fill_price,
                   "exit_time": str(bars5.index[j + 1]), "exit_price": exit_price,
                   "exit_reason": "time_exit",
                   "entry_fill_kind": "market_or_stop", "exit_fill_kind": "market_or_stop"})
    return out


def _tmb_precompute(frames, dates) -> dict:
    bars15 = B.build_day_session_series(frames, dates, 15)
    held = B._held_id(bars15)
    atr20 = B.wilder_atr(bars15, 20, held_id=held)
    naive15 = B._naive_et(bars15)
    return {"bars15": bars15, "atr20": atr20,
           "dates15": naive15.strftime("%Y-%m-%d").to_numpy(), "times15": naive15.time}


def c_t1_draw(real_trades, frames, pre, draw_idx: int) -> list[dict]:
    """sec 7.1 C-T1: long at a uniformly random 15-min bar's OWN open,
    09:45-15:45, using the 5xATR20/4xATR20 target/stop from the ATR20 of
    the PRIOR 15-min bar (not the chosen bar's own, still-forming one)."""
    rng = CTRL.draw_rng(draw_idx)
    dates15, times15, atr20, bars15 = pre["dates15"], pre["times15"], pre["atr20"], pre["bars15"]
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        idxs = np.where((dates15 == date_str) & (times15 >= dtime(9, 45)) & (times15 <= dtime(15, 45)))[0]
        idxs = idxs[idxs >= 1]
        if len(idxs) == 0:
            continue
        k = int(idxs[int(rng.integers(0, len(idxs)))])
        a = atr20[k - 1]
        if not np.isfinite(a):
            continue
        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        day1m = day1m.sort_index()
        entry_ts = bars15.index[k]
        fill_idx = int(day1m.index.get_indexer([entry_ts])[0])
        if fill_idx < 0:
            continue
        naive1m = B._naive_et(day1m)
        fill_price = float(bars15["open"].iloc[k])
        flat_minute = B._t2m(B.bb_flat_time(date_str))
        exit_price, exit_reason, exit_pos = B._tmb_walk(day1m, naive1m, fill_idx, float(a), flat_minute, "long")
        held1m = B._held_id(day1m)
        voided = bool(held1m[fill_idx] != held1m[exit_pos])
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-T1",
                   "draw": draw_idx, "direction": "long", "voided": voided,
                   "fill_time": str(entry_ts), "fill_price": fill_price,
                   "exit_time": str(day1m.index[exit_pos]), "exit_price": exit_price,
                   "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def c_c1_draw(real_trades, frames, draw_idx: int) -> list[dict]:
    """sec 7.1 C-C1: the real entry minute, fill price, target distance
    (`reward`) and stop distance (`stop_dist`), side chosen by a seeded
    coin."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        fill_ts = pd.Timestamp(rt["fill_time"])
        fill_price = rt["fill_price"]
        stop_dist, target_dist = rt["stop_dist"], rt["reward"]
        direction = "long" if rng.integers(0, 2) == 0 else "short"
        stop = fill_price - stop_dist if direction == "long" else fill_price + stop_dist
        target = fill_price + target_dist if direction == "long" else fill_price - target_dist
        exit_price, exit_reason, exit_ts, voided, tie = B._walk_1m_fixed(
            day1m.sort_index(), fill_ts, direction, stop, target, date_str)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-C1",
                   "draw": draw_idx, "direction": direction, "voided": voided,
                   "fill_time": str(fill_ts), "fill_price": fill_price,
                   "stop": stop, "target": target,
                   "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def c_n1_draw(real_trades, pre_nrs, market: str, draw_idx: int, *,
             chandelier_mult: float = 3.0) -> list[dict]:
    """sec 7.1 C-N1: the real entry minute and fill, a seeded coin for
    the side, the same chandelier from that fill, the same roll and
    training-end exits -- exactly strategy.w16.bar_batch._nrs_walk_from_
    entry's job."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        direction = "long" if rng.integers(0, 2) == 0 else "short"
        trade = B._nrs_walk_from_entry(
            pre_nrs, direction, rt["fill_price"], rt["entry_idx_1m"], rt["entry_hourly_idx"],
            rt["date"], rt["squeeze_bar_time"], market, chandelier_mult=chandelier_mult)
        trade = dict(trade, baseline="C-N1", draw=draw_idx)
        out.append(trade)
    return out


def compute_control(cell_rule: str, real_trades, *, frames=None, pre=None, market=None,
                    n_draws: int = N_CONTROL_DRAWS, level: str = SCORE_LEVEL,
                    progress: bool = True) -> list[float]:
    nets = []
    for i in range(n_draws):
        if cell_rule == "ABD":
            draw = c_a1_draw(real_trades, frames, pre, i)
        elif cell_rule == "SSS":
            draw = c_s1_draw(real_trades, frames, i)
        elif cell_rule == "TMB":
            draw = c_t1_draw(real_trades, frames, pre, i)
        elif cell_rule == "CRT":
            draw = c_c1_draw(real_trades, frames, i)
        elif cell_rule == "NRS":
            draw = c_n1_draw(real_trades, pre, market, i)
        else:
            raise ValueError(f"unknown rule {cell_rule!r}")
        nets.append(R.summarize(R.price_all(draw, level))["net"])
        if progress and (i + 1) % 100 == 0:
            print(f"    C-{cell_rule[0]}1 {market or ''}: {i + 1}/{n_draws} draws")
    return nets


# ---- sec 7.2 reported controls: C-C2, C-N2, C-T2 -----------------------

def _c_c2_draw(real_trades, frames, draw_idx: int) -> list[dict]:
    """sec 7.2 C-C2: same side, entry at a uniformly random minute from
    the real fill to the window end (12:00), same exits."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        day1m = day1m.sort_index()
        naive1m = B._naive_et(day1m)
        fill_ts = pd.Timestamp(rt["fill_time"])
        candidates = np.where((day1m.index > fill_ts) & (naive1m.time <= dtime(12, 0)))[0]
        if len(candidates) == 0:
            continue
        new_idx = int(candidates[int(rng.integers(0, len(candidates)))])
        new_fill_ts = day1m.index[new_idx]
        new_fill_price = float(day1m["open"].iloc[new_idx])
        direction = rt["direction"]
        stop_dist, target_dist = rt["stop_dist"], rt["reward"]
        stop = new_fill_price - stop_dist if direction == "long" else new_fill_price + stop_dist
        target = new_fill_price + target_dist if direction == "long" else new_fill_price - target_dist
        exit_price, exit_reason, exit_ts, voided, tie = B._walk_1m_fixed(
            day1m, new_fill_ts, direction, stop, target, date_str)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-C2",
                   "draw": draw_idx, "direction": direction, "voided": voided,
                   "fill_time": str(new_fill_ts), "fill_price": new_fill_price,
                   "stop": stop, "target": target,
                   "exit_time": str(exit_ts), "exit_price": exit_price, "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def _c_n2_draw(real_trades, pre_nrs, market: str, draw_idx: int, *,
              chandelier_mult: float = 3.0) -> list[dict]:
    """sec 7.2 C-N2: same side, entry at a uniformly random minute from
    the real fill to the end of that CME trading day. KNOWN SIMPLIFICATION
    (documented, not guessed at): the chandelier's ATR is read at the hour
    the NEW random fill lands in (not the real squeeze bar's own hour, and
    not recomputed for a fresh squeeze -- there is none at this new point);
    entry_hourly_idx becomes the hour AFTER that new fill's own hour, same
    convention generate_nrs_trades uses for a real fill."""
    rng = CTRL.draw_rng(draw_idx)
    m_naive, m_ts, n_m = pre_nrs["m_naive"], pre_nrs["m_ts"], pre_nrs["n_m"]
    h_start_vals, h_atr, n_h = pre_nrs["h_start_vals"], pre_nrs["h_atr"], pre_nrs["n_h"]
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        entry_idx_1m = rt["entry_idx_1m"]
        day_end = np.datetime64(pd.Timestamp(str(rt["date"])) + pd.Timedelta(hours=18))  # next CME day's 18:00 rollover
        candidates = np.where((np.arange(n_m) > entry_idx_1m) & (m_naive < day_end))[0]
        if len(candidates) == 0:
            continue
        new_idx = int(candidates[int(rng.integers(0, len(candidates)))])
        new_fill_price = float(pre_nrs["m_opens"][new_idx])
        new_hour = int(np.searchsorted(h_start_vals, m_naive[new_idx], side="right") - 1)
        if new_hour < 0 or new_hour >= n_h or not np.isfinite(h_atr[new_hour]):
            continue
        direction = "long" if rng.integers(0, 2) == 0 else "short"
        trade = B._nrs_walk_from_entry(
            pre_nrs, direction, new_fill_price, new_idx, new_hour + 1,
            rt["date"], rt["squeeze_bar_time"], market, chandelier_mult=chandelier_mult)
        trade = dict(trade, baseline="C-N2", draw=draw_idx)
        out.append(trade)
    return out


def _c_t2_draw(real_trades, frames, draw_idx: int) -> list[dict]:
    """sec 7.2 C-T2: the real entry times, a seeded coin for the side
    (the short uses TMB's own mirrored exits -- target 5xATR20 below,
    4xATR20 trailing stop above)."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        day1m = frames.get(date_str)
        if day1m is None or day1m.empty:
            continue
        day1m = day1m.sort_index()
        naive1m = B._naive_et(day1m)
        fill_ts = pd.Timestamp(rt["fill_time"])
        fill_idx = int(day1m.index.get_indexer([fill_ts])[0])
        if fill_idx < 0:
            continue
        direction = "long" if rng.integers(0, 2) == 0 else "short"
        flat_minute = B._t2m(B.bb_flat_time(date_str))
        exit_price, exit_reason, exit_pos = B._tmb_walk(
            day1m, naive1m, fill_idx, rt["atr20"], flat_minute, direction)
        held1m = B._held_id(day1m)
        voided = bool(held1m[fill_idx] != held1m[exit_pos])
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-T2",
                   "draw": draw_idx, "direction": direction, "voided": voided,
                   "fill_time": str(fill_ts), "fill_price": rt["fill_price"],
                   "exit_time": str(day1m.index[exit_pos]), "exit_price": exit_price,
                   "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


# ---------------------------------------------------------------------
# neighbour grids -- sec 7.3, 9 cells per scored cell, net at L2, training
# ---------------------------------------------------------------------

def run_neighbour_grid(rule: str, frames_or_df1m, market: str, dates, *,
                       pre_nrs: dict | None = None) -> dict:
    rows = []
    if rule == "ABD":
        for atr_mult in GRID_ABD_ATR_MULT:
            for scale in GRID_ABD_SCALE:
                trades = B.generate_abd_trades(frames_or_df1m, market, dates, atr_mult=atr_mult,
                                              target_mult=2.0 * scale, stop_mult=1.5 * scale)
                s = R.summarize(R.price_all(trades, SCORE_LEVEL))
                rows.append({"atr_mult": atr_mult, "scale": scale, "n_trades": s["n_trades"],
                            "net": s["net"], "is_registered_cell": (atr_mult, scale) == (3.1, 1.0)})
    elif rule == "SSS":
        for wick_mult in GRID_SSS_WICK_MULT:
            for hold_bars in GRID_SSS_HOLD_BARS:
                trades = B.generate_sss_trades(frames_or_df1m, market, dates, wick_mult=wick_mult,
                                              hold_bars=hold_bars)
                s = R.summarize(R.price_all(trades, SCORE_LEVEL))
                rows.append({"wick_mult": wick_mult, "hold_bars": hold_bars, "n_trades": s["n_trades"],
                            "net": s["net"], "is_registered_cell": (wick_mult, hold_bars) == (2.0, 1)})
    elif rule == "TMB":
        for hp in GRID_TMB_HP:
            for ac in GRID_TMB_AC:
                trades = B.generate_tmb_trades(frames_or_df1m, market, dates, hp_threshold=hp,
                                              ac_threshold=ac)
                s = R.summarize(R.price_all(trades, SCORE_LEVEL))
                rows.append({"hp_threshold": hp, "ac_threshold": ac, "n_trades": s["n_trades"],
                            "net": s["net"], "is_registered_cell": (hp, ac) == (50.0, -0.10)})
    elif rule == "CRT":
        for rr in GRID_CRT_RR:
            for we in GRID_CRT_WINDOW_END:
                trades = B.generate_crt_trades(frames_or_df1m, market, dates, reward_risk=rr,
                                              window_end=we)
                s = R.summarize(R.price_all(trades, SCORE_LEVEL))
                rows.append({"reward_risk": rr, "window_end": str(we), "n_trades": s["n_trades"],
                            "net": s["net"], "is_registered_cell": (rr, we) == (1.5, dtime(12, 0))})
    elif rule == "NRS":
        for cm in GRID_NRS_CHANDELIER:
            for sl in GRID_NRS_SQUEEZE_LEN:
                trades = B.generate_nrs_trades(frames_or_df1m, market, dates, chandelier_mult=cm,
                                              squeeze_len=sl, _pre=pre_nrs)
                s = R.summarize(R.price_all(trades, SCORE_LEVEL))
                rows.append({"chandelier_mult": cm, "squeeze_len": sl, "n_trades": s["n_trades"],
                            "net": s["net"], "is_registered_cell": (cm, sl) == (3.0, 4)})
    else:
        raise ValueError(f"unknown rule {rule!r}")
    n_positive = sum(1 for r in rows if r["net"] > 0)
    return {"cells": rows, "n_positive": n_positive, "n_total": len(rows),
           "share_positive": n_positive / len(rows) if rows else 0.0}


# ---------------------------------------------------------------------
# orchestration: one scored cell, end to end
# ---------------------------------------------------------------------

def run_cell(rule: str, market: str, archive, *, spend_holdout_candidate: str | None = None,
            compute_controls_flag: bool = True, n_control_draws: int = N_CONTROL_DRAWS,
            compute_grid_flag: bool = True, progress: bool = True) -> dict:
    is_nrs = (rule == "NRS")
    df_1m = load_root_bars(archive, market)
    if is_nrs:
        all_dates = B.nrs_cme_trading_days(df_1m)
    else:
        frames = session_frames(df_1m)
        all_dates = trading_dates(frames)

    candidate = f"{rule}-{market}"
    if spend_holdout_candidate:
        if candidate != spend_holdout_candidate:
            dates, _, label = H.split_dates(all_dates)
        else:
            dates, _, label = H.split_dates(all_dates, spend=True, candidate=candidate)
    else:
        dates, _, label = H.split_dates(all_dates)

    pre_nrs = pre_abd = pre_tmb = None
    if is_nrs:
        pre_nrs = B._nrs_precompute(df_1m)
        trades = B.generate_nrs_trades(df_1m, market, dates, _pre=pre_nrs)
        gen_input = df_1m
    else:
        trades = _generate(rule, frames, market, dates)
        gen_input = frames
        if rule == "ABD":
            pre_abd = _abd_precompute(frames, dates)
        elif rule == "TMB":
            pre_tmb = _tmb_precompute(frames, dates)

    priced_by_level = {lvl: R.price_all(trades, lvl) for lvl in LEVELS}
    n_voided = sum(1 for t in trades if t.get("voided"))
    result: dict = {"rule": rule, "market": market, "candidate": candidate,
                    "date_side": label, "n_raw_trades": len(trades), "n_voided": n_voided}

    control_nets = None
    control_summary = None
    if compute_controls_flag:
        t0 = _time.time()
        if rule == "ABD":
            control_nets = compute_control("ABD", trades, frames=frames, pre=pre_abd,
                                          n_draws=n_control_draws, progress=progress)
        elif rule == "SSS":
            control_nets = compute_control("SSS", trades, frames=frames,
                                          n_draws=n_control_draws, progress=progress)
        elif rule == "TMB":
            control_nets = compute_control("TMB", trades, frames=frames, pre=pre_tmb,
                                          n_draws=n_control_draws, progress=progress)
        elif rule == "CRT":
            control_nets = compute_control("CRT", trades, frames=frames,
                                          n_draws=n_control_draws, progress=progress)
        elif rule == "NRS":
            control_nets = compute_control("NRS", trades, pre=pre_nrs, market=market,
                                          n_draws=n_control_draws, progress=progress)
        seconds = _time.time() - t0
        control_summary = {
            "n_draws": len(control_nets), "seconds": seconds,
            "p5": float(np.percentile(control_nets, 5)) if control_nets else None,
            "p50": float(np.percentile(control_nets, 50)) if control_nets else None,
            "p95": float(np.percentile(control_nets, 95)) if control_nets else None,
        }

    neighbour_grid = None
    if compute_grid_flag:
        neighbour_grid = run_neighbour_grid(rule, gen_input, market, dates, pre_nrs=pre_nrs)
    neighbour_grid_share = neighbour_grid["share_positive"] if neighbour_grid else None

    result.update(R.score_cell(priced_by_level, control_nets=control_nets,
                               neighbour_grid_share=neighbour_grid_share))
    result["by_level"] = {lvl: R.summarize(rows) for lvl, rows in priced_by_level.items()}
    l2 = priced_by_level["L2"]
    result["exit_reasons"] = R.exit_reason_counts(l2)
    result["sample_trades"] = R.sample_trades(l2)
    result["account_view"] = R.account_view(l2, rule, market, account_usd=ACCOUNT_USD)
    if rule == "NRS":
        micro = FULL_TO_MICRO[market]
        result["account_view"]["overnight_margin"] = OVERNIGHT_MARGIN[micro]
        result["account_view"]["margin_initial_within_account"] = (
            OVERNIGHT_MARGIN[micro]["initial"] <= ACCOUNT_USD)
    result["trades_per_day"] = {"n_dates_with_trade": len({t["date"] for t in l2}),
                                "n_training_dates": len(dates)}
    result["long_short_split"] = {
        "long": sum(1 for t in l2 if t["direction"] == "long"),
        "short": sum(1 for t in l2 if t["direction"] == "short")}
    result["control_summary"] = control_summary
    result["neighbour_grid"] = neighbour_grid
    return result


# ---------------------------------------------------------------------
# reported variants (sec 3.x): ES for all four day-session rules, TMB
# mirrored short
# ---------------------------------------------------------------------

def run_reported_variants(archive) -> dict:
    out = {}
    df_es = load_root_bars(archive, "ES")
    frames_es = session_frames(df_es)
    dates_es, _, _ = H.split_dates(trading_dates(frames_es))
    out["ABD-ES"] = R.summarize(R.price_all(B.generate_abd_trades(frames_es, "ES", dates_es), SCORE_LEVEL))
    out["SSS-ES"] = R.summarize(R.price_all(B.generate_sss_trades(frames_es, "ES", dates_es), SCORE_LEVEL))
    out["TMB-ES"] = R.summarize(R.price_all(B.generate_tmb_trades(frames_es, "ES", dates_es), SCORE_LEVEL))
    out["CRT-ES"] = R.summarize(R.price_all(B.generate_crt_trades(frames_es, "ES", dates_es), SCORE_LEVEL))

    df_nq = load_root_bars(archive, "NQ")
    frames_nq = session_frames(df_nq)
    dates_nq, _, _ = H.split_dates(trading_dates(frames_nq))
    tmb_short = B.generate_tmb_trades(frames_nq, "NQ", dates_nq, mirror_short=True)
    out["TMB-short-NQ"] = R.summarize(R.price_all(tmb_short, SCORE_LEVEL))
    return out


# ---------------------------------------------------------------------
# source-claims block -- sec 7.4
# ---------------------------------------------------------------------

SOURCE_CLAIMS = {
    "ABD": {"claim": "PF 1.527, slightly more than 50% win, max DD $2,614 at 4 MNQ",
           "their_sample": "TradingView 5-min MNQ, a few months to 2026, costs unstated"},
    "SSS": {"claim": "PF 1.413, 52% win, max DD $1,142 at 4 MNQ",
           "their_sample": "TradingView 5-min MNQ, a few months to 2026, costs unstated"},
    "TMB": {"claim": "486 trades, 44% win, PF 1.381, max DD $4,172",
           "their_sample": "TradingView 15-min MNQ, period unstated"},
    "CRT": {"claim": "60-65% win at 1.5R, first setup, direct break",
           "their_sample": "self-reported, since 2023"},
    "NRS": {"claim": "account-level only (25 days, PF 6.84, 61.9% win); no rule-level test",
           "their_sample": "firm data"},
}


def _profit_factor(priced: list[dict]) -> float | None:
    gp = sum(t["net"] for t in priced if t["net"] > 0)
    gl = -sum(t["net"] for t in priced if t["net"] <= 0)
    return (gp / gl) if gl > 0 else None


def source_claims_block(cell_results: dict[str, dict]) -> dict:
    out = {}
    for rule, claim in SOURCE_CLAIMS.items():
        row = dict(claim)
        for cell_key, res in cell_results.items():
            if not cell_key.startswith(rule):
                continue
            l2 = res["by_level"]["L2"]
            row[f"{cell_key}_training_win_rate_l2"] = (l2["wins"] / l2["n_trades"]) if l2["n_trades"] else None
            row[f"{cell_key}_training_net_l2"] = l2["net"]
            row[f"{cell_key}_profit_factor_alarm"] = None    # filled in run_backtest (needs priced trades, not just summary)
        out[rule] = row
    return out


# ---------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------

def run_backtest(archive, *, spend_holdout: str | None = None,
                 compute_controls_flag: bool = True, n_control_draws: int = N_CONTROL_DRAWS,
                 compute_grid_flag: bool = True, progress: bool = True,
                 include_reported_variants: bool = True) -> dict:
    if spend_holdout and spend_holdout not in H.ALLOWED_CANDIDATES:
        raise SystemExit(f"only one of {sorted(H.ALLOWED_CANDIDATES)} may spend the BB-v0 holdout; "
                        f"{spend_holdout!r} cannot.")

    cells: dict[str, dict] = {}
    for candidate in SCORED_CELLS:
        rule, market = candidate.split("-")
        print(f"running {candidate} (training side)"
             f"{' [no controls]' if not compute_controls_flag else f' [{n_control_draws} control draws]'}"
             f"{' [no grid]' if not compute_grid_flag else ''}...")
        cells[candidate] = run_cell(rule, market, archive, spend_holdout_candidate=spend_holdout,
                                    compute_controls_flag=compute_controls_flag,
                                    n_control_draws=n_control_draws,
                                    compute_grid_flag=compute_grid_flag, progress=progress)
        # profit-factor alarm (sec 9 footer): a training PF > 3 over 1,000+
        # trades is treated as a likely bug and audited before the Result doc.
        l2 = cells[candidate]["by_level"]["L2"]
        pf = (None if l2["n_trades"] == 0 else
             (l2["gross"] / (l2["gross"] - l2["net"]) if (l2["gross"] - l2["net"]) > 0 else None))
        cells[candidate]["profit_factor_l2"] = pf
        cells[candidate]["profit_factor_alarm"] = bool(
            pf is not None and pf > 3.0 and l2["n_trades"] >= 1000)

    result: dict = {"cells": cells}
    result["source_claims"] = source_claims_block(cells)
    if include_reported_variants:
        result["reported_variants"] = run_reported_variants(archive)
    return result


def money(v):
    if v is None:
        return "N/A"
    return f"(${abs(v):,.2f})" if v < 0 else f"${v:,.2f}"


def _txt_report(preflight: dict | None, backtest: dict | None) -> str:
    lines: list[str] = []

    if preflight is not None:
        lines.append("=== W16 BB-v0 -- PRE-FLIGHT (no P&L) ===")
        we = preflight["worked_example"]
        lines.append(f"worked example (ABD): target_dist={we['computed_target_dist']} "
                    f"(expect {we['expected_target_dist']}, ok={we['target_ok']})  "
                    f"stop_dist={we['computed_stop_dist']} (expect {we['expected_stop_dist']}, ok={we['stop_ok']})")
        for cell, c in preflight["cells"].items():
            flag = "  [<300, NOT READ]" if c["underpowered_below_300"] else ""
            lines.append(f"\n{cell}: entries={c['n_entries']}  voided={c['n_voided']}{flag}")
            if cell.startswith("TMB"):
                lines.append(f"    HP>50 share={c.get('hp_over_50_share')}  "
                            f"calibration amendment needed={c.get('calibration_amendment_needed')}")
        lines.append("")

    if backtest is not None:
        lines.append("=== W16 BB-v0 -- BACKTEST (six scored cells, per 1 micro) ===")
        for candidate, cell in backtest["cells"].items():
            s = cell["by_level"]["L2"]
            lines.append(f"\n--- {candidate} ({cell['date_side']}) ---")
            lines.append(f"trades: {cell['n_raw_trades']} raw, {cell['n_voided']} voided")
            for lvl in ("L1", "L2", "L3"):
                ls = cell["by_level"][lvl]
                lines.append(f"  [{lvl}] n={ls['n_trades']}  wins={ls['wins']}  losses={ls['losses']}  "
                            f"net={money(ls['net'])}  avg_win={money(ls['avg_win'])}  "
                            f"avg_loss={money(ls['avg_loss'])}")
            lines.append(f"  criteria: {cell['criteria']}")
            if cell.get("control_summary"):
                cs = cell["control_summary"]
                lines.append(f"  control p95={money(cs['p95'])}  (n={cs['n_draws']}, {cs['seconds']:.1f}s)")
            if cell.get("neighbour_grid"):
                g = cell["neighbour_grid"]
                lines.append(f"  neighbour grid: {g['n_positive']}/{g['n_total']} cells net-positive at L2")
            if cell.get("profit_factor_alarm"):
                lines.append(f"  *** PROFIT FACTOR ALARM: PF={cell['profit_factor_l2']:.2f} over "
                            f"{s['n_trades']} trades -- audit before the Result doc ***")
        lines.append("\n--- source claims (sec 7.4) ---")
        for rule, row in backtest["source_claims"].items():
            lines.append(f"  {rule}: {row}")
        if backtest.get("reported_variants"):
            lines.append("\n--- reported variants ---")
            for k, v in backtest["reported_variants"].items():
                lines.append(f"  {k}: n={v['n_trades']}  net={money(v['net'])}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W16 BB-v0 runner.")
    ap.add_argument("--archive", type=Path, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--backtest", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-controls", action="store_true",
                    help="Skip the 5 x 1,000-draw scored controls -- fast sanity pass on trade "
                         "counts/net before committing to the full run.")
    ap.add_argument("--skip-grid", action="store_true",
                    help="Skip the sec 7.3 neighbour grids (9 cells x 6 scored cells) -- fast "
                         "sanity pass; criterion 8 then reports None, not False.")
    ap.add_argument("--n-control-draws", type=int, default=N_CONTROL_DRAWS,
                    help=f"Control draws per cell (registered: {N_CONTROL_DRAWS}). Lower only for "
                         "a quick look; the registered pass bar needs the full count.")
    ap.add_argument("--spend-holdout", metavar="CANDIDATE", default=None,
                    help=f"Read the locked holdout side for one candidate (one of "
                         f"{sorted(H.ALLOWED_CANDIDATES)}), after a training pass. Never set this "
                         "to explore -- sec 8: spent once, by one cell.")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    preflight_report = None
    backtest_report = None

    if a.preflight:
        preflight_report = run_preflight(archive)
        _print_preflight_summary(preflight_report)
    else:
        t0 = _time.time()
        backtest_report = run_backtest(
            archive, spend_holdout=a.spend_holdout,
            compute_controls_flag=not a.skip_controls, n_control_draws=a.n_control_draws,
            compute_grid_flag=not a.skip_grid)
        elapsed = _time.time() - t0
        for candidate, cell in backtest_report["cells"].items():
            s = cell["by_level"]["L2"]
            print(f"{candidate:8s}  n={s['n_trades']:5d}  net(L2)=${s['net']:,.2f}  "
                 f"passes_all_computed={cell['criteria']['passes_all_computed']}")
        print(f"\ntotal wall time: {elapsed:.1f}s")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        report = preflight_report if preflight_report is not None else backtest_report
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        txt_path = a.out.with_suffix(".txt")
        txt_path.write_text(_txt_report(preflight_report, backtest_report), encoding="utf-8")
        print(f"\nfull report: {a.out}")
        print(f"plain-English summary: {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
