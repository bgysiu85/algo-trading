#!/usr/bin/env python3
"""H60 scoring (§2.5) and the bar to clear (§7). W14-0003,
REGISTERED_h60_v0.md. Nothing in this module reads a bar: it prices trades
the engine already booked, against a basket the caller already built.

Two numbers per trade, both in dollars, at each friction level:
    net       gross - friction                              (§2.5 item 1)
    mr_net    net - notional x basket return, same window   (§2.5 item 2)

§7, per rule set, training side, L2:
    1  market-relative net per trade > 0
    2  net per trade > 0
    3  both halves (split at the median training SESSION) market-relative > 0
    4  drop-top-5 symbols still market-relative > 0
    5  calendar-month cluster bootstrap: total mr > 0 in >= 99.3% of 2,000
    6  beats the random-entry control's 95th percentile (mr per trade)
    7  no single year and no single symbol supplies > 50% of net
    8  still market-relative positive at L3
    9  >= 300 trades
    10 TL-60 only: beats DON-60 on market-relative net per trade
Every criterion is reported for every rule set, pass or fail. Nothing is
ranked.

THE TL-60 ENSEMBLE IS THREE THIRD-SIZE SLEEVES
----------------------------------------------
Its per-trade figures are stated per $10,000 of position -- total / (sleeve
trades / 3) -- so they compare with the six rule sets that trade $10,000,
and its trade count for criterion 9 is sleeve trades / 3.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

from strategy.h60 import costs as C
from strategy.h60.basket import Basket

BOOT_RESAMPLES = 2000
BOOT_BAR = 0.993          # 5% / 7 rule sets, §7 criterion 5
MIN_TRADES = 300
TOP_N_DROP = 5
MAX_SHARE = 0.50


def score(trades: pd.DataFrame, basket: Basket, grid: str) -> pd.DataFrame:
    t = trades.copy()
    if t.empty:
        for c in ("cost_L1", "cost_L2", "cost_L3", "net_L1", "net_L2", "net_L3",
                  "basket_ret", "mkt", "mr_gross", "mr_net_L1", "mr_net_L2",
                  "mr_net_L3", "financing", "net_L2_levered"):
            t[c] = pd.Series(dtype=float)
        return t
    k = C.trade_costs(t["qty"], t["entry_px"], t["exit_px"], t["entry_slot"],
                      t["exit_slot"], t["phase"], t["stop_fill"], grid)
    t["basket_ret"] = basket.ret(t["entry_mark"].to_numpy(), t["exit_mark"].to_numpy())
    t["mkt"] = t["notional"] * t["basket_ret"]
    t["mr_gross"] = t["gross"] - t["mkt"]
    for lv in ("L1", "L2", "L3"):
        t[f"cost_{lv}"] = k[lv]
        t[f"net_{lv}"] = t["gross"] - k[lv]
        t[f"mr_net_{lv}"] = t[f"net_{lv}"] - t["mkt"]
    t["financing"] = C.financing(t["notional"], t["nights"])
    t["net_L2_levered"] = t["net_L2"] - t["financing"]
    return t


def union_basket_return(t: pd.DataFrame, basket: Basket) -> float:
    """§4.2's total: what the equal-weight basket made over the UNION of the
    book's holding windows -- overlapping holds counted once, compounded."""
    if t.empty:
        return 0.0
    iv = sorted(zip(t["entry_mark"].astype(int), t["exit_mark"].astype(int)))
    merged = []
    for a, b in iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    lv = np.array([basket.ret(a, b) for a, b in merged], dtype=float)
    return float(np.prod(1.0 + lv) - 1.0)


def _month(d) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def bootstrap_share_positive(t: pd.DataFrame, col: str, name: str,
                             n: int = BOOT_RESAMPLES) -> float:
    """Share of calendar-month cluster resamples whose total is > 0. Seeded
    with crc32 of the book name (PROGRAM_INDEX §5: never hash())."""
    if t.empty:
        return 0.0
    months = t["entry_session"].map(_month)
    per = t.groupby(months)[col].sum().to_numpy()
    rng = np.random.default_rng(zlib.crc32(f"H60|boot|{name}".encode("utf-8")))
    draws = rng.integers(0, len(per), size=(n, len(per)))
    tot = per[draws].sum(axis=1)
    return float((tot > 0).mean())


