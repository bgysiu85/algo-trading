#!/usr/bin/env python3
"""IBKR futures costs for the W15-0022 methods (CRUDELE-3S, BREIT-CAP). W15-0033, Ben 2026-09-30:
"please use the IBKR costs as that will be the broker i'm using".

Per contract per SIDE, all-in = IBKR Pro commission (Fixed / Tiered <= 1,000 contracts a month) +
exchange fee (non-member tier) + regulatory fee (~$0.02: 0.011 regulatory + ~0.01 NFA). Published
rates read 2026-09-30 from interactivebrokers.com (/en/pricing/commissions-futures.php and
/en/accounts/fees/{CME,CBOT,COMEX,NYMEX}.php). Written into both registrations as a PRE-RUN amendment.

    vehicle      commission  exchange  reg    all-in
    MES, M2K       0.25       0.353    0.02    0.62
    M6A/B/E        0.25       0.24     0.02    0.51
    MTN            0.25       0.30     0.02    0.57
    MCL            0.25       0.50     0.02    0.77
    MGC, MHG       0.25       0.70     0.02    0.97
    SIL            0.25       0.70?    0.02    0.97   (IBKR's COMEX page does not list SIL: assumed
                                                       equal to the other COMEX micros; flagged)
    NG             0.85       1.60     0.02    2.47
    6J             0.85       1.60     0.02    2.47   (standard-size currency futures rate)

Levels (Ben's choice 2026-09-30, "Fee + 0/1/2 ticks", as the CHARTMARK registrations):
    low = all-in fee; mid (headline) = fee + 1 tick per side; high = fee + 2 ticks.
The tick is the vehicle's minimum tick in dollars. Slippage is therefore charged on EVERY fill at the
mid and high levels, and the old separate "1 tick on stop fills" is dropped (stop_slip_ticks = 0) so
slippage is not counted twice. Roll legs are charged two sides per contract, as before.
"""
from __future__ import annotations

from dataclasses import replace

from strategy.futbt.core import Frame, Venue
from strategy.tl_v0.spec import MARKETS

FEE_PER_SIDE = {
    "MES": 0.62, "M2K": 0.62, "M6A": 0.51, "M6B": 0.51, "M6E": 0.51, "MTN": 0.57,
    "MCL": 0.77, "MGC": 0.97, "MHG": 0.97, "SIL": 0.97, "NG": 2.47, "6J": 2.47,
}
ASSUMED = {"SIL": "not listed on IBKR's COMEX fee page; assumed equal to MGC / MHG ($0.70 exchange)"}
LEVEL_TICKS = {"low": 0, "mid": 1, "high": 2}


def venue_for(vehicle: str, tick_usd: float) -> Venue:
    fee = FEE_PER_SIDE[vehicle]
    return Venue({lv: round(fee + k * tick_usd, 4) for lv, k in LEVEL_TICKS.items()}, 0.0)


def with_ibkr(fr: Frame, vehicle: str | None = None) -> Frame:
    """The same frame with the IBKR venue. `vehicle` defaults to the market's registered vehicle
    (CL 4H is priced as one MCL)."""
    veh = vehicle or MARKETS[fr.market].vehicle
    return replace(fr, venue=venue_for(veh, fr.tick_usd))


def table() -> list[tuple]:
    """(market, vehicle, tick $, fee, low, mid, high) for the report header."""
    rows = []
    for name, m in MARKETS.items():
        v = venue_for(m.vehicle, m.tick_usd)
        rows.append((name, m.vehicle, m.tick_usd, FEE_PER_SIDE[m.vehicle], v.friction["low"],
                     v.friction["mid"], v.friction["high"]))
    return rows
