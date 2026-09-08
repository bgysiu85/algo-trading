#!/usr/bin/env python3
"""The live trader and the backtest must agree about the apex exit.

They did not, from 2026-09-05 to 2026-09-08.

`signals()` computes the raw apex condition. `backtest_session` gates it on
USE_APEX_EXIT, which went False on 09-05 after the exit was measured net -$544
over 213 exits. `evaluate_last_bar` returned the UNGATED value, and
brokers/ibkr/trader.py turned it straight into `reason = "apex_reversal"`.

So the backtest, the Pine script and every published figure were V11 (apex off)
while the live trader was still V7 (apex on) -- the variant measured at
+$3.86/trade against roughly $4.26 of round-trip friction, i.e. the one that
does not clear its own costs. A paper session run that way is not gathering
data on the strategy the project believes it is running.

claude/mcl_apex_macd_sweep.md said "the flag governs both -- no separate live
edit". Sharing signals() was necessary and not sufficient, because the flag is
read in backtest_session, which the live path never calls.

The existing wiring test in test_backtest_engine.py did not catch it: on its
synthetic frame exit_sig is False, so a gated and an ungated value are the same
value. These use a frame where the apex condition actually fires.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from strategy.mcl import mcl as S

ET = ZoneInfo("America/New_York")


def frame(closes, start="2026-09-08 05:00") -> pd.DataFrame:
    t0 = pd.Timestamp(start, tz=ET)
    idx = [t0 + timedelta(minutes=i) for i in range(len(closes))]
    return pd.DataFrame(
        {"open": closes, "high": [c * 1.002 for c in closes],
         "low": [c * 0.998 for c in closes], "close": closes,
         "volume": [10_000] * len(closes)},
        index=pd.DatetimeIndex(idx).tz_convert("UTC"))


def a_frame_whose_last_bar_is_past_an_apex() -> pd.DataFrame:
    """Rise then fall, so MACD/MFI/RSI are all off a recent high on the last
    bar -- which is exactly what the apex rule tests for."""
    closes = [3.0 + i * 0.02 for i in range(90)] + \
             [4.8 - i * 0.03 for i in range(30)]
    return frame(closes)


def test_the_control_actually_produces_an_apex_signal():
    """Without this the parity test below compares False to False and passes
    however the code is wired -- which is how the original wiring test missed
    a three-day live/backtest split."""
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert bool(S.signals(df).iloc[-1]["exit_sig"]), \
        "the fixture no longer triggers the apex rule; this suite is vacuous"


def test_the_live_path_respects_use_apex_exit():
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert S.evaluate_last_bar(df, use_apex=False).exit_signal is False
    assert S.evaluate_last_bar(df, use_apex=True).exit_signal is True


def test_the_live_default_is_the_shipped_flag():
    """Not merely overridable -- the DEFAULT has to be the shipped constant,
    because trader.py calls evaluate(df) with no arguments at all."""
    df = a_frame_whose_last_bar_is_past_an_apex()
    assert S.evaluate_last_bar(df).exit_signal is S.USE_APEX_EXIT


def test_the_trader_calls_it_with_no_override():
    """If trader.py ever passes use_apex itself, the constant stops governing
    the live path and this file stops meaning anything."""
    import inspect

    import brokers.ibkr.trader as T
    src = inspect.getsource(T)
    assert "evaluate(df)" in src, \
        "trader.py no longer calls evaluate(df) plainly -- re-check the gating"


def test_backtest_and_live_agree_bar_for_bar():
    """The property that matters, stated directly: on every bar of a real
    frame, what the live path would call an exit signal is what the backtest
    would act on."""
    df = a_frame_whose_last_bar_is_past_an_apex()
    sig = S.signals(df)
    for i in range(S.MIN_BARS_REQUIRED, len(df)):
        window = df.iloc[: i + 1]
        live = S.evaluate_last_bar(window)
        backtest_would_exit = (bool(sig.iloc[i]["exit_sig"])
                               and S.USE_APEX_EXIT)
        assert live.exit_signal == backtest_would_exit, (
            f"bar {i}: live says {live.exit_signal}, the backtest would act on "
            f"{backtest_would_exit}")
