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

# Commission. "legacy" is the flat $0.005/share this project charged until
# 2026-09-05 and what every published P/L in claude/*.md was computed with --
# keep it available or those results stop being reproducible. The IBKR plans
# come from the published AU schedule; see claude/ibkr_commission_structure.md.
#
# This is NOT a per-share constant any more, because neither real plan is
# linear in quantity: both have per-ORDER minimums ($0.35 Tiered, $1.00 Fixed),
# so cost per share falls as the order grows. Charging a flat rate at the end
# of a trade understates small orders and, with the scale-out mechanic issuing
# many orders per trade, understates them many times over.
COMMISSION_PLAN = "ibkr_tiered"
COMMISSION_PER_SHARE = 0.005     # legacy plan only; matches the Pine backtest
SLIPPAGE_TICKS = 1               # matches the Pine backtest
TICK = 0.01


# --- indicators -----------------------------------------------------------

# --- indicators -----------------------------------------------------------
#
# The maths lives in common/indicators.py; these bind V7's own periods to it.
# Keeping the wrappers preserves every existing call signature (mcl.macd(c),
# mcl.rsi(c), ...) while leaving exactly one implementation of each formula
# in the repo. Change a constant above and every call here follows.

from common.commissions import order_cost  # noqa: E402
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
    # Scale-out bookkeeping. cycles counts completed sell-then-buy-back
    # round trips inside the trade; shares_traded is every share transacted,
    # entry included. Both are 0 / initial size when scaling is off, so the
    # default output is unchanged apart from two extra columns.
    cycles: int = 0
    shares_traded: int = 0


def size_for(price: float, equity: float = EQUITY) -> int:
    if price <= 0:
        return 0
    return max(0, min(MAX_SHARES,
                      math.floor(equity * MAX_EQUITY_PCT / 100.0 / price)))


