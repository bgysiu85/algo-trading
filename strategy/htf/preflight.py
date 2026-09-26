#!/usr/bin/env python3
"""G2 -- HTF-Ben pre-flight (training side only, NO EXIT PRICES, NO P&L).
W15-0004 step 4, REGISTERED_htf_ben_v0.md sec 0 (gate G2) and sec 5.2.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.htf.preflight

WHAT THIS ANSWERS: are there enough v0 entries to read anything, and what
does the initial stop cost in dollars, before a single exit or profit is
looked at? Per REGISTERED sec 5.2: "It reads no exit prices and computes no
P&L" -- there is no exit-price column or P&L arithmetic ANYWHERE in this
module; that is not a flag that could be flipped, the capability simply does
not exist here. Turning triggers into a real trade ledger (one position at a
time, E5; exits; dollars) is the runner's job (step 7).

WHAT "ENTRY" MEANS HERE (weaker than the full runner's, on purpose)
--------------------------------------------------------------------
Each MACD cross (E1) is scored independently: trigger -> confirmation
window {t+1,t+2} (E2) -> daily filter read at the confirming bar (E3) ->
end-of-session block for scenario A -> initial stop distance / void check
(S1). E5 ("one position at a time... a trigger while in a position is
ignored, counted") is NOT applied here -- it requires knowing when the
PRIOR trade exited, which needs exit simulation, which this gate is
explicitly forbidden from doing. So "entries" here is an upper bound on
what the runner will actually take; the runner's own count will be equal
or lower. This is stated in every report this module emits, not just here.

VARIANTS RUN: v0 (E1-E3, S1), C1 (MACD cross alone: no confirmation
window, no daily filter, fills at the trigger bar's own t+1 open -- same
stop rule), and v0-TL (E1-E4 plus the sec 2.6 trend-line break+retest
gate, strategy.htf.tl_variant.detect_v0_tl, built W15-0007). v0-1H is
IDENTICAL to v0 at the entry-counting level (it only changes S2/S3, the
trail-checking cadence, which G2 never touches) -- reported here as
v0's own numbers, relabelled, per REGISTERED sec 2.6 ("identical to v0
on A-1H, so not run there").
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.htf import bars as B
from strategy.htf import signals as SIG
from strategy.htf import tl_variant as TLV

TRAIN_START = pd.Timestamp("2010-06-06").date()
TRAIN_END = pd.Timestamp("2021-12-31").date()
MIN_ENTRIES = 150

GRIDS = ("1H", "2H", "4H")
SCENARIO_GRID = {"B": "4H", "A-2H": "2H", "A-1H": "1H", "A-4H": "4H"}
INTRADAY_SCENARIOS = ("A-2H", "A-1H", "A-4H")
ALL_SCENARIOS = ("B", "A-2H", "A-1H", "A-4H")


def prepare_grids(df_1h: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """{grid_name: back-adjusted entry-chart frame} for 1H/2H/4H, plus the
    back-adjusted daily frame -- built once from the full archive so every
    EMA/MACD warm-up sees its true history, not a training-window-truncated
    one (REGISTERED sec 2.1: "All indicators ... are computed on this
    series" -- the back-adjusted one)."""
    grids = {g: B.back_adjust(B.resample(df_1h, g)) for g in GRIDS}
    daily_adj = B.back_adjust(B.daily(df_1h))
    return grids, daily_adj


def _training_mask(dates: pd.Series, start=TRAIN_START, end=TRAIN_END) -> np.ndarray:
    d = pd.Series(dates).to_numpy()
    return (d >= start) & (d <= end)


def detect_v0(entry_adj: pd.DataFrame, daily_adj: pd.DataFrame, *, scenario: str,
             warmup_bars: int = SIG.WARMUP_ENTRY_BARS, confirm_window: int = 2,
             swing_LR: int = 2) -> tuple[list[dict], dict]:
    """v0's entries (E1-E3, S1) and block counts, scored trigger-by-trigger
    (see module docstring: E5 not applied). Returns (entries, counts) over
    the WHOLE frame passed in -- callers slice to the training window
    afterward by each entry's 'year'/'session'. confirm_window/swing_LR
    default to the registered E2/S1 values (2 bars, L=R=2); overridable
    only for the neighbour grid (REGISTERED sec 3 item 8)."""
    bar_hours = B.GRID_HOURS[SCENARIO_GRID[scenario]]
    n = len(entry_adj)
    close = entry_adj["close_adj"]
    macd_line, signal_line = SIG.macd_seeded(close)
    up = SIG.macd_cross_up(macd_line, signal_line)
    down = SIG.macd_cross_down(macd_line, signal_line)
    confirms_long, confirms_short = SIG.confirmation_flags(close, macd_line, signal_line)
    daily_dir = SIG.daily_filter_as_of(entry_adj, daily_adj, bar_hours)
    ready = SIG.entry_ready_mask(entry_adj, warmup_bars)
    swing_low = SIG.swing_lows(entry_adj["low_adj"], L=swing_LR, R=swing_LR).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"], L=swing_LR, R=swing_LR).ffill()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()
    open_adj = entry_adj["open_adj"].to_numpy()

    counts = {"triggers": 0, "lapsed": 0, "blocked_daily_filter": 0,
             "blocked_end_of_session": 0, "voided": 0, "entries": 0}
    entries = []
    for i in range(n):
        if not ready[i]:
            continue
        if up.iloc[i]:
            direction = "long"
        elif down.iloc[i]:
            direction = "short"
        else:
            continue
        counts["triggers"] += 1
        confirms = confirms_long if direction == "long" else confirms_short
        c = SIG.confirmation_bar(confirms, i, window=confirm_window)
        if c is None:
            counts["lapsed"] += 1
            continue
        if daily_dir.iloc[c] != direction:
            counts["blocked_daily_filter"] += 1
            continue
        fill_idx = c + 1
        if fill_idx >= n:
            counts["lapsed"] += 1
            continue
        if scenario in INTRADAY_SCENARIOS and bool(last_bar[fill_idx]):
            counts["blocked_end_of_session"] += 1
            continue
        fill_price = float(open_adj[fill_idx])
        stop = _initial_stop(direction, fill_idx, fill_price, swing_low, swing_high,
                             low_adj, high_adj)
        if stop is None:
            counts["voided"] += 1
            continue
        counts["entries"] += 1
        entries.append(_entry_record(entry_adj, fill_idx, direction, fill_price, stop,
                                     scenario, bar_hours))
    return entries, counts


def detect_c1(entry_adj: pd.DataFrame, *, scenario: str,
             warmup_bars: int = SIG.WARMUP_ENTRY_BARS) -> tuple[list[dict], dict]:
    """C1 -- MACD cross alone (REGISTERED sec 3.7): no EMA confirmation, no
    daily filter. Fills at the open of the TRIGGER bar's own t+1 (there is
    no separate confirmation bar to fill after). Same stop rule (S1) and
    end-of-session block as v0."""
    bar_hours = B.GRID_HOURS[SCENARIO_GRID[scenario]]
    n = len(entry_adj)
    close = entry_adj["close_adj"]
    macd_line, signal_line = SIG.macd_seeded(close)
    up = SIG.macd_cross_up(macd_line, signal_line)
    down = SIG.macd_cross_down(macd_line, signal_line)
    ready = SIG.entry_ready_mask(entry_adj, warmup_bars)
    swing_low = SIG.swing_lows(entry_adj["low_adj"]).ffill()
    swing_high = SIG.swing_highs(entry_adj["high_adj"]).ffill()
    last_bar = SIG.session_last_bar_mask(entry_adj, bar_hours)
    low_adj = entry_adj["low_adj"].to_numpy()
    high_adj = entry_adj["high_adj"].to_numpy()
    open_adj = entry_adj["open_adj"].to_numpy()

    counts = {"triggers": 0, "lapsed": 0, "blocked_daily_filter": 0,
             "blocked_end_of_session": 0, "voided": 0, "entries": 0}
    entries = []
    for i in range(n):
        if not ready[i]:
            continue
        if up.iloc[i]:
            direction = "long"
        elif down.iloc[i]:
            direction = "short"
        else:
            continue
        counts["triggers"] += 1
        fill_idx = i + 1
        if fill_idx >= n:
            counts["lapsed"] += 1
            continue
        if scenario in INTRADAY_SCENARIOS and bool(last_bar[fill_idx]):
            counts["blocked_end_of_session"] += 1
            continue
        fill_price = float(open_adj[fill_idx])
        stop = _initial_stop(direction, fill_idx, fill_price, swing_low, swing_high,
                             low_adj, high_adj)
        if stop is None:
            counts["voided"] += 1
            continue
        counts["entries"] += 1
        entries.append(_entry_record(entry_adj, fill_idx, direction, fill_price, stop,
                                     scenario, bar_hours))
    return entries, counts


def _initial_stop(direction: str, fill_idx: int, fill_price: float,
                  swing_low: pd.Series, swing_high: pd.Series,
                  low_adj: np.ndarray, high_adj: np.ndarray) -> float | None:
    """S1: the most recent confirmed swing low/high before the fill, minus/
    plus 1 tick; if at or beyond the fill, fall back to the lowest low /
    highest high of the last 5 completed bars minus/plus 1 tick; if that is
    STILL at or beyond the fill, the trade is voided (None)."""
    tick = 0.01
    lo5 = max(0, fill_idx - 5)
    if direction == "long":
        level = swing_low.iloc[fill_idx]
        stop = (level - tick) if not pd.isna(level) else np.nan
        if np.isnan(stop) or stop >= fill_price:
            window = low_adj[lo5:fill_idx]
            stop = (window.min() - tick) if len(window) else np.nan
        if np.isnan(stop) or stop >= fill_price:
            return None
        return float(stop)
    level = swing_high.iloc[fill_idx]
    stop = (level + tick) if not pd.isna(level) else np.nan
    if np.isnan(stop) or stop <= fill_price:
        window = high_adj[lo5:fill_idx]
        stop = (window.max() + tick) if len(window) else np.nan
    if np.isnan(stop) or stop <= fill_price:
        return None
    return float(stop)


def _entry_record(entry_adj: pd.DataFrame, fill_idx: int, direction: str,
                  fill_price: float, stop: float, scenario: str, bar_hours: int) -> dict:
    stop_dist = abs(fill_price - stop)
    t_open = entry_adj["t_open"].iloc[fill_idx]
    session = entry_adj["session"].iloc[fill_idx]
    hours_left = None
    if scenario in INTRADAY_SCENARIOS:
        last_bucket = 22 // bar_hours
        bar_idx = int(entry_adj["bar"].iloc[fill_idx])
        hours_left = (last_bucket - bar_idx) * bar_hours
    return {"session": str(session), "year": int(pd.Timestamp(session).year),
           "t_open": str(t_open), "direction": direction,
           "fill_price": fill_price, "stop": stop, "stop_dist": stop_dist,
           "hours_left": hours_left}


def _pct(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def summarize(entries: list[dict], counts: dict, *, scenario: str) -> dict:
    """Training-side-only summary: per-year counts, stop-distance and
    (for A) hours-left percentiles, plus training totals."""
    train_entries = [e for e in entries if TRAIN_START <= pd.Timestamp(e["session"]).date() <= TRAIN_END]
    by_year: dict[int, list[dict]] = {}
    for e in train_entries:
        by_year.setdefault(e["year"], []).append(e)

    def _year_block(rows: list[dict]) -> dict:
        dists = [r["stop_dist"] for r in rows]
        block = {"entries": len(rows),
                "stop_dist_median": _pct(dists, 50), "stop_dist_p90": _pct(dists, 90),
                "stop_dist_max": (max(dists) if dists else None)}
        if scenario in INTRADAY_SCENARIOS:
            hrs = [r["hours_left"] for r in rows]
            block["hours_left_median"] = _pct(hrs, 50)
        return block

    per_year = {y: _year_block(rows) for y, rows in sorted(by_year.items())}
    totals = dict(counts)  # triggers/lapsed/blocked_.../voided/entries are already training+non-training combined above the caller's slicing -- see run()
    totals["entries_training"] = len(train_entries)
    totals.update(_year_block(train_entries))
    totals["underpowered"] = totals["entries_training"] < MIN_ENTRIES
    return {"per_year": per_year, "totals": totals}


def run(archive_1h) -> dict:
    """Load once, run v0, C1 and v0-TL on all four scenarios, training side
    only. v0-1H's report is v0's own numbers relabelled -- v0-1H is v0
    itself (all scenarios identical at the entry-counting level); it is not
    scored separately, only relabelled (module docstring)."""
    df_1h = B.load_1h(archive_1h)
    grids, daily_adj = prepare_grids(df_1h)

    four_h_adj = grids["4H"]
    report: dict = {"variants": {}}
    for variant, fn in (("v0", detect_v0), ("C1", detect_c1), ("v0-TL", TLV.detect_v0_tl)):
        report["variants"][variant] = {}
        for scenario in ALL_SCENARIOS:
            entry_adj = grids[SCENARIO_GRID[scenario]]
            if variant == "v0":
                entries, counts = fn(entry_adj, daily_adj, scenario=scenario)
            elif variant == "v0-TL":
                entries, counts = fn(entry_adj, daily_adj, four_h_adj, scenario=scenario)
            else:
                entries, counts = fn(entry_adj, scenario=scenario)
            # counts accumulated above cover the WHOLE series (pre-training-
            # filter) for triggers/lapsed/blocked/voided; "entries" in counts
            # likewise. Training-only entry counts/percentiles are recomputed
            # in summarize() from the training-sliced entry list, and counts
            # is kept alongside as the full-history diagnostic.
            report["variants"][variant][scenario] = {
                "counts_full_history": counts,
                **summarize(entries, counts, scenario=scenario),
            }
    report["variants"]["v0-1H"] = {
        "note": "identical to v0 at the entry-counting level (S2/S3 trail "
                "cadence is not modeled by G2); not run on A-1H (REGISTERED "
                "sec 2.6). See variants.v0 for the numbers.",
    }
    v0_b = report["variants"]["v0"]["B"]["totals"]["entries_training"]
    v0_a2h = report["variants"]["v0"]["A-2H"]["totals"]["entries_training"]
    report["underpowered_stop_rule"] = combine_underpowered(v0_b, v0_a2h)
    return report


def combine_underpowered(v0_b_entries: int, v0_a2h_entries: int,
                         min_required: int = MIN_ENTRIES) -> dict:
    """REGISTERED sec 5.2, verbatim: 'if v0 has fewer than 150 entries on
    the training side in BOTH B and A-2H, the study stops as underpowered'.
    That is an AND -- one scenario clearing the bar is enough to continue,
    even if the other falls short (which is then its own reported finding,
    not a stop condition on its own). Split out from run() so the
    AND-vs-OR distinction is directly unit-testable without a real
    archive."""
    below_b = v0_b_entries < min_required
    below_a2h = v0_a2h_entries < min_required
    return {
        "v0_B_entries_training": v0_b_entries, "v0_A2H_entries_training": v0_a2h_entries,
        "min_required": min_required,
        "underpowered": below_b and below_a2h,
        "v0_B_below_threshold": below_b, "v0_A2H_below_threshold": below_a2h,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G2: HTF-Ben pre-flight (no P&L).")
    ap.add_argument("--archive", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    report = run(archive)
    print("G2 -- HTF-Ben pre-flight (training side, no P&L, no exit prices)\n")
    for variant in ("v0", "C1", "v0-TL"):
        for scenario in ALL_SCENARIOS:
            t = report["variants"][variant][scenario]["totals"]
            print(f"{variant:4s} {scenario:5s}  triggers={t['triggers']:5d}  "
                  f"lapsed={t['lapsed']:5d}  daily_blk={t['blocked_daily_filter']:5d}  "
                  f"eos_blk={t['blocked_end_of_session']:5d}  voided={t['voided']:4d}  "
                  f"entries(training)={t['entries_training']:5d}  "
                  f"stop$ median={t['stop_dist_median']!s:>8s}  "
                  f"p90={t['stop_dist_p90']!s:>8s}")
    ur = report["underpowered_stop_rule"]
    print(f"\nunderpowered stop rule (sec 5.2, AND): v0 B={ur['v0_B_entries_training']}"
          f"{' [below 150]' if ur['v0_B_below_threshold'] else ''}, "
          f"v0 A-2H={ur['v0_A2H_entries_training']}"
          f"{' [below 150]' if ur['v0_A2H_below_threshold'] else ''} "
          f"(stops only if BOTH < {ur['min_required']}) -> "
          f"{'UNDERPOWERED' if ur['underpowered'] else 'OK'}")
    if ur["v0_B_below_threshold"] or ur["v0_A2H_below_threshold"]:
        print("  note: one scenario is individually below 150 even though the "
              "study is not stopped -- read its numbers with that in mind.")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")

    return 1 if ur["underpowered"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
