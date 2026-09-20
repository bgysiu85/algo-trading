# Prior-spike retention — measured, 2026-09-10

> **SUPERSEDED BY §6 — 2026-09-10.** The "cruder split" result in §2 below was
> measured on `bar_cache`, the 373 sessions MCL was fitted on. §4 step 1 said to
> re-run it on the screened universe before believing it. That re-run is done
> and **the separation does not survive**: on 4,212 screened trades, names that
> had run before do no better than names that had not, and the sign flips
> between halves. §2 is left as written because the method was right and the
> universe was not. **Do not spend the holdout on this.**

Two Warrior documents describe the same filter from opposite sides:
`warrior_0_universe_and_risk.md` §7.1 rejects a name that ran and gave the move
back; `warrior_3_gap_and_go.md` §1 grades **former runner** as ideal and
**former pump-and-dump** as avoid. Warrior 3 §2 notes they are one computation.

**Neither version is supported once the universe is not the fitting set.**

Tool: `common/prior_spike.py`. Report: `var/reports/prior_spike.txt`.
No Databento pull needed; the daily archive was already on disk.

---

## 1. Pinned before running

60-session window ending **5 sessions before the trade**; a spike is a run of
+100% peak-over-base; former runner ≥ 50% retained, pump-and-dump < 20%.

The five-session gap is the design. Without it the search runs up to the trade,
finds the move being traded, and files it as that name's own prior spike —
scoring every winner a former runner by construction.

## 2. The result on `bar_cache` — SUPERSEDED, see §6

373 sessions, 485 MCL trades, 100 shares flat, after commission and $4.26/RT.

| group | trades | net | per trade | win% | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|---:|
| former runner | 137 | +$447 | +$3.26 | 40.9% | −$302 | +$17 | +$430 |
| partial hold | 47 | +$774 | +$16.48 | 44.7% | +$5 | +$154 | +$620 |
| pump and dump | 30 | −$222 | −$7.39 | 33.3% | −$523 | +$68 | −$290 |
| no prior spike | 237 | −$762 | −$3.22 | 28.7% | −$1,599 | −$520 | −$242 |
| too new to judge | 34 | −$77 | −$2.25 | 29.4% | −$415 | +$33 | −$109 |

### His own split — NOT SUPPORTED

Former runners beat pump-and-dumps by **+$10.65/trade**, which is the right
direction, but the sign flips between halves. Thirty trades on one side. Not a
finding.

### The cruder split — SUPPORTED here, and only here

| | trades | net | per trade | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|
| **any prior spike** | 214 | **+$1,000** | **+$4.67** | **+$144** | +$4.20 | +$4.84 |
| **no prior spike** | 237 | −$762 | −$3.22 | −$1,599 | −$5.15 | −$1.78 |

Positive after drop-top-3, same sign in both halves, 214 against 237 trades.
On this cache, MCL's entire measured result sat in names that had run before.

**This is exactly the shape a fitted result takes.** MCL's parameters were
chosen on these 373 sessions; a subset rule that concentrates their profit is
describing the fit, not a property of the market. §6 is what that distinction
costs.

## 3. Three faults the first run exposed, and one it did not

The first run reported a different verdict. Corrected:

1. **Both controls compared net totals** across groups of 137 and 30 — so they
   compared group size, not performance. Now per trade.
2. **"No prior spike" was two answers.** A name with eight daily bars has not
   been shown to be quiet, only to be new. Splitting out "too new to judge"
   moved 34 trades and −$77 out of that bucket.
3. **Drop-top-3 needs a group to drop from.** Below 15 trades the report now
   draws no verdict.

The fault it did **not** expose: this scores trades MCL already took. A filter's
real job is changing which names reach the watchlist, and that needs the
screener simulation.

## 4. What to do with it, in order

1. **Re-run on the screened universe.** — **DONE, §6. It fails.**
2. ~~Then spend the holdout, once.~~ **Do not.** §4 step 2 said to spend it
   "only once there is something worth spending it on." There is not. The
   holdout stays clean.
3. ~~Then consider it as a screen rule.~~ Nothing to consider.

## 5. Confounds not yet ruled out

- **IB bars are split-adjusted**, and a reverse split follows a price collapse
  — exactly the names in the pump-and-dump bucket. An adjusted history can turn
  a collapse into a flat line, biasing that group toward looking better than it
  was. This is unresolved on both caches.
- **The +100% threshold is pinned, not tested.** A sweep over it would be
  fitting.
- §6 does not rule out that the filter works on the *screen* rather than on
  trades already taken. It rules out the version that was measured.

