> **ARCHIVED 2026-09-08.** Superseded by `mcl_rejected_mechanics.md`, which carries the verdict.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the conclusion is unaffected.** The P/L numbers below
> predate the 2026-09-05 fill-model correction (gap-through fills, peak-seeding)
> and are overstated because of it.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check** — measured on a fuller tape
> the backtests turn out slightly *conservative* on slippage, by about $1 per
> 100-share round trip. See `execution_cost_measured.md`.
>
> Neither correction rescues what was rejected here. The fill-model fix pushes
> costs **up**, and the slippage correction is worth roughly the same $1 to
> every variant compared, so it moves no comparison. Do not reopen these on the
> grounds that the numbers were stale — re-derive them if you must, and expect
> the same answer.

# Pyramiding on a recovered pullback — decision, 2026-09-05

Ben's follow-up after the scale-out exit was rejected: *if we're not selling,
should we buy MORE at the pullback — the low before it bounces back?*

A genuinely different mechanic. Nothing is sold early, so none of the
sell-low / buy-back-higher cost that sank the scale-out applies. Tested on its
own terms.

**Verdict: it does not beat simply starting at the size it builds to. Delta
−$268, 95% CI [−$2,142, +$1,502], P(better) = 39.6%, negative after dropping
the best 1/3/5 symbols, sign flips across the holdout. Not shipped; inert by
default.**

Code: `strategy/mcl/mcl.py` (`pyramid_qty`, `pyramid_pullback_pct`,
`max_adds`, `entry_shares`). Tools: `common/pyramid_study.py`,
`common/pyramid_verdict.py`. Tests: `tests/strategy/mcl/test_pyramid.py`.
Output: `var/reports/pyramid_study.txt`, `pyramid_verdict.txt`.

---

## 1. The rule as implemented

A dip of `pyramid_pullback_pct` below the running peak **arms** the position.
Reclaiming *that same peak* buys `pyramid_qty` more shares, at a 40 bps
marketable-limit chase. Nothing is ever sold; only the 5% trail exits. `max_adds`
caps how many times it can happen, `max_position_shares` caps the size.

## 2. The control is the whole study

On a dataset whose average trade is positive, **any** extra size looks better.
Verified directly — flat size is a pure multiplier here:

| flat size | net (after friction) | per trade | **return per $ deployed** |
|---|---:|---:|---:|
| 100 shares | +$1,567 | $3.16 | **0.483%** |
| 150 shares | +$2,350 | $4.74 | **0.483%** |
| 200 shares | +$3,134 | $6.32 | **0.483%** |
| 300 shares | +$4,701 | $9.48 | **0.483%** |

Identical to three decimals. So a pyramid that builds 100 → 200 must be judged
against **a flat 200 from the entry**, never against the 100-share baseline.
`entry_shares` was added to make that control exact.

## 3. What the pyramid does

Best configurations, all entering at 100:

| add on a dip of | add size | max adds | net | drop5 | return per $ | peak position |
|---|---|---|---:|---:|---:|---|
| −1% | +100 | 1 | +$2,887 | +$72 | 0.667% | 200 sh / $3,932 |
| −2% | +100 | 1 | +$2,866 | +$81 | **0.685%** | 200 sh / $3,932 |
| −2% | +200 | 1 | +$4,166 | +$228 | 0.813% | 300 sh / $5,898 ✗ |
| −2.5% | +100 | 1 | +$2,356 | −$374 | 0.583% | 200 sh / $3,822 |
| −3% | +100 | 1 | +$1,972 | −$726 | 0.502% | 200 sh / $3,822 |
| −2% | +100 | unlimited | +$2,252 | −$892 | 0.459% | 600 sh / $8,340 ✗ |

Two clean patterns, both worth knowing:

- **Shallower dips are better.** −1% and −2% beat −2.5%, −3%, −4% on every
  measure. The deeper the dip you wait for, the worse the add — you are buying
  a stock that has already broken down.
- **One add beats many.** `max_adds=1` beats 2 which beats unlimited, every
  time. Unlimited also runs the position to 600–2,100 shares, far past the
  account.

