"""The gate (REGISTERED_otf_gate.md sec 2.2) and its reported variants (sec 2.5) as keep-masks.

Inputs are the state columns of `otf.Stack.states_at` (d, w, m; nd, nw, nm for C-N) and the trade direction
(+1 long, -1 short). The action is SKIP: a removed trade is simply not in the kept book.

Removal reason for the primary (sec 3), first match wins:
    undefined  a timeframe has no completed bar yet
    any_bal    at least one timeframe is BAL
    disagree   all three are UP/DOWN but not all the same
    against    all three agree, against the trade's direction
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategy.otf_gate.spec import BAL, UNDEF, VARIANTS

REASONS = ("undefined", "any_bal", "disagree", "against")


def _arr(x):
    return np.asarray(x, dtype=np.int64)


def keep_mask(st: pd.DataFrame, direction, variant: str = "strict") -> np.ndarray:
    """True = KEEP. `st` has columns d, w, m (and nd, nw, nm for 'naive')."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; registered: {VARIANTS}")
    d, w, m = _arr(st["d"]), _arr(st["w"]), _arr(st["m"])
    sgn = _arr(direction)
    undefined = (d == UNDEF) | (w == UNDEF) | (m == UNDEF)
    if variant in ("strict", "live", "dalton"):        # live / dalton differ in HOW st was built, not in the rule
        return ~undefined & (d == sgn) & (w == sgn) & (m == sgn)
    if variant == "day_week":
        return (d != UNDEF) & (w != UNDEF) & (d == sgn) & (w == sgn)
    if variant == "soft":                              # remove only where a timeframe is OTF against the trade
        against = (d == -sgn) | (w == -sgn) | (m == -sgn)
        return ~undefined & ~against
    if variant == "opposite":
        return ~undefined & (d == -sgn) & (w == -sgn) & (m == -sgn)
    nd, nw, nm = _arr(st["nd"]), _arr(st["nw"]), _arr(st["nm"])      # naive alignment (C-N)
    und = (nd == UNDEF) | (nw == UNDEF) | (nm == UNDEF)
    return ~und & (nd == sgn) & (nw == sgn) & (nm == sgn)


def removal_reason(st: pd.DataFrame, direction) -> np.ndarray:
    """Reason string for every trade the PRIMARY removes; '' for a kept trade."""
    d, w, m = _arr(st["d"]), _arr(st["w"]), _arr(st["m"])
    sgn = _arr(direction)
    kept = keep_mask(st, direction, "strict")
    out = np.full(len(d), "", dtype=object)
    und = (d == UNDEF) | (w == UNDEF) | (m == UNDEF)
    bal = (d == BAL) | (w == BAL) | (m == BAL)
    agree = (d == w) & (w == m)
    out[~kept & und] = "undefined"
    out[~kept & ~und & bal] = "any_bal"
    out[~kept & ~und & ~bal & ~agree] = "disagree"
    out[~kept & ~und & ~bal & agree] = "against"
    return out
