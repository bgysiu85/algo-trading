#!/usr/bin/env python3
"""OWA-v0 runner: the pre-flight (G2), the six scored cells with sec 10's nine
criteria, controls C-1..C-3, the neighbour grid, the reported books, sec 12's
output, and the one-time holdout run.
docs/research/REGISTERED_w16_open_window.md. Board W16-0040 sub 4.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.owa_runner --preflight --out "D:\\Trading\\Claude outputs\\w16_0040_preflight.json"
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.owa_runner --backtest --out "D:\\Trading\\Claude outputs\\w16_0040_backtest.json"
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.owa_runner --spend-holdout "<cells>" --out "...holdout.json"

Pricing, criteria and files only -- the rule itself is strategy.w16.
open_window. The nine criteria are strategy.w16.runner.score_cell, unchanged
(the same six-cell, 99% bootstrap bar as BB-v0).

--spend-holdout reads the locked years ONCE. It takes no narrowing option,
computes the training result again in the same run, and refuses -- leaving the
ledger untouched -- unless the cells named are exactly the cells that pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import open_window as OW
from strategy.w16 import owa_controls as C
from strategy.w16 import owa_holdout as H
from strategy.w16 import owa_preflight as PF
from strategy.w16 import runner as R
from strategy.w16.costs import ibkr_round_trip, pnl_dollars

MICRO, FULL = "MNQ", "NQ"
VEHICLES = (MICRO, FULL)
REPORT_LEVELS = ("L0", "L1", "L2", "L3")
SCORE_LEVEL = "L2"
MIN_TRADES = R.MIN_TRADES                       # 300
ACCOUNT_USD = R.ACCOUNT_USD                     # $22,129
N_DRAWS = C.N_DRAWS                             # 1000
PF_ALARM, PF_ALARM_TRADES = 3.0, 1000
HOLDOUT_PER_TRADE_SHARE = 1.0 / 3.0

GRID_BIG_MULT = (1.25, 1.50, 1.75)
GRID_TRAIL = (2.0, 2.5, 3.0)
GRID_MACD_K = (2, 3, 4)

CRITERIA_TEXT = {
    "1_net_positive": "1 net > 0",
    "2_both_halves_positive": "2 both halves > 0",
    "3_no_year_over_50pct": "3 no year over 50% of net",
    "4_month_bootstrap": "4 month bootstrap >= 99%",
    "5_beats_control": "5 beats C-1 p95",
    "6_net_positive_at_l3": "6 net > 0 at L3",
    "7_survives_dropping_best_1pct": "7 net > 0 without best 1%",
    "8_neighbour_grid_6_of_9": "8 at least 6 of 9 neighbours > 0",
    "9_min_trades": "9 at least 300 trades",
}


# ---------------------------------------------------------------------
# data
# ---------------------------------------------------------------------

def training_cut(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Drop every bar dated owa_holdout.TRAINING_DATA_BEFORE or later (New
    York date) before anything is computed from it."""
    cutoff = pd.Timestamp(H.TRAINING_DATA_BEFORE, tz=OW.ET).tz_convert("UTC")
    return df_1m[np.asarray(df_1m.index < cutoff)]


def load_nq(archive) -> pd.DataFrame:
    from strategy.w16.preflight import load_root_bars
    return load_root_bars(archive, "NQ")


def data_fingerprint(archive) -> dict:
    from strategy.w16.fetch import bar_path
    path = bar_path(Path(archive), "NQ", "ohlcv-1m")
    if not path.exists():
        return {"file": str(path), "sha256": None}
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return {"file": str(path), "sha256": digest.hexdigest()}


def split(mk, **kwargs):
    return H.split_dates([d.date for d in mk.days], **kwargs)


# ---------------------------------------------------------------------
# pricing and statistics
# ---------------------------------------------------------------------

