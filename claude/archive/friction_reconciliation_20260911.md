# Friction reconciled — the three numbers are not in conflict

**Created:** 2026-09-11
**Status:** RECONCILIATION of existing measurements + a new sensitivity calculation.
**Governing standards:** `PROGRAM_INDEX.md` §4 — *"Friction, always, and stated"* and
*"An n = 1 measurement is not a constant."*

---

## 0. Summary

Three friction figures circulate in this project and have been treated as contradictory:

| Figure | n |
|---|---|
| **$1.00 / round trip** | 18,552 fills |
| **$4.26 / round trip** | **2 sessions** |
| **$8.92 / round trip** | 6 round trips |

**They are not contradictory. They measure different legs of the trade.** The reconciliation
is in §1.

**But the real finding is §3:** the friction uncertainty **does not change the sign of any
out-of-sample result**. On the screened universe, MCL's break-even friction is **−$0.96 per
round trip** — it would have to be *paid* to break even. Friction is not what is wrong with
these strategies, and the long-running argument about which number is right has been
answering a question that does not affect the conclusion.

---

## 1. The reconciliation

| | What it measures | n | Source |
|---|---|---|---|
| **$1.00 / RT** (median; $0.92 mean) | **Crossing cost only** — how far a fill lands from the touch when you cross the spread | **18,552 fills**, 116,067 matched, XNAS.BASIC `tcbbo` | `execution_cost_measured.md` §3.3 |
| **$4.26 / RT** ($0.0426/share) | **Stop-fill slippage** — the gap when a trailing stop fires and fills worse than its trigger. Charged **on top of** the modelled tick | **2 sessions** | `mcl_apex_macd_sweep.md`; flagged in `PROGRAM_INDEX` §4 |
| **$8.92 / RT** | **End-to-end actual**, one live paper session — both legs plus everything unmodelled | **6 round trips** | `mcl_session_20260909_review.md` |
| $6.50 / RT | **Retracted** — EQUS.MINI tape artefact, reversed within the hour | 116,067 fills | `execution_cost_measured.md` §5 |

**The engines model crossing at `SLIPPAGE_TICKS = 1` = $2.00/RT.** Measured crossing is $1.00.
So the model **overcharges the crossing leg by about $1.00** — the safe direction, and the
reason `execution_cost_measured.md` §4 concluded *"very little, and that is the finding"* and
left `SLIPPAGE_TICKS = 1` in place.

**The $4.26 is a different leg entirely**, and `execution_cost_measured.md` §6 says so in
plain terms:

> *"The stop-fill question is still open. §3.3 gives the spread a software-managed stop has to
> cross in pre-market. Turning that into a fill model is a separate job with its own
> assumptions, and it has not been done."*

So the correct reading is: **crossing cost is well measured and slightly over-modelled;
stop-fill cost is badly measured and is the live uncertainty.**

---

## 2. Why the $4.26 is weaker than its use implies

It is charged in **every** backtest figure this project has published. Three problems:

1. **n = 2 sessions.** `PROGRAM_INDEX` §4 names it directly: *"The $4.26 friction figure is
   n = 2 and is used everywhere — that is a known weakness, not a settled number."*
2. **It was measured on the wrong exit mix.** `execution_cost_measured.md` §1: the estimate was
   *"taken on a session that was 81% apex exits — for a configuration that now produces ~95%
   trailing exits."* It is an n=2 measurement of a mechanic the engine has since largely
   stopped using, applied to the mechanic that replaced it.
3. **The one independent check came in 2.1× higher.** The live paper session measured
   **$8.92/RT** on 6 round trips, with 76% of the loss attributed to execution gap.

And the well-sampled $1.00 figure cannot be substituted for it, because
`execution_cost_measured.md` §6 warns what it is:

> *"These are discretionary hotkey orders at chosen moments. They bound what is achievable on
> this universe at these hours; they do not measure what MCL's marketable limits would get."*

A human choosing his moment is a **lower bound** on what a mechanical stop firing into a
pre-market move will pay. Pre-market median spread is **83 bps** ($0.0300) on 17,625 fills —
a stop that has to cross that is structurally worse than a discretionary entry that waits.

---

## 3. Sensitivity — and this is why the argument matters less than it looked

P&L is linear in the per-round-trip charge, so every published figure can be re-priced
exactly. Below, each variant at the low ($1.00), shipped ($4.26) and live-observed ($8.92)
friction:

