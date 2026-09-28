#!/usr/bin/env python3
"""DVP-v0 backtest runner: G2 pre-flight (no P&L), the scored cell
(DVP-NQ) at L1/L2/L3, sec 9's nine criteria (bootstrap >= 95%, NOT
runner.py's 99% -- see BOOTSTRAP_PASS_PCT below), the C-D1/C-D2/C-D3
controls, the sec 7.4 neighbour grid, the sec 7.3 replication block, the
sec 3.6 reported variants, and full sec 4 reporting. Board W16-0006
subitem 2. REGISTERED_w16_drift_vwap.md.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_runner --preflight --out "D:\\Trading\\Claude outputs\\w16_0006_preflight.json"
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_runner --backtest --skip-controls --skip-grid   # fast sanity pass
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.dvp_runner --backtest --out "D:\\Trading\\Claude outputs\\w16_0006_backtest.json"

WHY THIS DOES NOT REUSE strategy.w16.runner.score_cell / BOOTSTRAP_PASS_PCT
------------------------------------------------------------------------
REGISTERED_w16_drift_vwap.md sec 9 #4: "Bootstrap by calendar month (2,000
seeded resamples with replacement): net > 0 in >= 95%." SB-v0's own runner
raises that to 99% for its six scored cells (runner.py: "raised from 95%
for 6 scored cells") -- a DIFFERENT multiplicity correction for a DIFFERENT
registration. The brief is explicit: "do not change runner.py's constant,
parameterise or wrap instead." `strategy.w16.runner.bootstrap_by_month`
IS reused as-is (it returns `pct_net_positive` regardless of threshold);
only the PASS/FAIL comparison against that percentage is done here, at
DVP-v0's own BOOTSTRAP_PASS_PCT, in `dvp_score_cell` below -- `runner.py`
itself is never edited and SB-v0's scoring is unaffected.

WHAT IS BUILT HERE
------------------------------------------------------------------------
Trade generation (strategy.w16.drift_vwap, both the registered pullback
rule and the C-D2 "no pullback" reported variant), cost/P&L at L1/L2/L3
(strategy.w16.costs / strategy.w16.runner.price_trade -- reused
unchanged), sec 9's nine criteria (`dvp_score_cell`), the C-D1 (scored),
C-D2, C-D3 (reported) controls, the sec 7.4 neighbour grid, the sec 7.3
replication block, the sec 3.6 reported variants, sec 4's reporting
(exit reasons, guardrail-day counts, same-bar ties, sample trades, account
view, break-even win rate), and the DVP-v0 holdout gate
(strategy.w16.dvp_holdout).
"""
from __future__ import annotations

import argparse
import json
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import controls as CTRL
from strategy.w16 import drift_vwap as D
from strategy.w16 import dvp_holdout as H
from strategy.w16 import runner as R
from strategy.w16.costs import FULL_TO_MICRO, POINT_VALUE, pnl_dollars, trade_cost
from strategy.w16.preflight import load_root_bars, session_frames
from strategy.w16.sessions import is_xnys_trading_day

LEVELS = R.LEVELS                       # ("L1", "L2", "L3")
SCORE_LEVEL = "L2"
SCORED_MARKET = "NQ"
SCORED_CANDIDATE = "DVP-NQ"
MIN_TRADES = 300
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_PASS_PCT = 0.95                # sec 9 #4 -- DVP-v0's OWN threshold; see module docstring
N_CONTROL_DRAWS = 1000                    # sec 7.1
ACCOUNT_USD = R.ACCOUNT_USD

GRID_SCALES = (0.75, 1.0, 1.25)           # sec 7.4 dim 1 (registered 1.0)
GRID_C3 = (0.0005, 0.001, 0.0015)         # sec 7.4 dim 2 (registered 0.001)
REGISTERED_GRID_CELL = (1.0, D.C3_THRESHOLD_DEFAULT)

REPLICATION_START = D.TRAIN_START_2020    # sec 7.3
REPLICATION_END = D.TRAIN_END_2023

# sec 7.3's pass bands, checked against the replication block's own figures.
REPL_WIN_RATE_BAND = (0.60, 0.68)
REPL_TRADES_PER_DAY_BAND = (1.5, 4.0)
REPL_AVG_WIN_TARGET = 866.0
REPL_AVG_LOSS_TARGET = -1300.0
REPL_BAND_TOLERANCE = 0.25



def trading_dates(frames) -> list[str]:
    """Sorted session dates that are XNYS trading days. SB-v0 sec 2 (inherited
    by DVP-v0 sec 2): "Days the XNYS calendar lists as closed ... don't count."
    The ET-date grouping of the Globex archive also yields Sundays and exchange
    holidays; without this filter they were counted as "sessions skipped"
    (first pre-flight, 2026-09-28) -- no trades, but wrong counts."""
    return [d for d in sorted(frames.keys()) if is_xnys_trading_day(d)]


