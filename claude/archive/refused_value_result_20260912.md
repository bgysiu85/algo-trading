# The bars `c_floor` refused were worth less than nothing

`python -m common.refused_value` · raw: `var/reports/refused_value_floor_sole.txt`,
`refused_value_locked.txt` · bundles `20260912ab`, `20260912ac`

Pre-registered prediction (2026-09-12, before the run): *removing or relaxing
`c_floor` will lose money or be immaterial.* **It held.**

## floor_sole — settled

2,102 refused bars over 168 symbol-days produced 308 trades, priced through
MCL's own exit. Control is the rule unchanged on the same symbol-days.

| friction | n | per trade | win% | drop-top-5 |
|---|---:|---:|---:|---:|
| REFUSED $1.00 | 308 | (0.15) | 37.3% | (3.40) |
| control $1.00 | 482 | **3.63** | 37.3% | 0.34 |
| **REFUSED $4.26** | 308 | **(3.41)** | 33.8% | (6.66) |
| **control $4.26** | 482 | **0.37** | 34.0% | (2.92) |
| REFUSED $8.92 | 308 | (8.07) | 27.9% | (11.32) |
| control $8.92 | 482 | (4.29) | 29.5% | (7.58) |

Both halves negative: **(5.43) early, (2.05) late.** Drop-top-5 deepens the loss.
Negative at every friction level.

**The refused bars lose $3.41 a trade where the rule's own entries make $0.37.**
The concurrency cap never has to be consulted: a population with negative
expectancy loses money at any scale. `c_floor` is not costing setups — it is
declining bad ones, and worse-than-average ones at that.

## locked — NO VERDICT, and the first report got this wrong

The targeted population (ignition refused *and* follow-through locked out) is
210 trades:

| friction | per trade | control |
|---|---:|---:|
| $1.00 | **3.20** | 3.63 |
| $4.26 | **(0.06)** | 0.37 |
| $8.92 | (4.72) | (4.29) |

Halves: **(3.39) early, +2.70 late — disagreeing in sign.**

Six cents below zero with the halves pointing opposite ways is not a settled
loss; it is an unstable measurement that landed just under the line. The
standing evidence rule refuses a verdict on that, and the report declared one
anyway.

**Cause: verdict ORDER.** `per < 0` was tested before the split check, so every
pooled negative — however small, however unstable — short-circuited into
"settled" and skipped the halves rule entirely. The rule was in the code and
unreachable from the branch that mattered. Fixed in `20260912ac`: halves are
checked first whatever the sign, and a disagreement renders as a refusal that
explicitly neither clears nor condemns the mechanic.

## What locked actually shows

It is **friction-marginal**: +3.20/trade at $1.00, roughly break-even at $4.26,
clearly negative at $8.92. Its drop-top-5 (4.60) is worse than the control's
(2.92), so what edge exists is concentrated. And the halves disagree.

That is the worst possible profile for a candidate mechanic. It is not evidence
of an edge; it is evidence that any edge is smaller than the cost of trading it,
and unstable over the period besides.

## The decision

**Leave `c_floor` alone.** No `pit_delta` variant is warranted:

1. Remove `c_floor` — refuted directly. The bars it refuses lose $3.41/trade.
2. Relax `FLOOR_FRACTION` — a weaker version of (1), pulling in a subset of the
   same losing population.
3. The re-arm window — targets `locked`, which returns no verdict and is
   friction-marginal at best.

The TNON 07:35 miss is real, it happens 3.12 times a session, and **it is the
rule working.** The bars it refuses are worse than the bars it takes.

## What this does not say

- **Not a claim about the market.** Taking these positions would have moved
  fills, changed which names were held, and changed what the cap refused next.
  None of that is modelled.
- **Not out of sample.** Same symbol-days as the interlock census, chosen
  because MCL traded them.
- **Not a statement about `c_vol`.** 15,956 bars were refused by the multiple
  alone — 58.3% of judgeable bars, seven times the `c_floor` count. That
  population has not been priced, and it is much the larger one.

## The one open follow-on

`c_vol` alone blocks 58.3% of judgeable bars against `c_floor`'s 7.7%. The same
machinery prices it with a one-line population change. Given this result the
prior should be that it too is declining bad bars — but it is seven times the
size, and nobody has looked.
