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
# Shown on alerts so a fill on a phone says which strategy fired it.
# Lives on the STRATEGY rather than in the trader, so a second trader
# cannot end up labelling its fills with the first one's name.
STRATEGY_NAME = "MC5"

# Price band, the SAME rule MCL and VW9 enforce. MC5 shipped without it and
# had never been run on real data, so nothing had exposed the gap -- exactly
# how VW9 reached a full grid before anyone noticed.
#
# It is not cosmetic. IB serves SPLIT-ADJUSTED history, so a small cap that
# later reverse-split comes back at an inflated price. Applied to VW9 the same
# fix moved its headline from -$31,296 to +$3,942: the loss was entirely the
# adjustment factor being traded as if it were a price.
#
# ENFORCE_PRICE_BAND is a call parameter on backtest_session() as well as a
# module default, so the cost of NOT having it can be measured rather than
# asserted -- see claude/mc5_first_results.md.
PRICE_MIN, PRICE_MAX = 2.0, 20.0
ENFORCE_PRICE_BAND = True

MAX_SHARES = 100
MAX_EQUITY_PCT = 40.0
EQUITY = 100_000.0

SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)

# See strategy/mcl/mcl.py and claude/ibkr_commission_structure.md.
COMMISSION_PLAN = "ibkr_tiered"
COMMISSION_PER_SHARE = 0.005     # legacy plan only
SLIPPAGE_TICKS = 1
TICK = 0.01

# Bars needed before the session for the indicators to be meaningful.
MIN_WARMUP_BARS = MACD_SLOW + MACD_SIGNAL


# --- indicators -----------------------------------------------------------

# --- indicators -----------------------------------------------------------
#
# Shared maths from common/indicators.py, bound to MC5's own periods. Note
# roc_pct's floor is MC5's ROC_MIN_BASE rather than the shared default -- see
# that constant for why an unfloored percentage of RSI is meaningless.

from common.commissions import order_cost
from common.indicators import (  # noqa: E402
    ema, rma,
    macd as _macd, rsi as _rsi,
    ols_slope as _ols_slope, roc_pct as _roc_pct,
    resample_bars,
)


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    return _macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)


def rsi(close: pd.Series, length: int = RSI_LEN) -> pd.Series:
    return _rsi(close, length)


def ols_slope(s: pd.Series, n: int = SLOPE_BARS) -> pd.Series:
    return _ols_slope(s, n)


def roc_pct(s: pd.Series, n: int = SLOPE_BARS) -> pd.Series:
    return _roc_pct(s, n, ROC_MIN_BASE)


# --- bar construction ------------------------------------------------------

