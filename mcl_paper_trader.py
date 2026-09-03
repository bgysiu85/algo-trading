#!/usr/bin/env python3
"""
MCL (Momentum Confluence Long) — pre-market paper execution layer
=================================================================

Mirrors the V7 Pine strategy and executes it against an IBKR **PAPER** account
using marketable limit orders, which is the only order type IBKR accepts for US
stocks outside regular trading hours.

The point of this script is NOT to make money. It is to measure the gap between
the backtest's assumed fills (bar close, 1 tick slippage) and what actually
fills pre-market. Every signal is logged with the live bid/ask at signal time,
the limit sent, and the realised fill or no-fill.

SAFETY
------
This refuses to run against a live account. It checks both:
  1. the socket port is a known PAPER port, and
  2. the managed account id starts with "DU" (IBKR paper accounts).
Either check failing aborts before any market data or order is requested.

Strategy (must stay in sync with the Pine V7 script)
----------------------------------------------------
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
    python mcl_paper_trader.py --watchlist watchlist.txt
    python mcl_paper_trader.py --watchlist watchlist.txt --dry-run

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

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

ET = ZoneInfo("America/New_York")

# Paper ports only.  7496 / 4001 are LIVE and are deliberately excluded.
PAPER_PORTS = {7497: "TWS paper", 4002: "IB Gateway paper"}
LIVE_PORTS = {7496: "TWS LIVE", 4001: "IB Gateway LIVE"}

SESSION_START = dtime(4, 0)
SESSION_END = dtime(9, 30)

# Signal parameters — keep identical to the Pine script
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MFI_LEN = 14
RSI_LEN = 14
TREND_LOOKBACK = 3          # "rising" = value > value[3]
APEX_LOOKBACK = 20          # apex = 20-bar high is >= 1 bar behind
VOL_MULTIPLE = 3.0          # volume >= 3x previous bar
FLOOR_FRACTION = 0.5        # previous bar >= 50% of trailing average
FLOOR_AVG_LEN = 60          # trailing average window (bars)

TRAIL_PCT = 5.0             # trailing stop, % off the high since entry
MAX_SHARES = 100
MAX_EQUITY_PCT = 40.0

# Execution
LIMIT_CROSS_BPS = 20        # how far through the touch to price the limit (20bps)
ORDER_TIMEOUT_S = 20        # cancel and record a no-fill after this long
COMMISSION_RT = 2.00        # round-trip commission assumed in the Pine backtest
                            # ($1 per side); used only for the CSV's trade_pnl

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

PROBE_TIMEOUT_S = 6         # tradability whatIf probe; normally answers in <1s
LOOP_SLEEP_S = 1.0          # fast loop: trailing stop, off streaming quotes
BAR_MIN_INTERVAL_S = 20.0   # hard floor between history requests per symbol
MAX_SYMBOLS_SAFE = 6        # beyond this, 1 req/min/symbol approaches IB's cap
EMPTY_WARN_S = 120          # how often to repeat the 'watching nothing' warning
MIN_BARS_REQUIRED = MACD_SLOW + MACD_SIGNAL + 5

LOG = logging.getLogger("mcl")


# --------------------------------------------------------------------------
# Indicators — implemented to match Pine's definitions exactly
# --------------------------------------------------------------------------

def ema(s: pd.Series, length: int) -> pd.Series:
    """Pine ta.ema — standard exponential moving average."""
    return s.ewm(span=length, adjust=False).mean()


def rma(s: pd.Series, length: int) -> pd.Series:
    """Pine ta.rma — Wilder's smoothing.  Used by ta.rsi."""
    return s.ewm(alpha=1.0 / length, adjust=False).mean()


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = ema(close, MACD_FAST) - ema(close, MACD_SLOW)
    sig = ema(line, MACD_SIGNAL)
    return line, sig


def rsi(close: pd.Series, length: int = RSI_LEN) -> pd.Series:
    """Pine ta.rsi — RMA of gains / RMA of losses."""
    delta = close.diff()
    up = rma(delta.clip(lower=0.0), length)
    down = rma((-delta).clip(lower=0.0), length)
    rs = up / down.replace(0.0, pd.NA)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(down != 0.0, 100.0)