def price(trades: list[dict], level: str, vehicle: str = MICRO) -> list[dict]:
    """Non-voided trades with gross / cost / net for one contract."""
    cost = ibkr_round_trip(vehicle, level)
    out = []
    for t in trades:
        if t["voided"]:
            continue
        gross = pnl_dollars(vehicle, t["fill_price"], t["exit_price"], t["direction"])
        out.append(dict(t, level=level, vehicle=vehicle, gross=gross, cost=cost, net=gross - cost))
    return out


def worst_runs(nets: list[float]) -> dict:
    """Longest run of consecutive losing trades, and the largest $ lost in one
    unbroken run of losers (a $0 trade counts as a loser, as in summarize)."""
    longest = count = 0
    worst = total = 0.0
    for n in nets:
        if n <= 0:
            count += 1
            total += n
        else:
            count, total = 0, 0.0
        longest = max(longest, count)
        worst = min(worst, total)
    return {"longest_losing_run": longest, "worst_losing_run_usd": worst}


def max_drawdown(nets: list[float]) -> float:
    """Largest fall of the closed-trade equity curve from a peak, the start
    (0) counting as the first peak. 0 or negative."""
    if not nets:
        return 0.0
    equity = np.concatenate(([0.0], np.cumsum(nets)))
    return float((equity - np.maximum.accumulate(equity)).min())


def stats(priced: list[dict]) -> dict:
    """sec 12's figures for one book at one level."""
    s = R.summarize(priced)
    n = s["n_trades"]
    nets = [t["net"] for t in priced]
    day_net: dict[str, float] = {}
    month_net: dict[str, float] = {}
    for t in priced:
        day_net[t["date"]] = day_net.get(t["date"], 0.0) + t["net"]
        month_net[t["date"][:7]] = month_net.get(t["date"][:7], 0.0) + t["net"]
    s.update(worst_runs(nets))
    s["win_rate"] = s["wins"] / n if n else None
    s["avg_net_per_trade"] = s["net"] / n if n else None
    s["max_drawdown"] = max_drawdown(nets)
    s["max_drawdown_pct_of_account"] = abs(s["max_drawdown"]) / ACCOUNT_USD * 100.0
    s["worst_day"] = (min(day_net.items(), key=lambda kv: kv[1]) if day_net else None)
    s["worst_month"] = (min(month_net.items(), key=lambda kv: kv[1]) if month_net else None)
    s["avg_hold_minutes"] = float(np.mean([t["hold_minutes"] for t in priced])) if n else None
    return s


def profit_factor(priced: list[dict]) -> float | None:
    won = sum(t["net"] for t in priced if t["net"] > 0)
    lost = -sum(t["net"] for t in priced if t["net"] <= 0)
    return won / lost if lost > 0 else None


def split_by(priced: list[dict], key) -> dict:
    groups: dict[str, list] = {}
    for t in priced:
        groups.setdefault(key(t), []).append(t)
    return {k: stats(v) for k, v in sorted(groups.items())}


def sample_rows(priced: list[dict], n: int = 20) -> list[dict]:
    keep = ("date", "direction", "trigger", "signal_bar", "fill_time", "fill_price", "stop",
            "exit_time", "exit_price", "exit_reason", "net")
    return [{k: t[k] for k in keep} for t in R.sample_trades(priced, n)]


def book_summary(book: dict) -> dict:
    """The short form used for reported books."""
    out = {"voided": sum(t["voided"] for t in book["trades"]),
           "dropped_no_fill_bar": len(book["dropped"])}
    for level in ("L1", "L2", "L3"):
        out[level] = stats(price(book["trades"], level))
    return out