## 4. Judged properly, it fails

The leading configuration (100 + one 100-share add on a recovered −2% dip)
against a flat 200, **both peaking at 200 shares**:

| | flat 200 | pyramid |
|---|---:|---:|
| trades | 496 | 496 |
| net after friction | **+$3,134** | +$2,866 |
| drop-top-5 after friction | −$608 | **+$81** |
| return per $ deployed | 0.483% | **0.685%** |

| the delta (pyramid − flat) | |
|---|---:|
| total | **−$268** |
| 95% CI, paired bootstrap by symbol, 10,000 resamples | [−$2,142, +$1,502] |
| P(pyramid better) | **39.6%** |
| after dropping the best 1 / 3 / 5 symbols | −$518 / −$804 / −$1,036 |
| early half / late half | +$133 / −$400 (**sign flips**) |

The higher return per dollar is real but it is not an edge: the pyramid only
reaches 200 shares on the subset of trades that pulled back and recovered, so
it deploys less capital and the ratio flatters it. Given the same money to
risk, flat 200 made more.

**The one thing that did survive** is concentration: drop-top-5 is +$81 for the
pyramid against −$608 for flat 200. Waiting for a recovered dip before adding
does put the extra size on better trades. But the delta test says that
difference is not distinguishable from noise on this sample, so it is a lead,
not a result.

## 5. The finding that matters more than the pyramid

Setting up this study exposed a definitional inconsistency: `common/scale_grid.py`
computes drop-top-N **before** measured slippage; `pyramid_study.py` computes it
**after**. On the shipped config the difference is not cosmetic:

| shipped MCL — 496 trades, 174 symbols | before friction | **after friction** |
|---|---:|---:|
| net | +$3,680 | **+$1,567** |
| per trade | $7.42 | **$3.16** |
| drop top 1 | +$3,095 | +$999 |
| drop top 3 | +$2,328 | +$277 |
| **drop top 5** | **+$1,706** | **−$304** |
| profitable symbols | — | **70 / 174** |

**Every published concentration figure in this project is the pre-friction
one.** After charging the measured live friction, removing the five best names
makes the shipped strategy a loser, and fewer than half its symbols are
profitable.

That is not a reason to stop trading it — the friction estimate rests on **two
live sessions**, it swung from −$2.93 to +$4.26 between them, and the shipped
config's exit mix barely appears in either. But it does mean the honest
statement of MCL's current evidence is "profitable on a hindsight-selected
universe, carried by a handful of names, with a friction estimate too thin to
resolve the question" — and it moves *re-measure friction every live session*
from first priority to the only priority. Nothing else in the queue can be
decided until that number is real.

## 6. What would change the verdict

- **More live friction data.** Same answer as everything else right now. If
  friction lands materially below $4.26/round trip, both the pyramid and the
  shipped config look better, and the drop5 sign may flip back.
- **The concentration lead.** If adding only on recovered dips really does put
  size on better trades, it should show up as a *cleaner* result on more data,
  not a bigger one. Worth re-checking once the universe is forward-selected
  rather than hindsight-selected, since selection bias is exactly what
  concentration measures.
- Not sub-minute data. Unlike the tight-trail idea, this mechanic works at
  1-minute resolution — a −2% dip on a $5 stock is 10c, well outside the
  spread. The bar model is adequate here; the sample is what is thin.

---

## Caveats

- Same 373-session hindsight-selected universe, IB split-adjusted prices.
- Friction charged at $0.0213/share transacted (the measured 2026-09-03 buy/sell
  average, **n=2 sessions**), plus real IBKR Tiered commission per order and a
  40 bps chase on every add.
- At 100 shares MCL sits *exactly* on the Tiered per-order minimum
  (100 × $0.0035 = $0.35), so it gets no volume discount and pays no minimum
  penalty. Adds of 100 shares are priced the same way. Smaller orders are not,
  which is one reason the scale-out mechanic was expensive.
- Anything peaking above ~200 shares cannot be funded: $4,131.89 net liq, and
  these are pre-market small caps with no margin.
