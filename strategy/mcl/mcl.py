#!/usr/bin/env python3
"""
MCL strategy -- pure logic, no broker, no I/O.

Indicators match Pine's definitions and are the same implementations verified in
test_indicators.py (RSI / MFI / MACD agree with independent loop references to
<3e-14).

V7 rules:
  Session : 04:00-09:30 ET, flat at the close of the window
  Entry   : MACD > signal AND MACD > 0
            AND MFI  > MFI[3]
            AND RSI  > RSI[3]
            AND volume >= 3x previous bar
            AND previous bar volume >= 50% of the trailing 60-bar average
  Exit    : price falls 5% below the highest price since entry
            OR the window closes
            (the apex-reversal exit is OFF by default since 2026-09-05 --
             see USE_APEX_EXIT)
  Size    : min(100 shares, 40% of equity / price), price $2-20 only

EXIT MODELLING -- deliberately more conservative than the Pine backtest
----------------------------------------------------------------------
Pine's `strategy.exit(stop=...)` fills intrabar AT the stop price, using a peak
that already includes the current bar's high. That is optimistic twice over: it
assumes a fill exactly at the level, and it lets the same bar that sets the peak
also trigger against it.

Here the trail level is derived from the peak as of the PREVIOUS bar and checked
against this bar's low. No same-bar lookahead. Expect slightly worse numbers
than the Pine equivalent; that gap is the modelling optimism, not a bug.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time as dtime

import pandas as pd

# --- parameters (V7) ------------------------------------------------------
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MFI_LEN = 14
RSI_LEN = 14
TREND_LOOKBACK = 3
APEX_LOOKBACK = 20
VOL_MULTIPLE = 3.0
FLOOR_FRACTION = 0.5
FLOOR_AVG_LEN = 60

# Exit configuration.
#
# USE_APEX_EXIT gates the apex-reversal exit. TURNED OFF 2026-09-05 after the
# 2x2 sweep over 376 cached sessions / 178 symbols (see
# claude/mcl_apex_macd_sweep.md). Apex exits were NET NEGATIVE in both cells
# that used them -- -$543.73 over 213 exits at a 27% win rate -- while every
# trailing-stop cut was positive. The rule was closing positions while the
# trail was still intact, and losing money doing it.
#
#   apex ON   561 trades  +$2,163.75  +$3.86/trade   drop-top-5  +$316
#   apex OFF  496 trades  +$3,865.53  +$7.79/trade   drop-top-5  +$1,883
#
# Paired by symbol, bootstrapped over the 178 names: +$1,701.78,
# 95% CI [+$703, +$2,816], P(improvement > 0) = 100%. Concentration IMPROVED,
# which is the check that rejected V8 and V9.
#
# The decisive number is friction. The 2026-09-03 live log measured ~$4.26 per
# round trip of slippage beyond the tick-each-way modelled here. Apex ON is
# +$3.86/trade and so does NOT clear it (-$0.40/trade, -$226 overall); apex OFF
# is +$7.79 and does (+$3.53/trade). That is also why that session lost money
# while the backtest showed a profit.
#
# CONSEQUENCE FOR LIVE, not obvious from the numbers: hold times stretch. The
# median stays at 2 bars but p90 goes 4 -> 24 and the maximum is 238 bars, so
# a position open for hours is now normal rather than a hung order. The 5%
# trailing stop is the ONLY protection during those holds and it lives inside
# the running process -- a crash with a position open leaves it unprotected,
# and that is materially more likely now. Worst single trade was unchanged at
# -$97.10, so longer holds did not deepen losses; the trail caps them either way.
#
# Pass use_apex explicitly to backtest_session() to sweep it; this constant is
# only the default. Set it back to True to reproduce V7.
USE_APEX_EXIT = False

# REQUIRE_MACD_POSITIVE gates the `MACD > 0` half of the entry.
#
# This has never been tested on its own. V9 dropped it AND the 3x volume surge
# at the same time, so its -81% expectancy collapse cannot be attributed to
# either change -- and the per-ticker damage (SUGP 2 -> 30 trades, DAIC 3 -> 21)
# points at the surge removal. Sweeping this flag with the surge left intact is
# the missing single-variable test.
REQUIRE_MACD_POSITIVE = True

TRAIL_PCT = 5.0
MAX_SHARES = 100
MAX_EQUITY_PCT = 40.0

# Price band, mirroring the live scanner screen ($2-20).
#
# The backtest did NOT apply this before, and the 2026-09-04 run over 375 pairs
# showed why it must. IB serves SPLIT-ADJUSTED history: a small cap that traded
# at $3 in 2025 and later did a 1:1000 reverse split comes back at $3,000. The
# run produced entry prices up to $32,104 and a headline of +$66.74/trade, which
# was almost entirely those names -- "100 shares at $32,104" is $3.2m of
# notional the account could never hold.
#
# Restricting to $2-20 cut the same run to +$3.74/trade.
#
# NOTE the residual bias, which this does NOT fix: filtering on the ADJUSTED
# price preferentially removes names that later reverse-split, and reverse
# splits follow price collapses. So the surviving subset is tilted towards
# names that held up, and +$3.74 is more likely optimistic than pessimistic.
# Only unadjusted prices with separate adjustment factors settle it.
PRICE_MIN, PRICE_MAX = 2.0, 20.0
ENFORCE_PRICE_BAND = True
EQUITY = 100_000.0

SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)

COMMISSION_PER_SHARE = 0.005     # matches the Pine backtest
SLIPPAGE_TICKS = 1               # matches the Pine backtest
TICK = 0.01


# --- indicators -----------------------------------------------------------

# --- indicators -----------------------------------------------------------
#
# The maths lives in common/indicators.py; these bind V7's own periods to it.
# Keeping the wrappers preserves every existing call signature (mcl.macd(c),
# mcl.rsi(c), ...) while leaving exactly one implementation of each formula
# in the repo. Change a constant above and every call here follows.

from common.indicators import (  # noqa: E402
    ema, rma,
    macd as _macd, rsi as _rsi, mfi as _mfi,
    rising as _rising, falling as _falling, past_apex as _past_apex,
)


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    return _macd(close, MACD_FAST, MACD_SLOW, MACD_SIGNAL)


def rsi(close: pd.Series, length: int = RSI_LEN) -> pd.Series:
    return _rsi(close, length)


def mfi(high, low, close, volume, length: int = MFI_LEN) -> pd.Series:
    return _mfi(high, low, close, volume, length)


def rising(s: pd.Series, n: int = TREND_LOOKBACK) -> pd.Series:
    return _rising(s, n)


def falling(s: pd.Series, n: int = TREND_LOOKBACK) -> pd.Series:
    return _falling(s, n)


def past_apex(s: pd.Series, lookback: int = APEX_LOOKBACK,
              n: int = TREND_LOOKBACK) -> pd.Series:
    return _past_apex(s, lookback, n)


# --- signals --------------------------------------------------------------

def signals(df: pd.DataFrame, require_macd_pos: bool | None = None) -> pd.DataFrame:
    """Add indicator and condition columns. df needs open/high/low/close/volume.

    require_macd_pos overrides REQUIRE_MACD_POSITIVE for this call only.
    """
    if require_macd_pos is None:
        require_macd_pos = REQUIRE_MACD_POSITIVE
    out = df.copy()
    c, h, l, v = out["close"], out["high"], out["low"], out["volume"]

    ml, ms = macd(c)
    m = mfi(h, l, c, v)
    r = rsi(c)
    prev_vol = v.shift(1)
    trail_avg = v.rolling(FLOOR_AVG_LEN).mean().shift(1)

    out["macd"], out["macd_sig"], out["mfi"], out["rsi"] = ml, ms, m, r
    out["prev_vol"], out["trail_avg"] = prev_vol, trail_avg
    out["c_macd"] = (ml > ms) & (ml > 0) if require_macd_pos else (ml > ms)
    out["c_mfi"] = rising(m)
    out["c_rsi"] = rising(r)
    out["c_vol"] = (v >= prev_vol * VOL_MULTIPLE) & (prev_vol > 0)
    out["c_floor"] = (trail_avg > 0) & (prev_vol >= trail_avg * FLOOR_FRACTION)
    out["entry"] = (out["c_macd"] & out["c_mfi"] & out["c_rsi"]
                    & out["c_vol"] & out["c_floor"])
    out["exit_sig"] = past_apex(ml) | past_apex(m) | past_apex(r)
    return out


# --- live / streaming evaluation -------------------------------------------
#
# The paper trader used to carry its own separate copy of every indicator
# function plus its own re-implementation of the entry/exit condition logic
# (evaluate() in the old mcl_paper_trader.py), evaluated on the last bar of a
# rolling window instead of vectorised over a whole session. That is exactly
# the kind of duplication claude/repo_reorg_and_github_plan.md's indicator
# consolidation section warns about -- and it was not merely a style issue.
# The old live copy hardcoded `macd_line > 0` unconditionally, so it never
# actually respected REQUIRE_MACD_POSITIVE the way the backtest did: flipping
# that flag changed backtest results but silently did nothing live. This
# function replaces both copies by calling signals() -- the same vectorised
# path the backtest uses -- and reading off the last row, so live and
# backtest cannot silently diverge again.

MIN_BARS_REQUIRED = MACD_SLOW + MACD_SIGNAL + 5


@dataclass
class Signals:
    long_entry: bool
    exit_signal: bool
    close: float
    detail: dict


def evaluate_last_bar(df: pd.DataFrame,
                      require_macd_pos: bool | None = None) -> "Signals | None":
    """Evaluate the strategy on the LAST CLOSED bar of df.

    df must have columns open/high/low/close/volume, 1-minute bars in
    chronological order, already restricted to the bars indicators should be
    built from (i.e. including pre-market). require_macd_pos overrides
    REQUIRE_MACD_POSITIVE for this call only, same as signals().
    """
    if len(df) < MIN_BARS_REQUIRED:
        return None
    sig = signals(df, require_macd_pos=require_macd_pos)
    row = sig.iloc[-1]
    return Signals(
        long_entry=bool(row["entry"]),
        exit_signal=bool(row["exit_sig"]),
        close=float(row["close"]),
        detail={
            "macd": round(float(row["macd"]), 5),
            "macd_sig": round(float(row["macd_sig"]), 5),
            "mfi": round(float(row["mfi"]), 2),
            "rsi": round(float(row["rsi"]), 2),
            "vol": int(row["volume"]),
            "prev_vol": int(row["prev_vol"]) if pd.notna(row["prev_vol"]) else 0,
            "trail_avg": round(float(row["trail_avg"]), 1) if pd.notna(row["trail_avg"]) else 0.0,
            "c_macd": bool(row["c_macd"]),
            "c_mfi": bool(row["c_mfi"]),
            "c_rsi": bool(row["c_rsi"]),
            "c_vol_mult": bool(row["c_vol"]),
            "c_floor": bool(row["c_floor"]),
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


def backtest_session(df: pd.DataFrame, session_date, tz,
                     use_apex: bool | None = None,
                     require_macd_pos: bool | None = None) -> list[Trade]:
    """Run one pre-market session.

    df must be 1-minute bars in chronological order, tz-aware, and should
    include enough history BEFORE the session for indicator warm-up (>= 60 bars;
    MACD and the volume average both need it).

    use_apex overrides USE_APEX_EXIT for this call only. Passing it explicitly
    rather than mutating the module constant keeps a variant sweep honest: two
    configurations can be evaluated over the same frame with no shared state
    between them.
    """
    if use_apex is None:
        use_apex = USE_APEX_EXIT
    sig = signals(df, require_macd_pos=require_macd_pos)
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
            if row["entry"]:
                px = float(row["close"]) + SLIPPAGE_TICKS * TICK
                if ENFORCE_PRICE_BAND and not (PRICE_MIN <= px <= PRICE_MAX):
                    continue
                q = size_for(px)
                if q >= 1:
                    pos = dict(entry_i=i, entry_px=px, qty=q,
                               peak=max(px, float(row["high"])),
                               entry_t=rows.iloc[i][tcol])
            continue

        # --- managing a position -------------------------------------------
        # Trail is derived from the peak as of the PREVIOUS bar, then tested
        # against this bar's low. No same-bar lookahead.
        trail = pos["peak"] * (1.0 - TRAIL_PCT / 100.0)
        exit_px = exit_reason = None

        if float(row["low"]) <= trail:
            exit_px, exit_reason = trail - SLIPPAGE_TICKS * TICK, "trailing_stop"
        elif last_of_session:
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "window_close"
        elif use_apex and bool(row["exit_sig"]):
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "apex_reversal"

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
