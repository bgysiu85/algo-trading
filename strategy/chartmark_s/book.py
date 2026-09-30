#!/usr/bin/env python3
"""Trades -> dollars for a SHORT (gross = entry - exit), IBKR friction, and the sec 4 scoring (shared with the long side:
strategy.chartmark.book.evaluate / verdict / max_drawdown work on the trade frame)."""
from __future__ import annotations

import pandas as pd

from strategy.chartmark import book as LB
from strategy.chartmark_s import spec as S
from strategy.chartmark_s.data import Frame

evaluate, verdict, max_drawdown, drop_top, per_year_counts, daily_vol_ratio = (
    LB.evaluate, LB.verdict, LB.max_drawdown, LB.drop_top, LB.per_year_counts, LB.daily_vol_ratio)
COLS = ["entry_t", "exit_t", "year", "entry_j", "exit_j", "entry_px", "exit_px", "gross", "cost", "net", "exit_reason",
        "phase", "bars_held", "n_rolls"]


def trade_frame(trades: list, fr: Frame, sym: str = "MCL", level: str = "mid", qty: int = 1) -> pd.DataFrame:
    ny = fr.ny
    rows = []
    for t in trades:
        sides = 2 + 2 * t.n_rolls
        gross = (t.entry_px - t.exit_px) * S.MULT[sym] * qty
        cost = S.per_side(sym, level) * sides * qty
        et, xt = ny[t.entry_j], ny[t.exit_j]
        rows.append(dict(entry_t=et.tz_localize(None), exit_t=xt.tz_localize(None), year=et.year,
                         entry_j=t.entry_j, exit_j=t.exit_j, entry_px=t.entry_px, exit_px=t.exit_px,
                         gross=gross, cost=cost, net=gross - cost, exit_reason=t.reason, phase=t.phase,
                         bars_held=t.exit_j - t.entry_j, n_rolls=t.n_rolls))
    return pd.DataFrame(rows, columns=COLS)
