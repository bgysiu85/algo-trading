#!/usr/bin/env python3
"""The pipeline: raw archive inputs -> training-side sessions -> books.

THE HOLDOUT IS CUT FIRST, BEFORE ANYTHING IS COMPUTED
-----------------------------------------------------
Every date passes through `common.tsmom_holdout.split_months` -- the one
implementation (REGISTERED_tsmom section 6, gate G4) -- and the prices are
truncated to the training side BEFORE the roll schedule, the back-adjusted
series, the volatility or any signal is built. Truncating afterwards would be
equivalent for the P/L, but the adjusted series would have been built with
gaps from locked years, and "equivalent" is an argument; not reading the
locked rows at all is a property. A test spies on `split_months` and fails if
this module stops calling it or stops honouring what it returns.

Arms: all three rates arms of spec section 2.3 are built side by side and
returned in registry order. Nothing here ranks them (section 3 item 13).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import common.tsmom_holdout as H
from strategy.tsmom.book import BookResult, run_book
from strategy.tsmom.registry import ALL_ROOTS, RATES_ARMS, Root, book_roots
from strategy.tsmom.roll import held_contract, held_series, roll_schedule


@dataclass
class RootInputs:
    """What the archive gives one root. `prices`/`volumes`: index = sessions
    (weekdays only), columns = contract symbols; NaN = no bar."""
    contracts: pd.DataFrame        # symbol, expiration, year, month[, instrument_id]
    prices: pd.DataFrame
    volumes: pd.DataFrame | None = None

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.prices.index)


def build_series(inp: RootInputs, root: Root):
    sched = roll_schedule(inp.contracts, inp.sessions, root)
    held = held_contract(sched, inp.sessions)
    return sched, held_series(inp.prices, held)


def training_inputs(inputs: dict[str, RootInputs]) -> tuple[dict[str, RootInputs], dict]:
    """Every root cut to the training side by split_months. Returns the cut
    inputs and what was set aside, per root."""
    out, held_back = {}, {}
    for name, inp in inputs.items():
        days = [d.strftime("%Y-%m-%d") for d in inp.sessions]
        keep, n_locked, label = H.split_months(days)
        keep_ix = pd.DatetimeIndex(pd.to_datetime(keep))
        vol = inp.volumes.reindex(keep_ix) if inp.volumes is not None else None
        out[name] = RootInputs(inp.contracts, inp.prices.reindex(keep_ix), vol)
        held_back[name] = {"sessions_kept": len(keep), "sessions_locked": n_locked,
                           "side": label}
    return out, held_back


def training_book(inputs: dict[str, RootInputs], arm: str, *, equity: float,
                  **kw) -> BookResult:
    roots = book_roots(arm)
    cut, _ = training_inputs({n: inputs[n] for n in roots})
    series = {n: build_series(cut[n], roots[n])[1] for n in roots}
    return run_book(series, roots, equity=equity, **kw)


def training_books(inputs: dict[str, RootInputs], *, equity: float,
                   **kw) -> dict[str, BookResult]:
    """All three rates arms, side by side, in registry order -- not ranked."""
    return {arm: training_book(inputs, arm, equity=equity, **kw) for arm in RATES_ARMS}


def coverage(inputs: dict[str, RootInputs]) -> pd.DataFrame:
    """REGISTERED_tsmom section 3 item 12, on the TRAINING side: bars per root,
    first/last session, held-contract sessions carried forward, and when the
    root has its WARMUP_RETURNS returns."""
    from strategy.tsmom.registry import WARMUP_RETURNS
    cut, held_back = training_inputs(inputs)
    rows = []
    for name, inp in cut.items():
        _, s = build_series(inp, ALL_ROOTS[name])
        n = s["ret"].notna().cumsum()
        enters = n.index[n >= WARMUP_RETURNS]
        rows.append({"root": name, "sessions": len(s),
                     "first": s.index[0].date(), "last": s.index[-1].date(),
                     "held_stale_sessions": int(s["stale"].sum()),
                     "rolls": int(s["rolled"].sum()),
                     "enters": enters[0].date() if len(enters) else None,
                     "locked_sessions_set_aside": held_back[name]["sessions_locked"]})
    return pd.DataFrame(rows).set_index("root")
