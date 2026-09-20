# Does the intraday floor move a delta? Two mechanics, two answers

`common.pit_delta`, 2026-09-11/12, 546 sessions, 4,997 symbol-days, 100 shares.
`MATERIAL = $0.50/trade` pre-registered in the module before either run.
Outputs `var/reports/pit_delta_mcl_ladder.txt`,
`pit_delta_mcl_cameron_partial.txt`.

## 1. The two results

At $4.26, delta = variant minus base, on identical trades:

| | unfloored | floored | the floor moved it | verdict |
|---|---:|---:|---:|---|
| Ladder | (0.09) | 0.07 | **0.16** | NOT MATERIAL |
| Cameron's partial | (2.65) | (1.78) | **0.87** | **MATERIAL** |

For reference, on the same runs the **level** moved (6.84) — base unfloored
(3.65) to base floored (10.49).

## 2. The pattern between them is the finding

**The floor cannot move a delta that is already zero.** The ladder's delta is
(0.09) and 0.07 — nine cents and seven cents, on a strategy losing $10.49 a
trade. A mechanic that does nothing does nothing on any population, and the 0.16
"move" is two noise figures crossing an axis.

**A mechanic with a real effect gets re-weighted.** Cameron's partial costs
(2.65)/trade unfloored and (1.78) floored. The floor removed 39% of the trades
and left the survivors with different post-entry paths, and the mechanic's cost
fell by **a third** — 0.87 of 2.65.

**Direction survived in both cases.** Cameron's partial is rejected on the
unfloored arm and rejected on the floored one. Nothing reversed.

So the rule to carry forward is:

> **Published deltas are durable in direction and unreliable in magnitude.**

## 3. What this does to `HANDOVER_20260911.md` §4

Its **conclusion** — re-run the rejected mechanics floored — is now **supported**
for any mechanic whose delta is non-trivial.

Its **reason and its magnitude were both wrong**. §4 said every delta is
"overstated by $6.84–$11.99/trade", transferring a level gap onto a difference.
The observed move is **0.87**, roughly one eighth of that, and it is a population
re-weighting rather than an offset — which is why its direction is not knowable
in advance. Cameron's partial came back *less* bad, not more.

`PROGRAM_INDEX` §7 item 3 should stay on the list, re-scoped: *re-run deltas for
mechanics whose delta is non-trivial; expect the sign to hold and the magnitude
to move by roughly a third.*

## 4. A second magnitude problem, separate from the floor

Cameron's partial was published at **−$1,435 over 4,481 trades = (0.32)/trade**
on `bar_cache_xnas`. On the point-in-time universe, unfloored, the same mechanic
costs **(2.65)/trade** — eight times as much.

That gap has nothing to do with the floor; both of those are unfloored figures.
It is the **universe**. So a published delta carries two magnitude risks, and
they compound:

1. the universe it was measured on, and
2. whether its entries were floored.

Neither has flipped a sign yet. Both move the size by multiples.

## 5. The mechanic this cannot reach

Ranked by published delta per trade on `bar_cache_xnas`:

| Mechanic | Published | Per trade | Re-runnable through `pit_delta`? |
|---|---:|---:|---|
| Cameron's **breakeven stop** | (27,260) | **(6.31)** | **No** |
| Take-profit ladder | (1,612) | (0.36) | yes — done, not material |
| Cameron's partial | (1,435) | (0.32) | yes — done, **material** |
| Dip entry | — | — | yes, not run |

**The largest-delta rejection is the one that cannot currently be re-run.** The
breakeven stop is not a single `backtest_session` parameter, and it was left out
of `variant_kwargs` deliberately rather than stubbed: a variant that differed
from its base by nothing would have produced a delta of exactly 0.00 and rendered
as NOT MATERIAL — the same words a real null produces.

Given §2, a mechanic at (6.31)/trade is exactly where re-weighting has the most
room to matter. **Making the breakeven stop expressible as a variant is the next
piece of work on this line**, and it is the only one of the four where the
outcome is genuinely open.

## 6. What is settled

- The ladder's rejection **stands**, on both arms, and the floor is irrelevant to
  it.
- Cameron's partial's rejection **stands in direction**; its published magnitude
  does not transfer to this universe or to a floored run.
- A level bias does **not** transfer to a delta — 0.16 and 0.87 against a level
  move of 6.84.
- The dip entry has not been run and should be, since its delta is non-trivial.
