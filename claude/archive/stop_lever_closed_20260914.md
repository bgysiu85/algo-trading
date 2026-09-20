# The stop lever is closed — 2026-09-14

`python -m common.entry_excursion --strategy mcl` · raw:
`var/reports/entry_excursion_mcl.txt` · bundles `20260914q`, `r`

Closes the item `entry_excursion_result_20260914.md` §5 left open as "the one
lever the numbers still point at".

## 1. The hypothesis, and why it looked good

The two populations draw down very differently:

| | p25 | p50 | p75 | p90 | p95 |
|---|---:|---:|---:|---:|---:|
| dips then runs (+$19.13) | $4.00 | **$8.00** | $14.99 | $24.00 | $32.36 |
| pops then fades (−$22.76) | $12.00 | **$21.00** | $39.00 | $69.00 | $99.00 |

Shifted 2.5–3x at every percentile. MCL's 5% trail on a $4 name is about $20 per
100 shares and early in a trade the peak *is* the entry, so the effective initial
stop sits almost exactly at the losers' median. The losers run the full width of
the stop before dying; the winners need a quarter of it.

## 2. The answer, with slippage charged

| stop | per share | winners cut | losers cut | ratio | book | vs now |
|---:|---:|---:|---:|---:|---:|---:|
| $5 | 0.0500 | 69.8% | 92.9% | 1.33 | (9.26) | **+1.22** |
| $8 | 0.0800 | 54.0% | 87.7% | 1.62 | (10.60) | (0.12) |
| $10 | 0.1000 | 42.0% | 81.7% | 1.95 | (11.17) | (0.70) |
| $12 | 0.1200 | 32.9% | 75.9% | 2.31 | (11.76) | (1.28) |
| $15 | 0.1500 | 24.4% | 64.7% | 2.65 | (12.76) | (2.28) |
| $20 | 0.2000 | 14.6% | 52.0% | 3.55 | (13.77) | (3.29) |
| $25 | 0.2500 | 9.3% | 42.3% | 4.52 | (14.45) | (3.97) |

**Monotone, and worse in the direction the hypothesis predicted would help.**
This reproduces `mcl_rejected_mechanics.md`'s cent-stop rejection — 10/15/20c
rejected, monotone — on the honest 3,955-trade point-in-time universe. The old
rejection stands and now has a mechanism: the winners' drawdown distribution
overlaps the losers' too heavily at every width that catches meaningful numbers
of losers.

## 3. The one positive row is the one to trust least

$5 shows +$1.22/trade. Three reasons it is not a finding, and the third is the
one that matters:

**It still loses $9.26 a trade.** Improving a loss is not an edge.

**It cuts 69.8% of the winners** — seven in ten profitable trades destroyed to
catch 92.9% of the losers. And $5 on 100 shares is 5 cents a share against a
measured 2.13 cents of stop slippage, so the stop is 2.3x the noise it is
supposed to sit outside of. The estimate charges average slippage; a stop that
fires into fast moves will do worse than average.

**THE ESTIMATE IS LEAST RELIABLE EXACTLY WHERE IT LOOKS BEST.** The `book`
column replaces every stopped trade with an assumed value — exits at its level,
survivors keep their group mean. At $25 only 9.3% of winners and 42.3% of losers
are cut, so most rows carry real outcomes. **At $5, 88% of the whole book is
stopped**, so nearly every row is the assumption rather than a measurement. The
row that shows improvement is the row built almost entirely out of the estimate's
own flattering assumptions.

A number whose reliability falls as its value rises is not evidence. It is the
shape of an artefact.

## 4. What is now closed

| lever | answer | evidence |
|---|---|---|
| Capture more with a better exit | no | $15.30 available on the losing 70.7%, 3.6x friction |
| Filter the bad entries out | no | 88 buckets across 22 features, none profitable |
| **Cut the losers cheaper with a stop** | **no** | **monotone; best row is 88% assumption** |
| Select a better universe | marginal | the screen adds 1.35x over generic selectivity |

**MCL on this universe, with minute OHLCV, does not work — and no tuning inside
it will.** Four independent measurements, four modules, each built to be able to
say the opposite.

It loses $10.52/trade point-in-time and about $6.26 gross of all friction.
Charge nothing for commissions or slippage and it still loses.

## 5. What is not closed

This closes the question **for this data**. Float, short interest, halt state,
news timing and order-book depth are absent from the tape and untested.
`data_scoping_20260914.md` has the first probe: float exists but moves 29x inside
the backtest window on a single name, so a current snapshot is not approximately
right — it is a different number — and any float feature has to be built from the
quarterly series or not at all.

Direction agreed with Ben: scope the other data first, then work forward from the
run census rather than backward from a rule that does not work.
