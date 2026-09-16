# REGISTERED — MCL-PB v4: the structure stop

v3 (`REGISTERED_pullback_break_v3.md`, `claude/pullback_break_v3_RESULT_20260916.md`)
was the first version to beat MCL per trade in both halves and still read
NOTHING. Its exits explain why: green-hold exits +4.31 mean / (2.63) median on
9,308 trades against trailing-stop exits (23.42) on 9,709 — a 3-bar profit take
paired with a 5% stop. v4 changes the stop and nothing else.

## 0. The prior, stated before the run

**The stop lever is closed for MCL** (`claude/stop_lever_closed_20260914.md`):
cent stops from $5 to $25 per 100 shares were monotonically worse than the 5%
trail on the 3,955-trade point-in-time book, reproducing the 10/15/20c rejection
in `mcl_rejected_mechanics.md`. Winners' drawdowns overlapped losers' at every
width that caught meaningful numbers of losers.

Why this is a registration and not a relitigation:

1. **Different entries.** MCL buys the close of a 3× volume bar; v3 buys the
   close of a break above a bounce top after a two-red-bar pullback. The
   pullback low is a structural level MCL's entries do not have.
2. **A structure stop, not a cent stop.** The stop is the pullback's own low,
   so it scales with each setup rather than with the price band — the objection
   that killed the cent stop (7.5% at $2, 0.75% at $20) does not apply.
3. **A full engine re-run, not an estimate.** `stop_lever_closed` §3 rejected
   its own best row because 88% of it was assumption. Here every trade is
   walked bar by bar through the published engine with the stop in place.

If v4 is worse than v3, the stop lever is closed for the pullback line as well,
and this line of work ends on that.

## 1. The rule

Everything as v3. In addition, at entry:

    hard_stop = min(low[peak_bar .. break_bar]) - 1 tick

i.e. one tick under the lowest low from the swing-high bar through the break
bar inclusive. The position exits on any bar whose low reaches it, at
`min(stop, open) - 1 tick` (gap-through, the trail's convention), labelled
`structure_stop`. The 5% trail remains and replaces the stop whenever it is the
higher level, so the position is always protected by the tighter of the two.

No minimum or maximum stop distance. A pullback deeper than 5% simply means the
trail is the binding level from the start, as in v3.

## 2. Cells

| cell | green hold | structure stop |
|---|---|---|
| **PB4-g3** (primary) | 3 bars | yes |
| PB4-g0 | none | yes |
| PB3-g3 | 3 bars | no — v3's primary, re-run as the control |

Verdict rule v1 §3, read on PB4-g3 against MCL. **And a second, registered
reading**: PB4-g3 against PB3-g3 on net per trade in both halves, and on the
mean of `structure_stop`+`trailing_stop` exits against v3's (23.42) — because
the claim under test is that the losers get cheaper without the winners being
cut proportionally. Both must hold for the stop to be called a direction.

## 3. What is expected, written down

If `stop_lever_closed` generalises, the structure stop will cut winners as
often as losers and PB4-g3 will be worse per trade than PB3-g3. That is the
null. `holdout.json` untouched.
