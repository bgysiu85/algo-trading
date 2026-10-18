#!/usr/bin/env python3
"""EXIT-CMP sec 13: the per-symbol table -- ONE place for tick, tick value, $ per point, IBKR fee and the rule distances.
W15-0053 sub 2 (gate G8). The live manager (sub 4) imports this module; no fee or tick is a constant anywhere else.

Rows MCL, CL, MES, ES, MNQ, NQ are as REGISTERED_exit_cmp.md sec 13. The others are the values already in the repo
(strategy/tl_v0/spec.py MARKETS for the point value and tick $, strategy/futbt/costs_ibkr.py FEE_PER_SIDE for the fee).
Only CL / MCL are backtested (sec 17); every other row is an UNVALIDATED parameter set.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVELS = ("low", "mid", "high")
_TICKS = {"low": 0, "mid": 1, "high": 2}

# CL / MCL rule distances (price, $/bbl): the ratchet arm (Ben: "$0.20/bbl price move") and the emergency stop
# distance (CHARTMARK-v2 K1 backstop). Other symbols scale these by volatility (sec 13).
CL_ARM = 0.20
CL_EMERGENCY = 0.60
VALIDATED = ("MCL", "CL")


@dataclass(frozen=True)
class Symbol:
    root: str
    point_usd: float      # $ per 1.00 of quoted price, one contract
    tick_usd: float       # $ per minimum tick, one contract
    fee: float            # IBKR Pro commission + exchange/regulatory, $ per contract per side

    @property
    def tick(self) -> float:
        """Minimum price increment."""
        return self.tick_usd / self.point_usd

    def per_side(self, level: str) -> float:
        """Fee plus 0 / 1 / 2 ticks of slippage on every fill (Ben, 2026-09-30)."""
        return self.fee + _TICKS[level] * self.tick_usd

    def round_trip(self, level: str) -> float:
        return 2 * self.per_side(level)


def _s(root, point, tick_usd, fee) -> Symbol:
    return Symbol(root, float(point), float(tick_usd), float(fee))


SYMBOLS: dict[str, Symbol] = {s.root: s for s in (
    _s("MCL", 100, 1.00, 0.77), _s("CL", 1000, 10.00, 2.37),
    _s("MES", 5, 1.25, 0.62), _s("ES", 50, 12.50, 2.26),
    _s("MNQ", 2, 0.50, 0.62), _s("NQ", 20, 5.00, 2.26),
    _s("M2K", 5, 0.50, 0.62), _s("MGC", 10, 1.00, 0.97), _s("SIL", 1000, 5.00, 0.97), _s("MHG", 2500, 1.25, 0.97),
    _s("M6A", 10_000, 1.00, 0.51), _s("M6B", 6250, 0.625, 0.51), _s("M6E", 12_500, 1.25, 0.51),
    _s("NG", 10_000, 10.00, 2.47), _s("6J", 12_500_000, 6.25, 2.47),
)}


def get(root: str) -> Symbol:
    """None of the manager's code may guess: a root outside the table is an error (sec 14 rail 7 alerts on it)."""
    try:
        return SYMBOLS[root]
    except KeyError:
        raise KeyError(f"{root!r} is not in the symbol table; the manager never touches it") from None


def arm_distance(root: str, atr_at_fill: float | None = None, median_cl_atr: float | None = None) -> float:
    """Ratchet arm, in price. CL / MCL: $0.20. Any other symbol: the CL value scaled by volatility,
    (0.20 / median CL 1H ATR(14)) x that symbol's 1H ATR(14) at the fill (sec 13)."""
    return _scaled(CL_ARM, root, atr_at_fill, median_cl_atr)


def emergency_distance(root: str, atr_at_fill: float | None = None, median_cl_atr: float | None = None) -> float:
    """Emergency stop distance, in price. CL / MCL: $0.60 (sec 13 / rail 3)."""
    return _scaled(CL_EMERGENCY, root, atr_at_fill, median_cl_atr)


def _scaled(cl_value: float, root: str, atr: float | None, med: float | None) -> float:
    get(root)
    if root in VALIDATED:
        return cl_value
    if atr is None or med is None or not med > 0:
        raise ValueError(f"{root}: a volatility-scaled distance needs its 1H ATR at the fill and the CL median ATR (G6)")
    return cl_value / med * atr
