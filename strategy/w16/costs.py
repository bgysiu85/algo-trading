#!/usr/bin/env python3
"""W16 session-baselines friction, in dollars per contract per side.
REGISTERED_w16_session_baselines.md sec 4 (gate G5) and Amendment A below.
Board W16-0003 subitem 3.

Three scored levels plus L0, all fixed dollar amounts per fill -- a futures
commission schedule is quoted per contract, not per dollar traded (same
convention as strategy/htf/costs.py):

    L0   nothing charged (replication controls only, sec 7.4)
    L1   NinjaTrader Free-plan all-in fee per side, 0 extra ticks (reported)
    L2   L1 PLUS 1 tick on every market or stop fill; target fills add 0
         ticks (THE SCORING LEVEL, sec 4 / sec 9)
    L3   L1 PLUS 2 ticks on every market or stop fill; target fills add 0
         ticks (criterion 6, sec 9 item 6)

WHAT COUNTS AS A "MARKET OR STOP FILL" VS A "TARGET FILL"
------------------------------------------------------------
Sec 4: ticks are added on "entries, stops, time exits, flat-at-close,
overnight entry/exit"; "Target limit fills: 0 ticks." Every one of those
still pays the L1 base commission -- the tick add-on is slippage on a fill
that has to cross the market to happen, not an extra fee; a resting limit
fill (the target) does not cross anything, so it pays commission only. This
module takes that as an explicit `fill_kind` argument rather than inferring
it from context, so a caller cannot get it right on one baseline and wrong
on another.

AMENDMENT A -- PRE-RUN, read live 2026-09-27 (gate G5; before sec 5 computes
any P&L -- G2's pre-flight reads no exit prices and no P&L, so this does not
follow a result)
------------------------------------------------------------------------------
Read from ninjatrader.com/pricing/commissions/ (page dated "as of August 14,
2026 ... updated quarterly" -- the same table W15's Amendment A read on
2026-09-25), which lists itemized exchange+NFA, clearing and commission fees
per contract, and an "all-in" figure that is their sum:

    Symbol  Product                    Exch+NFA  Clearing  Commission(Free)  All-in(Free)/side
    MES     Micro E-mini S&P 500       $0.36     $0.19     $0.39             $0.94
    MNQ     Micro E-mini NASDAQ-100    $0.36     $0.19     $0.39             $0.94
    ES      E-Mini S&P 500             $1.39     $0.19     $1.29             $2.87
    NQ      E-Mini NASDAQ 100          $1.39     $0.19     $1.29             $2.87

So sec 4's "low" friction level (NinjaTrader all-in fee, 0 ticks) is
$0.94/side for MES and MNQ, and $2.87/side for ES and NQ. Mid (L2) and high
(L3) add 1 and 2 ticks respectively (tick values below, already registered
in sec 2's table, independent of any live account reading). This is a plan
choice Ben makes independent of any backtest result -- moving to a paid
plan later (Lifetime/Monthly rates, same page) is a live-trading decision,
not a re-registration of this study.

Overnight margins (per micro, read live 2026-09-27, ninjatrader.com/
margin-details/), reported beside the account view (sec 5 item 7), never
scored: MES day $50.00 / maintenance $2,619.42 / initial $2,881.37; MNQ day
$100.00 / maintenance $4,329.42 / initial $4,762.37.
"""
from __future__ import annotations

# Tick size is 0.25 index points on every one of these four symbols (sec 2).
TICK_POINTS = 0.25

# $ per index point, per contract (sec 2's table).
POINT_VALUE = {"MES": 5.00, "MNQ": 2.00, "ES": 50.00, "NQ": 20.00}