def trade_report(trades: list[dict]) -> dict:
    """Everything in sec 12 that comes from the trade list alone."""
    levels = {v: {lvl: stats(price(trades, lvl, v)) for lvl in REPORT_LEVELS} for v in VEHICLES}
    l2 = price(trades, SCORE_LEVEL)
    mid = R.both_halves(l2)["split_date"]                   # the median trade date (sec 10 #2)
    return {
        "n_trades": len(l2),
        "voided": sum(t["voided"] for t in trades),
        "time_exit_without_flat_bar": sum(t["exit_reason"] == "time_no_bar" for t in trades),
        "levels": levels,
        "by_year": split_by(l2, lambda t: t["date"][:4]),
        "by_year_full_contract": split_by(price(trades, SCORE_LEVEL, FULL),
                                          lambda t: t["date"][:4]),
        "halves": {"split_date": mid,
                   "early": stats([t for t in l2 if t["date"] < mid]),
                   "late": stats([t for t in l2 if t["date"] >= mid])},
        "long_vs_short": split_by(l2, lambda t: t["direction"]),
        "pre_open_vs_rth": split_by(l2, lambda t: "pre_open" if t["pre_open"] else "rth"),
        "exit_reasons": {r: {"trades": s["n_trades"], "net": s["net"]}
                         for r, s in split_by(l2, lambda t: t["exit_reason"]).items()},
        "bootstrap": R.bootstrap_by_month(l2),
        "net_without_best_1pct": R.drop_best_pct(l2)["net"],
        "profit_factor": profit_factor(l2),
        "sample_trades": sample_rows(l2),
    }


# ---------------------------------------------------------------------
# neighbour grid (sec 8.3)
# ---------------------------------------------------------------------

def grid_cells(trigger: str):
    """The nine (label, Params) cells; the registered one is in the middle."""
    out = []
    for trail in GRID_TRAIL:
        if trigger == "C":
            for k in GRID_MACD_K:
                out.append(({"macd_k": k, "trail": trail}, OW.Params(macd_k=k, trail_mult=trail)))
        else:
            for big in GRID_BIG_MULT:
                out.append(({"big_mult": big, "trail": trail},
                            OW.Params(big_mult=big, trail_mult=trail)))
    return out


def run_grid(mk, trigger: str, filter_name: str, dates) -> dict:
    rows = []
    cache: dict = {}
    for label, params in grid_cells(trigger):
        key = (params.big_mult, params.macd_k)
        if key not in cache:
            cache[key] = OW.compute_signals(mk, filter_name, params)
        book = OW.simulate_book(mk, cache[key], trigger, dates, params=params)
        s = R.summarize(price(book["trades"], SCORE_LEVEL))
        rows.append(dict(label, n_trades=s["n_trades"], net=s["net"],
                         is_registered_cell=params == OW.REGISTERED))
    n_positive = sum(r["net"] > 0 for r in rows)
    return {"cells": rows, "n_positive": n_positive, "n_total": len(rows),
            "share_positive": n_positive / len(rows)}


# ---------------------------------------------------------------------
# one scored cell
# ---------------------------------------------------------------------

def verdict(criteria: dict, n_trades: int, complete: bool) -> str:
    if not complete:
        return "INCOMPLETE (quick look: controls or grid skipped or short) -- not a verdict"
    if n_trades < MIN_TRADES:
        return f"NOT READ ({n_trades} trades, fewer than {MIN_TRADES})"
    failed = [k.split("_")[0] for k in CRITERIA_TEXT if criteria[k] is not True]
    return "PASS" if not failed else f"FAIL (criteria {', '.join(failed)})"


