#!/usr/bin/env python3
"""
Shared indicators for the EMA Crossover strategy family (E15, VW9) -- pure
functions, no broker, no I/O. Sibling to strategy/mcl/mcl.py and
mc5_strategy.py; ema()/rma() are copied verbatim from those two files so the
three strategy families agree on what "EMA" and "RMA" mean bar for bar.

Adds two things MCL never needed: ATR (E15 and VW9 express every threshold in
ATR multiples, not dollars, per both specs' §2/§2.3) and session VWAP (VW9's
whole second indicator, per vw9_strategy_spec.md §2.2).

See claude/ema15_full_day_strategy_spec.md and claude/vw9_strategy_spec.md in
the Algo Trading project for the rules these implement.
"""

from __future__ import annotations

import pandas as pd

BAR_MINUTES_DEFAULT = 5


# --- ema / rma --------------------------------------------------------------
# Identical to strategy/mcl/mcl.py and strategy/mc5/mc5.py. Keep it
# that way -- if these three ever disagree on ema()/rma(), every cross-strategy
# comparison in this project (E15 vs VW9 vs V7 vs MC5) becomes meaningless.

def ema(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(span=length, adjust=False).mean()


def rma(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(alpha=1.0 / length, adjust=False).mean()


# --- ATR ----------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Pine's ta.tr: max(high-low, |high-prevclose|, |low-prevclose|).

    The first bar has no previous close, so its TR is just high-low -- the
    same convention Pine uses (ta.tr with the handle_na argument off falls
    back to high-low on bar 1).
    """
    prev_close = close.shift(1)
    a = (high - low).abs()
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    tr = pd.concat([a, b, c], axis=1).max(axis=1)
    tr.iloc[0] = a.iloc[0]
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """ta.rma-based ATR, matching Pine's ta.atr(length) exactly.

    Like mcl_strategy's rma()-based RSI, this is defined from bar 1 onward via
    the ewm recursion (Pine's rma has no hard warm-up gate either) -- but it is
    not a MEANINGFUL number until `length` bars have fed it. Callers must gate
    on bar count themselves, exactly as §2.3 of vw9_strategy_spec.md requires:
    "note ATR14 is itself undefined until bar 14 ... where an ATR-based
    threshold would gate an otherwise valid early signal, fall back to a
    percentage-of-price form and flag the row." That fallback is NOT
    implemented here -- it's an explicit open item in the spec, not a
    prerequisite for the §8.3 setup-count measurement, which only needs to
    know how many bars have elapsed (see setup_counts.py's `atr_ready` flag).
    """
    tr = true_range(high, low, close)
    return rma(tr, length)


# --- session VWAP ------------------------------------------------------

def session_vwap(high: pd.Series, low: pd.Series, close: pd.Series,
                  volume: pd.Series) -> pd.Series:
    """Cumulative volume-weighted typical price from the first bar of the
    series onward -- i.e. the caller must already have sliced to one session
    anchored at the bar it wants VWAP to start from.

    Per vw9_strategy_spec.md §2.2: anchor = 04:00 ET, carried unbroken through
    the session. This function doesn't know about clock time; it just anchors
    at index 0, so callers slice the frame to start at 04:00 ET before calling
    it. typical_price = (high+low+close)/3, per the spec's own formula.

    Not meaningful before a few bars and some cumulative dollar volume have
    accumulated -- see MIN_VWAP_BARS / MIN_VWAP_DOLLAR_VOL in setup_counts.py,
    which is the §2.2 "VWAP is not usable on bar 1" rule.
    """
    typical = (high + low + close) / 3.0
    cum_pv = (typical * volume).cumsum()
    cum_v = volume.cumsum()
    return cum_pv / cum_v.replace(0.0, pd.NA)


def cum_dollar_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Cumulative session dollar volume -- feeds MIN_VWAP_DOLLAR_VOL."""
    return (close * volume).cumsum()


# --- resampling ----------------------------------------------------------

def resample_bars(df: pd.DataFrame, bar_minutes: int) -> pd.DataFrame:
    """Resample 1-minute bars to `bar_minutes`, labelled at the interval
    START -- the same left/left convention as mc5_strategy.to_5m and
    db_bars.py, and required for the same reason: IB, TradingView and
    Databento all left-label, and getting this wrong shifts every signal by
    one bar.

    A bucket with zero source bars produces no output row (dropna on
    open/close) rather than a synthesised flat bar. This is the explicit rule
    in both E15 (§1: "Missing bars are skipped, not synthesised ... Advance
    the series only on bars that exist. This is the rule.") and VW9 inherits
    it unchanged. A thin name's 15-minute bar with zero prints must vanish
    from the series, not appear as O=H=L=C=prior_close/V=0, which would drag
    the EMA and VWAP toward silence and manufacture signals that never traded.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    if df.index.tz is None:
        raise ValueError("index must be timezone-aware")
    g = df.resample(f"{bar_minutes}min", label="left", closed="left")
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
    }).dropna(subset=["open", "close"])
    return out


# --- momentum oscillators --------------------------------------------------
#
# Merged here from strategy/mcl/mcl.py and strategy/mc5/mc5.py, which each
# carried their own copy (ema/rma existed in THREE places). The copies were
# verified structurally identical before the merge, and every caller's output
# was pinned numerically across the change.
#
# These take their periods as ARGUMENTS rather than reading module constants,
# which is the substantive change. The old copies closed over their own
# module's MACD_FAST/RSI_LEN/etc., so two strategies sharing one function
# would silently have shared one set of tuning parameters. MCL and MC5 happen
# to use identical values today (12/26/9, RSI 14) -- that coincidence is
# exactly what would have made the coupling invisible until someone retuned
# one strategy and moved the other.

def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9) -> tuple[pd.Series, pd.Series]:
    """Pine ta.macd -- returns (line, signal)."""
    line = ema(close, fast) - ema(close, slow)
    return line, ema(line, signal)


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Pine ta.rsi -- RMA of gains / RMA of losses. Returns float64.

    The zero-denominator guard is `.where(down != 0.0)`, not
    `.replace(0.0, pd.NA)`. Both put a missing value where there are no
    losses, and both produce identical numbers -- but pd.NA forces the
    Series to OBJECT dtype, and every subsequent operation inherits it. That
    silently produced an object-dtype RSI column in signals(), which works
    for pandas comparisons but raises on numpy ufuncs, so np.allclose() on
    the output fails with a type error rather than a sensible answer.
    np.nan keeps it float64 throughout.
    """
    delta = close.diff()
    up = rma(delta.clip(lower=0.0), length)
    down = rma((-delta).clip(lower=0.0), length)
    rs = up / down.where(down != 0.0)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(down != 0.0, 100.0)


def mfi(high, low, close, volume, length: int = 14) -> pd.Series:
    """Pine ta.mfi(hlc3, length)."""
    tp = (high + low + close) / 3.0
    raw = tp * volume
    diff = tp.diff()
    pos = raw.where(diff > 0, 0.0).rolling(length).sum()
    neg = raw.where(diff < 0, 0.0).rolling(length).sum()
    ratio = pos / neg.replace(0.0, pd.NA)
    return (100.0 - 100.0 / (1.0 + ratio)).fillna(50.0)


def rising(s: pd.Series, n: int = 3) -> pd.Series:
    return s > s.shift(n)


def falling(s: pd.Series, n: int = 3) -> pd.Series:
    return s < s.shift(n)


def past_apex(s: pd.Series, lookback: int = 20, n: int = 3) -> pd.Series:
    """Falling, and the rolling high is at least one bar behind.

    Mirrors Pine:  f_falling(src) and -ta.highestbars(src, lookback) >= 1
    """
    roll_max = s.rolling(lookback).max()
    return falling(s, n) & ~(s >= roll_max)


# --- gradients -------------------------------------------------------------

def ols_slope(s: pd.Series, n: int = 3) -> pd.Series:
    """Least-squares slope over a trailing window, in units per bar.

    Closed form rather than rolling.apply: with x = 0..n-1 the slope is
    sum((x_i - xbar) * y_i) / sum((x_i - xbar)^2), and the y_i are just shifts.
    For n = 3 this reduces to (y[t] - y[t-2]) / 2.
    """
    if n < 2:
        raise ValueError("slope needs at least 2 bars")
    xbar = (n - 1) / 2.0
    denom = sum((i - xbar) ** 2 for i in range(n))
    num = None
    for i in range(n):
        term = (i - xbar) * s.shift(n - 1 - i)
        num = term if num is None else num + term
    return num / denom


def roc_pct(s: pd.Series, n: int = 3, min_base: float = 5.0) -> pd.Series:
    """Percent change across the fitted line over a trailing window.

    Uses the FITTED endpoints, so the numerator (the slope) is immune to a
    spike in an interior bar. The denominator is the fitted start, floored at
    `min_base` -- an unfloored percentage of a near-zero base is unbounded.

    Only valid for a strictly positive series. Never use it on MACD.
    """
    slope = ols_slope(s, n)
    mean = s.rolling(n).mean()
    span = slope * (n - 1)
    start = (mean - span / 2.0).clip(lower=min_base)
    return (span / start) * 100.0
