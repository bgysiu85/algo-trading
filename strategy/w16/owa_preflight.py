#!/usr/bin/env python3
"""G2 -- the OWA-v0 pre-flight: training side, NO P&L.
REGISTERED_w16_open_window.md sec 7.1. Board W16-0040 sub 4.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.owa_runner --preflight

"No exit price is read." This module calls the signal code and the entry
fill, runs each book with `exits=False` (which never calls the exit walk --
a test replaces the walk with a function that raises), and imports only the
$-per-point table, to turn a stop DISTANCE into dollars.

WHAT IT CANNOT KNOW
------------------------------------------------------------------------
The two-fill cap and re-entry depend on exits. So it reports first fills per
day (exact: a day's first fill does not depend on any exit) and, beside them,
the days with two or more fillable signals (an upper bound on days at the
cap) and bounds on the trade count:
    lower = days with a first fill, upper = sum over days of min(2, fillable).
After the first fill, trigger B's arming is not reset again here, so B's later
signal counts are slightly higher than the backtest will see.
"""
from __future__ import annotations

import numpy as np

from strategy.w16 import open_window as OW
from strategy.w16.costs import POINT_VALUE

VEHICLE = "MNQ"
MIN_TRADES = 300
STOP_YEARS = ("2010", "2016", "2023")
LATE_MIN = 11 * 60 + 30


def cell_name(trigger: str, filter_name: str) -> str:
    return f"{trigger}-{filter_name}"


def _pct(values, q: float):
    return float(np.percentile(values, q)) if len(values) else None


def common_by_year(mk, dates) -> dict:
    """What does not depend on a trigger: days, data, big bars, filter share."""
    wanted = set(dates)
    out: dict[str, dict] = {}
    windows: dict[str, list] = {}
    for day in mk.days:
        if day.date not in wanted:
            continue
        y = day.date[:4]
        row = out.setdefault(y, {"trading_days": 0, "tradable": 0, "skipped": 0, "warmup": 0,
                                 "early_close_days": 0, "days_with_contract_change_in_window": 0})
        row["trading_days"] += 1
        row[day.status] += 1
        if day.status != "tradable":
            continue
        row["early_close_days"] += int(day.early)
        row["days_with_contract_change_in_window"] += int(day.roll_inside)
        windows.setdefault(y, []).append(day.window)

    filters = {name: OW.compute_signals(mk, name) for name in OW.FILTERS}
    big = filters["1H"].big            # the big bar does not depend on the filter
    up, dn = filters["1H"].big_up, filters["1H"].big_dn
    for y, row in out.items():
        idx = (np.concatenate(windows[y]).astype(np.int64) if y in windows
               else np.empty(0, dtype=np.int64))
        n_days = row["tradable"]
        row["window_bars"] = int(len(idx))
        row["big_bars_per_day"] = float(big[idx].sum() / n_days) if n_days else None
        row["big_green_per_day"] = float(up[idx].sum() / n_days) if n_days else None
        row["big_red_per_day"] = float(dn[idx].sum() / n_days) if n_days else None
        row["big_bar_share_of_window_bars"] = float(big[idx].mean()) if len(idx) else None
        for name in OW.FILTERS:
            state = mk.filt[name][idx]
            row[f"filter_{name}_share"] = (
                {"UP": float((state == OW.UP).mean()), "DOWN": float((state == OW.DOWN).mean()),
                 "NONE": float((state == OW.NONE).mean())} if len(idx) else None)
    return dict(sorted(out.items()))


def _empty_cell_year() -> dict:
    return {"signals_long": 0, "signals_short": 0, "dropped_no_fill_bar": 0,
            "first_fills_long": 0, "first_fills_short": 0,
            "first_fills_pre_open": 0, "first_fills_rth": 0, "first_fills_1130_or_later": 0,
            "days_with_2plus_fillable_signals": 0, "trades_upper_bound": 0}


