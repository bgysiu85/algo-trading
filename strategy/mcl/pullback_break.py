#!/usr/bin/env python3
"""MCL-PB v2 -- a swing high, two red bars, buy the break of the high.

Registered in docs/research/REGISTERED_pullback_break_v2.md BEFORE this
version ran. If this file and that document disagree, this file is wrong.

v1 (REGISTERED_pullback_break.md, verdict NOTHING) waited for MCL's five-clause
signal and THEN looked for a pullback. Ben's own examples all have the pullback
BEFORE the signal, so v2 drops the signal from the entry entirely:

    swing high  a bar whose high exceeds the previous bar's high starts a
                candidate; higher highs raise it. The candidate becomes a LIVE
                LEVEL once two red bars (close < open, the peak bar counting if
                red) have printed since its peak bar
    levels      several can be live at once -- the 6.20 top inside a pullback
                from a 6.79 top are both levels, and each is bought on its own
                break (AEHL 2026-09-03 07:33 and 07:58). The lowest live level
                is the resting buy-stop
    trigger     buy-stop at level + 1c, fires on the first bar whose high
                reaches it while flat, if macd > macd_sig on the LAST COMPLETED
                bar. A break that cannot fire (MACD closed, in a trade, before
                first_seen, final bar) just removes the level
    fill        max(level + 1c, open) + 1 tick
    limit       a level expires TIME_LIMIT_BARS after its peak bar

THE EXIT IS NOT RE-IMPLEMENTED. Each trigger is handed to MCL's own
`backtest_session` through `entry_bars` / `entry_px_by_bar`, one at a time, so
the trail, gap-through fills, commission, the 09:30 flatten and the optional
`target_cents` limit are the published engine's.

THE STATE IS WALKED THROUGH TRADES. Levels keep forming and being consumed
while a position is open; only the trigger is gated on being flat. A high made
inside a trade is a level the next setup can buy the break of.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy.mcl import mcl as MCL

STRATEGY_NAME = "MCL-PB"

STOP_OFFSET = 0.01        # registered: buy-stop at peak + 1c
MIN_RED_BARS = 2          # registered: Ben, "at least 2 red bars from the peak"
TIME_LIMIT_BARS = 60      # registered: mine, fixed before any run

TRIGGERED = "triggered"
BAND = "band_refused"     # triggered, but the engine refused the price band
EXPIRED = "expired"       # live, never broken within the time limit
REFUSED_MACD = "refused_macd"   # broken while MACD was closed
REFUSED_BUSY = "refused_busy"   # broken while in a trade / before the floor
WINDOW = "window"         # still live at 09:30


@dataclass
class Setup:
    """One LIVE LEVEL. Candidates that never reach two red bars are not setups."""
    peak_i: int
    peak: float
    armed_at: int
    reds: int
    outcome: str = WINDOW
    end_i: int | None = None
    fill_px: float | None = None
    trade: object = None


@dataclass
class SessionResult:
    trades: list = field(default_factory=list)
    setups: list = field(default_factory=list)
    index: object = None
    peaks: int = 0                 # every candidate swing high, armed or not


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


def walk(sig: pd.DataFrame, idx: list[int], allowed: list[bool],
         take_trade) -> SessionResult:
    """The state machine. `take_trade(j, fill_px)` returns MCL's Trade or None
    (band refused); triggers are suppressed until after that trade's exit bar."""
    o = sig["open"].to_numpy(float)
    h = sig["high"].to_numpy(float)
    c = sig["close"].to_numpy(float)
    m = sig["macd"].to_numpy(float)
    ms = sig["macd_sig"].to_numpy(float)
    red = c < o
    macd_open = m > ms

    out = SessionResult(index=sig.index)
    n = len(idx)
    cand = None                # (high, peak_i, reds) of the forming swing high
    live: list[Setup] = []     # ascending by peak
    flat_after = -1            # trigger only on bars strictly after this row

    def end(st: Setup, outcome: str, j: int):
        st.outcome, st.end_i = outcome, j
        live.remove(st)
        out.setups.append(st)

    for kk in range(n):
        j = idx[kk]
        last = kk == n - 1
        prev_high = h[idx[kk - 1]] if kk else None

        # 1. Expiry, measured from the peak bar and known at the open.
        for st in list(live):
            if j - st.peak_i > TIME_LIMIT_BARS:
                end(st, EXPIRED, j)

        # 2. Resting stops, lowest first, decided before this bar's own close.
        #    Every live level was armed on an earlier bar: levels are created
        #    in step 3, after this block has run for their bar.
        may_fire = (not last) and j > flat_after and allowed[j] and macd_open[j - 1]
        for st in sorted(live, key=lambda x: x.peak):
            if h[j] < st.peak + STOP_OFFSET - 1e-9:
                continue
            if may_fire:
                fill = round(max(st.peak + STOP_OFFSET, o[j])
                             + MCL.SLIPPAGE_TICKS * MCL.TICK, 6)
                st.fill_px = fill
                t = take_trade(j, fill)
                if t is None:
                    end(st, BAND, j)
                else:
                    st.trade = t
                    out.trades.append(t)
                    flat_after = sig.index.get_loc(pd.Timestamp(t.exit_time))
                    end(st, TRIGGERED, j)
                    may_fire = False       # the same bar cannot buy twice
            elif last:
                end(st, WINDOW, j)
            elif not macd_open[j - 1] and j > flat_after and allowed[j]:
                end(st, REFUSED_MACD, j)
            else:
                end(st, REFUSED_BUSY, j)

        # 3. The bar completes: the forming swing high and its red count.
        if cand is None:
            if prev_high is not None and h[j] > prev_high:
                cand = [h[j], j, 1 if red[j] else 0]
                out.peaks += 1
        elif h[j] > cand[0]:
            cand = [h[j], j, 1 if red[j] else 0]
        elif red[j]:
            cand[2] += 1
        if cand is not None and cand[2] >= MIN_RED_BARS:
            if not last:
                live.append(Setup(peak_i=cand[1], peak=cand[0], armed_at=j, reds=cand[2]))
            cand = None

        if last:
            for st in list(live):
                end(st, WINDOW, j)

    return out