def run_cell(mk, trigger: str, filter_name: str, dates, *, controls: bool = True,
             grid: bool = True, n_draws: int = N_DRAWS, reported: bool = True,
             log=lambda msg: None) -> dict:
    name = PF.cell_name(trigger, filter_name)
    sig = OW.compute_signals(mk, filter_name)
    book = OW.simulate_book(mk, sig, trigger, dates)
    trades = book["trades"]
    result = {"cell": name, "dropped_no_fill_bar": len(book["dropped"])}
    result.update(trade_report(trades))
    priced = {lvl: price(trades, lvl) for lvl in ("L1", "L2", "L3")}

    c1 = None
    if controls:
        net = result["levels"][MICRO][SCORE_LEVEL]["net"]
        log(f"  {name}: C-1 random later timing, {n_draws} draws")
        c1 = C.c1_totals(mk, trades, n_draws=n_draws)
        log(f"  {name}: C-2 random long")
        c2 = C.c2_totals(mk, trades, n_draws=n_draws)
        log(f"  {name}: C-3 random side")
        c3 = C.c3_totals(mk, trades, n_draws=n_draws)
        result["controls"] = {"C1": C.summarise(c1, net), "C2": C.summarise(c2, net),
                              "C3": C.summarise(c3, net),
                              "C2_median_stop_atr": C.median_stop_atr(trades)}
    grid_result = None
    if grid:
        log(f"  {name}: neighbour grid")
        grid_result = run_grid(mk, trigger, filter_name, dates)
    result["grid"] = grid_result

    scored = R.score_cell(priced, control_nets=None if c1 is None else list(c1),
                          neighbour_grid_share=None if grid_result is None
                          else grid_result["share_positive"])
    criteria = scored["criteria"]
    result["criteria"] = criteria
    result["max_year_share_of_net"] = scored["max_year_share_of_net"]
    complete = controls and grid and n_draws == N_DRAWS
    result["verdict"] = verdict(criteria, result["n_trades"], complete)
    result["profit_factor_alarm"] = bool(
        result["profit_factor"] is not None and result["profit_factor"] > PF_ALARM
        and result["n_trades"] >= PF_ALARM_TRADES)

    if reported:
        log(f"  {name}: reported books")
        result["reported_books"] = {
            "long_only": book_summary(OW.simulate_book(mk, sig, trigger, dates, sides=(OW.LONG,))),
            "short_only": book_summary(OW.simulate_book(mk, sig, trigger, dates,
                                                        sides=(OW.SHORT,))),
            "signal_close_fills": book_summary(OW.simulate_book(mk, sig, trigger, dates,
                                                                at_signal_close=True)),
            "no_daily_cap": book_summary(OW.simulate_book(mk, sig, trigger, dates, max_fills=None)),
        }
    return result


def all_books(mk, dates) -> dict:
    """Reported, never scored: A or B or C, first in that order, per filter."""
    out = {}
    for filter_name in OW.FILTERS:
        sig = OW.compute_signals(mk, filter_name)
        book = OW.simulate_book(mk, sig, OW.ALL_BOOK, dates)
        summary = book_summary(book)
        summary["by_trigger"] = {
            k: {"trades": s["n_trades"], "net": s["net"]}
            for k, s in split_by(price(book["trades"], SCORE_LEVEL), lambda t: t["trigger"]).items()}
        out[PF.cell_name(OW.ALL_BOOK, filter_name)] = summary
    return out


def run_backtest(mk, dates, side_label: str, *, controls: bool = True, grid: bool = True,
                 n_draws: int = N_DRAWS, log=lambda msg: None) -> dict:
    cells = {}
    for filter_name in OW.FILTERS:                    # table order of sec 6, never ranked
        for trigger in OW.TRIGGERS:
            name = PF.cell_name(trigger, filter_name)
            log(f"running {name}")
            cells[name] = run_cell(mk, trigger, filter_name, dates, controls=controls, grid=grid,
                                   n_draws=n_draws, log=log)
    log("running the All books (reported)")
    wanted = set(dates)
    return {
        "study": "W16-0040 OWA-v0 backtest",
        "side": side_label,
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "days": {k: sum(1 for d in mk.days if d.status == k and d.date in wanted)
                 for k in ("tradable", "skipped", "warmup")},
        "complete": controls and grid and n_draws == N_DRAWS,
        "n_control_draws": n_draws if controls else 0,
        "cells": cells,
        "all_books": all_books(mk, dates),
        "passing_cells": [n for n, c in cells.items() if c["verdict"] == "PASS"],
    }


