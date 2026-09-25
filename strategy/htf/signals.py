#!/usr/bin/env python3
"""HTF-Ben signals: MACD/EMA entry confirmation, the daily trend filter, and
2-bar swing pivots. W15-0004 step 3, REGISTERED_htf_ben_v0.md sec 2.2 (E1-E3,
E7) and the swing-low/high definition in sec 2.3 (S1), tested against sec 8's
G4 guards: each of these is proven not to use a bar before it closes, by a
test that a one-bar shift breaks it.

NO P&L, NO POSITION MANAGEMENT HERE. This module produces per-bar signals
(MACD cross, EMA/MACD confirmation, the daily direction as read from each
entry-chart bar, and confirmed swing pivot levels) from an entry-chart frame
(strategy.htf.bars.resample output, back-adjusted) and a daily frame
(strategy.htf.bars.daily output, back-adjusted). Turning these into actual
entries -- the one-position-at-a-time state machine, and the
lapsed/blocked-by-daily-filter/ignored/voided counts -- is G2's and the
runner's job (REGISTERED sec 5.2, sec 2.2 E5, sec 2.3 S1).

WHY EMAs/MACD ARE SMA-SEEDED, NOT PANDAS' DEFAULT EWM
------------------------------------------------------
REGISTERED sec 2.2 E7: "standard exponential (alpha = 2/(n+1)), seeded on the
first n bars' simple average, and need 200 four-hour bars / 60 daily bars of
warm-up before any signal." pandas' `.ewm(adjust=False)` seeds from the FIRST
OBSERVATION (implicit weight 1 on bar 0), not an n-bar SMA -- close for a long
series, but not what was registered, and this file exists specifically to
match the registered rule bar-for-bar. common/indicators.py's ema() is kept
for the other strategy families (E15/VW9/MC5); it is not reused here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.htf import bars as B

MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
EMA_FAST, EMA_SLOW = 9, 21
DAILY_EMA_FAST, DAILY_EMA_SLOW = 9, 21
SWING_L, SWING_R = 2, 2
WARMUP_ENTRY_BARS = 200
WARMUP_DAILY_BARS = 60


# --- EMA / MACD, SMA-seeded (E7) --------------------------------------------

def ema_seeded(s: pd.Series, n: int) -> pd.Series:
    """Standard EMA (alpha=2/(n+1)), seeded on the first n bars' simple
    average (E7) -- NOT pandas' ewm(adjust=False), which seeds from bar 0.
    NaN before the seed is available. Leading NaNs in `s` are skipped past
    (the seed is the first n CONSECUTIVE non-NaN values); this only matters
    for the daily frame, which is dense from its first row.
    """
    values = s.to_numpy(dtype=float)
    n_total = len(values)
    out = np.full(n_total, np.nan)
    valid = np.where(~np.isnan(values))[0]
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    start = int(valid[0])
    if np.isnan(values[start:start + n]).any():
        # a gap inside the seed window -- push start to the first run of n
        # consecutive non-NaN values
        run = 0
        start = None
        for i in range(len(values)):
            if not np.isnan(values[i]):
                run += 1
                if run == n:
                    start = i - n + 1
                    break
            else:
                run = 0
        if start is None:
            return pd.Series(out, index=s.index)
    alpha = 2.0 / (n + 1)
    seed = float(values[start:start + n].mean())
    out[start + n - 1] = seed
    prev = seed
    for i in range(start + n, n_total):
        x = values[i]
        if np.isnan(x):
            prev = np.nan
            out[i] = np.nan
            continue
        if np.isnan(prev):
            prev = x  # re-seed point after a gap: carry the raw value, not a
            out[i] = np.nan  # a false EMA -- still not "ready" this bar
            continue
        prev = alpha * x + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=s.index)


def macd_seeded(close: pd.Series, fast: int = MACD_FAST, slow: int = MACD_SLOW,
                signal: int = MACD_SIGNAL) -> tuple[pd.Series, pd.Series]:
    """(macd_line, signal_line), both SMA-seeded per E7. The signal line is
    seeded on the first `signal` bars of the macd LINE once it exists, not
    on the first `signal` bars of price."""
    fast_e = ema_seeded(close, fast)
    slow_e = ema_seeded(close, slow)
    line = fast_e - slow_e
    sig = ema_seeded(line, signal)
    return line, sig


# --- MACD cross (E1) ---------------------------------------------------

def macd_cross_up(line: pd.Series, signal: pd.Series) -> pd.Series:
    """True at bar t iff MACD[t-1] <= signal[t-1] and MACD[t] > signal[t]
    (E1) -- uses only t and t-1, both closed by t's own close."""
    prev_below = line.shift(1) <= signal.shift(1)
    now_above = line > signal
    return (prev_below & now_above).fillna(False)