def mfi(high: pd.Series, low: pd.Series, close: pd.Series,
        volume: pd.Series, length: int = MFI_LEN) -> pd.Series:
    """Pine ta.mfi(hlc3, length)."""
    tp = (high + low + close) / 3.0
    raw = tp * volume
    diff = tp.diff()
    pos = raw.where(diff > 0, 0.0).rolling(length).sum()
    neg = raw.where(diff < 0, 0.0).rolling(length).sum()
    ratio = pos / neg.replace(0.0, pd.NA)
    return (100.0 - 100.0 / (1.0 + ratio)).fillna(50.0)


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


def rising(s: pd.Series, n: int = TREND_LOOKBACK) -> pd.Series:
    return s > s.shift(n)


def falling(s: pd.Series, n: int = TREND_LOOKBACK) -> pd.Series:
    return s < s.shift(n)


def past_apex(s: pd.Series, lookback: int = APEX_LOOKBACK,
              n: int = TREND_LOOKBACK) -> pd.Series:
    """Falling, and the rolling high is at least one bar behind the current bar.

    Mirrors Pine:  f_falling(src) and -ta.highestbars(src, lookback) >= 1
    """
    roll_max = s.rolling(lookback).max()
    high_is_now = s >= roll_max        # current bar IS the high -> not past apex
    return falling(s, n) & (~high_is_now)


# --------------------------------------------------------------------------
# Signal evaluation
# --------------------------------------------------------------------------

@dataclass
class Signals:
    long_entry: bool
    exit_signal: bool
    close: float
    detail: dict


def evaluate(df: pd.DataFrame) -> Signals | None:
    """Evaluate the strategy on the LAST CLOSED bar of df.

    df must have columns: open, high, low, close, volume, and be 1-minute bars
    in chronological order, already restricted to bars we want indicators built
    from (i.e. include pre-market).
    """
    if len(df) < MIN_BARS_REQUIRED:
        return None

    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]

    macd_line, macd_sig = macd(close)
    m = mfi(high, low, close, vol)
    r = rsi(close)

    prev_vol = vol.shift(1)
    # trailing average lagged one bar, so the floor never sees the current bar
    trail_avg = vol.rolling(FLOOR_AVG_LEN).mean().shift(1)

    c_macd = (macd_line > macd_sig) & (macd_line > 0)
    c_mfi = rising(m)
    c_rsi = rising(r)
    c_vol_mult = (vol >= prev_vol * VOL_MULTIPLE) & (prev_vol > 0)
    c_floor = (trail_avg > 0) & (prev_vol >= trail_avg * FLOOR_FRACTION)

    entry = c_macd & c_mfi & c_rsi & c_vol_mult & c_floor
    exit_sig = past_apex(macd_line) | past_apex(m) | past_apex(r)

    i = -1
    return Signals(
        long_entry=bool(entry.iloc[i]),
        exit_signal=bool(exit_sig.iloc[i]),
        close=float(close.iloc[i]),
        detail={
            "macd": round(float(macd_line.iloc[i]), 5),
            "macd_sig": round(float(macd_sig.iloc[i]), 5),
            "mfi": round(float(m.iloc[i]), 2),
            "rsi": round(float(r.iloc[i]), 2),
            "vol": int(vol.iloc[i]),
            "prev_vol": int(prev_vol.iloc[i]) if pd.notna(prev_vol.iloc[i]) else 0,
            "trail_avg": round(float(trail_avg.iloc[i]), 1) if pd.notna(trail_avg.iloc[i]) else 0.0,
            "c_macd": bool(c_macd.iloc[i]),
            "c_mfi": bool(c_mfi.iloc[i]),
            "c_rsi": bool(c_rsi.iloc[i]),
            "c_vol_mult": bool(c_vol_mult.iloc[i]),
            "c_floor": bool(c_floor.iloc[i]),
        },
    )


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
    exiting: str | None = None      # sticky: once we decide to exit, keep trying
    exit_attempts: int = 0
    def trail_level(self) -> float:
        return self.peak * (1.0 - TRAIL_PCT / 100.0)


@dataclass
class SymbolState:
    symbol: str
    contract: object = None
    ticker: object = None
    position: Position | None = None
    last_bar_ts: datetime | None = None
    blocked: bool = False           # set after a hard error; stops trading this name
    retired: bool = False           # removed from the watchlist; no new entries
    bars_df: object = None          # cached history (see bars(): IB paces requests)
    bars_minute: tuple | None = None
    bars_fetched_at: float = 0.0
    min_tick: float = 0.0           # from IB ContractDetails; 0 = fall back on price


