> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it: MCL's headline went +$1,567 → +$161 and MC5's +$20,156 →
> −$400, on identical trades. Only the price they were booked at changed.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# MCL robustness analysis — 2026-09-05

Five offline tests run after `USE_APEX_EXIT = False` was shipped, to answer
the question the apex/MACD sweep could not: **is that result trustworthy, and
what is the next-largest lever?**

Source: `common/analysis.py --test all`, output at
`var/reports/analysis_20260905.txt`. Runs entirely off the cached bars
(`bar_cache/3d_to_2000/`, sliced to the engine's 2-session / 09:30 window), so
it costs nothing to re-run.

**Coverage: 373 cached sessions, 275 symbols.** 2 sessions skipped — superset
too short to give 2 sessions of warm-up.

> **Discrepancy to resolve.** `claude/mcl_apex_macd_sweep.md` reports the same
> cache as **376 sessions, 178 symbols**. Sessions differ by 3 (skip logic);
> symbols differ by 97, which is too large to be incidental. Most likely the
> sweep counted symbols that produced at least one trade and this counts
> symbols present in the cache — but that is a guess and it should be checked
> before either figure is quoted externally.

---

## Headline

1. **The apex removal survives a temporal holdout.** It improves in both
   halves of the sample. It is not a fitted regime.
2. **`TRAIL_PCT = 5%` is the worst setting in the sweep** on both net P/L and
   concentration. This is now the largest open decision in MCL.
3. Concurrency is a non-issue at cap 2.
4. Friction confirms the 2026-09-03 diagnosis exactly.
5. The entry-timing ceiling is large but shows **no winner/loser asymmetry**,
   which weakens the case that better fills amplify the tail.

---

## 1. Temporal holdout — apex removal is not fitted

90 distinct dates, 2025-09-02 to 2026-09-04, split at 2026-03-20.

| Half | Sessions | Variant | Trades | Net | $/trade | Win | drop5 |
|---|---:|---|---:|---:|---:|---:|---:|
| EARLY | 185 | V7 (apex ON) | 200 | +$777.79 | +$3.89 | 40.5% | **−$377.20** |
| EARLY | 185 | apex OFF | 177 | +$1,185.34 | +$6.70 | 42.9% | **−$60.77** |
| LATE | 188 | V7 (apex ON) | 361 | +$1,385.96 | +$3.84 | 36.0% | **−$166.13** |
| LATE | 188 | apex OFF | 319 | +$2,680.19 | +$8.40 | 44.8% | **+$872.95** |

| Half | Improvement | Per trade |
|---|---:|---:|
| EARLY | **+$407.55** | +$2.81 |
| LATE | **+$1,294.23** | +$4.56 |

**The test passes.** The improvement appears in both halves at a similar
per-trade magnitude. Winning in only one half would have meant a regime was
fitted rather than a rule found; that did not happen.

**But read the drop5 column, not just the improvement.** Three of the four
cells are negative once their five best names are removed. Only the late half
with apex off is comfortably robust (+$872.95). The early half improves from
−$377 to −$61 — better, still negative.

So: the *direction* of the apex effect is confirmed across time. The
*absolute profitability* of the strategy is only demonstrably concentration-
robust in the recent half. That is a weaker claim than the headline
+$1,883 drop5 on the full sample suggests, and it is the honest reading.

---

## 2. Concurrency — non-issue at cap 2

Unconstrained: 496 trades, +$3,865.53. **74 trades (14.9%) entered while
another position was already open.** First-come-first-served, matching live
trader behaviour.

| Cap | Taken | Skipped | Net | % of total |
|---:|---:|---:|---:|---:|
| 1 | 431 | 65 | +$3,055.10 | 79.0% |
| 2 | 490 | 6 | +$3,826.00 | **99.0%** |
| 3 | 495 | 1 | +$3,879.69 | 100.4% |
| 6 | 496 | 0 | +$3,865.53 | 100.0% |

Cap 2 costs 1% of P/L and removes the possibility of being in six correlated
small caps at once. Cap 3 is very slightly *better* than unconstrained,
which is noise (one skipped trade happened to be a loser), not a reason to
prefer it.

**Recommendation: set the cap to 2.** Cheap, and the backtest number stays
reachable in live.

---

## 3. TRAIL_PCT — the finding

| trail % | Trades | Net | $/trade | Win % | Med hold | drop5 |
|---:|---:|---:|---:|---:|---:|---:|
| 2.0 | 556 | +$4,157.25 | +$7.48 | 45.5 | 1 | +$3,053.19 |
| 3.0 | 533 | +$4,036.87 | +$7.57 | 46.2 | 1 | +$2,841.46 |
| 4.0 | 517 | +$3,930.51 | +$7.60 | 45.8 | 2 | +$2,061.43 |
| **5.0** | **496** | **+$3,865.53** | **+$7.79** | 44.2 | 2 | **+$1,883.03** ← current |
| 6.0 | 479 | +$3,822.84 | +$7.98 | 40.9 | 3 | +$1,899.51 |
| 8.0 | 449 | +$5,724.37 | +$12.75 | 40.1 | 5 | +$2,757.04 |
| 10.0 | 426 | +$6,654.09 | +$15.62 | 42.7 | 7 | +$3,737.74 |
| 15.0 | 382 | +$8,643.41 | +$22.63 | 43.2 | 14 | +$3,255.01 |

**5% is the lowest net figure and the lowest drop5 of every value tested.**
It sits at the bottom of a U: tighter is better, wider is much better, and the
current setting is the trough.

Going to 10% would nearly double net (+$6,654 vs +$3,866) and double drop5
(+$3,738 vs +$1,883), on 70 fewer trades — which also means less total
friction paid, compounding the gain.

### Why this is not shipped

The trail is a continuous parameter measured on a single dataset, and picking
its best value off one column is the exact shape a curve-fit takes. The apex
change had two things this does not yet have:

- **a mechanism** — apex exits were firing while the trail was still intact
  and were net −$544 at a 27% win rate;
- **a paired-by-symbol bootstrap** and a concentration check.

There is also a structural point that the raw table hides. Median hold moves
from 2 bars at 5% to 7 bars at 10% and 14 bars at 15%. That is not a tuning
tweak — it is a different strategy, holding through the pullbacks the 5% trail
exists to cut. It also interacts with apex removal: apex-off is what created
the long-hold tail in the first place, and a **tighter** trail would partly
undo that change while still scoring well here. Read the curve, not one cell.

### Required before any change

1. Temporal holdout, both halves, 5% vs the candidate.
2. Paired-by-symbol bootstrap of the delta, with a 95% CI.
3. Where the extra dollars come from — a handful of runners, or broadly?
4. Hold-time distribution and the operational consequences of it
   (see "Operational cost" below).

### Operational cost of a wider trail

The trailing stop is **software-managed inside the running process**. A longer
median hold means more wall-clock exposure to a crash leaving a position
unprotected. This was already flagged as the main risk of apex removal; a
wider trail multiplies it. Any move past ~8% should come with a restart-safe
stop, not just a better backtest number.

---

## 4. Friction — confirms the 2026-09-03 diagnosis

Measured live friction on 2026-09-03 was **~$4.26 per round trip** beyond the
one tick each way the engine already models.

**V7 (apex ON): 561 trades, +$2,163.75, +$3.86/trade. Break-even $3.86.**

| friction/trade | net | $/trade |
|---:|---:|---:|
| 0.00 | +$2,163.75 | +$3.86 |
| 1.00 | +$1,602.75 | +$2.86 |
| 2.00 | +$1,041.75 | +$1.86 |
| **4.26** | **−$226.11** | **−$0.40** ← measured |
| 6.00 | −$1,202.25 | −$2.14 |
| 8.00 | −$2,324.25 | −$4.14 |

**Shipped (apex OFF): 496 trades, +$3,865.53, +$7.79/trade. Break-even $7.79.**

| friction/trade | net | $/trade |
|---:|---:|---:|
| 0.00 | +$3,865.53 | +$7.79 |
| 1.00 | +$3,369.53 | +$6.79 |
| 2.00 | +$2,873.53 | +$5.79 |
| **4.26** | **+$1,752.57** | **+$3.53** ← measured |
| 6.00 | +$889.53 | +$1.79 |
| 8.00 | −$102.47 | −$0.21 |

**V7 as traded did not clear its own execution cost.** That is not a subtlety
— it is a −$226 expectation over the sample, and it is the whole explanation
for the 2026-09-03 session losing $163.60 while the backtest showed a profit.

Apex-off has real margin at the measured figure (+$3.53/trade) and breaks
even around $7.79, going negative only just past $8.00. That is a meaningful
buffer, but not a large one: a friction estimate that turns out to be
understated by 80% wipes the edge out.

**The $4.26 figure comes from one session.** It is the single most
load-bearing number in this analysis and it has a sample size of one day.
Re-measure it every live session and treat the friction table, not the
headline net, as the real scorecard.

---

## 5. Entry timing — large ceiling, weak mechanism

496 entries matched to their signal bar.

| Measure | Median | Mean | p75 | p90 |
|---|---:|---:|---:|---:|
| close − low ($) | $0.261 | $0.441 | $0.530 | $0.900 |
| as % of price | 4.85% | — | — | 14.69% |

**Perfect intrabar entry ceiling: +$44.08/trade** on 100 shares — buying the
exact low of every signal bar. Unachievable, but nothing about better entry
timing can be worth more than that, against a current edge of +$7.79.

So the ceiling is roughly 5.7× the current edge. That is large enough to
justify buying tick data on its own.

**But the asymmetry test comes back flat:**

| | n | mean gap |
|---|---:|---:|
| Winning trades | 219 | $0.456 |
| Losing trades | 277 | $0.429 |

Effectively identical. The original hypothesis — that bar-close entry is
destroying the big moves specifically — is **not supported**. Better fills
would shift the whole distribution up by roughly a constant, rescuing bad
trades about as much as amplifying good ones. That is still worth a lot in
absolute dollars, but it is a different argument from the one that motivated
the question, and it means intrabar entry is a *level* improvement rather
than a *tail* improvement.

Practical consequence: any partial capture of that gap is valuable, and there
is no reason to hold out for a sophisticated tick-triggered entry over a
simple one.

---

## Recommended order of work

1. **Trail decision** — holdout + paired bootstrap at 5% vs 8% vs 10%, plus
   the hold-time and restart-safety consequences. Largest open lever by a
   wide margin.
2. **Concurrency cap → 2.** Cheap, safe, keeps the backtest reachable.
3. **Re-measure friction every live session.** The whole analysis rests on
   $4.26 from one day.
4. **Leave `REQUIRE_MACD_POSITIVE = True` alone** until the trail is settled.
   Two simultaneous changes make the next live session unattributable — the
   same reasoning that held it back on 2026-09-05.
5. Entry timing stays open but drops in priority: the ceiling is real, the
   tail story is not.

---

## Caveats carried forward

- Same contemporaneous 407-pair set, still **IB split-adjusted** prices, still
  filtered to the `$2–20` band with the residual upward bias that filtering on
  adjusted price introduces. Unadjusted prices remain the open question.
- One session (AKAN 2026-09-04) is a hindsight pick added to test the cache
  pipeline. 1 of 373.
- Selection bias is inherited and unfixed: these are names chosen because they
  ran. Only forward testing on contemporaneous scanner picks fixes it.
- The holdout split at 2026-03-20 is a single cut. It was not swept, which is
  deliberate — sweeping the split point would reintroduce exactly the fitting
  the test exists to detect.