# $ per tick, per contract -- POINT_VALUE * TICK_POINTS, kept as its own
# table (not derived at call time) so a test can pin the four numbers sec 2
# already registered, independent of POINT_VALUE * TICK_POINTS being right.
# Cross-checked against ninjatrader.com/margin-details/ 2026-09-27: MES
# "Tick 0.25 / $1.25", MNQ "Tick 0.25 / $0.50" -- matches.
TICK_VALUE = {"MES": 1.25, "MNQ": 0.50, "ES": 12.50, "NQ": 5.00}

# Amendment A, NinjaTrader Free plan, all-in (exch+NFA + clearing +
# commission), read 2026-09-27. See module docstring for the itemized
# breakdown.
ALL_IN_L1 = {"MES": 0.94, "MNQ": 0.94, "ES": 2.87, "NQ": 2.87}

# Amendment A, read 2026-09-27 from ninjatrader.com/margin-details/.
# Reported (sec 5 item 7), never read by any function below -- nothing here
# prices a trade off margin, only the account view quotes it beside equity.
OVERNIGHT_MARGIN = {
    "MES": {"day": 50.00, "maintenance": 2619.42, "initial": 2881.37},
    "MNQ": {"day": 100.00, "maintenance": 4329.42, "initial": 4762.37},
}

FRICTION_LEVELS = ("L0", "L1", "L2", "L3")
_TICKS_ADDED = {"L0": 0, "L1": 0, "L2": 1, "L3": 2}

FULL_TO_MICRO = {"ES": "MES", "NQ": "MNQ"}
MICRO_TO_FULL = {"MES": "ES", "MNQ": "NQ"}

FILL_KINDS = ("market_or_stop", "target")


def per_side(symbol: str, level: str, *, fill_kind: str = "market_or_stop") -> float:
    """Dollars charged for ONE fill (one side) of one contract, at one
    friction level. `fill_kind`: "market_or_stop" (entries, stops, time
    exits, flat-at-close, overnight entry/exit -- everything sec 4 lists
    except the target) adds the level's ticks; "target" (a resting limit
    fill) never adds ticks, at any level, but still pays the L1 commission
    -- see module docstring."""
    if symbol not in TICK_VALUE:
        raise ValueError(f"unknown symbol {symbol!r}; expected one of {sorted(TICK_VALUE)}")
    if level not in _TICKS_ADDED:
        raise ValueError(f"unknown friction level {level!r}; expected one of {FRICTION_LEVELS}")
    if fill_kind not in FILL_KINDS:
        raise ValueError(f"unknown fill_kind {fill_kind!r}; expected one of {FILL_KINDS}")
    if level == "L0":
        return 0.0
    base = ALL_IN_L1[symbol]
    if fill_kind == "target":
        return base
    return base + _TICKS_ADDED[level] * TICK_VALUE[symbol]


def trade_cost(symbol: str, level: str, *, entry_kind: str = "market_or_stop",
               exit_kind: str = "market_or_stop", qty: int = 1) -> float:
    """Total $ for one round-trip trade (one entry fill + one exit fill),
    each priced by its own fill_kind -- a B1 winner (market entry, target
    exit) and a B1 loser (market entry, stop exit) are NOT the same cost,
    so both kinds are taken explicitly rather than assumed to match."""
    if qty < 0:
        raise ValueError("qty must be >= 0")
    return (per_side(symbol, level, fill_kind=entry_kind)
            + per_side(symbol, level, fill_kind=exit_kind)) * qty


def pnl_dollars(symbol: str, entry_px: float, exit_px: float, direction: str,
                qty: int = 1) -> float:
    """Gross P&L in dollars for one trade's raw entry/exit prices. Long
    profits when exit > entry; short mirrors. `symbol` may be the micro or
    the full contract -- POINT_VALUE covers both."""
    if direction not in ("long", "short"):
        raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
    if symbol not in POINT_VALUE:
        raise ValueError(f"unknown symbol {symbol!r}; expected one of {sorted(POINT_VALUE)}")
    mult = POINT_VALUE[symbol]
    diff = (exit_px - entry_px) if direction == "long" else (entry_px - exit_px)
    return diff * mult * qty
