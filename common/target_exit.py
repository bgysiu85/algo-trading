#!/usr/bin/env python3
"""Cameron's exit: half off at a target, breakeven stop on the rest, no trail.

    from common.target_exit import TargetExit

WHY THIS IS THE ONE TO BUILD
----------------------------
`warrior_0_universe_and_risk.md` §5.3 and `warrior_1` §6 both name it as the
largest untested gap in the spec set, and `HANDOVER_TO_BUILD_20260910.md` §0
says why it matters more than the other gaps: **MCL is Ben's own version of this
method, loosely derived.** So this is not one strategy being compared with
another. It is the intent, and MCL is the deviation.

    | | win rate | R | breakeven | margin |
    |---|---:|---:|---:|---:|
    | Cameron 2025 | 71.1% | 1.20 | 45.5% | +25.6 |
    | MCL          | 32.4% | 2.01 | 33.2% |  -0.8 |

He wins five trades in seven; MCL wins one in three. 2,212 of MCL's 2,413 exits
are the trail at -$1.2 each, and only the 201 reaching `window_close` make money.
The exit is the mechanism, and nothing here has ever tested his as specified.

THE RULE, from warrior_0 §5.3
-----------------------------
    1. Sell half at the first target, then move the stop to BREAKEVEN on the
       remainder.
    2. If half is not yet sold, the first candle to close red is the exit. If
       half IS sold, hold through red candles while the breakeven stop holds.
    3. Extension bar -- an outsized spike -- sell into it.

Rules 2 and 3 are NOT implemented here. Rule 2's first-red-candle exit is a
different entry-side rule that deserves its own registration, and rule 3 needs a
definition of "outsized" that the source does not give. **This module is rule 1
alone**, which is the part the win-rate argument rests on.

WHERE THE TARGET COMES FROM, and this is the load-bearing choice
----------------------------------------------------------------
`warrior_0` §5.2 lists four unreconciled statements of his first target -- 2:1,
15-20 cents, the next half or whole dollar, and 20c-on-10c -- and then says the
thing that settles it:

> "§5.1's rejection removes the cent stop these targets were scaled against, so
>  the target question has to be re-posed against a percentage stop before it
>  can be answered at all."

So the cent spellings are not testable as stated: they were scaled to a stop
this project measured and rejected on 2026-09-10, and across a $2-20 band 15c is
7.5% at $2 and 0.75% at $20 -- the same factor-of-ten that killed the cent stop.
Testing them here would re-open a settled question wearing a different hat.

**Re-posed as he asks: his target is 2R.** Against MCL's validated 5% trail that
is a 10% target, and TARGET_PCT is 10.0 for that reason and no other.

Note where that lands. `ladder_study` measured selling half at +10% on
2026-09-11 and found +$272 (+$106 after charging the extra orders), positive in
both halves and better after drop-top-3, **against a registered prediction that
it would lose**. That is the same first rung. So one half of this exit already
has a measurement, and it points the right way.

WHAT IS ACTUALLY NEW HERE
-------------------------
The BREAKEVEN STOP. The ladder left MCL's 5% trail on the remainder; he replaces
it with a stop at the entry price. That is the piece that converts a
partially-taken trade that later fails from a small loss into a scratch, and a
scratch counts as a win in nobody's arithmetic -- but it stops counting as a
loss, which is how a 32% win rate becomes a 71% one.

**So the study must not test the combination alone.** `common/cameron_exit.py`
runs a 2x2 that separates the two changes, because a combination that wins tells
you nothing about which half won:

    |               | trail on remainder | breakeven on remainder |
    |---------------|--------------------|------------------------|
    | no partial    | MCL today          | stop change alone      |
    | half at 2R    | the ladder         | CAMERON'S EXIT         |

Two of those four cells are already measured.

WHAT IS DELIBERATELY KEPT FROM MCL
-----------------------------------
The 5% trail BEFORE the target is reached. His initial stop is
min(structure, 10-20c) and that was measured and rejected. Replacing our
validated stop with a rejected one, in a test of the exit, would confound the
question with a settled answer. So: our stop until the target, his after it.
That is a hybrid and the report says so rather than claiming to be his method.
"""
from __future__ import annotations

from dataclasses import dataclass

# 2R against MCL's 5% trail. See the module docstring -- this is derived from
# his stated 2:1 re-posed against a percentage stop, exactly as warrior_0 §5.2
# says it must be, and NOT chosen because it wins.
TARGET_PCT = 10.0
TAKE_FRAC = 50.0


@dataclass(frozen=True)
class TargetExit:
    """One target, one partial, one stop change.

    take_frac = 0 is a real cell, not a disabled one: it moves the stop to
    breakeven at the target WITHOUT selling anything, which isolates the stop
    change from the partial. `is not None` on the caller's side keeps that
    distinguishable from "no target exit at all".
    """
    target_pct: float = TARGET_PCT
    take_frac: float = TAKE_FRAC
    # After the target: stop sits at the entry price and the trail is OFF.
    # False keeps MCL's trail on the remainder, which is the ladder's behaviour
    # and the control that isolates the partial.
    breakeven: bool = True

    def target_price(self, entry_px: float) -> float:
        return entry_px * (1.0 + self.target_pct / 100.0)

    def qty_at_target(self, held: int) -> int:
        """Truncating, so the position can never be oversold, and never the
        whole position -- taking 100% at the target is a different rule (a
        fixed profit target) and would make the breakeven stop unreachable,
        so the two would be indistinguishable in the output."""
        if held <= 1 or self.take_frac <= 0:
            return 0
        return max(0, min(int(held * self.take_frac / 100.0), held - 1))
