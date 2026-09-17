#!/usr/bin/env python3
r"""One symbol-day of the Stocks-in-Play ORB. No aggregates, no selection.

`docs/research/REGISTERED_orb_sip.md` sections 2 and 3 decide every rule here.
This module answers exactly one question -- given this name's RTH minute bars,
its opening range and its ATR, what trade happened -- and knows nothing about
universes, rankings or P/L books.

THE RULE (section 2)
--------------------
    direction   the opening-range candle: close > open -> long, close < open ->
                short, open == close -> NO ORDER (a doji is not a coin flip)
    entry       a stop order at the range high (long) or low (short), live from
                the first bar after the range until 15:59
    stop        10% x ATR(14) from the EXECUTED entry price
    exit        the stop, or the last bar's close

THE FILL MODEL (section 3.2), and it is ORB's, not a new one
------------------------------------------------------------
* A stop GAPS THROUGH. If the triggering bar opens beyond the trigger, the fill
  is that open and not the trigger price -- you cannot buy at a level the bar
  opened above. The same applies to the protective stop, which is why a fast
  reversal costs more than the registered risk.
* The trigger can first fire on the bar AFTER the range closes. `ts_event` is
  the interval start, so a 5-minute range ends with the 09:34 bar and 09:35 is
  the first bar that can execute.
* One entry per symbol-day.

THE ONE RULE THE PAPER DOES NOT STATE, decided here and recorded as amendment A
------------------------------------------------------------------------------
Can the protective stop be hit on the ENTRY BAR? The paper is silent, and on a
stop this tight (10% of ATR is $0.05-$0.30) the answer moves the result. A
minute bar does not say whether its low came before or after the entry print,
so either choice is an assumption:

    STOP_ON_ENTRY_BAR = True    the entry bar's low can stop the trade out
                                (conservative: assumes the worst ordering)
    STOP_ON_ENTRY_BAR = False   the stop is live from the next bar
                                (optimistic: assumes the favourable ordering)

The registered primary is True. False is reported beside it as a sensitivity,
never as the result -- see `REGISTERED_orb_sip.md` amendment A.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RTH_OPEN_MIN = 9 * 60 + 30
LAST_BAR_MIN = 15 * 60 + 59
STOP_FRAC = 0.10              # of ATR(14), section 2
STOP_ON_ENTRY_BAR = True      # amendment A

# Why a symbol-day produced no trade. Counted in every report: a strategy that
# cannot say what it did not trade is not measured.
NO_RANGE = "NO_RANGE"          # no bars inside the opening range
NO_BARS_AFTER = "NO_BARS_AFTER"
DOJI = "DOJI"
NO_TRIGGER = "NO_TRIGGER"
NO_ATR = "NO_ATR"
OK = "OK"

LONG, SHORT = 1, -1


@dataclass
class Trade:
    symbol: str
    date: str
    side: int
    entry_min: int
    entry_px: float
    exit_min: int
    exit_px: float
    exit_reason: str            # stop | session_end
    stop_px: float
    r: float                    # dollars per share at risk, = 10% x ATR
    bars_held: int
    or_high: float
    or_low: float

    @property
    def gross_per_share(self) -> float:
        return (self.exit_px - self.entry_px) * self.side


def direction(or_open: float, or_close: float) -> int:
    """+1 long, -1 short, 0 no order. Section 2's doji rule is an equality."""
    if or_close > or_open:
        return LONG
    if or_close < or_open:
        return SHORT
    return 0


