#!/usr/bin/env python3
"""MCL-PB v3 -- a swing high, two red bars, and a break that CLOSES on volume.

Registered in docs/research/REGISTERED_pullback_break_v3.md BEFORE this
version ran. If this file and that document disagree, this file is wrong.

v1 waited for MCL's signal (NOTHING). v2 bought a stop a cent above the swing
high with MACD read on the bar before (NOTHING; Ben's review of its trades is
what produced v3). Now:

    swing high  a bar whose high exceeds the previous bar's high starts a
                candidate; higher highs raise it. The candidate is ARMED once
                two red bars (close < open, the peak bar counting if red) have
                printed since its peak bar
    level       once armed, the highest high printed since the arming bar --
                the bounce top, which is what Ben buys the break of -- and the
                peak itself until a bar has printed. Several armed setups can
                be live; the lowest level is the one that can fire
    break       a bar whose high reaches level + 1c. It QUALIFIES at its close
                if close > level, volume > SMA20 of the 20 bars before it, and
                macd > macd_sig on the bar itself. Then the entry is that
                close + 1 tick (MCL's own fill). A break that does not qualify
                just raises the level to the bar's high
    limit       a setup expires TIME_LIMIT_BARS after its peak bar

THE EXIT IS NOT RE-IMPLEMENTED. Each entry is handed to MCL's own
`backtest_session` through `entry_bars`, one at a time, so the trail, the 09:30
flatten and the optional `green_hold_bars` / `target_cents` exits are the
published engine's.

THE STATE IS WALKED THROUGH TRADES. Setups keep forming and being consumed
while a position is open; only the entry is gated on being flat.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from common.indicators import resample_bars
from strategy.mcl import mcl as MCL

STRATEGY_NAME = "MCL-PB"

STOP_OFFSET = 0.01        # registered: the break is level + 1c
MIN_RED_BARS = 2          # registered: Ben, "at least 2 red bars from the peak"
TIME_LIMIT_BARS = 60      # registered: mine, fixed before any run
VOL_MA_LEN = 20           # registered: Ben, "volume above volume MA 20"
ATR_LEN = 10              # registered v5: mean true range of the 10 bars before the break
ATR_MULT = 1.0            # registered v5: close must clear the level by one average bar
RSI_MIN = 64.0            # registered v5: the lowest RSI14 of Ben's eight good breaks

TRIGGERED = "triggered"
BAND = "band_refused"     # triggered, but the engine refused the price band
EXPIRED = "expired"       # live, never broken within the time limit
REFUSED_BUSY = "refused_busy"   # crossed while in a trade / before the floor
WINDOW = "window"         # still live at 09:30


@dataclass
class Setup:
    """One ARMED swing high. Candidates that never reach two red bars are not setups."""
    peak_i: int
    peak: float
    armed_at: int
    reds: int
    bounce: float | None = None    # highest high since the arming bar, once one has printed
    outcome: str = WINDOW
    end_i: int | None = None
    fill_px: float | None = None
    refused_close: int = 0         # breaks refused because the bar closed at/below the level
    refused_vol: int = 0           # ... because volume was not above its 20-bar average
    refused_macd: int = 0          # ... because MACD was not above its signal on the bar
    refused_decisive: int = 0      # ... because the close did not clear the level decisively (v5)
    trade: object = None
    pullback_low: float | None = None   # lowest low, peak bar through break bar

    @property
    def level(self) -> float:
        """The bounce top once a bar has printed after arming; the peak until then."""
        return self.peak if self.bounce is None else self.bounce


@dataclass
class SessionResult:
    trades: list = field(default_factory=list)
    setups: list = field(default_factory=list)
    index: object = None
    peaks: int = 0                 # every candidate swing high, armed or not
    breaks: int = 0                # bars that reached a live level
    refused: dict = field(default_factory=lambda: {"close": 0, "vol": 0, "macd": 0, "decisive": 0})


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
         take_trade, decisive: str | None = None) -> SessionResult:
    """The state machine. `take_trade(j)` enters at bar j's close through MCL's
    engine and returns its Trade, or None when the engine refused the price
    band; entries are suppressed until after that trade's exit bar."""
    o = sig["open"].to_numpy(float)
    h = sig["high"].to_numpy(float)
    c = sig["close"].to_numpy(float)
    v = sig["volume"].to_numpy(float)
    lo = sig["low"].to_numpy(float)
    m = sig["macd"].to_numpy(float)
    ms = sig["macd_sig"].to_numpy(float)
    red = c < o
    macd_open = m > ms
    # SMA of the 20 bars BEFORE each bar -- the break bar's own volume is the
    # thing being judged, so it is not in its own average.
    vma = pd.Series(v).rolling(VOL_MA_LEN).mean().shift(1).to_numpy()
    # v5 -- the decisive close. ATR of the bars BEFORE the break bar; RSI is
    # MCL's own column on the break bar itself (known at its close).
    if decisive not in (None, "atr", "rsi"):
        raise ValueError(f"decisive must be None, 'atr' or 'rsi', not {decisive!r}")
    if decisive == "atr":
        prev_c = pd.Series(c).shift(1)
        trng = np.maximum(h - lo, np.maximum((h - prev_c).abs(), (lo - prev_c).abs()))
        atr = pd.Series(trng).rolling(ATR_LEN).mean().shift(1).to_numpy()
    rsi = sig["rsi"].to_numpy(float) if decisive == "rsi" else None

    out = SessionResult(index=sig.index)
    n = len(idx)
    cand = None                # [high, peak_i, reds] of the forming swing high
    live: list[Setup] = []
    flat_after = -1            # enter only on bars strictly after this row

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

        # 2. The lowest live level, if this bar reached it, judged at the close.
        may_enter = (not last) and j > flat_after and allowed[j]
        hit = [st for st in live if h[j] >= st.level + STOP_OFFSET - 1e-9]
        if hit:
            out.breaks += 1
            # Live levels coincide in practice -- an older setup's bounce top IS
            # the newer setup's peak -- so the tie-break decides which setup the
            # trade is credited to: the most recently armed, whose top is the
            # bar a chart reader would point at.
            lowest = min(hit, key=lambda x: (x.level, -x.armed_at))
            if not may_enter:
                for st in hit:
                    end(st, WINDOW if last else REFUSED_BUSY, j)
            else:
                ok = True
                if not c[j] > lowest.level:
                    lowest.refused_close += 1; out.refused["close"] += 1; ok = False
                elif not (vma[j] == vma[j] and v[j] > vma[j]):
                    lowest.refused_vol += 1; out.refused["vol"] += 1; ok = False
                elif not macd_open[j]:
                    lowest.refused_macd += 1; out.refused["macd"] += 1; ok = False
                elif decisive == "atr" and not (atr[j] == atr[j]
                                                and c[j] - lowest.level >= ATR_MULT * atr[j] - 1e-9):
                    lowest.refused_decisive += 1; out.refused["decisive"] += 1; ok = False
                elif decisive == "rsi" and not (rsi[j] == rsi[j] and rsi[j] >= RSI_MIN):
                    lowest.refused_decisive += 1; out.refused["decisive"] += 1; ok = False
                if ok:
                    # v4: the pullback low, swing-high bar through the break
                    # bar inclusive. The engine only uses it when asked to.
                    plow = float(lo[lowest.peak_i:j + 1].min())
                    t = take_trade(j, plow)
                    if t is None:
                        for st in hit:
                            end(st, BAND, j)
                    else:
                        lowest.trade, lowest.fill_px = t, float(t.entry_price)
                        lowest.pullback_low = plow
                        out.trades.append(t)
                        # LAST row at the exit timestamp. The XNAS.BASIC slice for
                        # 2025-06-09 carries duplicate timestamps, and get_loc
                        # then returns a slice: eleven symbol-days raised on it
                        # and fell out of every book in the v2 and v3 runs.
                        flat_after = int(np.flatnonzero(
                            sig.index == pd.Timestamp(t.exit_time)).max())
                        end(lowest, TRIGGERED, j)
                        for st in [x for x in hit if x is not lowest]:
                            end(st, REFUSED_BUSY, j)
                # a refused break is not consumed: the level rises below

        # 3. The bar completes: levels rise, the forming swing high, arming.
        for st in live:
            st.bounce = h[j] if st.bounce is None else max(st.bounce, h[j])
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
                live.append(Setup(peak_i=cand[1], peak=cand[0], armed_at=j,
                                  reds=cand[2]))
            cand = None

        if last:
            for st in list(live):
                end(st, WINDOW, j)

    return out