def backtest_session(df: pd.DataFrame, session_date, tz,
                     use_apex: bool | None = None,
                     require_macd_pos: bool | None = None,
                     scale_out_pct: float | None = None,
                     partial_trail_pct: float = 2.5,
                     rebuy_qty: int | None = None,
                     max_position_shares: int | None = None,
                     rebuy_slip_bps: float = 0.0,
                     trail_pct: float | None = None,
                     max_cycles: int | None = None,
                     commission_plan: str | None = None) -> list[Trade]:
    """Run one pre-market session.

    df must be 1-minute bars in chronological order, tz-aware, and should
    include enough history BEFORE the session for indicator warm-up (>= 60 bars;
    MACD and the volume average both need it).

    use_apex overrides USE_APEX_EXIT for this call only. Passing it explicitly
    rather than mutating the module constant keeps a variant sweep honest: two
    configurations can be evaluated over the same frame with no shared state
    between them.

    THE FOUR EXIT KNOBS, all call parameters with no module state:

        trail_pct          the full trailing stop, % below peak (closes the
                           trade; defaults to the TRAIL_PCT constant)
        partial_trail_pct  % below peak at which a portion is sold
        scale_out_pct      what portion of the CURRENT position that is
        rebuy_qty          shares bought back on a reclaim (None = restore
                           exactly what was sold, so size stays constant)

    plus rebuy_slip_bps (how far above the trigger the buy-back actually
    fills) and max_position_shares (a cap when rebuy_qty grows the position).

    SCALE-OUT / SCALE-BACK-IN (Ben, 2026-09-05, after Ross Cameron's method)
    -----------------------------------------------------------------------
    `scale_out_pct` is None by default and the mechanic is then entirely inert:
    this function reproduces its previous output bit-for-bit. When set, a
    SECOND trailing level is inserted above the existing one:

        partial level = peak * (1 - partial_trail_pct/100)     e.g. 2.5%
        full level    = peak * (1 - TRAIL_PCT/100)             e.g. 5%

    On a pullback to the partial level, `scale_out_pct` of the position is
    sold. If price then reaches the full level the remainder goes too and the
    trade is over. If instead it recovers and TOUCHES the previous bar's high,
    shares are bought back and the cycle repeats, without limit, until the full
    level is finally hit. Only the full level ever closes the position.

    `rebuy_qty` is the buy-back size. None restores exactly what was sold, so
    position size is constant across cycles. An integer buys that many shares
    regardless of what was sold, which lets the position GROW -- sell 50 of
    100, buy 100 back, hold 150. That converges rather than exploding (towards
    ~200 shares at a 50% scale-out, ~133 at 75%) but it roughly doubles risk
    per trade, so `max_position_shares` caps it.

    WHERE THE UPSIDE ACTUALLY COMES FROM, because it is not where it looks:
    with `rebuy_qty=None` this mechanic CANNOT earn more on a runner than
    simply holding. A stock that never pulls back 2.5% behaves identically; one
    that does pull back has had a piece sold cheap and bought back dearer. What
    it buys is a better exit on trades that end at the stop -- part of the
    position leaves 2.5% higher. So restore-mode trades runner profit for
    stop-out profit, and is a risk-shaping change, not a return change.
    The extra RETURN only appears when `rebuy_qty` exceeds what was sold: that
    is adding size into strength, and it is a different bet with different risk.
    Both are worth running; they should not be read as the same idea.

    Intrabar ordering follows the project convention -- the pessimistic branch
    first. The full stop is tested before the partial (a bar low reaching the
    full level has necessarily passed the partial one), and both before any
    buy-back, so a bar that could plausibly have done several things is
    resolved against the position.
    """
    if use_apex is None:
        use_apex = USE_APEX_EXIT
    # A real parameter, not a module constant read at call time. It used to be
    # the latter, which meant common/analysis.py had to SET AND RESTORE
    # S.TRAIL_PCT around every run in a try/finally -- fine single-threaded,
    # a latent bug the moment anything runs two configurations at once, and a
    # standing invitation to leave the constant mutated after an exception.
    if trail_pct is None:
        trail_pct = TRAIL_PCT
    if commission_plan is None:
        commission_plan = COMMISSION_PLAN
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
    # High of the PREVIOUS in-session bar -- the buy-back trigger. None on the
    # first bar, which correctly blocks a re-entry before there is a prior bar.
    prev_high = None

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
                    pos = dict(entry_i=i, entry_px=px, qty=q, init_qty=q,
                               peak=max(px, float(row["high"])),
                               entry_t=rows.iloc[i][tcol],
                               # Scaling bookkeeping. avg_px is the running
                               # average cost of the shares still held; realised
                               # accumulates P/L already banked by partial
                               # sells; shares_traded drives commission, which
                               # must be charged per share actually transacted
                               # rather than assuming one round trip.
                               avg_px=px, realised=0.0, shares_traded=q,
                               scaled_out=False, cycles=0,
                               # Accumulated per ORDER, not derived at the end,
                               # because the per-order minimum makes cost
                               # non-linear in quantity.
                               commission=order_cost(q, px, False,
                                                     commission_plan))
            continue

        # --- managing a position -------------------------------------------
        # Trail is derived from the peak as of the PREVIOUS bar, then tested
        # against this bar's low. No same-bar lookahead.
        trail = pos["peak"] * (1.0 - trail_pct / 100.0)
        exit_px = exit_reason = None

        if float(row["low"]) <= trail:
            exit_px, exit_reason = trail - SLIPPAGE_TICKS * TICK, "trailing_stop"
        elif last_of_session:
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "window_close"
        elif use_apex and bool(row["exit_sig"]):
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "apex_reversal"

        if exit_px is not None:
            q = pos["qty"]
            gross = pos["realised"] + (exit_px - pos["avg_px"]) * q
            comm = pos["commission"] + order_cost(q, exit_px, True,
                                                   commission_plan)
            trades.append(Trade(
                symbol="", date=str(session_date),
                entry_time=str(pos["entry_t"]), exit_time=str(rows.iloc[i][tcol]),
                entry_price=round(pos["entry_px"], 4), exit_price=round(exit_px, 4),
                qty=pos["init_qty"], reason=exit_reason,
                bars_held=i - pos["entry_i"],
                gross=round(gross, 2), commission=round(comm, 2),
                net=round(gross - comm, 2),
                cycles=pos["cycles"],
                shares_traded=pos["shares_traded"] + q))
            pos = None
        else:
            # --- scale out / scale back in, only when enabled ---------------
            # Ordering is deliberate: the full stop above has already been
            # ruled out for this bar, so a partial sell here cannot be masking
            # a full exit. Selling is checked before buying back, so a bar that
            # both dips to the partial level and tags the previous high is
            # resolved as a sell -- against the position, per convention.
            if scale_out_pct:
                partial = pos["peak"] * (1.0 - partial_trail_pct / 100.0)
                if not pos["scaled_out"] and float(row["low"]) <= partial:
                    sell_q = int(pos["qty"] * scale_out_pct / 100.0)
                    if 1 <= sell_q < pos["qty"]:
                        px_out = partial - SLIPPAGE_TICKS * TICK
                        pos["realised"] += (px_out - pos["avg_px"]) * sell_q
                        pos["commission"] += order_cost(sell_q, px_out, True,
                                                        commission_plan)
                        pos["qty"] -= sell_q
                        pos["shares_traded"] += sell_q
                        pos["scaled_out"] = True
                        pos["sold_qty"] = sell_q
                elif pos["scaled_out"] and prev_high is not None \
                        and float(row["high"]) >= prev_high:
                    # A cap on how many times one trade may cycle. Uncapped,
                    # a 1% partial on 1-minute bars produced up to 105 cycles
                    # and 21,200 shares transacted in a SINGLE trade -- 210+
                    # orders on one pre-market small cap, which IB's ~60
                    # requests / 10 minutes would refuse outright and which
                    # exercises the bar-level fill model hundreds of times in
                    # a way it was never validated for.
                    if max_cycles is not None and pos["cycles"] >= max_cycles:
                        pos["scaled_out"] = False
                        prev_high = float(row["high"])
                        continue
                    add = rebuy_qty if rebuy_qty is not None else pos["sold_qty"]
                    if max_position_shares is not None:
                        add = min(add, max_position_shares - pos["qty"])
                    if add >= 1:
                        # A break ABOVE the prior high is a stop-buy, and
                        # IBKR does not accept stop orders outside RTH. Live
                        # this is a marketable limit sent after the break is
                        # seen, so the fill is above the trigger, not at it --
                        # trader.py already crosses by LIMIT_CROSS_BPS = 20.
                        # Charging 0 bps here models a fill nobody can get.
                        px_in = (prev_high * (1.0 + rebuy_slip_bps / 10_000.0)
                                 + SLIPPAGE_TICKS * TICK)
                        # Weighted average cost of the shares now held. The
                        # buy-back is normally ABOVE the price the partial was
                        # sold at, which is exactly the cost this mechanic pays
                        # on a pullback that recovers.
                        pos["avg_px"] = ((pos["avg_px"] * pos["qty"]
                                          + px_in * add) / (pos["qty"] + add))
                        pos["commission"] += order_cost(add, px_in, False,
                                                        commission_plan)
                        pos["qty"] += add
                        pos["shares_traded"] += add
                        pos["cycles"] += 1
                    pos["scaled_out"] = False
            pos["peak"] = max(pos["peak"], float(row["high"]))

        prev_high = float(row["high"])

    return trades
