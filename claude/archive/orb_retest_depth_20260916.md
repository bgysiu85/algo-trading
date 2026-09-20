# ORB retest depth — a fourth cell, and the Reddit source that prompted it

**Written 2026-09-16, in the research chat. No program logic was touched.**
Built on `orb_preflight_RESULT_20260916.md`, which ran earlier the same day.

> **The one-line finding.** The preflight already counted the range-anchored
> zone retest, and it answers the question the source could not: **a 38–62%
> retest follows only 27.0% of upside triggers at 15 minutes.** The source says
> *"sometimes it never comes"*. It is 73% of the time.

---

## 1. The source

A Reddit post on `r/Daytrading` (*"Been trading this ORB + Fib strategy for 3
years"*), plus an annotated chart, given to the research chat on 2026-09-16.

**Claim:** opening range break → wait for a Fibonacci retracement of the move →
enter at 50% or 61.8% → confirm with MACD → target a new high of day.
**Stated result:** *"a consistent 10-15k a month."* Anonymous, three years, **no
account size, no sample, no dates, no drawdown.** Hypothesis generator, not
evidence — the standing rule.

**Its core idea is not new to us.** `orb_strategy_spec.md` §5.3 already carries
it as `RETEST_MODE = zone`, from source V4 (Raghee Horner): *"the retest must
reach into the 38–62% retracement of the range."* Two unrelated sources
arriving at the same fork is mild corroboration and nothing more.

---

## 2. What IS new — the anchor, and it is a different object

| | anchor at 0% | anchor at 100% |
|---|---|---|
| **`zone` (V4, already specified)** | `orb_high` | `orb_low` |
| **the chart's version** | a **post-breakout swing high** | the breakout extreme |

The chart's fib runs from the ORB low up to the high made by the *first
reversal candle after the break* — it measures **the retracement of the impulse,
not of the range**. Different anchors, different levels, different trades.

**Proposal: add `RETEST_MODE = zone_impulse` as a fourth cell**, and count it in
§10.3 alongside the three already counted. It is one more column in a pass that
is already running.

Why it may matter rather than merely differ: the range-anchored zone is fixed at
09:45 and cannot move, so a violent trigger leaves the retest zone far below the
entry. The impulse-anchored zone travels with the move, so its depth is
proportional to the thrust that produced it. On a universe where 15-minute
ranges run a **9.46% median width** (preflight, 15 min), those two are not
close to each other.

---

## 3. The preflight already prices the fork — and this is the useful part

From `orb_preflight_RESULT_20260916.md` §10.6, arithmetic ours:

| `ORB_MINUTES` | usable | up-triggers | **zone retest** | **zone as % of triggers** |
|---:|---:|---:|---:|---:|
| 5 | 19,260 | 12,998 | 5,037 | **38.8%** |
| **15** | 15,886 | 9,684 | 2,618 | **27.0%** |
| 30 | 14,089 | 7,971 | 1,715 | **21.5%** |

**So the retest fork's cost is now a number, not a caveat.** Requiring a
38–62% retest at 15 minutes discards **73% of triggers**. The source's own
admission — *"sometimes it never comes, and you just miss the trade entirely"* —
is the majority case, and the deeper the entry the worse it gets. The source
never quantifies this; we now can, and did so before running the strategy.

Standing requirement carried from §5.3: **a retest rule can only remove trades,
never add them.** So the comparison is per-trade P/L plus **drop-top-N on the
delta**, never total P/L.

---

## 4. Why the depth question is the same question as §10.5's warning

The preflight raised a problem and the retest fork is the lever on it.

> §10.5: *"6,001 triggers touched the structure stop at a median of 4 bars,
> 5,787 reached 2R at a median of 6."* With §7.2's stop-wins-on-the-same-bar,
> **`EXIT_MODE = r_2` starts at a disadvantage.**

A deeper entry moves the entry price toward the stop and away from the target,
which raises R per trade and changes that race directly. **The retest-depth fork
and the stop-beats-target problem are one problem seen twice**, and they should
be read together rather than in separate tables.

This also means the three-way coupling the preflight found — `ORB_MINUTES` ×
`STOP_MODE` — is really **four-way**: length × stop × retest mode × exit mode.
The preflight's own conclusion applies unchanged: *"picking a length first and a
stop second would fix the wrong confound."* Add retest depth to the same joint
grid rather than sweeping it afterwards.

---

## 5. What in the source must NOT be carried over

**The text and the chart describe two incompatible trades.** Levels read off the
chart: 0% = 5.66 (marked INITIAL TP), 38.2% = 5.29, 50% = 5.18, 61.8% = 5.06,
78.6% = 4.90.

| configuration | entry | stop | risk | reward | **R:R** |
|---|---:|---:|---:|---:|---:|
| chart's entry + **text's** stop ("below 78.6%") | 5.29 | 4.90 | 0.39 | 0.37 | **0.95** |
| chart's entry + **chart's** stop (arrow ≈ 5.18) | 5.29 | 5.18 | 0.11 | 0.37 | **3.4** |
| text's entry (61.8%) + text's stop | 5.06 | 4.90 | 0.16 | 0.60 | **3.75** |

**A 3.9× spread in R across three readings of one setup**, and the post claims
*"insane risk-to-reward"* while specifying the combination that returns **less
than 1:1**. Three further defects:

1. **The text says enter at 50% or 61.8%; the chart marks entry at 38.2%** —
   which its own legend calls "GOOD" against 61.8%'s "BEST". The demonstrated
   trade is the weakest of its three levels; the best one is asserted, never
   shown.
2. **The stop has a third reading** — *"below the 78.6% **or** the recent swing
   low"*. Not the same price.
3. **The levels do not reconcile to their own anchors.** 5.66 − 4.62 = 1.04
   gives 50% = 5.14 and 61.8% = 5.02; the chart prints 5.18 and 5.06, which are
   consistent with a 100% anchor near **4.70**, not the labelled 4.62. Harmless
   on a picture, fatal in code — the annotation set and the level set came from
   different anchors.

**The MACD confirmation layer is already closed.** `entry_split_result_20260914.md`:
22 features, 11 families, **0 clear** against a needed 1.86× lift, and
`macd_margin` was the **best of them at 1.56×**. It is already the nearest miss
and it still misses. `orb_strategy_spec.md` is deliberate on this —
*"Indicators: **None.** The range, and price."* Do not let this source reopen it.
Note also the source hedges it into unfalsifiability: *"bullish divergence **or**
starting to curl back up from its midline"*, with no MACD pane on the chart.

**The chart is not this instrument.** Its time axis runs continuously
16:30 → 18:00 → *(next day)* → 06:00 → 09:00. US equities do not trade 18:00
through 06:00 even with extended hours. This is a 24-hour tape — futures or
crypto — where the "opening range" is a convention someone chose rather than an
actual open releasing overnight information at once. That is the spec's §1.1
item 4 again, and this source is the ninth instance of it.

**On Fibonacci specifically.** 23.6 / 38.2 / 50 / 61.8 / 78.6 is five levels
across one range, so *something* is almost always "at a fib level" — multiple
comparisons dressed as analysis. **The retracement-depth idea survives this;
the ratios do not.** Treat depth as a swept parameter with the ratios as three
arbitrary points in it, never as constants. Same family as the harmonic
"Bat pattern" material noted in `source_videos_20260907.md` §11.

---

## 6. What to do

1. **Add `zone_impulse` to `RETEST_MODE`** and count it in §10.3 next to the
   three already counted. Cheap; the bars are loaded.
2. **Run retest depth inside the joint grid**, not after it — §4 above.
3. **Carry the 27.0% forward as the fork's price.** Any cell requiring a deep
   retest is spending three quarters of its triggers to buy a better entry, and
   the per-trade figure has to clear that.
4. **Nothing else from this source.** Not the fib ratios as constants, not the
   MACD gate, not the R:R claim, not the stop rule.

Nothing here changes `orb_strategy_spec.md` §11. The go/no-go is unchanged and
unmet, and the holdout is unspent.