# ---------------------------------------------------------------------
# holdout (sec 9)
# ---------------------------------------------------------------------

def holdout_bar(cell: dict, training_cell: dict) -> dict:
    micro = cell["levels"][MICRO]
    l2 = micro["L2"]
    train_per_trade = training_cell["levels"][MICRO]["L2"]["avg_net_per_trade"]
    per_trade = l2["avg_net_per_trade"]
    checks = {
        "net_positive": l2["net"] > 0,
        "per_trade_at_least_a_third_of_training": bool(
            per_trade is not None and per_trade >= train_per_trade * HOLDOUT_PER_TRADE_SHARE),
        "beats_c1_p95": bool(cell["controls"]["C1"]["p95"] is not None
                             and l2["net"] > cell["controls"]["C1"]["p95"]),
        "net_positive_at_l3": micro["L3"]["net"] > 0,
    }
    return {"checks": checks, "cleared": all(checks.values()),
            "training_net_per_trade": train_per_trade, "holdout_net_per_trade": per_trade}


def run_holdout(df_full: pd.DataFrame, expected: list[str], *, log=lambda msg: None) -> dict:
    """The one holdout run. Training is computed again from the cut data; the
    ledger is written before any indicator is computed on a locked bar."""
    H.refuse_if_spent()
    mk_train = OW.prepare(training_cut(df_full))
    dates, _, label = split(mk_train)
    training = run_backtest(mk_train, dates, label, log=log)
    passing = training["passing_cells"]
    if not passing:
        raise H.HoldoutRefused("no cell passes sec 10 on training; the holdout is not read.")
    if sorted(expected) != sorted(passing):
        raise H.HoldoutRefused(
            f"the cells named {sorted(expected)} are not the cells that pass training in this "
            f"run {sorted(passing)}. The holdout is spent once, for every passing cell and no "
            "other. Nothing has been spent.")
    ny = df_full.index.tz_convert(OW.ET)                           # timestamps only
    calendar = OW.trading_calendar(OW.day_number(ny.min().strftime("%Y-%m-%d")),
                                   OW.day_number(ny.max().strftime("%Y-%m-%d")))
    H.split_dates([s for _, s, _ in calendar], spend=True, cells=passing)   # writes the ledger
    log(f"holdout ledger written for {passing}: {H.LEDGER_PATH}")
    mk_full = OW.prepare(df_full)
    locked = [d.date for d in mk_full.days if H.is_locked(d.date)]
    cells = {}
    for name in passing:
        trigger, filter_name = name.split("-")
        log(f"holdout {name}")
        cell = run_cell(mk_full, trigger, filter_name, locked, controls=True, grid=False,
                        reported=False, log=log)
        for k in ("criteria", "verdict", "max_year_share_of_net", "grid"):
            cell.pop(k, None)                   # sec 10 is not applied to the holdout
        cell["holdout_bar"] = holdout_bar(cell, training["cells"][name])
        cells[name] = cell
    return {
        "study": "W16-0040 OWA-v0 HOLDOUT (spent once)",
        "side": f"LOCKED, from {H.LOCK_FROM}",
        "first_date": min(locked) if locked else None,
        "last_date": max(locked) if locked else None,
        "cells": cells,
        "cleared": [n for n, c in cells.items() if c["holdout_bar"]["cleared"]],
        "training": training,
    }


# ---------------------------------------------------------------------
# text report: dollars, negatives in brackets, nothing ranked
# ---------------------------------------------------------------------

def money(v) -> str:
    if v is None:
        return "-"
    return f"(${abs(v):,.0f})" if v < 0 else f"${v:,.0f}"


def money2(v) -> str:
    if v is None:
        return "-"
    return f"(${abs(v):,.2f})" if v < 0 else f"${v:,.2f}"


