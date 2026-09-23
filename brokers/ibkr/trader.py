#!/usr/bin/env python3
"""
MCL (Momentum Confluence Long) — IBKR pre-market paper execution layer
========================================================================

IB-specific execution: order placement, fill logging, position/watchlist
state, the tradability probe. Strategy logic — indicators, entry/exit signal
evaluation, position sizing — lives in strategy/mcl/mcl.py and is not duplicated
here; see claude/repo_reorg_and_github_plan.md STEP 2 for why this file was
split out of the old mcl_paper_trader.py.

Invoked through `main.py --mode paper|dry --strategy mcl`, which also takes
the session lock (common/session_lock.py) for the duration. Running this
module directly still works but bypasses that lock, so a scheduled backtest
would not know a session was live and would contend with it for IB's
account-wide request budget.

Mirrors the V7 Pine strategy and executes it against an IBKR **PAPER**
account using marketable limit orders, which is the only order type IBKR
accepts for US stocks outside regular trading hours.

The point of this script is NOT to make money. It is to measure the gap
between the backtest's assumed fills (bar close, 1 tick slippage) and what
actually fills pre-market. Every signal is logged with the live bid/ask at
signal time, the limit sent, and the realised fill or no-fill.

SAFETY
------
This refuses to run against a live account. It checks both:
  1. the socket port is a known PAPER port, and
  2. the managed account id starts with "DU" (IBKR paper accounts).
Either check failing aborts before any market data or order is requested.

Strategy (must stay in sync with strategy/mcl/mcl.py and the Pine V7 script)
-------------------------------------------------------------------------
Session : 04:00-09:30 ET, flat at 09:30
Entry   : MACD > signal AND MACD > 0
          AND MFI rising      (mfi  > mfi[3])
          AND RSI rising      (rsi  > rsi[3])
          AND volume >= 3x previous bar
          AND previous bar volume >= 50% of trailing 60-bar average (lagged 1)
Exit    : after an apex, ANY of MACD / MFI / RSI turning down
          (falling vs 3 bars ago AND its 20-bar high is >= 1 bar behind)
          OR price <= 5% below the highest price since entry
          OR 09:30 window close
Size    : min(100 shares, 40% of equity / price)

Usage
-----
    python main.py --mode paper --strategy mcl
    python main.py --mode dry   --strategy mcl

--dry-run logs signals and computes intended orders but places none. Run this
first, every time, before letting it place anything.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import math
import os
import re
import signal as _signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

try:
    from ib_async import IB, Stock, LimitOrder, util
except ImportError:  # pragma: no cover
    sys.exit("ib_async not installed.  pip install ib_async pandas")

from common import notify, ui_bridge
from common import strategy_adapter as SA
from common.commissions import order_cost
from strategy.mcl import mcl as S
from strategy.mcl.mcl import (  # re-exported so tests/tools can do trader.evaluate(...)
    Signals,
    evaluate_last_bar as evaluate,
    MIN_BARS_REQUIRED,
)

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ET = ZoneInfo("America/New_York")

# Paper ports only.  7496 / 4001 are LIVE and are deliberately excluded.
PAPER_PORTS = {7497: "TWS paper", 4002: "IB Gateway paper"}
LIVE_PORTS = {7496: "TWS LIVE", 4001: "IB Gateway LIVE"}

# Signal parameters (MACD/MFI/RSI lengths, trail %, sizing caps, the session
# window) now live in strategy/mcl/mcl.py as the single source of truth — see
# S.TRAIL_PCT, S.SESSION_START/S.SESSION_END, S.size_for() below. What stays
# here is execution-only configuration: order placement, IB pacing, and the
# tradability probe, none of which the backtest needs.

# Execution
LIMIT_CROSS_BPS = 20        # how far through the touch to price the limit (20bps)
ORDER_TIMEOUT_S = 20        # cancel and record a no-fill after this long

# AN EXIT DOES NOT WAIT OUT THE TIMEOUT WHEN ITS LIMIT CAN NO LONGER FILL.
#
# CRBP, 2026-09-14. The trail fired at 07:02:10 with the bid at 9.08 and the
# order went out at 9.06. It then sat for the full ORDER_TIMEOUT_S while the
# stock fell to 5.28, and the next attempt did not leave until 07:02:31. The
# position was unprotected for twenty seconds during a 42% collapse, and the
# round trip cost $241.37 -- 46% of that week's two-day loss.
#
# The limit was unfillable within about a second of being placed. A marketable
# SELL limit fills against the BID; once the bid is below the limit there is no
# counterparty at the touch and waiting is pure loss. So an exit order is
# abandoned and re-priced the moment its own quote says it cannot fill.
#
# ENTRIES KEEP THEIR PATIENCE. Twenty seconds of waiting is how a buy gets a
# good fill, and a missed entry costs the signal, not the position.
#
# The poll count is a DEBOUNCE ON THE FEED -- two consecutive reads, half a
# second -- not a judgement about the market. Nothing here is a threshold on
# price.
EXIT_ABANDON_POLLS = 2

# THE MEDS GHOST, 2026-09-16. The abandon path above broke out of its poll
# loop, read `trade.fills` in the same instant, saw nothing, cancelled, and
# recorded NO_FILL_ABANDONED. The fill had landed at IB in between. The trader
# kept 100 shares on its books that the account no longer held and sent 850+
# more SELLs into a flat account over three and a half hours -- every one a
# short sale had it filled. An order's outcome is not known until IB says the
# order is finished, so after ANY cancel the trader now waits for that, bounded
# by this. Past the bound the outcome is UNKNOWN, and unknown is handled by
# asking IB what the account actually holds before anything else is sent.
CANCEL_CONFIRM_S = 3.0
# After this many consecutive exit attempts that did not fill, alert once and
# slow down. Not stop: by then IB has confirmed the shares are really held
# (every retry reconciles first), and a real position that cannot fill still
# needs managing -- at a cadence that is not 850 orders a morning.
MAX_EXIT_ATTEMPTS = 5
EXIT_RETRY_BACKOFF_S = 30.0

# THE CRML SHORT, 2026-09-21 (W02-0014). MCL and MC5 each held 100 CRML at
# 09:30, so the ACCOUNT held 200. MCL's window_close SELL went ORDER_UNKNOWN at
# 09:30:02 and filled after the cancel wait. The re-send check above asked IB
# what the ACCOUNT held, got MC5's 100, and sold again at 09:30:06; MC5's own
# first-attempt exit sold 100 more at 09:30:07 without asking anyone. 300 sold
# against 200 bought: short 100, found by Ben the next morning because the
# startup guard refused to trade. Three rules close it, each tested in
# tests/brokers/ibkr/test_double_sell_short.py:
#
#   S1  An ORDER_UNKNOWN order is remembered, and before anything is re-sent
#       its own fills are read. A fill there IS the exit.
#   S2  "What IB holds" means what IB holds FOR THIS STRATEGY: the account
#       position less the shares every other strategy's book holds in the
#       same symbol. Two books in one name must not vouch for each other.
#   S3  No SELL leaves -- first attempt or re-send -- for more than the
#       account holds less SELLs already working. A long-only book cannot go
#       short, whatever its own count says.
#
# S3 has ONE exemption, and it is the reason first attempts used to trust
# local state: IB's position push can lag a fresh ENTRY fill by a moment, and
# refusing a legitimate exit then would leave a real position unmanaged. That
# lag is a property of the first seconds after an entry, not of a position
# fifty minutes old (MC5's CRML). So a first attempt within this many seconds
# of its entry still trusts local state; after it, S3 applies to every SELL.
POSITION_PUSH_LAG_S = 15.0

# IBKR STATES THE ACCEPTABLE LIMIT IN THE TEXT OF THE REJECTION.
#
#   Error 202: Order Canceled - reason:We cannot accept an order at a limit
#   price at or more aggressive than 6.31944. Please submit your order using
#   a limit price that is closer to the current market
#
# CRBP 2026-09-14 took three of these in consecutive seconds -- 5.26, then
# 5.52, then 6.04 -- while holding a position in a stock that was collapsing.
# The broker had already supplied the answer on the first one and nothing
# read it.
#
# The band is consumed ONCE, by the next order on that symbol, and then
# cleared. It is a fact about the market a second ago, not a setting: keeping
# it would mean clamping a later order to a price the market has left.
BAND_RE = re.compile(r"more aggressive than\s*([0-9]*\.?[0-9]+)")

# A CANCEL THE TRADER SENDS COMES BACK AS A 202 TOO, 2026-09-17.
#
#   Error 202: Order Canceled - reason:
#
# with nothing after the colon. Once `_settle` waited for the terminal status
# (the ghost fix), a self-sent cancel returned `Cancelled` plus that echo and
# fell into the "IB never worked it" branch: six REJECTED rows on 09-17 that
# were four abandoned exits and two timed-out entries, and NO_FILL_ABANDONED /
# NO_FILL_CANCELLED stopped appearing at all. The trader now remembers the
# order ids it cancelled itself; an echo with a blank reason on one of those
# is the no-fill it always was. An echo that CARRIES a reason ("We cannot
# accept an order at a limit price...") is IB refusing, whoever sent the
# cancel, and stays a rejection.
CANCEL_ECHO_RE = re.compile(r"Order Cancel(?:l)?ed\s*-\s*reason:\s*$")

# A BUY IS NOT SENT INTO A QUOTE THAT HAS LEFT ITS REFERENCE, 2026-09-17.
#
# The engine buys the signal bar at its close plus a tick. CRBP (09-14) was
# bought 6.6% BELOW its reference into a collapse; RETO (09-17) 34.5% ABOVE
# it, minutes after the bar closed. Neither is a worse fill of the modelled
# trade -- each is a trade the backtest does not contain. The threshold is the
# one the 09-14/15 review wrote down before the 09-17 trades existed, and it
# is registered in docs/research/REGISTERED_drift_guard.md; changing it is a
# new registration. Measured on the ASK, the side a marketable BUY crosses,
# absolute, either direction. Exits are never guarded.
DRIFT_GUARD_PCT = 6.0


def is_cancel_echo(why: str, status: str) -> bool:
    """True when `why` says nothing beyond 'the order was cancelled'."""
    w = (why or "").strip()
    return not w or w == status or bool(CANCEL_ECHO_RE.search(w))

# Commission for the round-trip P/L recorded in the fill log. This is a
# REPORTING figure only -- it is not consulted when deciding or pricing an
# order -- but it is not cosmetic either: common/friction.py derives measured
# slippage from these rows, and friction is currently the number the whole
# project turns on.
#
# It used to be a flat $2.00 regardless of share count while the backtests
# charged a per-share rate, so the two P/L calculations disagreed by
# construction. Both now call common/commissions.py with the same plan, priced
# per leg at the price that leg actually traded at. On MCL's 100 shares the
# old constant overstated cost by about $1.30 a round trip, which fed straight
# into the friction estimate.
COMMISSION_PLAN = S.COMMISSION_PLAN

# Read from the strategy module rather than written here, so this trader can
# never label its fills with another strategy's name.
STRATEGY_NAME = getattr(S, "STRATEGY_NAME", "?")

# Loop cadence.
#
# IB paces historical-data requests hard: no identical request inside 15s, and
# no more than 60 requests in any 10-minute window ACROSS ALL CONTRACTS. Polling
# reqHistoricalData on a fast loop trips both and IB starts silently refusing.
# So bars are fetched at most ONCE PER MINUTE PER SYMBOL (they are 1-minute bars
# — nothing changes in between), which is 10 requests / 10 min / symbol and
# leaves headroom for ~6 names.
#
# The trailing stop does NOT need bars. It needs the live price, which arrives
# on the streaming quote for free. So it runs on the fast loop at no API cost.

# IBKR refuses to open positions in some low-float small caps ("No Opening
# Trades: Small Cap, Subject to Compliance Restriction", error 201). That is
# exactly the population this screen selects, so it must be detected once and
# the name removed — not rediscovered on every signal.
INELIGIBLE_MARKERS = (
    "no trading permission",
    "customer ineligible",
    "ineligibilityreasons",
    "ineligibility reasons",
    "no opening trades",
    "compliance restriction",
)

# How much 1-minute history to request per symbol.
#
# MEASURED 2026-09-09 with common/history_probe.py, at 06:22 ET, on four live
# watchlist names (YMAT, FGL, SUNE, DPU):
#
#     "1 D"    ~143 bars, 04:00 -> 06:22   i.e. THIS SESSION SO FAR, only
#     "2 D"   ~1100 bars, 26 hours
#
# So "1 D" provides NO warm-up at all at the open -- it starts at 04:00, the
# same minute the strategy does. Every backtest in this project computes
# indicators over the whole three-day cached frame and only then restricts to
# the session date, so every backtest figure assumes a warm start. Live has
# been starting cold this entire time, and nothing said so.
#
# What that cost, per strategy:
#   MCL needs 40 one-minute bars   -> blind until ~04:40, 10.8% of its
#                                     backtested trades
#   MC5 needs 40 FIVE-minute bars  -> blind until ~07:20, 45.9% of MC5's
#
# The duration belongs to the FEED, not to a strategy: SymbolFeed shares one
# bar cache per symbol precisely so two strategies cost one request, so there
# is one duration and it has to satisfy the hungriest of them. "2 D" covers
# both with room to spare and costs no extra REQUESTS -- IB paces on request
# count, and this is still one per symbol per minute. It costs response size.
HISTORY_DURATION = "2 D"

PROBE_TIMEOUT_S = 6         # tradability whatIf probe; normally answers in <1s
LOOP_SLEEP_S = 1.0          # fast loop: trailing stop, off streaming quotes
BAR_MIN_INTERVAL_S = 20.0   # hard floor between history requests per symbol
# How far past a bar's close we insist on being before calling it closed.
# Guards the ONE direction that costs money: a local clock running fast would
# judge a still-forming bar finished and hand a partial bar to a strategy.
# A floor, not a proof -- it buys exactly this many seconds against skew, and
# common/bar_freshness.py reports IB's clock against ours so the figure can be
# set from a measurement rather than from this comment.
BAR_CLOSE_SKEW_S = 2.0
MAX_SYMBOLS_SAFE = 6        # beyond this, 1 req/min/symbol approaches IB's cap
EMPTY_WARN_S = 120          # how often to repeat the 'watching nothing' warning

# Most positions that may be open AT ONCE, across all symbols.
#
# Until 2026-09-05 there was no such limit anywhere. MAX_SYMBOLS_SAFE above
# reads like one but is not: it only WARNS about watchlist size, for IB request
# pacing, and never gates an entry. The entry path checked st.position (this
# symbol), retired, session, bar-dedupe and size -- never the total across
# symbols. Nothing bounded portfolio exposure.
#
# That matters more than it looks because size_for() bills every position
# against the FULL account equity (MAX_EQUITY_PCT of it), and self.equity is
# read once at startup and never decremented as positions open. So N concurrent
# positions commit N x 40% of equity, not 40% between them.
#
# Empirically it has been benign -- over 373 cached sessions the most ever open
# at once was 4 (once), 3 on three days, and peak simultaneous notional reached
# 69% of net liq without ever exceeding it. This is closing an unbounded hole,
# not stopping an observed bleed.
#
# 2 is chosen from claude/mcl_robustness_analysis.md: caps of 1/2/3/6 retain
# 79.0% / 99.0% / 100.4% / 100% of backtest P/L. Cap 2 costs ~1% and removes
# the tail. Cap 3 scoring above unconstrained is one skipped loser, i.e. noise.
#
# Enforced by counting open positions in the entry path. No reservation or lock
# is needed: run() iterates symbols sequentially and awaits each order to
# completion before moving to the next, so two entries cannot be in flight at
# the same time. If that loop is ever made concurrent, this needs a reservation.
MAX_CONCURRENT_POSITIONS = 2

# WHAT THE CAP COUNTS -- added 2026-09-23 (W02-0015), Ben, in his words: "adjust
# the trader mechanics to allow each strategy a max position of 3, rather than
# a total pool of 3 ... it seems like MC5 is dragging down MCL."
#
#   account   (the default, unchanged) -- one pool shared by every strategy in
#             the process. The earlier strategy in --strategy order takes the
#             last free slot.
#   strategy  -- each strategy has its OWN pool of max_positions. With two
#             strategies at cap 3 that is up to 6 positions at once, and MC5
#             can no longer crowd MCL out (or the reverse).
#
# The account-level worry the shared pool was written for still holds and is
# why the default did not move: size_for() bills every position against the
# full startup equity. At 100 shares and the $2-20 band a position is at most
# $2,000 of notional, so 6 open is at most $12,000 against ~$22k net liq --
# inside the account, but no longer "at most 3 x". Chosen per session, on the
# command line, and written into the CONFIG row and every declined-entry row.
CAP_SCOPES = ("account", "strategy")
DEFAULT_CAP_SCOPE = "account"

LOG = logging.getLogger("mcl")


# --------------------------------------------------------------------------
# Order-placement mechanics — IB-specific, not strategy logic
# --------------------------------------------------------------------------

def round_to_tick(price: float, action: str, min_tick: float = 0.0) -> float:
    """Round a limit price to a legal tick, staying marketable.

    IB rejects a price off the minimum variation with error 110 and cancels the
    order — so 5.3206 on a $5 stock never reaches the book.

    Two constraints apply and BOTH must hold, so take whichever is coarser:

    * SEC Rule 612 — $0.01 at or above $1.00, $0.0001 below it. This depends on
      the CURRENT PRICE, not the contract.
    * The contract's own minTick from IB, which can be coarser still.

    IB's minTick is the contract's floor, not the increment in force right now:
    a stock that may trade below $1 reports 0.0001 even while quoted at $1.60.
    Trusting it alone produces a sub-penny limit and an instant rejection.

    Rounds in the aggressive direction: a BUY limit rounds UP, a SELL limit rounds
    DOWN, so the order stays at least as marketable as intended rather than
    slipping behind the touch by a tick.
    """
    rule612 = 0.01 if price >= 1.0 else 0.0001
    tick = max(min_tick, rule612) if min_tick > 0 else rule612
    steps = price / tick
    # up for a buy, down for a sell; the 1e-9 absorbs float representation error
    steps = math.ceil(steps - 1e-9) if action == "BUY" else math.floor(steps + 1e-9)
    # tick can be 0.0001 or finer, so keep enough decimals to represent it exactly
    return round(steps * tick, 6)


# --------------------------------------------------------------------------
# Position state
# --------------------------------------------------------------------------

@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    entry_time: datetime
    peak: float
    # Per POSITION, not read from a module at exit time. The default is MCL's
    # so that every existing caller -- the suite that is this refactor's
    # control -- behaves exactly as before; the live entry path passes the
    # value explicitly, and stage 4 removes the default once every caller is
    # strategy-aware.
    trail_pct: float = S.TRAIL_PCT
    exiting: str | None = None      # sticky: once we decide to exit, keep trying
    exit_attempts: int = 0
    # Set once the exit has failed MAX_EXIT_ATTEMPTS times with IB confirming
    # the shares are still held. The portal shows it; the alert fires once.
    needs_attention: bool = False
    last_retry_at: float = 0.0      # monotonic; throttles retries past the cap
    # The last closed bar whose high the peak has consumed. While an order is
    # waiting (up to 20s) bars close unseen; the next feed reads every bar
    # after this one rather than only the newest.
    last_bar_seen: datetime | None = None
    def trail_level(self) -> float:
        return self.peak * (1.0 - self.trail_pct / 100.0)


@dataclass
class SymbolFeed:
    """Everything about a SYMBOL that must not be duplicated per strategy.

    Split out of SymbolState 2026-09-09, stage 3 of
    claude/multi_strategy_trader_spec.md. Both of these are scarce:

      * qualifying a contract is an IB request, and IB paces them account-wide
        at ~60 per 10 minutes -- signalling the limit by returning EMPTY LISTS
        rather than errors, so exhausting it makes a strategy go blind without
        saying so;
      * a streaming market-data line is one of ~100 an account carries.

    Two strategies watching WYHG want one of each, not two. `blocked` lives
    here too: IBKR refusing to trade a name is a fact about the name, and
    rediscovering it per strategy would spend a rejected order to learn it
    twice.

    The bar cache is here for the same reason and one more: MC5 and MCL both
    consume 1-MINUTE bars (MC5 resamples its own), so one fetch serves both. A
    per-strategy cache would double the history requests for identical data.
    """
    symbol: str
    contract: object = None
    ticker: object = None
    min_tick: float = 0.0           # from IB ContractDetails; 0 = fall back on price
    blocked: bool = False           # set after a hard error; stops trading this name
    bars_df: object = None          # cached history (see bars(): IB paces requests)
    bars_minute: tuple | None = None
    bars_fetched_at: float = 0.0
    # (action, price) from IB's own 202 rejection -- see BAND_RE. It lives on
    # the FEED, not the state: the band is a fact about the contract at the
    # broker, and both strategies watching this name hit the same one.
    price_band: tuple | None = None


# The shared fields, delegated below. Named once so the property pairs and the
# test that checks them cannot drift apart.
_FEED_FIELDS = ("contract", "ticker", "min_tick", "blocked",
                "bars_df", "bars_minute", "bars_fetched_at", "price_band")


@dataclass
class SymbolState:
    """One strategy's view of one symbol.

    Holds only what is per-strategy: the position, which bar has been
    evaluated, and whether this strategy still wants the name. Everything
    shared reaches it through `feed`, and is exposed as a property of the same
    name so every existing caller -- including the whole test suite, which is
    the control for this refactor -- keeps working unchanged.
    """
    symbol: str
    feed: SymbolFeed | None = None
    # The StrategyAdapter this state belongs to. Required in the live path;
    # None only in a caller that predates multi-strategy, which step_symbol
    # refuses loudly rather than defaulting -- a state silently attributed to
    # the wrong strategy is the whole class of defect this stage exists to
    # prevent.
    strategy: object = None
    position: Position | None = None
    last_bar_ts: datetime | None = None
    retired: bool = False           # removed from the watchlist; no new entries
    # An order whose outcome IB never confirmed within CANCEL_CONFIRM_S. Local
    # state may be wrong in either direction until the next exit reconciles
    # against IB's own position -- and nothing is sent until it has.
    unknown_order: bool = False
    # The Trade whose outcome was unknown (S1). ib_async keeps updating it
    # after the trader stopped waiting, so a fill that landed late shows up
    # here -- read it before anything is re-sent.
    unknown_trade: object = None
    # When this strategy last released a position on this symbol, ET. An
    # entry signal is taken only from a bar that OPENED at or after this --
    # see bar_after_exit.
    last_exit_et: datetime | None = None

    def __post_init__(self):
        if self.feed is None:
            self.feed = SymbolFeed(symbol=self.symbol)


def _delegate(name: str):
    return property(lambda self: getattr(self.feed, name),
                    lambda self, v: setattr(self.feed, name, v))


for _f in _FEED_FIELDS:
    setattr(SymbolState, _f, _delegate(_f))
del _f


def drop_forming_bar(df: "pd.DataFrame", now: datetime,
                     minutes: int = 1) -> "pd.DataFrame":
    """Hand back only bars that have closed, judged by the clock.

    Every strategy here acts on a CLOSED bar, so the minute in progress must
    not reach evaluate_last_bar: acting on a partial bar is H1 in
    claude/multi_strategy_trader_spec.md and shows up in a backtest as an edge
    that does not exist live.

    This used to be an unconditional `df.iloc[:-1]`, and it embedded an
    ASSUMPTION about IB that nothing could check from in here -- that the
    response always includes the forming minute. `common/bar_freshness.py`
    measured it on BNC on 2026-09-16 and the assumption holds 10 times in 11.
    The eleventh:

        06:04:05  raw last 06:03  -> acts on 06:02  (closed, raw 65s)

    The 06:03 bar had already closed, the trim threw it away, and the strategy
    acted a full extra minute late. A minute with no print produces no bar --
    the mechanism `mc5.last_closed_bucket` already documents -- so on a thin
    name the response often ends with a bar that is already finished. Whether
    IB includes the forming minute is not a property of IB. It is a property of
    the moment you ask.

    So the assumption is replaced by a measurement: whether the bar labelled T
    has closed IS decidable in here, given the time. `now` is REQUIRED and has
    no default, because a default preserving the old behaviour would let a
    caller that forgot it get the defect back in silence.

    `BAR_CLOSE_SKEW_S` is the guard on the one direction that hurts: a local
    clock running fast would call a bar closed with a second still to run. It
    buys that many seconds and no more, which is why the probe now reports IB's
    own clock against ours instead of this constant being an opinion.

    See docs/research/REGISTERED_bar_trim.md.
    """
    if df is None or len(df) <= 1:
        return df
    if now.tzinfo is None:
        raise ValueError(
            "drop_forming_bar needs an aware `now`; a naive one cannot be "
            "compared with a bar label without guessing a zone, and the guess "
            "decides whether a forming bar reaches a strategy.")
    closed_at = df.index[-1] + pd.Timedelta(minutes=minutes)
    if pd.Timestamp(now) >= closed_at + pd.Timedelta(seconds=BAR_CLOSE_SKEW_S):
        return df                      # the last bar has ended; it is real data
    return df.iloc[:-1]


def bar_session_ok(signal_ts, now_et: datetime,
                   session_start: dtime, session_end: dtime) -> tuple[bool, str]:
    """Whether the bar a signal was COMPUTED ON belongs to the session running now.

    THE DEFECT THIS EXISTS FOR, found live 2026-09-16.

    `MCLPaperTrader.in_session` asks what time it is. Nothing asked what time
    the BAR was. At 04:00:10 the frame IB hands back still ends with
    yesterday's 19:59 bar -- nothing has printed today yet -- so the strategy
    evaluated a fourteen-hour-old bar, the dedupe saw a timestamp it had never
    seen before and let it through, and the trader bought at the open on a
    signal from last night's close. Two checks that look like one check: a
    CLOCK inside the window is not a BAR inside the window.

    That is this project's own shape `a check placed one step short of the
    thing it protects`. The clock gate protects "are we trading now"; what
    needed protecting was "is this signal about now".

    The rule is TODAY and inside [session_start, session_end) -- which is
    exactly the `in_sess` mask of `strategy/mcl/mcl.backtest_session`: same
    date equality, same half-open interval, same left-labelled bars.
    tests/brokers/ibkr/test_stale_signal_bar.py runs both over one frame and
    asserts they agree bar for bar, so the live path and the engine cannot go
    back to trading two different rules.

    `signal_ts` is the value the DEDUPE used, not a second read of `sig.bar_ts`.
    A gate that works out "which bar" independently of the guard standing next
    to it is two values that look comparable and are not.

    The window comes from the ADAPTER, never a module constant: MCL and MC5
    share 04:00-09:30 so today every answer is the same, and VW9 runs to 20:00
    and will not.
    """
    if signal_ts is None:
        return False, "signal carries no bar timestamp"
    ts = pd.Timestamp(signal_ts)
    if ts.tz is None:
        # Every live frame is tz-aware: _fetch_bars parses with utc=True, and
        # test_stale_signal_bar pins that. A naive stamp therefore comes from a
        # caller this function has never seen, and guessing its zone is a
        # five-hour error in whichever direction the guess fell. Refusing is
        # the only answer that cannot be wrong in the permissive direction.
        return False, f"bar {ts} carries no timezone"
    bar_et = ts.tz_convert(ET)
    if bar_et.date() != now_et.date():
        return False, (f"bar {bar_et:%Y-%m-%d %H:%M} ET is not today "
                       f"({now_et:%Y-%m-%d})")
    if not (session_start <= bar_et.time() < session_end):
        return False, (f"bar {bar_et:%H:%M} ET outside "
                       f"{session_start:%H:%M}-{session_end:%H:%M}")
    return True, ""


def parse_watchlist(path: Path) -> list[str]:
    """One ticker per line. Blank lines and # comments ignored, including
    trailing comments — `UPC  # added 05:55, rank 1` yields `UPC`, so the file
    can carry provenance for each pick (the scanner writes it that way)."""
    if not path.exists():
        return []
    out, seen = [], set()
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.split("#", 1)[0].strip().upper()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# --------------------------------------------------------------------------
# Fill-gap logger — the actual deliverable of this exercise
# --------------------------------------------------------------------------

FIELDS = [
    "ts_et",
    # WHICH strategy. One file, not one per strategy: the IB account is shared,
    # so only a single ledger can be reconciled against it -- and a per-strategy
    # file cannot show that two of them were competing for the same cap.
    "strategy",
    "symbol", "action", "reason",
    "ref_close",            # the price this order was measured against
    "ref_kind",             # WHICH price that is -- see _exit_reference()
    "bid", "ask", "spread", "spread_pct",
    "limit_sent", "qty",
    "fill_price", "filled_qty", "status",
    "slippage_vs_ref",      # fill - ref_close  (negative = worse for a buy)
                            # ON A SELL, only meaningful with ref_kind set:
                            # rows written before 2026-09-09 used the ENTRY
                            # price as the reference on every fast-path exit,
                            # so their "slippage" is the trade's whole P/L.
    "seconds_to_fill",
    # -- round-trip result, written on the SELL row only --------------------
    "entry_price", "exit_price", "trade_pnl", "trade_pct", "hold_minutes",
    # THE DETAIL BEHIND THE STATUS, not evidence of a rejection. This comment
    # used to say "populated only when IB refused the order outright" and that
    # stopped being true the moment SKIPPED_PAUSED, SKIPPED_CONCURRENCY_CAP,
    # SKIPPED_PRICE_BAND, SKIPPED_STALE_BAR, SKIPPED_BAR_BEFORE_EXIT and
    # SKIPPED_DRIFT started writing their own reasons here. A reader that
    # treats a non-empty reject_reason as "this was rejected" is wrong on six
    # row shapes already; `status` is the field that says what happened.
    "reject_reason",
    "macd", "macd_sig", "mfi", "rsi", "vol", "prev_vol", "trail_avg",
    # -- the trail this trade is running, in percent -------------------------
    # NOT the same thing as trail_avg above, which is a volume average. This is
    # the trailing-stop width, and it is here because the portal can change it
    # mid-session: without the column, a session where someone moved the trail
    # from a browser produces rows indistinguishable from rows taken at the
    # default, in the one ledger every downstream reader uses. Anything later
    # comparing the live record against a 5% backtest would then be comparing
    # two populations under one label.
    #
    # It cannot be reconstructed afterwards -- the rows that need it are the
    # ones written during the experiment.
    "trail_pct",
    # -- HOW FAR THE MARKET HAD ALREADY MOVED WHEN THE ORDER WENT OUT --------
    # (mid at order / ref_close - 1), in percent.
    #
    # `slippage_vs_ref` alone called the worst trade in the book a good fill.
    # CRBP 2026-09-14: the decision was priced off 9.75, the bid on the SAME
    # ROW was 9.11, the buy filled at 9.16 -- and slippage_vs_ref recorded
    # +0.59, a fifty-nine cent FAVOURABLE fill, on a round trip that lost
    # $241.37 in forty-two seconds.
    #
    # A buy that fills far BELOW its reference is not a bargain. It is the
    # reference being stale, and the two readings are indistinguishable
    # without this column beside it. Every number needed was already on the
    # row; nothing computed it.
    #
    # It is a DIAGNOSTIC, not a filter. Tested across 138 live round trips,
    # drift does not separate outcomes -- quartiles are non-monotone and the
    # whole extreme-bucket effect is that one trade.
    "ref_drift_pct",
]


def clamp_to_band(limit: float, action: str, edge: float,
                  min_tick: float) -> float:
    """The limit moved onto the acceptable side of IB's stated band.

    "More aggressive" is HIGHER for a buy and LOWER for a sell, and the number
    IB quotes is ITSELF refused ("at or more aggressive than"), so the limit
    has to land a tick past it rather than on it.

    A limit already inside the band is returned unchanged: the clamp exists to
    turn a rejection into a fill, never to make an acceptable order worse.

    THIS IS A FUNCTION because the first version lived inline and its tests
    reimplemented the arithmetic beside it -- three mutations of the real code
    survived a green suite. A guard tested by a copy of itself is not tested.
    """
    tick = min_tick or 0.01
    if action == "BUY" and limit >= edge:
        return round_to_tick(edge - tick, action, min_tick)
    if action == "SELL" and limit <= edge:
        return round_to_tick(edge + tick, action, min_tick)
    return limit


def bar_after_exit(signal_ts, last_exit_et) -> tuple[bool, str]:
    """Whether the signal bar OPENED after this strategy's last exit on the name.

    THE DEFECT THIS EXISTS FOR, found live 2026-09-17.

    While a position is open the entry path is not reached, so the bars that
    close during it are never marked evaluated. The moment the position is
    released, the next poll evaluates the last closed bar -- which closed
    while the old position was still on -- and buys it at the CURRENT quote.
    Seven re-entries within five seconds of the same strategy's own exit on
    09-17, (82.62); the worst was MC5 RETO, sold 3.30 at 08:24:24 and bought
    3.29 at 08:24:25 on a five-minute bar that had closed at 2.45.

    The engine cannot do that. `backtest_session` reads each bar once, in
    order: a signal on a bar it holds a position through is consumed, the
    bar the exit is booked on is never an entry bar, and the earliest
    re-entry is the NEXT bar's own signal at that bar's close. Live, the exit
    fires on a quote INSIDE a bar; that bar is the engine's exit bar. So the
    rule that matches the engine is on the bar's OPEN, not its close: an
    entry signal is taken only from a bar that opened at or after the exit.
    Bars are left-labelled, so the open is the stamp itself. (A first
    version compared the bar's close; the engine parity test in
    tests/brokers/ibkr/test_bar_after_exit.py is what caught it.)

    No exit on record means no constraint.
    """
    if last_exit_et is None:
        return True, ""
    ts = pd.Timestamp(signal_ts)
    if ts.tz is None:
        return False, "signal bar carries a naive timestamp"
    ex = pd.Timestamp(last_exit_et)
    if ts >= ex:
        return True, ""
    return False, (f"bar {ts.tz_convert(ET):%H:%M} opened before this strategy's "
                   f"exit at {ex.tz_convert(ET):%H:%M:%S}")


def ask_drift_pct(ask: float, ref_close: float) -> float:
    """(ask / ref_close - 1) * 100, NaN when either side is missing.

    The guard's own reading. It is NOT `ref_drift`, which is on the mid and
    is the fill-log column; a BUY pays the ask, so the guard reads the ask.
    NaN means "no quote", which is marketable_limit's NO_QUOTE case and not a
    drift -- the guard admits it rather than refusing it under the wrong name.
    """
    if ask != ask or ask <= 0 or not ref_close or ref_close != ref_close:
        return float("nan")
    return (ask / ref_close - 1.0) * 100.0


def drift_guard_ok(ask: float, ref_close: float,
                   limit_pct: float = DRIFT_GUARD_PCT) -> tuple[bool, str]:
    """Whether a BUY may be placed: |drift| <= limit_pct, or no quote at all."""
    d = ask_drift_pct(ask, ref_close)
    if d != d:
        return True, ""
    # Rounded before the compare: 5.30 / 5.00 is 6.000000000000005 in float,
    # and "at the threshold" is admitted by the registration.
    if round(abs(d), 6) <= limit_pct:
        return True, ""
    return False, (f"ask {ask:.4f} is {d:+.1f}% from the signal close "
                   f"{ref_close:.4f}; guard {limit_pct:.1f}%")


def ref_drift(bid: float, ask: float, ref_close: float) -> float:
    """(mid / ref_close - 1) * 100, or NaN when it cannot be computed.

    NaN rather than 0.0 when a side of the book is missing: a drift of zero
    means "the market is exactly where the decision was priced", which is a
    strong and specific claim, and it is not the same statement as "there was
    no quote". Writing 0.0 here would be the shape this column exists to fix.
    """
    if bid != bid or ask != ask or not ref_close or ref_close != ref_close:
        return float("nan")
    return ((bid + ask) / 2.0 / ref_close - 1.0) * 100.0


class FillLog:
    def __init__(self, path: Path):
        self.path = path
        # var/fills/ is gitignored, so it does not exist on a fresh clone and
        # opening the log for append would fail before a single order is placed.
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()

        # If a log from an earlier run of an OLDER version is sitting here, its
        # header has fewer columns than we now write. Appending to it would put
        # 29 values under a 23-column header — silently misaligned, and this CSV
        # is the entire point of the exercise. Roll it aside and start clean.
        if not new:
            try:
                with path.open("r", newline="", encoding="utf-8",
                               errors="replace") as fh:
                    header = (fh.readline().strip() or "").split(",")
            except OSError:
                header = []
            if header != FIELDS:
                stamp = datetime.now().strftime("%H%M%S")
                stale = path.with_name(f"{path.stem}_pre{stamp}.csv")
                path.rename(stale)
                LOG.warning("existing %s had an old column layout (%d cols vs %d) "
                            "— moved to %s and started a fresh log",
                            path.name, len(header), len(FIELDS), stale.name)
                new = True

        # ENCODING IS NOT OPTIONAL HERE. Without it Python uses the locale
        # encoding, which on Ben's machine is cp1252: one non-ASCII character
        # anywhere in a row -- an em dash in a message, a symbol in a broker
        # rejection -- is written as a byte no UTF-8 reader can decode, and
        # churn_count, tv_reconcile and the portal all open this file as UTF-8.
        # The whole session's log becomes unreadable to them, not just the row.
        #
        # Found 2026-09-14 when a CONFIG row carried an em dash. It was latent
        # long before that: `reject_reason` has always been able to hold
        # whatever IB sent back.
        self.fh = path.open("a", newline="", encoding="utf-8")
        self.w = csv.DictWriter(self.fh, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            self.w.writeheader()
            self.fh.flush()

    def write(self, **row):
        self.w.writerow(row)
        self.fh.flush()

    def close(self):
        self.fh.close()


# --------------------------------------------------------------------------
# Trader
# --------------------------------------------------------------------------

class MCLPaperTrader:
    def __init__(self, ib: IB, watchlist: Path, log: FillLog, dry_run: bool,
                 tg: "notify.Notifier | None" = None, strategies=None,
                 max_positions: int | None = None,
                 cap_scope: str | None = None):
        self.ib = ib
        # The cap is an INSTANCE value, not the module constant, so a session
        # can run at a different size without editing a constant that the dry
        # runs, the tests and every previous session's semantics depend on.
        # MAX_CONCURRENT_POSITIONS stays the default and stays the documented
        # number; passing this is a deliberate per-session choice that appears
        # in the command line, in the startup log, and in every declined-entry
        # row -- so a later reader of the fill log can tell which cap produced
        # it rather than assuming the constant.
        #
        # `is None`, not `or`: max_positions=0 must mean "take no new entries"
        # (a way to run flat and still record signals), not "use the default".
        self.max_positions = (MAX_CONCURRENT_POSITIONS if max_positions is None
                              else max_positions)
        # What the cap counts: every strategy's positions ("account") or only
        # the signalling strategy's own ("strategy"). See CAP_SCOPES. An
        # unknown value is REFUSED rather than defaulted -- a typo that quietly
        # fell back to the shared pool would be a session run under a cap
        # nobody chose, with a log that says otherwise.
        scope = DEFAULT_CAP_SCOPE if cap_scope is None else cap_scope
        if scope not in CAP_SCOPES:
            raise ValueError(f"cap_scope must be one of {CAP_SCOPES}, "
                             f"got {cap_scope!r}")
        self.cap_scope = scope
        # Default to a DISABLED notifier rather than resolving credentials
        # here. Constructing one per test, or per dry run, must not touch
        # 1Password or spawn a thread; main() passes a live one in.
        self.tg = tg or notify.Notifier()
        self.watchlist = watchlist
        self.log = log
        self.dry_run = dry_run
        # Keyed by (strategy name, symbol). One symbol can carry a state per
        # strategy; they share a SymbolFeed and compete for one position cap.
        self.states: dict[tuple[str, str], SymbolState] = {}
        # Per SYMBOL, shared across strategies. See SymbolFeed.
        self.feeds: dict[str, SymbolFeed] = {}
        self.strategies = list(strategies or [SA.mcl_adapter()])
        self.equity = 0.0
        self.session_pnl = 0.0
        self.session_trades = 0
        self._wl_mtime: float | None = None
        self._paced_warned = False
        self._empty_warned_at = 0.0
        self._stop = False
        # -- the portal (algo-trading-ui), off unless UI_RELAY_URL is set ----
        # `paused` stops NEW ENTRIES only: an open position is still managed,
        # its trail still runs, and its exit still fires. Anything else would
        # mean a button in a browser could leave a position unprotected.
        self.paused = False
        self.disabled_strategies: set[str] = set()
        self.ui = None                  # common.ui_bridge.UIBridge, or None
        # IB delivers the real rejection reason on the error event, not in
        # trade.log — without this we only ever see "Inactive".
        self._errors: dict[int, str] = {}
        self.ib.errorEvent += self._on_error
        # Order ids whose cancel THIS trader sent (see CANCEL_ECHO_RE). Read
        # and cleared by marketable_limit once the outcome is known.
        self._self_cancelled: set[int] = set()

    def _on_error(self, reqId, errorCode, errorString, contract):  # noqa: ANN001

        if reqId and reqId > 0:
            self._errors[reqId] = f"Error {errorCode}: {errorString}"

    # -- setup ------------------------------------------------------------

    def feed_for(self, symbol: str) -> SymbolFeed:
        """The one feed for this symbol, created on first ask.

        Pulled out of _subscribe so the invariant is testable NOW rather than
        at stage 4. With a single strategy _subscribe runs once per symbol, so
        a version that built a fresh feed every call would be indistinguishable
        from this one -- and would then quietly duplicate the contract
        qualification and the market-data line the moment a second strategy
        arrived.
        """
        feed = self.feeds.get(symbol)
        if feed is None:
            feed = self.feeds[symbol] = SymbolFeed(symbol=symbol)
        return feed

    async def _subscribe(self, symbol: str) -> bool:
        feed = self.feed_for(symbol)
        made = [SymbolState(symbol=symbol, feed=feed, strategy=a)
                for a in self.strategies]
        for st in made:
            self.states[(st.strategy.name, symbol)] = st
        # Qualification and the data line are per SYMBOL, so they are done once
        # against the first state and reach the others through the shared feed.
        st = made[0]
        c = Stock(symbol, "SMART", "USD", primaryExchange="NASDAQ")
        try:
            qualified = await self.ib.qualifyContractsAsync(c)
        except Exception as e:  # noqa: BLE001
            LOG.error("could not qualify %s: %s", symbol, e)
            st.blocked = True
            return False
        if not qualified:
            LOG.error("could not qualify %s — skipping", symbol)
            st.blocked = True
            return False
        # qualified[0] CAN BE None. PSNYW on 2026-09-15 is a warrant, so there
        # is no Stock definition for it: IB answered error 200, the list came
        # back non-empty with a None in it, and `st.contract = None` travelled
        # all the way to reqMktData, which reads contract.secType and raised
        #
        #     'NoneType' object has no attribute 'secType'
        #
        # out of _subscribe, out of sync_watchlist, into the run loop -- see
        # the two further defects that turned one bad ticker into a watchlist
        # that stopped reloading.
        got = qualified[0]
        if got is None:
            LOG.error("could not qualify %s — no security definition "
                      "(a warrant, right or unit has none as a Stock)", symbol)
            self.block_symbol(st, "no Stock security definition")
            return False
        # And a contract that qualified as something OTHER than a stock is not
        # one this strategy can trade. Checking the TYPE is the mechanism; a
        # ticker-shaped guess at what is a warrant is a heuristic that would be
        # wrong on the first five-letter common stock it met.
        # The DEFAULT REFUSES. An object with no secType at all is an unknown
        # thing, not a stock, and defaulting to "STK" would have made this
        # guard permissive in exactly the case where nothing is known.
        if getattr(got, "secType", "") != "STK":
            kind = getattr(got, "secType", None) or "unknown"
            LOG.error("%s qualified as %s, not STK — skipping", symbol, kind)
            self.block_symbol(st, f"secType {kind}, not STK")
            return False
        st.contract = got

        # Minimum price variation. US stocks >= $1.00 must be priced in whole
        # cents; a limit like 5.3206 is rejected outright with IB error 110.
        # Ask IB rather than assume — some contracts differ.
        try:
            details = await self.ib.reqContractDetailsAsync(st.contract)
            if details and getattr(details[0], "minTick", 0):
                st.min_tick = float(details[0].minTick)
        except Exception as e:  # noqa: BLE001
            LOG.warning("%s could not read minTick (%s) — using price-based default",
                        symbol, e)

        # Pre-flight: can this account actually OPEN a position in this name?
        # A whatIf order is validated by IB and returns the same rejections as a
        # live one, but is never transmitted. Finding out here costs nothing;
        # finding out when a signal fires costs the signal.
        why = await self.check_tradable(st)
        if why:
            LOG.error("%s NOT TRADABLE — %s", symbol, why)
            self.block_symbol(st, why)
            return False

        # streaming top-of-book so we always have a live bid/ask at signal time
        st.ticker = self.ib.reqMktData(st.contract, "", False, False)
        LOG.info("subscribed %s (contract minTick %s; $0.01 applies at or above "
                 "$1.00 regardless)", symbol, st.min_tick if st.min_tick else "auto")
        return True

    async def check_tradable(self, st: SymbolState) -> str | None:
        """Return a reason string if this account cannot open a position, else None.

        Sends a whatIf order: IB validates permissions, margin and compliance
        restrictions exactly as for a live order but never transmits it. 1 share
        at $1.00 — minimum size, far below any market, harmless even if the flag
        were ignored.

        Uses whatIfOrderAsync, which resolves with an OrderState as soon as IB
        answers. (placeOrder(whatIf=True) does not work here: ib_async's Trade
        object has no orderState attribute, so success is undetectable and every
        probe burns the full timeout.)
        """
        probe = LimitOrder("BUY", 1, 1.00)
        probe.tif = "DAY"
        probe.outsideRth = True

        seen_before = set(self._errors)
        try:
            state = await asyncio.wait_for(
                self.ib.whatIfOrderAsync(st.contract, probe),
                timeout=PROBE_TIMEOUT_S)
            if state is not None and getattr(state, "initMarginChange", None):
                return None                       # margin computed: tradable
        except asyncio.TimeoutError:
            LOG.warning("%s tradability probe timed out after %ss — continuing; "
                        "a rejection would still be caught on the first order",
                        st.symbol, PROBE_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if any(k in msg.lower() for k in INELIGIBLE_MARKERS):
                return msg
            LOG.warning("%s tradability probe failed (%s) — continuing anyway",
                        st.symbol, e)

        # A rejection usually arrives on the error event rather than as a return
        # value or an exception, so check anything new that landed meanwhile.
        for rid, msg in list(self._errors.items()):
            if rid in seen_before:
                continue
            if any(k in msg.lower() for k in INELIGIBLE_MARKERS):
                self._errors.pop(rid, None)
                return msg
        return None

    def block_symbol(self, st: SymbolState, why: str) -> None:
        """Mark a symbol untradable, comment it out of the watchlist, and record why.

        Without this the strategy re-issues an order on every fresh signal and
        burns real entries against a name IB will never accept.
        """
        st.blocked = True
        short = why.replace("<br>", " ").strip()[:220]

        # 1. append to the blocklist so the scanner never re-adds it
        try:
            blocked = self.watchlist.with_name("watchlist_blocked.txt")
            # ASCII hyphen and explicit utf-8: the default Windows encoding
            # mangles an em dash into a replacement character on read-back.
            line = f"{st.symbol}  # {now_et_str()} - {short}\n"
            existing = (blocked.read_text(encoding="utf-8", errors="replace")
                        if blocked.exists() else "")
            if not any(ln.split("#")[0].strip().upper() == st.symbol
                       for ln in existing.splitlines()):
                blocked.write_text(existing + line, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            LOG.warning("could not update watchlist_blocked.txt: %s", e)

        # 2. comment the symbol out of watchlist.txt in place
        try:
            lines = self.watchlist.read_text(encoding="utf-8").splitlines()
            out, changed = [], False
            for ln in lines:
                bare = ln.split("#", 1)[0].strip().upper()
                if bare == st.symbol:
                    out.append(f"# {ln.strip()}   <-- BLOCKED {now_et_str()}: {short}")
                    changed = True
                else:
                    out.append(ln)
            if changed:
                self.watchlist.write_text("\n".join(out) + "\n", encoding="utf-8")
                self._wl_mtime = self.watchlist.stat().st_mtime   # our own edit
                LOG.warning("%s commented out of %s", st.symbol,
                            self.watchlist.name)
        except Exception as e:  # noqa: BLE001
            LOG.warning("could not comment %s out of the watchlist: %s",
                        st.symbol, e)

    async def sync_watchlist(self, first: bool = False) -> None:
        """Re-read watchlist.txt and add/retire symbols without restarting.

        Added names are qualified and subscribed immediately.  Removed names stop
        taking NEW entries but an OPEN POSITION is still managed to its exit — a
        position is never orphaned by an edit to the file.
        """
        try:
            mtime = self.watchlist.stat().st_mtime
        except OSError:
            return
        if not first and mtime == self._wl_mtime:
            return

        wanted = set(parse_watchlist(self.watchlist))
        if not wanted and first:
            return

        # PER SYMBOL, not per pass. One unqualifiable ticker used to abort the
        # whole loop, and `wanted - self.symbols` is a SET -- so which of the
        # remaining names were silently never subscribed depended on iteration
        # order. A symbol that raises is blocked rather than retried: it is
        # already in self.states by this point, so it leaves `wanted -
        # self.symbols` and cannot spin.
        for sym in sorted(wanted - self.symbols):
            try:
                await self._subscribe(sym)
            except Exception as e:                          # noqa: BLE001
                LOG.exception("%s could not be subscribed (%s: %s) — blocked, "
                              "the rest of the watchlist continues",
                              sym, type(e).__name__, e)
                for st in [v for k, v in self.states.items() if k[1] == sym]:
                    st.blocked = True

        for (_name, sym), st in self.states.items():
            if sym not in wanted and not st.retired:
                st.retired = True
                if st.position:
                    LOG.warning("%s removed from watchlist but HOLDING — will manage "
                                "to exit, no new entries", sym)
                else:
                    LOG.info("%s removed from watchlist", sym)
            elif sym in wanted and st.retired:
                st.retired = False
                LOG.info("%s re-added to watchlist", sym)

        # THE MTIME IS SPENT LAST, and this is the defect that turned one bad
        # ticker into a trader working from a stale list in silence.
        #
        # It used to be committed at the top, BEFORE the subscribe loop. So
        # when PSNYW raised, the run loop logged "watchlist reload failed" --
        # and every later pass saw `mtime == self._wl_mtime` and returned
        # immediately. The reload did not retry. It only recovered because
        # tv_feed rewrote the file minutes later and changed the mtime.
        #
        # State advanced before the work it guards completed: the same shape as
        # the loader that had a column and never filled it, and the guard that
        # checked the table instead of the loader.
        self._wl_mtime = mtime

    # -- restarting into an account that is not flat ----------------------

    def open_at_broker(self) -> list:
        """What IBKR says this account is holding, right now.

        THE GAP THIS CLOSES, found 2026-09-09 when Ben asked whether he should
        restart a live session that was holding two positions.

        Until now the trader NEVER asked. `prepare()` did the watchlist and the
        equity and nothing else, and a Position existed in self.states only
        because THIS process had filled the buy that created it. So restarting
        mid-session did three things, all silent:

          * both positions lost their trailing stop -- it is software-managed
            in this process, and outside RTH there is no broker-side stop, so
            killing the process just leaves the shares sitting there;
          * the new process could not see them, so the concurrency cap read 0
            open rather than 2;
          * and with `st.position is None` for those names, the entry path was
            free to BUY THEM AGAIN.

        The module docstring already warned that a crash with a position open
        leaves it unprotected. The restart case -- where it silently doubles
        down -- was covered nowhere.
        """
        try:
            return [p for p in self.ib.positions() if p.position]
        except Exception as e:                                # noqa: BLE001
            LOG.error("could not read positions from IBKR: %s", e)
            raise

    def _held_row(self, symbol: str) -> dict | None:
        """The BUY that opened this position, from today's fill log.

        IBKR knows the symbol, the size and the average cost. It does not know
        which STRATEGY opened it, when, or what the trail is measured from --
        and those are exactly what managing the position requires. The fill log
        is the only place they exist.
        """
        try:
            rows = list(csv.DictReader(self.log.path.open(newline="", encoding="utf-8")))
        except OSError:
            return None
        buys = [r for r in rows
                if r.get("symbol") == symbol and r.get("action") == "BUY"
                and r.get("status") in ("FILLED", "PARTIAL_FILL", "DRY_RUN")]
        return buys[-1] if buys else None

    async def adopt_open_positions(self, held) -> list[str]:
        """Rebuild in-process Positions for what the broker is holding.

        ALL OR NOTHING. Any position that cannot be reconstructed faithfully
        aborts the whole adoption, because a half-managed account is worse than
        an unmanaged one: some positions would have a trailing stop and others
        would not, and nothing on screen would say which.

        The PEAK is the dangerous field. The trail is measured from the highest
        price since entry, and that is not recorded anywhere -- so it is
        rebuilt from the bars between the entry time and now. Guessing it low
        makes the trail too tight and stops the position out instantly;
        guessing it high makes the trail too loose and it gives back more than
        the rule allows. Neither is acceptable, so it is READ rather than
        assumed, and a symbol whose bars cannot be fetched is a refusal.
        """
        problems: list[str] = []
        plans = []
        for p in held:
            symbol = getattr(p.contract, "symbol", "?")
            qty = int(p.position)
            if qty < 0:
                problems.append(f"{symbol}: SHORT {qty} — this trader is "
                                f"long-only and will not manage a short")
                continue
            row = self._held_row(symbol)
            if row is None:
                problems.append(f"{symbol}: no BUY row in {self.log.path.name}, "
                                f"so the entry time and strategy are unknown")
                continue
            name = (row.get("strategy") or "").strip()
            adapter = next((a for a in self.strategies if a.name == name), None)
            if adapter is None:
                problems.append(
                    f"{symbol}: fill row names strategy {name!r}, which is not "
                    f"running (have {[a.name for a in self.strategies]})")
                continue
            try:
                entry_price = float(row["fill_price"])
                entry_time = datetime.strptime(
                    row["ts_et"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            except (KeyError, TypeError, ValueError) as e:
                problems.append(f"{symbol}: fill row unusable ({e})")
                continue
            plans.append((symbol, qty, entry_price, entry_time, adapter))

        if problems:
            for pr in problems:
                LOG.error("cannot adopt %s", pr)
            return problems

        for symbol, qty, entry_price, entry_time, adapter in plans:
            if not await self._subscribe(symbol):
                return [f"{symbol}: could not subscribe, so it cannot be managed"]
            st = self.states[(adapter.name, symbol)]
            df = await self.bars(st)
            if df is None or df.empty:
                return [f"{symbol}: no bars, so the peak since entry cannot be "
                        f"read and the trail would be a guess"]
            since = df[df.index >= entry_time]
            peak = max(entry_price,
                       float(since["high"].max()) if len(since) else entry_price)
            st.position = Position(symbol=symbol, qty=qty,
                                   entry_price=entry_price,
                                   entry_time=entry_time, peak=peak,
                                   trail_pct=adapter.trail_pct)
            LOG.warning("ADOPTED %s %s %d @ %.4f (entered %s), peak %.4f from "
                        "%d bar(s) since entry, trail %.1f%% -> %.4f",
                        adapter.name, symbol, qty, entry_price,
                        entry_time.strftime("%H:%M:%S"), peak, len(since),
                        adapter.trail_pct, st.position.trail_level())
        return []

    def bridge_state(self) -> str:
        """`off`, `configured-but-unattached`, or `attached`.

        THREE STATES, and the ledger could previously tell only two apart.
        The CONFIG row was written by the bridge, so a session with no bridge
        left no row -- and "no bridge configured" and "a bridge was configured
        and refused to attach" are not the same fact. On 2026-09-15 the second
        happened (the agent token had just been deleted by a test run in the
        portal repo) and the log was indistinguishable from the first.
        """
        if self.ui is not None:
            return "attached"
        return ("configured-but-unattached" if os.environ.get("UI_RELAY_URL")
                else "off")

    def record_config(self, reason: str = "session_open") -> None:
        """Write what this trader is running with, unconditionally.

        FROM THE TRADER, NOT THE BRIDGE. The row records a fact about the
        TRADER -- the trail, the cap, what is paused -- and routing it through
        an optional component made the audit trail depend on that component
        being there. A check placed one step short of the thing it protects.

        Every value is read back off `self`, never off the constant or the
        command-line argument it came from: those can drift from what is
        actually running, and this row exists precisely for the case where
        someone changed one of them.
        """
        # _trail_for takes a SymbolState and there is no state yet. Read the
        # trail off each ADAPTER, and name them: with two strategies running,
        # one number in this column would be a claim about both that is only
        # true while they happen to agree.
        trails = " ".join(f"{a.name}:{getattr(a, 'trail_pct', None)}"
                          for a in self.strategies)
        cfg = (f"trail_pct={trails} "
               f"paused={self.paused} "
               f"max_positions={self.max_positions} "
               f"cap_scope={getattr(self, 'cap_scope', DEFAULT_CAP_SCOPE)} "
               f"strategies={'+'.join(a.name for a in self.strategies)} "
               f"disabled={','.join(sorted(self.disabled_strategies)) or '-'} "
               f"dry_run={self.dry_run} "
               f"bridge={self.bridge_state()}")
        self.log.write(ts_et=now_et_str(), action="CONFIG", reason=reason,
                       status="APPLIED", reject_reason=cfg[:200])
        LOG.info("config: %s", cfg)

    async def prepare(self):
        # BEFORE anything can change it, and before the first order. A session
        # that dies in sync_watchlist still leaves a row saying what it was
        # about to run with.
        self.record_config()
        await self.sync_watchlist(first=True)
        await asyncio.sleep(2)
        await self.refresh_equity()

    async def refresh_equity(self):
        rows = await self.ib.accountSummaryAsync()
        for r in rows:
            if r.tag == "NetLiquidation" and r.currency == "USD":
                self.equity = float(r.value)
        LOG.info("account equity: $%s", f"{self.equity:,.2f}")
        cap = self.equity * S.MAX_EQUITY_PCT / 100.0
        LOG.info("sizing: %d shares max, or %%%.0f of equity ($%s) — "
                 "the equity cap only bites above $%s/share",
                 S.MAX_SHARES, S.MAX_EQUITY_PCT, f"{cap:,.0f}", f"{cap / S.MAX_SHARES:,.2f}")

    # -- helpers ----------------------------------------------------------

    @property
    def symbols(self) -> set:
        return {sym for _name, sym in self.states}

    def in_session(self, now_et: datetime, adapter=None) -> bool:
        """Whether THIS strategy is trading now.

        MCL and MC5 share 04:00-09:30 so today every answer is the same; VW9
        runs to 20:00 and will not. Taking the window off the adapter rather
        than a module means adding VW9 does not silently extend MCL's session
        or truncate VW9's.
        """
        a = adapter or self.strategies[0]
        return a.session_start <= now_et.time() < a.session_end

    def any_session_open(self, now_et: datetime) -> bool:
        return any(self.in_session(now_et, a) for a in self.strategies)

    def size_for(self, price: float, adapter=None) -> int:
        a = adapter or self.strategies[0]
        return a.module.size_for(price, self.equity)

    @staticmethod
    def _name_of(st: SymbolState) -> str:
        """The strategy label for a fill row. Empty rather than a default when
        unknown: a row labelled with the WRONG strategy is worse than one
        labelled with none, which is the same rule notify.py applies."""
        return st.strategy.name if st.strategy is not None else ""

    def quote(self, st: SymbolState) -> tuple[float, float]:
        t = st.ticker
        bid = float(t.bid) if t and t.bid and t.bid > 0 else float("nan")
        ask = float(t.ask) if t and t.ask and t.ask > 0 else float("nan")
        return bid, ask

    async def bars(self, st: SymbolState) -> pd.DataFrame | None:
        """1-minute bars including pre-market, most recent last.

        Cached and refreshed at most once per wall-clock minute per symbol.
        These are 1-minute bars: re-requesting them every few seconds returns
        identical data and trips IB's historical-data pacing limits, after
        which requests are refused and the strategy goes blind without saying so.
        """
        now = datetime.now(ET)
        elapsed = time.monotonic() - st.bars_fetched_at
        fresh_enough = (
            st.bars_df is not None
            and st.bars_minute == (now.hour, now.minute)
        )
        if fresh_enough or elapsed < BAR_MIN_INTERVAL_S:
            return st.bars_df

        df = await self._fetch_bars(st, now)
        st.bars_fetched_at = time.monotonic()
        if df is not None:
            st.bars_df = df
            st.bars_minute = (now.hour, now.minute)
        return st.bars_df

    async def _fetch_bars(self, st: SymbolState,
                          now: datetime) -> pd.DataFrame | None:
        """`now` is the CALLER's clock reading, taken BEFORE the request went
        out, never a fresh one taken after it came back.

        A slow response makes that reading stale, and stale errs toward
        dropping the last bar -- the safe direction, and the one the old
        unconditional trim always took. Re-reading the clock afterwards would
        push the other way, using time the response spent in flight as
        evidence that a bar had closed.
        """
        try:
            data = await self.ib.reqHistoricalDataAsync(
                st.contract,
                endDateTime="",
                durationStr=HISTORY_DURATION,
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,          # include pre-market
                formatDate=2,
            )
        except Exception as e:  # noqa: BLE001
            LOG.warning("%s history failed: %s", st.symbol, e)
            return None
        if not data:
            return None
        df = util.df(data)
        if df is None or df.empty:
            return None
        df = df.rename(columns=str.lower)
        df["date"] = pd.to_datetime(df["date"], utc=True)
        df = df.set_index("date").sort_index()
        return drop_forming_bar(df, now)

    # -- order placement --------------------------------------------------

    @staticmethod
    def _trail_for(st) -> float | None:
        """The trailing-stop width this row's trade is running, or None.

        On an EXIT the position's own trail is the truth: it is the one that
        produced the stop, and it can differ from the strategy's current value
        because the portal may have changed the latter mid-session. On an ENTRY
        the strategy's value is the truth, because it is what stamps the
        Position moments later -- see the Position construction in step_symbol,
        which reads the same attribute.

        None rather than a default when it cannot be known: a wrong number in
        this column is worse than an empty one, because a reader would believe
        it.
        """
        if getattr(st, "position", None) is not None:
            return getattr(st.position, "trail_pct", None)
        return getattr(getattr(st, "strategy", None), "trail_pct", None)

    async def _settle(self, trade, order) -> bool:
        """Cancel `order` and wait for IB to say the order is FINISHED.

        True when a terminal status arrived within CANCEL_CONFIRM_S -- and
        `trade.fills` may now hold a fill that was in flight when the cancel
        went out, which the caller must re-read rather than assume away.
        False when nothing terminal arrived: the outcome is UNKNOWN and the
        caller must treat it as such, never as a no-fill.

        The MEDS ghost was exactly the gap this closes: a snapshot of
        `trade.fills` taken before IB had answered.
        """
        try:
            self.ib.cancelOrder(order)
        except Exception as e:                              # noqa: BLE001
            LOG.error("cancelOrder raised (%s: %s) -- outcome treated as "
                      "unknown", type(e).__name__, e)
            return False
        self._self_cancelled.add(order.orderId)
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < CANCEL_CONFIRM_S:
            if trade.isDone():
                return True
            await asyncio.sleep(0.1)
        return trade.isDone()

    async def marketable_limit(self, st: SymbolState, action: str, qty: int,
                               ref_close: float, reason: str, detail: dict,
                               closing: "Position | None" = None,
                               ref_kind: str = ""):
        """Send a marketable limit order, outsideRth, and record what happened.

        IBKR does not accept market orders outside RTH for US stocks, so a
        marketable limit priced through the touch is the closest equivalent.

        `closing` is the position being exited, if any — its presence makes the
        row carry the completed round trip (entry, exit, P/L, hold time).
        """
        def round_trip(exit_px: float, filled: int) -> dict:
            if closing is None:
                return {}
            comm = (order_cost(filled, closing.entry_price, False,
                               COMMISSION_PLAN)
                    + order_cost(filled, exit_px, True, COMMISSION_PLAN))
            pnl = (exit_px - closing.entry_price) * filled - comm
            pct = ((exit_px / closing.entry_price) - 1.0) * 100.0
            held = (datetime.now(ET) - closing.entry_time).total_seconds() / 60.0
            return dict(entry_price=round(closing.entry_price, 4),
                        exit_price=round(exit_px, 4),
                        trade_pnl=round(pnl, 2),
                        trade_pct=round(pct, 3),
                        hold_minutes=round(held, 1))

        trail_pct = self._trail_for(st)
        bid, ask = self.quote(st)
        spread = (ask - bid) if (bid == bid and ask == ask) else float("nan")
        spread_pct = (spread / ask * 100.0) if (ask == ask and ask > 0) else float("nan")

        if action == "BUY":
            base = ask
        else:
            base = bid
        if base != base or base <= 0:
            LOG.warning("%s no quote — skipping %s", st.symbol, action)
            self.log.write(ts_et=now_et_str(), strategy=self._name_of(st),
                           symbol=st.symbol, action=action,
                           reason=reason, ref_close=ref_close,
                           ref_kind=ref_kind, bid=bid, ask=ask,
                           spread=spread, spread_pct=spread_pct, qty=qty,
                           trail_pct=trail_pct,
                           status="NO_QUOTE", **detail)
            return None

        cross = base * (LIMIT_CROSS_BPS / 10_000.0)
        raw = base + cross if action == "BUY" else base - cross
        limit = round_to_tick(raw, action, st.min_tick)

        # Consume a band IB handed us on the previous attempt for this action.
        # "More aggressive" is HIGHER for a buy and LOWER for a sell, and the
        # quoted number is itself refused, so the limit has to land a tick on
        # the acceptable side of it.
        band = st.price_band
        if band and band[0] == action:
            st.price_band = None
            tick = st.min_tick or 0.01
            edge = band[1]
            if action == "BUY":
                limit = round_to_tick(edge - tick, action, st.min_tick)
            elif action == "SELL" and limit <= edge:
                limit = round_to_tick(edge + tick, action, st.min_tick)
            else:
                edge = None
            if edge is not None:
                LOG.info("%s %s limit clamped to %.4f by IB's stated band %.5f",
                         action, st.symbol, limit, band[1])

        row = dict(ts_et=now_et_str(), strategy=self._name_of(st),
                   symbol=st.symbol, action=action, reason=reason,
                   ref_close=ref_close, ref_kind=ref_kind, bid=bid, ask=ask,
                   spread=spread, spread_pct=spread_pct, limit_sent=limit,
                   qty=qty, trail_pct=trail_pct,
                   ref_drift_pct=ref_drift(bid, ask, ref_close), **detail)

        if self.dry_run:
            # Assume the marketable limit fills at its own price. That is the
            # honest assumption: we crossed the spread by LIMIT_CROSS_BPS, so a
            # resting counterparty at the touch fills us at or inside the limit.
            # It cannot capture *whether* size was there — only live orders can.
            slip = (limit - ref_close) if action == "BUY" else (ref_close - limit)
            LOG.info("[DRY] %s %s %d @ limit %.4f (ref %.4f, bid %.4f ask %.4f, "
                     "slip %+.4f)",
                     action, st.symbol, qty, limit, ref_close, bid, ask, -slip)
            self.log.write(status="DRY_RUN", fill_price=limit, filled_qty=qty,
                           slippage_vs_ref=round(-slip, 4),
                           **round_trip(limit, qty), **row)
            return limit, qty

        order = LimitOrder(action, qty, limit)
        order.tif = "DAY"
        order.outsideRth = True          # REQUIRED pre-market
        trade = self.ib.placeOrder(st.contract, order)

        t0 = asyncio.get_event_loop().time()
        through = 0          # consecutive polls with the quote past our limit
        abandoned = False
        while asyncio.get_event_loop().time() - t0 < ORDER_TIMEOUT_S:
            await asyncio.sleep(0.25)
            if trade.isDone():
                break
            if closing is None:
                continue     # entries wait; see EXIT_ABANDON_POLLS
            b, a = self.quote(st)
            # A marketable SELL limit fills against the BID, a BUY against the
            # ASK. Once the touch is past our limit there is nobody to fill it.
            touch = b if action == "SELL" else a
            if touch != touch:
                through = 0          # no quote is not evidence of anything
            elif (touch < limit) if action == "SELL" else (touch > limit):
                through += 1
            else:
                through = 0
            if through >= EXIT_ABANDON_POLLS:
                abandoned = True
                break

        if not trade.isDone():
            # Timed out or abandoned with the order still working. Cancel it
            # and WAIT for IB to say what became of it. The read of
            # `trade.fills` used to happen right here, in the same instant as
            # the break, and on MEDS the fill landed between that read and the
            # cancel arriving at IB. See CANCEL_CONFIRM_S.
            if not await self._settle(trade, order):
                waited = asyncio.get_event_loop().time() - t0
                LOG.error("%s %s order outcome UNKNOWN -- cancel sent, no "
                          "terminal status in %.1fs. Nothing is sent for this "
                          "symbol until IB's position has been read.",
                          action, st.symbol, CANCEL_CONFIRM_S)
                st.unknown_order = True
                st.unknown_trade = trade
                self.log.write(status="ORDER_UNKNOWN", filled_qty=0,
                               seconds_to_fill=round(waited, 2),
                               reject_reason="no terminal order status within "
                                             f"{CANCEL_CONFIRM_S:.0f}s of cancel",
                               **row)
                return None

        filled = int(sum(f.execution.shares for f in trade.fills))
        status = trade.orderStatus.status
        ours = order.orderId in self._self_cancelled
        self._self_cancelled.discard(order.orderId)

        # An order IB never worked (Read-Only API on, outside-RTH refused, no
        # permissions) reports as Inactive/ApiCancelled with no fill. That is a
        # configuration failure, not thin liquidity, and must not be recorded as
        # a no-fill — it would poison the fill-rate measurement.
        #
        # An order THIS trader cancelled reports the same way -- `Cancelled`
        # and a 202 whose reason is blank -- and is the opposite fact: a
        # working order nobody filled. See CANCEL_ECHO_RE. Only a cancel we
        # did not send, or one IB attached a reason to, is a rejection.
        rejected, why = False, status
        if not filled and status in ("Inactive", "ApiCancelled", "Cancelled"):
            # The real reason arrives on the error event; trade.log is often empty.
            why = (self._errors.pop(order.orderId, "")
                   or "; ".join(e.message for e in trade.log if e.message)
                   or status)
            rejected = not (ours and is_cancel_echo(why, status))
        if rejected:
            LOG.error("%s %s REJECTED by IB — %s", action, st.symbol, why)
            low = why.lower()
            if any(k in low for k in INELIGIBLE_MARKERS):
                if action == "BUY":
                    LOG.error("  >> This account cannot OPEN a position in %s. "
                              "Blocking it so no further signals are wasted.",
                              st.symbol)
                    self.block_symbol(st, why)
                else:
                    LOG.error("  >> SELL rejected as ineligible while HOLDING %s. "
                              "Close this position manually in Gateway.", st.symbol)
            if "read-only" in low or "read only" in low:
                LOG.error("  >> Untick 'Read-Only API' in Gateway "
                          "(Configure > Settings > API > Settings).")
            elif "minimum price variation" in low:
                LOG.error("  >> Limit price was off the tick grid. minTick for %s "
                          "is %s.", st.symbol, st.min_tick or "unknown")
            # No try/except around the float(): BAND_RE only matches digits
            # with at most one dot, so it cannot raise. A mutation pass showed
            # the handler was unreachable, and an unreachable guard is noise
            # that reads like protection.
            m = BAND_RE.search(why)
            if m:
                st.price_band = (action, float(m.group(1)))
                LOG.warning("  >> IB's acceptable %s limit for %s is past %s; "
                            "the next attempt will respect it.",
                            action, st.symbol, m.group(1))
            # already dead at IB — cancelling again just logs error 10147/10148
            if status not in ("Cancelled", "ApiCancelled", "Inactive"):
                self.ib.cancelOrder(order)
            self.log.write(status="REJECTED", filled_qty=0, reject_reason=why[:200],
                           **row)
            return None

        if filled and trade.orderStatus.avgFillPrice:
            avg = float(trade.orderStatus.avgFillPrice)
            elapsed = asyncio.get_event_loop().time() - t0
            slip = (avg - ref_close) if action == "BUY" else (ref_close - avg)

            # A partial fill's remainder was cancelled -- and CONFIRMED -- by
            # the settle above: every path that reaches this line has
            # `trade.isDone()`, so the count below is IB's final word and not
            # a snapshot. A second settle here was written first and removed
            # when mutation showed it could never run; a guard that cannot
            # fire is the shape this whole fix exists to remove.
            if filled < qty:
                LOG.warning("%s %s PARTIAL %d/%d @ %.4f — remainder cancelled",
                            action, st.symbol, filled, qty, avg)

            LOG.info("%s %s %d filled @ %.4f (ref %.4f, slip %+.4f)",
                     action, st.symbol, filled, avg, ref_close, -slip)
            rt = round_trip(avg, filled)
            self.log.write(status="FILLED" if filled == qty else "PARTIAL_FILL",
                           fill_price=avg, filled_qty=filled,
                           slippage_vs_ref=round(-slip, 4),
                           seconds_to_fill=round(elapsed, 2),
                           **rt, **row)
            # Notify AFTER the log write, never before: the CSV is the record
            # of what happened and must not be delayed or skipped because a
            # third party is slow. The send itself cannot block or raise --
            # see common/notify.py -- but ordering makes that explicit.
            self.notify_fill(st.symbol, action, avg, filled, rt,
                             strategy=self._name_of(st) or STRATEGY_NAME)
            return avg, filled

        # No fill, and IB has CONFIRMED it (the settle above returned). A second
        # cancel here would only log error 10147 against an order already dead.
        waited = asyncio.get_event_loop().time() - t0
        if abandoned:
            # A DISTINCT STATUS, deliberately. Pooled with the timeout these
            # two become one number and the change that produced them is
            # unmeasurable -- "waited 20s and nobody came" and "was unfillable
            # after half a second" are different facts about the market and
            # about this code.
            b, a = self.quote(st)
            LOG.warning("%s %s exit limit %.4f is through the market "
                        "(bid %.4f ask %.4f) after %.1fs — abandoned to "
                        "re-price", action, st.symbol, limit, b, a, waited)
            self.log.write(status="NO_FILL_ABANDONED", filled_qty=0,
                           seconds_to_fill=round(waited, 2),
                           reject_reason=f"limit {limit:.4f} through the "
                                         f"market (bid {b:.4f} ask {a:.4f})",
                           **row)
            return None
        LOG.warning("%s %s NO FILL in %ds at limit %.4f — cancelled",
                    action, st.symbol, ORDER_TIMEOUT_S, limit)
        self.log.write(status="NO_FILL_CANCELLED", filled_qty=0,
                       seconds_to_fill=round(waited, 2), **row)
        return None

    # -- end of session ----------------------------------------------------

    def archive_watchlist(self, force: bool = False) -> bool:
        """Archive today's watchlist and clear it for tomorrow.

        Guarded on the clock: a mid-session Ctrl-C must NOT wipe a list that took
        real work to build. Only a session that actually reached SESSION_END
        (or --force) clears the file.

        watchlist_pinned.txt is deliberately left alone — it is meant to persist.
        """
        now = datetime.now(ET)
        if not force and now.time() < S.SESSION_END:
            LOG.info("stopped before %s — watchlist left untouched "
                     "(pass --force-archive to clear it anyway)",
                     S.SESSION_END.strftime("%H:%M"))
            return False

        still_open = [s.symbol for s in self.states.values() if s.position]
        if still_open:
            LOG.warning("NOT archiving — still holding %s. Close these first, "
                        "then clear the watchlist by hand.", ", ".join(still_open))
            return False

        stamp = now.strftime("%Y%m%d")
        archive_dir = self.watchlist.parent / "archive"
        moved = []

        for src in (self.watchlist,
                    self.watchlist.with_name("watchlist_blocked.txt")):
            if not src.exists():
                continue
            try:
                body = src.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                LOG.warning("could not read %s: %s", src.name, e)
                continue
            if not [ln for ln in body.splitlines()
                    if ln.split("#", 1)[0].strip()]:
                continue                      # nothing but comments; skip

            try:
                archive_dir.mkdir(exist_ok=True)
                dest = _unique_path(archive_dir / f"{src.stem}_{stamp}{src.suffix}")
                dest.write_text(body, encoding="utf-8")
            except OSError as e:
                # Never clear a file we failed to archive.
                LOG.error("could not archive %s (%s) — leaving it in place",
                          src.name, e)
                continue
            moved.append((src, dest))

        for src, dest in moved:
            try:
                if src == self.watchlist:
                    src.write_text(
                        WATCHLIST_TEMPLATE.format(
                            date=now.strftime("%Y-%m-%d"), stamp=stamp),
                        encoding="utf-8")
                else:
                    src.write_text(
                        f"# Cleared after the {now:%Y-%m-%d} session; that day's "
                        f"blocks are in archive/{dest.name}\n"
                        "# Rebuilt automatically as names are refused.\n",
                        encoding="utf-8")
                self._wl_mtime = self.watchlist.stat().st_mtime
                LOG.info("archived %s -> archive/%s and cleared it",
                         src.name, dest.name)
            except OSError as e:
                LOG.error("archived %s but could not clear it: %s", src.name, e)

        if not moved:
            LOG.info("nothing to archive — watchlist already empty")
        return bool(moved)

    # -- position management ----------------------------------------------

    def _adopt_unknown_entry(self, st: SymbolState, now_et: datetime,
                             detail: dict) -> None:
        # THIS strategy's share (S2): another strategy already in the name
        # must not have its shares adopted a second time.
        held = self._ib_held_for(st)
        if not held:
            if held is None:
                LOG.error("%s entry outcome unknown AND IB unreadable; the "
                          "next poll's reconcile is the only safety left",
                          st.symbol)
            else:
                st.unknown_order = False       # IB says flat: nothing to adopt
                st.unknown_trade = None
            return
        if held < 0:
            LOG.error("%s IB holds less than the other strategies' books say "
                      "(%d short of them) -- nothing to adopt", st.symbol, -held)
            st.unknown_order = False
            st.unknown_trade = None
            return
        cost = None
        try:
            for p in self.ib.positions():
                if getattr(p.contract, "symbol", None) == st.symbol:
                    cost = float(getattr(p, "avgCost", 0) or 0) or None
        except Exception:                                   # noqa: BLE001
            cost = None
        px = cost if cost else float(self.quote(st)[1])
        LOG.error("%s ADOPTED %d shares IB holds from an entry the trader "
                  "never saw fill, at %.4f", st.symbol, held, px)
        st.position = Position(symbol=st.symbol, qty=held, entry_price=px,
                               entry_time=now_et, peak=px,
                               trail_pct=st.strategy.trail_pct)
        self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                       strategy=self._name_of(st), symbol=st.symbol,
                       action="BUY", reason="adopted_unknown_entry",
                       status="FILLED", fill_price=round(px, 4),
                       filled_qty=held, qty=held, ref_kind="ib_position",
                       trail_pct=st.strategy.trail_pct, **detail)

    def _ib_held(self, st: SymbolState) -> int | None:
        """Shares of `st.symbol` the ACCOUNT holds, per IB, or None if that
        cannot be read. `ib.positions()` is a local snapshot of pushed
        positions, not a request, so this costs nothing against pacing."""
        try:
            return int(sum(p.position for p in self.ib.positions()
                           if getattr(p.contract, "symbol", None) == st.symbol))
        except Exception as e:                              # noqa: BLE001
            LOG.error("could not read positions from IBKR: %s", e)
            return None

    def _others_booked(self, st: SymbolState) -> int:
        """Shares every OTHER strategy's book holds in `st.symbol`."""
        return int(sum(s.position.qty for s in self.states.values()
                       if s is not st and s.symbol == st.symbol
                       and s.position is not None))

    def _ib_held_for(self, st: SymbolState) -> int | None:
        """Shares of `st.symbol` IB holds FOR THIS STRATEGY (S2): the account
        position less what every other strategy's book holds in the name.

        `_ib_held` alone is the account, and with MCL and MC5 both in CRML it
        answered "100" to MCL's question when those 100 were MC5's. None when
        IB cannot be read."""
        held = self._ib_held(st)
        if held is None:
            return None
        return held - self._others_booked(st)

    def _working_sells(self, st: SymbolState) -> int:
        """Shares still working in SELL orders on `st.symbol` at IB, per
        ib_async's open-trade list. 0 if that cannot be read -- the position
        check still applies."""
        try:
            trades = self.ib.openTrades()
        except Exception:                                   # noqa: BLE001
            return 0
        n = 0
        for t in trades or []:
            o = getattr(t, "order", None)
            c = getattr(t, "contract", None)
            if o is None or getattr(c, "symbol", None) != st.symbol:
                continue
            if getattr(o, "action", "") != "SELL":
                continue
            try:
                done = t.isDone()
            except Exception:                               # noqa: BLE001
                done = False
            if done:
                continue
            rem = getattr(getattr(t, "orderStatus", None), "remaining", None)
            n += int(rem if rem else getattr(o, "totalQuantity", 0) or 0)
        return n

    def _sell_room(self, st: SymbolState) -> int | None:
        """The most any SELL on `st.symbol` may be for right now (S3): the
        ACCOUNT position less SELLs already working. None if IB cannot be
        read."""
        held = self._ib_held(st)
        if held is None:
            return None
        return held - self._working_sells(st)

    def _resolve_unknown_exit(self, st: SymbolState, pos: "Position",
                              reason: str, detail: dict,
                              now_et: datetime) -> bool:
        """Read the fills of the order that went ORDER_UNKNOWN (S1). Returns
        True when that order turned out to have closed the whole position --
        the caller must then send nothing.

        A late fill is recorded as an ordinary FILLED exit row, so every
        reader that pairs BUY and SELL keeps working; the note says where it
        came from.
        """
        trade = st.unknown_trade
        try:
            fills = list(getattr(trade, "fills", []) or [])
            filled = int(sum(f.execution.shares for f in fills))
            done = bool(trade.isDone())
        except Exception as e:                              # noqa: BLE001
            LOG.warning("%s could not read the unknown order (%s)",
                        st.symbol, e)
            return False
        if filled <= 0:
            if done:
                st.unknown_trade = None      # IB: finished, nothing filled
            return False
        avg = float(getattr(trade.orderStatus, "avgFillPrice", 0) or 0)
        if not avg:
            avg = (sum(float(f.execution.shares) * float(f.execution.price)
                       for f in fills) / filled)
        sold = min(filled, pos.qty)
        comm = (order_cost(sold, pos.entry_price, False, COMMISSION_PLAN)
                + order_cost(sold, avg, True, COMMISSION_PLAN))
        pnl = (avg - pos.entry_price) * sold - comm
        held_min = (datetime.now(ET) - pos.entry_time).total_seconds() / 60.0
        self.session_pnl += pnl
        self.session_trades += 1
        LOG.error("%s LATE FILL: the SELL logged ORDER_UNKNOWN filled %d @ "
                  "%.4f. Recorded as the exit; nothing re-sent. P/L %+.2f",
                  st.symbol, sold, avg, pnl)
        self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                       strategy=self._name_of(st), symbol=st.symbol,
                       action="SELL", reason=reason, qty=pos.qty,
                       ref_close=round(avg, 4), ref_kind="late_fill",
                       status="FILLED", fill_price=round(avg, 4),
                       filled_qty=sold, entry_price=round(pos.entry_price, 4),
                       exit_price=round(avg, 4), trade_pnl=round(pnl, 2),
                       trade_pct=round((avg / pos.entry_price - 1) * 100, 3),
                       hold_minutes=round(held_min, 1),
                       trail_pct=pos.trail_pct,
                       reject_reason="late fill of the order logged "
                                     "ORDER_UNKNOWN",
                       **detail)
        if done:
            st.unknown_trade = None
        if sold >= pos.qty:
            st.position = None
            st.unknown_order = False
            st.unknown_trade = None
            st.last_exit_et = now_et
            return True
        pos.qty -= sold                  # partial: IB check below sizes the rest
        return False

    def _ib_exit_fill(self, st: SymbolState, since: datetime):
        """(avg price, shares) of SELL executions in `st.symbol` since `since`,
        from IB's own fill list, or None when there are none it can see."""
        try:
            fills = self.ib.fills()
        except Exception as e:                              # noqa: BLE001
            LOG.warning("could not read fills from IBKR: %s", e)
            return None
        shares, notional = 0, 0.0
        for f in fills:
            ex = getattr(f, "execution", None)
            c = getattr(f, "contract", None)
            if ex is None or c is None or getattr(c, "symbol", None) != st.symbol:
                continue
            if getattr(ex, "side", "") != "SLD":
                continue
            t = getattr(ex, "time", None)
            if t is not None and since is not None:
                try:
                    if t < since:
                        continue
                except TypeError:
                    pass                # naive vs aware: keep it, do not drop it
            shares += int(ex.shares)
            notional += float(ex.shares) * float(ex.price)
        if shares <= 0:
            return None
        return notional / shares, shares

    def _reconcile_flat(self, st: SymbolState, pos: "Position", reason: str,
                        detail: dict, now_et: datetime | None = None) -> None:
        """IB says flat; the trader thought it held `pos`. Close the position
        LOCALLY, from IB's own executions where they can be seen.

        When IB can show the sell, this is an ordinary late-discovered fill and
        is recorded as FILLED with reason `reconciled_flat`, so every reader
        that pairs BUY and SELL rows keeps working. When it cannot, the row is
        RECONCILED_FLAT with no price: the position is gone and its P/L is
        unknown, and a reader must not pretend otherwise. Either way the
        position is released -- which is what frees the concurrency slot MEDS
        held from 06:17 to 09:30.
        """
        found = self._ib_exit_fill(st, pos.entry_time)
        ts = now_et_str()
        base = dict(ts_et=ts, strategy=self._name_of(st), symbol=st.symbol,
                    action="SELL", qty=pos.qty, ref_kind="ib_execution",
                    trail_pct=pos.trail_pct, **detail)
        if found:
            avg, shares = found
            # IB's SELLs since this entry include another strategy's exits in
            # the same name; this position can only account for its own qty.
            shares = min(shares, pos.qty)
            comm = (order_cost(shares, pos.entry_price, False, COMMISSION_PLAN)
                    + order_cost(shares, avg, True, COMMISSION_PLAN))
            pnl = (avg - pos.entry_price) * shares - comm
            held_min = (datetime.now(ET) - pos.entry_time).total_seconds() / 60.0
            self.session_pnl += pnl
            self.session_trades += 1
            LOG.error("%s RECONCILED: IB is flat; its executions show %d sold "
                      "@ %.4f (the trader had missed the fill). P/L %+.2f",
                      st.symbol, shares, avg, pnl)
            self.log.write(status="FILLED", reason="reconciled_flat",
                           fill_price=round(avg, 4), filled_qty=shares,
                           ref_close=round(avg, 4),
                           entry_price=round(pos.entry_price, 4),
                           exit_price=round(avg, 4), trade_pnl=round(pnl, 2),
                           trade_pct=round((avg / pos.entry_price - 1) * 100, 3),
                           hold_minutes=round(held_min, 1), **base)
        else:
            LOG.error("%s RECONCILED: IB is flat and shows no execution the "
                      "trader can see. Position released; P/L UNKNOWN -- read "
                      "it from the Flex statement.", st.symbol)
            self.log.write(status="RECONCILED_FLAT", reason="reconciled_flat",
                           filled_qty=0,
                           reject_reason="IB flat, local qty "
                                         f"{pos.qty}, no execution visible",
                           **base)
        st.position = None
        st.unknown_order = False
        st.unknown_trade = None
        st.last_exit_et = now_et or datetime.now(ET)

    @staticmethod
    def _exit_reference(pos: "Position", reason: str,
                        bar_close: float | None,
                        last_price: float) -> tuple[float, str]:
        """The price this exit should be MEASURED against, and its name.

        THE DEFECT THIS REPLACES, found 2026-09-08 and fixed on its own so it
        can be attributed. manage_position took one `ref_close` that did two
        unrelated jobs: a fallback price when the ask is NaN, and the fill
        log's measurement reference. The fast loop needs the first and has no
        bar, so it passed pos.entry_price -- which then became the second. On
        every trailing-stop exit the log's `slippage_vs_ref` was therefore the
        trade's WHOLE per-share P/L, not slippage. Both rows of the 2026-09-08
        session show it exactly: -0.39 = 5.43 - 5.82.

        It is not cosmetic. common/friction.py reads slippage_vs_ref straight
        out of these rows, and friction is the number this project turns on.
        The published $4.26 survives -- it was measured on 2026-09-03, when 84%
        of exits were apex_reversal, and those come from the BAR path where the
        reference was a real bar close. But apex was disabled on 2026-09-05, so
        roughly 95% of exits since are trailing stops, and running friction.py
        over yesterday's session would have reported a sell-side slippage of
        39c and 22c a share: enormous, plausible, and entirely the trade's P/L.

        A trailing stop is triggered by a LEVEL, so the level is what the fill
        should be judged against -- "how far below the trigger did we actually
        get out" is the question friction needs answered. A window or apex exit
        is triggered by a BAR, so the bar's close is its reference.
        """
        if reason == "trailing_stop":
            return pos.trail_level(), "trail_level"
        if reason == "window_close":
            # Triggered by the CLOCK, not by a bar. Measured against the bar
            # the rows from the bar path carried a close that was minutes
            # stale while the fast loop's rows carried the quote, and the two
            # alternated row by row on MEDS -- so `slippage_vs_ref` meant two
            # different things under one heading. One reference: the quote.
            return last_price, "quote"
        if bar_close is not None:
            return bar_close, "bar_close"
        # Only reachable if a bar-triggered exit is retried from the fast loop,
        # where there is no bar. Named rather than silently substituted, so a
        # row measured against a quote is never averaged in as if it were
        # measured against a bar.
        return last_price, "quote"

    async def manage_position(self, st: SymbolState, now_et: datetime,
                              bar_close: float | None, detail: dict,
                              bar_high: float | None = None,
                              exit_signal: bool = False) -> None:
        """Trail / window / apex exit for an open position.

        Called from two places, deliberately:
          * the fast loop, every second, off the streaming quote — this is the
            trailing stop, and it costs no API request. `bar_close` is None
            there: that path has no bar, and saying so is the point.
          * the bar path, once a minute, which additionally supplies the apex
            exit signal, the bar high, and the bar's close.

        Pine's `strategy.exit(stop=)` fills intrabar at the stop price. Nothing
        outside a backtest can do that, but a 1-second poll on live quotes is far
        closer than waiting for the bar to close.
        """
        pos = st.position
        if pos is None:
            return

        bid, ask = self.quote(st)
        # The FALLBACK price, when the ask is NaN. Deliberately not the same
        # variable as the measurement reference below -- conflating the two is
        # what produced the defect _exit_reference documents.
        fallback = bar_close if bar_close is not None else pos.entry_price
        last_price = ask if ask == ask else fallback
        candidates = [pos.peak, last_price]
        if bar_high is not None:
            candidates.append(bar_high)
        pos.peak = max(candidates)

        if not self.in_session(now_et, st.strategy):
            reason = "window_close"
        elif last_price <= pos.trail_level():
            reason = "trailing_stop"
        elif exit_signal:
            # From the STRATEGY, not a literal. MC5's backtest calls this
            # gradient_reversal; a hard-coded name here put a label in the fill
            # log that nothing downstream could join to.
            reason = st.strategy.exit_signal_reason
        elif pos.exiting:
            # An earlier exit didn't fill. The decision to be flat stands even
            # if the signal has since flipped back — otherwise a missed exit
            # silently becomes a held position.
            reason = pos.exiting
        else:
            return

        if pos.exiting is None:
            pos.exiting = reason
            if reason == "trailing_stop":
                LOG.info("%s TRAIL HIT — peak %.4f, level %.4f, price %.4f",
                         st.symbol, pos.peak, pos.trail_level(), last_price)
        pos.exit_attempts += 1
        if pos.exit_attempts > 1:
            LOG.warning("%s exit retry #%d (%s) — still holding %d",
                        st.symbol, pos.exit_attempts, reason, pos.qty)

        # BEFORE ANY RE-SEND, ASK IB WHAT THE ACCOUNT HOLDS. The first attempt
        # trusts local state -- IB's position push can lag a fill by a moment
        # and refusing a legitimate first exit would leave a real position
        # unmanaged. Every attempt after that, and any attempt following an
        # order whose outcome IB never confirmed, is checked against IB's own
        # number first. A long-only book must be UNABLE to sell what it does
        # not hold; MEDS proved the local count can be wrong for hours.
        # S1: an order whose outcome was unknown may have closed this already.
        if st.unknown_trade is not None and not self.dry_run:
            if self._resolve_unknown_exit(st, pos, reason, detail, now_et):
                return
        if pos.exit_attempts > 1 or st.unknown_order:
            # S2: this strategy's share, not the account's.
            held = self._ib_held_for(st)
            if held is None:
                LOG.error("%s cannot read IB's position; NOT sending an exit "
                          "it cannot verify", st.symbol)
                return
            if held <= 0:
                self._reconcile_flat(st, pos, reason, detail, now_et)
                return
            if held < pos.qty:
                LOG.error("%s IB holds %d, trader thought %d -- sizing the "
                          "exit to IB's number", st.symbol, held, pos.qty)
                self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                               strategy=self._name_of(st), symbol=st.symbol,
                               action="SELL", reason=reason, qty=pos.qty,
                               filled_qty=held, status="RECONCILED_QTY",
                               reject_reason=f"IB holds {held}, local {pos.qty}",
                               **detail)
                pos.qty = held
            st.unknown_order = False

        # Past the cap, alert ONCE and slow down. IB has just confirmed the
        # shares are held, so the position is real and still needs an exit --
        # at thirty-second intervals rather than one a second.
        if pos.exit_attempts > MAX_EXIT_ATTEMPTS:
            if not pos.needs_attention:
                pos.needs_attention = True
                msg = (f"NEEDS ATTENTION: {st.symbol} exit ({reason}) has not "
                       f"filled after {pos.exit_attempts - 1} attempts; IB "
                       f"confirms {pos.qty} still held. Retrying every "
                       f"{EXIT_RETRY_BACKOFF_S:.0f}s.")
                LOG.error(msg)
                try:
                    self.tg.send(msg, force=True)
                except Exception as e:                      # noqa: BLE001
                    LOG.warning("alert failed (%s) — trading unaffected", e)
            since = time.monotonic() - pos.last_retry_at
            if since < EXIT_RETRY_BACKOFF_S:
                pos.exit_attempts -= 1      # this poll did not count
                return
        pos.last_retry_at = time.monotonic()

        ref, ref_kind = self._exit_reference(pos, reason, bar_close, last_price)

        # S3: never sell more than the ACCOUNT holds less SELLs still working.
        # Exempt only a first attempt on a position IB may not have caught up
        # with yet -- see POSITION_PUSH_LAG_S.
        fresh = (pos.exit_attempts == 1 and not st.unknown_order
                 and (now_et - pos.entry_time).total_seconds()
                 < POSITION_PUSH_LAG_S)
        if not self.dry_run and not fresh:
            room = self._sell_room(st)
            if room is None or room < pos.qty:
                why = ("IB unreadable" if room is None else
                       f"account holds {room} after working SELLs, "
                       f"local qty {pos.qty}")
                LOG.error("%s SELL %d REFUSED -- it would take the account "
                          "short (%s)", st.symbol, pos.qty, why)
                self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                               strategy=self._name_of(st), symbol=st.symbol,
                               action="SELL", reason=reason, qty=pos.qty,
                               filled_qty=0, status="REFUSED_WOULD_SHORT",
                               reject_reason=why, trail_pct=pos.trail_pct,
                               **detail)
                # Counted as an attempt, so the next poll takes the re-send
                # path: it asks IB for THIS strategy's share (S2) and
                # releases the position if IB is really flat for it.
                return

        res = await self.marketable_limit(st, "SELL", pos.qty, ref,
                                          reason, detail, closing=pos,
                                          ref_kind=ref_kind)
        if not res:
            return

        exit_px, sold = res
        # Same per-leg schedule as the fill-log row above, so the running
        # session total and the CSV cannot disagree.
        pnl = (exit_px - pos.entry_price) * sold - (
            order_cost(sold, pos.entry_price, False, COMMISSION_PLAN)
            + order_cost(sold, exit_px, True, COMMISSION_PLAN))
        self.session_pnl += pnl
        self.session_trades += 1
        LOG.info("CLOSED %s %s  %d @ %.4f -> %.4f  P/L %+.2f  "
                 "(session: %d trades, %+.2f)",
                 st.symbol, reason, sold, pos.entry_price, exit_px, pnl,
                 self.session_trades, self.session_pnl)
        if sold < pos.qty:
            # Only part of the position went. Keep the rest and keep trying —
            # never mark flat while shares are still held.
            pos.qty -= sold
            LOG.warning("%s still holding %d after partial exit",
                        st.symbol, pos.qty)
        else:
            st.position = None
            st.last_exit_et = now_et

    # -- per-symbol logic -------------------------------------------------

    async def step_symbol(self, st: SymbolState, now_et: datetime):
        if st.strategy is None:
            raise RuntimeError(
                f"{st.symbol} has no strategy attached. Refusing rather than "
                "assuming one: a state attributed to the wrong strategy sizes, "
                "bands and trails against rules it never agreed to.")
        if st.blocked or st.contract is None:
            return

        df = await self.bars(st)
        if df is None or df.empty:
            return

        last_ts = df.index[-1].to_pydatetime()
        # The ADAPTER decides which bar has closed. For MCL that is the last
        # 1-minute row; for MC5 the last complete 5-minute bucket, which is why
        # the current time goes in.
        sig = st.strategy.evaluate(df, now_et)
        if sig is None:
            return

        bid, ask = self.quote(st)
        detail = sig.detail

        # ---- manage an open position -----------------------------------
        if st.position:
            # Only feed the peak a bar high from a bar that CLOSED AFTER entry.
            # The last closed bar is usually the one before we filled, and its
            # high is pre-entry — seeding the peak with it makes the trail
            # instantly too tight and can stop the position out within seconds.
            # Pine's peakSinceEntry only ever sees bars from the entry onward.
            # And EVERY bar that closed since the last one fed, not only the
            # newest: marketable_limit can block for twenty seconds, bars close
            # unseen in that time, and a skipped bar's high never reached the
            # peak. On MEDS the tape printed 4.96 and the trader's peak read
            # 4.79 -- a trail loosened at random by the order queue.
            pos = st.position
            after = max(filter(None, (pos.entry_time, pos.last_bar_seen)))
            closed = df[df.index > after]
            bar_high = float(closed["high"].max()) if len(closed) else None
            if len(closed):
                pos.last_bar_seen = last_ts
            await self.manage_position(st, now_et, bar_close=sig.close,
                                       detail=detail, bar_high=bar_high,
                                       exit_signal=sig.exit_signal)
            return

        # ---- look for an entry -----------------------------------------
        if st.retired:
            return                      # removed from the watchlist
        if not self.in_session(now_et, st.strategy):
            return
        # Dedupe on the bar the SIGNAL was computed on, which the strategy
        # hands us, NOT on the frame's last row.
        #
        # `last_ts` is the last 1-MINUTE bar. For MCL that is the signal bar
        # and this guard worked; for MC5 the frame advances every minute while
        # the signal changes every five, so the guard never fired inside a
        # bucket and one signal entered up to five times at successively worse
        # prices. On 2026-09-11 that was 40% of all entries.
        #
        # A strategy that does not supply `bar_ts` falls back to the frame's
        # last row -- the old behaviour, which is correct only when the two
        # coincide. That fallback is deliberate and narrow: a new strategy
        # omitting the field gets the SAFE-for-1-minute answer, and
        # test_entry_dedup pins that every registered adapter supplies it.
        signal_ts = getattr(sig, "bar_ts", None) or last_ts
        if st.last_bar_ts == signal_ts:
            return                      # already evaluated this bar
        st.last_bar_ts = signal_ts

        if not sig.long_entry:
            return

        # STALE SIGNAL BAR. First among the refusals, and deliberately so:
        # every check below this one is about US -- paused, capped, out of band
        # -- and this one is about whether the SIGNAL is about today at all.
        # A bar that does not belong to this session should not be reported as
        # having been declined for the concurrency cap it also happened to hit.
        #
        # It sits AFTER the dedupe on purpose. The stale bar is still marked
        # evaluated, so the same fourteen-hour-old timestamp is not re-declined
        # and re-logged on every poll until a real bar arrives; one row per
        # stale bar is the record, not one row per second.
        ok, why = bar_session_ok(signal_ts, now_et,
                                 st.strategy.session_start,
                                 st.strategy.session_end)
        if not ok:
            LOG.warning("%s %s entry signal declined — stale bar: %s",
                        st.strategy.name, st.symbol, why)
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_STALE_BAR", reject_reason=why,
                           **detail)
            return

        # A BAR THAT CLOSED DURING THE PREVIOUS POSITION. Second, and before
        # the account-level gates for the same reason the stale gate is first:
        # this is about whether the signal is about NOW. The bar is already
        # marked evaluated above, so it is declined once, not once a second.
        ok, why = bar_after_exit(signal_ts, st.last_exit_et)
        if not ok:
            LOG.info("%s %s entry signal declined — %s",
                     st.strategy.name, st.symbol, why)
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_BAR_BEFORE_EXIT", reject_reason=why,
                           **detail)
            return

        # Stopped from the portal. Recorded in the fill log like every other
        # declined entry, so a later reader can see the signal fired and why it
        # was not taken -- an absence would look like the strategy never fired.
        if self.paused or st.strategy.name in self.disabled_strategies:
            why = ("paused from the portal" if self.paused
                   else f"{st.strategy.name} disabled from the portal")
            LOG.info("%s %s entry signal declined — %s",
                     st.strategy.name, st.symbol, why)
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_PAUSED", reject_reason=why,
                           **detail)
            return

        # Portfolio-level gate. Everything above this point is about THIS
        # symbol; this is the only check that looks at the account as a whole.
        # The bar is already marked evaluated above, which is correct: the
        # signal fired and we declined it, so it should not be reconsidered.
        # ACROSS EVERY STRATEGY. A cap that counted only its own would be two
        # caps of two on an account sized for two -- and the account is shared,
        # so the second strategy would be spending buying power the first
        # already committed.
        # With cap_scope "strategy" only the signalling strategy's own
        # positions count; with "account" (the default) every strategy's do.
        per_strategy = getattr(self, "cap_scope", DEFAULT_CAP_SCOPE) == "strategy"
        mine = self._name_of(st)
        counted = [s for s in self.states.values()
                   if s.position is not None
                   and (not per_strategy or self._name_of(s) == mine)]
        open_now = len(counted)
        if open_now >= self.max_positions:
            LOG.info("%s %s entry signal declined — %d position(s) already open "
                     "(cap %d %s): %s", st.strategy.name, st.symbol, open_now,
                     self.max_positions,
                     f"for {mine}" if per_strategy else "across all strategies",
                     ", ".join(sorted(
                         f"{s.strategy.name}:{s.symbol}" for s in counted)))
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_CONCURRENCY_CAP",
                           reject_reason=(
                               f"{open_now} open for {mine}, cap "
                               f"{self.max_positions} per strategy"
                               if per_strategy else
                               f"{open_now} open, cap {self.max_positions}"),
                           **detail)
            return

        # PRICE BAND -- live/backtest parity, added 2026-09-05.
        #
        # strategy/mcl/mcl.py's backtest refuses any entry outside $2-20
        # (ENFORCE_PRICE_BAND), and brokers/ibkr/scanner.py screens on the same
        # band. The LIVE path did neither: it went from evaluate_last_bar()
        # straight to size_for(), so anything that reached the watchlist by
        # another route, or drifted out of band between the scan and the
        # signal, was traded. GELS was bought at $0.935 that way -- a price the
        # backtest has never modelled and never will, which quietly makes any
        # live-vs-backtest comparison a comparison of two different universes.
        #
        # This is a RESTRICTION on what live may buy, never an expansion.
        if not st.strategy.in_band(sig.close):
            LOG.info("%s %s entry signal declined — %.4f outside the $%.2f-%.2f "
                     "band", st.strategy.name, st.symbol, sig.close,
                     st.strategy.price_min, st.strategy.price_max)
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_PRICE_BAND",
                           reject_reason=f"{sig.close:.4f} outside "
                                         f"{st.strategy.price_min:.2f}-"
                                         f"{st.strategy.price_max:.2f}",
                           **detail)
            return

        qty = self.size_for(sig.close, st.strategy)
        if qty < 1:
            LOG.info("%s signal but size 0 (equity %.2f, price %.2f)",
                     st.symbol, self.equity, sig.close)
            return

        # THE DRIFT GUARD -- last, on a fresh quote, immediately before the
        # order. Everything above decided the signal is one to take; this
        # decides whether the market is still where the signal was priced.
        # A refusal is recorded like every other declined entry, once per
        # bar (the bar is already marked evaluated).
        _b, ask_now = self.quote(st)
        ok, why = drift_guard_ok(ask_now, sig.close, DRIFT_GUARD_PCT)
        if not ok:
            LOG.warning("%s %s entry signal declined — %s",
                        st.strategy.name, st.symbol, why)
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close", bid=_b, ask=ask_now,
                           ref_drift_pct=ref_drift(_b, ask_now, sig.close),
                           status="SKIPPED_DRIFT", reject_reason=why,
                           **detail)
            return

        res = await self.marketable_limit(st, "BUY", qty, sig.close,
                                          "entry_signal", detail,
                                          ref_kind="signal_close")
        if res is None and st.unknown_order:
            # THE REVERSE GHOST. An entry whose outcome IB never confirmed may
            # have filled -- shares in the account with no position on the
            # book, unmanaged, untrailed, and free to be bought again on the
            # next signal. Ask IB now; adopt whatever it holds at its own
            # average cost, with the flag left set so the first exit
            # reconciles before it sends.
            self._adopt_unknown_entry(st, now_et, detail)
        if res:
            avg, filled = res
            # The trail travels with the POSITION, not with whichever strategy
            # module happens to be imported. H2 in the spec: MCL and MC5 are
            # both at 5.0 today, so reading the wrong one is invisible until
            # the day one of them changes.
            # THE PEAK STARTS AT THE FILL, and at nothing else.
            #
            # It was `max(avg, sig.close)` until 2026-09-16. `sig.close` is the
            # SIGNAL bar's close -- a price from BEFORE the order existed --
            # and on VEEA that day the signal bar closed at 5.8709 while the
            # fill came at 5.70. The position opened with a peak it had never
            # traded at, a trail level of 5.577 against an entry of 5.70, and
            # was eleven cents from a stop the moment it existed. The trail is
            # a giveback rule: it can only measure giveback from a high the
            # position actually saw.
            #
            # This is the same rule the two neighbouring paths already keep.
            # The manage_position peak feed refuses any bar high from a bar
            # that closed before entry; the restart-adoption path seeds from
            # `max(entry_price, highs SINCE entry)`. Pine's peakSinceEntry
            # never sees a pre-entry bar either. Three of four agreed and the
            # fourth was the one placing the orders.
            st.position = Position(symbol=st.symbol, qty=filled, entry_price=avg,
                                   entry_time=now_et, peak=avg,
                                   trail_pct=st.strategy.trail_pct)

    def notify_fill(self, symbol: str, action: str, price: float,
                    filled: int, rt: dict, strategy: str = STRATEGY_NAME) -> None:
        """Push a fill to Telegram. Commission is recomputed from the SAME
        schedule the P/L used (common/commissions.py), per leg, so the message
        can never quote a different number from the fill log.

        Wrapped whole: this is decoration on a live trading path and must not
        be able to raise into it, however the notifier is configured.
        """
        try:
            if action == "BUY":
                comm = order_cost(filled, price, False, COMMISSION_PLAN)
                self.tg.send(
                    notify.buy_filled(symbol, price, filled, comm,
                                      strategy=strategy),
                    force=True)
            else:
                comm = order_cost(filled, price, True, COMMISSION_PLAN)
                # rt["trade_pnl"] is the ROUND TRIP net, both legs' commission
                # already deducted. Absent when this sell is not closing a
                # tracked position, in which case there is no P/L to claim.
                pnl = rt.get("trade_pnl")
                if pnl is None:
                    return
                self.tg.send(
                    notify.sell_filled(symbol, price, filled, comm, pnl,
                                       strategy=strategy),
                    force=True)
        except Exception as e:                              # noqa: BLE001
            LOG.warning("notification failed (%s: %s) — trading unaffected",
                        type(e).__name__, e)

    # -- main loop --------------------------------------------------------

    async def run(self):
        LOG.info("entering main loop — %s", "DRY RUN" if self.dry_run else "LIVE PAPER ORDERS")
        while not self._stop:
            now_et = datetime.now(ET)
            last_end = max(a.session_end for a in self.strategies)
            if now_et.time() >= last_end and not any(
                    s.position for s in self.states.values()):
                LOG.info("%s ET reached and flat — stopping", last_end)
                break
            # picks up edits to watchlist.txt mid-session, no restart needed
            try:
                await self.sync_watchlist()
                live = sum(1 for s in self.states.values()
                           if not s.retired and not s.blocked)
                if live == 0 and self.any_session_open(now_et):
                    if time.monotonic() - self._empty_warned_at >= EMPTY_WARN_S:
                        self._empty_warned_at = time.monotonic()
                        LOG.warning("still watching nothing — %s is empty. Add "
                                    "tickers (picked up within 5s) or start "
                                    "main.py --mode scan.", self.watchlist.name)
                if live > MAX_SYMBOLS_SAFE and not self._paced_warned:
                    self._paced_warned = True
                    LOG.warning("%d active symbols — above %d, IB's 60-requests"
                                "-per-10-minutes history cap may start refusing "
                                "bar requests. Trim the watchlist.",
                                live, MAX_SYMBOLS_SAFE)
            except Exception as e:  # noqa: BLE001
                LOG.warning("watchlist reload failed: %s", e)
            for st in list(self.states.values()):
                # Fast path first: the trailing stop runs off the streaming
                # quote every second and makes no API request.
                if st.position is not None:
                    try:
                        await self.manage_position(
                            st, now_et, bar_close=None, detail={})
                    except Exception as e:  # noqa: BLE001
                        LOG.exception("%s trail check failed: %s", st.symbol, e)
                try:
                    await self.step_symbol(st, now_et)
                except Exception as e:  # noqa: BLE001
                    LOG.exception("%s step failed: %s", st.symbol, e)

            # The portal, if one is configured. It throttles itself, runs its
            # network calls off this thread, and swallows its own failures --
            # a relay that is down must be invisible from in here.
            if self.ui is not None:
                try:
                    await self.ui.tick(self, now_et)
                except Exception as e:  # noqa: BLE001
                    LOG.warning("portal tick failed: %s", e)

            await asyncio.sleep(LOOP_SLEEP_S)

        open_pos = [s.symbol for s in self.states.values() if s.position]
        shorts = [] if self.dry_run else self.shorts_at_broker()
        LOG.info("=" * 60)
        LOG.info("SESSION SUMMARY%s", "  (DRY RUN — no orders placed)"
                 if self.dry_run else "")
        LOG.info("  closed trades : %d", self.session_trades)
        LOG.info("  net P/L       : %+.2f", self.session_pnl)
        if self.session_trades:
            LOG.info("  avg per trade : %+.2f",
                     self.session_pnl / self.session_trades)
        if open_pos:
            LOG.info("  STILL OPEN    : %s", ", ".join(open_pos))
        if shorts:
            LOG.error("  SHORT AT IBKR : %s", ", ".join(shorts))
        LOG.info("  fill log      : %s", self.log.path)
        LOG.info("=" * 60)

    def shorts_at_broker(self) -> list[str]:
        """Any SHORT position IB reports, as "SYM -100" strings, alerted once.

        This book is long-only, so a short is always a defect -- and until
        2026-09-21 the first anyone heard of one was the next morning, when
        the startup guard refused to trade (W02-0014). Now the session that
        made it says so before it exits."""
        try:
            short = [p for p in self.ib.positions() if p.position < 0]
        except Exception as e:                              # noqa: BLE001
            LOG.warning("could not read positions at session end: %s", e)
            return []
        out = [f"{getattr(p.contract, 'symbol', '?')} {int(p.position)}"
               for p in short]
        if out:
            msg = ("SHORT AT SESSION END: " + ", ".join(out) + ". This book "
                   "is long-only -- buy to cover in IBKR before the next "
                   "session, or the trader will refuse to start.")
            LOG.error(msg)
            try:
                self.tg.send(msg, force=True)
            except Exception as e:                          # noqa: BLE001
                LOG.warning("alert failed (%s)", e)
        return out

    def stop(self, *_):
        LOG.info("stop requested")
        self._stop = True


