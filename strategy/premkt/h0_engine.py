#!/usr/bin/env python3
"""H0 wearing the `backtest_session` interface, so it can be audited like a rule.

    from strategy.premkt import h0_engine
    h0_engine.backtest_session(df, date, ET, entry_shares=100, not_before=t)

WHY AN ADAPTER RATHER THAN A THIRD ARM INSIDE `pit_h0`
------------------------------------------------------
`pit_strategy` splits a strategy's look-ahead into a universe part and an
intraday part by running three arms -- stage-2 unfloored, point-in-time
unfloored, point-in-time floored -- on one tape. `pit_h0` cannot do that split:
it has no stage-2 arm and no unfloored arm, so `pit_h0_result_20260911.md` §6
had to be left flagged rather than settled, and this document has been quoted
since as though the split were known.

The cheap fix is not to grow a second copy of that machinery. It is to let H0
through the machinery that already exists. H0 is a rule like any other -- buy at
04:30, trail 8%, flat at 09:30 -- and the only thing keeping it out was the
shape of its call signature.

Running it this way is strictly better than reimplementing the arms:

  * H0 and MCL are then measured by the SAME code over the SAME universes with
    the SAME friction ladder, drop-top-5, halves and floor control. A control
    and the thing it controls, scored by two different modules, is precisely the
    "two values that look comparable and are not" shape this project keeps
    finding; this removes the possibility.
  * The three-arm split, the floor-bite count and the staleness guard come for
    free and cannot drift out of step with the strategy reports.

WHAT THIS IS NOT
----------------
It is NOT a new hypothesis. `signal_h0` and `rules()` are imported and called
unchanged, at their registered defaults, so this produces the same trades
`pit_h0` produces for the same inputs. `test_h0_engine_matches_pit_h0` asserts
exactly that, field for field, because an adapter that quietly altered the
control would invalidate every comparison drawn through it.

The one deliberate difference is at the caller, not here: `pit_strategy` will
run this WITHOUT a floor as well as with one, which `pit_h0` never did. That
unfloored arm is the measurement this file exists to enable -- H0 entering at
04:30 on names the screen had not yet surfaced, which is what every published
backtest was doing.
"""
from __future__ import annotations

from datetime import time as dtime

import pandas as pd

from common.harness import run_session
from strategy.premkt.hypotheses import (ENTRY_SHARES, TRAIL_PRIMARY, rules,
                                        signal_h0)

# Surfaced so `pit_strategy` can report which configuration it ran, and so a
# reader of the report does not have to open two files to learn the trail.
STRATEGY_NAME = "H0"
TRAIL_PCT = TRAIL_PRIMARY


def backtest_session(df: pd.DataFrame, session_date, tz, *,
                     entry_shares: int | None = None,
                     trail_pct: float | None = None,
                     not_before: dtime | None = None) -> list:
    """One session of H0, returning harness Trades.

    Keyword-only after `tz` on purpose. MCL and MC5 both take a long tail of
    positional-capable exit knobs that mean nothing here, and accepting them
    silently would let a caller pass `ladder=` or `scale_out_pct=` to H0 and
    get the unmodified rule back while believing a mechanic had been applied.
    A TypeError is the honest answer to that call.
    """
    sig = signal_h0(df, session_date, tz, not_before=not_before)
    return run_session(
        sig, session_date, tz,
        rules(TRAIL_PRIMARY if trail_pct is None else trail_pct),
        entry_shares=ENTRY_SHARES if entry_shares is None else entry_shares)
