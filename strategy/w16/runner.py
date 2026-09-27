#!/usr/bin/env python3
"""W16 session-baselines backtest runner: G5 (costs) integration, trade
generation for all three baselines, dollar P&L at L1/L2/L3, and the sec 9
scoring criteria that don't require a separately-run control or grid.
Board W16-0003 subitem 3 ("engine, costs ... holdout ledger, look-ahead
tests, pre-flight (G2-G5)"); the actual training-side run against the real
archive is subitem 4 (Ben, locally) -- this module is the engine that run
calls, not the run itself.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.runner --preflight
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.runner --backtest

WHAT IS, AND IS NOT, BUILT HERE (read this before assuming a number below
is a finished sec 9 verdict)
------------------------------------------------------------------------
Built: trade generation for B1/B2/B3 (via strategy.w16.signals), cost/P&L at
L1/L2/L3 (via strategy.w16.costs), per-year and both-halves aggregation, exit-
reason and voided/skipped counts (sec 5 items 1-3), the holdout gate (G3,
strategy.w16.holdout), and four of sec 9's nine pass criteria that need
nothing but the trade list itself: #1 net>0, #2 both halves net>0, #3 no
year >50% of net, #7 net>0 after dropping the best 1% of trades, #9 >=300
trades. #4 (month bootstrap, 2,000 resamples) is implemented
(`bootstrap_by_month`) since it needs only the trade list and a seed.

NOT built here, on purpose -- each needs machinery beyond "one cell's own
trade list": #5 (beats its own random-timing control's p95) needs 1,000
control draws actually run (strategy.w16.controls has the draw functions;
`score_cell` accepts pre-computed `control_nets` and scores #5 if given
them, and reports #5 as `None` -- not False -- if not); #6 (net>0 at L3) IS
computed (L3 is just another cost level, already available) but is listed
here for completeness; #8 (neighbour grid, sec 7.3) needs re-parameterized
versions of the B1/B2/B3 rules (range length, target ratio, bar size, ...)
that do not exist yet -- building those is a separate, materially larger
piece of work than re-running the registered rule, and REGISTERED sec 7.3
is explicit that "the grid never replaces the registered rule", so its
absence does not block reading #1-#4/#6/#7/#9 on the registered cells.
`score_cell`'s return dict has `beats_control` and `neighbour_grid_share`
both explicitly `None` until those are supplied, rather than silently
omitted keys a caller could mistake for "not applicable".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.w16 import holdout as H
from strategy.w16 import signals as SIG
from strategy.w16 import sessions as S
from strategy.w16.costs import FULL_TO_MICRO, pnl_dollars, trade_cost
from strategy.w16.preflight import ROOTS, load_root_bars, session_frames

LEVELS = ("L1", "L2", "L3")
SCORE_LEVEL = "L2"
MIN_TRADES = 300
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_PASS_PCT = 0.99          # sec 9 #4: raised from 95% for 6 scored cells


# ---------------------------------------------------------------------
# trade generation (one baseline, one market, training or holdout dates)
# ---------------------------------------------------------------------

def generate_b1_trades(frames: dict[str, pd.DataFrame], market: str, dates) -> list[dict]:
    out = []
    for date_str in sorted(dates):
        if date_str not in frames:
            continue
        res = SIG.orb_session(frames[date_str], date_str, market=market)
        if res["skipped"] or res["trade"] is None:
            continue
        out.append(res["trade"])
    return out


def generate_b2_trades(frames: dict[str, pd.DataFrame], market: str, ordered_days: list[str]) -> list[dict]:
    out = []
    for a, b in zip(ordered_days, ordered_days[1:]):
        if a not in frames or b not in frames:
            continue
        res = SIG.overnight_trade(frames[a], frames[b], a, b, market=market)
        if res["skipped"]:
            continue
        t = res["trade"]
        t["hold_length"] = str(pd.Timestamp(frames[b].sort_index().index[0])
                                - pd.Timestamp(frames[a].sort_index().index[-1]))
        t["entry_time"] = str(frames[a].sort_index().index[-1])
        out.append(t)
    return out


def generate_b3_trades(frames: dict[str, pd.DataFrame], market: str, dates) -> list[dict]:
    out = []
    for date_str in sorted(dates):
        if date_str not in frames:
            continue
        res = SIG.vwap_flip_session(frames[date_str], date_str, market=market)
        if res["skipped"]:
            continue
        out.extend(SIG.pair_b3_legs(res["legs"]))
    return out


# ---------------------------------------------------------------------
# cost/P&L
# ---------------------------------------------------------------------

def price_trade(trade: dict, level: str) -> dict:
    """Add gross/cost/net (per 1 micro) at one friction level to a copy of
    `trade`. Voided trades price to all-zero (they are reported, never
    scored, sec 5 item 3)."""
    out = dict(trade)
    market = trade["market"]
    micro = FULL_TO_MICRO[market]
    if trade.get("voided"):
        out.update(level=level, gross=0.0, cost=0.0, net=0.0)
        return out
    entry_px = trade.get("fill_price", trade.get("entry_price"))
    exit_px = trade["exit_price"]
    direction = trade["direction"]
    gross = pnl_dollars(micro, entry_px, exit_px, direction)
    cost = trade_cost(micro, level, entry_kind=trade["entry_fill_kind"],
                      exit_kind=trade["exit_fill_kind"])
    out.update(level=level, gross=gross, cost=cost, net=gross - cost)
    return out


def price_all(trades: list[dict], level: str) -> list[dict]:
    return [price_trade(t, level) for t in trades if not t.get("voided")]


def summarize(priced: list[dict]) -> dict:
    if not priced:
        return {"n_trades": 0, "wins": 0, "losses": 0, "gross": 0.0, "cost": 0.0,
                "net": 0.0, "avg_win": None, "avg_loss": None, "largest_loss": None,
                "max_drawdown": None}
    nets = [t["net"] for t in priced]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    equity = np.cumsum(nets)
    running_max = np.maximum.accumulate(equity)
    drawdown = equity - running_max
    return {
        "n_trades": len(priced), "wins": len(wins), "losses": len(losses),
        "gross": float(sum(t["gross"] for t in priced)),
        "cost": float(sum(t["cost"] for t in priced)),
        "net": float(sum(nets)),
        "avg_win": float(np.mean(wins)) if wins else None,
        "avg_loss": float(np.mean(losses)) if losses else None,
        "largest_loss": float(min(nets)) if nets else None,
        "max_drawdown": float(drawdown.min()) if len(drawdown) else None,
    }


def by_year(priced: list[dict]) -> dict[int, dict]:
    years: dict[int, list[dict]] = {}
    for t in priced:
        y = int(t["date"][:4])
        years.setdefault(y, []).append(t)
    return {y: summarize(rows) for y, rows in sorted(years.items())}


def both_halves(priced: list[dict]) -> dict:
    """sec 9 #2/#3: split at the median trade date."""
    if not priced:
        return {"early": summarize([]), "late": summarize([]), "split_date": None}
    dated = sorted(priced, key=lambda t: t["date"])
    mid_date = dated[len(dated) // 2]["date"]
    early = [t for t in priced if t["date"] < mid_date]
    late = [t for t in priced if t["date"] >= mid_date]
    return {"early": summarize(early), "late": summarize(late), "split_date": mid_date}


def drop_best_pct(priced: list[dict], pct: float = 0.01) -> dict:
    """sec 9 #7: net after dropping the best `pct` of trades by net $."""
    if not priced:
        return summarize([])
    ordered = sorted(priced, key=lambda t: t["net"], reverse=True)
    n_drop = int(round(len(ordered) * pct))
    kept = ordered[n_drop:]
    return summarize(kept)


def bootstrap_by_month(priced: list[dict], *, n_draws: int = BOOTSTRAP_DRAWS,
                       seed: int = 0) -> dict:
    """sec 9 #4: resample the training months WITH REPLACEMENT `n_draws`
    times (seeded, reproducible); the share of draws with net > 0."""
    if not priced:
        return {"n_draws": n_draws, "pct_net_positive": None, "pass": False}
    by_month: dict[str, list[float]] = {}
    for t in priced:
        by_month.setdefault(t["date"][:7], []).append(t["net"])
    months = sorted(by_month)
    rng = np.random.default_rng(seed)
    n_pos = 0
    for _ in range(n_draws):
        draw_months = rng.choice(months, size=len(months), replace=True)
        total = sum(sum(by_month[m]) for m in draw_months)
        if total > 0:
            n_pos += 1
    pct = n_pos / n_draws
    return {"n_draws": n_draws, "pct_net_positive": pct, "pass": pct >= BOOTSTRAP_PASS_PCT}


def score_cell(priced_by_level: dict[str, list[dict]], *, control_nets: list[float] | None = None,
              neighbour_grid_share: float | None = None) -> dict:
    """sec 9's nine criteria, on the SCORE_LEVEL (L2) trade list, with #6
    read off the L3 list already computed alongside it. See module
    docstring for what #5/#8 need that this function alone cannot supply."""
    l2 = priced_by_level["L2"]
    l3 = priced_by_level["L3"]
    l2_summary = summarize(l2)
    halves = both_halves(l2)
    yearly = by_year(l2)
    total_net = l2_summary["net"]
    year_nets = {y: v["net"] for y, v in yearly.items()}
    max_year_share = (max(abs(v) for v in year_nets.values()) / abs(total_net)
                      if year_nets and total_net != 0 else None)

    criteria = {
        "1_net_positive": total_net > 0,
        "2_both_halves_positive": halves["early"]["net"] > 0 and halves["late"]["net"] > 0,
        "3_no_year_over_50pct": (max_year_share is not None and max_year_share <= 0.5),
        "4_month_bootstrap": bootstrap_by_month(l2)["pass"],
        "5_beats_control": (None if control_nets is None else
                            total_net > float(np.percentile(control_nets, 95))),
        "6_net_positive_at_l3": summarize(l3)["net"] > 0,
        "7_survives_dropping_best_1pct": drop_best_pct(l2)["net"] > 0,
        "8_neighbour_grid_6_of_9": (None if neighbour_grid_share is None else
                                    neighbour_grid_share >= 6.0 / 9.0),
        "9_min_trades": l2_summary["n_trades"] >= MIN_TRADES,
    }
    computed = [v for v in criteria.values() if v is not None]
    criteria["passes_all_computed"] = bool(computed) and all(computed)
    return {"criteria": criteria, "l2_summary": l2_summary, "both_halves": halves,
           "by_year": yearly, "max_year_share_of_net": max_year_share}


# ---------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------

def run_cell(baseline: str, market: str, archive, *, spend_holdout_candidate: str | None = None) -> dict:
    df_1m = load_root_bars(archive, market)
    frames = session_frames(df_1m)
    all_dates = sorted(frames.keys())

    if spend_holdout_candidate:
        candidate = f"{baseline}-{market}"
        if candidate != spend_holdout_candidate:
            dates, _, label = H.split_dates(all_dates)          # training only
        else:
            dates, _, label = H.split_dates(all_dates, spend=True, candidate=candidate)
    else:
        dates, _, label = H.split_dates(all_dates)

    if baseline == "B1":
        trades = generate_b1_trades(frames, market, dates)
    elif baseline == "B2":
        ordered = [d for d in all_dates if d in set(dates)]
        trades = generate_b2_trades(frames, market, ordered)
    elif baseline == "B3":
        trades = generate_b3_trades(frames, market, dates)
    else:
        raise ValueError(f"unknown baseline {baseline!r}")

    priced_by_level = {lvl: price_all(trades, lvl) for lvl in LEVELS}
    n_voided = sum(1 for t in trades if t.get("voided"))
    result = {"baseline": baseline, "market": market, "date_side": label,
             "n_raw_trades": len(trades), "n_voided": n_voided}
    result.update(score_cell(priced_by_level))
    result["by_level"] = {lvl: summarize(rows) for lvl, rows in priced_by_level.items()}
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W16 session-baselines runner.")
    ap.add_argument("--archive", type=Path, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--backtest", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    from common.tsmom_fetch import default_archive
    archive = a.archive or default_archive()

    if a.preflight:
        from strategy.w16.preflight import run as preflight_run
        report = preflight_run(archive)
        print(json.dumps(report, indent=2, default=str)[:2000])
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return 0

    report = {}
    for baseline in ("B1", "B2", "B3"):
        for market in ROOTS:
            print(f"running {baseline} {market} (training side)...")
            report[f"{baseline}-{market}"] = run_cell(baseline, market, archive)
    for key, cell in report.items():
        s = cell["by_level"]["L2"]
        print(f"{key:6s}  n={s['n_trades']:5d}  net(L2)=${s['net']:,.2f}  "
              f"passes_all_computed={cell['criteria']['passes_all_computed']}")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