def parse_watchlist(path: Path) -> list[str]:
    """One ticker per line. Blank lines and # comments ignored, including
    trailing comments — `UPC  # added 05:55, rank 1` yields `UPC`, so the file
    can carry provenance for each pick (mcl_scanner.py writes it that way)."""
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
    "ts_et", "symbol", "action", "reason",
    "ref_close",            # what the backtest would have filled at
    "bid", "ask", "spread", "spread_pct",
    "limit_sent", "qty",
    "fill_price", "filled_qty", "status",
    "slippage_vs_ref",      # fill - ref_close  (negative = worse for a buy)
    "seconds_to_fill",
    # -- round-trip result, written on the SELL row only --------------------
    "entry_price", "exit_price", "trade_pnl", "trade_pct", "hold_minutes",
    "reject_reason",        # populated only when IB refused the order outright
    "macd", "macd_sig", "mfi", "rsi", "vol", "prev_vol", "trail_avg",
]


class FillLog:
    def __init__(self, path: Path):
        self.path = path
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
    def __init__(self, ib: IB, watchlist: Path, log: FillLog, dry_run: bool):
        self.ib = ib
        self.watchlist = watchlist
        self.log = log
        self.dry_run = dry_run
        self.states: dict[str, SymbolState] = {}
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

    async def _subscribe(self, symbol: str) -> bool:
        st = SymbolState(symbol=symbol)
        self.states[symbol] = st
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

        for sym in wanted - set(self.states):
            await self._subscribe(sym)

        for sym, st in self.states.items():
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
        cap = self.equity * MAX_EQUITY_PCT / 100.0
        LOG.info("sizing: %d shares max, or %%%.0f of equity ($%s) — "
                 "the equity cap only bites above $%s/share",
                 MAX_SHARES, MAX_EQUITY_PCT, f"{cap:,.0f}", f"{cap / MAX_SHARES:,.2f}")

    # -- helpers ----------------------------------------------------------

    def in_session(self, now_et: datetime) -> bool:
        return SESSION_START <= now_et.time() < SESSION_END

    def size_for(self, price: float) -> int:
        if price <= 0:
            return 0
        by_equity = math.floor(self.equity * MAX_EQUITY_PCT / 100.0 / price)
        return max(0, min(MAX_SHARES, by_equity))

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
                durationStr="1 D",
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
        # drop the still-forming bar so we only ever act on closed bars
        return df.iloc[:-1] if len(df) > 1 else df

    # -- order placement --------------------------------------------------

    async def marketable_limit(self, st: SymbolState, action: str, qty: int,
                               ref_close: float, reason: str, detail: dict,
                               closing: "Position | None" = None):
        """Send a marketable limit order, outsideRth, and record what happened.

        IBKR does not accept market orders outside RTH for US stocks, so a
        marketable limit priced through the touch is the closest equivalent.

        `closing` is the position being exited, if any — its presence makes the
        row carry the completed round trip (entry, exit, P/L, hold time).
        """
        def round_trip(exit_px: float, filled: int) -> dict:
            if closing is None:
                return {}
            pnl = (exit_px - closing.entry_price) * filled - COMMISSION_RT
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
            self.log.write(ts_et=now_et_str(), symbol=st.symbol, action=action,
                           reason=reason, ref_close=ref_close, bid=bid, ask=ask,
                           spread=spread, spread_pct=spread_pct, qty=qty,
                           status="NO_QUOTE", **detail)
            return None

        cross = base * (LIMIT_CROSS_BPS / 10_000.0)
        raw = base + cross if action == "BUY" else base - cross
        limit = round_to_tick(raw, action, st.min_tick)

        row = dict(ts_et=now_et_str(), symbol=st.symbol, action=action, reason=reason,
                   ref_close=ref_close, bid=bid, ask=ask, spread=spread,
                   spread_pct=spread_pct, limit_sent=limit, qty=qty, **detail)

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
            self.log.write(status="FILLED" if filled == qty else "PARTIAL_FILL",
                           fill_price=avg, filled_qty=filled,
                           slippage_vs_ref=round(-slip, 4),
                           seconds_to_fill=round(elapsed, 2),
                           **round_trip(avg, filled), **row)
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
        if not force and now.time() < SESSION_END:
            LOG.info("stopped before %s — watchlist left untouched "
                     "(pass --force-archive to clear it anyway)",
                     SESSION_END.strftime("%H:%M"))
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

    async def manage_position(self, st: SymbolState, now_et: datetime,
                              ref_close: float, detail: dict,
                              bar_high: float | None = None,
                              exit_signal: bool = False) -> None:
        """Trail / window / apex exit for an open position.

        Called from two places, deliberately:
          * the fast loop, every second, off the streaming quote — this is the
            trailing stop, and it costs no API request;
          * the bar path, once a minute, which additionally supplies the apex
            exit signal and the bar high.

        Pine's `strategy.exit(stop=)` fills intrabar at the stop price. Nothing
        outside a backtest can do that, but a 1-second poll on live quotes is far
        closer than waiting for the bar to close.
        """
        pos = st.position
        if pos is None:
            return

        bid, ask = self.quote(st)
        last_price = ask if ask == ask else ref_close
        candidates = [pos.peak, last_price]
        if bar_high is not None:
            candidates.append(bar_high)
        pos.peak = max(candidates)

        if not self.in_session(now_et):
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

        res = await self.marketable_limit(st, "SELL", pos.qty, ref_close,
                                          reason, detail, closing=pos)
        if not res:
            return

        exit_px, sold = res
        pnl = (exit_px - pos.entry_price) * sold - COMMISSION_RT
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
        if st.blocked or st.contract is None:
            return

        df = await self.bars(st)
        if df is None or df.empty:
            return

        last_ts = df.index[-1].to_pydatetime()
        sig = evaluate(df)
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
            await self.manage_position(st, now_et, ref_close=sig.close,
                                       detail=detail, bar_high=bar_high,
                                       exit_signal=sig.exit_signal)
            return

        # ---- look for an entry -----------------------------------------
        if st.retired:
            return                      # removed from the watchlist
        if not self.in_session(now_et):
            return
        if st.last_bar_ts == last_ts:
            return                      # already evaluated this bar
        st.last_bar_ts = last_ts

        if not sig.long_entry:
            return

        qty = self.size_for(sig.close)
        if qty < 1:
            LOG.info("%s signal but size 0 (equity %.2f, price %.2f)",
                     st.symbol, self.equity, sig.close)
            return

        res = await self.marketable_limit(st, "BUY", qty, sig.close,
                                          "entry_signal", detail)
        if res:
            avg, filled = res
            st.position = Position(symbol=st.symbol, qty=filled, entry_price=avg,
                                   entry_time=now_et, peak=max(avg, sig.close))

    # -- main loop --------------------------------------------------------

    async def run(self):
        LOG.info("entering main loop — %s", "DRY RUN" if self.dry_run else "LIVE PAPER ORDERS")
        while not self._stop:
            now_et = datetime.now(ET)
            if now_et.time() >= SESSION_END and not any(s.position for s in self.states.values()):
                LOG.info("09:30 ET reached and flat — stopping")
                break
            # picks up edits to watchlist.txt mid-session, no restart needed
            try:
                await self.sync_watchlist()
                live = sum(1 for s in self.states.values()
                           if not s.retired and not s.blocked)
                if live == 0 and self.in_session(now_et):
                    if time.monotonic() - self._empty_warned_at >= EMPTY_WARN_S:
                        self._empty_warned_at = time.monotonic()
                        LOG.warning("still watching nothing — %s is empty. Add "
                                    "tickers (picked up within 5s) or start "
                                    "mcl_scanner.py.", self.watchlist.name)
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
                            st, now_et,
                            ref_close=st.position.entry_price,
                            detail={})
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
                    "(re-read every 5s) or start mcl_scanner.py.", wl)

    ib = IB()
    await ib.connectAsync(args.host, args.port, clientId=args.client_id)

    accounts = ib.managedAccounts()
    LOG.info("connected. accounts: %s", accounts)
    if not accounts or not all(a.startswith("DU") for a in accounts):
        ib.disconnect()
        sys.exit(f"REFUSING TO RUN: account(s) {accounts} do not look like IBKR "
                 f"paper accounts (expected ids starting 'DU').")

    log = FillLog(Path(args.out))
    trader = MCLPaperTrader(ib, wl, log, args.dry_run)

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
# Screen: $2-20 price, RVOL(1D) >= 5x, float < 20m, top pre-market gainer.
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


def main():
    p = argparse.ArgumentParser(description="MCL pre-market paper trader (IBKR)")
    p.add_argument("--watchlist", default="watchlist.txt",
                   help="file with today's qualifying tickers, one per line")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002,
                   help="4002 IB Gateway paper (default) or 7497 TWS paper")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--out", default=f"mcl_fills_{datetime.now(ET):%Y%m%d}.csv")
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
    args = p.parse_args()

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