def require_p_ref(market: str) -> float:
    """sec 3.4/12: P_ref is fixed ONCE, by the pre-flight, before any P&L
    -- `--backtest` REFUSES to run for a market whose module constant is
    still None (Amendment A has not pinned it yet), rather than silently
    computing one from the training data it is about to score."""
    p_ref = {"NQ": D.P_REF_NQ, "ES": D.P_REF_ES}.get(market)
    if p_ref is None:
        raise SystemExit(
            f"strategy.w16.drift_vwap.P_REF_{market} is None. REGISTERED_w16_drift_vwap.md "
            "sec 3.4: P_ref is fixed once by the pre-flight (Amendment A), before any P&L. "
            f"Run --preflight, read its printed P_ref for {market}, have Ben pin it into "
            "REGISTERED_w16_drift_vwap.md as Amendment A, and set P_REF_{market} in "
            "strategy/w16/drift_vwap.py to that number -- only then can --backtest score it.")
    return p_ref


# ---------------------------------------------------------------------
# pre-flight (G2, no P&L)
# ---------------------------------------------------------------------

def _distance_usd_stats(trades_or_triggers, market: str, fill_prices, p_ref: float, *,
                        scale: float = 1.0) -> dict:
    micro = FULL_TO_MICRO[market]
    stop_usd, target_usd = [], []
    for fp, direction in fill_prices:
        sd = D.scaled_distance(D.STOP_PTS[direction], fp, p_ref, scale=scale)
        td = D.scaled_distance(D.TARGET_PTS[direction], fp, p_ref, scale=scale)
        stop_usd.append(sd * POINT_VALUE[micro])
        target_usd.append(td * POINT_VALUE[micro])
    def _stats(vals):
        if not vals:
            return {"median": None, "p90": None, "max": None}
        return {"median": float(np.percentile(vals, 50)), "p90": float(np.percentile(vals, 90)),
               "max": float(max(vals))}
    return {"stop_dist_usd": _stats(stop_usd), "target_dist_usd": _stats(target_usd)}


def run_preflight(archive) -> dict:
    report: dict = {"markets": {}}
    for market in ("NQ", "ES"):
        df_1m = load_root_bars(archive, market)
        frames = session_frames(df_1m)
        all_dates = trading_dates(frames)
        train_dates, n_locked, _ = H.split_dates(all_dates)
        train_dates = sorted(train_dates)

        p_ref = D.compute_p_ref(frames, market)

        per_year: dict[int, dict] = {}
        total_sessions = total_skipped = total_triggers = total_days_with_trigger = 0
        first_long = first_short = 0
        fill_prices_2010, fill_prices_2016, fill_prices_2023 = [], [], []

        for date_str in train_dates:
            year = int(date_str[:4])
            y = per_year.setdefault(year, {
                "sessions": 0, "skipped": 0, "triggers": 0, "days_with_trigger": 0,
                "entries_upper_bound": 0, "first_long": 0, "first_short": 0})
            res = D.dvp_triggers_session(frames[date_str], date_str, market=market)
            y["sessions"] += 1
            total_sessions += 1
            if res["skipped"]:
                y["skipped"] += 1
                total_skipped += 1
                continue
            y["triggers"] += res["n_triggers"]
            y["entries_upper_bound"] += res["n_entries_upper_bound"]
            total_triggers += res["n_triggers"]
            if res["n_triggers"] > 0:
                y["days_with_trigger"] += 1
                total_days_with_trigger += 1
            if res["first_direction"] == "long":
                y["first_long"] += 1
                first_long += 1
            elif res["first_direction"] == "short":
                y["first_short"] += 1
                first_short += 1

            if p_ref is not None and year in (2010, 2016, 2023):
                for j, direction, fill_idx, fill_price, fill_ts, tau in D.iter_triggers(
                        frames[date_str], date_str):
                    bucket = {2010: fill_prices_2010, 2016: fill_prices_2016,
                             2023: fill_prices_2023}[year]
                    bucket.append((fill_price, direction))

        entries_upper_bound_total = sum(y["entries_upper_bound"] for y in per_year.values())
        underpowered = entries_upper_bound_total < MIN_TRADES

        dist_2010 = (_distance_usd_stats(None, market, fill_prices_2010, p_ref)
                    if p_ref is not None and fill_prices_2010 else None)
        dist_2016 = (_distance_usd_stats(None, market, fill_prices_2016, p_ref)
                    if p_ref is not None and fill_prices_2016 else None)
        dist_2023 = (_distance_usd_stats(None, market, fill_prices_2023, p_ref)
                    if p_ref is not None and fill_prices_2023 else None)

        report["markets"][market] = {
            "p_ref": p_ref,
            "per_year": {y: v for y, v in sorted(per_year.items())},
            "totals": {
                "sessions": total_sessions, "skipped": total_skipped,
                "triggers": total_triggers, "days_with_trigger": total_days_with_trigger,
                "entries_upper_bound": entries_upper_bound_total,
                "first_trigger_long": first_long, "first_trigger_short": first_short,
                "trades_per_day_upper_bound": (entries_upper_bound_total / total_sessions
                                              if total_sessions else None),
                "underpowered_below_300": underpowered,
            },
            "stop_target_distance_usd_per_mnq": {
                "2010": dist_2010, "2016": dist_2016, "2023": dist_2023},
        }
    return report