def to_5m(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-minute bars to 5-minute, labelled at the interval START.

    Delegates to common.indicators.resample_bars, which was verified to
    produce identical output to the copy that used to live here -- including
    on gapped input, where both drop an empty bucket rather than synthesising
    a flat bar.
    """
    return resample_bars(df, BAR_MINUTES)


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


# --- the live path --------------------------------------------------------
#
# Counted in FIVE-MINUTE bars, not minutes. MACD needs MACD_SLOW + MACD_SIGNAL
# to mean anything, the gradients need SLOPE_BARS on top, and roc_pct needs one
# more. 40 five-minute bars is 3 hours 20 minutes of wall clock -- against
# MCL's 40 one-minute bars, which is 40 minutes.
#
# THAT DIFFERENCE IS A WARM-UP PROBLEM A BACKTEST CANNOT SHOW. backtest_session
# computes signals() over the WHOLE cached frame (three days) and only then
# restricts to the session date, so its indicators are warm at 04:00. The live
# trader requests durationStr="1 D", so live MC5 would not be warm until about
# 07:20 and would sit out more than half of a 04:00-09:30 session. Returning
# None while cold is correct and is NOT the fix; the fix is fetching enough
# history, and it belongs with the trader.
MIN_BARS_REQUIRED = MACD_SLOW + MACD_SIGNAL + SLOPE_BARS + 2


@dataclass
class Signals:
    """Same field names as strategy/mcl/mcl.Signals, deliberately.

    The trader consumes whichever the active strategy returns, so the two have
    to stay interchangeable. They are separate classes rather than one shared
    import because making either module depend on the other is a coupling
    neither needs -- and a test asserts the field names match, so drift is
    caught here rather than discovered live.
    """
    long_entry: bool
    exit_signal: bool
    close: float
    detail: dict


def last_closed_bucket(df1m: pd.DataFrame, now) -> "pd.Timestamp | None":
    """The most recent 5-minute bucket that is provably COMPLETE.

    THE TRAP THIS EXISTS FOR. resample_bars labels a bucket at its START, so at
    08:07 the newest bucket is 08:05 and it holds two minutes of a five-minute
    bar. Evaluating it enters on a signal that has not formed -- and it will
    look like it works, because a bucket that is going to close green is
    usually already green. The trader's own 1-minute trim does not help: it
    drops the forming MINUTE, which still leaves a forming BUCKET.

    This project has paid for this once. entry_latency's first MC5 run compared
    5-minute fills with 1-minute bars and reported fill positions of 7.85x the
    bar range with a third of signal bars "not found" -- every number wrong,
    and the report looked complete.

    A bucket labelled T is complete when BOTH hold:

      * the clock has passed T + BAR_MINUTES, and
      * the frame carries a closed 1-minute bar at or after T + BAR_MINUTES - 1.

    The clock alone is not enough: IB history can lag, and a bucket missing its
    last two minutes is not complete because a wall clock says so. The data
    alone is not enough either -- a minute with no print produces no bar, so
    "we hold the 08:09 bar" can never be required.

    A name thin enough to print nothing for several minutes waits for its next
    print. That is the right answer: there is no fill to be had in a minute
    with no trades, and it resolves as soon as anything trades.
    """
    if df1m is None or len(df1m) == 0:
        return None
    last_1m = df1m.index[-1]
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize(last_1m.tz)
    step = pd.Timedelta(minutes=BAR_MINUTES)
    minute = pd.Timedelta(minutes=1)
    # Floor to the bucket the last closed minute falls in, then walk back until
    # one is complete. One step in practice; the loop is here so a stale frame
    # degrades to "no signal" rather than to a wrong one.
    bucket = last_1m.floor(f"{BAR_MINUTES}min")
    while bucket >= df1m.index[0]:
        if now >= bucket + step and last_1m >= bucket + step - minute:
            return bucket
        bucket -= step
    return None


def evaluate_last_bar(df, now) -> "Signals | None":
    """Evaluate MC5 on the last COMPLETE 5-minute bar. None if there is none.

    `df` may be 1-minute or 5-minute bars. `now` is required rather than
    defaulted: every safe answer here depends on what time it is, and a default
    would be a guess made in the one place a guess is most expensive.

    Returns None -- not a no-signal Signals -- whenever the strategy has
    nothing to say: too few bars to warm the indicators, or no complete bucket
    yet. The trader already treats None as "nothing happened this poll".
    """
    if df is None or len(df) == 0:
        return None
    if _looks_5m(df):
        df5 = df
    else:
        closed_at = last_closed_bucket(df, now)
        if closed_at is None:
            return None
        df5 = to_5m(df)
        df5 = df5[df5.index <= closed_at]
    if len(df5) < MIN_BARS_REQUIRED:
        return None

    sig = signals(df5)
    row = sig.iloc[-1]
    return Signals(
        long_entry=bool(row["entry"]),
        exit_signal=bool(row["exit_sig"]),
        close=float(row["close"]),
        detail={
            "macd": round(float(row["macd"]), 5),
            "macd_sig": round(float(row["macd_sig"]), 5),
            "rsi": round(float(row["rsi"]), 2),
            "rsi_roc": round(float(row["rsi_roc"]), 3),
            "macd_slope": round(float(row["macd_slope"]), 5),
            "vol": int(row["volume"]),
            "c_rsi": bool(row["c_rsi"]),
            "c_ema": bool(row["c_ema"]),
            "c_macd": bool(row["c_macd"]),
        },
    )


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


def backtest_session(df, session_date, tz,
                     enforce_price_band: bool | None = None,
                     gap_fills: bool = True,
                     seed_peak_with_bar_high: bool = False,
                     entry_shares: int | None = None) -> list[Trade]:
    """Run one pre-market session on 5-minute bars.

    Accepts 1-minute OR 5-minute bars and resamples if needed, so this can be
    handed exactly the same frame mcl_strategy.backtest_session receives.
    Include pre-session history for warm-up (see the module docstring).
    """
    band = ENFORCE_PRICE_BAND if enforce_price_band is None else enforce_price_band
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
                if band and not (PRICE_MIN <= px <= PRICE_MAX):
                    continue
                # entry_shares bypasses size_for() so a comparison against a
                # real trading day holds size fixed -- see mcl.backtest_session.
                q = size_for(px) if entry_shares is None else int(entry_shares)
                if q >= 1:
                    pos = dict(entry_i=i, entry_px=px, qty=q,
                               # See strategy/mcl/mcl.py: the entry bar's high
                               # happened BEFORE the close we bought at, so
                               # trailing from it prices a move the position
                               # never had. Worse on 5-minute bars than on
                               # 1-minute ones, because the high is further
                               # from the close.
                               peak=(max(px, float(row["high"]))
                                     if seed_peak_with_bar_high else px),
                               entry_t=rows.iloc[i][tcol])
            continue

        trail = pos["peak"] * (1.0 - TRAIL_PCT / 100.0)
        exit_px = exit_reason = None

        if float(row["low"]) <= trail:
            # GAP-THROUGH. Selling AT the trail assumes the market offered that
            # price. When the bar OPENS below the level it never did: price was
            # already through the stop when the bar began, and the best
            # obtainable fill is the open.
            #
            # Measured on MC5 (5-minute bars, 688 stop exits): the bar opened
            # below the trail 48% of the time, and pricing those at `trail`
            # overstated P/L by $20,394 -- against a headline of $20,156. The
            # whole apparent edge was this one assumption. It bites hardest on
            # coarse bars, because a 5-minute gap is bigger than a 1-minute one.
            #
            # gap_fills=False restores the optimistic model, purely so old
            # results stay reproducible.
            fill = (min(trail, float(row["open"])) if gap_fills else trail)
            exit_px, exit_reason = fill - SLIPPAGE_TICKS * TICK, "trailing_stop"
        elif last_of_session:
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "window_close"
        elif bool(row["exit_sig"]):
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "gradient_reversal"

        if exit_px is not None:
            q = pos["qty"]
            gross = (exit_px - pos["entry_px"]) * q
            comm = (order_cost(q, pos["entry_px"], False, COMMISSION_PLAN)
                    + order_cost(q, exit_px, True, COMMISSION_PLAN))
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
    # This line used to read
    #     band = ENFORCE_PRICE_BAND if enforce_price_band is None else ...
    # copied from backtest_session, where `enforce_price_band` is a parameter.
    # Here it is not, so every call raised NameError -- and `band` was never
    # read afterwards anyway. Nothing calls this function, which is why nobody
    # noticed: a calibration aid that cannot be run is one that never existed.
    # Found 2026-09-07 while building the harness.
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
