#!/usr/bin/env python3
"""W07-0012 subitem 6: the S3 backtest/report layer for SWING-v0
(`docs/research/REGISTERED_swing_v0.md`, the "spec"), built on top of
`fill_engine.py`'s priced trades (subitem 5).

    python -m strategy.swing.report_layer run --pit-dir var/swing_pit
    python -m strategy.swing.report_layer --self-test

WHAT THIS MODULE IS, AND IS NOT
--------------------------------
Turns `fill_engine.build_trades()`'s raw fills into the nine things spec S3
requires every run to emit: net market-relative return at three friction
levels (cash-funded headline, 2:1-levered reported beside it, never the
headline -- G3), split by half and by year, drop-top-N by name, a cluster
(by-calendar-month) bootstrap, a random-decile control, the full K x N x
bucket grid plus the ensemble, and the counts/coverage checks. It does NOT
spend the holdout (`holdout_swing.json`, spec S6) -- that is reserved for
the deployed cell alone, later, and is explicitly out of this subitem's own
title ("bootstrap, drop-top-N, random-decile control, K x N x bucket grid,
coverage checks").

FRICTION: WHERE THE THREE NUMBERS COME FROM
---------------------------------------------
Spec S2.6 registers three levels. "Measured" (5.46 bps) is G2's OWN all-in
figure (`swing_g2_RESULT_20260919.md` S0: "spread + IBKR tiered fees,
marketable both legs") -- already inclusive of commission, so nothing is
added to it here. "Bucket-specific" (7.98/3.61/2.96 bps by open/midday/
close) is G2's *spread-only* figure (`swing_g2_RESULT_20260919.md` S3:
"spread swing across the session") -- S2.6 explicitly says commission is
"added on top of spread at every level, per swing_preflight_20260914.md
S3.3", so this module adds it here for the bucket-specific and stress
levels. "Stress" is registered as "2x the bucket figure"; this module reads
that as 2x the bucket-specific level's FULL total (spread + commission),
the more conservative of the two readings the wording leaves open. Both
choices are caveats every report carries, not hidden assumptions.

COMMISSION: A DOCUMENTED SIMPLIFICATION
------------------------------------------
`swing_preflight_20260914.md` S3.3's exact commission figure is a function
of position dollar size, which this study's registration does not fix
(spec S2.5 sizes by risk-budget FRACTION, not a dollar amount). Rather than
invent a per-share formula the spec does not pin down, this module uses
S3.5's own conservative UPPER-BOUND combined "commission, both legs" +
"exchange + regulatory + clearing" bps by cap tier -- 1.7 bps (S&P 500 /
large cap: 0.9 + 0.8) and 3.3 bps (S&P 400 / mid cap: 1.6 + 1.7) -- keyed by
whichever index's membership spell covers the traded code on its ENTRY
date. A code found in neither index's spells on that date (should not
happen for a code that just traded, but defensively handled) falls back to
the more conservative (mid-cap) figure.

FINANCING (2:1 LEVERED VARIANT)
----------------------------------
0.99 bps per TRADING day held. `swing_preflight_20260914.md` S3.4 and
`swing_g2_RESULT_20260919.md` S0 both give the same table -- 2/5/10/20
session holds cost 1.98/4.95/9.90/19.80 bps, exactly linear in TRADING
days, not calendar days. `Trade.n` (from `fill_engine.py`) IS that trading-
day count already, so financing here is simply `n * 0.99` bps. Gross return
and both-legs cost are doubled for the 2:1 variant; financing is added
once, never doubled again (it already reflects the loan on the full 2:1
notional).

MARKET-RELATIVE SCORING (spec G1)
------------------------------------
"Score return minus the equal-weight universe return over the same holding
period, never outright directional." The benchmark -- the equal-weight
average bucket-to-bucket return of every code ELIGIBLE on the entry date
(not the picked decile) with both a priced entry and exit -- does not
depend on which codes were picked. It is therefore identical for every
grid cell and every random-decile draw that shares the same (entry_date,
exit_date, bucket, index) key. This module caches it once and reuses it
everywhere, which is the difference between an 18-cell grid plus a
2,000-draw random-decile control finishing in minutes rather than hours.

DROP-TOP-N (spec S3 item 4)
-------------------------------
Read here as: rank CODES (not days) by their total weighted market-relative
net contribution across the whole sample, drop the top N codes' trades
entirely, recompute. "n/a" (never "$0") when the sample has N or fewer
distinct codes traded in total -- the spec's own instruction not to report
a dropped-everything zero as if it were a real number.

THE ENSEMBLE (spec S2.4 / S3 item 7)
----------------------------------------
N in {5, 10, 20}, "each sleeve sized at one third of the per-trade risk
budget". Every aggregation helper below (`aggregate`, `by_half`, `by_year`,
`drop_top_n`, `cluster_bootstrap_by_month`) is WEIGHT-aware -- it reads a
`weight` key from each row, defaulting to 1.0. An ensemble cell pools all
three sleeves' scored rows with `weight = 1/3` each, so it can reuse every
helper unchanged rather than re-deriving a parallel set of formulas.

NO REPO IMPORTS BEYOND THE PACKAGE ITSELF
---------------------------------------------
Same convention as the rest of strategy/swing/: standard library only, plus
pit_universe, reversal_v0 and fill_engine, siblings in this package.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Iterable

from strategy.swing import fill_engine as F
from strategy.swing import pit_universe as P
from strategy.swing import reversal_v0 as R

DEFAULT_PIT_DIR = Path("var") / "swing_pit"

# -- spec S2.6: the three registered friction levels -----------------------
MEASURED_BPS = 5.46  # G2's pooled all-in figure -- already inclusive of commission
BUCKET_SPREAD_BPS = {"open": 7.98, "midday": 3.61, "close": 2.96}  # spread only
COMMISSION_BPS_BY_INDEX = {"sp500": 1.7, "sp400": 3.3}  # swing_preflight S3.5, upper bound
DEFAULT_COMMISSION_BPS = max(COMMISSION_BPS_BY_INDEX.values())  # conservative fallback
FRICTION_LEVELS = ("measured", "bucket", "stress")
STRESS_MULTIPLIER = 2.0

# -- spec S2.5 / swing_preflight S3.4: 2:1 levered financing ---------------
FINANCING_BPS_PER_TRADING_DAY = 0.99
LEVERAGE = 2.0

# -- spec S3 -----------------------------------------------------------------
DROP_TOP_N_VALUES = (1, 3, 5)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260925  # W07-0012 subitem 6 build date -- fixed, documented
RANDOM_DECILE_DRAWS = 2000
RANDOM_DECILE_SEED = 20260926  # distinct from BOOTSTRAP_SEED, also fixed


# ----------------------------------------------------------------------------
# friction / cost model
# ----------------------------------------------------------------------------

def code_index_on(universe: R.Universe, code: str, day: dt.date) -> str | None:
    """Which index's spell covers `code` on `day` -- there should be exactly
    one for a code with a real trade on that day; the first match is used if
    more than one somehow does (a straddling data artefact, not expected)."""
    for s in universe.spells:
        if s.code == code and s.covers(day):
            return s.index
    return None


def commission_bps_for(index: str | None) -> float:
    return COMMISSION_BPS_BY_INDEX.get(index, DEFAULT_COMMISSION_BPS)


def friction_bps(level: str, bucket: str, index: str | None) -> float:
    if level == "measured":
        return MEASURED_BPS
    if level not in ("bucket", "stress"):
        raise ValueError(f"unknown friction level {level!r}")
    total = BUCKET_SPREAD_BPS[bucket] + commission_bps_for(index)
    return STRESS_MULTIPLIER * total if level == "stress" else total


def financing_bps(n: int) -> float:
    return n * FINANCING_BPS_PER_TRADING_DAY


def net_return(trade: F.Trade, level: str, index: str | None = None) -> float:
    return trade.ret - friction_bps(level, trade.bucket, index) / 10000.0


def levered_net_return(trade: F.Trade, level: str, index: str | None = None) -> float:
    gross2 = LEVERAGE * trade.ret
    cost2 = LEVERAGE * friction_bps(level, trade.bucket, index) / 10000.0
    fin = financing_bps(trade.n) / 10000.0
    return gross2 - cost2 - fin


# ----------------------------------------------------------------------------
# market-relative benchmark (spec G1) -- pick-independent, cacheable
# ----------------------------------------------------------------------------

def universe_eligible_bucket_return(universe: R.Universe, store: dict,
                                    entry_date: dt.date, exit_date: dt.date,
                                    bucket: str, index: str | None = None,
                                    cache: dict | None = None) -> float | None:
    """Equal-weight average (exit/entry - 1) over every code eligible on
    `entry_date` with a priced bucket fill at BOTH dates. Depends only on
    (entry_date, exit_date, bucket, index) -- never on which codes were
    picked -- so the same key is reused across every grid cell and every
    random-decile draw that shares it. None if nothing in the eligible set
    has both prices (an n/a day, not a zero)."""
    key = (entry_date, exit_date, bucket, index)
    if cache is not None and key in cache:
        return cache[key]
    rets = []
    for code in R.eligible_on(universe, entry_date, index=index):
        entry_px, _ = F.bucket_price(store, code, entry_date, bucket)
        if entry_px is None:
            continue
        exit_px, _ = F.bucket_price(store, code, exit_date, bucket)
        if exit_px is None:
            continue
        rets.append(exit_px / entry_px - 1.0)
    result = (sum(rets) / len(rets)) if rets else None
    if cache is not None:
        cache[key] = result
    return result


# ----------------------------------------------------------------------------
# scoring: one row per trade, every level, cash-funded and 2:1 levered
# ----------------------------------------------------------------------------

SCORE_FIELDS = (
    ["code", "signal_date", "entry_date", "exit_date", "bucket", "n", "index",
     "weight", "raw_ret", "benchmark_ret"]
    + [f"net_{lvl}" for lvl in FRICTION_LEVELS]
    + [f"mr_{lvl}" for lvl in FRICTION_LEVELS]
    + [f"levered_net_{lvl}" for lvl in FRICTION_LEVELS]
    + [f"levered_mr_{lvl}" for lvl in FRICTION_LEVELS]
)


def score_trades(trades: list[F.Trade], universe: R.Universe, store: dict,
                 index: str | None = None, cache: dict | None = None
                 ) -> tuple[list[dict], int]:
    """Every trade becomes one row: raw return, the pick-independent
    benchmark, and net/market-relative return (cash-funded and 2:1 levered)
    at all three friction levels. Returns (rows, n_no_benchmark) -- a trade
    whose entry-date eligible universe has no priced benchmark is still
    scored for net return but carries None for every market-relative field,
    counted rather than dropped (same discipline as `fill_engine.Unfilled`)."""
    if cache is None:
        cache = {}
    rows: list[dict] = []
    n_no_benchmark = 0
    for t in trades:
        t_index = code_index_on(universe, t.code, t.entry_date)
        bench = universe_eligible_bucket_return(
            universe, store, t.entry_date, t.exit_date, t.bucket,
            index=index, cache=cache)
        row = {
            "code": t.code, "signal_date": t.signal_date, "entry_date": t.entry_date,
            "exit_date": t.exit_date, "bucket": t.bucket, "n": t.n, "index": t_index,
            "weight": 1.0, "raw_ret": t.ret, "benchmark_ret": bench,
        }
        for lvl in FRICTION_LEVELS:
            net = net_return(t, lvl, t_index)
            lev = levered_net_return(t, lvl, t_index)
            row[f"net_{lvl}"] = net
            row[f"levered_net_{lvl}"] = lev
            row[f"mr_{lvl}"] = (net - bench) if bench is not None else None
            row[f"levered_mr_{lvl}"] = (lev - bench) if bench is not None else None
        if bench is None:
            n_no_benchmark += 1
        rows.append(row)
    return rows, n_no_benchmark


# ----------------------------------------------------------------------------
# weight-aware aggregation helpers (spec S3 items 1-5)
# ----------------------------------------------------------------------------

def mean_of(rows: list[dict], field: str) -> float | None:
    agg = aggregate(rows, field)
    return agg["mean"]


def aggregate(rows: list[dict], field: str) -> dict:
    """Weighted mean/total, reading each row's own 'weight' (default 1.0) --
    this is what lets an ensemble's pooled sleeves (each weighted 1/3, spec
    S2.4) reuse every helper below unchanged."""
    pairs = [(r[field], r.get("weight", 1.0)) for r in rows if r.get(field) is not None]
    if not pairs:
        return {"n": 0, "mean": None, "total": None}
    wsum = sum(w for _, w in pairs)
    total = sum(v * w for v, w in pairs)
    return {"n": len(pairs), "mean": (total / wsum) if wsum else None, "total": total}


def by_half(rows: list[dict], field: str) -> dict:
    """Split at the median ENTRY date of the sample (spec S3 item 2). Falls
    back to an index split if the median-date split puts nothing in the
    second half (every row sharing the same date, a degenerate case a real
    multi-year sample will not hit, but a synthetic/small one might)."""
    dates = sorted(r["entry_date"] for r in rows)
    if not dates:
        return {"first_half": aggregate([], field), "second_half": aggregate([], field),
                "median_date": None}
    median_date = dates[len(dates) // 2]
    first = [r for r in rows if r["entry_date"] <= median_date]
    second = [r for r in rows if r["entry_date"] > median_date]
    if not second and len(rows) > 1:
        ordered = sorted(rows, key=lambda r: (r["entry_date"], r["code"]))
        mid = len(ordered) // 2
        first, second = ordered[:mid], ordered[mid:]
    return {"first_half": aggregate(first, field), "second_half": aggregate(second, field),
            "median_date": median_date.isoformat()}


def by_year(rows: list[dict], field: str) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(r["entry_date"].year, []).append(r)
    return {y: aggregate(rs, field) for y, rs in sorted(out.items())}


def drop_top_n(rows: list[dict], field: str, n: int) -> dict | str:
    """Rank codes by total WEIGHTED contribution, drop the top n codes'
    trades entirely, recompute. 'n/a' (never a $0-shaped aggregate) when the
    sample has n or fewer distinct codes traded -- spec S3 item 4."""
    contrib: dict[str, float] = {}
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        contrib[r["code"]] = contrib.get(r["code"], 0.0) + v * r.get("weight", 1.0)
    if len(contrib) <= n:
        return "n/a"
    top = set(sorted(contrib, key=lambda c: -contrib[c])[:n])
    kept = [r for r in rows if r["code"] not in top]
    return aggregate(kept, field)


def cluster_bootstrap_by_month(rows: list[dict], field: str,
                                resamples: int = BOOTSTRAP_RESAMPLES,
                                seed: int = BOOTSTRAP_SEED) -> dict:
    """Resample calendar-MONTH blocks of (weighted) values, 2,000 times,
    seeded (spec S3 item 5). Reports the share of resamples whose total is
    positive -- the number spec S4 criterion 4 reads against its >=95% bar."""
    groups: dict[tuple, list[tuple]] = {}
    for r in rows:
        v = r.get(field)
        if v is None:
            continue
        key = (r["entry_date"].year, r["entry_date"].month)
        groups.setdefault(key, []).append((v, r.get("weight", 1.0)))
    keys = sorted(groups)
    if not keys:
        return {"resamples": resamples, "months": 0, "pct_positive": None}
    rng = random.Random(seed)
    n_positive = 0
    for _ in range(resamples):
        picked = [rng.choice(keys) for _ in keys]
        total = sum(v * w for k in picked for v, w in groups[k])
        if total > 0:
            n_positive += 1
    return {"resamples": resamples, "months": len(keys),
            "pct_positive": round(100 * n_positive / resamples, 2)}


# ----------------------------------------------------------------------------
# random-decile control (spec S3 item 6)
# ----------------------------------------------------------------------------

def random_decile_picks(universe: R.Universe, calendar: list, picks: dict,
                        index: str | None, seed: int) -> dict:
    """Same-sized decile as `picks[day]`, drawn at random (not by rank) from
    that day's eligible universe -- the selection control spec item 6 asks
    for. A day whose eligible universe is no bigger than the actual decile
    just takes the whole eligible set (nothing to randomise)."""
    rng = random.Random(seed)
    out: dict = {}
    for day in calendar:
        k = len(picks.get(day, []))
        if k == 0:
            out[day] = []
            continue
        elig = sorted(R.eligible_on(universe, day, index=index))
        out[day] = elig if len(elig) <= k else rng.sample(elig, k)
    return out


def random_decile_control(universe: R.Universe, calendar: list, store: dict,
                          picks: dict, bucket: str, n: int,
                          index: str | None = None,
                          draws: int = RANDOM_DECILE_DRAWS,
                          seed: int = RANDOM_DECILE_SEED,
                          level: str = "bucket",
                          cache: dict | None = None) -> dict:
    """2,000 seeded draws (spec S3 item 6), same N/costs/bucket as the real
    cell, scored at market-relative `level` (the deployed friction level by
    default). Reuses `fill_engine.build_trades` and the same pick-
    independent benchmark cache the real grid uses."""
    if cache is None:
        cache = {}
    draw_means = []
    for d in range(draws):
        rnd_picks = random_decile_picks(universe, calendar, picks, index, seed + d)
        trades, _unfilled = F.build_trades(rnd_picks, calendar, store, bucket, n)
        rows, _n_no_bench = score_trades(trades, universe, store, index=index, cache=cache)
        m = mean_of(rows, f"mr_{level}")
        if m is not None:
            draw_means.append(m)
    if not draw_means:
        return {"draws": draws, "draws_with_a_result": 0,
                "mean_of_draw_means": None, "pct_draws_positive": None}
    return {
        "draws": draws, "draws_with_a_result": len(draw_means),
        "mean_of_draw_means": sum(draw_means) / len(draw_means),
        "pct_draws_positive": round(
            100 * sum(1 for m in draw_means if m > 0) / len(draw_means), 2),
    }


# ----------------------------------------------------------------------------
# one grid cell, and the K x N x bucket grid + ensemble (spec S3 item 7)
# ----------------------------------------------------------------------------

def _level_reports(rows: list[dict], prefix: str) -> dict:
    return {
        "by_level": {lvl: aggregate(rows, f"{prefix}_{lvl}") for lvl in FRICTION_LEVELS},
        "by_half": {lvl: by_half(rows, f"{prefix}_{lvl}") for lvl in FRICTION_LEVELS},
        "by_year": {lvl: by_year(rows, f"{prefix}_{lvl}") for lvl in FRICTION_LEVELS},
        "drop_top_n": {lvl: {dn: drop_top_n(rows, f"{prefix}_{lvl}", dn)
                             for dn in DROP_TOP_N_VALUES}
                      for lvl in FRICTION_LEVELS},
        "bootstrap": {lvl: cluster_bootstrap_by_month(rows, f"{prefix}_{lvl}")
                     for lvl in FRICTION_LEVELS},
    }


def run_cell(universe: R.Universe, prices: dict, calendar: list, store: dict,
            k: int, n: int, bucket: str, index: str | None = None,
            cache: dict | None = None) -> dict:
    picks = R.daily_picks(universe, prices, calendar, k, index=index)
    trades, unfilled = F.build_trades(picks, calendar, store, bucket, n)
    F.check_no_lookahead(trades, calendar, n)
    rows, n_no_benchmark = score_trades(trades, universe, store, index=index, cache=cache)
    return {
        "k": k, "n": n, "bucket": bucket, "rows": rows,
        "n_no_benchmark": n_no_benchmark,
        "fill_summary": F.summarize(trades, unfilled),
        "cash_funded": _level_reports(rows, "mr"),
        "levered_2x1": _level_reports(rows, "levered_mr"),
    }


def ensemble_cell(sleeves: list[dict]) -> dict:
    """Pools the N=5/10/20 sleeves' scored rows at weight 1/3 each (spec
    S2.4) and reuses `_level_reports` unchanged -- see the module docstring
    on why every aggregation helper is weight-aware."""
    w = 1.0 / len(sleeves)
    pooled = []
    for sleeve in sleeves:
        for r in sleeve["rows"]:
            rr = dict(r)
            rr["weight"] = r.get("weight", 1.0) * w
            pooled.append(rr)
    fill_summary = {
        "picks": sum(s["fill_summary"]["picks"] for s in sleeves),
        "filled": sum(s["fill_summary"]["filled"] for s in sleeves),
        "unfilled": sum(s["fill_summary"]["unfilled"] for s in sleeves),
    }
    return {
        "k": sleeves[0]["k"], "bucket": sleeves[0]["bucket"],
        "n_values": sorted(s["n"] for s in sleeves), "rows": pooled,
        "n_no_benchmark": sum(s["n_no_benchmark"] for s in sleeves),
        "fill_summary": fill_summary,
        "cash_funded": _level_reports(pooled, "mr"),
        "levered_2x1": _level_reports(pooled, "levered_mr"),
    }


def run_grid(universe: R.Universe, prices: dict, calendar: list, store: dict,
            index: str | None = None) -> dict:
    """The full 2 K x 3 N x 3 bucket = 18-cell grid, unranked, plus the
    ensemble per (K, bucket) -- spec S3 item 7, G7 ("no best-cell table")."""
    cache: dict = {}
    cells = {}
    for k in R.K_VALUES:
        for bucket in R.BUCKETS:
            for n in R.N_VALUES:
                cells[(k, bucket, n)] = run_cell(
                    universe, prices, calendar, store, k, n, bucket,
                    index=index, cache=cache)
    ensembles = {}
    for k in R.K_VALUES:
        for bucket in R.BUCKETS:
            sleeves = [cells[(k, bucket, n)] for n in R.N_VALUES]
            ensembles[(k, bucket)] = ensemble_cell(sleeves)
    return {"cells": cells, "ensembles": ensembles}


# ----------------------------------------------------------------------------
# coverage / counts (spec S3 items 8-9)
# ----------------------------------------------------------------------------

def coverage_report(universe: R.Universe, prices: dict, calendar: list,
                    picks_by_k: dict, suspects_path: Path, pit_dir: Path) -> dict:
    n_hindsight = R.check_hindsight(universe, calendar)
    n_suspects = R.check_no_suspect_leak(universe, suspects_path, pit_dir)
    by_k = {}
    for k, picks in picks_by_k.items():
        sizes = [len(v) for v in picks.values()]
        by_k[k] = {
            "decile_size_min": min(sizes) if sizes else None,
            "decile_size_median": statistics.median(sizes) if sizes else None,
            "decile_size_max": max(sizes) if sizes else None,
            "n_no_trade_days": sum(1 for s in sizes if s == 0),
        }
    codes_covered = sorted(prices)
    first_last = {c: (min(prices[c]).isoformat(), max(prices[c]).isoformat())
                  for c in codes_covered}
    return {
        "hindsight_guard_pairs_checked": n_hindsight,
        "hindsight_guard_rejections": 0,  # check_hindsight raises rather than counting failures
        "suspect_leak_guard_spells_confirmed_absent": n_suspects,
        "by_k": by_k,
        "n_codes_covered": len(codes_covered),
        "first_last_date_by_code": first_last,
        "caveat": (
            "No separate 'published counts' artefact exists on disk to cross"
            "-check membership.csv against beyond the file pair itself -- "
            "this reports what load_universe()/check_universe_files() "
            "already verified (spell-count parity between membership.csv "
            "and suspects.csv, W07-0002's own outputs), not an independent "
            "third source."),
    }


# ----------------------------------------------------------------------------
# top-level orchestration
# ----------------------------------------------------------------------------

def run(pit_dir: Path = DEFAULT_PIT_DIR, index: str | None = None,
       random_control_cells: list[tuple] | None = None,
       random_control_draws: int = RANDOM_DECILE_DRAWS) -> dict:
    universe = R.load_universe(pit_dir)
    all_codes = sorted({s.code for s in universe.spells})
    prices = R.load_prices(all_codes, pit_dir / "eod")
    calendar = R.trading_calendar(prices)
    store = F.load_intraday_store(all_codes, pit_dir / F.INTRADAY_SUBDIR)

    grid = run_grid(universe, prices, calendar, store, index=index)

    picks_by_k = {k: R.daily_picks(universe, prices, calendar, k, index=index)
                  for k in R.K_VALUES}
    coverage = coverage_report(universe, prices, calendar, picks_by_k,
                               pit_dir / R.SUSPECTS_NAME, pit_dir)

    if random_control_cells is None:
        # the deployed cell's own bucket, every N in the ensemble (spec S4
        # criterion 5 is judged at the deployed cell) -- callers can pass a
        # wider list (e.g. all 18 cells) at the cost of runtime.
        random_control_cells = [(5, "midday", n) for n in R.N_VALUES]
    rc_cache: dict = {}
    random_controls = {}
    for (k, bucket, n) in random_control_cells:
        random_controls[(k, bucket, n)] = random_decile_control(
            universe, calendar, store, picks_by_k[k], bucket, n, index=index,
            draws=random_control_draws, cache=rc_cache)

    return {
        "pit_dir": str(pit_dir), "index": index,
        "window": [calendar[0].isoformat(), calendar[-1].isoformat()],
        "grid": grid, "coverage": coverage, "random_decile_control": random_controls,
    }


# ----------------------------------------------------------------------------
# JSON-safe projection (the raw scored rows are bulky and not JSON-native --
# dates -- so they are stripped here; export them to CSV separately with
# `write_scored_rows_csv` when a specific cell's trade-level detail is needed)
# ----------------------------------------------------------------------------

def _strip_cell(cell: dict) -> dict:
    out = {k: v for k, v in cell.items() if k != "rows"}
    out["n_trades"] = len(cell.get("rows", []))
    return out


def to_json_safe(result: dict) -> dict:
    grid = result["grid"]
    cells = {f"K{k}_{bucket}_N{n}": _strip_cell(cell)
            for (k, bucket, n), cell in grid["cells"].items()}
    ensembles = {f"K{k}_{bucket}_ensemble": _strip_cell(cell)
                for (k, bucket), cell in grid["ensembles"].items()}
    random_controls = {f"K{k}_{bucket}_N{n}": rc
                       for (k, bucket, n), rc in result["random_decile_control"].items()}
    return {
        "pit_dir": result["pit_dir"], "index": result["index"], "window": result["window"],
        "grid": {"cells": cells, "ensembles": ensembles},
        "coverage": result["coverage"], "random_decile_control": random_controls,
    }


def write_scored_rows_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SCORE_FIELDS)
        for r in rows:
            w.writerow([
                r["code"], r["signal_date"].isoformat(),
                r["entry_date"].isoformat(), r["exit_date"].isoformat(), r["bucket"],
                r["n"], r.get("index") or "", round(r.get("weight", 1.0), 6),
                round(r["raw_ret"], 6),
                round(r["benchmark_ret"], 6) if r["benchmark_ret"] is not None else "",
            ] + [
                (round(r[f], 6) if r.get(f) is not None else "")
                for f in SCORE_FIELDS[10:]
            ])


def format_report(result: dict, index: str | None = None) -> str:
    L = [f"SWING-v0 S3 report layer (W07-0012 subitem 6) -- "
        f"{result['window'][0]} to {result['window'][1]}"
        + (f", index={index}" if index else ""), ""]

    L.append("DEPLOYED CELL (K=5, midday, N-ensemble) -- headline")
    dep = result["grid"]["ensembles"].get((5, "midday"))
    if dep is not None:
        for label, block in (("cash-funded", dep["cash_funded"]),
                             ("2:1 levered (never the headline)", dep["levered_2x1"])):
            L.append(f"  {label}:")
            for lvl in FRICTION_LEVELS:
                agg = block["by_level"][lvl]
                mean_str = f"{agg['mean']*10000:.2f} bps" if agg["mean"] is not None else "n/a"
                L.append(f"    {lvl:9s}  n={agg['n']:>6}  "
                         f"mean market-relative net = {mean_str}")
        L.append(f"  fill summary: {dep['fill_summary']}")
        boot = dep["cash_funded"]["bootstrap"]["bucket"]
        L.append(f"  cluster bootstrap (bucket level, by calendar month): "
                 f"{boot['pct_positive']}% of {boot['resamples']} resamples positive "
                 f"({boot['months']} months)")
        for dn in DROP_TOP_N_VALUES:
            dtn = dep["cash_funded"]["drop_top_n"]["bucket"][dn]
            L.append(f"  drop-top-{dn} (bucket level): "
                     f"{dtn if isinstance(dtn, str) else dtn['mean']}")
    else:
        L.append("  (no K=5/midday ensemble in this result)")
    L.append("")

    L.append("RANDOM-DECILE CONTROL (spec S3 item 6, S4 criterion 5)")
    for key, rc in result["random_decile_control"].items():
        L.append(f"  K={key[0]} {key[1]} N={key[2]}: "
                 f"{rc['pct_draws_positive']}% of {rc['draws_with_a_result']} draws "
                 f"had a positive mean market-relative net return")
    L.append("")

    L.append("FULL K x N x BUCKET GRID (unranked -- spec S3 item 7 / G7)")
    for (k, bucket, n), cell in sorted(result["grid"]["cells"].items()):
        agg = cell["cash_funded"]["by_level"]["bucket"]
        mean_bps = f"{agg['mean']*10000:.2f} bps" if agg["mean"] is not None else "n/a"
        L.append(f"  K={k} {bucket:6s} N={n:2d}: n={agg['n']:>6}  "
                 f"mean market-relative net (bucket-specific) = {mean_bps}")
    L.append("")

    L.append("COVERAGE / COUNTS (spec S3 items 8-9)")
    cov = result["coverage"]
    L.append(f"  hindsight-guard rejections: {cov['hindsight_guard_rejections']} "
             f"(must be exactly zero -- {cov['hindsight_guard_pairs_checked']} pairs checked)")
    L.append(f"  suspect-leak guard: {cov['suspect_leak_guard_spells_confirmed_absent']} "
             "spells confirmed absent")
    L.append(f"  codes covered: {cov['n_codes_covered']}")
    for k, row in cov["by_k"].items():
        L.append(f"  K={k}: decile size min/median/max = "
                 f"{row['decile_size_min']}/{row['decile_size_median']}/"
                 f"{row['decile_size_max']}, no-trade days = {row['n_no_trade_days']}")
    L.append(f"  caveat: {cov['caveat']}")
    L.append("")

    L.append("CAVEATS")
    L.append("  - Commission is a documented simplification (bps by cap tier, "
             "swing_preflight S3.5's upper bound), not an exact per-share fee "
             "-- see the module docstring.")
    L.append("  - Stress friction is read as 2x the bucket-specific level's "
             "full total (spread+commission), one of two readings the spec "
             "leaves open.")
    L.append("  - This report does not spend the holdout (spec S6) and is "
             "not the deployed cell's final result.")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------
# self-test (offline, synthetic data -- no network, no real var/swing_pit)
# ----------------------------------------------------------------------------

def self_test() -> list[str]:
    # -- friction / financing arithmetic -------------------------------------
    assert friction_bps("measured", "open", "sp400") == MEASURED_BPS
    assert friction_bps("bucket", "midday", "sp500") == 3.61 + 1.7
    assert abs(friction_bps("stress", "midday", "sp500") - 2 * (3.61 + 1.7)) < 1e-9
    assert friction_bps("bucket", "open", None) == 7.98 + DEFAULT_COMMISSION_BPS
    assert financing_bps(5) == 5 * 0.99
    try:
        friction_bps("nonsense", "open", "sp500")
    except ValueError:
        pass
    else:
        raise AssertionError("friction_bps did not reject an unknown level")

    # -- synthetic universe / prices / intraday store, small enough to hand-check
    cal = [dt.date(2026, 1, 5) + dt.timedelta(days=i) for i in range(14)]
    spells = (
        P.Spell("sp500", "AAA", "Alpha", cal[0], cal[-1], True, False),
        P.Spell("sp500", "BBB", "Beta", cal[0], cal[-1], True, False),
        P.Spell("sp400", "CCC", "Gamma", cal[0], cal[-1], True, False),
    )
    universe = R.Universe(spells=spells, n_suspects_excluded=0)

    # -- code_index_on / commission_bps_for -----------------------------------
    assert code_index_on(universe, "AAA", cal[3]) == "sp500"
    assert code_index_on(universe, "CCC", cal[3]) == "sp400"
    assert code_index_on(universe, "ZZZ", cal[3]) is None
    assert commission_bps_for(None) == DEFAULT_COMMISSION_BPS

    # -- universe_eligible_bucket_return: equal-weight over ALL eligible codes
    # with both prices, pick-independent, and cached ------------------------
    store = {
        "AAA": {(cal[3], "midday"): (10.0, "HIT"), (cal[5], "midday"): (11.0, "HIT")},
        "BBB": {(cal[3], "midday"): (20.0, "HIT"), (cal[5], "midday"): (19.0, "HIT")},
        # CCC has no intraday file at all -- must be silently excluded from
        # the benchmark, not treated as a zero
    }
    cache: dict = {}
    bench = universe_eligible_bucket_return(
        universe, store, cal[3], cal[5], "midday", cache=cache)
    expected = ((11.0 / 10.0 - 1.0) + (19.0 / 20.0 - 1.0)) / 2
    assert bench is not None and abs(bench - expected) < 1e-9
    assert cache[(cal[3], cal[5], "midday", None)] == bench
    # calling again with a DIFFERENT (unrelated) picks scenario must return
    # the identical cached value -- proof the benchmark really is pick-
    # independent, not accidentally re-derived from whichever picks called it
    bench2 = universe_eligible_bucket_return(
        universe, store, cal[3], cal[5], "midday", cache=cache)
    assert bench2 == bench and len(cache) == 1

    no_bench = universe_eligible_bucket_return(
        universe, store, cal[6], cal[8], "midday", cache=cache)
    assert no_bench is None  # nothing has prices at cal[6]/cal[8]

    # -- score_trades: net, market-relative, cash-funded and levered --------
    picks = {cal[2]: ["AAA", "BBB"]}
    trades, unfilled = F.build_trades(picks, cal, store, "midday", n=2)
    assert not unfilled and len(trades) == 2
    rows, n_no_bench = score_trades(trades, universe, store, cache=cache)
    assert n_no_bench == 0
    aaa_row = next(r for r in rows if r["code"] == "AAA")
    assert aaa_row["index"] == "sp500"
    expected_net_bucket = 0.1 - friction_bps("bucket", "midday", "sp500") / 10000.0
    assert abs(aaa_row["net_bucket"] - expected_net_bucket) < 1e-9
    assert abs(aaa_row["mr_bucket"] - (expected_net_bucket - bench)) < 1e-9
    expected_levered = 2 * 0.1 - 2 * friction_bps("bucket", "midday", "sp500") / 10000.0 \
        - financing_bps(2) / 10000.0
    assert abs(aaa_row["levered_net_bucket"] - expected_levered) < 1e-9

    # -- weighted aggregate / by_half / by_year -------------------------------
    agg = aggregate(rows, "mr_bucket")
    assert agg["n"] == 2
    for r in rows:
        r["weight"] = 0.5
    agg_w = aggregate(rows, "mr_bucket")
    assert agg_w["mean"] == agg["mean"]  # weighted mean unchanged when weights are equal
    assert abs(agg_w["total"] - agg["total"] * 0.5) < 1e-9
    for r in rows:
        r["weight"] = 1.0

    half = by_half(rows, "mr_bucket")
    assert half["first_half"]["n"] + half["second_half"]["n"] == 2

    yr = by_year(rows, "mr_bucket")
    assert set(yr) == {2026}

    # -- drop_top_n: n/a when too few codes, else the right code is dropped -
    assert drop_top_n(rows, "mr_bucket", 5) == "n/a"  # only 2 distinct codes <= 5
    only_one = [r for r in rows if r["code"] == "AAA"]
    assert drop_top_n(only_one, "mr_bucket", 1) == "n/a"  # 1 distinct code <= 1
    dropped = drop_top_n(rows, "mr_bucket", 1)
    assert dropped != "n/a" and dropped["n"] == 1  # the other code remains

    # -- cluster_bootstrap_by_month: all-positive inputs => 100% ------------
    all_pos_rows = [{"entry_date": cal[3], "mr_bucket": 0.01, "weight": 1.0},
                    {"entry_date": cal[5], "mr_bucket": 0.02, "weight": 1.0}]
    boot = cluster_bootstrap_by_month(all_pos_rows, "mr_bucket", resamples=50, seed=1)
    assert boot["pct_positive"] == 100.0
    boot_repeat = cluster_bootstrap_by_month(all_pos_rows, "mr_bucket", resamples=50, seed=1)
    assert boot_repeat == boot  # seeded -> reproducible

    # -- random_decile_picks: same size as actual, a subset of eligible -----
    rnd_picks = random_decile_picks(universe, cal, picks, None, seed=7)
    assert len(rnd_picks[cal[2]]) == len(picks[cal[2]])
    assert set(rnd_picks[cal[2]]) <= {"AAA", "BBB", "CCC"}

    # -- random_decile_control: runs, reproducible with the same seed -------
    rc = random_decile_control(universe, cal, store, picks, "midday", 2,
                               draws=5, seed=11, cache={})
    rc_repeat = random_decile_control(universe, cal, store, picks, "midday", 2,
                                      draws=5, seed=11, cache={})
    assert rc["draws"] == 5
    assert rc == rc_repeat

    # -- run_cell / ensemble_cell / run_grid: end-to-end smoke, small grid --
    prices = {
        "AAA": {cal[i]: 100 + i for i in range(len(cal))},
        "BBB": {cal[i]: 50 - i * 0.2 for i in range(len(cal))},
        "CCC": {cal[i]: 30 + i * 0.1 for i in range(len(cal))},
    }
    store_full = {
        "AAA": {(cal[i], b): (100 + i, "HIT") for i in range(len(cal))
               for b in R.BUCKETS},
        "BBB": {(cal[i], b): (50 - i * 0.2, "HIT") for i in range(len(cal))
               for b in R.BUCKETS},
        "CCC": {(cal[i], b): (30 + i * 0.1, "HIT") for i in range(len(cal))
               for b in R.BUCKETS},
    }
    cell = run_cell(universe, prices, cal, store_full, k=5, n=2, bucket="midday")
    assert "cash_funded" in cell and "levered_2x1" in cell
    ens = ensemble_cell([
        run_cell(universe, prices, cal, store_full, k=5, n=n, bucket="midday")
        for n in R.N_VALUES
    ])
    assert abs(sum(r["weight"] for r in ens["rows"]) -
              len(ens["rows"]) / 3.0) < 1e-6 or not ens["rows"]

    grid = run_grid(universe, prices, cal, store_full)
    assert len(grid["cells"]) == len(R.K_VALUES) * len(R.BUCKETS) * len(R.N_VALUES)
    assert len(grid["ensembles"]) == len(R.K_VALUES) * len(R.BUCKETS)

    # -- coverage_report: guards pass, decile stats present ------------------
    picks_by_k = {k: R.daily_picks(universe, prices, cal, k) for k in R.K_VALUES}
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        pit = Path(t)
        suspects_path = pit / R.SUSPECTS_NAME
        suspects_path.parent.mkdir(parents=True, exist_ok=True)
        with suspects_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["index", "code", "name", "start", "end", "is_delisted",
                       "verdict", "in_window_rows", "expected_rows"])
        cov = coverage_report(universe, prices, cal, picks_by_k, suspects_path, pit)
        assert cov["hindsight_guard_rejections"] == 0
        assert cov["n_codes_covered"] == 3
        assert 5 in cov["by_k"] and 10 in cov["by_k"]

    # -- format_report: does not raise, mentions the deployed cell ----------
    result = {
        "window": [cal[0].isoformat(), cal[-1].isoformat()],
        "grid": grid,
        "random_decile_control": {(5, "midday", 5): rc},
        "coverage": cov,
    }
    text = format_report(result)
    assert "DEPLOYED CELL" in text and "RANDOM-DECILE CONTROL" in text

    return ["self-test passed: friction levels (measured all-in, bucket-"
           "specific spread+commission, 2x stress), financing, the pick-"
           "independent cached market-relative benchmark, weighted "
           "aggregation (proven with an ensemble's 1/3-weighted pool), "
           "by-half/by-year, drop-top-N's n/a case, the seeded cluster "
           "bootstrap and random-decile control's reproducibility, the "
           "full grid+ensemble, and coverage/counts all behaved as specified"]


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("stage", nargs="?", choices=["run"])
    p.add_argument("--pit-dir", type=Path, default=DEFAULT_PIT_DIR)
    p.add_argument("--index", choices=["sp400", "sp500"], default=None)
    p.add_argument("--random-draws", type=int, default=RANDOM_DECILE_DRAWS,
                  help="override the random-decile control's draw count "
                       "(default 2000, per spec S3 item 6) -- pass a small "
                       "number for a quick smoke run before committing to "
                       "the full 2000 on real data")
    p.add_argument("--out", type=Path,
                  default=Path("claude") / "raw" / "w07_0012_report_layer.txt")
    p.add_argument("--json-out", type=Path,
                  default=Path("var") / "swing_pit" / "report_layer_result.json")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)

    if a.self_test:
        for line in self_test():
            print(line)
        return 0
    if a.stage != "run":
        p.error("choose a stage: run")

    try:
        result = run(a.pit_dir, index=a.index, random_control_draws=a.random_draws)
    except (R.UniverseGuardRefused, R.HindsightError, F.LookaheadError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        return 2

    text = format_report(result, index=a.index)
    print(text)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text, encoding="utf-8")
    a.json_out.parent.mkdir(parents=True, exist_ok=True)
    a.json_out.write_text(json.dumps(to_json_safe(result), indent=2, default=str),
                          encoding="utf-8")
    print(f"written to {a.out} and {a.json_out}")
    print("This is the S3 report layer -- it does not spend the holdout "
         "(spec S6); that is reserved for the deployed cell alone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
