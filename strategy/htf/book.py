#!/usr/bin/env python3
"""HTF-Ben trade-book aggregation and sec.4 scoring. W15-0004 step 7
checkpoint 6. REGISTERED_htf_ben_v0.md sec 3 items 1,2,3,4,5,10 and sec 4
(criteria 1,2,3,4,7,9 -- criteria 5,6 are one-line comparisons against
controls.py's own trade lists; criterion 8 needs the neighbour grid, a
separate checkpoint; see score() for how the caller supplies those two).

Every function here takes a plain list[runner.Trade] (v0, C1, C2 or a C3
draw all produce the same Trade shape) plus (symbol, level, qty) -- nothing
here knows which variant/scenario produced the trades, so the same code
scores v0, reports C1/C2, and feeds C3's per-draw net.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from strategy.htf import costs as C

BOOTSTRAP_N = 2000


def net_table(trades: list, symbol: str, level: str, qty: int = 1) -> pd.DataFrame:
    """One row per trade: year (of the entry session), net $, exit_reason,
    trail_started, hold hours. The frame every other function in this
    module is built from."""
    rows = []
    for t in trades:
        entry_t = pd.Timestamp(t.entry_t)
        exit_t = pd.Timestamp(t.exit_t)
        rows.append({
            "session": t.session, "year": entry_t.year,
            "entry_t": entry_t, "exit_t": exit_t,
            "direction": t.direction, "exit_reason": t.exit_reason,
            "trail_started": t.trail_started, "n_rolls": t.n_rolls,
            "gross": t.gross_pnl(symbol, qty), "cost": t.cost(symbol, level, qty),
            "net": t.net_pnl(symbol, level, qty),
            "hold_hours": (exit_t - entry_t) / pd.Timedelta(hours=1),
        })
    return pd.DataFrame(rows, columns=["session", "year", "entry_t", "exit_t", "direction",
                                       "exit_reason", "trail_started", "n_rolls", "gross",
                                       "cost", "net", "hold_hours"])


@dataclass
class Summary:
    """sec 3 item 1: dollars-and-trades headline at one friction level."""
    trades: int
    wins: int
    losses: int
    gross: float
    cost: float
    net: float
    avg_win: float | None
    avg_loss: float | None
    largest_loss: float | None
    worst_loss_streak: int


def summarize(df: pd.DataFrame) -> Summary:
    n = len(df)
    if n == 0:
        return Summary(0, 0, 0, 0.0, 0.0, 0.0, None, None, None, 0)
    wins_mask = df["net"] > 0
    losses_mask = df["net"] < 0
    wins = df.loc[wins_mask, "net"]
    losses = df.loc[losses_mask, "net"]
    streak = worst_loss_streak(df["net"].to_numpy())
    return Summary(
        trades=n, wins=int(wins_mask.sum()), losses=int(losses_mask.sum()),
        gross=float(df["gross"].sum()), cost=float(df["cost"].sum()), net=float(df["net"].sum()),
        avg_win=(float(wins.mean()) if len(wins) else None),
        avg_loss=(float(losses.mean()) if len(losses) else None),
        largest_loss=(float(losses.min()) if len(losses) else None),
        worst_loss_streak=streak,
    )


def worst_loss_streak(net: np.ndarray) -> int:
    """Longest run of consecutive net<=0 trades, in TRADE ORDER (the frame
    must already be sorted by entry_t -- net_table's row order preserves
    the caller's trade-list order, which runner.simulate/controls.simulate_c2
    both produce time-ordered)."""
    best = cur = 0
    for x in net:
        if x <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def year_table(df: pd.DataFrame) -> dict[int, float]:
    """sec 3 item 2: net per calendar year, EVERY year in [min,max] present
    (0.0, not omitted, for a year with no trades -- 'none omitted')."""
    if df.empty:
        return {}
    lo, hi = int(df["year"].min()), int(df["year"].max())
    by_year = df.groupby("year")["net"].sum()
    return {y: float(by_year.get(y, 0.0)) for y in range(lo, hi + 1)}


def split_halves(df: pd.DataFrame) -> tuple[float, float]:
    """sec 3 item 3: split at the MEDIAN TRADE date (not a fixed calendar
    date), split not swept -- a trade at exactly the median goes to the
    first half (< vs >=, an arbitrary but fixed tie-break, same either way
    for an odd trade count)."""
    if df.empty:
        return 0.0, 0.0
    median_t = df["entry_t"].median()
    first = df.loc[df["entry_t"] < median_t, "net"].sum()
    second = df.loc[df["entry_t"] >= median_t, "net"].sum()
    return float(first), float(second)


def top_year_share(year_net: dict[int, float]) -> tuple[int | None, float]:
    """sec 4 criterion 3: the year supplying the largest share of TOTAL net
    (share of the sum, not of sum-of-positives -- a year can exceed 100%
    when other years are net negative, which is itself the finding)."""
    if not year_net:
        return None, 0.0
    total = sum(year_net.values())
    if total == 0:
        return None, 0.0
    top_year = max(year_net, key=lambda y: abs(year_net[y]))
    return top_year, year_net[top_year] / total


def exit_reason_counts(df: pd.DataFrame) -> dict[str, int]:
    """sec 3 item 4."""
    if df.empty:
        return {}
    return {k: int(v) for k, v in df["exit_reason"].value_counts().items()}


def trail_started_share(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    return float(df["trail_started"].mean())


def median_hold_hours(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    return float(df["hold_hours"].median())


def sample_trades(trades: list, symbol: str, level: str, qty: int = 1, every: int = 20) -> list[dict]:
    """sec 3 item 10: every 1/every'th trade (not the best), in order."""
    out = []
    for i in range(0, len(trades), every):
        t = trades[i]
        out.append({
            "entry_t": str(t.entry_t), "exit_t": str(t.exit_t), "direction": t.direction,
            "fill": t.fill_raw, "stop": None if pd.isna(t.initial_stop_adj) else t.initial_stop_adj,
            "exit": t.exit_price_raw, "exit_reason": t.exit_reason,
            "net": t.net_pnl(symbol, level, qty),
        })
    return out