def _pct_text(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def _level_lines(levels: dict) -> list[str]:
    out = [f"  {'':<8}{'trades':>7}{'wins':>6}{'losses':>7}{'win%':>7}{'gross':>12}{'costs':>11}"
           f"{'net':>12}{'avg win':>10}{'avg loss':>10}{'worst':>10}{'max DD':>12}{'DD %':>7}"]
    for vehicle in VEHICLES:
        for lvl in REPORT_LEVELS:
            s = levels[vehicle][lvl]
            out.append(f"  {vehicle + ' ' + lvl:<8}{s['n_trades']:>7}{s['wins']:>6}{s['losses']:>7}"
                       f"{_pct_text(s['win_rate']):>7}{money(s['gross']):>12}{money(s['cost']):>11}"
                       f"{money(s['net']):>12}{money(s['avg_win']):>10}{money(s['avg_loss']):>10}"
                       f"{money(s['largest_loss']):>10}{money(s['max_drawdown']):>12}"
                       f"{s['max_drawdown_pct_of_account']:>6.1f}%")
    return out


def _risk_lines(levels: dict) -> list[str]:
    out = []
    for vehicle in VEHICLES:
        for lvl in ("L1", "L2", "L3"):
            s = levels[vehicle][lvl]
            day, month = s["worst_day"], s["worst_month"]
            out.append(f"  {vehicle} {lvl}: longest losing run {s['longest_losing_run']} trades; "
                       f"worst losing run {money(s['worst_losing_run_usd'])}; worst day "
                       f"{'-' if not day else day[0] + ' ' + money(day[1])}; worst month "
                       f"{'-' if not month else month[0] + ' ' + money(month[1])}")
    return out


def _split_line(label: str, s: dict, width: int = 12) -> str:
    return (f"  {label:<{width}}trades {s['n_trades']:>6}  win {_pct_text(s['win_rate']):>6}  "
            f"net {money(s['net']):>11}  per trade {money2(s['avg_net_per_trade']):>10}")


def cell_text(cell: dict) -> list[str]:
    out = ["", "=" * 100, f"CELL {cell['cell']}"
           + (f"   VERDICT: {cell['verdict']}" if "verdict" in cell else "")]
    if cell.get("profit_factor_alarm"):
        out.append(f"*** PROFIT FACTOR ALARM: {cell['profit_factor']:.2f} over {cell['n_trades']} "
                   "trades -- audit before the Result doc ***")
    out.append(f"trades {cell['n_trades']}   voided {cell['voided']}   dropped (no fill bar) "
               f"{cell['dropped_no_fill_bar']}   time exit with no flat bar "
               f"{cell['time_exit_without_flat_bar']}")
    if "criteria" in cell:
        out.append("criteria (L2, 1 MNQ): " + "; ".join(
            f"{text}: {({True: 'yes', False: 'NO', None: 'not run'})[cell['criteria'][key]]}"
            for key, text in CRITERIA_TEXT.items()))
    out += _level_lines(cell["levels"]) + _risk_lines(cell["levels"])
    hold = cell["levels"][MICRO]["L2"]["avg_hold_minutes"]
    out.append(f"  average holding time {'-' if hold is None else f'{hold:.0f} minutes'}")
    out.append(f"  month bootstrap: net > 0 in {_pct_text(cell['bootstrap']['pct_net_positive'])} "
               f"of {cell['bootstrap']['n_draws']}; net without best 1% of trades "
               f"{money(cell['net_without_best_1pct'])}; largest year / net "
               f"{_pct_text(cell.get('max_year_share_of_net'))}")
    out.append("calendar years (L2, 1 MNQ | 1 NQ net):")
    for y, s in cell["by_year"].items():
        out.append(_split_line(y, s) + f"  | NQ {money(cell['by_year_full_contract'][y]['net']):>12}")
    out.append(f"halves (split {cell['halves']['split_date']}), sides, session (L2, 1 MNQ):")
    out.append(_split_line("first half", cell["halves"]["early"]))
    out.append(_split_line("second half", cell["halves"]["late"]))
    for k, s in cell["long_vs_short"].items():
        out.append(_split_line(k, s))
    for k, s in cell["pre_open_vs_rth"].items():
        out.append(_split_line({"pre_open": "fill <09:30", "rth": "fill 09:30+"}[k], s))
    labels = {"initial_stop": "initial stop", "trail_stop": "trailed stop", "time": "time exit",
              "time_no_bar": "time, no bar"}
    out.append("exit reasons (L2): " + "; ".join(
        f"{labels[r]} {v['trades']} trades {money(v['net'])}"
        for r, v in cell["exit_reasons"].items()))
    if "controls" in cell:
        names = {"C1": "C-1 random later timing (scored)", "C2": "C-2 random long",
                 "C3": "C-3 random side"}
        for key, label in names.items():
            s = cell["controls"][key]
            out.append(f"  {label}: p5 {money(s['p5'])}  p50 {money(s['p50'])}  p95 "
                       f"{money(s['p95'])}  (draws below the real net: "
                       f"{_pct_text(s.get('share_of_draws_below_real'))})")
    if cell.get("grid"):
        g = cell["grid"]
        out.append(f"neighbour grid, net at L2: {g['n_positive']} of {g['n_total']} above $0")
        for row in g["cells"]:
            knobs = ", ".join(f"{k} {v}" for k, v in row.items()
                              if k in ("big_mult", "macd_k", "trail"))
            out.append(f"  {knobs:<26} trades {row['n_trades']:>6}  net {money(row['net']):>11}"
                       + ("   <- registered" if row["is_registered_cell"] else ""))
    if cell.get("reported_books"):
        out.append("reported books (never scored):")
        for k, b in cell["reported_books"].items():
            out.append(_split_line(k.replace("_", " "), b["L2"], width=20)
                       + f"  L1 {money(b['L1']['net'])}  L3 {money(b['L3']['net'])}")
    out.append("20 sample trades (L2, 1 MNQ):")
    for t in cell["sample_trades"]:
        out.append(f"  {t['date']} {t['direction']:<5} {t['trigger']} bar {t['signal_bar']} fill "
                   f"{t['fill_time'][11:]} @ {t['fill_price']:.2f} stop {t['stop']:.2f} exit "
                   f"{t['exit_time'][11:]} @ {t['exit_price']:.2f} {t['exit_reason']:<12} "
                   f"{money2(t['net'])}")
    return out


def backtest_text(report: dict) -> str:
    out = [report["study"].upper(),
           f"side: {report['side']}   dates {report['first_date']} .. {report['last_date']}",
           f"days: {report['days']}   control draws: {report['n_control_draws']}",
           "All $ per ONE contract; negatives in brackets. L2 (fee + 1 tick per fill) scores. "
           "Nothing is ranked."]
    if not report["complete"]:
        out.append("*** QUICK LOOK: controls or grid skipped or short. Not a verdict. ***")
    for cell in report["cells"].values():
        out += cell_text(cell)
    out += ["", "=" * 100, "ALL BOOKS (A or B or C, first in that order) -- reported, never scored"]
    for name, b in report["all_books"].items():
        out.append(_split_line(name, b["L2"]) + f"  L1 {money(b['L1']['net'])}  L3 "
                   f"{money(b['L3']['net'])}  by trigger " + ", ".join(
                       f"{k} {v['trades']} {money(v['net'])}" for k, v in b["by_trigger"].items()))
    out += ["", f"cells passing sec 10: {report['passing_cells'] or 'none'}"]
    return "\n".join(out) + "\n"


def holdout_text(report: dict) -> str:
    out = [report["study"].upper(),
           f"side: {report['side']}   dates {report['first_date']} .. {report['last_date']}"]
    for name, cell in report["cells"].items():
        out += cell_text(cell)
        bar = cell["holdout_bar"]
        out.append(f"HOLDOUT BAR {name}: {'CLEARED' if bar['cleared'] else 'NOT CLEARED'}  "
                   + "; ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in bar["checks"].items())
                   + f"  (per trade {money2(bar['holdout_net_per_trade'])} vs training "
                     f"{money2(bar['training_net_per_trade'])})")
    out += ["", f"cells clearing the holdout bar: {report['cleared'] or 'none'}",
            f"Commit {H.LEDGER_PATH.name}: the holdout is spent."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------

def write_outputs(out: Path, report: dict, text: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    txt = out.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    print(f"\nfull report:  {out}\nread this:    {txt}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="W16-0040 OWA-v0 runner.", allow_abbrev=False)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="G2: counts only, no P&L.")
    mode.add_argument("--backtest", action="store_true", help="Training side, 2010-2023.")
    mode.add_argument("--spend-holdout", metavar="CELLS", default=None,
                      help="ONE TIME ONLY. Comma-separated list of EVERY cell that passed "
                           f"training, from {', '.join(H.CELLS)}.")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None,
                    help="JSON report path; a .txt summary is written beside it.")
    ap.add_argument("--skip-controls", action="store_true",
                    help="--backtest only: no controls (quick look, no verdict).")
    ap.add_argument("--skip-grid", action="store_true",
                    help="--backtest only: no neighbour grid (quick look, no verdict).")
    ap.add_argument("--n-control-draws", type=int, default=N_DRAWS,
                    help=f"--backtest only: fewer than {N_DRAWS} is a quick look, no verdict.")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    narrowed = a.skip_controls or a.skip_grid or a.n_control_draws != N_DRAWS
    if narrowed and not a.backtest:
        ap.error("--skip-controls, --skip-grid and --n-control-draws apply to --backtest only; "
                 "the holdout is read in full or not at all")
    if a.n_control_draws < 1:
        ap.error("--n-control-draws must be at least 1")
    if a.spend_holdout is not None:
        H.refuse_if_spent()
        if a.out is None:
            ap.error("--spend-holdout needs --out: the one run must leave its report on disk")
        a.out.parent.mkdir(parents=True, exist_ok=True)       # prove it is writable first
        probe = a.out.with_suffix(".probe")
        probe.write_text("writable\n", encoding="utf-8")
        probe.unlink()

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()
    started = time.time()

    def log(msg):
        print(f"[{time.time() - started:6.0f}s] {msg}", flush=True)

    log(f"loading NQ 1-minute bars from {archive}")
    df = load_nq(archive)

    if a.spend_holdout is not None:
        expected = [c.strip() for c in a.spend_holdout.split(",") if c.strip()]
        report = run_holdout(df, expected, log=log)
        report["data"] = data_fingerprint(archive)
        text = holdout_text(report)
    else:
        df = training_cut(df)
        log(f"{len(df):,} training bars; preparing indicators")
        mk = OW.prepare(df)
        dates, _, label = split(mk)
        if a.preflight:
            report = PF.run_preflight(mk, dates, label)
            report["data"] = data_fingerprint(archive)
            text = PF.text_report(report)
        else:
            report = run_backtest(mk, dates, label, controls=not a.skip_controls,
                                  grid=not a.skip_grid, n_draws=a.n_control_draws, log=log)
            report["data"] = data_fingerprint(archive)
            text = backtest_text(report)

    if a.out:                      # on disk before anything else can go wrong
        write_outputs(a.out, report, text)
    print()
    if a.preflight or a.spend_holdout is not None:
        print(text)
    else:
        for name, c in report["cells"].items():
            print(f"{name:6s} trades {c['n_trades']:6d}  net(L2, 1 MNQ) "
                  f"{money(c['levels'][MICRO]['L2']['net']):>12}  {c['verdict']}")
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
