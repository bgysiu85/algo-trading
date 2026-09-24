#!/usr/bin/env python3
"""Hindsight guards (gate G5). W14-0003, REGISTERED_h60_v0.md §6.1.

    1. membership by date   a trade's signal and fill sessions are covered by
                            a membership spell -- re-derived here from the
                            spells, not read back from the engine's own flag
    2. no bar before close  every rule's decisions at bar t are identical
                            when the series is CUT at t: nothing after t can
                            have been read
    3. fill at next open    every entry fills at the open of the bar after
                            its signal, at that bar's open price

Each is a function that RAISES on a violation, run by the scoring path over
the real book before any number is printed (run.py), and each is
mutation-tested in tests/strategy/h60/test_h60_guards.py: the test plants the
defect the guard exists for and asserts the guard fires. A guard that cannot
fail is not a guard (PROGRAM_INDEX §4).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.h60.panel import Panel, SymArrays, slice_arrays


class HindsightError(AssertionError):
    pass


# --------------------------------------------------------------------------
# 1. membership by date
# --------------------------------------------------------------------------

def check_membership(trades: pd.DataFrame, panel: Panel) -> int:
    """Every trade's signal and entry sessions sit inside a spell of its
    symbol. Returns the number checked."""
    uni = panel.universe
    bad = []
    for sym, s_sig, s_ent in zip(trades["symbol"], trades["s_signal"], trades["s_entry"]):
        for s in (int(s_sig), int(s_ent)):
            if not uni.eligible(sym, panel.sessions[s]):
                bad.append((sym, panel.sessions[s]))
    if bad:
        raise HindsightError(f"{len(bad)} trade session(s) outside membership, "
                             f"e.g. {bad[:5]}")
    return len(trades)


# --------------------------------------------------------------------------
# 2. a bar is knowable only at its close
# --------------------------------------------------------------------------

def truncate(a: SymArrays, t: int) -> SymArrays:
    """The symbol as it looked at the CLOSE of bar t."""
    return slice_arrays(a, 0, t + 1)


def _same(x, y) -> bool:
    x, y = np.asarray(x, float), np.asarray(y, float)
    return bool(np.all((x == y) | (np.isnan(x) & np.isnan(y))
                       | np.isclose(x, y, rtol=1e-9, atol=1e-12)))


def check_no_lookahead(rule_fn, a: SymArrays, cuts, variant: str | None = None) -> int:
    """Run `rule_fn` on the full series and on the series cut at each t in
    `cuts`; every per-bar decision at or before t must agree, and so must the
    stop an entry at t would carry. Returns the number of cuts checked."""
    call = (lambda x: rule_fn(x)) if variant is None else (lambda x: rule_fn(x, variant))
    full = call(a)
    for t in cuts:
        t = int(t)
        if t + 1 >= a.n:
            continue
        cut = call(truncate(a, t))
        k = t + 1
        if not np.array_equal(full.entry[:k], cut.entry[:k]):
            j = int(np.flatnonzero(full.entry[:k] != cut.entry[:k])[0])
            raise HindsightError(f"{a.symbol}: the entry at bar {j} changes when "
                                 f"the series is cut at bar {t} -- it read a later bar")
        for name in ("xsig", "ratchet", "atr_prev"):
            f, c = getattr(full, name), getattr(cut, name)
            if f is not None and not _same(f[:k], c[:k]):
                raise HindsightError(f"{a.symbol}: {name} before bar {t} changes "
                                     f"when later bars are removed")
        if full.stop is not None and full.entry[t]:
            # the stop of an entry signalled at t, filled at t+1's open. The
            # cut series has no t+1, so both are asked with the same price.
            px = [a.o[t + 1]]
            if not _same(full.stop([t], px), cut.stop([t], px)):
                raise HindsightError(f"{a.symbol}: the stop for a signal at bar {t} "
                                     f"depends on bars after it")
    return len(list(cuts))


# --------------------------------------------------------------------------
# 3. entry fills at the next bar's open
# --------------------------------------------------------------------------

def check_fills(trades: pd.DataFrame, panel: Panel) -> int:
    bad = []
    for sym, g in trades.groupby("symbol"):
        a = panel.arrays(sym)
        sig = g["sig_idx"].to_numpy(int)
        fill = g["fill_idx"].to_numpy(int)
        px = g["entry_px"].to_numpy(float)
        wrong = (fill != sig + 1) | (px != a.o[fill])
        if wrong.any():
            bad.append((sym, int(sig[wrong][0])))
    if bad:
        raise HindsightError(f"entries not filled at the next bar's open: {bad[:5]}")
    return len(trades)
