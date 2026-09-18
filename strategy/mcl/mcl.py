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

# The label this strategy gives its signal exit. See mc5.EXIT_SIGNAL_REASON for
# why it is a constant rather than a literal: the trader used to hard-code
# "apex_reversal" for every strategy while MC5's backtest wrote
# "gradient_reversal" for the same rule, and both now land in one database.
EXIT_SIGNAL_REASON = "apex_reversal"

# REQUIRE_MACD_POSITIVE gates the `MACD > 0` half of the entry.
#
# This has never been tested on its own. V9 dropped it AND the 3x volume surge
# at the same time, so its -81% expectancy collapse cannot be attributed to
# either change -- and the per-ticker damage (SUGP 2 -> 30 trades, DAIC 3 -> 21)
# points at the surge removal. Sweeping this flag with the surge left intact is
# the missing single-variable test.
REQUIRE_MACD_POSITIVE = True

# Shown on alerts so a fill on a phone says which strategy fired it.
# Lives on the STRATEGY rather than in the trader, so a second trader
# cannot end up labelling its fills with the first one's name.
STRATEGY_NAME = "MCL"

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

from common import profit_ladder as PL  # noqa: E402
from common import target_exit as TE  # noqa: E402
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

def signals(df: pd.DataFrame, require_macd_pos: bool | None = None,
            vol_multiple: float | None = None) -> pd.DataFrame:
    """Add indicator and condition columns. df needs open/high/low/close/volume.

    require_macd_pos overrides REQUIRE_MACD_POSITIVE for this call only, and
    vol_multiple overrides VOL_MULTIPLE the same way. Both default to None,
    which reads the module constant, so the live path -- which passes neither
    -- is bit-identical and a sweep cannot change what the trader does.

    REGISTERED_entry_sweep.md (H-E2) is why vol_multiple exists: the 3x surge
    is one of the two clauses that force MCL's entry onto the spike bar, and
    V9 removed it together with MACD > 0, so neither has ever been read alone.
    """
    if require_macd_pos is None:
        require_macd_pos = REQUIRE_MACD_POSITIVE
    if vol_multiple is None:
        vol_multiple = VOL_MULTIPLE
    if vol_multiple <= 0:
        raise ValueError(f"vol_multiple must be positive, got {vol_multiple!r}")
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
    out["c_vol"] = (v >= prev_vol * vol_multiple) & (prev_vol > 0)
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
    # The bar this signal was COMPUTED ON, which the live trader dedupes
    # entries on. For MCL it equals the frame's last row -- which is precisely
    # why it must be carried rather than inferred by the caller: the caller
    # inferring it is correct for MCL and wrong for MC5, and it looked right
    # for three sessions. See mc5.Signals.bar_ts.
    bar_ts: object = None


def evaluate_last_bar(df: pd.DataFrame,
                      require_macd_pos: bool | None = None,
                      use_apex: bool | None = None) -> "Signals | None":
    """Evaluate the strategy on the LAST CLOSED bar of df.

    df must have columns open/high/low/close/volume, 1-minute bars in
    chronological order, already restricted to the bars indicators should be
    built from (i.e. including pre-market). require_macd_pos overrides
    REQUIRE_MACD_POSITIVE for this call only, same as signals().

    USE_APEX_EXIT IS APPLIED HERE, not left to the caller.

    It was, until 2026-09-08, and the result was a live/backtest split on the
    one rule that changed. `signals()` computes the raw apex condition;
    `backtest_session` gates it on USE_APEX_EXIT, which has been False since
    2026-09-05; this function returned the UNGATED value, and trader.py acted
    on it. So the backtest, the Pine script and every published figure were
    V11 (apex off) while the live trader was still V7 (apex on) -- the version
    measured at +$3.86/trade against ~$4.26 of round-trip friction, i.e. the
    one that does not clear its own costs.

    claude/mcl_apex_macd_sweep.md states "live and backtest both route through
    signals() / evaluate_last_bar(), so the flag governs both -- no separate
    live edit". Routing through the same function was necessary and was not
    sufficient: the flag is read in backtest_session, which the live path never
    calls. It is read here now, so that claim is true rather than nearly true.
    """
    if len(df) < MIN_BARS_REQUIRED:
        return None
    if use_apex is None:
        use_apex = USE_APEX_EXIT
    sig = signals(df, require_macd_pos=require_macd_pos)
    row = sig.iloc[-1]
    return Signals(
        long_entry=bool(row["entry"]),
        exit_signal=bool(row["exit_sig"]) and use_apex,
        close=float(row["close"]),
        bar_ts=sig.index[-1],
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


def check_profit_floor(profit_floor) -> None:
    """(arm_ticks, floor_ticks), both whole ticks, arm strictly above floor.

    A floor at or above its own arming level would sit above the price that
    armed it and exit on the next bar by construction -- a rule that only
    ever measures its own trigger. Refused rather than run.
    """
    if profit_floor is None:
        return
    try:
        arm, floor = profit_floor
    except (TypeError, ValueError):
        raise ValueError(f"profit_floor must be (arm_ticks, floor_ticks), "
                         f"got {profit_floor!r}") from None
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (arm, floor)):
        raise ValueError(f"profit_floor ticks must be ints, got {profit_floor!r}")
    if floor < 0 or arm <= floor:
        raise ValueError(f"profit_floor needs arm_ticks > floor_ticks >= 0, "
                         f"got {profit_floor!r}")


