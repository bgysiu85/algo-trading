# What separates MCL's winners from its losers: almost nothing survives

`python -m common.entry_features` · raw: `var/reports/entry_features_entries.txt`
482 entries, 13 features, 104 comparisons. Bundle `20260912ag`.

## Base rate

**+$0.37/trade, 34.0% win** at $4.26. That is what any feature has to beat.

## Three features cleared the pre-registered bar — and that is FEWER than chance

The bar was: same direction in both halves, effect larger than $4.26 in both.

| feature | early | late | |
|---|---:|---:|---|
| `macd_level` | 9.85 | 14.62 | top quartile better |
| `mfi_slope` | (8.66) | (15.55) | top quartile **worse** |
| `mins_since_open` | (11.37) | (6.90) | later is worse |

Direction agrees between halves by chance roughly half the time. With 13
features that is ~6.5 expected agreements before any effect exists, and a
sizeable fraction of those will exceed $4.26 on 43–77-trade buckets where the
standard error is tens of dollars. **Three passes out of thirteen is what noise
looks like.** Nothing here is established.

## Reading the three, sceptically

**`macd_level` — weak.** The top bucket is positive in both halves (3.27,
17.45) but the middle is incoherent: early runs (6.58) / 7.40 / (10.11) / 3.27,
late runs 2.84 / (6.65) / (8.10) / 17.45. A feature where only the extremes
differ and the middle is noise is what top-minus-bottom does to random data.

**`mfi_slope` — the bucket level disagrees.** Top-minus-bottom agrees, but the
bottom bucket is +13.83 (49% win) late and (2.17) (35%) early. The agreement
lives entirely in the difference, not in the buckets.

**`mins_since_open` — the only coherent one, and it has a confound.** Bucket 1
is the best and positive in BOTH halves (+9.31 at 44%; +6.56 at 32%), and later
buckets are worse in both.

**But MCL flattens at 09:30.** A trade entered at 09:20 has ten minutes before
a forced exit, so it cannot develop. The last bucket runs to 328 minutes after
04:00 — i.e. 09:28. So "late entries lose" may be entirely an artefact of the
forced flatten rather than anything about late entries.

That is checkable and cheap: compare exit reason and bars-held across the
buckets. If late entries are dominated by `session_end` exits, the finding is
mechanical and there is nothing to act on.

## One finding counted twice

`rsi_slope` and `mfi_slope` are both "how fast the indicator is rising", and in
the late half both have a strong first bucket (+14.55 at 49%; +13.83 at 49%).
That is ONE pattern appearing in two correlated columns, not two findings. Any
count of "how many features separated" that treats them as independent is
inflated — which is exactly why the report ranks nothing.

## The shape of the hypothesis, if one exists

Across several features the late half suggests **gentle momentum beats explosive
momentum**: low `rsi_slope`, low `mfi_slope`, early in the session. It is
coherent as a story, it is visible in one half only, and a coherent story is the
most dangerous thing this report can produce. It is not evidence.

## What this does NOT support

- **No condition should be added.** Not one feature cleared the bar in a way
  that survives the multiplicity.
- **The TNON question is not answered by this.** Nothing here distinguishes the
  07:35 bar from the 04:04 and 08:31 bars that also fired and lost.
- **`holdout.json` is untouched** and must stay so until a specific hypothesis
  is registered.

## The one next step worth taking

Rule out the forced-flatten confound on `mins_since_open`. If late entries lose
because the window closes on them, that is a fact about the exit, not the entry
— and it points at the session window rather than at any entry condition.

If the confound is ruled out and the time effect survives, THAT is the
hypothesis worth registering and spending the holdout on. Nothing else here is.
