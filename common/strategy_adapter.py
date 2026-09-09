#!/usr/bin/env python3
"""One interface the live trader can talk to, whichever strategy is running.

Stage 2 of claude/multi_strategy_trader_spec.md.

WHY AN ADAPTER RATHER THAN A SECOND IMPORT
------------------------------------------
brokers/ibkr/trader.py does `from strategy.mcl import mcl as S` and then reads
`S.TRAIL_PCT`, `S.SESSION_START`, `S.size_for` and nine other module
attributes. That is a perfectly good design for one strategy and has exactly
one failure mode for two: `S` is whichever module was imported last, and every
one of those reads silently answers for the wrong strategy.

The values MCL and MC5 disagree on today are the session window (they agree),
the price band (they agree) and the trail (they agree at 5.0). **That is the
danger, not the safety.** Every constant matching means a trader that reads
the wrong module produces correct-looking numbers until the day one of them
changes -- the same shape as USE_APEX_EXIT governing the backtest and not the
live path, which ran for three days.

So the trader stops reading a module and reads an adapter it was handed.

WHY THE REGISTRY IS EXPLICIT
----------------------------
The two `evaluate_last_bar` functions do not have the same signature -- MCL's
takes optional strategy overrides, MC5's requires the current time so it can
tell whether its 5-minute bucket has closed. This could be papered over by
inspecting signatures, or by adding an unused `now` to MCL. Both hide the
difference. The registry states each call site once, in full, where it can be
read.

WHAT THE TRADER STILL OWNS
--------------------------
Order placement, quotes, the position book, the concurrency cap. The adapter
answers "what does this strategy say about these bars, and what size and band
does it want" -- nothing about execution. `evaluate` owning the resample is
what lets the trader stay ignorant of bar size, and is what will let VW9 slot
in without the trader changing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import Callable

from strategy.mc5 import mc5 as MC5
from strategy.mcl import mcl as MCL


@dataclass(frozen=True)
class StrategyAdapter:
    """Everything the live path needs from a strategy, and nothing else."""

    name: str
    module: object
    bar_minutes: int
    session_start: dtime
    session_end: dtime
    price_min: float
    price_max: float
    enforce_band: bool
    trail_pct: float
    commission_plan: str
    _evaluate: Callable

    def evaluate(self, df, now):
        """The strategy's read of the last CLOSED bar, or None.

        `df` is always 1-minute bars, and `now` is always the current time. A
        strategy that trades a longer bar resamples and decides for itself
        whether one has closed -- see strategy/mc5/mc5.last_closed_bucket. The
        trader never learns what a 5-minute bar is.
        """
        return self._evaluate(df, now)

    def size_for(self, price: float) -> int:
        return self.module.size_for(price)

    def in_band(self, price: float) -> bool:
        """False only when the strategy enforces a band and price is outside
        it. A strategy with the band off trades anything, which is the
        behaviour ENFORCE_BAND=False has always meant."""
        if not self.enforce_band:
            return True
        return self.price_min <= price <= self.price_max


def _from_module(module, bar_minutes: int, evaluate: Callable) -> StrategyAdapter:
    """Read the constants OFF the strategy module, never restate them here.

    A copy of TRAIL_PCT in this file is a second source of truth that agrees
    with the first until someone changes one of them. Every field below is a
    read, so a strategy edit reaches the live path without a second edit -- and
    a test asserts that by changing a module constant and checking the adapter
    followed.
    """
    return StrategyAdapter(
        name=module.STRATEGY_NAME,
        module=module,
        bar_minutes=bar_minutes,
        session_start=module.SESSION_START,
        session_end=module.SESSION_END,
        price_min=module.PRICE_MIN,
        price_max=module.PRICE_MAX,
        enforce_band=module.ENFORCE_PRICE_BAND,
        trail_pct=module.TRAIL_PCT,
        commission_plan=module.COMMISSION_PLAN,
        _evaluate=evaluate,
    )


def mcl_adapter() -> StrategyAdapter:
    # `now` is unused: MCL trades 1-minute bars and the trader has already
    # dropped the forming one, so its last row is closed by construction.
    # Taking the argument and ignoring it keeps one interface; adding an
    # unused `now` to mcl.evaluate_last_bar itself would push the lie into the
    # strategy.
    return _from_module(MCL, 1, lambda df, now: MCL.evaluate_last_bar(df))


def mc5_adapter() -> StrategyAdapter:
    # `now` is REQUIRED here. MC5 trades 5-minute buckets and the trader's
    # 1-minute trim does not close a bucket -- see mc5.last_closed_bucket.
    return _from_module(MC5, MC5.BAR_MINUTES,
                        lambda df, now: MC5.evaluate_last_bar(df, now))


BUILDERS = {
    "mcl": mcl_adapter,
    "mc5": mc5_adapter,
}


def build(key: str) -> StrategyAdapter:
    try:
        return BUILDERS[key]()
    except KeyError:
        raise SystemExit(
            f"unknown strategy {key!r}; the live trader can run "
            f"{sorted(BUILDERS)}") from None


def build_all(keys) -> list[StrategyAdapter]:
    """In the order given. Order is not cosmetic: with a shared position book
    and a concurrency cap, the strategy evaluated first is the one that gets
    the last free slot."""
    return [build(k) for k in keys]