def reaches_arm(entry_px: float, high: float, profit_floor) -> bool:
    """Has `high` reached entry + arm ticks? Compared in TICKS with a tolerance,
    because 2.69 + 0.15 is 2.8400000000000003 in binary and a bar whose high is
    exactly 2.84 must arm -- the float-boundary trap screen_at_build.md §4
    recorded twice."""
    return (high - entry_px) / TICK >= profit_floor[0] - 1e-6


def floor_level(entry_px: float, profit_floor) -> float:
    """entry + floor ticks, rounded to kill binary residue."""
    return round(entry_px + profit_floor[1] * TICK, 6)


def stop_level(peak: float, trail_pct: float,
               trail_cents: float | None = None) -> float:
    """Where the trailing stop sits, given the peak so far.

    PERCENTAGE OR CENTS, and they are not two tunings of one rule. Every stop
    in this project is a percentage; every stop Ross Cameron states is 10-20
    cents (warrior_0_universe_and_risk.md §5.1). Across a $2-20 band 15c is
    7.5% at $2 and 0.75% at $20 -- a factor of ten.

    A FUNCTION rather than one line inside the walk, because the walk is only
    reachable through a full backtest and three separate mutations of that
    line survived a synthetic-frame test that could not tell the two rules
    apart. The arithmetic is the claim; it should be assertable directly.

    `trail_cents=0` means a stop AT the peak, not "fall back to percent" --
    `is not None`, deliberately. A zero that silently reverted would make the
    tightest cell in a sweep secretly the loosest.
    """
    if trail_cents is not None:
        return peak - trail_cents
    return peak * (1.0 - trail_pct / 100.0)


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
    # Pyramid bookkeeping: adds is how many times shares were ADDED on a
    # recovered pullback (nothing sold), max_qty the largest position held.
    # max_qty is what the account actually has to fund, so it is reported
    # rather than inferred -- the scale-out grid's winner needed 734 shares
    # against $4,131.89 net liq and nothing in the backtest noticed.
    adds: int = 0
    max_qty: int = 0


def size_for(price: float, equity: float = EQUITY) -> int:
    if price <= 0:
        return 0
    return max(0, min(MAX_SHARES,
                      math.floor(equity * MAX_EQUITY_PCT / 100.0 / price)))


def in_session_mask(index, session_date, tz):
    """Which bars of `index` belong to `session_date`'s session, bar for bar.

    EXTRACTED from backtest_session 2026-09-16, unchanged, so that the live
    trader's stale-bar gate has something REAL to be tested against. It was
    three inline lines; the live path had no equivalent at all, and when one
    was finally written the only way to check the two agreed would have been to
    copy the expression into the test -- and a guard tested by a copy of itself
    is not tested.

    `backtest_session` calls this, `tests/brokers/ibkr/test_stale_signal_bar.py`
    calls this and compares it against `trader.bar_session_ok` bar for bar. One
    construction, so the engine and the live path cannot drift.

    Bars are LEFT-LABELLED: the 09:29 bar covers 09:29:00-09:29:59 and is the
    last one in a session ending at 09:30, which is why the interval is
    half-open at the end.
    """
    local = index.tz_convert(tz)
    return ((local.date == session_date)
            & (local.time >= SESSION_START)
            & (local.time < SESSION_END))


