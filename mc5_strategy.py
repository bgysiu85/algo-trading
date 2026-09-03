#!/usr/bin/env python3
"""
MC5 -- pre-market momentum on the 5-MINUTE timeframe. Pure logic, no broker.

Same session and same watchlist as MCL/V7, deliberately, so the two can be run
over identical data and compared.

RULES
  Session : 04:00-09:30 ET, flat at the close of the window
  Entry   : RSI rate of change >= +5% over the last 3 bars
            AND EMA9 > EMA21
            AND MACD line > MACD signal
  Exit    : RSI slope < 0 AND MACD slope < 0        (both, as specified)
            OR price falls 5% below the highest price since entry
            OR the window closes
  Size    : min(100 shares, 40% of equity / price)  -- same as V7

HOW "GRADIENT" IS DEFINED HERE, AND WHY IT IS NOT AN ANGLE
-----------------------------------------------------------
An angle on a chart is not a property of the data. It depends on the pixel
scale of the pane, so the same RSI move reads as 20 degrees or 60 degrees
depending on zoom. Nothing computable can be pinned to it.

So the entry gradient is a RATE OF CHANGE instead:

  1. fit a least-squares line through the last SLOPE_BARS values
  2. take the fitted line's start and end value across that window
  3. express the change as a percentage of the fitted start value

At SLOPE_BARS = 3 on 5-minute bars, that reads as "RSI rose at least 5% over
the last 15 minutes, measured on a smoothed line rather than on one noisy
bar-to-bar jump".

MACD IS DIFFERENT AND USES SIGN, NOT PERCENT
--------------------------------------------
MACD oscillates around zero and crosses it. A percentage rate of change is
undefined at zero and explodes either side of it -- a MACD moving from -0.001
to +0.001 is an infinite percentage rise and a meaningless signal. So the MACD
gradient is the SIGN of the fitted slope only, which is exactly what the stated
rule ("MACD has a negative gradient") needs.

The same reasoning applies to the RSI exit: EXIT_RSI_ROC_PCT is 0.0, i.e. any
negative gradient exits, as specified. Raise it to -5.0 if you want the exit to
demand the same magnitude the entry does.

EXIT MODELLING
--------------
As in mcl_strategy: the trail is derived from the peak as of the PREVIOUS bar
and tested against this bar's low. No same-bar lookahead.

WARM-UP MATTERS MORE HERE THAN ON 1-MINUTE
------------------------------------------
04:00-09:30 is only 66 five-minute bars. MACD alone needs ~35 of them to mean
anything, so a session started cold would be blind until roughly 07:00 ET --
more than half the session. Feed at least the prior day's extended hours in and
let the indicators warm up before the window opens. A '2 D' 1-minute request
resampled here covers it comfortably.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time as dtime

import pandas as pd

# --- parameters -----------------------------------------------------------
BAR_MINUTES = 5

EMA_FAST, EMA_SLOW = 9, 21
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_LEN = 14

SLOPE_BARS = 3                 # least-squares window for every gradient
ENTRY_RSI_ROC_PCT = 5.0        # entry: RSI must rise at least this much (%)
EXIT_RSI_ROC_PCT = 0.0         # exit: any negative gradient. -5.0 to demand more

# A percentage needs a denominator, and RSI can sit arbitrarily close to zero.
# Unfloored, RSI moving 2 -> 8 reads as +300% while the stock is still deeply
# oversold; on synthetic runs that produced readings above 7000%. Those bars are
# filtered out anyway by the EMA and MACD legs, but an unbounded input has no
# place in a threshold comparison. Floor the base at a level where "percent of
# RSI" still means something.
ROC_MIN_BASE = 5.0

TRAIL_PCT = 5.0
MAX_SHARES = 100
MAX_EQUITY_PCT = 40.0
EQUITY = 100_000.0

SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)

COMMISSION_PER_SHARE = 0.005
SLIPPAGE_TICKS = 1
TICK = 0.01

# Bars needed before the session for the indicators to be meaningful.
MIN_WARMUP_BARS = MACD_SLOW + MACD_SIGNAL


# --- indicators -----------------------------------------------------------

def ema(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(span=length, adjust=False).mean()


def rma(s: pd.Series, length: int) -> pd.Series:
    return s.ewm(alpha=1.0 / length, adjust=False).mean()


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = ema(close, MACD_FAST) - ema(close, MACD_SLOW)
    return line, ema(line, MACD_SIGNAL)


def rsi(close: pd.Series, length: int = RSI_LEN) -> pd.Series:
    delta = close.diff()
    up = rma(delta.clip(lower=0.0), length)
    down = rma((-delta).clip(lower=0.0), length)
    rs = up / down.replace(0.0, pd.NA)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(down != 0.0, 100.0)


def ols_slope(s: pd.Series, n: int = SLOPE_BARS) -> pd.Series:
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


def roc_pct(s: pd.Series, n: int = SLOPE_BARS) -> pd.Series:
    """Percent change across the fitted line over a trailing window.

    Uses the FITTED endpoints, so the numerator (the slope) is immune to a
    spike in an interior bar. The denominator is the fitted start, floored at
    ROC_MIN_BASE -- see that constant for why.

    Only valid for a strictly positive series. Never use it on MACD.
    """
    slope = ols_slope(s, n)
    mean = s.rolling(n).mean()
    span = slope * (n - 1)
    start = (mean - span / 2.0).clip(lower=ROC_MIN_BASE)
    return (span / start) * 100.0


# --- bar construction ------------------------------------------------------

def to_5m(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute bars to 5-minute, labelled at the interval START.

    Left-labelled and left-closed to match the convention IB, TradingView and
    Databento all use. Getting this wrong shifts every signal by one bar, which
    is the classic way a backtest quietly acquires lookahead.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("index must be a DatetimeIndex")
    if df.index.tz is None:
        raise ValueError("index must be timezone-aware")
    g = df.resample(f"{BAR_MINUTES}min", label="left", closed="left")
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum(),
    }).dropna(subset=["open", "close"])
    return out


def _looks_5m(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    deltas = pd.Series(df.index[1:]) - pd.Series(df.index[:-1])
    return deltas.median() >= pd.Timedelta(minutes=BAR_MINUTES)


# --- signals --------------------------------------------------------------

def signals(df5: pd.DataFrame) -> pd.DataFrame:
    """Add indicators and conditions. df5 must already be 5-minute bars."""
    out = df5.copy()
    c = out["close"]

    ml, ms = macd(c)
    r = rsi(c)
    e_fast, e_slow = ema(c, EMA_FAST), ema(c, EMA_SLOW)

    out["ema_fast"], out["ema_slow"] = e_fast, e_slow
    out["macd"], out["macd_sig"], out["rsi"] = ml, ms, r
    out["rsi_roc"] = roc_pct(r)
    out["rsi_slope"] = ols_slope(r)
    out["macd_slope"] = ols_slope(ml)

    # entry: all three, as specified
    out["c_rsi"] = out["rsi_roc"] >= ENTRY_RSI_ROC_PCT
    out["c_ema"] = e_fast > e_slow
    out["c_macd"] = ml > ms
    out["entry"] = out["c_rsi"] & out["c_ema"] & out["c_macd"]

    # exit: BOTH gradients negative
    out["x_rsi"] = out["rsi_roc"] <= EXIT_RSI_ROC_PCT
    out["x_macd"] = out["macd_slope"] < 0
    out["exit_sig"] = out["x_rsi"] & out["x_macd"]
    return out


# --- backtest -------------------------------------------------------------

@dataclass
class Trade:
    symbol: str
    date: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: int
    reason: str
    bars_held: int
    gross: float
    commission: float
    net: float


def size_for(price: float, equity: float = EQUITY) -> int:
    if price <= 0:
        return 0
    return max(0, min(MAX_SHARES,
                      math.floor(equity * MAX_EQUITY_PCT / 100.0 / price)))


def backtest_session(df, session_date, tz) -> list[Trade]:
    """Run one pre-market session on 5-minute bars.

    Accepts 1-minute OR 5-minute bars and resamples if needed, so this can be
    handed exactly the same frame mcl_strategy.backtest_session receives.
    Include pre-session history for warm-up (see the module docstring).
    """
    df5 = df if _looks_5m(df) else to_5m(df)
    sig = signals(df5)
    local = sig.index.tz_convert(tz)
    in_sess = ((local.date == session_date)
               & (local.time >= SESSION_START)
               & (local.time < SESSION_END))
    idx = [i for i, f in enumerate(in_sess) if f]
    if not idx:
        return []

    trades: list[Trade] = []
    pos = None
    rows = sig.reset_index()
    tcol = rows.columns[0]

    for k, i in enumerate(idx):
        row = rows.iloc[i]
        last_of_session = (k == len(idx) - 1)

        if pos is None:
            if bool(row["entry"]):
                px = float(row["close"]) + SLIPPAGE_TICKS * TICK
                q = size_for(px)
                if q >= 1:
                    pos = dict(entry_i=i, entry_px=px, qty=q,
                               peak=max(px, float(row["high"])),
                               entry_t=rows.iloc[i][tcol])
            continue

        trail = pos["peak"] * (1.0 - TRAIL_PCT / 100.0)
        exit_px = exit_reason = None

        if float(row["low"]) <= trail:
            exit_px, exit_reason = trail - SLIPPAGE_TICKS * TICK, "trailing_stop"
        elif last_of_session:
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "window_close"
        elif bool(row["exit_sig"]):
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "gradient_reversal"

        if exit_px is not None:
            q = pos["qty"]
            gross = (exit_px - pos["entry_px"]) * q
            comm = COMMISSION_PER_SHARE * q * 2
            trades.append(Trade(
                symbol="", date=str(session_date),
                entry_time=str(pos["entry_t"]), exit_time=str(rows.iloc[i][tcol]),
                entry_price=round(pos["entry_px"], 4), exit_price=round(exit_px, 4),
                qty=q, reason=exit_reason, bars_held=i - pos["entry_i"],
                gross=round(gross, 2), commission=round(comm, 2),
                net=round(gross - comm, 2)))
            pos = None
        else:
            pos["peak"] = max(pos["peak"], float(row["high"]))

    return trades


def slope_distribution(df, tz) -> dict:
    """Observed RSI rate-of-change inside the session -- calibration aid.

    ENTRY_RSI_ROC_PCT = 5.0 was chosen before seeing any of these numbers.
    Run this across the watchlist before trusting that threshold.
    """
    df5 = df if _looks_5m(df) else to_5m(df)
    sig = signals(df5)
    local = sig.index.tz_convert(tz)
    m = (local.time >= SESSION_START) & (local.time < SESSION_END)
    roc = sig.loc[m, "rsi_roc"].dropna()
    pos = roc[roc > 0]
    if pos.empty:
        return {}
    return {
        "bars": int(len(roc)),
        "rising_bars": int(len(pos)),
        "p50": round(float(pos.quantile(0.50)), 2),
        "p75": round(float(pos.quantile(0.75)), 2),
        "p90": round(float(pos.quantile(0.90)), 2),
        "max": round(float(pos.max()), 2),
        "at_or_above_threshold": int((roc >= ENTRY_RSI_ROC_PCT).sum()),
    }
