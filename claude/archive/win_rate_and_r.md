# Win rate is not the target — the measured case

**Created:** 2026-09-11
**Status:** SYNTHESIS of measurements already in this project. No new backtest was run.
**Prompted by:** Ben asking for the highest-win-rate intraday small-cap momentum strategy.
**Governing standards:** `PROGRAM_INDEX.md` §4.

---

## 0. The one-line answer

**The highest win rate ever recorded in this project belongs to Ben's own real trading —
48.7% — and it lost $114,983.** Every mechanic tested here that deliberately raised win rate
lost money, and the two variants with the best expectancy have win rates of **34.9%** and
**34.0%**. Win rate and profitability point in opposite directions in every measurement we have.

---

## 1. The identity that settles it

For a strategy with win rate `p`, average win `W` and average loss `L`, define
**R = W / L** (the reward-to-risk ratio). Expectancy is positive only when

```
p  >  1 / (1 + R)        equivalently    R  >  (1 - p) / p
```

**A win rate is meaningless without R.** It is half of a two-variable condition.

The identity checks out against all four books we have numbers for:

| Book | Avg win | Avg loss | **R** | Breakeven win rate | Actual | Margin |
|---|---:|---:|---:|---:|---:|---:|
| **Ben, real trades** (1,658 RT) | 11.9c | 20.6c | **0.58** | **63.4%** | 48.7% | **−14.7 pts** |
| MCL backtest (2,413 trades) | 41.8c | 20.8c | **2.01** | 33.2% | 32.4% | −0.8 pts |
| Cameron 2024 (self-reported) | 12c | 12c | 1.00 | 50.0% | 65.5% | +15.5 pts |
| Cameron 2025 (self-reported) | 18c | 15c | **1.20** | 45.5% | **71.1%** | **+25.6 pts** |

Source for rows 1–2 and Cameron: `execution_gap_20260910.md` §1 — **the only doc in this
project that pairs a win rate with average win, average loss and R.** Everywhere else R is
not computable from what was reported.

### Reading the table

- **Ben has the second-highest win rate and the worst result.** 48.7% is a perfectly
  respectable hit rate. It is 14.7 points short of what his R requires.
- **MCL has the lowest win rate (32.4%) and comes closest to breakeven** (−0.8 pts), because
  its R is 2.01 — it wins twice what it loses.
- **Cameron's edge is not his win rate.** At R = 1.20 his bar is 45.5%. He clears it by 25.6
  points. Had he traded at Ben's R of 0.58, his 71.1% would still be a *losing* system by
  reference to a 63.4% bar — he would clear it by only 7.7 points, and with 12–18c average
  wins that margin is inside the friction band.

---

## 2. What Ben actually needs — stated two ways

At his existing **48.7%** win rate, breakeven requires **R ≥ 1.05**. He is at **0.58**.
Holding one leg fixed, the two routes are:

| Route | What must change | Size of the change |
|---|---|---|
| **A — hold winners longer** | avg win 11.9c → **21.7c** | **+82%** |
| **B — cut losers smaller** | avg loss 20.6c → **11.3c** | **−45%** |

For scale: **Cameron's average loss is 15c. Ben's is 37% bigger. Cameron's average win is
18c. Ben's is 34% smaller.** The gap is on both legs, and it is not a gap in how often he
is right.

**This reframes the whole problem.** "Get a higher win rate" is a 14.7-point ask against a
bar that moves every time the exit changes. "Cut the average loss by 45%, or nearly double
the average win" is a concrete engineering target that does not move.

---

## 3. The price list — win rate is purchasable, and we have the receipt

`cameron_exit_result.md` §4.1 swept the profit target across **the same 485 trades**, changing
nothing else:

| Target | **Win rate** | Net P&L | Drop-top-3 |
|---|---:|---:|---:|
| 2% | **39.8%** | −$155 | −$964 |
| 3% | 39.6% | −$122 | −$932 |
| 5% | 36.1% | +$96 | −$713 |
| 7.5% | 34.0% | +$180 | −$630 |
| 10% | 34.0% | +$422 | −$610 |
| 15% | 34.0% | **+$428** | −$607 |
| none | 34.0% | +$161 | −$923 |

**Win rate falls monotonically as the target widens. P&L rises monotonically.**
A 2% target buys **+5.8 percentage points of win rate for −$316**.

The doc's own conclusion:

> *"So his win rate is not evidence of a better exit. It is a different point on the same
> trade-off curve — and the curve points the other way for us."*

**Caveat, and it is a real one.** This sweep is **in-sample on the 485-trade `bar_cache`**,
and `ladder_and_regime_20260911.md` has since overturned two other findings from that same
cache when re-run on 4,481 trades. **The monotone direction is the durable part; the dollar
levels are not.** Re-running this sweep on `bar_cache_xnas` is cheap and is listed as an open
item in §7.

---

## 4. Every win-rate-raising mechanic tested here, and what it cost

| Mechanic | Effect on win rate | Effect on money |
|---|---|---|
| Tighter profit target (2%) | **+5.8 pts** | **−$316** |
| Cameron's breakeven stop | **−11.3 pts** | **−$4,271** (→ −$27,260 on 4,481 trades) |
| Fixed cent stops 10/15/20c | **−2.6 to −10.2 pts** | −$411 to −$2,171, **monotone** |
| Max hold cap 3–30 bars | −0.9 to −4.3 pts | −$585 to −$2,084, **boundary check fails** |
| Take-profit ladder | +0.1 pt | +$272 → **−$1,612** on 4,481 trades |
| Confirm-N trailing stop | not reported | +$8,300 but **rejected** — 91% in one quartile |
| MC5 apex/gradient-reversal exit **removed** | **+4.5 pts** | **+$3,177** |

