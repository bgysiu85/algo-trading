#!/usr/bin/env python3
"""H60 friction -- three levels, in dollars per trade. W14-0003,
REGISTERED_h60_v0.md §2.4. Source: claude/swing_g2_RESULT_20260919.md
(§0 all-in median, §3 the half-hour table), measured on this universe.

    L1 flat     5.46 bps round trip of notional (half on each leg)
    L2 scoring  half the quoted spread of the half-hour the fill is in, each
                leg, + IBKR tiered commission and fees per order
                (common.commissions.order_cost), + one extra half-spread on
                every stop fill (a stop sells through the bid)
    L3 stress   L2 with every spread part doubled

WHICH HALF-HOUR A FILL IS IN
----------------------------
    open fill      the half-hour the bar OPENS in
    close fill     the LAST half-hour of the bar (the 15:30 bar -> 15:30)
    intrabar fill  the WIDER of the bar's half-hours -- the engine cannot see
                   when inside the hour a stop or target traded, so it is
                   charged the more expensive of the two it could have been

COMMISSION, VECTORISED
----------------------
The random-entry control prices every (symbol, bar) pair a draw could pick --
millions of round trips. `tiered_vec` is common.commissions.tiered_cost's
arithmetic on arrays; tests/strategy/h60/test_h60_costs_basket.py pins it to
`order_cost(..., "ibkr_tiered")` over a grid of sizes and prices, so the two
cannot drift without a failing test.
"""
from __future__ import annotations

import numpy as np

from common import commissions as CM
from strategy.h60.bars import BARS_PER_SESSION, half_hours
from strategy.h60.exits import PH_CLOSE, PH_INTRA, PH_OPEN

ALL_IN_BPS = 5.46

# ET half-hour start (minute of day) -> median quoted spread, bps (G2 §3)
SPREAD_BPS = {
    570: 7.98, 600: 4.58, 630: 4.01, 660: 3.94, 690: 3.61, 720: 3.31,
    750: 3.21, 780: 3.04, 810: 3.04, 840: 3.31, 870: 3.04, 900: 3.03,
    930: 2.96,
}
COMMISSION_PLAN = "ibkr_tiered"


def fill_spread_bps(slot: int, phase: int, grid: str) -> float:
    hh = half_hours(slot, grid)
    if phase == PH_OPEN:
        return SPREAD_BPS[hh[0]]
    if phase == PH_CLOSE:
        return SPREAD_BPS[hh[-1]]
    if phase == PH_INTRA:
        return max(SPREAD_BPS[x] for x in hh)
    raise ValueError(f"unknown phase {phase!r}")


def spread_table(grid: str) -> np.ndarray:
    """[slot, phase] -> bps."""
    t = np.zeros((BARS_PER_SESSION, 3))
    for s in range(BARS_PER_SESSION):
        for p in (PH_OPEN, PH_INTRA, PH_CLOSE):
            t[s, p] = fill_spread_bps(s, p, grid)
    return t


def tiered_vec(qty, price, is_sell: bool) -> np.ndarray:
    """common.commissions.tiered_cost(...).total, removing liquidity, on arrays."""
    q = np.asarray(qty, float)
    p = np.asarray(price, float)
    value = q * p
    comm = np.minimum(np.maximum(CM.TIERED_PER_SHARE * q, CM.TIERED_MIN_ORDER),
                      CM.TIERED_MAX_PCT * value)
    exch = np.where(p >= 1.0, CM.TIERED_REMOVE_PER_SHARE * q,
                    CM.TIERED_REMOVE_SUB_DOLLAR_PCT * value)
    clear = CM.TIERED_CLEARING_PER_SHARE * q
    passthru = comm * CM.TIERED_PASSTHROUGH
    reg = CM.CAT_FEE_PER_SHARE * q
    if is_sell:
        reg = reg + CM.SEC_FEE_PCT_OF_SALES * value + CM.FINRA_TAF_PER_SHARE_SOLD * q
    total = comm + exch + clear + passthru + reg
    return np.where(q > 0, total, 0.0)


def trade_costs(qty, entry_px, exit_px, entry_slot, exit_slot, exit_phase,
                stop_fill, grid: str) -> dict:
    """Per-trade L1 / L2 / L3 in dollars (arrays in, arrays out). Entries
    always fill at a bar's open."""
    qty = np.asarray(qty, dtype=np.int64)
    ep = np.asarray(entry_px, float)
    xp = np.asarray(exit_px, float)
    n_in, n_out = qty * ep, qty * xp
    l1 = (ALL_IN_BPS / 2.0 / 1e4) * (n_in + n_out)
    tab = spread_table(grid)
    s_in = tab[np.asarray(entry_slot, int), PH_OPEN]
    s_out = tab[np.asarray(exit_slot, int), np.asarray(exit_phase, int)]
    half_in = n_in * s_in / 2.0 / 1e4
    half_out = n_out * s_out / 2.0 / 1e4
    extra = np.where(np.asarray(stop_fill, bool), half_out, 0.0)
    spread = half_in + half_out + extra
    comm = tiered_vec(qty, ep, False) + tiered_vec(qty, xp, True)
    return {"L1": l1, "L2": spread + comm, "L3": 2.0 * spread + comm,
            "spread_L2": spread, "commission": comm}


def financing(notional, nights, rate: float = 0.0713, borrowed: float = 0.5):
    """The 2:1 levered line (reported, never scored): half the position is
    borrowed at IBKR AU's 7.13%/yr, charged per calendar night held -- the
    G2 result's 0.99 bps of position per day."""
    return np.asarray(notional, float) * borrowed * rate * np.asarray(nights) / 365.0
