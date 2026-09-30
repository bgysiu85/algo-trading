"""The 27-cell neighbour grid (REGISTERED_va80.md sec 2.5, criterion 6): acceptance brackets {1,2,3} x bracket
length {15,30,60} min x value-area share {60%,70%,80%}. The centre (2, 30, 70%) is the primary. Reported, never
ranked; the study counts the cells with net > $0 at mid (>= 18 of 27)."""
from __future__ import annotations

import itertools

from strategy.va80 import spec as S
from strategy.va80.engine import Params, evaluate

CELLS = tuple(itertools.product(S.GRID_ACCEPT, S.GRID_LENGTH, S.GRID_SHARE))
assert len(CELLS) == 27 and S.CENTRE in CELLS


def params(cell) -> Params:
    a, l, s = cell
    return Params(accept=a, length=l, share=s)


def run_grid(store, days, *, want_exit: bool = False) -> dict:
    """{cell: records} for all 27 cells (records as engine.evaluate)."""
    return {c: evaluate(store, days, params(c), want_exit=want_exit) for c in CELLS}


def counts(records) -> dict:
    ok = [r for r in records if r["status"] == "ok"]
    trig = [r for r in ok if r["trigger"]]
    rot = [r for r in trig if r["rotated"]]
    return {"triggers": len(trig), "rotated": len(rot), "trades": len(trig) - len(rot)}
