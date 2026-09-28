#!/usr/bin/env python3
"""W16 session-baselines backtest runner: G5 (costs) integration, trade
generation for all three baselines, dollar P&L at L1/L2/L3, the control
comparison (sec 9 #5), and full sec 5 reporting (exit reasons, sample
trades, account view). Board W16-0003 subitem 3 built this engine;
subitem 4 (Ben, locally, real archive) is running it -- this module is
what subitem 4's command calls.

    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.runner --preflight
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.runner --backtest --skip-controls   # fast sanity pass
    D:\\Trading\\.venv\\Scripts\\python.exe -m strategy.w16.runner --backtest                    # full run, sec 9 #5 included

WHAT IS, AND IS NOT, BUILT HERE (read this before assuming a number below
is a finished sec 9 verdict)
------------------------------------------------------------------------
Built: trade generation for B1/B2/B3 (via strategy.w16.signals), cost/P&L at
L1/L2/L3 (via strategy.w16.costs), per-year and both-halves aggregation,
exit-reason counts, sample trades and account view (sec 5 items 1-3/7/8),
the holdout gate (G3, strategy.w16.holdout), and EIGHT of sec 9's nine pass
criteria: #1 net>0, #2 both halves net>0, #3 no year >50% of net, #4 month
bootstrap (2,000 resamples), #5 beats its own random-timing control (1,000
seeded draws via strategy.w16.controls, run for real by `compute_controls`
-- B1 against C-B1, B2 against C-O2 AND C-O3 per sec 9's own AND-condition,
B3 against C-B3), #6 net>0 at L3, #7 net>0 after dropping the best 1% of
trades, #9 >=300 trades. `--skip-controls` skips #5's 1,000 draws for a
fast sanity pass on trade counts and net before committing to the full run
(#5 then reports `None`, not False).

Also built (board W16-0005): #8 (neighbour grid, sec 7.3) -- re-parameterized
B1/B2/B3 variants (range length, target ratio, entry/exit clock time, bar
size, flip-confirmation count) via strategy.w16.grid, on the SAME
detection functions as the registered rule (strategy.w16.signals, now
parameterized) and the SAME pricing as the registered run (price_all /
summarize below). `run_cell` runs all 9 cells and supplies the resulting
`neighbour_grid_share` to `score_cell`; `--skip-grid` skips it for a fast
sanity pass, same shape as `--skip-controls`. `score_cell`'s return dict
has `neighbour_grid_share` explicitly `None` when the caller withheld it
(`--skip-grid`), rather than a silently omitted key that could be mistaken
for "not applicable".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from collections import Counter

from strategy.w16 import controls as CTRL
from strategy.w16 import holdout as H
from strategy.w16 import signals as SIG
from strategy.w16 import sessions as S
from strategy.w16.costs import FULL_TO_MICRO, OVERNIGHT_MARGIN, pnl_dollars, trade_cost
from strategy.w16.preflight import ROOTS, load_root_bars, session_frames

LEVELS = ("L1", "L2", "L3")
SCORE_LEVEL = "L2"
MIN_TRADES = 300
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_PASS_PCT = 0.99          # sec 9 #4: raised from 95% for 6 scored cells
ACCOUNT_USD = 22129.0              # sec 2 -- the project's standard account


# ---------------------------------------------------------------------
# trade generation (one baseline, one market, training or holdout dates)
# ---------------------------------------------------------------------

def generate_b1_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                       target_r: float = 2.0, range_minutes: int = 30) -> list[dict]:
    """target_r/range_minutes: sec 7.3 grid dimensions (registered 2.0/30,
    the defaults) -- passed straight through to SIG.orb_session so the
    grid (strategy.w16.grid) generates trades through this SAME function,
    not a copy of it. Board W16-0005."""
    out = []
    for date_str in sorted(dates):
        if date_str not in frames:
            continue
        res = SIG.orb_session(frames[date_str], date_str, market=market,
                              target_r=target_r, range_minutes=range_minutes)
        if res["skipped"] or res["trade"] is None:
            continue
        out.append(res["trade"])
    return out


def generate_b2_trades(frames: dict[str, pd.DataFrame], market: str, ordered_days: list[str], *,
                       entry_time=None, exit_time=None) -> list[dict]:
    """entry_time/exit_time: sec 7.3 grid dimensions (registered None/None,
    meaning the registered 15:59-close/09:30-open rule -- see
    SIG.overnight_trade). `frames` must be wide enough to contain the
    requested clock times when they are given (strategy.w16.sessions.
    session_frames_wide, not the RTH-only session_frames) -- the registered
    call (entry_time=exit_time=None) works with either. Board W16-0005."""
    out = []
    for a, b in zip(ordered_days, ordered_days[1:]):
        if a not in frames or b not in frames:
            continue
        res = SIG.overnight_trade(frames[a], frames[b], a, b, market=market,
                                  entry_time=entry_time, exit_time=exit_time)
        if res["skipped"]:
            continue
        t = res["trade"]
        t["hold_length"] = str(pd.Timestamp(t["exit_bar_time"]) - pd.Timestamp(t["entry_bar_time"]))
        t["entry_time"] = t["entry_bar_time"]
        out.append(t)
    return out


def generate_b3_trades(frames: dict[str, pd.DataFrame], market: str, dates, *,
                       flip_confirm: int = 1) -> list[dict]:
    """flip_confirm: sec 7.3 grid dimension 2 (registered 1, the default)
    -- passed straight through to SIG.vwap_flip_session. `frames` may hold
    N-minute resampled bars (strategy.w16.sessions.resample_session_bars)
    for the grid's bar-size dimension; this function does not care, it
    only calls vwap_flip_session on whatever frame each date maps to.
    Board W16-0005."""
    out = []
    for date_str in sorted(dates):
        if date_str not in frames:
            continue
        res = SIG.vwap_flip_session(frames[date_str], date_str, market=market,
                                    flip_confirm=flip_confirm)
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
              control_deterministic: float | None = None,
              neighbour_grid_share: float | None = None) -> dict:
    """sec 9's nine criteria, on the SCORE_LEVEL (L2) trade list, with #6
    read off the L3 list already computed alongside it.

    #5 ("beats its controls on net", sec 9): `control_nets` is the cell's
    own random-timing control distribution (C-B1 for B1, C-O3 for B2, C-B3
    for B3) -- the p95 comparator every baseline needs. B2's row in sec 9
    is an AND of two conditions ("B2 > C-O2 and > C-O3 p95"); the other
    baselines have only the p95 test. `control_deterministic` carries that
    extra condition (C-O2's own net) and is ignored (has no effect) unless
    supplied -- so B1/B3 callers that never pass it get exactly the single
    p95 test, unchanged from before this was added.
    #8 (neighbour grid) is unchanged: `None` until a caller supplies
    `neighbour_grid_share` -- see module docstring for why that is not
    built yet."""
    l2 = priced_by_level["L2"]
    l3 = priced_by_level["L3"]
    l2_summary = summarize(l2)
    halves = both_halves(l2)
    yearly = by_year(l2)
    total_net = l2_summary["net"]
    year_nets = {y: v["net"] for y, v in yearly.items()}
    max_year_share = (max(abs(v) for v in year_nets.values()) / abs(total_net)
                      if year_nets and total_net != 0 else None)

    if control_nets is None:
        crit5 = None
    else:
        beats_p95 = total_net > float(np.percentile(control_nets, 95))
        crit5 = beats_p95 and (total_net > control_deterministic
                               if control_deterministic is not None else True)

    criteria = {
        "1_net_positive": total_net > 0,
        "2_both_halves_positive": halves["early"]["net"] > 0 and halves["late"]["net"] > 0,
        "3_no_year_over_50pct": (max_year_share is not None and max_year_share <= 0.5),
        "4_month_bootstrap": bootstrap_by_month(l2)["pass"],
        "5_beats_control": crit5,
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
# sec 5 reporting: exit reasons, sample trades, account view
# ---------------------------------------------------------------------

def exit_reason_counts(priced: list[dict]) -> dict:
    """sec 5 item 3: counts by exit_reason (B1/C-B1: stop/target/time_exit;
    B3/C-B3: flip/flat_at_close). Trades with no exit_reason (B2 and its
    controls, which have none) are omitted rather than miscounted."""
    return dict(Counter(t["exit_reason"] for t in priced if "exit_reason" in t))


def sample_trades(priced: list[dict], n: int = 20) -> list[dict]:
    """sec 5 item 8: n trades evenly spaced through the dated list (every
    ~1/nth), not the best n -- so a run with fewer than n trades just
    returns all of them."""
    if not priced:
        return []
    dated = sorted(priced, key=lambda t: t["date"])
    if len(dated) <= n:
        return dated
    step = len(dated) / n
    positions = sorted({min(int(i * step), len(dated) - 1) for i in range(n)})
    return [dated[i] for i in positions]


def account_view(priced: list[dict], baseline: str, market: str,
                 account_usd: float = ACCOUNT_USD) -> dict:
    """sec 5 item 7: equity curve summary at $22,129 fixed size, 1 micro;
    for B2, the NinjaTrader overnight margin (G5, Amendment A) checked
    against the account, reported never scored."""
    if not priced:
        out = {"equity_final": 0.0, "max_drawdown_usd": 0.0,
              "max_drawdown_pct_of_account": 0.0}
    else:
        dated = sorted(priced, key=lambda t: t["date"])
        nets = np.array([t["net"] for t in dated])
        equity = np.cumsum(nets)
        running_max = np.maximum.accumulate(equity)
        drawdown = equity - running_max
        max_dd = float(drawdown.min())
        out = {"equity_final": float(equity[-1]), "max_drawdown_usd": max_dd,
              "max_drawdown_pct_of_account": abs(max_dd) / account_usd * 100.0}
    if baseline == "B2":
        micro = FULL_TO_MICRO[market]
        margin = OVERNIGHT_MARGIN[micro]
        out["overnight_margin"] = margin
        out["margin_initial_within_account"] = margin["initial"] <= account_usd
    return out


# ---------------------------------------------------------------------
# controls (sec 9 #5): C-B1 / C-O2+C-O3 / C-B3, run for real at N_DRAWS
# ---------------------------------------------------------------------

N_DRAWS = CTRL.N_DRAWS


def b3_flip_counts(frames: dict[str, pd.DataFrame], market: str, dates) -> dict[str, int]:
    """Per-day flip counts on the given (training) dates -- what C-B3 needs
    to draw a matched number of random flips per day. Re-runs
    vwap_flip_session (already run once by generate_b3_trades); cheap next
    to the 1,000 control draws themselves, and keeps this function
    independent of generate_b3_trades's own return shape."""
    out = {}
    for date_str in dates:
        if date_str not in frames:
            continue
        res = SIG.vwap_flip_session(frames[date_str], date_str, market=market)
        if res["skipped"]:
            continue
        out[date_str] = res["n_flips"]
    return out


def training_full_index_price(df_1m: pd.DataFrame, train_dates: set) -> tuple[pd.DatetimeIndex, pd.Series]:
    """Every 1-minute bar timestamp (NOT RTH-windowed -- a C-O3 draw can
    start anywhere) whose ET calendar date is in `train_dates`, plus its
    close price -- what C-O3 draws its random window against. `df_1m` is
    the full loaded root bars (strategy.w16.preflight.load_root_bars)."""
    from strategy.w16.readback import local_naive_et
    df = df_1m.sort_index()
    naive = local_naive_et(df.index)
    date_strs = naive.strftime("%Y-%m-%d")
    mask = np.asarray(date_strs.isin(train_dates))
    sub = df[mask]
    return pd.DatetimeIndex(sub.index), sub["close"]


def compute_controls(baseline: str, market: str, *, frames=None, trades=None,
                     full_index=None, price_at=None, flip_counts=None,
                     level: str = SCORE_LEVEL, n_draws: int = N_DRAWS,
                     progress: bool = True) -> dict:
    """Runs the registered control for one cell, `n_draws` seeded draws
    (sec 7.1: 1,000). Returns {"random_nets": [...], "deterministic_net":
    float|None} -- the deterministic value is C-O2's net and is only
    non-None for B2 (sec 9 #5's extra AND-condition)."""
    random_nets: list[float] = []
    deterministic_net = None
    if baseline == "B1":
        naive_cache = CTRL.naive_time_cache(frames, {t["date"] for t in trades})
        for i in range(n_draws):
            draw = CTRL.c_b1_draw(trades, frames, i, naive_cache=naive_cache)
            random_nets.append(summarize(price_all(draw, level))["net"])
            if progress and (i + 1) % 100 == 0:
                print(f"    C-B1 {market}: {i + 1}/{n_draws} draws")
    elif baseline == "B2":
        candidates_cache = CTRL.o3_candidates_cache(trades, full_index)
        for i in range(n_draws):
            draw = CTRL.c_o3_draw(trades, full_index, price_at, i,
                                  candidates_cache=candidates_cache)
            random_nets.append(summarize(price_all(draw, level))["net"])
            if progress and (i + 1) % 100 == 0:
                print(f"    C-O3 {market}: {i + 1}/{n_draws} draws")
        o2 = CTRL.c_o2_trades(trades, frames)
        deterministic_net = summarize(price_all(o2, level))["net"]
    elif baseline == "B3":
        naive_cache = CTRL.naive_time_cache(frames, flip_counts.keys(), sort=True)
        for i in range(n_draws):
            legs = CTRL.c_b3_draw(flip_counts, frames, i, naive_cache=naive_cache)
            for leg in legs:
                leg["market"] = market
            draw = SIG.pair_b3_legs(legs)
            random_nets.append(summarize(price_all(draw, level))["net"])
            if progress and (i + 1) % 100 == 0:
                print(f"    C-B3 {market}: {i + 1}/{n_draws} draws")
    else:
        raise ValueError(f"unknown baseline {baseline!r}")
    return {"random_nets": random_nets, "deterministic_net": deterministic_net}


# ---------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------

def run_cell(baseline: str, market: str, archive, *, spend_holdout_candidate: str | None = None,
            compute_controls_flag: bool = True, n_control_draws: int = N_DRAWS,
            compute_grid_flag: bool = True) -> dict:
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

    control_nets = None
    control_deterministic = None
    control_summary = None
    if compute_controls_flag:
        train_dates = set(dates)
        if baseline == "B1":
            ctrl = compute_controls(baseline, market, frames=frames, trades=trades,
                                    n_draws=n_control_draws)
        elif baseline == "B2":
            full_index, price_at = training_full_index_price(df_1m, train_dates)
            ctrl = compute_controls(baseline, market, frames=frames, trades=trades,
                                    full_index=full_index, price_at=price_at,
                                    n_draws=n_control_draws)
        elif baseline == "B3":
            flip_counts = b3_flip_counts(frames, market, dates)
            ctrl = compute_controls(baseline, market, frames=frames, trades=trades,
                                    flip_counts=flip_counts, n_draws=n_control_draws)
        control_nets = ctrl["random_nets"]
        control_deterministic = ctrl["deterministic_net"]
        control_summary = {
            "n_draws": len(control_nets),
            "p5": float(np.percentile(control_nets, 5)) if control_nets else None,
            "p50": float(np.percentile(control_nets, 50)) if control_nets else None,
            "p95": float(np.percentile(control_nets, 95)) if control_nets else None,
            "deterministic": control_deterministic,
        }

    neighbour_grid = None
    if compute_grid_flag:
        from strategy.w16 import grid as GRID
        neighbour_grid = GRID.run_neighbour_grid(baseline, market, archive,
                                                 df_1m=df_1m, frames=frames)
    neighbour_grid_share = neighbour_grid["share_positive"] if neighbour_grid else None

    result.update(score_cell(priced_by_level, control_nets=control_nets,
                             control_deterministic=control_deterministic,
                             neighbour_grid_share=neighbour_grid_share))
    result["by_level"] = {lvl: summarize(rows) for lvl, rows in priced_by_level.items()}
    l2 = priced_by_level["L2"]
    result["exit_reasons"] = exit_reason_counts(l2)
    result["sample_trades"] = sample_trades(l2)
    result["account_view"] = account_view(l2, baseline, market)
    result["control_summary"] = control_summary
    result["neighbour_grid"] = neighbour_grid
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="W16 session-baselines runner.")
    ap.add_argument("--archive", type=Path, default=None)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--backtest", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-controls", action="store_true",
                    help="Skip the 1,000-draw control comparison (sec 9 #5) -- fast sanity "
                         "pass on trade counts/net before committing to the full run.")
    ap.add_argument("--skip-grid", action="store_true",
                    help="Skip the sec 7.3 neighbour grid (sec 9 #8, 9 cells per baseline) "
                         "-- fast sanity pass; #8 then reports None, not False.")
    ap.add_argument("--n-control-draws", type=int, default=N_DRAWS,
                    help=f"Control draws per cell (registered: {N_DRAWS}). Lower only for a "
                         "quick look; the registered pass bar needs the full count.")
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
            print(f"running {baseline} {market} (training side)"
                 f"{' [no controls]' if a.skip_controls else f' [{a.n_control_draws} control draws]'}...")
            report[f"{baseline}-{market}"] = run_cell(
                baseline, market, archive,
                compute_controls_flag=not a.skip_controls,
                n_control_draws=a.n_control_draws,
                compute_grid_flag=not a.skip_grid)
    for key, cell in report.items():
        s = cell["by_level"]["L2"]
        ctrl = cell.get("control_summary")
        ctrl_str = f"  control_p95=${ctrl['p95']:,.2f}" if ctrl else ""
        print(f"{key:6s}  n={s['n_trades']:5d}  net(L2)=${s['net']:,.2f}{ctrl_str}  "
              f"passes_all_computed={cell['criteria']['passes_all_computed']}")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\nfull report: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
