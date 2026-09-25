#!/usr/bin/env python3
"""HTF-Ben friction, in dollars per contract per side. W15-0004 step 7.
REGISTERED_htf_ben_v0.md sec 2.5 and Amendment A (2026-09-25, NinjaTrader
Free-plan published fees).

Three levels, MCL and CL, all fixed dollar amounts -- NOT bps of notional
(unlike the equity-basket studies in this repo, e.g. strategy/h60/costs.py):
a futures commission schedule is quoted per contract, not per dollar traded.

    low  = NinjaTrader Free-plan all-in fee, 0 ticks
    mid  = low + 1 tick   (headline level, REGISTERED sec 2.5)
    high = low + 2 ticks

TICK VALUE: $1/tick for MCL (1,000 bbl... no -- MCL is 100 bbl, tick $0.01 =
$1), $10/tick for CL (1,000 bbl, tick $0.01 = $10). These are the standard
CME-published tick values, already registered (sec 2.5's table) independent
of any live account reading.

WHAT IS CHARGED, AND WHEN (sec 2.5: "on every entry, stop fill, flat and
roll leg"): a full round-trip trade charges the per-side rate TWICE (entry +
exit), whatever the exit reason (initial stop, trailed stop, session flat,
data end). A roll that closes a position mid-trade (sec 2.1: "closed at the
last 1-hour close of the old contract and reopened at the first 1-hour open
of the new one, with a full round-trip cost charged") adds one more full
round trip (two more sides) on top of the trade's own entry/exit -- the
runner (this module's caller) is what knows a roll happened; this module
only prices however many sides it is told to price.
"""
from __future__ import annotations

TICK = 0.01
TICK_VALUE = {"MCL": 1.0, "CL": 10.0}
CONTRACT_MULT = {"MCL": 100.0, "CL": 1000.0}   # $ P&L per $1/bbl move, per contract

# Amendment A, NinjaTrader Free plan, all-in (exch+NFA + clearing + commission)
ALL_IN_LOW = {"MCL": 1.09, "CL": 2.99}

FRICTION_LEVELS = ("low", "mid", "high")
_TICKS_ADDED = {"low": 0, "mid": 1, "high": 2}


def per_side(symbol: str, level: str) -> float:
    """Dollars charged for ONE side (one fill) of one contract, at one
    friction level."""
    if symbol not in ALL_IN_LOW:
        raise ValueError(f"unknown symbol {symbol!r}; expected 'MCL' or 'CL'")
    if level not in _TICKS_ADDED:
        raise ValueError(f"unknown friction level {level!r}; expected one of {FRICTION_LEVELS}")
    return ALL_IN_LOW[symbol] + _TICKS_ADDED[level] * TICK_VALUE[symbol]


def round_trip_cost(symbol: str, level: str, *, n_round_trips: int = 1, qty: int = 1) -> float:
    """Total $ for `n_round_trips` full round trips (2 sides each) of `qty`
    contracts -- a plain trade is n_round_trips=1 (entry+exit); a trade that
    also crosses one roll is n_round_trips=2 (its own entry/exit, plus the
    roll's close-old/open-new leg, sec 2.1)."""
    if n_round_trips < 0 or qty < 0:
        raise ValueError("n_round_trips and qty must be >= 0")
    return per_side(symbol, level) * 2.0 * n_round_trips * qty


def pnl_dollars(symbol: str, entry_px: float, exit_px: float, direction: str, qty: int = 1) -> float:
    """Gross P&L in dollars for one trade's raw-series entry/exit prices
    (sec 2.1: P&L is booked on the actual held contract, never the
    back-adjusted series). Long profits when exit > entry; short mirrors."""
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
    mult = CONTRACT_MULT[symbol]
    diff = (exit_px - entry_px) if direction == "long" else (entry_px - exit_px)
    return diff * mult * qty