| Variant | n | @ $1.00 | @ $4.26 | @ $8.92 | Sign |
|---|---:|---:|---:|---:|---|
| MCL, `bar_cache` (**fitted**) | 485 | +$1,742 | +$161 | −$2,099 | **FLIPS** |
| MC5 apex-off, `bar_cache` (**fitted**) | 671 | +$8,158 | +$5,971 | +$2,844 | stays positive |
| **MCL, screened universe** | 4,481 | **−$8,786** | −$23,394 | −$44,275 | **stays negative** |
| **MC5, screened universe** | 10,905 | **−$61,785** | −$97,335 | −$148,152 | **stays negative** |
| **VW9, screened universe** | 1,477 | **−$2,510** | −$7,325 | −$14,208 | **stays negative** |

### Break-even friction — the charge at which each variant is exactly zero

| Variant | Break-even friction |
|---|---:|
| MC5 apex-off, `bar_cache` (fitted) | $13.16 / RT |
| MCL, `bar_cache` (fitted) | $4.59 / RT |
| **MCL, screened universe** | **−$0.96 / RT** |
| **VW9, screened universe** | **−$0.70 / RT** |
| **MC5, screened universe** | **−$4.67 / RT** |

**A negative break-even friction means the variant loses money at zero cost.** MCL on the
screened universe would need to be *paid* $0.96 per round trip to reach breakeven. MC5 would
need $4.67.

**Conclusion: friction is not what is wrong with these strategies.** Every out-of-sample
result is negative *gross*, before any cost assumption is applied. The friction figure only
determines the sign of the two variants measured on the hindsight-selected `bar_cache`, which
were never the evidence.

This is the same conclusion `execution_cost_measured.md` §4 reached from the other direction —
*"Crossing cost was never the thing that was wrong"* — now extended to the full friction
range and to the screened universe.

---

## 4. What is decided and what is not

**Decided:**

- The three figures measure different things and are not in conflict.
- Crossing cost is **well measured at $1.00/RT** (n=18,552) and **over-modelled at $2.00**.
  `SLIPPAGE_TICKS = 1` stays; the overcharge is in the safe direction.
- **Friction uncertainty does not change any out-of-sample verdict.** No strategy is rescued
  at $1.00, and none newly fails at $8.92 that was not already failing.
- Every published `bar_cache` figure should be read as sign-unstable across the friction
  range, and therefore as carrying no weight independent of the screened-universe result.

**Not decided:**

- **The stop-fill cost is genuinely unknown.** n=2, wrong exit mix, and the single live check
  landed at 2.1×. This is the largest un-nailed number in the project.
- Whether the live $8.92 is representative or is an n=6 outlier.
- Whether MCL's mechanical marketable-limit stops do better or worse than Ben's discretionary
  hotkey fills. The evidence says worse; nothing measures how much worse.

---

## 5. What would close it

In order of value, and none of these is expensive:

1. **Log the quote with every live order.** `execution_cost_measured.md` §8 item 2 already
   proposes this: *"so friction is a standing measurement rather than a study. This is what
   stops n = 2 recurring."* This is the single highest-value item here — it converts friction
   from a periodic argument into a running number, and IBKR's own real-time quotes (already
   paid for) serve it. **No new subscription needed.**
2. **Price the stop leg separately from the entry leg** in the backtest, rather than charging
   one blended number per round trip. The two legs have different spreads (pre-market 83 bps
   vs RTH 60 bps) and different urgency.
3. **Report every result at all three friction levels**, as §3 does here. It costs one extra
   column and removes the argument from every future doc.
4. **Re-measure stop-fill gap** on the accumulated live sessions once there are more than a
   handful.

---

## 6. Reporting rule going forward

Any P&L figure published in this project should state **which friction charge was applied**
and, where the sign is not stable across $1.00–$8.92, **say so**. A figure quoted at $4.26
without that note is quoting an n=2 measurement of a superseded exit mechanic as though it
were a constant.

---

## 7. Corrections to make elsewhere

- `PROGRAM_INDEX.md` §7 item 1 should record that crossing cost is now **closed** (n=18,552)
  and that the **open** item is specifically **stop-fill slippage**, not friction in general.
  These are currently conflated.
- Any doc describing $4.26 as "the measured friction" should say "the measured **stop-fill**
  friction, n=2", since the better-measured number for the other leg is $1.00.