def bootstrap_by_year(year_net: dict[int, float], *, n: int = BOOTSTRAP_N, seed: int = 0) -> float:
    """sec 4 criterion 4: cluster bootstrap BY CALENDAR YEAR -- each resample
    draws len(years) years with replacement and sums their net; returns the
    share of resamples whose total > 0. A single-year book (or none) cannot
    be meaningfully bootstrapped by year and returns NaN, left to the caller
    to report as such rather than a fabricated 0%/100%."""
    years = list(year_net.keys())
    if len(years) < 2:
        return float("nan")
    nets = np.array([year_net[y] for y in years])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(nets), size=(n, len(nets)))
    totals = nets[draws].sum(axis=1)
    return float((totals > 0).mean())


@dataclass
class Criterion:
    n: int
    label: str
    passed: bool | None   # None = not evaluated (e.g. dependency not supplied)
    detail: str


def score(*, df_mid: pd.DataFrame, df_high: pd.DataFrame, year_net_mid: dict[int, float],
         net_c1: float | None, net_c2: float | None, c3_p95: float | None,
         neighbour_positive: int | None = None, neighbour_total: int | None = None,
         min_trades: int = 150) -> list[Criterion]:
    """sec 4's nine criteria, evaluated where the inputs allow (criterion 8
    needs the neighbour grid -- pass neighbour_positive/neighbour_total once
    that checkpoint exists; left as None/'NOT YET BUILT' until then, never
    silently scored as a pass)."""
    net_mid = float(df_mid["net"].sum()) if len(df_mid) else 0.0
    net_high = float(df_high["net"].sum()) if len(df_high) else 0.0
    first, second = split_halves(df_mid)
    top_year, top_share = top_year_share(year_net_mid)
    boot = bootstrap_by_year(year_net_mid)
    n_trades = len(df_mid)

    crit = []
    crit.append(Criterion(1, "Net > $0", net_mid > 0, f"${net_mid:,.2f}"))
    crit.append(Criterion(2, "Both halves net > $0", (first > 0) and (second > 0),
                          f"${first:,.2f} / ${second:,.2f}"))
    crit.append(Criterion(3, "No single calendar year > 50% of net",
                          (abs(top_share) <= 0.50) if year_net_mid else None,
                          f"{top_year}: {top_share:.1%}" if top_year is not None else "n/a"))
    crit.append(Criterion(4, "Bootstrap by year: total > 0 in >= 95%",
                          (boot >= 0.95) if not np.isnan(boot) else None,
                          f"{boot:.1%}" if not np.isnan(boot) else "NOT ENOUGH YEARS"))
    crit.append(Criterion(5, "Beats C1 and C2 on net",
                          (net_mid > net_c1 and net_mid > net_c2) if (net_c1 is not None and net_c2 is not None) else None,
                          f"v0 ${net_mid:,.2f} vs C1 ${net_c1:,.2f} vs C2 ${net_c2:,.2f}"
                          if (net_c1 is not None and net_c2 is not None) else "NOT SUPPLIED"))
    crit.append(Criterion(6, "Beats the p95 of C3 on net",
                          (net_mid > c3_p95) if c3_p95 is not None else None,
                          f"v0 ${net_mid:,.2f} vs C3 p95 ${c3_p95:,.2f}" if c3_p95 is not None else "NOT SUPPLIED"))
    crit.append(Criterion(7, "Still net > $0 at high friction", net_high > 0, f"${net_high:,.2f}"))
    if neighbour_positive is not None and neighbour_total is not None:
        crit.append(Criterion(8, "At least 12 of 18 neighbour cells net > $0",
                              neighbour_positive >= 12, f"{neighbour_positive}/{neighbour_total}"))
    else:
        crit.append(Criterion(8, "At least 12 of 18 neighbour cells net > $0", None, "NOT YET BUILT"))
    crit.append(Criterion(9, f"At least {min_trades} trades on the training side",
                          n_trades >= min_trades, f"{n_trades} trades"))
    return crit
