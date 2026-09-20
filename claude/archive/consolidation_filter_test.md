# Consolidation filter — measured, 2026-09-09

Ben, watching tonight's MCL paper session: *"the buy order for ACCL at 6:31am
is during a period of consolidation … we would just be holding a stock for
long periods, exposing us to more risks and wasting opportunities as this
would have taken 1 of 2 available buy slots. We need a safeguard … Perhaps
using the Bollinger Bandwidth? When the Higher band and the Lower Band are
narrowing the gap, we should not take any trades. Only take trades when the
gap begins to widen."*

**Not registering it. The proposal is backwards in this data, and the premise
it rests on does not hold.** What the measurement did turn up is a different
and larger problem, in §4.

Measurement: `var/reports/consol2.py`, output
`var/reports/consolidation_measurement.txt`. 373 cached sessions (bar_cache,
2025-09-02 → 2026-09-04), MCL live config, 100 shares flat, cap 2, tiered
commission plus the measured $4.26/RT.

Parameters pinned before looking, at the conventional Bollinger defaults, and
not swept: length 20, 2 sd, on 1-minute closes; `BBW = (upper−lower)/basis`;
slope = `BBW[t] − BBW[t−5]`.

**What this evidence is not.** `holdout.json` splits the *screened* universe,
not `bar_cache`, so the locked slice offers no protection here — and MCL was
fitted on this data anyway. The controls available are both halves (split at
the calendar midpoint, 2026-03-20, chosen once) and drop-top-3. Anything that
fails those is not a finding.

---

## 1. A slot is not scarce, so nothing is being "wasted"

| | |
|---|---:|
| trades taken | 479 |
| **denied by the 2-position cap** | **9  (1.9%)** |
| denied for capital | 0 |
| the same run with **no cap at all** | 485 trades |
| net, capped | **+$270** |
| net, uncapped | **+$162** |

Over a year the cap turned away nine entries, and lifting it entirely makes
the strategy *worse* — the six extra trades cost $108. Whatever ACCL was doing
in that slot, it was almost certainly not displacing another trade, and on
this evidence a freed slot is worth about nothing.

That removes the "wasting opportunities" half of the argument. The
"holding for long periods" half is real and is §4.

## 2. The proposed gate points the wrong way

Bucketing each of the 479 entries by the bandwidth slope over the five bars
before it — negative is narrowing, which is what Ben would skip:

| BBW slope at entry | n | net | per trade | drop-top-3 |
|---|---:|---:|---:|---:|
| **< −0.005  (narrowing — would be SKIPPED)** | 68 | **+$686** | **+$10.09** | +$1 |
| −0.005 – 0 | 22 | −$14 | −$0.64 | −$281 |
| 0 – 0.005 | 38 | −$103 | −$2.71 | −$352 |
| **≥ 0.005  (widening — would be KEPT)** | 351 | **−$299** | **−$0.85** | −$1,304 |

And in both halves, on the one split:

| | narrowing (skip) | widening (keep) |
|---|---:|---:|
| early (→ 2026-03-20) | n=35, +$2.09/trade | n=139, −$2.31/trade |
| late (2026-03-20 →) | n=55, +$10.89/trade | n=250, −$0.32/trade |

The sign is the same in both halves and it is the opposite of the proposal:
the entries taken into a *contracting* range are the ones that made money; the
entries taken into an *expanding* range are the ones that lost it. Gating the
way it was described would have removed the only positive group.

Bandwidth *level* says the same thing more weakly — the narrowest quintile
(+$2.87/trade) beats the second (−$5.18) and roughly ties the widest.

**But it is not a finding in either direction.** Drop-top-3 takes the
narrowing bucket from +$686 to +$1, and in the late half from +$599 to −$12.
Three trades are the entire effect. The correct conclusion is not "invert the
rule" — it is that bandwidth at entry does not separate these trades, and a
gate built on it would be fitted to three of them.

## 3. Why the direction is not a surprise

`premarket_hypotheses_results_20260908.md` §2 measured every entry
confirmation this project has tried and found each one made the screen worse:
H0 (buy at 04:30, no rule) +$4.72/trade, H1 (new session high on 2× volume)
−$8.44, H2 (opening-range break on 2× volume) −$12.21. The reading there was
that confirmation-style entries on pre-market gappers buy the top of the move.

"Only take trades when the gap begins to widen" is another confirmation rule,
and it lands in the same place. The cross-tab is consistent with it: entries
held under five minutes come in at a median BBW of 0.176 and are 78% widening;
entries held five minutes or more come in at 0.064 and are 64% widening. The
losers are the ones bought after the range had already opened up.

## 4. The finding that matters, and it is not the one we went looking for

| hold | n | net | per trade | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|---:|
| **0–5 min** | **316** | **−$1,935** | **−$6.12** | **−$2,940** | −$736 | −$1,200 |
| 5–15 min | 99 | +$1,337 | +$13.50 | +$765 | +$482 | +$854 |
| 15–30 min | 25 | +$11 | +$0.44 | −$303 | +$113 | −$102 |
| 30–60 min | 22 | +$240 | +$10.90 | −$73 | +$9 | +$231 |
| 60–120 min | 12 | +$177 | +$14.76 | −$90 | −$85 | +$262 |
| 120 min+ | 5 | +$440 | +$88.10 | −$32 | −$32 | +$472 |

Two thirds of all trades are stopped out inside five minutes, they lose
$1,935, they lose it in **both halves**, and drop-top-3 makes the number
*worse* — so this is not one bad trade, it is the shape of the book. Every
longer bucket is positive. The trades Ben is worried about, the ones that sit
for an hour, are where the money is.

That inverts the concern. The exposure worth removing is not the position that
sits; it is the position that is bought and stopped out before the next
coffee. 456 of 479 exits are the trailing stop and the median hold is 2
minutes: a 5% trail on a $5 stock is 25 cents, which these names cover in a
minute or two of noise.

**This is a description, not a rule.** Hold time is known only after the fact
and cannot be filtered on at entry. What it does is redirect the question from
the entry to the exit — and the exit has its own measured history
(`mcl_trail_decision.md`, `mcl_stop_timing_study.md`), which is where a
registration should start rather than with a new entry gate.

## 5. What I would register instead, if anything

Nothing yet, and specifically not a bandwidth gate. The ranked candidates:

1. **A minimum-time or minimum-excursion stop.** Do not arm the 5% trail for
   the first N minutes, or until the position has been green by some amount.
   Directly aimed at the −$1,935. It is an exit change, so it needs the trail
   studies as its benchmark, N pinned before the run, and a boundary check.
2. **The screener simulation** (PROGRAM_INDEX §7 item 1). Still the largest
   open item and it sits underneath all of this: the universe these 479 trades
   were drawn from was chosen with the whole day known.
3. Bandwidth, only as part of (1) and only if it survives drop-top-N — which
   on this evidence it does not.

## 6. What was not checked

ACCL itself. Tonight's session was still running when this was written; its
own outcome should be read from the fill log afterwards. One trade cannot
settle any of the above, but it is worth seeing whether it landed in the
0–5-minute bucket or the long tail — the answer changes which of the two
stories it belongs to.