def backtest_session_detail(df: pd.DataFrame, session_date, tz,
                            not_before=None, **engine_kw) -> SessionResult:
    """Every setup and every trade for one session.

    `engine_kw` goes to MCL.backtest_session unchanged (use_apex,
    require_macd_pos, entry_shares, target_cents, ...). `entry_bars` /
    `entry_px_by_bar` / `entry_delay_bars` are owned here and refused.
    """
    for bad in ("entry_bars", "entry_px_by_bar", "entry_delay_bars"):
        if bad in engine_kw:
            raise TypeError(f"{bad} is set by MCL-PB itself")
    sig = MCL.signals(df, require_macd_pos=engine_kw.get("require_macd_pos"))
    idx, allowed = session_positions(sig, session_date, tz, not_before)
    if not idx:
        return SessionResult(index=sig.index)

    def take_trade(j: int, fill: float):
        take = pd.Series(False, index=sig.index)
        take.iloc[j] = True
        px = pd.Series(np.nan, index=sig.index)
        px.iloc[j] = fill
        tr = MCL.backtest_session(df, session_date, tz, not_before=not_before,
                                  entry_bars=take, entry_px_by_bar=px,
                                  **engine_kw)
        if not tr:
            return None
        if len(tr) != 1:
            raise AssertionError(f"one trigger produced {len(tr)} trades")
        t = tr[0]
        if pd.Timestamp(t.entry_time) != sig.index[j]:
            raise AssertionError("engine entered on a different bar from the trigger")
        return t

    return walk(sig, idx, allowed, take_trade)


def backtest_session(df: pd.DataFrame, session_date, tz, **kw) -> list:
    """Same signature and return type as MCL.backtest_session."""
    return backtest_session_detail(df, session_date, tz, **kw).trades
