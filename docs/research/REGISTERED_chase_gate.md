# REGISTERED — don't chase: refuse the entry when the name has already run

**H-P1.** Written and committed 2026-09-18 **before any code exists**, on the
one cell from `running_up_preflight_RESULT_20260918.md` that points the right
way. The pre-flight is descriptive by construction — no threshold, no P&L — and
its own §5 says the reverse filter "has to be registered with its threshold
taken from the distributions printed here, then scored against
`gate_study.abstention`, the friction margin and the symbol-cluster bootstrap,
exactly like H-B1, H-B3 and H-B4 — all three of which read as random removal."
This is that registration.

---

## 1. Where the thresholds come from, and why that is not a search

Every value swept below is a number the pre-flight **already printed**, before
this file existed, on a pass that could not see a P&L. That is the difference
between taking a threshold from a distribution and choosing one from a result:
the deciles of `ret_5m` were computed to describe the trade population, and the
only thing added here is money.

The pre-flight's reverse table, reproduced so the sweep's provenance is on the
record:

| `ret_5m <= cut` | MCL one-bar removed | MCL survivors lost | MC5 one-bar removed | MC5 survivors lost |
|---|---:|---:|---:|---:|
| 0.050 | 81% | 49% | 50% | 26% |
| 0.083 | 64% | 25% | 38% | 14% |
| 0.100 | 57% | 18% | 33% | 11% |

---

## 2. The rule, exactly

> **An entry is refused when `ret_5m` at the entry bar exceeds `CEIL`.**

`ret_5m` is `common.running_up.ret_at(df, ts, back=5)` — **imported, never
restated**, so the gate is the pre-flight's own feature by construction. It is
the five-minute return ending at the entry bar, computed from bars at or before
it, so it is point-in-time by construction too.

Delivered through the engines' existing `entry_gate` hook: a boolean Series
AND-ed with the rule's own signal, `None` bit-identical, the same hook H-B3 and
H-B4 used. **For MC5 the value is stamped on the 5-minute bar label the engine
trades**, matching how the pre-flight computed it.

### Signal-ordinal, not book-ordinal

Refusing an entry leaves the strategy flat, so bars the baseline was *in a
trade* for become live signals and the gated book is **not a subset** of the
baseline. That is the form that would be deployed, it is what `entry_gate`
produces, and the index has had a row about it since 2026-09-17.

---

## 3. The families

**F1 — MCL.** `CEIL` ∈ {0.033, 0.050, 0.083, 0.100, 0.150}. Base: no gate.
**F2 — MC5.** `CEIL` ∈ {0.033, 0.050, 0.083, 0.100, 0.150}. Base: no gate.

One constant moves per family and nothing else does. A test asserts it.

**The boundary check is scored** (§4 of the index): if a family's best cell sits
at the edge of the swept range it reads **UNDECIDED — BOUNDARY** whatever its
numbers. One asymmetry to state before the run, because it will need reading:
this family is **monotone toward the base** — as `CEIL` rises the gate admits
everything — so a best cell at the LOOSE end (0.150) is not an arbitrage, it is
the gate doing nothing, and it reads NOTHING rather than BOUNDARY. A best cell
at the TIGHT end (0.033) is the ordinary boundary case and reads UNDECIDED.

---

## 4. The second condition, and why it is a comparison rather than a cell

The obvious next move is the two-condition version — *near the session high
**and** not extended*, which in an ad-hoc pass over the pre-flight's features
read **3.3% one-bar on MCL against a 12.6% base** and **15.5% on MC5 against
37.2%**. Registering that as a cell would be a mistake, and naming the mistake
is the point of this section.

**`dist_from_high` on its own barely separates anything:** AUC **0.494** on MCL
and **0.443** on MC5, against a `rand` control at 0.526 / 0.505. `ret_5m` reads
0.751 / 0.636. So in a two-condition cell, essentially all the separation is
coming from one of the two conditions, and the other is a second knob that will
look like it is contributing because tightening *any* condition on a losing book
improves the total.

So the second condition is tested the way H-S6 tested the give-back's shape:
**as a difference, at a matched abstention budget.**

> For each book, take the scored `CEIL` cell and its removal count *k*. Solve a
> `dist_from_high >= D` threshold so that `ret_5m <= CEIL AND dist_from_high >= D`
> removes as close as possible to *k* trades in total. Compare the two books per
> trade.

Both rules then spend the same abstention budget and the only thing that differs
is **which** trades they spend it on. `D` is **solved against the constraint,
never chosen**, and the count comes from the incumbent's behaviour rather than
from either rule's P&L, so no comparator is ever selected for performing well.

