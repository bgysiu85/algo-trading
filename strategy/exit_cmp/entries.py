#!/usr/bin/env python3
"""EXIT-CMP sec 4: the fixed entry set, by RE-RUNNING the CHARTMARK-v1 entry machine. W15-0053 sub 2 (gate G3).

`strategy.chartmark.engine.simulate` finds the 2,670 base long fills (order logic E1-E5, v1 exits only decide when the machine is
flat again). Only the ENTRY side of each trade is kept here: entry bar, fill price, A0, initial stop S. No exit, gross, cost or
net field of a v1 trade, and no column of the trades CSV, is read by this module (parity.py is the one reader, after the code
is frozen)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from strategy.chartmark import engine as E
from strategy.chartmark import spec as V1
from strategy.chartmark.data import Frame, Ind
from strategy.chartmark_clone import spec as CS


class EntryError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    e: int
    entry_px: float
    a0: float
    s0: float
    placed_j: int
    gap_fill: bool
    own_low: bool


def entry_set(fr: Frame, ind: Ind, p: V1.Params = V1.BASE) -> list[Entry]:
    trades, _ = E.simulate(fr, ind, p)
    return [Entry(t.entry_j, t.entry_px, t.a0, t.stop0, t.placed_j, t.gap_fill, t.stop_from_entry_bar) for t in trades]


def per_year(fr: Frame, entries: list[Entry]) -> dict[int, int]:
    yrs = np.asarray(fr.ny.year)
    return {int(k): int(v) for k, v in sorted(Counter(int(yrs[x.e]) for x in entries).items())}


def check_registered(fr: Frame, entries: list[Entry]) -> dict[int, int]:
    """G3: 2,670 fills with the sec 4 per-year counts. Mismatch = stop."""
    py = per_year(fr, entries)
    if len(entries) != CS.POOL_N or py != CS.POOL_PER_YEAR:
        raise EntryError(f"entry set is {len(entries)} fills {py}; registered {CS.POOL_N} {CS.POOL_PER_YEAR} -- stop (G3).")
    return py
