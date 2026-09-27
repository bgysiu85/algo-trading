#!/usr/bin/env python3
"""Every fixed value the TL-v0 step-4 engine uses, with where it was registered.

Nothing here is chosen from a measurement of returns. A change is a PRE-RUN
amendment to docs/research/REGISTERED_tl_v0.md with a reason that does not
mention a result, or it is a new hypothesis (section 9).

MARKETS (section 2.1: "the TSMOM archive's roots as registered there; the
rates arm as chosen at TSMOM G3 (MTN, signal from TN)")
-----------------------------------------------------------------------------
The eleven TSMOM core roots plus the MTN arm = 12 markets. ZN is TSMOM's rates
arm (a), an ALTERNATIVE to (b) MTN, not a thirteenth market. The pre-flight
(common/tl_v0_preflight.py) carried ZN as a 13th row; the registration's own
market line does not, so the backtest follows the registration. See
Amendment A in the registration.

VEHICLE (what is sized and charged) follows section 5's micro list: MES, M2K,
MCL, MGC, SIL, MHG, M6A, M6B, M6E, and MTN for the rates arm. NG and 6J have no
micro in that list and are sized in FULL contracts, as the pre-flight did.

TICK (one tick of slippage on every stop fill, section 2.1) is the VEHICLE's
minimum tick in dollars (CME contract specs). MTN's tick is taken as TN's
1/64-point tick scaled to the micro's $100/point -- flagged in the report as
the one value not read off a published micro spec.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.tsmom.registry import CORE, RATES_ARMS, Root


@dataclass(frozen=True)
class Market:
    name: str            # the market as reported ("MTN" for the rates arm)
    signal_root: str     # the archive root whose bars are read ("TN" for MTN)
    vehicle: str
    mult: float          # $ per 1.00 of quoted price, ONE vehicle contract
    tick_usd: float      # $ per tick, ONE vehicle contract
    root: Root           # TSMOM roll-rule definition (front / cycle + cycle months)
    note: str = ""


def _m(name, signal_root, vehicle, mult, tick_usd, root, note=""):
    return Market(name, signal_root, vehicle, float(mult), float(tick_usd), root, note)


MARKETS: dict[str, Market] = {m.name: m for m in (
    _m("ES", "ES", "MES", 5, 1.25, CORE["ES"]),
    _m("RTY", "RTY", "M2K", 5, 0.50, CORE["RTY"]),
    _m("CL", "CL", "MCL", 100, 1.00, CORE["CL"]),
    _m("NG", "NG", "NG", 10_000, 10.00, CORE["NG"], "full contract (no micro in sec 5)"),
    _m("6A", "6A", "M6A", 10_000, 1.00, CORE["6A"]),
    _m("6B", "6B", "M6B", 6_250, 0.625, CORE["6B"]),
    _m("6E", "6E", "M6E", 12_500, 1.25, CORE["6E"]),
    _m("6J", "6J", "6J", 12_500_000, 6.25, CORE["6J"], "full contract (no micro in sec 5)"),
    _m("GC", "GC", "MGC", 10, 1.00, CORE["GC"]),
    _m("SI", "SI", "SIL", 1_000, 5.00, CORE["SI"]),
    _m("HG", "HG", "MHG", 2_500, 1.25, CORE["HG"]),
    _m("MTN", "TN", "MTN", 100, 100 / 64, RATES_ARMS["b_MTN"],
       "signal+P/L on TN's held contract x $100/pt; MTN listed 2024-03-25, so "
       "2010-2021 describes the signal, not an executable history; tick assumed "
       "= TN's 1/64 pt"),
)}

# --- rules: REGISTERED_tl_v0 section 2 -------------------------------------
PIVOT_SIZES: tuple[int, ...] = (3, 5, 8)      # ensemble L = R, equal risk
RULESETS: tuple[str, ...] = ("v0", "v0-rev")  # unranked; v0-rev is the holdout candidate
BREAK_BUF = 0.10                              # x ATR(14), action line (lives in common/tl_v0_lines)
STOP_BUF = 0.25                               # x ATR(14), safety line and fallback
ATR_LEN = 14

# --- sizing and friction: section 2.1, section 3 item 9 ---------------------
RISK_PCT = 0.01                               # 1% of equity per trade
EQUITY = 22_129.0                             # the account (TSMOM spec sec 3; W01-0005 scope)
EQUITIES: tuple[float, ...] = (22_129.0, 100_000.0, 500_000.0)
FRICTION: dict[str, float] = {"low": 0.50, "mid": 1.25, "high": 2.50}   # $/contract/side
LEVELS: tuple[str, ...] = ("low", "mid", "high")

# --- controls: section 3 item 6 ----------------------------------------------
DONCHIAN_ENTRY = 20
DONCHIAN_EXIT = 10
CHANDELIER_ATR = 3.0
TSMOM_LOOKBACK = 252                          # 12 months of sessions

# --- training window: section 5 / section 6 -----------------------------------
TRAIN_START = "2010-06-01"

# --- reporting ----------------------------------------------------------------
N_BOOT = 2_000
SEED = 20260927
MC_PATHS = 5_000                              # Davey MC (reported only)
DAVEY_DD_PAUSE = 0.10                         # 10% of EQUITY -> $2,213
