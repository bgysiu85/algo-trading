"""VA80 v1 costs: IBKR futures fees, REGISTERED_va80.md Amendment 2 (W15-0033, G5). Pure arithmetic, no data.

Per contract per SIDE, all-in = IBKR commission + exchange fee (non-member) + regulatory (~$0.02):
    MES / MNQ  0.62      ES / NQ  2.26
Levels (Ben, 2026-09-30: fee + 0 / 1 / 2 ticks): low = fee, mid (headline) = fee + 1 tick, high = fee + 2 ticks.
The ticks are slippage on a fill that has to cross the market, so they are charged on the entry (a market fill at the
bar open), the stop and the time exit -- and NOT on a resting target limit fill, which pays the fee only (W16 sec 4
convention, VA80 sec 2.4). 1 MES is the headline vehicle; 1 ES, 1 MNQ and 1 NQ are reported.

A trade carries `legs`: [(weight, gross_points, exit_reason), ...]. A plain trade has one leg of weight 1. A partial
exit (POC half, reported variant) has two legs of weight 0.5; costs and P&L scale with the weight.
"""
from __future__ import annotations

from strategy.va80 import spec as S

FEE_PER_SIDE = {"MES": 0.62, "MNQ": 0.62, "ES": 2.26, "NQ": 2.26}
POINT_VALUE = {"MES": 5.0, "MNQ": 2.0, "ES": 50.0, "NQ": 20.0}
TICK_VALUE = {"MES": 1.25, "MNQ": 0.50, "ES": 12.50, "NQ": 5.00}
LEVEL_TICKS = {"low": 0, "mid": 1, "high": 2}
FILL_KINDS = ("market_or_stop", "target")

# the vehicle that carries each scored / reported market (headline first)
HEADLINE = {"ES": "MES", "NQ": "MNQ"}
FULL = {"ES": "ES", "NQ": "NQ"}


def side_cost(vehicle: str, level: str, fill_kind: str) -> float:
    """Dollars for one fill of one contract: the fee, plus the level's ticks unless it is a resting target fill."""
    if fill_kind not in FILL_KINDS:
        raise ValueError(f"fill_kind must be one of {FILL_KINDS}, got {fill_kind!r}")
    ticks = LEVEL_TICKS[level]
    return FEE_PER_SIDE[vehicle] + (ticks * TICK_VALUE[vehicle] if fill_kind == "market_or_stop" else 0.0)


def exit_kind(reason: str) -> str:
    return "target" if reason == S.TARGET else "market_or_stop"


def trade_cost(vehicle: str, level: str, exit_reason: str, weight: float = 1.0) -> float:
    """Round trip: a market entry, then an exit of the kind the exit reason implies."""
    return weight * (side_cost(vehicle, level, "market_or_stop") + side_cost(vehicle, level, exit_kind(exit_reason)))


def legs_of(trade: dict) -> list:
    return trade.get("legs") or [(1.0, trade["gross_points"], trade["exit_reason"])]


def price_trade(trade: dict, vehicle: str, level: str) -> dict:
    """{'gross', 'cost', 'net'} in dollars for one trade (all its legs)."""
    gross = cost = 0.0
    for w, pts, why in legs_of(trade):
        gross += w * pts * POINT_VALUE[vehicle]
        cost += trade_cost(vehicle, level, why, w)
    return {"gross": gross, "cost": cost, "net": gross - cost}
