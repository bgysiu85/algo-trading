#!/usr/bin/env python3
"""WICK-REV holdout (gate G4). REGISTERED_wick_reversal.md sec 8.

training 2010-06-06 -> 2021-12-31 (SESSION date) | holdout 2022-01-03 -> 2025-09-22, own ledger
holdout_w15_0063.json, SPENT ONCE, only on the combination-directions that show an edge on the training
side, all scored together | seen 2025-09-23 onward: counts and P(rev) only, "seen -- not evidence".
The shared strategy.futbt.holdout.Holdout refuses --limit / narrowing flags and every other line's ledger by name.
"""
from __future__ import annotations

from strategy.futbt.holdout import Holdout
from strategy.wick_rev import spec as S

H = Holdout("WICK-REV", S.LEDGER, S.CANDIDATE, S.REGISTRATION)


def split_dates(dates, **kw):
    return H.split_dates(dates, **kw)


def main(argv=None) -> int:
    return H.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
