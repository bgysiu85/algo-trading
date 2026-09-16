#!/usr/bin/env python3
"""MCL-PB -- MCL's signal, but wait for the pullback and buy the break of the peak.

Registered in docs/research/REGISTERED_pullback_break.md BEFORE this file
existed. The rule there is the rule here; if they ever disagree, this file is
wrong.

Ben, 2026-09-16: all of MCL's entry conditions are met, the move does not
hold, and the trade reverses -- worst before 07:00 ET. So on MCL's signal do
NOT buy. Wait for price to peak and pull back, and buy when it passes that
peak again, provided MACD still says the window is open.

    signal   MCL's five-clause entry on completed bar s (flat, no setup pending,
             at or after the point-in-time floor)
    peak     high[s], raised by any later higher high
    arm      the first later bar with high < peak arms it, from the NEXT bar
    trigger  buy-stop at peak + 1c, fires when an armed bar's high reaches it
    fill     max(peak + 1c, open) + 1 tick
    still    macd > signal AND macd > 0 on the last COMPLETED bar (j-1)
    cancel   low < peak - 0.5 * (peak - pole_low)    (depth, at the close,
                                                      peak as of j-1;
             pole_low = min(low[s-4..s]), Cameron's 2-5 candle pole)
             macd < signal                           (at the close)
             09:30 -- never trigger on the final in-session bar

THE EXIT IS NOT RE-IMPLEMENTED. Each trigger is handed to MCL's own
`backtest_session` through `entry_bars` / `entry_px_by_bar`, one at a time,
so the trail, the gap-through fills, commission and the 09:30 flatten are the
published engine's. Running one trigger at a time is what makes the setup
position-aware: a setup can only open once the previous trade has exited, which
a single precomputed mask could not know.

NOTHING HERE LOOKS INSIDE A BAR IT HAS NOT FINISHED. The stop level is fixed
before the bar opens (the peak as of j-1), the MACD test reads j-1, and both
cancels are applied at j's close, after the resting stop has had its chance.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.mcl import mcl as MCL

STRATEGY_NAME = "MCL-PB"

DEPTH_FRACTION = 0.5      # registered: cancel below half the pole
POLE_BARS = 5             # registered (amendment 2): the pole starts at the lowest
                          # low of the signal bar and the 4 bars before it
STOP_OFFSET = 0.01        # registered: buy-stop at peak + 1c

TRIGGERED = "triggered"
CANCEL_DEPTH = "cancel_depth"
CANCEL_MACD = "cancel_macd"
WINDOW = "window"
BAND = "band_refused"     # triggered, but the engine refused the price band


@dataclass
class Setup:
    signal_i: int                  # row in the signals frame
    signal_close: float
    outcome: str = WINDOW
    end_i: int | None = None       # bar the setup ended on (trigger or cancel)
    peak: float = 0.0
    fill_px: float | None = None
    armed_at: int | None = None
    pole_low: float = 0.0
    trade: object = None           # MCL.Trade once the engine has taken it


@dataclass
class SessionResult:
    trades: list = field(default_factory=list)
    setups: list = field(default_factory=list)
    index: object = None           # the signals frame's timestamps, for row -> time


def session_positions(sig: pd.DataFrame, session_date, tz, not_before=None):
    """(in-session row indices, entry-allowed flags) -- MCL's own definitions."""
    local = sig.index.tz_convert(tz)
    in_sess = ((local.date == session_date)
               & (local.time >= MCL.SESSION_START)
               & (local.time < MCL.SESSION_END))
    idx = [i for i, f in enumerate(in_sess) if f]
    allowed = ([True] * len(sig) if not_before is None
               else [t >= not_before for t in local.time])
    return idx, allowed


