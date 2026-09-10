#!/usr/bin/env python3
"""A take-profit ladder: sell half on every N% gain, shared by MCL and MC5.

Ben, 2026-09-10: "for every 10% increase, sell 50% of shares until when 20
shares or less, sell them all by either the 10% increase rule, or the trailing
stop mechanism."

THIS IS NOT THE SCALE-OUT THAT WAS REJECTED
-------------------------------------------
`claude/archive/mcl_scale_out_decision.md` rejected a mechanic that sold into a
PULLBACK and bought back on the recovery. This one sells into STRENGTH and
never buys back. Opposite direction, no re-entry, no position growth. The two
should not be conflated and a verdict on one is not a verdict on the other.

But §4 of that document carries an argument that applies here with more force,
and it is registered before the run rather than discovered after:

    With size held constant, the mechanic CANNOT earn more on a runner than
    simply holding. What it buys is a better exit on trades that end at the
    stop. So it trades runner profit for stop-out profit: a risk-shaping
    change, not a return change.

A ladder is the sharper version of that trade, because it sells ONLY when the
trade is winning -- precisely the trades MCL's money is in. `hold_cap_decision`
measured the baseline's P/L by hold length and found every bucket profitable
except 1-bar holds, with 60+ bars the best at +$36.33/trade. Those long holds
are the runners a ladder caps.

**So the expected sign is negative**, for the same arithmetic reason the time
cap was. What makes this worth measuring anyway is that a ladder is not a time
cap: it never sells a loser early, so the left tail is untouched. Whether the
locked gains outweigh the forfeited upside is an empirical question about how
often a trade that reaches +10% goes on to +21%, and `rung_survival()` answers
that WITHOUT the ladder at all.

PINNED BEFORE RUNNING
---------------------
Ben's rule, as he specified it on 2026-09-10 when asked:

    STEP_PCT     10.0   each rung is 10% above the PREVIOUS RUNG's price, not
                        10% of entry -- so rungs sit at 1.10x, 1.21x, 1.331x,
                        1.464x of entry. This is the literal reading of "every
                        10% increase". `ladder_linear()` is the alternative and
                        is a CONTROL, not a second candidate.
    SELL_FRAC    50.0   half of the CURRENT position at each rung
    FLOOR_SHARES   20   at or below this the next rung sells the whole
                        remainder, rather than leaving a 6-share and then
                        3-share tail each paying a per-order commission minimum

On the 100-share entry MCL and MC5 both use, that is: 50 at +10%, 25 at +21%,
13 at +33.1%, and the last 12 at +46.4%.

TWO THINGS THIS MUST NOT DO, both of which would flatter it
-----------------------------------------------------------
1. **Fire on the bar's HIGH.** A rung reached only by the bar's high is a rung
   reached intrabar, at a price the strategy could not have acted on -- the
   same optimism `seed_peak_with_bar_high` exists to control. Rungs are tested
   against the CLOSE. On a 5-minute bar the difference is large.

2. **Round the sell quantity up.** `int()` truncates, so 25 -> 12 and not 13,
   and the position can never go negative or oversell. A ladder that sold one
   share more than it held would show as a phantom profit on the final rung.
"""
from __future__ import annotations

from dataclasses import dataclass

STEP_PCT = 10.0
SELL_FRAC = 50.0
FLOOR_SHARES = 20


@dataclass(frozen=True)
class LadderConfig:
    step_pct: float = STEP_PCT
    sell_frac: float = SELL_FRAC
    floor_shares: int = FLOOR_SHARES
    # False = Ben's rule (each rung 10% above the last rung's PRICE).
    # True  = the control: each rung a fixed 10% of the ENTRY price.
    linear: bool = False

    @property
    def step(self) -> float:
        return 1.0 + self.step_pct / 100.0


def rung_price(entry_px: float, n: int, cfg: LadderConfig = LadderConfig()) -> float:
    """Price of the n-th rung, n starting at 1.

    Compounding: entry * 1.10^n. Linear: entry * (1 + 0.10n).
    """
    if n < 1:
        raise ValueError("rungs are numbered from 1")
    if cfg.linear:
        return entry_px * (1.0 + n * cfg.step_pct / 100.0)
    return entry_px * cfg.step ** n


def sell_qty(held: int, cfg: LadderConfig = LadderConfig()) -> int:
    """Shares to sell at a rung, given what is currently held.

    At or below the floor the whole remainder goes: leaving a 6-share and then
    a 3-share tail pays IBKR's per-order minimum twice for almost no stock, and
    on a $4 name a $0.35 minimum on 3 shares is 12c a share of commission
    against a 40c move.

    Truncating rather than rounding means 25 -> 12, and the position can never
    be oversold.
    """
    if held <= 0:
        return 0
    if held <= cfg.floor_shares:
        return held
    q = int(held * cfg.sell_frac / 100.0)
    # A fraction that truncates to zero on a position above the floor would
    # stall the ladder forever while the caller kept advancing the rung. Sell
    # one share rather than loop.
    return max(1, min(q, held))


def rungs_reached(entry_px: float, close: float, done: int,
                  cfg: LadderConfig = LadderConfig()) -> int:
    """How many NEW rungs this close clears, beyond the `done` already taken.

    Returns a count rather than a boolean because a 5-minute bar -- or a gap --
    can clear two rungs at once. Treating that as one rung would leave the
    ladder permanently behind the price and would quietly change the rule into
    "sell half every bar while rising".

    Bounded at 64 so a corrupt price cannot spin.
    """
    n = 0
    while n < 64 and close >= rung_price(entry_px, done + n + 1, cfg):
        n += 1
    return n


def plan(entry_px: float, close: float, held: int, done: int,
         cfg: LadderConfig = LadderConfig()) -> tuple[int, int]:
    """(shares to sell now, rungs consumed) for one bar.

    Consuming every rung the close cleared, but selling only ONCE for them, is
    deliberate. Two rungs in one bar means the price ran; halving twice in the
    same bar at the same price would take 75% off at a single price and is not
    what the rule describes. The rung counter advances so the ladder stays
    aligned with the price.
    """
    if held <= 0 or entry_px <= 0:
        return 0, 0
    n = rungs_reached(entry_px, close, done, cfg)
    if n == 0:
        return 0, 0
    return sell_qty(held, cfg), n
