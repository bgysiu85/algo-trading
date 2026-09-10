#!/usr/bin/env python3
"""Dip buying — the half of his method MCL did not inherit.

    from common.dip_entry import DipConfig, find_dips

WHY THIS IS SECOND ON THE LIST
------------------------------
`warrior_census_20260910.md` §6, over 317 recaps:

    | setup          | mentions | red-day share | green-day share | lift |
    | micro_pullback |      172 |         46.2% |           61.6% |  0.7 |
    | dip_buy        |      129 |         33.3% |           46.4% |  0.7 |

**Three quarters as often as the micro pullback, at exactly the same red-day
lift.** MCL implements the first and nothing in this repository implements the
second. `HANDOVER_TO_BUILD_20260910.md` §0 is what makes that matter: MCL is
Ben's own version of this method, loosely derived — so this is not a strategy
we chose not to build, it is half a method we inherited without noticing.

THE DIFFERENCE IS ONE THING, AND IT IS THE THING WE KEEP MEASURING
-------------------------------------------------------------------
Both setups look at the same picture: a name runs, then pulls back. They differ
on one thing — where you buy.

    micro pullback   wait for the first candle to make a NEW HIGH — a
                     confirmation entry, above the pullback
    dip buy          buy INTO the pullback, at the level, before the new high

**Four independent measurements in this project already point at the second.**

  1. `premarket_hypotheses_results_20260908.md` §2 scored every confirmation
     entry we have tried and each one made the screen WORSE: H0 (buy at 04:30,
     no rule) +$4.72/trade, H1 (new session high on 2x volume) −$8.44, H2
     (opening-range break on 2x volume) −$12.21.
  2. `consolidation_filter_test.md` §2 found entries into a CONTRACTING range
     made money (+$10.09/trade) and entries into an EXPANDING range lost it
     (−$0.85), in both halves — the opposite of the proposed gate.
  3. `hold_cap_decision.md` §4: 1-bar holds are 107 trades at −$36.68 each.
     Price gave back 5% of its peak within the minute, which is what buying a
     spike that has already gone looks like.
  4. Ben, 2026-09-10 and again on MC5: *"all the entries were enter at the
     close of the 5min bar and much of the move were gone by then."*

Four readings, four methods, one direction: **our entries are late.** Dip
buying is the named, sourced strategy that is late's opposite, and that
convergence is why it is worth the build rather than the 129 mentions alone.

THE TRAP THAT WOULD MAKE ANY RESULT HERE FAKE
----------------------------------------------
**A dip entry gets a better fill by construction.** Buy the pullback instead of
the breakout and your entry price is lower on every single setup where both
fire. So a P/L comparison is guaranteed to favour it before any edge exists,
and a study that ran one would produce a large, entirely mechanical win.

Where dip buying actually costs is the setups where the dip fires and **the
move never resumes** — the ones the confirmation entry correctly refused. That
is why `dip_study` reports three buckets (both fired / dip only / MCL only) and
leads with MAE alongside MFE. MFE alone rewards the earlier entry for being
earlier.

WHERE THE PARAMETERS COME FROM — none of them is swept
-------------------------------------------------------
Four knobs would be four things to fit, so every one is derived from something
already settled or already sourced, and this docstring is the registration:

    impulse_min   2 x TRAIL_PCT = 10%.  A move smaller than twice the trail is
                  not a move this strategy is about; it is inside the noise the
                  stop already tolerates.
    dip_min       1 x TRAIL_PCT = 5%.   A pullback shallower than the trail is
                  not a pullback, it is a wiggle — and by definition MCL would
                  not have been stopped out of it.
    hold_min      0.50.  The hold-50% rule, `warrior_5_selection_in_practice`
                  §1, in his own words: a name that pops and gives it all back
                  is *"not going to work."* Same number, applied per-name.
    dip_max       1 - hold_min = 0.50.  NOT a separate knob: a pullback deeper
                  than half the impulse IS a failure of the hold-50% rule, so
                  the two are one constant seen from both ends.

`lookback` is a window length rather than a threshold — the impulse has to be
found somewhere — and is set to 20 bars because MCL's own session is 04:00
to 09:30 on 1-minute bars and a run that took longer than 20 minutes is not the
parabolic kind either strategy is about.

WHAT IS NOT IN HERE
-------------------
His stop. `warrior_4_reversal.md` §3 shows the same 10-20c answer across three
of his setups, and that cent stop was measured and REJECTED on 2026-09-10 on
the price band ($2-20, where 15c is 7.5% at one end and 0.75% at the other).
Substituting it back in would confound a test of the ENTRY with a settled
question about the stop, so the exit stays MCL's validated 5% trail.

His level-2 trigger. `warrior_1` §3b names a surge on the level 2 and time &
sales as the second early-entry trigger. We have no level 2 in the backtest and
a proxy for it would be a fifth parameter.

The two dip videos. `warrior_4_reversal.md` §6 names `ORWJzImSTdE` (1:05:05)
and `hz7vhSIXXSc` (51:55) as the long-side sources and NEITHER IS TRANSCRIBED.
So this detector is built from the shape the census names and the mechanics the
other four documents give, not from a stated dip-buy rule. **That is a real
weakness and it is why `dip_study` is a measurement rather than a strategy.**
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from strategy.mcl.mcl import TRAIL_PCT


@dataclass(frozen=True)
class DipConfig:
    """Every field derived. See the module docstring for each derivation."""
    impulse_min: float = 2.0 * TRAIL_PCT / 100.0     # 10%
    dip_min: float = TRAIL_PCT / 100.0               # 5%
    hold_min: float = 0.50                           # warrior_5 §1
    lookback: int = 20

    @property
    def dip_max(self) -> float:
        """Not a separate knob. A pullback past half the impulse IS a
        hold-50% failure, so this is `hold_min` seen from the other end."""
        return 1.0 - self.hold_min


@dataclass(frozen=True)
class Dip:
    i: int                # bar index of the signal
    price: float          # the close it would be bought at
    base: float           # where the impulse started
    peak: float           # the impulse high
    retained: float       # share of the impulse still held, 0..1


def find_dips(df: pd.DataFrame, cfg: DipConfig | None = None,
              lo: int = 0, hi: int | None = None) -> list[Dip]:
    """Every bar that is a dip into a live impulse, in order.

    `lo`/`hi` bound the bars CONSIDERED, not the bars looked at: the impulse
    behind a signal at `lo` is allowed to start before it, because an impulse
    that began at 06:55 is the reason a 07:00 bar is a dip. Truncating the
    lookback at the window edge would silently make the first `lookback` bars
    of every session unable to signal.

    One signal per impulse. The rule is "buy the dip", not "buy every bar of
    the dip": firing on each bar of a three-bar pullback would take three
    positions in one setup and make the count a function of pullback duration.
    """
    cfg = cfg or DipConfig()
    hi = len(df) if hi is None else hi
    if len(df) == 0:
        return []
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)

    out: list[Dip] = []
    armed_peak = -1          # index of the impulse peak already signalled on
    for i in range(max(lo, 1), min(hi, len(df))):
        j0 = max(0, i - cfg.lookback)
        window_high = high[j0:i]
        if len(window_high) == 0:
            continue
        k = int(window_high.argmax())
        peak = float(window_high[k])
        peak_i = j0 + k
        # The base is the lowest LOW before the peak inside the window. Using
        # the lowest CLOSE would understate the impulse on the exact bars this
        # is about -- the ones that ran hard off a wick.
        pre = low[j0:peak_i + 1]
        if len(pre) == 0:
            continue
        base = float(pre.min())
        if base <= 0 or peak <= base:
            continue
        if (peak - base) / base < cfg.impulse_min:
            continue

        px = close[i]
        drop = (peak - px) / peak
        if drop < cfg.dip_min:
            continue
        retained = (px - base) / (peak - base)
        if retained < cfg.hold_min:
            # The hold-50% rejection. This is not "no signal yet" -- it is the
            # setup being disqualified, and it is the whole reason the rule
            # exists: a name that gives the impulse back is not going to work.
            continue
        if peak_i == armed_peak:
            continue
        armed_peak = peak_i
        out.append(Dip(i=i, price=px, base=base, peak=peak,
                       retained=min(1.0, retained)))
    return out


def excursions(df: pd.DataFrame, i: int, entry: float,
               end: int | None = None) -> tuple[float, float]:
    """(MFE, MAE) from bar i+1 to `end`, as fractions of the entry price.

    Forward only, and from i+1, because bar i is the bar the signal was read
    from -- including its own high would credit the entry with a move that had
    already happened when the decision was made.

    Reported as a PAIR and never separately. MFE alone rewards an earlier entry
    for being earlier: there is simply more session left in front of it. MAE is
    the offsetting cost, and for a dip entry -- which buys into a falling
    pullback -- it is where the whole risk of the idea lives.
    """
    end = len(df) if end is None else end
    if entry <= 0 or i + 1 >= end:
        return 0.0, 0.0
    hi = float(df["high"].to_numpy(dtype=float)[i + 1:end].max())
    lo = float(df["low"].to_numpy(dtype=float)[i + 1:end].min())
    return (hi - entry) / entry, (entry - lo) / entry