---

## 6. The screened-universe re-run — the finding does not survive

`bar_cache_xnas`, XNAS.BASIC, **training side only** (before 2026-01-12; 8,484
sessions set aside). 19,292 cached sessions, **4,481 MCL trades** — nine times
§2's sample. Halves split at the registered `both_halves_split` 2025-04-08.

| group | trades | net | per trade | win% | drop-top-3 | early | late |
|---|---:|---:|---:|---:|---:|---:|---:|
| former runner | 948 | −$4,556 | −$4.81 | 27.2% | −$5,802 | −$2,846 | −$1,710 |
| partial hold | 428 | −$2,917 | −$6.82 | 29.2% | −$3,446 | −$330 | −$2,587 |
| pump and dump | 262 | −$1,979 | −$7.55 | 26.3% | −$2,682 | −$30 | −$1,948 |
| no prior spike | 2,574 | −$13,858 | −$5.38 | 25.1% | −$18,291 | −$104 | −$13,754 |
| too new to judge | 269 | −$84 | −$0.31 | 27.9% | −$2,064 | +$162 | −$246 |

### The cruder split — NOT SUPPORTED

| | trades | net | per trade | drop-top-3 | early/trade | late/trade |
|---|---:|---:|---:|---:|---:|---:|
| any prior spike | 1,638 | −$9,452 | −$5.77 | −$10,698 | −$5.00 | −$6.26 |
| no prior spike | 2,574 | −$13,858 | −$5.38 | −$18,291 | −$0.10 | −$8.69 |

The gap **inverts**: on the screened tape, names that had run before do
marginally *worse* per trade, and the halves disagree — spiked names are worse
early (−$5.00 vs −$0.10) and better late (−$6.26 vs −$8.69). §2's +$7.89/trade
separation is gone.

### The rubric's own claim — NOT SUPPORTED, again

Former runner −$4.81 vs pump-and-dump −$7.55, a +$2.75/trade gap pointing the
right way, but the sign flips between halves on per-trade figures. Same verdict
as §2, now on 948 and 262 trades instead of 137 and 30.

### Every group loses money, and that is the frame

Total **−$23,394 over 4,481 trades, −$5.22/trade, 25–29% win rate**. Friction
alone is 4,481 × $4.26 = **$19,089**; after commission and before slippage the
book is −$4,305, or **−$0.96/trade**. That is consistent with
`screened_universe_results.md` §2 (MCL −$0.53/trade on `bar_cache_db`,
commission only) — the same known result on a different tape, not a new one.

The best group in the table is −$4.81/trade. **No subset rule rescues a
strategy that loses on every subset**, so the question this doc was asking was
partly moot on this universe before it was asked.

### What made the difference between §2 and §6

The universe, not the code. §2 is 485 trades on the days MCL was tuned on. §6 is
4,481 trades on days chosen by a rule. The filter's separation lived entirely in
the first and not at all in the second.

### The halves control had to be repaired first

The 12:56 run of this same command printed **every `late` column as 0.00** — the
halves split was derived from the full cache's calendar midpoint (~2025-Q4/2026-Q1),
which lands *after* the training cut at 2026-01-12, so the entire training side
fell in `early` and the control divided nothing. `(x) × (0) = 0` then read as
"the sign flips between halves" and produced two confident verdicts from a
control that had not run. **Both verdicts in that run were void.**

Fixed in `common/prior_spike.py`: the split prefers `holdout.json`'s registered
`both_halves_split` (2025-04-08) and falls back to the midpoint of the dates
*actually being scored*; and an emptiness guard counts trades per half — on
counts, not means, because a mean of 0.00 is ambiguous between "no trades" and
"trades averaging zero" — and refuses to draw any verdict if either half is
empty. The 13:16 run in the table above is the first one whose control divided.

This is the fourth instance this week of the project's recurring defect shape:
**two values that agree by accident hide a defect in either.** Here a control's
output was indistinguishable from the failure it was built to detect.

## 7. What this leaves

- Three rules across two Warrior documents — §7.1's daily trust check and both
  history rows of the Gap-and-Go rubric — have **no support on this tape** and
  should stop being quoted as candidates.
- `holdout.json` stays **unspent**. It was cut 2026-09-07 and remains clean.
- The one version not yet tested is the filter as a **screen rule** — changing
  which names reach the watchlist rather than scoring trades already taken.
  That needs the screener simulation (`screener_simulation_scope.md`), which is
  now the gating piece of work for this and for H0 both.
