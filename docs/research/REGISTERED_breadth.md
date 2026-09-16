# REGISTERED — what replaces go/no-go criterion 2

`orb_strategy_spec.md` §11 criterion 2 and §11.1. Written and committed
**before `common/breadth.py` exists and before ORB produces any number**, per
§14 item 6. The commit hash is the timestamp.

The replacement is applied **identically to ORB and retroactively to MC5**, in
the same pass, so the two are judged by the same instrument.

---

## 1. The criterion being replaced

> **2. A majority of symbols with ≥1 trade are profitable.**

§11.1 already recorded the problem: the statistic is confounded with trades
per symbol. VW9's Setup B had 1.7 trades a symbol, where it approximates the
trade win rate; MC5 has 4.1.

**There is a second confound, and it is worse, because no better estimator of
the same quantity escapes it.** With right-skewed payoffs most symbols are
negative even at a genuinely positive expectancy. A strategy with a 27% trade
win rate and a long right tail *should* leave most symbols underwater — that is
what the payoff shape does, not evidence about breadth.

This kills the obvious repair. "Median across symbols of per-symbol mean net
≥ 0" looks like a sample-size-independent restatement and is **the same test**:
the median is non-negative exactly when at least half the symbols are
profitable. Swapping one for the other would have changed the wording and
nothing else.

So criterion 2 is not re-estimated. **It is replaced with a different
question.**

---

## 2. Retiring it is a measurement, not an assertion

The old criterion is only retired if it can be shown to carry no information
on this data. Two things are computed and printed before any replacement
verdict:

**2.1 Share profitable by trade-count bucket** — 1, 2, 3–5, 6–10, 11+ trades a
symbol, every bucket printed. If the share climbs with trade count, the
statistic is reading sample size.

**2.2 The shuffled control.** Trade nets are permuted across symbol labels with
each symbol's **trade count held fixed**, 2,000 times, and the share-profitable
recomputed. This is the distribution the statistic takes when there is *no*
symbol-specific effect at all — only skew and trade count.

> **If the observed share sits inside the middle 90% of the shuffled
> distribution, the old criterion carries no information about breadth on this
> sample, and its retirement is evidenced rather than argued.**

If the observed share sits **outside** that distribution, the old criterion was
measuring something real and this registration is wrong. In that case the
replacement below is adopted anyway *in addition*, and the old criterion is
kept rather than dropped. Recorded now so a surprising result cannot quietly
become a reason to drop it.

---

## 3. The replacement

> **2. The result survives resampling the symbols it was measured on.**
>
> A **symbol-cluster bootstrap** — symbols drawn with replacement, as many as
> the sample has, 2,000 resamples, the statistic recomputed over every trade
> belonging to each drawn symbol — must satisfy BOTH:
>
> **(a)** total net > 0 in at least **95%** of resamples; and
> **(b)** the **2.5th percentile of per-trade net ≥ $0**.

Symbols, not symbol-days and not trades: two sessions on the same ticker are
not independent draws — the same convention `trail_study.paired_bootstrap` and
`manual_vs_strategy._bootstrap` already use here, and this module calls the
existing construction rather than writing a third.

**Why this is the right question.** The intent behind criterion 2 was "the edge
is not an artefact of a few names". That is a question about whether the result
would survive a different draw of symbols, which is what a cluster bootstrap
asks directly. It is sample-size-aware in the correct direction — few symbols
gives a wide interval and fails — and it is unaffected by how many trades each
symbol happens to carry.

**(b) is not redundant with (a).** A large sample can put the total
comfortably above zero while per-trade net sits at a hundredth of a cent. The
per-trade floor is what keeps criterion 2 a statement about edge rather than
about trade count, and it is the half that interacts with criterion 3.

### 3.1 Thresholds, and why these numbers

- **95%** is the conventional one-sided level and it is the level this project
  has already used on permutation tests (`regime_study` reports p 0.0240 and
  0.2964 against it). Choosing a different one here would make ORB's bar
  incomparable with the results it is being judged against.
- **$0 at the 2.5th percentile**, not a positive figure, because criterion 3
  already sets the per-trade dollar bar at **$1.00**. Two overlapping dollar
  thresholds would make a failure ambiguous about which one it failed.

### 3.2 What this does NOT replace

**Criterion 1 (drop-top-3 and drop-top-5) stands unchanged.** Concentration
and resampling are different tests: drop-top-N asks what happens when the best
names are removed, the bootstrap asks what happens when the draw changes.
Neither implies the other and both are required.

---

## 4. Applied to MC5 in the same pass

§11.1 puts MC5 at +$1.11/trade over 7,403 trades and 1,791 symbols, 706
profitable (39.4%) — a failure under the old criterion. It is re-scored under
§3 with no other change, and the result is reported **whichever way it goes**.

**Registered consequence:** if MC5 passes the replacement having failed the
original, that is not evidence the replacement is lenient — it is the expected
consequence of removing a confound the original had. And if MC5 fails the
replacement too, the replacement is not softened. Either outcome is published.

---

## 5. What would make this run wrong

- **Resampling trades instead of symbols.** Trades within a symbol are
  correlated; resampling them independently understates the interval and the
  criterion passes things it should not.
- **Dropping symbols with one trade.** They are the thin part of the
  distribution the old criterion was mismeasuring. A floor would remove exactly
  the rows that motivated this change. All symbols are in; the trade-count
  buckets show what they contribute.
- **Shuffling without fixing trade counts.** The control's whole purpose is to
  hold trade count constant so that skew alone is what remains.
- **Judging MC5 and ORB by different seeds, resample counts or floors.** One
  call, one set of parameters, both strategies.
- **Reading (a) without (b).** A large enough sample makes (a) easy.

---

## 6. What this cannot settle

It does not say the edge is real out of sample — criterion 5's temporal
holdout is a separate question, and `var/state/holdout.json` is untouched by
any of this and remains unspent.

It says only that the measured result is not an artefact of which symbols
happened to be in the sample.
