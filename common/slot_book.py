#!/usr/bin/env python3
"""The position-slot cap, modelled in a backtest (W03-0003).

WHY THIS EXISTS
---------------
Every published backtest here runs one symbol-day at a time. The live trader
does not: `brokers/ibkr/trader.py` refuses a BUY when `max_positions` are
already open (`SKIPPED_CONCURRENCY_CAP`), either across every strategy
(`cap_scope=account`, the default, live until 2026-09-22) or per strategy
(`cap_scope=strategy`, live from 2026-09-23). No backtest knew slots existed,
so a rule whose whole value is FREEING a slot -- a time cap
(REGISTERED_time_cap.md, W03-0004) -- could not be measured at all.

`common/portfolio.py` has a slot cap, but it re-implements the exits by hand
(and has drifted from the engines), sizes from capital, and runs one strategy
at a time. This module does not touch the exits: it drives the PUBLISHED
engines and only decides which entries they are allowed to take.

HOW THE WALK WORKS, EXACTLY
---------------------------
A "leg" is one (book, symbol) on one date -- e.g. ("MCL", "TCRT"). Each leg's
engine is run on its own, exactly as the published books are. Then:

  1. Every trade of every leg becomes two events: an ENTRY at the close of the
     signal bar and an EXIT at the close of the exit bar (bar length is the
     book's own: 1 minute for MCL, 5 for MC5). A stop inside a 5-minute bar is
     treated as holding the slot until that bar closes -- conservative for
     freeing slots, which is the direction that cannot flatter a time cap.
  2. Events are walked in time order. At the same moment EXITS go first, so a
     slot freed in a minute can be used by an entry in that minute (optimistic;
     live, the fill and the next decision are seconds apart -- registered and
     flagged, same as portfolio.py). Among simultaneous entries the legs' own
     order decides (the caller passes MCL before MC5, then the universe order).
  3. At the FIRST entry that finds the slots full, that bar is BLOCKED for that
     leg only, the leg's engine is re-run with the block as an `entry_gate`, and
     the walk restarts from the top of the day.

Step 3 is the point. A simple pass that drops the refused trade would also drop
everything that leg did afterwards, but the live trader does not stop watching a
symbol because one bar was refused: it marks that bar evaluated and judges the
next bar on its own. Re-running the engine with only that bar blocked is exactly
that. Blocking bar b cannot change anything before b, so every event before the
refusal is unchanged and restarting is safe; each pass blocks one new bar, so
the walk always ends.

`refusals` records every blocked bar with the trade the leg WOULD have taken
there. Successive refusals of the same leg are overlapping versions of nearly
the same trade, so their nets must never be summed as "what the cap cost" --
the cap's cost is the capped book's net minus the free book's.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Hashable, Sequence

import pandas as pd

BAR_MINUTES = {"MCL": 1, "MC5": 5}
SCOPES = ("strategy", "account")
MAX_PASSES = 20_000     # a guard, not a tuning knob: see test_walk_terminates


@dataclass(frozen=True)
class Leg:
    book: str
    symbol: str


@dataclass(frozen=True)
class Refusal:
    leg: Leg
    bar: pd.Timestamp          # the signal bar that was blocked (its START stamp)
    at: pd.Timestamp           # when the entry would have filled (bar close)
    trade: object              # the trade the leg would have taken there
    open_legs: tuple           # who held the slots, for the report


def bar_len(book: str) -> pd.Timedelta:
    return pd.Timedelta(minutes=BAR_MINUTES[book])


def entry_at(leg: Leg, t) -> pd.Timestamp:
    return pd.Timestamp(t.entry_time) + bar_len(leg.book)


def exit_at(leg: Leg, t) -> pd.Timestamp:
    return pd.Timestamp(t.exit_time) + bar_len(leg.book)


def first_refusal(trades: dict[Leg, list], order: Sequence[Leg], cap: int,
                  scope: str):
    """Walk the day; return (leg, trade, open_legs) at the first entry that
    finds the slots full, or None if every entry fits."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
    rank = {leg: k for k, leg in enumerate(order)}
    events = []
    for leg, ts in trades.items():
        for n, t in enumerate(ts):
            ein, eout = entry_at(leg, t), exit_at(leg, t)
            if eout < ein:
                raise ValueError(f"{leg}: exit before entry in {t}")
            # kind 0 = exit, 1 = entry: exits first at the same moment.
            events.append((eout, 0, rank[leg], n, leg, t))
            events.append((ein, 1, rank[leg], n, leg, t))
    events.sort(key=lambda e: (e[0], e[1], e[2], e[3]))
    open_now: dict[tuple, Leg] = {}
    for _, kind, _, n, leg, t in events:
        key = (leg, n)
        if kind == 0:
            open_now.pop(key, None)
            continue
        held = [lg for lg in open_now.values()
                if scope == "account" or lg.book == leg.book]
        if len(held) >= cap:
            return leg, t, tuple(sorted((lg.book, lg.symbol) for lg in open_now.values()))
        open_now[key] = leg
    return None


def walk(order: Sequence[Leg], run_leg: Callable[[Leg, frozenset], list],
         cap: int | None, scope: str = "strategy",
         cache: dict | None = None):
    """Run every leg under a slot cap. Returns (trades_by_leg, refusals).

    `run_leg(leg, blocked)` must return the leg's trades with entries forbidden
    on every bar in `blocked` (a frozenset of signal-bar timestamps) and must be
    deterministic. `cache`, shared across calls, keys on (leg, blocked), so arms
    that reach the same state reuse the run. cap=None is no slot cap at all.
    """
    cache = {} if cache is None else cache

    def get(leg: Leg, blocked: frozenset):
        k = (leg, blocked)
        if k not in cache:
            cache[k] = run_leg(leg, blocked)
        return cache[k]

    blocked = {leg: frozenset() for leg in order}
    refusals: list[Refusal] = []
    for _ in range(MAX_PASSES):
        trades = {leg: get(leg, blocked[leg]) for leg in order}
        if cap is None:
            return trades, refusals
        hit = first_refusal(trades, order, cap, scope)
        if hit is None:
            return trades, refusals
        leg, t, held = hit
        bar = pd.Timestamp(t.entry_time)
        if bar in blocked[leg]:
            # The engine entered on a bar it was told not to. Continuing
            # would loop forever on a broken gate; fail loudly instead.
            raise RuntimeError(f"{leg} entered on blocked bar {bar}")
        refusals.append(Refusal(leg, bar, entry_at(leg, t), t, held))
        blocked[leg] = blocked[leg] | {bar}
    raise RuntimeError(f"slot walk did not settle in {MAX_PASSES} passes")


def gate_for(index: pd.Index, blocked: frozenset) -> pd.Series | None:
    """The `entry_gate` the engines take: True everywhere except the blocked
    bars. None when nothing is blocked, so the unblocked run is the engine
    exactly as published (no gate argument at all)."""
    if not blocked:
        return None
    g = pd.Series(True, index=index)
    hit = index.isin(list(blocked))
    if hit.sum() != len(blocked):
        missing = sorted(set(blocked) - set(index[hit]))
        raise ValueError(f"blocked bars not on the engine's index: {missing[:3]}")
    g[hit] = False
    return g