def now_et_str() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

async def main_async(args):
    if args.port in LIVE_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is {LIVE_PORTS[args.port]}. "
                 f"Paper ports are {sorted(PAPER_PORTS)}.")
    if args.port not in PAPER_PORTS:
        sys.exit(f"REFUSING TO RUN: port {args.port} is not a known paper port "
                 f"{sorted(PAPER_PORTS)}.")

    wl = Path(args.watchlist)
    if not wl.exists():
        sys.exit(f"watchlist not found: {wl}")
    symbols = parse_watchlist(wl)
    if symbols:
        LOG.info("watchlist: %s", ", ".join(symbols))
    else:
        # Starting empty is the NORMAL morning state now that the watchlist is
        # archived and cleared at the end of each session, so this is a warning
        # rather than a refusal. The loop keeps repeating it while nothing is
        # being watched, so a genuine oversight still gets noticed.
        LOG.warning("watchlist is empty — watching nothing. Add tickers to %s "
                    "(re-read every 5s) or start main.py --mode scan.", wl)

    ib = IB()
    await ib.connectAsync(args.host, args.port, clientId=args.client_id)

    accounts = ib.managedAccounts()
    LOG.info("connected. accounts: %s", accounts)
    if not accounts or not all(a.startswith("DU") for a in accounts):
        ib.disconnect()
        sys.exit(f"REFUSING TO RUN: account(s) {accounts} do not look like IBKR "
                 f"paper accounts (expected ids starting 'DU').")

    log = FillLog(Path(args.out))
    # Resolved once, here, at startup -- the same discipline as every other
    # credential in this project. A lazy resolve mid-session can block on a
    # 1Password prompt with a position open.
    tg = (notify.Notifier() if args.no_telegram
          else notify.Notifier.from_env(args.telegram_batch_min))
    strategies = SA.build_all(getattr(args, "strategy", ["mcl"]))
    trader = MCLPaperTrader(ib, wl, log, args.dry_run, tg=tg,
                            strategies=strategies,
                            max_positions=getattr(args, "max_positions", None),
                            cap_scope=getattr(args, "cap_scope", None))
    # The portal, when one is configured. Attached AFTER the DU check above,
    # so a bridge can never exist on a session that failed it.
    trader.ui = ui_bridge.UIBridge.from_env(dry_run=bool(args.dry_run))
    if trader.ui is not None:
        trader.ui.note_account(accounts[0] if accounts else "")
        tg.observer = trader.ui.record_message
        LOG.info("portal: publishing to %s as %s", trader.ui.base_url,
                 trader.ui.agent_id)

    # SAID OUT LOUD. The row records the state, which is the durable half; this
    # is the half that reaches Ben tonight. Last time the bridge refused, the
    # only trace was one WARNING inside a wall of IB logging and it went
    # unnoticed for two hours while the dashboard sat empty.
    if trader.bridge_state() == "configured-but-unattached":
        LOG.warning("PORTAL NOT PUBLISHING: UI_RELAY_URL is set but the bridge "
                    "would not start. The session trades normally; the "
                    "dashboard stays empty.")
        if tg is not None:
            try:
                tg.send("\u26a0\ufe0f <b>portal not publishing</b>\n"
                        "the relay is configured but the bridge would not "
                        "start; the session is trading normally", force=True)
            except Exception:                               # noqa: BLE001
                LOG.debug("could not send the portal warning", exc_info=True)

    # Read the cap back OFF THE TRADER rather than off the constant or the
    # argument. Those can drift from what is running; this cannot.
    LOG.info("strategies: %s (one book, cap %d %s)%s",
             ", ".join(a.name for a in strategies), trader.max_positions,
             "across all of them" if trader.cap_scope == "account"
             else (f"PER STRATEGY -- up to "
                   f"{trader.max_positions * len(strategies)} open in total"),
             "" if trader.max_positions == MAX_CONCURRENT_POSITIONS
             else f"  [OVERRIDDEN from the default "
                  f"{MAX_CONCURRENT_POSITIONS}]")

    # BEFORE the watchlist, the equity, or a single bar request. A trader that
    # starts into a non-flat account and does not know it is the failure this
    # check exists for -- see open_at_broker().
    held = trader.open_at_broker()
    if held:
        lines = ", ".join(
            f"{getattr(p.contract, 'symbol', '?')} {int(p.position)} @ "
            f"{float(getattr(p, 'avgCost', 0)):.4f}" for p in held)
        LOG.warning("IBKR reports %d open position(s): %s", len(held), lines)
        if getattr(args, "on_open_positions", "refuse") == "adopt":
            problems = await trader.adopt_open_positions(held)
            if problems:
                ib.disconnect()
                sys.exit(
                    "REFUSING TO RUN: could not adopt every open position, and "
                    "adopting some would leave the rest unmanaged with nothing "
                    "on screen saying which.\n  "
                    + "\n  ".join(problems))
        else:
            ib.disconnect()
            sys.exit(
                f"REFUSING TO RUN: IBKR is holding {len(held)} position(s) "
                f"({lines}).\n"
                "  This trader manages a position only if THIS process opened "
                "it: the trailing stop lives in here, and outside RTH there is "
                "no broker-side stop.\n"
                "  Starting anyway would leave those shares with no stop, "
                "report 0 of the concurrency cap as used, and allow a SECOND "
                "entry in the same name.\n"
                "  Either let the running session finish and close them, or "
                "restart with --on-open-positions adopt to rebuild them from "
                f"{log.path.name}.")

    for s in (_signal.SIGINT, _signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(s, trader.stop)
        except NotImplementedError:
            pass  # Windows

    # State the end-of-session behaviour up front, so it is visible in the
    # console rather than assumed. Both of these only happen at 09:30.
    LOG.info("at session end: watchlist %s; PC %s",
             "kept as-is (--no-archive)" if args.no_archive
             else "archived and cleared",
             f"sleeps after {args.sleep_delay_min} min" if args.sleep_on_exit
             else "stays awake (pass --sleep-on-exit to change)")

    try:
        await trader.prepare()
        await trader.run()
    finally:
        log.close()
        ib.disconnect()
        LOG.info("disconnected. fill log: %s", args.out)
        # THE ONLY PLACE THIS CAN LIVE, and it is deliberately the last thing.
        # After log.close() so the file is complete, and after ib.disconnect()
        # so nothing here can touch the broker. Read back off the FILE rather
        # than the trader's own state: a summary built from memory agrees with
        # itself by construction, one read off the ledger can disagree, and
        # that disagreement is the thing worth seeing.
        #
        # Wrapped whole. This runs on the shutdown path, including the one
        # after a crash, and a broken summary must never mask why the session
        # ended.
        finish_session(tg, log.path,
                       [a.name for a in trader.strategies],
                       no_summary=args.no_summary)
        if not args.no_archive:
            trader.archive_watchlist(force=args.force_archive)
        # THE PORTAL'S LAST WORD, before the machine can sleep.
        # claude/handover_session_end_upload_20260919.md sec 1: final state
        # push, then history upload, then --sleep-on-exit -- in that order,
        # because the push is what stops the portal showing a position the
        # account no longer holds, and the upload is what makes "the trader
        # stopped" a fact rather than an inference from silence
        # (claude/handover_portal_stale_position_20260918.md item 2). Placed
        # here, after log.close() and ib.disconnect(), so the fill log is
        # complete and nothing here can touch the broker -- same reasoning as
        # finish_session() above. Neither call can raise; a failed push or
        # upload must never skip --sleep-on-exit.
        if trader.ui is not None:
            trader.ui.push_final_state(trader)
            trader.ui.upload_history(trader)
        if args.sleep_on_exit:
            flat = not any(s.position for s in trader.states.values())
            suspend_machine(args.sleep_delay_min, flat)


WATCHLIST_TEMPLATE = """\
# MCL watchlist — one ticker per line, lines starting with # are ignored.
#
# Cleared automatically at the end of the {date} session; the list that ran
# that day is in archive/watchlist_{stamp}.txt
#
# Screen: pre-market change >= 20% (against the PREVIOUS REGULAR CLOSE),
#         pre-market price $2-25, pre-market volume >= 100k.
#         Float is NOT filtered; it is shown on the alert only.
#         The trader still refuses entries outside $2-20.
# The running script re-reads this file every 5 seconds, so names can be added
# or removed mid-session without restarting.
#
# Names here are for ONE session only. Add today's below.
"""


def _unique_path(path: Path) -> Path:
    """archive/watchlist_20260902.txt -> ..._2.txt if it already exists."""
    if not path.exists():
        return path
    for n in range(2, 100):
        alt = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not alt.exists():
            return alt
    return path


def finish_session(tg, log_path, strategy_names, no_summary: bool = False) -> None:
    """Everything the notifier owes once trading has stopped.

    A FUNCTION, not four lines inside main()'s finally block, because that is
    unreachable from a test -- and both halves of it fail silently. A summary
    that never sends and a batch that is dropped both look exactly like a quiet
    session from the phone.

    Called after log.close() and ib.disconnect(), so nothing here can touch the
    broker, and the file it reads is complete.
    """
    if not no_summary:
        try:
            rows = notify.read_fills(log_path)
            if rows:
                tg.send(notify.session_summary(
                    rows, strategy=",".join(strategy_names)), force=True)
        except Exception as e:                              # noqa: BLE001
            # The shutdown path runs after a crash too, and a broken summary
            # must never mask why the session ended.
            LOG.warning("session summary failed (%s: %s) — the fill log is "
                        "unaffected, run `python -m common.notify --summary "
                        "%s`", type(e).__name__, e, log_path)
    # Sends anything still waiting in a batch. Without it, ending a session on
    # a 30-minute cadence discards most of the last half hour.
    tg.flush()


def suspend_machine(delay_min: int, flat: bool) -> None:
    """Put the machine to sleep after the session, once it is safely finished.

    Refuses if a position is still open — sleeping suspends this process, and the
    trailing stop lives in it, so an open position would sit unprotected.
    """
    if not flat:
        LOG.warning("NOT sleeping: a position is still open. The trailing stop "
                    "lives in this process and would be suspended with it.")
        return
    if not sys.platform.startswith("win"):
        LOG.warning("NOT sleeping: --sleep-on-exit is implemented for Windows only.")
        return

    LOG.info("=" * 60)
    LOG.info("Sleeping this PC in %d minutes. Press Ctrl-C to cancel.", delay_min)
    LOG.info("=" * 60)
    try:
        for remaining in range(delay_min, 0, -1):
            LOG.info("sleep in %d min...", remaining)
            time.sleep(60)
    except KeyboardInterrupt:
        LOG.info("sleep cancelled — machine staying awake.")
        return

    LOG.info("suspending now. goodnight.")
    import subprocess
    # NOTE: SetSuspendState hibernates instead of sleeping when hibernation is
    # enabled. Either is fine here — both end the session and stop drawing power.
    subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                   check=False)


