#!/usr/bin/env python3
"""EXIT-CMP: trades -> dollars and the sec 9 metrics. W15-0053 sub 2. Money comes from exitmgr.symbols (no constant here)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from exitmgr import symbols as SY
from strategy.chartmark import book as BK
from strategy.chartmark.data import Frame
from strategy.exit_cmp.entries import Entry
from strategy.exit_cmp.walk import Exit
from strategy.htf import book as HBK

COLS = ["entry_t", "exit_t", "year", "entry_j", "exit_j", "entry_px", "exit_px", "gross", "cost", "net", "exit_reason",
        "bars_held", "n_rolls", "mfe_px", "fired"]


def trade_frame(fr: Frame, entries: list[Entry], exits: list[Exit], roll_cum: np.ndarray, sym: str = "MCL",
                level: str = "mid", qty: int = 1) -> pd.DataFrame:
    s = SY.get(sym)
    ny = fr.ny
    e = np.array([x.e for x in entries])
    xj = np.array([x.exit_j for x in exits])
    ep = np.array([x.entry_px for x in entries])
    xp = np.array([x.exit_px for x in exits])
    rolls = roll_cum[xj] - roll_cum[e]
    gross = (xp - ep) * s.point_usd * qty
    cost = s.per_side(level) * (2 + 2 * rolls) * qty
    df = pd.DataFrame(dict(
        entry_t=ny[e].tz_localize(None), exit_t=ny[xj].tz_localize(None), year=np.asarray(ny.year)[e], entry_j=e, exit_j=xj,
        entry_px=ep, exit_px=xp, gross=gross, cost=cost, net=gross - cost, exit_reason=[x.reason for x in exits],
        bars_held=xj - e, n_rolls=rolls, mfe_px=[x.mfe_px - entry.entry_px for x, entry in zip(exits, entries)],
        fired=[x.fired for x in exits]))
    return df[COLS]


def worst_run_usd(net: np.ndarray) -> float:
    """Largest sum of consecutive losing trades (<= 0), in order of exit."""
    worst = cur = 0.0
    for v in net:
        cur = cur + v if v < 0 else 0.0
        worst = min(worst, cur)
    return float(worst)


def overlap_share(df: pd.DataFrame) -> float:
    """Share of trades opened while an earlier (by entry) one was still open."""
    d = df.sort_values("entry_j")
    run, k = -1, 0
    for ej, xj in zip(d["entry_j"], d["exit_j"]):
        k += int(ej <= run)
        run = max(run, xj)
    return k / len(d) if len(d) else 0.0


def metrics(df: pd.DataFrame, *, arm: float, point_usd: float, qty: int = 1) -> dict:
    """sec 9 headline columns for one (rule, scenario, level, size)."""
    if df.empty:
        return dict(n=0)
    net = df["net"].to_numpy()
    wins, losses = net[net > 0], net[net < 0]
    yn = HBK.year_table(df)
    h1, h2 = HBK.split_halves(df)
    mfe = np.maximum(df["mfe_px"].to_numpy(), 0.0)
    gave_back = (df["mfe_px"].to_numpy() >= arm - 1e-9) & (net <= 0)
    reached = df["mfe_px"].to_numpy() >= arm - 1e-9
    best_total = float((mfe * point_usd * qty).sum())
    sd = float(net.std(ddof=1)) if len(net) > 1 else float("nan")
    return dict(n=len(df), wins=int(len(wins)), losses=int(len(losses)), gross=float(df["gross"].sum()),
                cost=float(df["cost"].sum()), net=float(net.sum()),
                avg_win=float(wins.mean()) if len(wins) else None, avg_loss=float(losses.mean()) if len(losses) else None,
                largest_loss=float(net.min()), worst_run=worst_run_usd(net[np.argsort(df["exit_j"].to_numpy(), kind="stable")]),
                loss_streak=int(HBK.worst_loss_streak(net[np.argsort(df["exit_j"].to_numpy(), kind="stable")])),
                max_dd=BK.max_drawdown(df), half1=h1, half2=h2, year_net=yn,
                exits=dict(df["exit_reason"].value_counts()), median_bars=float(df["bars_held"].median()),
                give_back=int(gave_back.sum()), reached_arm=int(reached.sum()),
                give_back_share=float(gave_back.sum() / reached.sum()) if reached.sum() else None,
                capture=float(net.sum() / best_total) if best_total > 0 else None,
                net_per_sd=float(net.sum() / sd) if sd and sd == sd and sd > 0 else None,
                overlap=overlap_share(df), rolls=int((df["n_rolls"] > 0).sum()))


def sample_rows(df: pd.DataFrame, k: int = 20) -> list[dict]:
    """20 real trades, evenly spread through the book (entry / exit time and price, net)."""
    if df.empty:
        return []
    idx = np.unique(np.linspace(0, len(df) - 1, min(k, len(df))).round().astype(int))
    return [dict(entry_t=str(r.entry_t), exit_t=str(r.exit_t), entry_px=float(r.entry_px), exit_px=float(r.exit_px),
                 net=float(r.net), reason=r.exit_reason) for r in df.iloc[idx].itertuples()]
