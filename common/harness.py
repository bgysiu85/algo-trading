#!/usr/bin/env python3
"""One position lifecycle, shared by every strategy.

WHY THIS EXISTS
---------------
MCL, MC5 and VW9 each carry their own copy of the same loop: enter, trail,
stop, book the trade. The copies have drifted, and every result-inflating bug
this project has found lived in that loop rather than in any signal:

  * gap-through fills. Selling AT a level the market never offered. 48% of
    MC5's stop exits were affected; correcting it moved MC5 from +$20,156 to
    -$400 on IDENTICAL trades.
  * peak seeding from the entry bar's high, which happened BEFORE the close
    that was bought. It put the trail above the market at the instant of entry
    in 53% of MC5's stop exits.
  * stop-and-target inside one bar, where the order of resolution decides the
    sign of the trade.

Three strategies meant three chances to get those wrong and three places to fix
them. Six strategies would mean six. So the split here is:

    the STRATEGY decides which bars are entries    (and, optionally, exits)
    the HARNESS decides what happens to a position

A strategy hands over a frame with an `entry` column and gets Trades back. It
never writes fill logic again.

WHAT THIS IS NOT
----------------
It is not a rewrite of the existing strategies. MCL, MC5 and VW9 keep their own
loops, because rewriting a published result is how a published result quietly
changes. The harness is validated BY those loops instead: `tests/common/
test_harness_equivalence.py` runs MC5's own signals through both paths on real
cached bars and requires the trades to be identical, field for field. If the
harness ever disagrees with the engine that produced the results in
`screened_universe_results.md`, that test fails and says so.

THE DEFAULTS ARE THE CORRECTED ONES
-----------------------------------
`gap_fills=True`, `seed_peak_with_bar_high=False`, `stop_wins_ties=True`. The
optimistic settings still exist, purely so an old result can be reproduced on
demand, and each is documented where it is read. A new strategy that says
nothing gets the honest model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time as dtime

import pandas as pd

from common.commissions import order_cost

TICK = 0.01


# --- the trade record -------------------------------------------------------

@dataclass
class Trade:
    """One round trip. Field names match what common/db_load.py loads and what
    common/day_compare.py joins on, so a harness strategy needs no new
    downstream plumbing."""
    symbol: str
    date: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    qty: int
    reason: str
    bars_held: int
    gross: float
    commission: float
    net: float
    # Optional, for strategies that report them. Zero is not "missing" here --
    # it is the true value when the mechanic is off.
    r_multiple: float | None = None
    setup_kind: str | None = None


# --- configuration ----------------------------------------------------------

@dataclass
class Exits:
    """How a position is closed. Every field is optional; whatever is set is
    checked, in the priority order documented on `run_session`.

    A strategy that sets none of these exits only at the session end, which is
    a legitimate configuration and not a mistake -- it is what measures how
    much of a signal's value the exit rules are actually capturing.
    """
    trail_pct: float | None = None
    # A stop level supplied per-bar by the strategy, in a `stop_level` column.
    # This is how a structure stop is expressed: the strategy knows what its
    # structure is, the harness does not.
    use_stop_column: bool = False
    # Fixed fraction of the entry price. The blunt instrument, for a source
    # that specifies no stop at all.
    stop_pct: float | None = None
    # Target as a multiple of initial risk. Requires a stop, because without
    # one R is undefined -- run_session raises rather than inventing a
    # denominator.
    target_r: float | None = None
    time_stop_bars: int | None = None
    # Honour an `exit_sig` column if the strategy supplies one.
    use_exit_signal: bool = True
    flat_at_session_end: bool = True


@dataclass
class Rules:
    """Everything the harness needs that is not a signal."""
    session_start: dtime
    session_end: dtime
    exits: Exits = field(default_factory=Exits)

    price_min: float = 2.0
    price_max: float = 20.0
    enforce_price_band: bool = True

    commission_plan: str = "ibkr_tiered"
    slippage_ticks: int = 1
    tick: float = TICK

    max_shares: int = 100
    max_equity_pct: float = 40.0
    equity: float = 5_000.0

    max_entries_per_session: int | None = None

    # --- the fill model. Defaults corrected 2026-09-05; see the docstring. ---
    gap_fills: bool = True
    seed_peak_with_bar_high: bool = False
    stop_wins_ties: bool = True


def size_for(price: float, rules: Rules) -> int:
    if price <= 0:
        return 0
    return max(0, min(rules.max_shares,
                      math.floor(rules.equity * rules.max_equity_pct
                                 / 100.0 / price)))


# --- the loop ---------------------------------------------------------------

def run_session(sig: pd.DataFrame, session_date, tz, rules: Rules, *,
                symbol: str = "", entry_shares: int | None = None,
                setup_kind: str | None = None) -> list[Trade]:
    """Run one session.

    `sig` must be indexed by a tz-aware timestamp and carry open/high/low/close
    plus a boolean `entry` column. Optional columns: `exit_sig` (bool) and
    `stop_level` (float, the strategy's structure stop for a position opened on
    that bar).

    EXIT PRIORITY, and the order is a decision rather than an accident:

      1. stop      -- trailing, structure or fixed, whichever are configured
      2. target    -- target_r
      3. time stop
      4. exit signal
      5. session end

    The stop is checked FIRST because when one bar contains both the stop and
    the target, assuming the target filled first is the single most flattering
    assumption available. `stop_wins_ties=False` restores the optimistic
    ordering for reproducing an old result, and nothing else in this project
    sets it.
    """
    if rules.exits.target_r is not None and not (
            rules.exits.use_stop_column or rules.exits.stop_pct is not None
            or rules.exits.trail_pct is not None):
        raise ValueError(
            "target_r needs a stop: R is the distance from entry to the stop, "
            "and with no stop there is no denominator. Set stop_pct, "
            "use_stop_column, or trail_pct.")

    local = sig.index.tz_convert(tz)
    in_sess = ((local.date == session_date)
               & (local.time >= rules.session_start)
               & (local.time < rules.session_end))
    idx = [i for i, f in enumerate(in_sess) if f]
    if not idx:
        return []

    rows = sig.reset_index()
    tcol = rows.columns[0]
    slip = rules.slippage_ticks * rules.tick

    trades: list[Trade] = []
    pos = None
    n_entries = 0

    for k, i in enumerate(idx):
        row = rows.iloc[i]
        last_of_session = (k == len(idx) - 1)

        if pos is None:
            if not bool(row.get("entry", False)):
                continue
            if (rules.max_entries_per_session is not None
                    and n_entries >= rules.max_entries_per_session):
                continue
            px = float(row["close"]) + slip
            if rules.enforce_price_band and not (
                    rules.price_min <= px <= rules.price_max):
                # THE BAND IS NOT OPTIONAL AND NOT COSMETIC. VW9 shipped
                # without it and took positions at $4,152/share -- a split
                # adjustment factor, not a price. Its headline moved from
                # -$31,296 to +$3,942 once applied.
                continue
            q = size_for(px, rules) if entry_shares is None else int(entry_shares)
            if q < 1:
                continue

            stop0 = None
            if rules.exits.use_stop_column:
                v = row.get("stop_level")
                stop0 = None if v is None or pd.isna(v) else float(v)
            elif rules.exits.stop_pct is not None:
                stop0 = px * (1.0 - rules.exits.stop_pct / 100.0)

            pos = {
                "entry_i": i,
                "entry_px": px,
                "qty": q,
                "entry_t": row[tcol],
                "stop": stop0,
                # The entry bar's high happened BEFORE the close that was
                # bought. Seeding the trail from it prices a move the position
                # never had.
                "peak": (max(px, float(row["high"]))
                         if rules.seed_peak_with_bar_high else px),
                "r": (px - stop0) if stop0 is not None else None,
            }
            n_entries += 1
            continue

        # --- an open position -------------------------------------------
        e = rules.exits
        stop_level = None
        if e.trail_pct is not None:
            stop_level = pos["peak"] * (1.0 - e.trail_pct / 100.0)
        if pos["stop"] is not None:
            # The tighter of the two, so a structure stop and a trail can be
            # run together without one silently cancelling the other.
            stop_level = (pos["stop"] if stop_level is None
                          else max(stop_level, pos["stop"]))

        target = None
        if e.target_r is not None and pos["r"]:
            target = pos["entry_px"] + e.target_r * pos["r"]

        low, high, close = (float(row["low"]), float(row["high"]),
                            float(row["close"]))
        hit_stop = stop_level is not None and low <= stop_level
        hit_target = target is not None and high >= target

        exit_px = exit_reason = None
        if hit_stop and (rules.stop_wins_ties or not hit_target):
            # GAP-THROUGH. When the bar OPENS below the stop, price was already
            # through it before the bar began and the level was never offered.
            fill = (min(stop_level, float(row["open"])) if rules.gap_fills
                    else stop_level)
            exit_px, exit_reason = fill - slip, "stop"
        elif hit_target:
            # Symmetrically honest on the way up: a bar that OPENS above the
            # target filled at the open, not at the target.
            fill = (max(target, float(row["open"])) if rules.gap_fills
                    else target)
            exit_px, exit_reason = fill - slip, "target"
        elif (e.time_stop_bars is not None
              and i - pos["entry_i"] >= e.time_stop_bars):
            exit_px, exit_reason = close - slip, "time_stop"
        elif e.use_exit_signal and bool(row.get("exit_sig", False)):
            exit_px, exit_reason = close - slip, "signal"
        elif last_of_session and e.flat_at_session_end:
            exit_px, exit_reason = close - slip, "session_end"

        if exit_px is None:
            pos["peak"] = max(pos["peak"], high)
            continue

        q = pos["qty"]
        gross = (exit_px - pos["entry_px"]) * q
        comm = (order_cost(q, pos["entry_px"], False, rules.commission_plan)
                + order_cost(q, exit_px, True, rules.commission_plan))
        trades.append(Trade(
            symbol=symbol, date=str(session_date),
            entry_time=str(pos["entry_t"]), exit_time=str(row[tcol]),
            entry_price=round(pos["entry_px"], 4),
            exit_price=round(exit_px, 4), qty=q, reason=exit_reason,
            bars_held=i - pos["entry_i"], gross=round(gross, 2),
            commission=round(comm, 2), net=round(gross - comm, 2),
            r_multiple=(round((exit_px - pos["entry_px"]) / pos["r"], 3)
                        if pos["r"] else None),
            setup_kind=setup_kind))
        pos = None

    return trades