def build_parser() -> argparse.ArgumentParser:
    """The trader's arguments, as a function so a test can read the real
    defaults instead of rebuilding them. A test that constructs its own parser
    and asserts on that is asserting about itself."""
    p = argparse.ArgumentParser(description="MCL pre-market paper trader (IBKR)")
    p.add_argument("--watchlist", default="var/watchlist.txt",
                   help="file with today's qualifying tickers, one per line")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002,
                   help="4002 IB Gateway paper (default) or 7497 TWS paper")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--out", default=f"var/fills/mcl_fills_{datetime.now(ET):%Y%m%d}.csv")
    p.add_argument("--on-open-positions", choices=["refuse", "adopt"],
                   default="refuse",
                   help="what to do if IBKR is already holding something at "
                        "startup. refuse (default) stops before touching "
                        "anything and tells you what is held; adopt rebuilds "
                        "the positions from today's fill log and manages them, "
                        "and aborts unless EVERY one can be reconstructed.")
    p.add_argument("--cap-scope", choices=CAP_SCOPES, default=None,
                   help="what --max-positions counts: 'account' (default) = "
                        "one pool shared by every strategy; 'strategy' = each "
                        "strategy gets its own pool of --max-positions, so "
                        "MCL and MC5 at 3 can hold up to 6 between them.")
    p.add_argument("--max-positions", type=int, default=None,
                   help="open positions allowed ACROSS ALL strategies, or per "
                        "strategy with --cap-scope strategy "
                        f"(default {MAX_CONCURRENT_POSITIONS}). Raising this "
                        "makes the session's trades not directly comparable "
                        "with previous ones, so it is recorded in the startup "
                        "log and in every SKIPPED_CONCURRENCY_CAP row.")
    p.add_argument("--strategy", nargs="+", default=["mcl"],
                   help="one or more strategies to run in THIS process, in "
                        "priority order. They share one position book and one "
                        "MAX_CONCURRENT_POSITIONS cap, because they share one "
                        "account -- and the earlier one takes the last free "
                        "slot. Two processes would each see half the account.")
    notify.add_batch_arg(p)
    p.add_argument("--no-summary", action="store_true",
                   help="skip the end-of-session Telegram summary")
    p.add_argument("--no-telegram", action="store_true",
                   help="run without notifications even if configured")
    p.add_argument("--dry-run", action="store_true",
                   help="evaluate and log signals but place no orders")
    p.add_argument("--allow-empty", action="store_true",
                   help="accepted and ignored — starting empty is now the default, "
                        "since the watchlist is cleared at the end of each session")
    p.add_argument("--no-archive", action="store_true",
                   help="do not archive and clear the watchlist at session end")
    p.add_argument("--force-archive", action="store_true",
                   help="archive and clear even if the session ended early "
                        "(normally an early Ctrl-C leaves the watchlist alone)")
    p.add_argument("--sleep-on-exit", action="store_true",
                   help="put this PC to sleep after the session ends (Windows). "
                        "Refuses while a position is open; Ctrl-C cancels the countdown.")
    p.add_argument("--sleep-delay-min", type=int, default=20,
                   help="minutes to wait after the session before sleeping (default 20, "
                        "which leaves time to read the log or for Claude to review it)")
    return p


def main(argv: list[str] | None = None):
    p = build_parser()
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