**Only the last one raised win rate and made money — and it did so by deleting a losing exit
(the removed mechanic was −$12.23 × 138 fires), not by targeting win rate.** Every mechanic
adopted *in order to* raise win rate lost money.

Sources: `cameron_exit_result.md`, `cent_stop_decision.md`, `hold_cap_decision.md`,
`apex_and_ladder_20260911.md`, `ladder_and_regime_20260911.md`, `mcl_rejected_mechanics.md`.

---

## 5. The inversion, laid out

Ranking every variant by expectancy after friction, and reading its win rate off:

| Variant | Per trade | **Win rate** | Status |
|---|---:|---:|---|
| MC5, apex OFF, `bar_cache` | **+$8.90** | 34.9% | in-sample; −$8.93 on screened universe |
| MCL V12 | +$4.22 | 42.7% | stale, pre-fill-correction |
| H0 "buy the screen at 04:30, no entry rule" | +$4.72 | not reported | fails both-halves **and** leak test |
| MCL shipped, `bar_cache` | +$0.33 | 34.0% | fails drop-top-3 (−$923) |
| **Ben, real** | **−$69/trade** | **48.7%** | the highest win rate in the project |
| MCL, screened universe (4,481 trades) | −$5.22 | 26.2% | the honest out-of-sample figure |
| MC5, screened universe | −$8.93 | 21.7% | closed candidate |

**There is no variant in this project where a high win rate and positive expectancy coincide.**
The best-expectancy variant has a 34.9% win rate. The highest-win-rate book is the biggest loser.

---

## 6. Why win rate is not in the standards

`PROGRAM_INDEX.md` §4 lists eighteen acceptance checks — register before you run, friction
always and stated, drop-top-N on level **and** delta, paired-by-symbol bootstrap, temporal
holdout, leak cut both halves, boundary check, coverage, control the tool, and the rest.

**Win rate is not one of them, and is never used to accept anything.** It appears only as a
descriptive column. That was not an oversight; §4 exists because net P&L alone killed V8, V9,
every `TRAIL_PCT` candidate, VW9, the scale-out, the pyramid, the scale-up, confirm-N, MC5 and
all three pre-registered hypotheses of 2026-09-08. Win rate is a weaker signal than net P&L,
not a stronger one.

**Reporting rule, going forward:** any doc stating a win rate must state average win, average
loss and R alongside it, or state explicitly that they were not computed. Ten of this
project's results docs currently report a win rate with no paired reward figure
(`cameron_exit_result`, `ladder_and_regime`, `apex_and_ladder`, `prior_spike_result`,
`hold_cap_decision`, `cent_stop_decision`, `mcl_apex_macd_sweep`, `mcl_robustness_analysis`,
`screened_universe_results`, `warrior_census`). In each of those, R is not recoverable from
the doc.

---

## 7. What to chase instead

Ranked by measured evidence, not by appeal.

**1. The daily loss stop — the best-evidenced item in the project.**
`execution_gap_20260910.md` §3, run as a counterfactual on Ben's *real* 1,658 round trips:

| Daily stop | Recovered |
|---|---:|
| **−$2,000** | **+$55,083** — 48% of the total loss |
| −$5,000 | +$30,926 |

It needs no signal, no entry rule and no backtest. It attacks average loss (route B in §2)
at the day level, which is where the census says the damage is done. **It remains untested as
a live rule.**

**2. Whatever kills the 1-bar trades.**
`hold_cap_decision.md` §4: 1-bar trades are **107 of 485, −$3,924, −$36.68 per trade**. Drop
them and MCL goes +$161 → **+$4,086 (+$10.81/trade)**. Independently reproduced in
`consolidation_filter_test.md` §4: 0–5 minute holds are 316 of 479 trades at −$6.12, negative
in both halves. **22.1% of trades destroy 96% of the gross result.**

The caveat the docs put on this themselves is real: the worst bucket of any partition is low
by construction, and hold time is unknowable at entry. But a rule that predicts *at entry*
which trades die in one bar is worth more than any exit change on this list, and it is a pure
average-loss lever.

**3. The census's sizing and gating items, not entry items.**
`warrior_census_20260910.md`: `ignored_own_filter` **10.7×**, `broke_ice_boredom` **8.0×**,
`oversized` **6.4×**, `traded_low_quality` **4.3×** — versus `back_side` 1.1× and `slippage`
1.0×. Its own conclusion:

> *"Every high-lift item is a position-sizing or gating decision. Not one is an entry rule.
> The entry is not where his money is won or lost, and by extension it is probably not where
> ours is either."*

**4. Re-run the §3 target sweep on `bar_cache_xnas`.** Cheap, and it converts the most
decision-relevant table in this document from in-sample to out-of-sample.

---

## 8. What this document does not say

- **It does not say a high win rate is bad.** Cameron has both. It says a high win rate is
  not evidence of anything on its own, and that every route we have tested to *buy* one has
  cost more than it returned.
- **It does not say MCL is close to working.** MCL's −0.8 point margin is on the fitted
  `bar_cache`. On the screened universe it is **−$5.22/trade over 4,481 trades at a 26.2% win
  rate**, and `PROGRAM_INDEX`'s banner — *"no strategy in this project has a positive edge
  after measured costs"* — has not been reversed by anything measured since.
- **It does not resolve the friction question**, which materially affects every dollar figure
  quoted above. See `friction_reconciliation_20260911.md`.