def next_setup(sig: pd.DataFrame, idx: list[int], allowed: list[bool],
               k0: int) -> tuple[Setup | None, int]:
    """The first setup opening at in-session position >= k0, walked to its end.

    Returns (setup, k_end). `setup` is None when no signal remains. The caller
    resumes at k_end + 1 whatever the outcome.
    """
    o = sig["open"].to_numpy(float)
    h = sig["high"].to_numpy(float)
    lo = sig["low"].to_numpy(float)
    m = sig["macd"].to_numpy(float)
    ms = sig["macd_sig"].to_numpy(float)
    entry = sig["entry"].to_numpy(bool)
    cmacd = (m > ms) & (m > 0)

    n = len(idx)
    k = k0
    while k < n and not (entry[idx[k]] and allowed[idx[k]]):
        k += 1
    if k >= n:
        return None, n

    s = idx[k]
    st = Setup(signal_i=s, signal_close=float(sig["close"].iloc[s]), peak=h[s])
    base = float(lo[max(0, s - POLE_BARS + 1):s + 1].min())
    st.pole_low = base
    armed = False

    for kk in range(k + 1, n):
        j = idx[kk]
        last = kk == n - 1
        level = st.peak + STOP_OFFSET

        # 1. The resting stop. Only if armed before this bar, MACD open as of
        #    the last completed bar, and not the bar the window closes on.
        if armed and not last and h[j] >= level - 1e-9 and cmacd[j - 1]:
            st.outcome, st.end_i = TRIGGERED, j
            st.fill_px = round(max(level, o[j]) + MCL.SLIPPAGE_TICKS * MCL.TICK, 6)
            return st, kk

        # 2. The bar completes: the depth cancel against the peak as of the
        #    PREVIOUS bar -- the trail's own convention. Against a peak that
        #    includes this bar's high, a wide green bar making the new high
        #    would cancel itself on its own opening print.
        cancel_level = st.peak - DEPTH_FRACTION * (st.peak - base)

        if h[j] > st.peak:
            st.peak = h[j]
            armed = False          # a new high that did not fire is a new peak
        elif h[j] < st.peak and not armed:
            armed = True
            st.armed_at = j

        if lo[j] < cancel_level:
            st.outcome, st.end_i = CANCEL_DEPTH, j
            return st, kk
        if m[j] < ms[j]:
            st.outcome, st.end_i = CANCEL_MACD, j
            return st, kk

    st.outcome, st.end_i = WINDOW, idx[-1]
    return st, n - 1


def backtest_session_detail(df: pd.DataFrame, session_date, tz,
                            not_before=None, **engine_kw) -> SessionResult:
    """Every setup and every trade for one session.

    `engine_kw` goes to MCL.backtest_session unchanged (use_apex,
    require_macd_pos, entry_shares, ...), so the control and this variant can be
    run with identical settings. `entry_bars` / `entry_px_by_bar` are owned
    here and refused if passed.
    """
    for bad in ("entry_bars", "entry_px_by_bar", "entry_delay_bars"):
        if bad in engine_kw:
            raise TypeError(f"{bad} is set by MCL-PB itself")
    sig = MCL.signals(df, require_macd_pos=engine_kw.get("require_macd_pos"))
    idx, allowed = session_positions(sig, session_date, tz, not_before)
    out = SessionResult(index=sig.index)
    if not idx:
        return out

    k = 0
    while k < len(idx):
        st, k_end = next_setup(sig, idx, allowed, k)
        if st is None:
            break
        out.setups.append(st)
        k = k_end + 1
        if st.outcome != TRIGGERED:
            continue

        take = pd.Series(False, index=sig.index)
        take.iloc[st.end_i] = True
        px = pd.Series(np.nan, index=sig.index)
        px.iloc[st.end_i] = st.fill_px
        tr = MCL.backtest_session(df, session_date, tz, not_before=not_before,
                                  entry_bars=take, entry_px_by_bar=px,
                                  **engine_kw)
        if not tr:
            st.outcome = BAND
            continue
        if len(tr) != 1:
            raise AssertionError(f"one trigger produced {len(tr)} trades")
        t = tr[0]
        if pd.Timestamp(t.entry_time) != sig.index[st.end_i]:
            raise AssertionError("engine entered on a different bar from the trigger")
        st.trade = t
        out.trades.append(t)
        e = sig.index.get_loc(pd.Timestamp(t.exit_time))
        # Resume strictly after the exit bar: MCL itself cannot enter on it.
        while k < len(idx) and idx[k] <= e:
            k += 1
    return out


def backtest_session(df: pd.DataFrame, session_date, tz, **kw) -> list:
    """Same signature and return type as MCL.backtest_session."""
    return backtest_session_detail(df, session_date, tz, **kw).trades