def trade_symbol_day(symbol: str, date: str, minute, open_, high, low, close,
                     atr: float, or_minutes: int = 5,
                     stop_frac: float = STOP_FRAC,
                     stop_on_entry_bar: bool = STOP_ON_ENTRY_BAR):
    """(Trade, OK) or (None, reason). Arrays are one symbol-day's RTH bars."""
    minute = np.asarray(minute); open_ = np.asarray(open_, float)
    high = np.asarray(high, float); low = np.asarray(low, float)
    close = np.asarray(close, float)
    if not np.isfinite(atr) or atr <= 0:
        return None, NO_ATR

    end = RTH_OPEN_MIN + or_minutes
    in_range = minute < end
    if not in_range.any():
        return None, NO_RANGE
    ro, rc = open_[in_range][0], close[in_range][-1]
    side = direction(ro, rc)
    if side == 0:
        return None, DOJI
    or_high = float(high[in_range].max())
    or_low = float(low[in_range].min())

    after = np.flatnonzero(~in_range)
    if after.size == 0:
        return None, NO_BARS_AFTER

    trigger = or_high if side == LONG else or_low
    hit = (high[after] >= trigger) if side == LONG else (low[after] <= trigger)
    if not hit.any():
        return None, NO_TRIGGER
    i = after[int(np.argmax(hit))]

    # Gap through: a bar that opened beyond the trigger fills at its open.
    entry_px = max(trigger, open_[i]) if side == LONG else min(trigger, open_[i])
    stop_px = entry_px - side * stop_frac * atr
    r = abs(entry_px - stop_px)

    first = i if stop_on_entry_bar else i + 1
    exit_idx, exit_px, reason = len(minute) - 1, close[-1], "session_end"
    if first < len(minute):
        stopped = ((low[first:] <= stop_px) if side == LONG
                   else (high[first:] >= stop_px))
        if stopped.any():
            j = first + int(np.argmax(stopped))
            # The protective stop gaps through in the same direction as the
            # entry did: a bar that opened past it fills at the open.
            exit_px = (min(stop_px, open_[j]) if side == LONG
                       else max(stop_px, open_[j]))
            exit_idx, reason = j, "stop"

    return Trade(symbol=symbol, date=date, side=side,
                 entry_min=int(minute[i]), entry_px=float(entry_px),
                 exit_min=int(minute[exit_idx]), exit_px=float(exit_px),
                 exit_reason=reason, stop_px=float(stop_px), r=float(r),
                 bars_held=int(exit_idx - i), or_high=or_high,
                 or_low=or_low), OK


# --------------------------------------------------------------------------
# friction -- section 3.3, three levels, and the criteria are read at BASE
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Friction:
    name: str
    entry_cents: float
    stop_cents: float
    close_cents: float
    commission: str             # "paper" ($0.0035/share) | "tiered"


PAPER = Friction("PAPER", 0.0, 0.0, 0.0, "paper")
BASE = Friction("BASE", 0.01, 0.02, 0.01, "tiered")
HARSH = Friction("HARSH", 0.02, 0.04, 0.02, "tiered")
LEVELS = (PAPER, BASE, HARSH)
PAPER_PER_SHARE = 0.0035


def commission(shares: int, price: float, is_sell: bool, plan: str) -> float:
    if plan == "paper":
        return PAPER_PER_SHARE * shares
    from common.commissions import tiered_cost
    return tiered_cost(shares, price, is_sell).total


def net(trade: Trade, shares: int, fr: Friction) -> float:
    """Dollars after slippage and commission, for `shares` shares.

    Slippage is charged AGAINST the trade on both legs: an entry stop fills
    worse than its trigger, a protective stop fills worse than its level, and
    the closing exit crosses the spread. `execution_cost_measured.md` is why
    the stop leg carries twice the entry leg's cents.
    """
    exit_cents = fr.stop_cents if trade.exit_reason == "stop" else fr.close_cents
    entry = trade.entry_px + trade.side * fr.entry_cents
    exit_ = trade.exit_px - trade.side * exit_cents
    gross = (exit_ - entry) * trade.side * shares
    buy_px, sell_px = (entry, exit_) if trade.side == LONG else (exit_, entry)
    cost = (commission(shares, buy_px, False, fr.commission)
            + commission(shares, sell_px, True, fr.commission))
    return gross - cost
