# The entry is the problem, and it is not visible from this tape — 2026-09-14

`python -m common.entry_split --strategy mcl` (21.6s, 32 workers) · raw:
`var/reports/entry_split_mcl.txt` · bundles `20260914m`–`p`

## 0. What it was asked

`entry_excursion_result_20260914.md` split MCL's 3,955 point-in-time trades into
two businesses — dips-then-runs at **+$19.13** with $44.00 available in 30 bars,
pops-then-fades at **−$22.76** with $15.30 — and showed the difference is a
property of the situation entered. The catch was that the label is defined
AFTER entry, so it is hindsight, not a rule.

This asked whether anything observable **at the entry bar** says which one a
trade will be. 22 features, 11 families, `entry_features`' own bucketing
imported rather than copied.

## 1. The bar, derived before the run

A filter has to lift the dip-then-run rate far enough that the book makes money,
and that comes out of the two group means:

    p × 19.13 = (1 − p) × 22.76   →   p = 54.3%

Against a base rate of **29.2%** — a lift of **1.86x**. Both recomputed from the
run's own trades, not pasted from the doc that motivated it.

## 2. Three features separate, and the money does not follow

`CLEARS 0`. `SEPARATES 2 of 11 families` — momentum level and trend — against
`entry_features`' **0 of 11** on trade P/L. The label change did make the target
more learnable, as predicted.

| | rate, low → high bucket | lift | P/L per bucket |
|---|---:|---:|---|
| `macd_margin` | 37.2% → 22.4% | 1.56x | **(8.31)** (8.99) (13.26) (11.51) |
| `ma20_dist` | 38.1% → 21.8% | 1.46x | (10.85) (10.41) (11.89) **(8.93)** |
| `ma20_slope` | 36.3% → 23.6% | 1.37x | (9.95) (11.16) (11.82) **(9.13)** |

Three more — `rsi_slope`, `vol_over_trail`, `floor_margin` — are monotone in
both halves in the same direction, below the lift bar. Six related features
saying one thing: **the less extended the entry, the more often it dips then
runs.** MCL buys momentum that has already gone.

**But on two of the three, the bucket with the FEWEST dip-then-run trades has
the BEST P/L.** The rate and the money run opposite ways. That is what the label
can do and the money cannot: it says which KIND of trade, never how large, so a
bucket can hold more of the good kind and still lose more.

## 3. The number that ends it

**88 buckets across 22 features. Not one is profitable.**

The best is `macd_margin`'s lowest quartile at **(8.31)/trade** against
(10.52) over all 3,955. Every quarter of every column loses money. A filter
selects a subset, and no subset this feature set can name is a subset that makes
money.

An earlier arithmetic estimate of (6.80) for a `ma20_dist` filter was wrong: it
assumed the two group means hold inside a filtered subset. They do not — that is
precisely what §2 shows.

## 4. What this closes

**The entry is the problem — and it is not identifiable from minute OHLCV.**
Both halves of that, measured:

| question | answer | source |
|---|---|---|
| Can a better exit rescue the losing 70.7%? | No — $15.30 available, 3.6x friction | `entry_excursion` |
| Can any entry feature filter them out? | No — 88 buckets, none profitable | this run |
| Can trade P/L be predicted at entry? | No — 0 of 11 families | `entry_features` |
| Can a run be predicted from the tape? | No — 0.108% base, 1.94x best | `run_signal` |

MCL on this universe, with this data, does not work, and no tuning inside it
will. That is a decision-grade negative rather than a discouraging one: four
independent measurements agreeing is worth more than any of them alone.

## 5. The one lever the numbers still point at

Not in this run, but visible in the excursion data underneath it:

    dips then runs   median MAE   $8.00
    pops then fades  median MAE  $21.00

The winners' drawdown is a quarter of the losers'. MCL's 5% trail on a $4 name
is about **$20 on 100 shares**, and early in a trade the peak is the entry — so
the effective initial stop sits almost exactly at the losers' median MAE. The
losers are running the full width of the stop before dying; the winners never
need most of it.

Arithmetic, holding the winners intact: cutting the losing group at (8) instead
of (22.76) takes the book to about **breakeven**; at (5), to **+$2/trade**. That
is a larger lever than filtering, and it uses post-entry information, which is
available in real time and is not hindsight.

**The tension to resolve first.** `mcl_rejected_mechanics.md` records cent stops
at 10/15/20c **rejected, monotone** — on a $4 name that is $10–20 per 100
shares, the exact range this points at. That test ran on the 485-trade cache and
the leaky universe, and three findings from that cache have since inverted. The
medians here and that rejection disagree; the disagreement is the thing to
measure.

**Before running anything:** the medians are not enough. If the winners' MAE has
a long tail, a stop between $8 and $21 kills more winners than the median
suggests. The distribution — p25/p50/p75/p90 of MAE per group — decides whether
a stop separates the populations at all, and it is already computed per row.

## 6. Defects found on the way

1. **The report measured a proxy and let the reader infer the money.** The rate
   alone was printed; the P/L row was added and immediately showed two of the
   three separators running backwards. The inference this whole thread exists
   because I made, about to be invited from a table.
2. **The verdict text was phrased as if the tiers were about money.** A tier is
   a statement about SHAPE. A separator whose money disagrees is flagged now,
   and the report states the best bucket in the table outright.
3. **KeyError('macd') on the first real session.** `features_at` reads indicator
   columns and was handed raw OHLCV. All 19 tests passed — every one fed the
   renderer dictionaries and none ran the pipeline.
4. **Every fixture named its feature column `"f"`.** None of the 22 real names
   existed on those rows, so `render` refused all of them as NOT BUCKETABLE and
   every assertion about the report passed without a single bucket being built.

Three of the four are the same shape: the suite exercised the renderer and never
the path into it.

2,210 tests passing.

## 7. Next

1. **MAE distribution per group**, not just the median. Decides whether a stop
   separates the two populations. Already computed; needs reporting.
2. If it separates: a stop sweep on the honest universe through `pit_delta`,
   registered against the 10/15/20c rejection it contradicts.
3. If it does not: the last lever inside this data is gone, and the question is
   which data sees it — float, short interest, halt state, news, order-book
   depth. None are in this tape.