def _print_preflight_summary(report: dict) -> None:
    print("G2 -- W16 DVP-v0 pre-flight (training side, no P&L)\n")
    for market, m in report["markets"].items():
        t = m["totals"]
        flag = " [<300, NOT READ]" if t["underpowered_below_300"] else ""
        p_ref = m["p_ref"]
        p_ref_str = f"{p_ref:,.2f}" if p_ref is not None else "N/A (no 2020-2023 sessions in this archive)"
        print(f"{market}: P_ref={p_ref_str}  sessions={t['sessions']}  skipped={t['skipped']}  "
             f"triggers={t['triggers']}  days_with_trigger={t['days_with_trigger']}  "
             f"entries_upper_bound={t['entries_upper_bound']}{flag}")
        print(f"    first-trigger fills: long={t['first_trigger_long']}  short={t['first_trigger_short']}  "
             f"trades/day upper bound={t['trades_per_day_upper_bound']:.2f}"
             if t['trades_per_day_upper_bound'] is not None else "")


# ---------------------------------------------------------------------
# scoring (sec 9), at DVP-v0's own bootstrap threshold
# ---------------------------------------------------------------------

def dvp_score_cell(priced_by_level: dict[str, list[dict]], *,
                   control_nets: list[float] | None = None,
                   neighbour_grid_share: float | None = None) -> dict:
    """sec 9's nine criteria for the scored cell DVP-NQ. Mirrors
    strategy.w16.runner.score_cell's shape (reuses summarize/both_halves/
    by_year/drop_best_pct/bootstrap_by_month) but with DVP-v0's OWN
    bootstrap threshold (95%, not runner.py's 99%) and a single p95
    control comparator (no B2-style AND condition -- DVP-NQ has only one
    scored control, C-D1, sec 9 #5)."""
    l2 = priced_by_level["L2"]
    l3 = priced_by_level["L3"]
    l2_summary = R.summarize(l2)
    halves = R.both_halves(l2)
    yearly = R.by_year(l2)
    total_net = l2_summary["net"]
    year_nets = {y: v["net"] for y, v in yearly.items()}
    max_year_share = (max(abs(v) for v in year_nets.values()) / abs(total_net)
                      if year_nets and total_net != 0 else None)

    boot = R.bootstrap_by_month(l2, n_draws=BOOTSTRAP_DRAWS, seed=0)
    bootstrap_pass = (boot["pct_net_positive"] is not None and
                      boot["pct_net_positive"] >= BOOTSTRAP_PASS_PCT)

    if control_nets is None:
        crit5 = None
    else:
        crit5 = total_net > float(np.percentile(control_nets, 95))

    criteria = {
        "1_net_positive": total_net > 0,
        "2_both_halves_positive": halves["early"]["net"] > 0 and halves["late"]["net"] > 0,
        "3_no_year_over_50pct": (max_year_share is not None and max_year_share <= 0.5),
        "4_month_bootstrap_ge_95pct": bootstrap_pass,
        "5_beats_c_d1_p95": crit5,
        "6_net_positive_at_l3": R.summarize(l3)["net"] > 0,
        "7_survives_dropping_best_1pct": R.drop_best_pct(l2)["net"] > 0,
        "8_neighbour_grid_6_of_9": (None if neighbour_grid_share is None else
                                    neighbour_grid_share >= 6.0 / 9.0),
        "9_min_trades": l2_summary["n_trades"] >= MIN_TRADES,
    }
    computed = [v for v in criteria.values() if v is not None]
    criteria["passes_all_computed"] = bool(computed) and all(computed)
    return {"criteria": criteria, "l2_summary": l2_summary, "both_halves": halves,
           "by_year": yearly, "max_year_share_of_net": max_year_share,
           "bootstrap": {"n_draws": boot["n_draws"], "pct_net_positive": boot["pct_net_positive"],
                        "pass_threshold": BOOTSTRAP_PASS_PCT}}


def break_even_win_rate(avg_win: float | None, avg_loss: float | None) -> float | None:
    """sec 4 item 4: the win rate needed to break even given the REALISED
    average win/loss, beside the actual win rate."""
    if not avg_win or not avg_loss:
        return None
    loss_mag = abs(avg_loss)
    denom = avg_win + loss_mag
    if denom == 0:
        return None
    return loss_mag / denom


# ---------------------------------------------------------------------
# controls: C-D1 (scored, sec 7.1), C-D2 (dvp_session_no_pullback, sec
# 7.2), C-D3 (random direction, sec 7.2)
# ---------------------------------------------------------------------

