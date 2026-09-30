#!/usr/bin/env python3
"""TL-v2 prices through the IBKR cost model, not TL-v0's flat friction.
REGISTERED_tl_v2.md Amendment 1 (PRE-RUN, 2026-09-30, W15-0033): Ben, "please use the IBKR costs as
that will be the broker i'm using".

    per contract per side, on EVERY fill:   low = IBKR all-in fee,  mid = fee + 1 tick,  high = fee + 2 ticks
    the separate "one tick on a stop fill" is dropped (it is inside mid / high; never counted twice)
    a roll charges two more sides per contract, as before

The table is strategy.futbt.costs_ibkr (the 12-market table of REGISTERED_crudele_3s.md Amendment C);
nothing is re-typed here. Booking is TL-v0's (strategy.tl_v0.pnl.book: the actual held contract, legs
checked against the adjusted move); only the dollars charged differ.
"""
from __future__ import annotations

import numpy as np

from strategy.futbt.costs_ibkr import venue_for
from strategy.tl_v0 import pnl
from strategy.tl_v0.spec import LEVELS, Market


def friction(m: Market) -> dict[str, float]:
    """{'low','mid','high'} $ per contract per side for this market's registered vehicle."""
    return dict(venue_for(m.vehicle, m.tick_usd).friction)


def net(b: pnl.Booked, level: str, qty: float, m: Market) -> float:
    return b.gross - friction(m)[level] * qty * b.sides


def daily(trades, booked, frame, m: Market) -> np.ndarray:
    return pnl.daily(trades, booked, frame, m, friction=friction(m), stop_slip=False)


__all__ = ["friction", "net", "daily", "LEVELS"]
