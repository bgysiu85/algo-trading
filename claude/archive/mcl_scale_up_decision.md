> **ARCHIVED 2026-09-08 — superseded by `mcl_rejected_mechanics.md`.**
> The verdict here stands and the workings below are the evidence for it. Read
> the consolidated doc first; come here for the grid, the bucket table and the
> execution note. **Do not quote figures from this file as current** — they
> predate the 2026-09-05 fill-model correction, as the original banner says.

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

# Sell into strength, buy back on the dip — decision, 2026-09-05

**Read `mcl_scale_out_decision.md` first.** This is its mirror image and the
second half of the same question; that document has the shared context, the
cost model, and the two implementation bugs found along the way.

Ben asked to revisit this one last time, and re-reading his original
description showed something Part I never tested. His words were "when there is
pull back on the stock, he sells a portion... then once it increases back to
its previous candle high, he buys again", and his own example sells at $5.85
and buys back "at $5.85 or $6". That is **sell low, buy high** — and Part I
measured it faithfully.

But scaling is usually described the other way round: sell a portion **into
strength** on the way up, buy it back **on the pullback**. Same two orders,
opposite sign. Part I says nothing about it.

**Verdict: it also loses. 0 of 90 cells at the shipped 5% trail beat doing
nothing, and the best cell is the one that acts least.**

Code: `strategy/mcl/mcl.py` (`scale_up_pct`, `scale_up_portion`,
`rebuy_dip_pct`, `rebuy_ref`). Tool: `common/scale_up_grid.py`.
Tests: `tests/strategy/mcl/test_scale_up.py`. Output:
`var/reports/scale_up_grid.csv`.

## 1. The grid, 450 cells

Compared always against the *same* trail with the mechanic off — implemented
as a sell level 1e9% above the last fill, so it is the identical code path
rather than a second one that could drift.

| trail | baseline | best cell | delta | best cell is |
|---|---:|---:|---:|---|
| 3% | +$1,567 | +$1,491 | −$76 | sell 25% at +12%, buy −3% |
| **5%** | **+$1,567** | **+$1,425** | **−$142** | sell 25% at +12%, buy −3% |
| 8% | +$3,644 | +$3,200 | −$444 | sell 25% at +12%, buy −5% |
| 10% | +$4,680 | +$4,020 | −$660 | sell 25% at +12%, buy −5% |
| 15% | +$6,873 | +$5,302 | −$1,572 | sell 25% at +12%, buy −5% |

Unlike Part I there is no trail at which it turns positive. And every axis is
monotone in the *act less* direction:

| sell trigger (trail 5%, portion 25%, dip 3%) | net | rebuys |
|---|---:|---:|
| +1% | −$89 | 228 |
| +2% | +$379 | 164 |
| +3% | +$600 | 128 |
| +5% | +$1,011 | 89 |
| +8% | +$1,333 | 44 |
| +12% | +$1,425 | 20 |

| portion sold (trail 5%, +2%, −2% dip) | net |
|---|---:|
| 25% | +$355 |
| 50% | −$668 |
| 75% | −$1,692 |

The optimum of the whole surface is "off". That is the cleanest form a
rejection can take.

## 2. Why — measured in two stages, because the first answer was wrong

**Stage 1.** The obvious explanation is that selling high and buying low must
at least bank a credit on each cycle. It does not. With the dip measured from
the peak reached *after* the sell (`rebuy_ref="peak"`), a stock that keeps
running is bought back **above** where it was sold:

| configuration | bought back below its own sell price | median gap | banked by the round trips |
|---|---:|---:|---:|
| sell 50% at +2%, buy −2% from peak | **45%** | −0.33% | **−$922** |
| sell 50% at +5%, buy −3% from peak | 61% | +0.64% | −$56 |
| sell 25% at +12%, buy −3% from peak | 70% | +1.32% | +$17 |

Note the symmetry with Part I's bug: **both directions of the mechanic buy back
higher than they sold**, for different reasons. Part I because "reclaim the
level" is above the sell by construction; here because a dip from a *higher*
peak is still above the sell.

**Stage 2.** So `rebuy_ref="sell"` was added — a limit resting a fixed % below
the **sell price**, which makes each round trip profitable *by construction*.
It works exactly as intended and still loses:

| best cell: sell 25% at +8%, rebuy 3% below the sell | |
|---|---:|
| bought back below the sell price | **100%** |
| banked by the round trips alone | **+$112** |
| net | +$1,273 vs baseline +$1,567 |
| delta | **−$294** |
| 95% CI (paired bootstrap by symbol, 10,000 resamples) | [−$632, −$17] |
| P(delta > 0) | **1.6%** |
| delta after dropping best 1 / 3 / 5 symbols | −$326 / −$365 / −$388 |

Every one of the 60 cells tested in this mode is negative.

**Where the loss lands says the rest.** Symbols bucketed by their baseline P/L:

| bucket | n | baseline | with the mechanic | delta |
|---|---:|---:|---:|---:|
| top 10 winners | 10 | +$2,867 | +$2,741 | **−$127** |
| next 40 | 40 | +$2,542 | +$2,487 | −$55 |
| the rest | 124 | −$3,842 | −$3,803 | **+$39** |

It buys a little protection on the losers and pays for it on the runners. The
round trips are genuinely profitable — and irrelevant, because +$112 of banked
credit cannot cover being short of size on the ten names that carry the year.

## 3. The finding that unifies all of this

Three mechanics have now been measured on MCL, and they fail for what looks
like three different reasons but is one:

| mechanic | what it does to size | result |
|---|---|---|
| scale-out (Part I) | reduces on weakness, restores on strength | −$682 to −$1,625 |
| pyramid (`mcl_pyramid_decision.md`) | adds on a recovered dip | −$268 vs flat 200 |
| scale-up (Part II) | reduces on strength, restores on weakness | −$142 to −$294 |

**In a strategy whose P/L is carried by a handful of big movers, anything that
reduces exposure to a runner costs more than any amount of round-tripping
earns — and anything that adds size does no better than simply starting with
that size.** Flat size was the only thing that ever scaled P/L, and it scales
it exactly: 100/150/200/300 shares all return 0.483% per dollar deployed, to
three decimals.

That closes the intraday position-management question. What is left is not a
better mechanic; it is the two things underneath — how much size the account
can carry (the sizing study), and whether the fills are real (friction, n=2).

## 4. Execution note, in the mechanic's favour and still not enough

Worth recording because it was the one structural advantage this version had.
Part I's buy-back is a break *above* a level, so it is a marketable limit
paying a ~40 bps chase. Here **both legs rest** — a limit sell above the market,
a limit buy below it — so nothing is chased and the grid charges no cross at
all. The cost moves from spread to **queue position**: a resting limit at a
level price merely touches need not fill, and pre-market books are thin. A bar
model cannot see that, and this one does not model it.

So the numbers above are, if anything, **generous** to the mechanic. It loses
anyway.