def evaluate(t: pd.DataFrame, *, name: str, training_sessions, random_p95: float | None,
             sleeves: int = 1, don_mr_per_trade: float | None = None) -> dict:
    """§7 for one scored book. `t` is score() output. Returns
    {criterion: {"value": ..., "pass": bool}} plus "all_pass"."""
    n_equiv = len(t) / sleeves if sleeves else len(t)
    per = (lambda s: float(s.sum()) / n_equiv if n_equiv else float("nan"))
    out: dict = {}
    mr = per(t["mr_net_L2"]) if len(t) else float("nan")
    net = per(t["net_L2"]) if len(t) else float("nan")
    out["1_mr_net_per_trade_gt_0"] = {"value": mr, "pass": bool(len(t) and mr > 0)}
    out["2_net_per_trade_gt_0"] = {"value": net, "pass": bool(len(t) and net > 0)}

    ses = sorted(training_sessions)
    median = ses[len(ses) // 2] if ses else None
    if len(t) and median is not None:
        first = t[t["entry_session"] < median]["mr_net_L2"]
        second = t[t["entry_session"] >= median]["mr_net_L2"]
        h = (float(first.sum()) if len(first) else None,
             float(second.sum()) if len(second) else None)
    else:
        h = (None, None)
    out["3_both_halves_mr_gt_0"] = {
        "value": {"split_at": str(median), "first": h[0], "second": h[1]},
        "pass": bool(h[0] is not None and h[1] is not None and h[0] > 0 and h[1] > 0)}

    by_sym = t.groupby("symbol")["mr_net_L2"].sum().sort_values(ascending=False)
    top = list(by_sym.index[:TOP_N_DROP])
    rest = float(t[~t["symbol"].isin(top)]["mr_net_L2"].sum()) if len(t) else float("nan")
    out["4_drop_top5_symbols_mr_gt_0"] = {"value": {"dropped": top, "rest": rest},
                                          "pass": bool(len(t) and rest > 0)}

    share = bootstrap_share_positive(t, "mr_net_L2", name)
    out["5_month_bootstrap_ge_99.3pct"] = {"value": share, "pass": share >= BOOT_BAR}

    out["6_beats_random_p95"] = {
        "value": {"mr_per_trade": mr, "random_p95": random_p95},
        "pass": bool(random_p95 is not None and len(t) and mr > random_p95)}

    total = float(t["net_L2"].sum()) if len(t) else 0.0
    if total > 0:
        yrs = t.groupby(t["entry_session"].map(lambda d: d.year))["net_L2"].sum()
        syms = t.groupby("symbol")["net_L2"].sum()
        sy, ss = float(yrs.max() / total), float(syms.max() / total)
        out["7_no_year_or_symbol_gt_50pct"] = {
            "value": {"max_year_share": sy, "year": int(yrs.idxmax()),
                      "max_symbol_share": ss, "symbol": str(syms.idxmax())},
            "pass": sy <= MAX_SHARE and ss <= MAX_SHARE}
    else:
        out["7_no_year_or_symbol_gt_50pct"] = {"value": "net <= 0", "pass": False}

    l3 = float(t["mr_net_L3"].sum()) if len(t) else float("nan")
    out["8_mr_positive_at_L3"] = {"value": l3, "pass": bool(len(t) and l3 > 0)}
    out["9_at_least_300_trades"] = {"value": n_equiv, "pass": n_equiv >= MIN_TRADES}
    if don_mr_per_trade is not None:
        out["10_tl_beats_don"] = {"value": {"tl": mr, "don": don_mr_per_trade},
                                  "pass": bool(len(t) and mr > don_mr_per_trade)}
    out["all_pass"] = all(v["pass"] for k, v in out.items() if k[0].isdigit())
    return out
