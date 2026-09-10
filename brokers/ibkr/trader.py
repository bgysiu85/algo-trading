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

from common import notify
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


# The shared fields, delegated below. Named once so the property pairs and the
# test that checks them cannot drift apart.
_FEED_FIELDS = ("contract", "ticker", "min_tick", "blocked",
                "bars_df", "bars_minute", "bars_fetched_at")


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

    def __post_init__(self):
        if self.feed is None:
            self.feed = SymbolFeed(symbol=self.symbol)


def _delegate(name: str):
    return property(lambda self: getattr(self.feed, name),
                    lambda self, v: setattr(self.feed, name, v))


for _f in _FEED_FIELDS:
    setattr(SymbolState, _f, _delegate(_f))
del _f


def drop_forming_bar(df: "pd.DataFrame") -> "pd.DataFrame":
    """Hand back only bars that have closed.

    Every strategy here acts on a CLOSED bar, so the minute in progress must
    not reach evaluate_last_bar: acting on a partial bar is H1 in
    claude/multi_strategy_trader_spec.md and shows up in a backtest as an
    edge that does not exist live.

    THIS IS A FUNCTION AND NOT ONE INLINE LINE because it embeds an assumption
    about IB that nothing had ever checked -- that the response INCLUDES the
    forming minute. If IB instead returns only completed bars, this discards a
    good one and every entry is a minute late. common/bar_freshness.py measures
    which it is, and measures it by calling THIS, so the probe cannot drift
    from what the trader really does.
    """
    return df.iloc[:-1] if len(df) > 1 else df


