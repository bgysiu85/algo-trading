#!/usr/bin/env python3
"""The live trader and the backtest must agree about MC5's apex exit.

They did not, from 2026-09-10 to 2026-09-17 -- the same split MCL had from
09-05 to 09-08, one module later. `backtest_session` gates `exit_sig` on
USE_APEX_EXIT (False since 09-11); `evaluate_last_bar` returned the ungated
value; trader.py turned it into `reason = "gradient_reversal"`. 25 such rows
in var/fills over 09-11..09-17; ten on 09-17 for (150.74). Every live MC5
session in that window ran a strategy the published figures do not describe.

The test that should have caught it (test_mc5_live_path, "agrees with
backtest_session on the same bar") compared the live value to the RAW
exit_sig, so it pinned the defect. Same shape as MCL's original wiring test.
These use a frame where the apex condition actually fires.
"""
from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from common import strategy_adapter as SA
from strategy.mc5 import mc5 as M

ET = ZoneInfo("America/New_York")


def frame5(closes, start="2026-09-08 05:00") -> pd.DataFrame:
    t0 = pd.Timestamp(start, tz=ET)
    idx = [t0 + timedelta(minutes=5 * i) for i in range(len(closes))]
    return pd.DataFrame(
        {"open": closes, "high": [c * 1.002 for c in closes],
         "low": [c * 0.998 for c in closes], "close": closes,
         "volume": [10_000] * len(closes)},
        index=pd.DatetimeIndex(idx).tz_convert("UTC"))


def a_frame_whose_last_bar_is_past_an_apex() -> pd.DataFrame:
    closes = [3.0 + i * 0.02 for i in range(90)] + \
             [4.8 - i * 0.03 for i in range(30)]
    return frame5(closes)


def now_after(df):
    return (df.index[-1] + timedelta(minutes=5, seconds=10)).tz_convert(ET).to_pydatetime()


def test_the_control_actually_produces_an_apex_signal():
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert bool(M.signals(df).iloc[-1]["exit_sig"]), \
        "the fixture no longer triggers the apex rule; this suite is vacuous"


def test_the_live_path_respects_use_apex_exit():
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert M.evaluate_last_bar(df, now_after(df), use_apex=False).exit_signal is False
    assert M.evaluate_last_bar(df, now_after(df), use_apex=True).exit_signal is True


def test_the_live_default_is_the_shipped_flag():
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert M.evaluate_last_bar(df, now_after(df)).exit_signal is M.USE_APEX_EXIT
    assert M.USE_APEX_EXIT is False, "the shipped flag is OFF; if that changes, change it on purpose"


def test_the_adapter_calls_it_with_no_override():
    df = a_frame_whose_last_bar_is_past_an_apex()
    through_adapter = SA.mc5_adapter().evaluate(df, now_after(df))
    assert through_adapter is not None
    assert through_adapter.exit_signal is M.USE_APEX_EXIT, (
        "the adapter is overriding the shipped apex flag")


def test_backtest_and_live_agree_bar_for_bar():
    df = a_frame_whose_last_bar_is_past_an_apex()
    sig = M.signals(df)
    for i in range(M.MIN_BARS_REQUIRED, len(df)):
        window = df.iloc[: i + 1]
        live = M.evaluate_last_bar(window, now_after(window))
        backtest_would_exit = bool(sig.iloc[i]["exit_sig"]) and M.USE_APEX_EXIT
        assert live.exit_signal == backtest_would_exit, (
            f"bar {i}: live says {live.exit_signal}, the backtest would act on "
            f"{backtest_would_exit}")