def backtest_session(df: pd.DataFrame, session_date, tz,
                     price_min: float | None = None,
                     use_apex: bool | None = None,
                     require_macd_pos: bool | None = None,
                     vol_multiple: float | None = None,
                     scale_out_pct: float | None = None,
                     partial_trail_pct: float = 2.5,
                     rebuy_qty: int | None = None,
                     max_position_shares: int | None = None,
                     rebuy_slip_bps: float = 0.0,
                     trail_pct: float | None = None,
                     trail_cents: float | None = None,
                     max_cycles: int | None = None,
                     commission_plan: str | None = None,
                     rebuy_trigger: str = "peak",
                     entry_shares: int | None = None,
                     pyramid_qty: int | None = None,
                     pyramid_pullback_pct: float = 2.5,
                     scale_up_pct: float | None = None,
                     scale_up_portion: float = 50.0,
                     rebuy_dip_pct: float = 2.5,
                     rebuy_ref: str = "peak",
                     gap_fills: bool = True,
                     seed_peak_with_bar_high: bool = False,
                     trail_on_close: bool = False,
                     trail_confirm_bars: int = 0,
                     max_adds: int | None = None,
                     entry_delay_bars: int = 0,
                     max_hold_bars: int | None = None,
                     not_before: dtime | None = None,
                     entry_bars: "pd.Series | None" = None,
                     entry_px_by_bar: "pd.Series | None" = None,
                     ladder: "PL.LadderConfig | None" = None,
                     target_exit: "TE.TargetExit | None" = None,
                     target_cents: float | None = None,
                     green_hold_bars: int | None = None,
                     hard_stop: float | None = None,
                     skip_entries: int = 0,
                     entry_gate: "pd.Series | None" = None,
                     profit_floor: "tuple[int, int] | None" = None) -> list[Trade]:
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
        rebuy_trigger      what counts as a reclaim:
                             "peak"          price regains the high the
                                             pullback started from (DEFAULT --
                                             this is the rule as described)
                             "prev_bar_high" the first bar that fails to make
                                             a lower high

    The two triggers are not variations on a theme, they are opposite trades,
    and the difference was found by measuring rather than reasoning. Over 4,359
    re-entries, "prev_bar_high" bought back BELOW its own sell price 82% of the
    time, median -2.99%, and below the peak it sold off 88% of the time, median
    -3.69%. That is not re-entering on strength, it is averaging down into a
    slide -- which is why it needed a 15% trail to survive, why it earned most
    on the FLATTEST names, and why it ran away without limit as cycles were
    allowed to accumulate. "peak" is the rule actually intended and behaves
    like a normal parameter: capping cycles at 1 IMPROVES it.

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
    trade is over. If instead it recovers and RECLAIMS THE PEAK the pullback
    started from (`rebuy_trigger`, above), shares are bought back and the cycle
    repeats until the full level is finally hit -- capped by `max_cycles` if
    given. Only the full level ever closes the position.

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

    NOT_BEFORE: THE POINT-IN-TIME ENTRY FLOOR
    -----------------------------------------
    `not_before` is an ET time-of-day before which no entry may be taken. It
    exists for `common/pit_strategy.py`, which runs this engine over a universe
    built by `common/screen_sim.py` where every name carries a `first_seen` --
    the moment the live screen would actually have surfaced it. A name the feed
    puts on the watchlist at 07:20 cannot be bought at 04:30, and running
    without the floor would reproduce exactly the look-ahead that whole exercise
    exists to remove, while producing a number that looks like an answer.

    Two properties, both tested:

      * It can only move an entry LATER or remove it. The floor is applied to
        the bar's own timestamp and no bar is ever brought forward, so a floor
        earlier than SESSION_START is inert rather than permissive.
      * `not_before=None` is BIT-IDENTICAL to this function before the
        parameter existed. This is a published engine; a default that changed
        behaviour would silently rewrite every result already in the docs.

    The floor is tested against the bar's START timestamp, which is up to one
    bar more conservative than necessary (a 1-minute bar stamped 06:09 is not
    knowable until 06:10, so a `first_seen` of 06:10 could legitimately fill on
    it). Conservative is the correct direction for a control: it can cost
    entries, never manufacture them.

    SKIP_ENTRIES: PASS OVER THE FIRST N ENTRIES OF THE SESSION
    ----------------------------------------------------------
    `skip_entries` is the number of entries the engine WOULD OTHERWISE HAVE
    TAKEN that are passed over before the first position is opened. An entry
    here means a bar on which the rule fires while flat, at or after the
    floor, inside the price band, with a size of at least one share -- a
    band-refused signal is not an entry and is not counted. Registered in
    docs/research/REGISTERED_first_entry_skip.md (H-B1) from the live record's
    finding that the first entry in a name-day lost and later ones did not.

    It is the SIGNAL-ORDINAL form, on purpose: with the first position never
    opened, bars the baseline was in a trade for become live signal bars, so
    the skipped book's entries are not a subset of the baseline's. That is
    what a live trader following the rule would experience, and the
    alternative -- deleting the first trade from a finished book -- is an
    accounting filter that the study prints beside it and does not read.

    `0` is bit-identical to this function before the parameter existed, for
    the same reason `not_before=None` is.

    ENTRY_GATE: A MASK OVER ENTRIES, AND-ED WITH THE RULE
    -----------------------------------------------------
    `entry_gate` is a boolean Series on the bar index. An entry can be taken on
    a bar only if the rule fires there AND the gate is True there. Unlike
    `entry_bars`, which REPLACES the rule's signal so a refused bar can be
    priced, the gate can only remove entries -- it is the shape of every
    "take the signal only if ..." hypothesis (docs/research/REGISTERED_range_rank.md
    is the first). A bar absent from the gate's index is False: a gate that
    does not know about a bar does not admit it. Signal-ordinal, as
    `skip_entries`: a gated-off entry leaves the engine flat and later bars
    fire as the rule says. `None` is bit-identical to this function before
    the parameter existed.
    """
    if skip_entries < 0:
        raise ValueError(f"skip_entries must be >= 0, got {skip_entries}")
    check_profit_floor(profit_floor)
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
    sig = signals(df, require_macd_pos=require_macd_pos, vol_multiple=vol_multiple)
    local = sig.index.tz_convert(tz)
    in_sess = in_session_mask(sig.index, session_date, tz)
    idx = [i for i, f in enumerate(in_sess) if f]
    if not idx:
        return []

    # The point-in-time entry floor (see the docstring). A MASK over entries
    # rather than a narrowing of `idx`, deliberately: `idx` also drives
    # `prev_high` and `last_of_session`, so dropping bars from it would change
    # the buy-back trigger and which bar counts as the forced flatten -- i.e.
    # it would alter the EXIT model as a side effect of an ENTRY restriction.
    # `None` yields an all-True mask, which is why the default path is
    # bit-identical rather than merely equivalent.
    entry_allowed = ([True] * len(sig) if not_before is None
                     else [t >= not_before for t in local.time])

    # `entry_bars` REPLACES the rule's own entry signal, bar for bar. It exists
    # so a refused bar can be PRICED with this exact exit model instead of a
    # second implementation of the exit written next to the question -- which
    # is how the live path and the backtest drifted apart for three days.
    #
    # It is a replacement rather than an addition on purpose. "Enter where the
    # rule said no" and "enter where the rule said yes OR where I say so" are
    # different populations, and a union would quietly mix a control into its
    # own treatment.
    #
    # None leaves the rule untouched, so the default path is bit-identical.
    if entry_bars is None:
        take = None
    else:
        aligned = entry_bars.reindex(sig.index, fill_value=False)
        take = [bool(x) for x in aligned]
    if entry_gate is not None:
        gate = entry_gate.reindex(sig.index, fill_value=False)
        entry_allowed = [a and bool(g) for a, g in zip(entry_allowed, gate)]

    # `entry_px_by_bar` REPLACES THE FILL PRICE on the bar entry happens, and
    # nothing else. It exists for one legitimate case: a LIMIT order whose
    # price was decided at signal time and which filled later, at the limit
    # rather than at a bar's close.
    #
    # IT CANNOT BE USED TO FILL INSIDE THE SIGNAL BAR. The signal is not known
    # until that bar closes, so no price inside it was ever available -- a
    # study that "fills at the signal bar's midpoint" is reading the future.
    # The caller chooses WHICH bar via entry_bars; this says what was paid
    # there, and the caller is responsible for that price having been reachable.
    #
    # No slippage tick is added to an overridden price: a limit fills at the
    # limit or better, and adding a tick would charge market-order slippage to
    # an order that did not pay it. The ROUND-TRIP friction charged downstream
    # was measured on market orders and is therefore the wrong number for a
    # limit -- conservative, in an unmeasured direction, and said out loud
    # rather than corrected by guesswork.
    #
    # None leaves the fill untouched, so the default path is bit-identical.
    px_at = (None if entry_px_by_bar is None
             else entry_px_by_bar.reindex(sig.index).tolist())

    # The ENTRY floor (REGISTERED_price_floor, H-S5): raises PRICE_MIN for the
    # price an entry may be taken at, and nothing else. The universe, the
    # ceiling, the slippage tick and the delayed-entry price are untouched, and
    # None is the shipped constant, so it is bit-identical by default. Not the
    # profit floor, which is a different rule with a local of its own below.
    entry_floor = PRICE_MIN if price_min is None else float(price_min)

    trades: list[Trade] = []
    pos = None
    rows = sig.reset_index()
    tcol = rows.columns[0]
    # High of the PREVIOUS in-session bar -- the buy-back trigger. None on the
    # first bar, which correctly blocks a re-entry before there is a prior bar.
    prev_high = None
    skipped = 0

    for k, i in enumerate(idx):
        row = rows.iloc[i]
        last_of_session = (k == len(idx) - 1)

        if pos is None:
            fires = row["entry"] if take is None else take[i]
            if fires and entry_allowed[i]:
                # ENTRY LATENCY. entry_delay_bars=0 is the rule as backtested:
                # the signal bar closes and we are filled at that close. LIVE,
                # measured 2026-09-09, the order leaves SIXTY SECONDS after the
                # bar closes -- three signals out of three -- so the price
                # actually paid belongs to the NEXT bar. Delaying by a bar
                # prices that minute instead of assuming it away.
                #
                # The signal is deliberately NOT re-tested at the delayed bar.
                # A live order already sent is not withdrawn because the next
                # bar looked worse, and re-testing here would measure a
                # different and flattering strategy.
                if entry_delay_bars:
                    j = i + entry_delay_bars
                    # Must land with at least one bar LEFT to manage on. An
                    # entry on the final bar could never be exited, and the
                    # trade would be silently dropped from the results -- the
                    # same failure the trail_confirm_bars comment below
                    # records, arriving through a different door.
                    if j >= idx[-1]:
                        continue
                    i, row = j, rows.iloc[j]
                over = None if px_at is None else px_at[i]
                px = (float(row["close"]) + SLIPPAGE_TICKS * TICK
                      if over is None or over != over else float(over))
                if ENFORCE_PRICE_BAND and not (entry_floor <= px <= PRICE_MAX):
                    continue
                # entry_shares bypasses size_for() so a study can hold size
                # fixed while varying something else -- and, crucially, so a
                # pyramid can be compared against simply STARTING at the size
                # it builds to. Without that control, extra size always wins.
                q = size_for(px) if entry_shares is None else entry_shares
                if q >= 1:
                    # The entry the engine would have taken. Passed over
                    # while the skip budget lasts -- after the band and the
                    # size, so a refused signal does not spend it.
                    if skipped < skip_entries:
                        skipped += 1
                        continue
                    pos = dict(entry_i=i, entry_px=px, qty=q, init_qty=q,
                               ladder_done=0, target_taken=False,
                               # SEEDING THE PEAK. The default takes the entry
                               # bar's HIGH -- but that high happened BEFORE
                               # the close we bought at, so it is a move the
                               # position never captured. Trailing from it puts
                               # the stop above the market at the instant of
                               # entry in a large minority of trades, which the
                               # optimistic fill model then books as a
                               # guaranteed profit. False trails from the entry
                               # price alone, which is the price actually paid.
                               peak=(max(px, float(row["high"]))
                                     if seed_peak_with_bar_high else px),
                               entry_t=rows.iloc[i][tcol],
                               # Scaling bookkeeping. avg_px is the running
                               # average cost of the shares still held; realised
                               # accumulates P/L already banked by partial
                               # sells; shares_traded drives commission, which
                               # must be charged per share actually transacted
                               # rather than assuming one round trip.
                               avg_px=px, realised=0.0, shares_traded=q,
                               scaled_out=False, cycles=0, capped=False,
                               armed=False, arm_level=None, adds=0, max_qty=q,
                               # Sell-into-strength ladder. up_ref is the price
                               # the next sell level is measured from: the entry
                               # first, then each buy-back price in turn.
                               up_ref=px, scaled_up=False, up_peak=0.0,
                               up_sold_qty=0, up_sell_px=0.0,
                               breached_at=None, breach_level=0.0,
                               # H-C2's profit floor: set at the CLOSE of the
                               # first managed bar that reaches entry + arm
                               # ticks, so it protects from the next bar on.
                               floor_armed=False,
                               # Accumulated per ORDER, not derived at the end,
                               # because the per-order minimum makes cost
                               # non-linear in quantity.
                               commission=order_cost(q, px, False,
                                                     commission_plan))
            continue

        # --- managing a position -------------------------------------------
        # NEVER MANAGE THE ENTRY BAR. With no delay the loop already moves past
        # it, so this is a no-op; with a delay the entry was taken at a bar the
        # loop has not reached yet, and without this the trail would be tested
        # against the very bar we bought on -- a same-bar lookahead that stops
        # trades out at the instant of entry and would make the delay look far
        # worse than it is.
        if i <= pos["entry_i"]:
            continue

        # Trail is derived from the peak as of the PREVIOUS bar, then tested
        # against this bar's low. No same-bar lookahead.
        # PERCENTAGE OR CENTS, and they are not two tunings of one rule.
        #
        # Every stop in this project is a percentage; every stop Ross Cameron
        # states is 10-20 cents (warrior_0_universe_and_risk.md §5.1, and he
        # calls the cap calibrated to his own average loser rather than to the
        # chart). Across a $2-20 band 15c is 7.5% at $2 and 0.75% at $20 -- a
        # factor of TEN, so this is a structural difference and not a
        # parameter to sweep between.
        #
        # The cap is applied to the DISTANCE, so a cent stop is always at or
        # tighter than the percentage one it replaces; it can never widen a
        # stop, which would be a different change wearing the same name.
        trail = stop_level(pos["peak"], trail_pct, trail_cents)
        # CAMERON'S EXIT, rule 1 of warrior_0 §5.3: once the target is reached
        # the stop moves to BREAKEVEN and the trail is off. This is the piece
        # the ladder did not test -- it left the 5% trail on the remainder --
        # and it is the piece the 71%-vs-32% win-rate argument rests on.
        #
        # The trail stays in force BEFORE the target. His own initial stop is
        # min(structure, 10-20c) and that was measured and rejected on
        # 2026-09-10; substituting a rejected stop into a test of the exit
        # would confound the question with a settled answer. Our stop until the
        # target, his after it, and the report calls it a hybrid.
        if (target_exit is not None and target_exit.breakeven
                and pos.get("target_taken")):
            trail = pos["avg_px"]
        # HARD STOP (MCL-PB v4, 2026-09-16): a fixed price under the position,
        # the pullback low the entry was bought above. It is tested exactly as
        # the trail is -- same gap-through, same tick -- and simply replaces
        # the trail level while it is the higher of the two, so a trade is
        # protected by whichever is tighter. The exit is labelled by which
        # level did the work. None is bit-identical.
        stop_label = "trailing_stop"
        if hard_stop is not None and hard_stop > trail:
            trail, stop_label = hard_stop, "structure_stop"
        # PROFIT FLOOR (H-C2, docs/research/REGISTERED_profit_floor.md): once
        # armed, entry + floor ticks replaces the stop level while it is the
        # HIGHER of the two -- exactly the hard stop's shape, so it can only
        # tighten the exit, never widen it. Same gap-through, same tick.
        # Labelled by the level that did the work. None is bit-identical.
        if profit_floor is not None and pos["floor_armed"]:
            floor_px = floor_level(pos["entry_px"], profit_floor)
            if floor_px > trail:
                trail, stop_label = floor_px, "profit_floor"
        exit_px = exit_reason = None

        # HOW THE TRAIL IS TESTED, which is a separate question from how wide
        # it is. The default is the intrabar low, so a single wick through the
        # level exits the trade at the level. The two alternatives both exist
        # to answer "did we sell into noise?" without simply widening:
        #
        #   trail_on_close      require the bar to CLOSE below the level. A
        #                       wick that recovers within the bar is ignored,
        #                       but the fill is then the close, which can be
        #                       well below the level -- it buys fewer exits at
        #                       a worse price on the ones that do happen.
        #   trail_confirm_bars  the low may breach, but the position is only
        #                       closed if price is STILL below the level N bars
        #                       later. Between breach and confirmation the
        #                       trade is unprotected, which is a real risk and
        #                       not merely a modelling choice.
        #
        # Both are strictly looser than the default, so neither can be judged
        # against the 5% baseline alone -- they have to beat a WIDER intrabar
        # trail that gives up the same amount of room. See common/stop_timing.py.
        # NOTE THE SHAPE OF THIS CHAIN. It used to start with
        # `if trail_confirm_bars > 0:` -- a test on a PARAMETER, not on price
        # -- so whenever either variant was enabled the branch was always
        # taken and the `elif last_of_session` below became unreachable. A
        # position still open at 09:30 was then never closed and the trade was
        # silently DROPPED from the results: 450 trades instead of 496, with
        # the dropped ones' P/L simply missing. The trail test therefore has to
        # resolve to an exit-or-not first, and the other exits are checked
        # afterwards on `exit_px is None`.
        if trail_confirm_bars > 0:
            if pos["breached_at"] is None:
                if float(row["low"]) <= trail:
                    pos["breached_at"] = i
                    pos["breach_level"] = trail
            elif i - pos["breached_at"] >= trail_confirm_bars:
                if float(row["close"]) <= pos["breach_level"]:
                    exit_px = float(row["close"]) - SLIPPAGE_TICKS * TICK
                    exit_reason = stop_label
                else:
                    # Back above the level at the check: forget the breach.
                    # Without this the rule would be a DELAYED stop (one early
                    # wick arms a certain exit) rather than a CONFIRMED one.
                    pos["breached_at"] = None
        elif trail_on_close:
            if float(row["close"]) <= trail:
                exit_px = float(row["close"]) - SLIPPAGE_TICKS * TICK
                exit_reason = stop_label
        elif float(row["low"]) <= trail:
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
            exit_px, exit_reason = fill - SLIPPAGE_TICKS * TICK, stop_label

        # FIXED PROFIT TARGET IN CENTS (Ben, 2026-09-16, for MCL-PB): a limit
        # sell resting at entry + target_cents for the WHOLE position. Tested
        # AFTER the trail so a bar that reaches both resolves as the stop, the
        # project's standing tie rule. A bar that OPENS above the target fills
        # at the open -- a resting limit is filled at its price or better -- and
        # no slippage tick is charged, as for every limit fill in this engine.
        # Distinct from `target_exit`, which is a PARTIAL at a percentage with
        # a breakeven stop. None leaves the engine bit-identical.
        if (exit_px is None and target_cents is not None
                and float(row["high"]) >= pos["entry_px"] + target_cents - 1e-9):
            tgt = pos["entry_px"] + target_cents
            exit_px, exit_reason = max(tgt, float(row["open"])), "target"

        if exit_px is None and last_of_session:
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "window_close"
        elif (exit_px is None and green_hold_bars is not None
                and i - pos["entry_i"] >= green_hold_bars
                and float(row["close"]) > pos["entry_px"]):
            # GREEN HOLD (Ben, 2026-09-16, for MCL-PB v3): a position that is in
            # profit N bars after entry is closed at that close; one that is not
            # keeps riding the trail. After the trail (stop wins ties) and after
            # the window close (the session forcing the issue is not this
            # rule's exit). `is not None`: 0 bars means "sell the entry bar's
            # own close if green", not "off". None is bit-identical.
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "green_hold"
        elif exit_px is None and use_apex and bool(row["exit_sig"]):
            exit_px, exit_reason = (float(row["close"]) - SLIPPAGE_TICKS * TICK,
                                    EXIT_SIGNAL_REASON)
        elif (exit_px is None and max_hold_bars is not None
                and i - pos["entry_i"] >= max_hold_bars):
            # TIME CAP. Ben, 2026-09-10: "the position should not be held for
            # more than 5 mins."
            #
            # LAST in the exit order, deliberately. The trail is protection and
            # must win when both land on the same bar; window_close is the
            # session forcing the issue and is not a decision this rule gets to
            # relabel. A cap that outranked either would silently re-attribute
            # exits that already had a cause, and the exit mix is how this
            # project reads what a strategy is doing.
            #
            # `is not None`, not truthiness: max_hold_bars=0 must mean "the
            # tightest cap" and not "no cap". The same trap was live in
            # trail_cents, where a zero that fell back to the default would have
            # made the tightest cell of a sweep secretly the loosest.
            exit_px, exit_reason = float(row["close"]) - SLIPPAGE_TICKS * TICK, "hold_cap"

        # Arming reads THIS bar's high AFTER this bar's exits were decided, so
        # the floor can first act on the next bar -- the trail's own
        # previous-bar convention. The entry bar never gets here.
        if profit_floor is not None and reaches_arm(pos["entry_px"],
                                                    float(row["high"]),
                                                    profit_floor):
            pos["floor_armed"] = True

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
                shares_traded=pos["shares_traded"] + q,
                adds=pos["adds"], max_qty=pos["max_qty"]))
            pos = None
        else:
            # --- target exit: half off, then breakeven ------------------------
            # AFTER the full-exit block for the same reason the ladder is: a bar
            # that reaches the target AND trips the stop resolves as the stop.
            #
            # Tested against the CLOSE. A target tagged only by the bar's high
            # is a target reached intrabar at a price the strategy could not
            # have acted on -- and this rule is far more sensitive to that than
            # the trail is, because the target is a level price runs THROUGH
            # rather than one it settles below.
            if (target_exit is not None and pos is not None
                    and not pos.get("target_taken")
                    and float(row["close"]) >= target_exit.target_price(pos["avg_px"])):
                sell_q = target_exit.qty_at_target(pos["qty"])
                # The flag is set even when nothing is sold. take_frac=0 is the
                # cell that isolates the STOP change from the partial, and it
                # only means anything if the breakeven still arms.
                pos["target_taken"] = True
                if sell_q > 0:
                    px_out = float(row["close"]) - SLIPPAGE_TICKS * TICK
                    pos["realised"] += (px_out - pos["avg_px"]) * sell_q
                    pos["commission"] += order_cost(sell_q, px_out, True,
                                                    commission_plan)
                    pos["qty"] -= sell_q
                    pos["shares_traded"] += sell_q

            # --- take-profit ladder, only when enabled -----------------------
            # Ben, 2026-09-10. Sells half on every +10% (compounding from the
            # last rung), down to a 20-share floor where the remainder goes at
            # once. See common/profit_ladder.py -- the rule, its pinned
            # parameters and the reason its expected sign is negative all live
            # there rather than being restated here.
            #
            # AFTER the full-exit block above, so a bar that both clears a rung
            # and trips the trailing stop is resolved as the STOP. The stop is
            # protection and must not be pre-empted by a profit-taking rule; a
            # ladder that outranked it would book part of the position at a
            # rung and the rest at a stop the trade had already hit, which
            # reads as two better fills than the trade actually got.
            #
            # Tested against the CLOSE, never the high: a rung tagged only by a
            # bar's high is a rung reached intrabar at a price the strategy
            # could not act on.
            if ladder is not None and pos is not None:
                sell_q, used = PL.plan(pos["avg_px"], float(row["close"]),
                                       pos["qty"], pos["ladder_done"], ladder)
                if sell_q > 0:
                    px_out = float(row["close"]) - SLIPPAGE_TICKS * TICK
                    pos["realised"] += (px_out - pos["avg_px"]) * sell_q
                    pos["commission"] += order_cost(sell_q, px_out, True,
                                                    commission_plan)
                    pos["qty"] -= sell_q
                    pos["shares_traded"] += sell_q
                    pos["ladder_done"] += used
                    if pos["qty"] <= 0:
                        # The ladder took the last share. Close the trade here
                        # rather than leaving a zero-quantity position that the
                        # next bar's stop check would price against nothing.
                        gross = pos["realised"]
                        trades.append(Trade(
                            symbol="", date=str(session_date),
                            entry_time=str(pos["entry_t"]),
                            exit_time=str(rows.iloc[i][tcol]),
                            entry_price=round(pos["entry_px"], 4),
                            exit_price=round(px_out, 4),
                            qty=pos["init_qty"], reason="profit_ladder",
                            bars_held=i - pos["entry_i"],
                            gross=round(gross, 2),
                            commission=round(pos["commission"], 2),
                            net=round(gross - pos["commission"], 2),
                            cycles=pos["cycles"],
                            shares_traded=pos["shares_traded"],
                            adds=pos["adds"], max_qty=pos["max_qty"]))
                        pos = None
                        # MUST skip the rest of the bar. Everything below
                        # assumes a position -- peak maintenance dereferences
                        # pos on the very next statement -- and falling through
                        # raised TypeError rather than returning a wrong
                        # number, which is the one merciful way for this to go
                        # wrong.
                        continue

            # --- scale out / scale back in, only when enabled ---------------
            # Ordering is deliberate: the full stop above has already been
            # ruled out for this bar, so a partial sell here cannot be masking
            # a full exit. Selling is checked before buying back, so a bar that
            # both dips to the partial level and tags the previous high is
            # resolved as a sell -- against the position, per convention.
            if scale_out_pct and not pos["capped"]:
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
                        # Freeze the level the pullback began from. peak keeps
                        # updating, but it cannot rise while scaled out without
                        # first crossing this level and triggering the re-entry.
                        pos["rebuy_level"] = pos["peak"]
                elif pos["scaled_out"] and (
                        (trigger_level := (pos["rebuy_level"]
                                           if rebuy_trigger == "peak"
                                           else prev_high)) is not None) \
                        and float(row["high"]) >= trigger_level:
                    # A cap on how many times one trade may cycle. Uncapped,
                    # a 1% partial on 1-minute bars produced up to 105 cycles
                    # and 21,200 shares transacted in a SINGLE trade -- 210+
                    # orders on one pre-market small cap, which IB's ~60
                    # requests / 10 minutes would refuse outright and which
                    # exercises the bar-level fill model hundreds of times in
                    # a way it was never validated for.
                    #
                    # Hitting the cap does NOT close the trade: it retires the
                    # mechanic for the rest of it. The shares still held ride
                    # the full trail from here. Retiring it has to switch off
                    # SELLING as well as buying -- an earlier version only
                    # stopped the buy-back, which let the position sell itself
                    # down 50% on every subsequent pullback and never rebuy,
                    # bleeding to nothing on a trade that was never stopped out.
                    capped = (max_cycles is not None
                              and pos["cycles"] >= max_cycles)
                    if capped:
                        pos["capped"] = True
                    add = rebuy_qty if rebuy_qty is not None else pos["sold_qty"]
                    if max_position_shares is not None:
                        add = min(add, max_position_shares - pos["qty"])
                    if not capped and add >= 1:
                        # A break ABOVE the prior high is a stop-buy, and
                        # IBKR does not accept stop orders outside RTH. Live
                        # this is a marketable limit sent after the break is
                        # seen, so the fill is above the trigger, not at it --
                        # trader.py already crosses by LIMIT_CROSS_BPS = 20.
                        # Charging 0 bps here models a fill nobody can get.
                        px_in = (trigger_level * (1.0 + rebuy_slip_bps / 10_000.0)
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
                        pos["max_qty"] = max(pos["max_qty"], pos["qty"])
                    pos["scaled_out"] = False

            # --- SELL INTO STRENGTH, BUY BACK ON THE DIP --------------------
            # The MIRROR of the scale_out_pct mechanic above, and the
            # difference is the whole point rather than a variation.
            #
            #   scale_out_pct   sells on a PULLBACK, buys back on the RECOVERY
            #                   -> sells low, buys high. A structural cost, and
            #                      measured as one: negative at every setting
            #                      at the shipped trail.
            #   scale_up_pct    sells into STRENGTH, buys back on the DIP
            #                   -> sells high, buys low. A structural credit,
            #                      paid for in a different currency: the sold
            #                      shares are not there if price keeps running.
            #
            # Execution differs too, in this one's favour. The scale-out's
            # buy-back is a break above a level, so it is a marketable limit
            # that pays a ~40 bps chase. BOTH legs here rest: a limit sell
            # above the market and a limit buy below it. Nothing is chased.
            # The cost is queue position -- a resting limit at a level that is
            # only touched need not fill, especially pre-market -- which a bar
            # model cannot see. See the docstring's caveat.
            if scale_up_pct and scale_up_portion:
                if not pos["scaled_up"]:
                    sell_level = pos["up_ref"] * (1.0 + scale_up_pct / 100.0)
                    if float(row["high"]) >= sell_level:
                        sell_q = int(pos["qty"] * scale_up_portion / 100.0)
                        if 1 <= sell_q < pos["qty"]:
                            # A resting sell fills AT the limit, not through
                            # it. One tick against, per project convention.
                            px_out = sell_level - SLIPPAGE_TICKS * TICK
                            pos["realised"] += (px_out - pos["avg_px"]) * sell_q
                            pos["commission"] += order_cost(sell_q, px_out, True,
                                                            commission_plan)
                            pos["qty"] -= sell_q
                            pos["shares_traded"] += sell_q
                            pos["scaled_up"] = True
                            pos["up_sold_qty"] = sell_q
                            # The dip is measured from the peak reached AFTER
                            # the sell, so a stock that keeps running raises
                            # the bar for the buy-back rather than lowering it.
                            pos["up_peak"] = max(pos["peak"], float(row["high"]))
                            pos["up_sell_px"] = px_out
                else:
                    # WHERE THE DIP IS MEASURED FROM decides whether the round
                    # trip can lose, and it is not a detail:
                    #   "peak"  dip from the high reached AFTER the sell. If
                    #           price runs, the buy-back lands ABOVE the sell
                    #           -- measured, only 45% of these bought back
                    #           below their own sell price at +2%/-2%.
                    #   "sell"  a limit resting below the SELL price. The round
                    #           trip is then profitable by construction; what
                    #           it gives up is that a stock which never comes
                    #           back leaves the shares behind for good.
                    buy_level = ((pos["up_sell_px"] if rebuy_ref == "sell"
                                  else pos["up_peak"])
                                 * (1.0 - rebuy_dip_pct / 100.0))
                    if float(row["low"]) <= buy_level:
                        capped = (max_cycles is not None
                                  and pos["cycles"] >= max_cycles)
                        add = (rebuy_qty if rebuy_qty is not None
                               else pos["up_sold_qty"])
                        if max_position_shares is not None:
                            add = min(add, max_position_shares - pos["qty"])
                        if not capped and add >= 1:
                            px_in = buy_level + SLIPPAGE_TICKS * TICK
                            pos["avg_px"] = ((pos["avg_px"] * pos["qty"]
                                              + px_in * add) / (pos["qty"] + add))
                            pos["commission"] += order_cost(add, px_in, False,
                                                            commission_plan)
                            pos["qty"] += add
                            pos["shares_traded"] += add
                            pos["cycles"] += 1
                            pos["max_qty"] = max(pos["max_qty"], pos["qty"])
                            # The ladder resets to where we just bought, so the
                            # next sell is scale_up_pct above THAT, not above
                            # the original entry.
                            pos["up_ref"] = px_in
                        pos["scaled_up"] = False
                    elif float(row["high"]) > pos["up_peak"]:
                        pos["up_peak"] = float(row["high"])

            # --- PYRAMID: add on a recovered pullback, never sell -----------
            # Ben's second question, and a genuinely different mechanic from
            # the scale-out above: nothing is ever sold early, so there is no
            # sell-low / buy-back-higher cost. A pullback of
            # `pyramid_pullback_pct` off the peak ARMS the position; reclaiming
            # that same peak BUYS `pyramid_qty` more. Only the trail exits.
            #
            # The control this has to beat is NOT the 100-share baseline. It
            # is simply STARTING with the larger size, because on a dataset
            # with positive average trade P/L any extra size looks good. If
            # "100 then +100 on a recovered dip" only matches "200 from the
            # start", the timing is worth nothing and this is just leverage.
            if pyramid_qty:
                arm = pos["peak"] * (1.0 - pyramid_pullback_pct / 100.0)
                if not pos["armed"] and float(row["low"]) <= arm:
                    pos["armed"] = True
                    pos["arm_level"] = pos["peak"]
                elif pos["armed"] and pos["arm_level"] is not None \
                        and float(row["high"]) >= pos["arm_level"]:
                    add = pyramid_qty
                    if max_position_shares is not None:
                        add = min(add, max_position_shares - pos["qty"])
                    if max_adds is not None and pos["adds"] >= max_adds:
                        add = 0
                    if add >= 1:
                        # Same marketable-limit chase as the scale-out's
                        # buy-back: this is a break above a level, which IBKR
                        # will not take as a stop order pre-market.
                        px_in = (pos["arm_level"] * (1.0 + rebuy_slip_bps / 10_000.0)
                                 + SLIPPAGE_TICKS * TICK)
                        pos["avg_px"] = ((pos["avg_px"] * pos["qty"]
                                          + px_in * add) / (pos["qty"] + add))
                        pos["commission"] += order_cost(add, px_in, False,
                                                        commission_plan)
                        pos["qty"] += add
                        pos["shares_traded"] += add
                        pos["adds"] += 1
                        pos["max_qty"] = max(pos["max_qty"], pos["qty"])
                    pos["armed"] = False

            pos["peak"] = max(pos["peak"], float(row["high"]))

        prev_high = float(row["high"])

    return trades