def parse_watchlist(path: Path) -> list[str]:
    """One ticker per line. Blank lines and # comments ignored, including
    trailing comments — `UPC  # added 05:55, rank 1` yields `UPC`, so the file
    can carry provenance for each pick (the scanner writes it that way)."""
    if not path.exists():
        return []
    out, seen = [], set()
    for ln in path.read_text().splitlines():
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
    "reject_reason",        # populated only when IB refused the order outright
    "macd", "macd_sig", "mfi", "rsi", "vol", "prev_vol", "trail_avg",
]


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
                with path.open("r", newline="") as fh:
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

        self.fh = path.open("a", newline="")
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
                 max_positions: int | None = None):
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
        # IB delivers the real rejection reason on the error event, not in
        # trade.log — without this we only ever see "Inactive".
        self._errors: dict[int, str] = {}
        self.ib.errorEvent += self._on_error

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
        st.contract = qualified[0]

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
            lines = self.watchlist.read_text().splitlines()
            out, changed = [], False
            for ln in lines:
                bare = ln.split("#", 1)[0].strip().upper()
                if bare == st.symbol:
                    out.append(f"# {ln.strip()}   <-- BLOCKED {now_et_str()}: {short}")
                    changed = True
                else:
                    out.append(ln)
            if changed:
                self.watchlist.write_text("\n".join(out) + "\n")
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
        self._wl_mtime = mtime

        wanted = set(parse_watchlist(self.watchlist))
        if not wanted and first:
            return

        for sym in wanted - self.symbols:
            await self._subscribe(sym)

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
            rows = list(csv.DictReader(self.log.path.open(newline="")))
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

    async def prepare(self):
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

        df = await self._fetch_bars(st)
        st.bars_fetched_at = time.monotonic()
        if df is not None:
            st.bars_df = df
            st.bars_minute = (now.hour, now.minute)
        return st.bars_df

    async def _fetch_bars(self, st: SymbolState) -> pd.DataFrame | None:
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
        return drop_forming_bar(df)

    # -- order placement --------------------------------------------------

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
                           status="NO_QUOTE", **detail)
            return None

        cross = base * (LIMIT_CROSS_BPS / 10_000.0)
        raw = base + cross if action == "BUY" else base - cross
        limit = round_to_tick(raw, action, st.min_tick)

        row = dict(ts_et=now_et_str(), strategy=self._name_of(st),
                   symbol=st.symbol, action=action, reason=reason,
                   ref_close=ref_close, ref_kind=ref_kind, bid=bid, ask=ask,
                   spread=spread, spread_pct=spread_pct, limit_sent=limit,
                   qty=qty, **detail)

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
        while asyncio.get_event_loop().time() - t0 < ORDER_TIMEOUT_S:
            await asyncio.sleep(0.25)
            if trade.isDone():
                break

        filled = int(sum(f.execution.shares for f in trade.fills))
        status = trade.orderStatus.status

        # An order IB never worked (Read-Only API on, outside-RTH refused, no
        # permissions) reports as Inactive/ApiCancelled with no fill. That is a
        # configuration failure, not thin liquidity, and must not be recorded as
        # a no-fill — it would poison the fill-rate measurement.
        if not filled and status in ("Inactive", "ApiCancelled", "Cancelled"):
            # The real reason arrives on the error event; trade.log is often empty.
            why = (self._errors.pop(order.orderId, "")
                   or "; ".join(e.message for e in trade.log if e.message)
                   or status)
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

            # A partial fill leaves the remainder working. Cancel it, or the
            # position on the book drifts away from the position in this script.
            if filled < qty:
                self.ib.cancelOrder(order)
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

        self.ib.cancelOrder(order)
        LOG.warning("%s %s NO FILL in %ds at limit %.4f — cancelled",
                    action, st.symbol, ORDER_TIMEOUT_S, limit)
        self.log.write(status="NO_FILL_CANCELLED", filled_qty=0, **row)
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
            reason = "apex_reversal"
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

        ref, ref_kind = self._exit_reference(pos, reason, bar_close, last_price)
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
            bar_high = None
            if last_ts > st.position.entry_time:
                bar_high = float(df["high"].iloc[-1])
            await self.manage_position(st, now_et, bar_close=sig.close,
                                       detail=detail, bar_high=bar_high,
                                       exit_signal=sig.exit_signal)
            return

        # ---- look for an entry -----------------------------------------
        if st.retired:
            return                      # removed from the watchlist
        if not self.in_session(now_et, st.strategy):
            return
        if st.last_bar_ts == last_ts:
            return                      # already evaluated this bar
        st.last_bar_ts = last_ts

        if not sig.long_entry:
            return

        # Portfolio-level gate. Everything above this point is about THIS
        # symbol; this is the only check that looks at the account as a whole.
        # The bar is already marked evaluated above, which is correct: the
        # signal fired and we declined it, so it should not be reconsidered.
        # ACROSS EVERY STRATEGY. A cap that counted only its own would be two
        # caps of two on an account sized for two -- and the account is shared,
        # so the second strategy would be spending buying power the first
        # already committed.
        open_now = sum(1 for s in self.states.values() if s.position is not None)
        if open_now >= self.max_positions:
            LOG.info("%s %s entry signal declined — %d position(s) already open "
                     "(cap %d): %s", st.strategy.name, st.symbol, open_now,
                     self.max_positions,
                     ", ".join(sorted(
                         f"{s.strategy.name}:{s.symbol}"
                         for s in self.states.values()
                         if s.position is not None)))
            self.log.write(ts_et=now_et.strftime("%Y-%m-%d %H:%M:%S"),
                           strategy=self._name_of(st),
                           symbol=st.symbol, action="BUY",
                           reason="entry_signal", ref_close=round(sig.close, 4),
                           ref_kind="signal_close",
                           status="SKIPPED_CONCURRENCY_CAP",
                           reject_reason=f"{open_now} open, cap "
                                         f"{self.max_positions}",
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

        res = await self.marketable_limit(st, "BUY", qty, sig.close,
                                          "entry_signal", detail,
                                          ref_kind="signal_close")
        if res:
            avg, filled = res
            # The trail travels with the POSITION, not with whichever strategy
            # module happens to be imported. H2 in the spec: MCL and MC5 are
            # both at 5.0 today, so reading the wrong one is invisible until
            # the day one of them changes.
            st.position = Position(symbol=st.symbol, qty=filled, entry_price=avg,
                                   entry_time=now_et, peak=max(avg, sig.close),
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
            await asyncio.sleep(LOOP_SLEEP_S)

        open_pos = [s.symbol for s in self.states.values() if s.position]
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
        LOG.info("  fill log      : %s", self.log.path)
        LOG.info("=" * 60)

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
                            max_positions=getattr(args, "max_positions", None))
    # Read the cap back OFF THE TRADER rather than off the constant or the
    # argument. Those can drift from what is running; this cannot.
    LOG.info("strategies: %s (one book, cap %d across all of them)%s",
             ", ".join(a.name for a in strategies), trader.max_positions,
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
    p.add_argument("--max-positions", type=int, default=None,
                   help="open positions allowed ACROSS ALL strategies "
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