**If the 2D gate does not beat the 1D gate at the same budget, "near the session
high" adds nothing** and the 3.3% cell is `ret_5m` wearing a second condition.

---

## 5. Reported and never scored

Declared here, before the numbers exist, so that a tempting cell cannot be
promoted after the fact — the FLAT-40 lesson from H-S6.

**5.1 MC5's floor — "don't buy while it is dropping."** The pre-flight found MC5
U-shaped: its bottom `ret_5m` decile (−45% to −1.8%) dies **41.3%** of the time
against a 37.2% base, so a floor at −1.8% is a real but small effect. It is
**reported at `ret_5m >= -0.018` combined with each scored ceiling, and never
scored**, because a band is two free parameters and this project has no budget
for a second knob on a book that is closed as a candidate. Worth about four
percentage points where the ceiling is worth thirty-three.

**5.2 The one-bar exit's distance from the trail.** The pre-flight's §4 names
the leading alternative explanation and it is not an entry story at all: a name
that has just run 11% in five minutes is **more volatile**, and the 5% trail is
a fixed percentage, so the next bar's ordinary range is larger and the trail is
more likely to be hit by noise than by a reversal. On that reading these are not
bad entries — **they are a stop too tight for the volatility at the moment of
entry.**

The two readings predict the same separation and this pass cannot distinguish
them, but one number bears on it and is free off the trades CSV: for the
baseline books' one-bar trades, the distribution of `exit_px / entry_px - 1`
against the trail's −5%. **Exits clustered AT the trail** are the volatility
reading; **exits well below it** are real reversals. Reported for both baselines,
never scored, and it decides which registration comes next rather than this one.

---

## 6. How a cell is read

Every cell carries, and a cell missing any of them is not read:

1. **Per trade and per symbol-day.** A disagreement is a REFUSAL.
2. **The abstention control.** Matched-count random removal, 2,000 seeded draws,
   SEED 20260916, via `gate_study.abstention`. A cell inside the band is
   abstention, not selection, however it reads otherwise. **This is the control
   that killed H-B1, H-B3 and H-B4 and it is the one that decides this.**
3. **The marginal trade** — what each REFUSED trade was worth,
   `(tot(cell) − tot(base)) / (n(cell) − n(base))`. Added to the index's §4 this
   morning from H-E2. A gate that refuses trades worth *more* than the book's
   average is removing the wrong trades whatever the average does.
4. **Both halves**, cut at 2025-08-07, and **drop-top-N** on the delta.
5. **The session-clustered bootstrap**, ≥ 0.95.
6. **All three friction levels**, $1.00 / $4.26 / $8.92, with the $4.26 margin
   applied per trade.
7. **The mechanism, read back as a measurement.** The gate's whole claim is that
   it removes trades that die on the next bar. So every cell prints the **one-bar
   share** of its book. **A cell whose one-bar share does not fall did not
   operate as claimed** and may not be described as removing chases, whatever
   its P&L says. That requirement is what refuted the primary hypothesis of H-E2
   this morning, and it is cheap.

**CLEARS** requires better per trade AND better on total, in BOTH halves, beyond
the abstention band and the margin. Anything less is NOTHING, REFUSED or
UNDECIDED.

---

## 7. What would make this fail, and my prediction

**The prior from the three that came before is bad.** H-B1, H-B3 and H-B4 each
had a mechanism, each removed trades from a losing book, and each landed inside
random removal's band — one of them by four cents. The pre-flight's trade-off
table looks better than any of theirs did, which is a reason to register this
and **not** a reason to believe it.

**Prediction, on the record.** MCL's gate clears the abstention band at 0.083 or
0.100 and still reads REFUSED on the denominators, because removing 25% of the
survivors will cost more per symbol-day than it gains per trade — the exact
shape seven of nine cells took in H-E2 this morning. MC5 is the one I would bet
on for a per-trade pass, because its one-bar trades lose **(31.95)** each and
are 139% of its net, so removing a third of them is arithmetically large.
Moderate confidence on MC5, low on MCL.

**And a pass does not reopen MC5.** The sizing ceiling stands: even a *perfect*
filter on its one-bar problem leaves **+$0.70 a trade at $8.92**. A rule that
recovers part of that reduces a loss; it does not create an edge, and §6 of
`REGISTERED_giveback_cap` already says a pass is not adoptable on its own.

## 8. Nothing ships from this

`holdout.json` stays shut. `entry_gate` is a backtest parameter: the live
evaluator does not take it, a test asserts the signature, and this run cannot
move the trader. No strategy constant is read, written or swept.