def backtest_session_detail(df: pd.DataFrame, session_date, tz,
                            not_before=None, **engine_kw) -> SessionResult:
    """Every setup and every trade for one session.

    `engine_kw` goes to MCL.backtest_session unchanged (use_apex,
    require_macd_pos, entry_shares, green_hold_bars, ...). `entry_bars` /
    `entry_px_by_bar` / `entry_delay_bars` / `hard_stop` are owned here and
    refused. `structure_stop=True` (v4) sets the engine's hard stop one tick
    under each trade's own pullback low. `decisive="atr"` / `"rsi"` (v5) adds
    the decisive-close condition to the break bar. `bar_minutes=5` (v6) runs
    the whole thing on resampled 5-minute bars.
    """
    for bad in ("entry_bars", "entry_px_by_bar", "entry_delay_bars", "hard_stop"):
        if bad in engine_kw:
            raise TypeError(f"{bad} is set by MCL-PB itself")
    # v6: the same rule on coarser bars. Resampled once here, so the walk, the
    # indicators and MCL's engine all see the same 5-minute frame -- every
    # bar-denominated parameter (two reds, SMA20, green hold, expiry) then
    # counts 5-minute bars, as registered.
    bar_minutes = engine_kw.pop("bar_minutes", 1)
    if bar_minutes != 1:
        df = resample_bars(df, bar_minutes)
    sig = MCL.signals(df, require_macd_pos=engine_kw.get("require_macd_pos"))
    idx, allowed = session_positions(sig, session_date, tz, not_before)
    if not idx:
        return SessionResult(index=sig.index)

    structure_stop = engine_kw.pop("structure_stop", False)
    decisive = engine_kw.pop("decisive", None)

    def take_trade(j: int, pullback_low: float):
        take = pd.Series(False, index=sig.index)
        take.iloc[j] = True
        kw = dict(engine_kw)
        if structure_stop:
            # REGISTERED v4: one tick under the pullback low.
            kw["hard_stop"] = pullback_low - MCL.TICK
        tr = MCL.backtest_session(df, session_date, tz, not_before=not_before,
                                  entry_bars=take, **kw)
        if not tr:
            return None
        if len(tr) != 1:
            raise AssertionError(f"one entry produced {len(tr)} trades")
        t = tr[0]
        if pd.Timestamp(t.entry_time) != sig.index[j]:
            raise AssertionError("engine entered on a different bar from the break")
        return t

    return walk(sig, idx, allowed, take_trade, decisive=decisive)


def backtest_session(df: pd.DataFrame, session_date, tz, **kw) -> list:
    """Same signature and return type as MCL.backtest_session."""
    return backtest_session_detail(df, session_date, tz, **kw).trades