def macd_cross_down(line: pd.Series, signal: pd.Series) -> pd.Series:
    prev_above = line.shift(1) >= signal.shift(1)
    now_below = line < signal
    return (prev_above & now_below).fillna(False)


# --- EMA9/21 confirmation (E2) ------------------------------------------

def confirms_from_emas(ema9: pd.Series, ema21: pd.Series, macd_line: pd.Series,
                       signal_line: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(confirms_long, confirms_short) at each bar c, from c and c-1 only
    (E2): EMA9 rising (falling for short) AND the EMA9/EMA21 gap closing
    AND the MACD cross not yet reversed. Split out from confirmation_flags
    so it can be exercised directly on hand-built EMA series, independent
    of ema_seeded's own warm-up length."""
    gap = (ema9 - ema21).abs()
    gap_prev = gap.shift(1)
    gap_closing = gap < gap_prev
    ema9_rising = ema9 > ema9.shift(1)
    ema9_falling = ema9 < ema9.shift(1)
    macd_still_above = macd_line > signal_line
    macd_still_below = macd_line < signal_line
    confirms_long = (ema9_rising & gap_closing & macd_still_above).fillna(False)
    confirms_short = (ema9_falling & gap_closing & macd_still_below).fillna(False)
    return confirms_long, confirms_short


def confirmation_flags(close: pd.Series, macd_line: pd.Series, signal_line: pd.Series,
                       ema_fast: int = EMA_FAST, ema_slow: int = EMA_SLOW,
                       ) -> tuple[pd.Series, pd.Series]:
    """(confirms_long, confirms_short) computed from price -- SMA-seeded
    EMA9/EMA21 (E7) fed into confirms_from_emas. `ema_fast`/`ema_slow`
    default to the registered 9/21 (EMA_FAST/EMA_SLOW); overridable only
    for tests that need a shorter warm-up on a short synthetic series."""
    ema9 = ema_seeded(close, ema_fast)
    ema21 = ema_seeded(close, ema_slow)
    return confirms_from_emas(ema9, ema21, macd_line, signal_line)


def confirmation_bar(confirms: pd.Series, trigger_pos: int) -> int | None:
    """The first of {t+1, t+2} (positional index) where `confirms` is True,
    else None (E2: "If neither bar confirms, the trigger lapses"). Reads
    ONLY positions trigger_pos+1 and trigger_pos+2 -- a trigger at t can
    never be confirmed by t itself or by t+3 onward."""
    for c in (trigger_pos + 1, trigger_pos + 2):
        if c >= len(confirms):
            continue
        if bool(confirms.iloc[c]):
            return c
    return None


# --- daily filter (E3) --------------------------------------------------

def daily_direction(daily_adj: pd.DataFrame) -> pd.Series:
    """'long' / 'short' / 'none' per daily bar, from the back-adjusted daily
    close vs daily EMA9/EMA21 (both SMA-seeded, E7), gated on the 60-daily-
    bar warm-up. Indexed the same as daily_adj (positional order = session
    order)."""
    close = daily_adj["close_adj"]
    ema9 = ema_seeded(close, DAILY_EMA_FAST)
    ema21 = ema_seeded(close, DAILY_EMA_SLOW)
    long_ok = (close > ema9) & (close > ema21)
    short_ok = (close < ema9) & (close < ema21)
    warm = np.arange(len(daily_adj)) >= WARMUP_DAILY_BARS
    direction = np.where(long_ok.to_numpy() & warm, "long",
                 np.where(short_ok.to_numpy() & warm, "short", "none"))
    return pd.Series(direction, index=daily_adj.index)


def session_last_bar_mask(entry_df: pd.DataFrame, bar_hours: int) -> np.ndarray:
    """True for the one bar in each session whose close IS that session's
    own 17:00 close -- i.e. the only bar of the session at which that
    session's own daily bar (bars.daily) is actually complete. Matches
    bars.resample's bucketing: last bucket index = 22 // bar_hours."""
    last_bucket = 22 // bar_hours
    return (entry_df["bar"].to_numpy() == last_bucket)


def daily_filter_as_of(entry_df: pd.DataFrame, daily_adj: pd.DataFrame,
                       bar_hours: int) -> pd.Series:
    """The daily direction (E3) as legally knowable at each entry-chart
    bar's close: the LAST bar of session S may use S's own (now-complete)
    daily bar; every earlier bar of session S must use the PRIOR session's
    daily bar, because S's own is still forming. G4: mutating S's daily
    close must not change the decision at any bar of S except that last
    one -- see test_signals.py::TestDailyFilterNoLookahead.
    """
    direction = daily_direction(daily_adj)
    session_order = list(daily_adj["date"])
    dir_by_session = dict(zip(session_order, direction))
    prev_by_session = {d: (session_order[i - 1] if i > 0 else None)
                       for i, d in enumerate(session_order)}
    last_mask = session_last_bar_mask(entry_df, bar_hours)
    sessions = entry_df["session"].to_numpy()
    out = np.empty(len(entry_df), dtype=object)
    for i, (sess, is_last) in enumerate(zip(sessions, last_mask)):
        use_sess = sess if is_last else prev_by_session.get(sess)
        out[i] = dir_by_session.get(use_sess, "none") if use_sess is not None else "none"
    return pd.Series(out, index=entry_df.index)


# --- swing pivots (S1) ---------------------------------------------------

def _swing(series: pd.Series, want: str, L: int = SWING_L, R: int = SWING_R) -> pd.Series:
    """Shared implementation for swing_lows/swing_highs. `want` is 'min' or
    'max'. Returns a series that is NaN everywhere except position p+R for
    each confirmed pivot at position p, where it holds the pivot's level
    (S1: "known only on the close of the 2nd bar after it")."""
    values = series.to_numpy(dtype=float)
    n = len(values)
    out = np.full(n, np.nan)
    for p in range(L, n - R):
        window = values[p - L:p + R + 1]
        if np.isnan(window).any():
            continue
        piv = window.min() if want == "min" else window.max()
        if values[p] == piv:
            out[p + R] = values[p]
    return pd.Series(out, index=series.index)


def swing_lows(low: pd.Series, L: int = SWING_L, R: int = SWING_R) -> pd.Series:
    """Confirmed swing-low LEVEL, placed at the bar (p+R) it becomes known
    on -- not at the pivot bar p itself (S1, L=R=2: "a bar whose low is the
    lowest of the 2 bars on each side ... becomes known only on the close
    of the 2nd bar after it"). NaN elsewhere. Callers wanting "the most
    recent confirmed swing low as of bar i" forward-fill this series
    themselves (e.g. for S1's stop placement in the runner, step 7)."""
    return _swing(low, "min", L, R)


def swing_highs(high: pd.Series, L: int = SWING_L, R: int = SWING_R) -> pd.Series:
    """Mirror of swing_lows for swing highs (used for short-side stops)."""
    return _swing(high, "max", L, R)


# --- warm-up gate (E7) ----------------------------------------------------

def entry_ready_mask(entry_df: pd.DataFrame,
                     warmup_bars: int = WARMUP_ENTRY_BARS) -> np.ndarray:
    """True from the (warmup_bars)'th entry-chart bar onward (positional,
    0-indexed) -- E7's "200 four-hour bars ... of warm-up before any
    signal", applied per entry chart (Amendment 0: "'4-hour bar' below
    means 'the scenario's entry-chart bar'")."""
    n = len(entry_df)
    mask = np.zeros(n, dtype=bool)
    if n > warmup_bars:
        mask[warmup_bars:] = True
    return mask
