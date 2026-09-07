#!/usr/bin/env python3
"""
Adapter registering VW9 at the 15-minute timeframe (vw9_strategy_spec.md §7
cell B) with common/backtest.py's Runner. Sibling to vw9_5m.py -- see that
module's docstring for what this binding does and does not do; only
TIMEFRAME_MINUTES differs.

    python main.py --mode backtest --strategy vw9_15m
    python main.py --mode backtest --strategy vw9_15m --exit-mode trail_atr
"""

from __future__ import annotations

from datetime import time as dtime

from strategy.vw9.backtest import Trade, backtest_session_tf  # noqa: F401

SESSION_START = dtime(4, 0)
SESSION_END = dtime(20, 0)

BACKTEST_SESSIONS = 1
BACKTEST_END_HOUR = 20
BACKTEST_END_MINUTE = 0

TIMEFRAME_MINUTES = 15
DEFAULT_EXIT_MODE = "fixed_2r"


def backtest_session(df, session_date, tz, exit_mode: str = DEFAULT_EXIT_MODE,
                     entry_shares: int | None = None):
    return backtest_session_tf(df, session_date, tz, TIMEFRAME_MINUTES,
                               exit_mode=exit_mode, entry_shares=entry_shares)
