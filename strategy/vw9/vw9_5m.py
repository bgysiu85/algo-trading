#!/usr/bin/env python3
"""
Adapter registering VW9 at the 5-minute timeframe (vw9_strategy_spec.md §7
cell A -- the headline "reaches into the pre-market edge" variant, see §0)
with common/backtest.py's Runner. All logic lives in strategy/vw9/backtest.py;
this module is only a thin binding: it supplies the SESSION_START/SESSION_END
and BACKTEST_* attributes the Runner reads, and a backtest_session(df,
session_date, tz) wrapper with the exact signature it calls.

    python main.py --mode backtest --strategy vw9_5m
    python main.py --mode backtest --strategy vw9_5m --exit-mode ride_ema9

BACKTEST_SESSIONS/BACKTEST_END_HOUR/BACKTEST_END_MINUTE tell the Runner to
slice ONE session ending 20:00 ET from the shared superset it already
fetches -- not MCL/MC5's two sessions ending 09:30 -- per §1's full session
(04:00-20:00) and §9.
"""

from __future__ import annotations

from datetime import time as dtime

from strategy.vw9.backtest import Trade, backtest_session_tf  # noqa: F401

SESSION_START = dtime(4, 0)
SESSION_END = dtime(20, 0)

BACKTEST_SESSIONS = 1
BACKTEST_END_HOUR = 20
BACKTEST_END_MINUTE = 0

TIMEFRAME_MINUTES = 5
DEFAULT_EXIT_MODE = "fixed_2r"


def backtest_session(df, session_date, tz, exit_mode: str = DEFAULT_EXIT_MODE):
    return backtest_session_tf(df, session_date, tz, TIMEFRAME_MINUTES,
                               exit_mode=exit_mode)