def _session_arrays_cache(frames: dict[str, pd.DataFrame], dates) -> dict:
    """{date: (minute_of_day, opens, highs, lows, candidates, flat_minute)}
    for every date in `dates`, built ONCE and shared across every draw of
    C-D1/C-D3 -- the per-trade work inside a draw becomes pure numpy
    array indexing, no per-draw `local_naive_et`/`np.where` recomputation.
    Same reasoning as strategy.w16.controls.naive_time_cache/
    o3_candidates_cache: at 1,000 draws x thousands of trades, recomputing
    this per draw does not scale (module docstring's runtime section)."""
    from strategy.w16.readback import local_naive_et
    open_min = D._t2m(D.dvp_open_time())
    cache: dict = {}
    for date_str in dates:
        bars = frames.get(date_str)
        if bars is None:
            continue
        bars = bars.sort_index()
        naive = local_naive_et(bars.index)
        minute_of_day = (naive.hour * 60 + naive.minute).to_numpy()
        late_min = D._t2m(D.dvp_late_time(date_str))
        candidates = np.where((minute_of_day >= open_min) & (minute_of_day <= late_min))[0]
        candidates = candidates[candidates < len(bars)]
        cache[date_str] = (
            minute_of_day,
            bars["open"].to_numpy(dtype=float),
            bars["high"].to_numpy(dtype=float),
            bars["low"].to_numpy(dtype=float),
            candidates,
            D._t2m(D.dvp_flat_time(date_str)),
        )
    return cache


