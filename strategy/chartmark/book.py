#!/usr/bin/env python3
"""Trades -> dollars (1 MCL headline, 1 CL reported), IBKR friction (Amendment A.3), and the sec 4 scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.chartmark import spec as S
from strategy.chartmark.data import Frame
from strategy.htf import book as HBK


def trade_frame(trades: list, fr: Frame, sym: str = "MCL", level: str = "mid", qty: int = 1) -> pd.DataFrame:
    ny = fr.ny
    rows = []
    for t in trades:
        sides = 2 + 2 * t.n_rolls
        gross = (t.exit_px - t.entry_px) * S.MULT[sym] * qty
        cost = S.per_side(sym, level) * sides * qty
        et, xt = ny[t.entry_j], ny[t.exit_j]
        rows.append(dict(entry_t=et.tz_localize(None), exit_t=xt.tz_localize(None), year=et.year,
                         entry_j=t.entry_j, exit_j=t.exit_j, entry_px=t.entry_px, exit_px=t.exit_px,
                         gross=gross, cost=cost, net=gross - cost, exit_reason=t.reason, phase=t.phase,
                         bars_held=t.exit_j - t.entry_j, n_rolls=t.n_rolls))
    return pd.DataFrame(rows, columns=["entry_t", "exit_t", "year", "entry_j", "exit_j", "entry_px", "exit_px",
                                       "gross", "cost", "net", "exit_reason", "phase", "bars_held", "n_rolls"])


def max_drawdown(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    eq = np.concatenate([[0.0], df.sort_values("exit_t")["net"].cumsum().to_numpy()])
    return float((np.maximum.accumulate(eq) - eq).max())


def daily_vol_ratio(df: pd.DataFrame, first, last) -> float:
    """Criterion 5 (I9): net / std of daily realised net P&L over calendar days first..last."""
    if df.empty:
        return float("nan")
    days = pd.date_range(pd.Timestamp(first).normalize(), pd.Timestamp(last).normalize(), freq="D")
    d = df.assign(day=df["exit_t"].dt.normalize()).groupby("day")["net"].sum().reindex(days).fillna(0.0)
    sd = float(d.std(ddof=1))
    return float(df["net"].sum() / sd) if sd > 0 else float("nan")


def drop_top(year_net: dict, k: int) -> float:
    ys = sorted(year_net, key=lambda y: year_net[y], reverse=True)
    return float(sum(v for y, v in year_net.items() if y not in ys[:k]))


def per_year_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("year")
    return pd.DataFrame({"trades": g.size(), "wins": g["net"].apply(lambda s: int((s > 0).sum())),
                         "losses": g["net"].apply(lambda s: int((s < 0).sum())),
                         "gross": g["gross"].sum(), "cost": g["cost"].sum(), "net": g["net"].sum()})


def evaluate(df_mid: pd.DataFrame, df_high: pd.DataFrame, *, c1_mid: pd.DataFrame, c3_p99: float,
             n_grid_pos: int | None, first, last) -> list[dict]:
    """The ten sec 4 criteria for the BASE. Returns rows {n, name, value, ok}. ok=None -> NOT READ / needs input."""
    out = []
    n = len(df_mid)
    yn = HBK.year_table(df_mid) if n else {}
    h1, h2 = HBK.split_halves(df_mid) if n else (0.0, 0.0)
    net = float(df_mid["net"].sum()) if n else 0.0
    boot = HBK.bootstrap_by_year(yn, n=2000, seed=0) if n else float("nan")
    _, share = HBK.top_year_share(yn)
    c1net = float(c1_mid["net"].sum()) if len(c1_mid) else 0.0
    r_base, r_c1 = daily_vol_ratio(df_mid, first, last), daily_vol_ratio(c1_mid, first, last)
    d1, d2 = (drop_top(yn, 1), drop_top(yn, 2)) if yn else (0.0, 0.0)
    out.append(dict(n=1, name="Net > $0 at mid", value=net, ok=net > 0))
    out.append(dict(n=2, name="Both halves net > $0", value=(h1, h2), ok=h1 > 0 and h2 > 0))
    out.append(dict(n=3, name="Drop-top-1 and drop-top-2 years > $0", value=(d1, d2), ok=d1 > 0 and d2 > 0))
    out.append(dict(n=4, name="Bootstrap by year, net>0 in >=95%", value=boot, ok=bool(boot >= 0.95)))
    out.append(dict(n=5, name="Beats C1 on net and on net per unit of volatility", value=(net, c1net, r_base, r_c1),
                    ok=bool(net > c1net and r_base > r_c1)))
    out.append(dict(n=6, name="Beats C3 p99 on net", value=(net, c3_p99), ok=None if np.isnan(c3_p99) else net > c3_p99))
    out.append(dict(n=7, name="No single year > 50% of net", value=share, ok=share <= 0.5 and net > 0))
    hn = float(df_high["net"].sum()) if len(df_high) else 0.0
    out.append(dict(n=8, name="Net > $0 at high friction", value=hn, ok=hn > 0))
    out.append(dict(n=9, name=">=18 of 27 cells net > $0", value=n_grid_pos,
                    ok=None if n_grid_pos is None else n_grid_pos >= 18))
    out.append(dict(n=10, name=">=150 trades", value=n, ok=n >= 150))
    return out


def verdict(rows: list[dict]) -> str:
    by = {r["n"]: r["ok"] for r in rows}
    if by[10] is False:
        return "NOT READ (fewer than 150 trades)"
    if by[5] is False or by[6] is False:
        return "FAIL (criterion 5 or 6 closes the study)"
    if any(v is None for v in by.values()):
        return "INCOMPLETE"
    return "PASS" if all(by.values()) else "FAIL"
