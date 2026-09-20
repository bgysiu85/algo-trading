#!/usr/bin/env python3
"""Every fixed value the TSMOM engine uses, with where it was registered.

Nothing in this file is chosen from a measurement of returns. Each value comes
from `docs/research/REGISTERED_tsmom.md` section 2 (the spec table), section 0.2
(amendment C, which contract is held) or `claude/tsmom_spec_20260917.md`. A
change here is a PRE-RUN amendment with a reason that does not mention a return,
or it is a new hypothesis (REGISTERED_tsmom section 9).
"""
from __future__ import annotations

from dataclasses import dataclass

# --- signal, vol, sizing: REGISTERED_tsmom section 2 ------------------------

# Equal-weight ensemble over k in {3, 6, 9, 12} months is THE deployed spec.
ENSEMBLE_KS: tuple[int, ...] = (3, 6, 9, 12)
# Section 3 item 11: the lookback grid the ensemble is placed in. 36/48 are
# excluded for the reason stated there (warm-up would eat the sample).
LOOKBACK_GRID: tuple[int, ...] = (1, 3, 6, 9, 12, 24)

# MOP eq. (1): centre of mass 60 days -> delta = 60/61; com=60 in pandas.
EWMA_COM = 60
DELTA = 60 / 61
ANNUALISE = 261            # MOP p. 233: 261, not 252
WARMUP_RETURNS = 261       # spec section 1.2 [D]: an instrument enters after 261 returns
TARGET_VOL = 0.40          # MOP p. 236: 40% ex-ante per position

# Spec section 1.4 [D]: five sleeves, rebalanced on these trading days of the month.
TRANCHE_DAYS: tuple[int, ...] = (1, 5, 9, 13, 17)

# Spec section 4 rule 1 and amendment C: roll N trading days before the event.
ROLL_OFFSET_SESSIONS = 5

# Spec section 6: USD per (vehicle) contract per side.
FRICTION: dict[str, float] = {"low": 0.50, "mid": 1.25, "high": 2.50}


# --- the instruments: spec section 2.2, amendment C, G3 -----------------------

@dataclass(frozen=True)
class Root:
    """One signal root.

    point_value : USD per 1.00 of quoted price, FULL-SIZE contract (CME).
    vehicle     : what would be traded; P/L and integer sizing are in vehicle
                  contracts, `fraction` of the full-size contract.
    rule        : "front"  -- front month, rolled ROLL_OFFSET sessions before
                              its expiration (spec section 4 rule 1);
                  "cycle"  -- nearest contract in `cycle` whose delivery month
                              has not begun, rolled ROLL_OFFSET sessions before
                              the first business day of its delivery month
                              (amendment C, REGISTERED_tsmom section 0.2).
    """
    name: str
    point_value: float
    vehicle: str
    fraction: float
    rule: str = "front"
    cycle: tuple[int, ...] = ()

    @property
    def vehicle_point_value(self) -> float:
        return self.point_value * self.fraction


_CORE = (
    Root("ES", 50.0, "MES", 0.1),
    Root("RTY", 50.0, "M2K", 0.1),
    Root("GC", 100.0, "MGC", 0.1, "cycle", (2, 4, 6, 8, 10, 12)),
    Root("SI", 5000.0, "SIL", 0.2, "cycle", (3, 5, 7, 9, 12)),      # Jan NOT held (amendment C)
    Root("HG", 25000.0, "MHG", 0.1, "cycle", (3, 5, 7, 9, 12)),
    Root("CL", 1000.0, "MCL", 0.1),
    Root("NG", 10000.0, "MNG", 0.1),
    Root("6E", 125000.0, "M6E", 0.1),
    Root("6A", 100000.0, "M6A", 0.1),
    Root("6B", 62500.0, "M6B", 0.1),
    Root("6J", 12500000.0, "MJY", 0.1),
)
CORE: dict[str, Root] = {r.name: r for r in _CORE}

# The three rates arms of spec section 2.3, reported side by side and UNRANKED
# (REGISTERED_tsmom section 3 item 13). G3 chose (b) as the one that would be
# traded; that choice does not rank the arms and is not read from them.
RATES_ARMS: dict[str, Root | None] = {
    "a_ZN": Root("ZN", 1000.0, "ZN", 1.0, "cycle", (3, 6, 9, 12)),
    "b_MTN": Root("TN", 1000.0, "MTN", 0.1, "cycle", (3, 6, 9, 12)),   # signal and P/L from TN; MTN = TN/10
    "c_none": None,
}
TRADED_ARM = "b_MTN"   # G3, Ben 2026-09-19: "let's go with option b then"

ALL_ROOTS: dict[str, Root] = {**CORE, "ZN": RATES_ARMS["a_ZN"], "TN": RATES_ARMS["b_MTN"]}

# Registered dataset. Every report reads it out of the archive manifest and
# refuses anything else (REGISTERED_tsmom section 8).
DATASET = "GLBX.MDP3"


def book_roots(arm: str) -> dict[str, Root]:
    """The instruments in one arm's book: the eleven core roots plus the arm."""
    if arm not in RATES_ARMS:
        raise KeyError(f"unknown rates arm {arm!r}; registered: {sorted(RATES_ARMS)}")
    roots = dict(CORE)
    extra = RATES_ARMS[arm]
    if extra is not None:
        roots[extra.name] = extra
    return roots