def cell_preflight(mk, trigger: str, filter_name: str, dates) -> dict:
    sig = OW.compute_signals(mk, filter_name)
    book = OW.simulate_book(mk, sig, trigger, dates, exits=False)
    by_year: dict[str, dict] = {}

    def row(date):
        return by_year.setdefault(date[:4], _empty_cell_year())

    for d in book["days"]:
        r = row(d["date"])
        r["days_with_2plus_fillable_signals"] += int(d["fillable_signals"] >= 2)
        r["trades_upper_bound"] += min(OW.MAX_FILLS_PER_DAY, d["fillable_signals"])
    for s in book["signals"]:
        r = row(s["date"])
        r[f"signals_{s['direction']}"] += 1
        r["dropped_no_fill_bar"] += int(not s["fillable"])
    stops: dict[str, list[float]] = {}
    for f in book["trades"]:                       # first fills only (exits=False)
        r = row(f["date"])
        r[f"first_fills_{f['direction']}"] += 1
        pre = f["fill_minute"] < OW.RTH_OPEN_MIN
        r["first_fills_pre_open" if pre else "first_fills_rth"] += 1
        r["first_fills_1130_or_later"] += int(f["fill_minute"] >= LATE_MIN)
        stops.setdefault(f["date"][:4], []).append(f["stop_dist"] * POINT_VALUE[VEHICLE])

    totals = _empty_cell_year()
    for r in by_year.values():
        for k in totals:
            totals[k] += r[k]
    lower = len(book["trades"])
    upper = totals["trades_upper_bound"]
    if upper < MIN_TRADES:
        read = "NOT READ (fewer than 300 trades whatever the exits do)"
    elif lower >= MIN_TRADES:
        read = "will be read (300+ trades whatever the exits do)"
    else:
        read = "depends on the exits"
    return {
        "cell": cell_name(trigger, filter_name),
        "by_year": dict(sorted(by_year.items())),
        "totals": totals,
        "trades_lower_bound": lower,
        "trades_upper_bound": upper,
        "read_status": read,
        "initial_stop_usd_per_mnq": {
            y: {"n": len(stops.get(y, [])), "median": _pct(stops.get(y, []), 50),
                "p90": _pct(stops.get(y, []), 90),
                "max": max(stops[y]) if stops.get(y) else None}
            for y in STOP_YEARS},
    }


def run_preflight(mk, dates, side_label: str) -> dict:
    cells = {}
    for filter_name in OW.FILTERS:
        for trigger in OW.TRIGGERS:
            cells[cell_name(trigger, filter_name)] = cell_preflight(mk, trigger, filter_name, dates)
    return {
        "study": "W16-0040 OWA-v0 pre-flight (G2) -- no P&L, no exit price read",
        "side": side_label,
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "common_by_year": common_by_year(mk, dates),
        "cells": cells,
        "note": ("The two-fill cap and re-entry depend on exits: the backtest's trade counts "
                 "will differ from the first fills here and lie between the two bounds."),
    }


def _share(d: dict | None) -> str:
    if not d:
        return "-"
    return "/".join(f"{d[k] * 100:.0f}" for k in ("UP", "DOWN", "NONE"))


def _num(v, places: int = 2) -> str:
    return "-" if v is None else f"{v:.{places}f}"


def text_report(report: dict) -> str:
    out = ["W16-0040 OWA-v0 PRE-FLIGHT (G2) -- NO P&L, NO EXIT PRICE READ",
           f"side: {report['side']}   dates {report['first_date']} .. {report['last_date']}", ""]
    out.append("DAYS, BIG BARS (08:00-12:00) AND TREND-FILTER SHARE (UP/DOWN/NONE %)")
    out.append(f"{'year':<6}{'days':>6}{'trade':>7}{'skip':>6}{'warm':>6}{'early':>6}{'rolls':>6}"
               f"{'big/day':>9}{'big share':>11}{'1H U/D/N':>12}{'15m U/D/N':>12}")
    for y, r in report["common_by_year"].items():
        share = r["big_bar_share_of_window_bars"]
        out.append(f"{y:<6}{r['trading_days']:>6}{r['tradable']:>7}{r['skipped']:>6}{r['warmup']:>6}"
                   f"{r['early_close_days']:>6}{r['days_with_contract_change_in_window']:>6}"
                   f"{_num(r['big_bars_per_day']):>9}"
                   f"{('-' if share is None else f'{share * 100:.1f}%'):>11}"
                   f"{_share(r['filter_1H_share']):>12}{_share(r['filter_15_share']):>12}")
    out.append("'rolls' = tradable days with a contract change inside 08:00-flat (a void risk).")
    for name, c in report["cells"].items():
        out += ["", f"CELL {name}: first fills {c['trades_lower_bound']}, upper bound "
                    f"{c['trades_upper_bound']} -> {c['read_status']}"]
        out.append(f"{'year':<7}{'sig L':>7}{'sig S':>7}{'drop':>6}{'fill L':>8}{'fill S':>8}"
                   f"{'<09:30':>8}{'09:30+':>8}{'11:30+':>8}{'2+ days':>9}{'max trades':>12}")
        for y, r in list(c["by_year"].items()) + [("TOTAL", c["totals"])]:
            out.append(f"{y:<7}{r['signals_long']:>7}{r['signals_short']:>7}"
                       f"{r['dropped_no_fill_bar']:>6}{r['first_fills_long']:>8}"
                       f"{r['first_fills_short']:>8}{r['first_fills_pre_open']:>8}"
                       f"{r['first_fills_rth']:>8}{r['first_fills_1130_or_later']:>8}"
                       f"{r['days_with_2plus_fillable_signals']:>9}{r['trades_upper_bound']:>12}")
        out.append("initial stop, $ per 1 MNQ (first fills): " + "; ".join(
            f"{y}: n={s['n']} median {_num(s['median'])} p90 {_num(s['p90'])} max {_num(s['max'])}"
            for y, s in c["initial_stop_usd_per_mnq"].items()))
    out += ["", report["note"]]
    return "\n".join(out) + "\n"