def c_d1_draw(real_trades: list[dict], frames: dict[str, pd.DataFrame], draw_idx: int, *,
             arrays_cache: dict | None = None) -> list[dict]:
    """One C-D1 draw (sec 7.1): for every real (non-voided) trade, a
    control trade on the SAME session, SAME direction, SAME stop/target
    point distances, entered at a uniformly random 5-min-aligned bar's
    open within the registered fill window [10:30, dvp_late_time],
    walked with the same exits (stop/target/flat-at-15:55). `arrays_cache`
    (see `_session_arrays_cache`) is required for real-archive scale; it
    is rebuilt on the fly (slow) only when omitted, for a caller that
    just wants one draw without paying the cache-building cost."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    cache = arrays_cache if arrays_cache is not None else _session_arrays_cache(
        frames, {t["date"] for t in real_trades if not t.get("voided")})
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        entry = cache.get(date_str)
        if entry is None:
            continue
        minute_of_day, opens, highs, lows, candidates, flat_minute = entry
        if len(candidates) == 0:
            continue
        pos = int(rng.integers(0, len(candidates)))
        fill_idx = int(candidates[pos])
        fill_price = float(opens[fill_idx])
        direction = rt["direction"]
        stop_dist = rt["stop_dist"]
        target_dist = rt["target_dist"]
        if direction == "long":
            stop, target = fill_price - stop_dist, fill_price + target_dist
        else:
            stop, target = fill_price + stop_dist, fill_price - target_dist
        exit_price, exit_reason, exit_idx, tie = D.fast_walk_stop_target_time_exit(
            minute_of_day, opens, highs, lows, fill_idx, direction, stop, target, flat_minute)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-D1",
                   "draw": draw_idx, "direction": direction, "voided": False,
                   "fill_price": fill_price, "stop": stop, "target": target,
                   "exit_price": exit_price, "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def compute_c_d1(real_trades: list[dict], frames: dict[str, pd.DataFrame], *,
                 n_draws: int = N_CONTROL_DRAWS, level: str = SCORE_LEVEL,
                 progress: bool = True) -> list[float]:
    dates = {t["date"] for t in real_trades if not t.get("voided")}
    arrays_cache = _session_arrays_cache(frames, dates)
    nets = []
    for i in range(n_draws):
        draw = c_d1_draw(real_trades, frames, i, arrays_cache=arrays_cache)
        nets.append(R.summarize(R.price_all(draw, level))["net"])
        if progress and (i + 1) % 100 == 0:
            print(f"    C-D1: {i + 1}/{n_draws} draws")
    return nets


def c_d3_draw(real_trades: list[dict], frames: dict[str, pd.DataFrame], draw_idx: int, *,
             p_ref: float | None, scale: float = 1.0,
             arrays_cache: dict | None = None) -> list[dict]:
    """C-D3 (sec 7.2): the REAL entry times and exits, side chosen by a
    seeded coin -- stop/target distances follow the drawn side.
    `arrays_cache`: see `_session_arrays_cache` -- required for real-
    archive scale, same reasoning as `c_d1_draw`."""
    rng = CTRL.draw_rng(draw_idx)
    out = []
    cache = arrays_cache if arrays_cache is not None else _session_arrays_cache(
        frames, {t["date"] for t in real_trades if not t.get("voided")})
    for rt in real_trades:
        if rt.get("voided"):
            continue
        date_str = rt["date"]
        entry = cache.get(date_str)
        if entry is None:
            continue
        minute_of_day, opens, highs, lows, _candidates, flat_minute = entry
        fill_ts = pd.Timestamp(rt["fill_time"])
        tau_min = fill_ts.hour * 60 + fill_ts.minute
        fill_idx = int(np.searchsorted(minute_of_day, tau_min))
        if fill_idx >= len(minute_of_day):
            continue
        fill_price = float(opens[fill_idx])
        direction = "long" if rng.integers(0, 2) == 0 else "short"
        stop_dist = D.scaled_distance(D.STOP_PTS[direction], fill_price, p_ref, scale=scale)
        target_dist = D.scaled_distance(D.TARGET_PTS[direction], fill_price, p_ref, scale=scale)
        if direction == "long":
            stop, target = fill_price - stop_dist, fill_price + target_dist
        else:
            stop, target = fill_price + stop_dist, fill_price - target_dist
        exit_price, exit_reason, exit_idx, tie = D.fast_walk_stop_target_time_exit(
            minute_of_day, opens, highs, lows, fill_idx, direction, stop, target, flat_minute)
        out.append({"date": date_str, "market": rt["market"], "baseline": "C-D3",
                   "draw": draw_idx, "direction": direction, "voided": False,
                   "fill_price": fill_price, "stop": stop, "target": target,
                   "exit_price": exit_price, "exit_reason": exit_reason,
                   "entry_fill_kind": "market_or_stop",
                   "exit_fill_kind": "target" if exit_reason == "target" else "market_or_stop"})
    return out


def compute_c_d3(real_trades: list[dict], frames: dict[str, pd.DataFrame], *,
                 p_ref: float | None, scale: float = 1.0, n_draws: int = N_CONTROL_DRAWS,
                 level: str = SCORE_LEVEL, progress: bool = True) -> list[float]:
    dates = {t["date"] for t in real_trades if not t.get("voided")}
    arrays_cache = _session_arrays_cache(frames, dates)
    nets = []
    for i in range(n_draws):
        draw = c_d3_draw(real_trades, frames, i, p_ref=p_ref, scale=scale, arrays_cache=arrays_cache)
        nets.append(R.summarize(R.price_all(draw, level))["net"])
        if progress and (i + 1) % 100 == 0:
            print(f"    C-D3: {i + 1}/{n_draws} draws")
    return nets


# ---------------------------------------------------------------------
# neighbour grid (sec 7.4): 9 cells, net at L2, training side
# ---------------------------------------------------------------------

def run_neighbour_grid(frames: dict[str, pd.DataFrame], market: str, dates, *,
                       p_ref: float | None) -> dict:
    """9 (scale, c3_threshold) cells (sec 7.4). Never picks a best cell
    (sec 7.4: "a robustness check, not a search")."""
    rows = []
    for scale in GRID_SCALES:
        for c3 in GRID_C3:
            trades = D.generate_dvp_trades(frames, market, dates, p_ref=p_ref,
                                           loss_rule="total", scale=scale, c3_threshold=c3)
            summary = R.summarize(R.price_all(trades, SCORE_LEVEL))
            rows.append({"scale": scale, "c3_threshold": c3,
                        "n_trades": summary["n_trades"], "net": summary["net"],
                        "is_registered_cell": (scale, c3) == REGISTERED_GRID_CELL})
    n_positive = sum(1 for r in rows if r["net"] > 0)
    return {"cells": rows, "n_positive": n_positive, "n_total": len(rows),
           "share_positive": n_positive / len(rows) if rows else 0.0}


# ---------------------------------------------------------------------
# replication block (sec 7.3): literal points, 2020-01-02 -> 2023-12-29,
# per 1 NQ (not MNQ), at L0 and L2, against Conti's own stated figures.
# ---------------------------------------------------------------------

def _price_trade_full_contract(trade: dict, level: str) -> dict:
    """Like strategy.w16.runner.price_trade, but priced against the FULL
    contract symbol (NQ/ES, $20/$50 per point) instead of always
    converting to the micro -- sec 7.3's replication block is explicitly
    "per 1 NQ", not per 1 MNQ."""
    out = dict(trade)
    market = trade["market"]
    entry_px = trade.get("fill_price", trade.get("entry_price"))
    exit_px = trade["exit_price"]
    direction = trade["direction"]
    gross = pnl_dollars(market, entry_px, exit_px, direction)
    cost = trade_cost(market, level, entry_kind=trade["entry_fill_kind"],
                      exit_kind=trade["exit_fill_kind"])
    out.update(level=level, gross=gross, cost=cost, net=gross - cost)
    return out


def _band_ok(value: float | None, lo: float, hi: float) -> bool | None:
    return None if value is None else (lo <= value <= hi)


def _within_pct(value: float | None, target: float, tol: float = REPL_BAND_TOLERANCE) -> bool | None:
    if value is None:
        return None
    return abs(value - target) <= tol * abs(target)


def run_replication(frames: dict[str, pd.DataFrame], market: str, *, trigger_minutes: int = 5) -> dict:
    """sec 7.3: Conti's LITERAL rule (p_ref=None -- unscaled points), his
    own guardrails, on 2020-01-02 -> 2023-12-29 only, priced per 1 (full)
    NQ/ES contract, at L0 and L2, against his stated figures."""
    dates = [d for d in trading_dates(frames) if REPLICATION_START <= d <= REPLICATION_END]
    trades = D.generate_dvp_trades(frames, market, dates, p_ref=None, loss_rule="total",
                                   scale=1.0, trigger_minutes=trigger_minutes)
    n_trade_days = len({t["date"] for t in trades if not t.get("voided")})
    # Conti's ~2.8/day = >4,000 trades / ~1,410 trading days (2021 -> Aug 2026):
    # per TRADING SESSION, not per day that happened to trade.
    n_days = len(dates)
    out = {"market": market, "trigger_minutes": trigger_minutes,
          "date_range": [REPLICATION_START, REPLICATION_END], "n_trading_sessions": n_days,
          "n_sessions_with_trade_days": n_trade_days}
    for level in ("L0", "L2"):
        # price per 1 FULL contract (NQ/ES) -- strategy.w16.runner.price_trade
        # always converts to the MICRO via FULL_TO_MICRO, which is wrong
        # for this block (sec 7.3: "per 1 NQ"), so price directly here.
        priced_full = [_price_trade_full_contract(t, level) for t in trades if not t.get("voided")]
        s = R.summarize(priced_full)
        trades_per_day = (s["n_trades"] / n_days) if n_days else None
        out[level] = {
            "n_trades": s["n_trades"], "gross": s["gross"], "cost": s["cost"], "net": s["net"],
            "win_rate": (s["wins"] / s["n_trades"]) if s["n_trades"] else None,
            "avg_win": s["avg_win"], "avg_loss": s["avg_loss"], "trades_per_day": trades_per_day,
        }
        if level == "L2":
            win_rate = out[level]["win_rate"]
            out["bands"] = {
                "win_rate_60_68pct": _band_ok(win_rate, *REPL_WIN_RATE_BAND),
                "trades_per_day_1p5_4p0": _band_ok(trades_per_day, *REPL_TRADES_PER_DAY_BAND),
                "avg_win_within_25pct_of_866": _within_pct(s["avg_win"], REPL_AVG_WIN_TARGET),
                "avg_loss_within_25pct_of_1300": _within_pct(s["avg_loss"], REPL_AVG_LOSS_TARGET),
            }
            out["bands"]["all_pass"] = all(v for v in out["bands"].values() if v is not None) and \
                all(v is not None for v in out["bands"].values())
    return out


# ---------------------------------------------------------------------
# reported variants (sec 3.6)
# ---------------------------------------------------------------------

def run_reported_variants(frames: dict[str, pd.DataFrame], market: str, dates, *,
                          p_ref: float | None) -> dict:
    out = {}

    t15 = D.generate_dvp_trades(frames, market, dates, p_ref=p_ref, loss_rule="total",
                                trigger_minutes=15)
    out["trigger_15min"] = R.summarize(R.price_all(t15, SCORE_LEVEL))

    tcons = D.generate_dvp_trades(frames, market, dates, p_ref=p_ref, loss_rule="consecutive")
    out["consecutive_losses"] = R.summarize(R.price_all(tcons, SCORE_LEVEL))

    tnog = D.generate_dvp_trades(frames, market, dates, p_ref=p_ref, loss_rule=None)
    out["no_guardrails"] = R.summarize(R.price_all(tnog, SCORE_LEVEL))

    tlit = D.generate_dvp_trades(frames, market, dates, p_ref=None, loss_rule="total")
    out["literal_points_full_training"] = R.summarize(R.price_all(tlit, SCORE_LEVEL))

    treal = D.generate_dvp_trades(frames, market, dates, p_ref=p_ref, loss_rule="total")
    priced = R.price_all(treal, SCORE_LEVEL)
    out["long_book"] = R.summarize([t for t in priced if t["direction"] == "long"])
    out["short_book"] = R.summarize([t for t in priced if t["direction"] == "short"])

    return out


# ---------------------------------------------------------------------
# orchestration: the scored cell, end to end
# ---------------------------------------------------------------------

def _trades_per_day_stats(priced: list[dict]) -> dict:
    from collections import Counter
    counts = list(Counter(t["date"] for t in priced).values())
    if not counts:
        return {"median": None, "p90": None, "max": None}
    return {"median": float(np.percentile(counts, 50)), "p90": float(np.percentile(counts, 90)),
           "max": int(max(counts))}


def run_backtest(archive, *, spend_holdout: str | None = None,
                 compute_controls_flag: bool = True, n_control_draws: int = N_CONTROL_DRAWS,
                 compute_grid_flag: bool = True, progress: bool = True,
                 include_replication: bool = True, include_reported_variants: bool = True) -> dict:
    market = SCORED_MARKET
    p_ref = require_p_ref(market)
    if spend_holdout and spend_holdout != SCORED_CANDIDATE:
        raise SystemExit(f"only {SCORED_CANDIDATE!r} may spend the DVP-v0 holdout; "
                        f"{spend_holdout!r} cannot.")

    df_1m = load_root_bars(archive, market)
    frames = session_frames(df_1m)
    all_dates = trading_dates(frames)

    if spend_holdout:
        dates, n_held, label = H.split_dates(all_dates, spend=True, candidate=spend_holdout)
    else:
        dates, n_held, label = H.split_dates(all_dates)

    gen = D.generate_dvp_trades_full(frames, market, dates, p_ref=p_ref, loss_rule="total")
    trades = gen["trades"]
    priced_by_level = {lvl: R.price_all(trades, lvl) for lvl in LEVELS}
    l2 = priced_by_level["L2"]
    l3 = priced_by_level["L3"]

    result: dict = {
        "candidate": SCORED_CANDIDATE, "market": market, "date_side": label,
        "p_ref": p_ref, "n_raw_trades": len(trades),
        "n_voided": sum(1 for t in trades if t.get("voided")),
        "n_sessions": gen["n_sessions"], "n_sessions_skipped": gen["n_skipped"],
        "n_days_capped_by_four": gen["n_days_capped_by_four"],
        "n_days_stopped_by_loss": gen["n_days_stopped_by_loss"],
    }

    control_nets = None
    control_summary = None
    c_d2_summary = None
    c_d3_summary = None
    if compute_controls_flag:
        t0 = _time.time()
        control_nets = compute_c_d1(trades, frames, n_draws=n_control_draws, progress=progress)
        c_d1_seconds = _time.time() - t0
        control_summary = {
            "n_draws": len(control_nets), "seconds": c_d1_seconds,
            "p5": float(np.percentile(control_nets, 5)) if control_nets else None,
            "p50": float(np.percentile(control_nets, 50)) if control_nets else None,
            "p95": float(np.percentile(control_nets, 95)) if control_nets else None,
        }
        d2_trades = D.generate_dvp_no_pullback_trades(frames, market, dates, p_ref=p_ref, loss_rule="total")
        c_d2_summary = R.summarize(R.price_all(d2_trades, SCORE_LEVEL))
        c_d3_nets = compute_c_d3(trades, frames, p_ref=p_ref, n_draws=n_control_draws, progress=progress)
        c_d3_summary = {
            "n_draws": len(c_d3_nets),
            "p5": float(np.percentile(c_d3_nets, 5)) if c_d3_nets else None,
            "p50": float(np.percentile(c_d3_nets, 50)) if c_d3_nets else None,
            "p95": float(np.percentile(c_d3_nets, 95)) if c_d3_nets else None,
        }

    neighbour_grid = None
    if compute_grid_flag:
        neighbour_grid = run_neighbour_grid(frames, market, dates, p_ref=p_ref)
    neighbour_grid_share = neighbour_grid["share_positive"] if neighbour_grid else None

    result.update(dvp_score_cell(priced_by_level, control_nets=control_nets,
                                 neighbour_grid_share=neighbour_grid_share))
    result["by_level"] = {lvl: R.summarize(rows) for lvl, rows in priced_by_level.items()}
    l2_by_level = result["by_level"]["L2"]
    result["break_even_win_rate_l2"] = break_even_win_rate(l2_by_level["avg_win"], l2_by_level["avg_loss"])
    result["exit_reasons"] = R.exit_reason_counts(l2)
    result["same_bar_ties"] = sum(1 for t in l2 if t.get("same_bar_tie"))
    result["trades_per_day"] = _trades_per_day_stats(l2)
    result["long_short_split"] = {
        "long": sum(1 for t in l2 if t["direction"] == "long"),
        "short": sum(1 for t in l2 if t["direction"] == "short"),
    }
    result["sample_trades"] = R.sample_trades(l2)
    result["account_view"] = R.account_view(l2, "DVP", market, account_usd=ACCOUNT_USD)
    result["control_summary_c_d1"] = control_summary
    result["control_c_d2_no_pullback"] = c_d2_summary
    result["control_summary_c_d3"] = c_d3_summary
    result["neighbour_grid"] = neighbour_grid

    if include_replication:
        repl = run_replication(frames, market)
        if repl.get("bands", {}).get("all_pass") is False:
            repl["diagnostic_15min_trigger"] = run_replication(frames, market, trigger_minutes=15)
        result["replication"] = repl

    if include_reported_variants:
        variants = run_reported_variants(frames, market, dates, p_ref=p_ref)
        if D.P_REF_ES is not None:
            try:
                df_es = load_root_bars(archive, "ES")
                frames_es = session_frames(df_es)
                es_dates, _, _ = H.split_dates(trading_dates(frames_es))
                es_trades = D.generate_dvp_trades(frames_es, "ES", es_dates, p_ref=D.P_REF_ES,
                                                  loss_rule="total")
                variants["es"] = R.summarize(R.price_all(es_trades, SCORE_LEVEL))
            except Exception as exc:                       # pragma: no cover -- best-effort report
                variants["es"] = {"error": str(exc)}
        else:
            variants["es"] = {"note": "P_REF_ES is None -- ES reported variant skipped"}
        result["reported_variants"] = variants

    return result


def _txt_report(preflight: dict | None, backtest: dict | None) -> str:
    lines: list[str] = []

    def money(v):
        if v is None:
            return "N/A"
        return f"(${abs(v):,.2f})" if v < 0 else f"${v:,.2f}"

    if preflight is not None:
        lines.append("=== W16 DVP-v0 -- PRE-FLIGHT (no P&L) ===")
        for market, m in preflight["markets"].items():
            t = m["totals"]
            lines.append(f"\n{market}: P_ref = {m['p_ref']}")
            lines.append(f"  sessions={t['sessions']}  skipped={t['skipped']}  "
                        f"triggers={t['triggers']}  days_with_trigger={t['days_with_trigger']}")
            lines.append(f"  entries_upper_bound={t['entries_upper_bound']}"
                        f"{'  [<300, NOT READ]' if t['underpowered_below_300'] else ''}")
            lines.append(f"  first-trigger fills: long={t['first_trigger_long']} short={t['first_trigger_short']}")
        lines.append("")

    if backtest is not None:
        lines.append("=== W16 DVP-v0 -- BACKTEST (scored cell DVP-NQ, per 1 MNQ) ===")
        lines.append(f"date side: {backtest['date_side']}")
        lines.append(f"P_ref (NQ): {backtest['p_ref']}")
        lines.append(f"trades: {backtest['n_raw_trades']} raw, {backtest['n_voided']} voided")
        for lvl in ("L1", "L2", "L3"):
            s = backtest["by_level"][lvl]
            lines.append(f"\n[{lvl}] n={s['n_trades']}  wins={s['wins']}  losses={s['losses']}  "
                        f"gross={money(s['gross'])}  cost={money(s['cost'])}  net={money(s['net'])}")
            lines.append(f"      avg_win={money(s['avg_win'])}  avg_loss={money(s['avg_loss'])}  "
                        f"largest_loss={money(s['largest_loss'])}  max_dd={money(s['max_drawdown'])}")
        lines.append(f"\nbreak-even win rate (L2): {backtest['break_even_win_rate_l2']}")
        lines.append(f"exit reasons (L2): {backtest['exit_reasons']}")
        lines.append(f"same-bar ties: {backtest['same_bar_ties']}")
        lines.append(f"trades/day: {backtest['trades_per_day']}")
        lines.append(f"long/short split: {backtest['long_short_split']}")
        lines.append(f"days capped by G-four: {backtest['n_days_capped_by_four']}")
        lines.append(f"days stopped by G-loss: {backtest['n_days_stopped_by_loss']}")
        lines.append("\n--- sec 9 criteria ---")
        for k, v in backtest["criteria"].items():
            lines.append(f"  {k}: {v}")
        if backtest.get("control_summary_c_d1"):
            c = backtest["control_summary_c_d1"]
            lines.append(f"\nC-D1 control (n={c['n_draws']}): p5={money(c['p5'])}  "
                        f"p50={money(c['p50'])}  p95={money(c['p95'])}")
        if backtest.get("neighbour_grid"):
            g = backtest["neighbour_grid"]
            lines.append(f"neighbour grid: {g['n_positive']}/{g['n_total']} cells net-positive at L2")
        if backtest.get("replication"):
            r = backtest["replication"]
            l2r = r.get("L2", {})
            lines.append(f"\nreplication (literal points, {r['date_range'][0]} -> {r['date_range'][1]}, per 1 NQ, L2):")
            lines.append(f"  n_trades={l2r.get('n_trades')}  win_rate={l2r.get('win_rate')}  "
                        f"trades/day={l2r.get('trades_per_day')}")
            lines.append(f"  avg_win={money(l2r.get('avg_win'))}  avg_loss={money(l2r.get('avg_loss'))}  "
                        f"net={money(l2r.get('net'))}")
            lines.append(f"  bands: {r.get('bands')}")
        lines.append(f"\naccount view: {backtest['account_view']}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W16 DVP-v0 runner.")
    ap.add_argument("--archive", type=Path, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--backtest", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-controls", action="store_true",
                    help="Skip C-D1/C-D2/C-D3 -- fast sanity pass.")
    ap.add_argument("--skip-grid", action="store_true",
                    help="Skip the sec 7.4 neighbour grid (9 cells) -- fast sanity pass.")
    ap.add_argument("--n-control-draws", type=int, default=N_CONTROL_DRAWS,
                    help=f"Control draws (registered: {N_CONTROL_DRAWS}).")
    ap.add_argument("--spend-holdout", metavar="CANDIDATE", default=None,
                    help=f"Read the locked holdout side (only {SCORED_CANDIDATE!r} is accepted), "
                         "after a training pass. Never set this to explore.")
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    preflight_report = None
    backtest_report = None

    if a.preflight:
        preflight_report = run_preflight(archive)
        _print_preflight_summary(preflight_report)
    else:
        backtest_report = run_backtest(
            archive, spend_holdout=a.spend_holdout,
            compute_controls_flag=not a.skip_controls, n_control_draws=a.n_control_draws,
            compute_grid_flag=not a.skip_grid)
        s = backtest_report["by_level"]["L2"]
        print(f"DVP-NQ  n={s['n_trades']:5d}  net(L2)=${s['net']:,.2f}  "
             f"passes_all_computed={backtest_report['criteria']['passes_all_computed']}")

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
