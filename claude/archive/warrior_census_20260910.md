# The Warrior census — 401 videos, every recap since 1 Jul 2025

**Built 2026-09-10.** Every video on `@DaytradeWarrior` in the 90-second-to-40-minute
band from 2026-09-10 back to roughly 2025-07-01 — **401 of 401, all read in full**,
each reduced to one structured row. Zero malformed rows across 34 independent
workers.

This replaces the 35-video sample that `execution_gap_20260910.md` was built on.
**It corrects one of that document's conclusions — see §3.**

Dataset: `census.csv`, 401 rows, schema in §7.

---

## 0. Why this exists

The earlier pass read 35 videos chosen by title. Titles are chosen for clicks, so
a title-selected sample over-represents drama — max-loss days, record days — and
under-represents the ordinary Tuesday. That is exactly the wrong bias for
measuring what a method does on average.

**This is a census, not a sample.** Every video in the band, in order, whatever
its title. The composition is: **317 recaps**, 55 watchlists, 18 trainings, 6
news, 4 other, 1 interview.

**Standing caveat, unchanged:** these are his self-reported figures, narrated on
camera, on a channel that sells a course. They are not an audited record. What
the census fixes is *selection* bias, not *source* bias.

---

## 1. The day-level ledger, and it is the whole story

| | **Cameron, 317 recaps** | **Ben, 134 trading days** |
|---|---:|---:|
| green days | **86.5%** | **29.1%** |
| mean green day | $23,832 | $1,270 |
| mean red day | −$16,844 | −$1,732 |
| red ÷ green magnitude | **0.71** | **1.36** |
| **day expectancy** | **+$18,343** | **−$858** |
| no-trade days | 28 (8.8% of recaps) | 0 |

Both legs are inverted, exactly as the per-trade ledger was:

- **He wins most days; Ben loses most days.**
- **His losses are smaller than his wins; Ben's are larger.**

Either one alone would be survivable. Together they are the entire difference.
His expectancy is carried by the 86.5%, not by the size of his winners — at a 0.71
ratio he would still need a 58% green rate just to break even, and he clears it by
28 points.

**Stated total across 282 days that quote a figure: +$4,738,892**, or $16,805 a
day — which reconciles with the 86.5%/0.71 expectancy of $18,343 to within the
gap between "days that state a figure" and "all days".

**28 no-trade days.** Ben has none. 22 of the 28 fall in cold markets.

---

## 2. Trades per day

| | median | mean | max |
|---|---:|---:|---:|
| **Cameron** | **2** | 2.7 | 12 |
| **Ben** | **10** | 12.4 | 46 |

Full distribution, 175 recaps that state a count:

```
0 trades  ████████████████████████████ 28
1 trade   ███████████████████████████████████ 35
2         ███████████████████████████████████ 35
3         ███████████████████████ 23
4         ████████████████████████ 24
5         ███████████ 11
6         ████ 4
7         ██████ 6
8         █████ 5
9-12      ████ 4
```

**56% of his traded days are one or two trades.** Ben's median day is 10.

---

## 3. THE CORRECTION — trade count is an output, not an input

`execution_gap_20260910.md` §2 read Cameron's "40% fewer trades, 3× the money" as
support for a per-day trade budget, and paired it with Ben's −0.570 correlation
between trades/day and daily P/L. **The census says that pairing was wrong.**

| his trades that day | n | green rate | mean stated P/L |
|---|---:|---:|---:|
| 1–2 | 70 | 85.7% | $1,392 |
| 3–4 | 47 | 83.0% | $6,838 |
| 5–6 | 15 | 80.0% | $15,020 |
| **7+** | 15 | **100.0%** | **$19,453** |

**His green rate is flat across the range and his P/L rises 14× with it.** More
trades is not worse for him — it is dramatically better.

The resolution is that the two men's trade counts are produced by different
things:

> **For Cameron, trade count is a symptom of opportunity.** He takes more trades
> on days the market offers more, and those are his best days. His 2025
> trade-count reduction removed *low-quality setups*, and he says so explicitly —
> and even then he wondered aloud whether he had cut too far.
>
> **For Ben, trade count is a symptom of tilt.** Measured: on days where his first
> three trades were net negative he went on to take a **median of 9 more**
> trades; after a positive start, **6**. Rank correlation between the first-three
> P/L and the number of further trades: **−0.199**.

**So a per-day trade cap is the wrong instrument.** It would have cut Ben's damage
only by accident, and applied to a working strategy it would cut the best days
hardest. What the data supports instead is a **state-dependent** rule — stop after
a defined drawdown, not after a defined count. That is the daily-loss stop already
in `execution_gap_20260910.md` §3, and this strengthens it at the expense of §2.

One further nuance from Ben's tape: trades taken while the day was already red
cost **−$69.52** each, and trades taken while green cost **−$68.88**. Essentially
identical. **His trades do not get worse when he is tilting — there are just more
of them.** The sequence effect is real and separate: his first five trades of a
day cost −$25 each, trades six onward −$95.

---

## 4. Regime, quantified from 234 labelled recaps

| his label | n | green rate | mean day | median trades | no-trade days |
|---|---:|---:|---:|---:|---:|
| **hot** | 53 | 94.3% | **$46,481** | 4 | 0 |
| mixed | 38 | 97.2% | $24,172 | 2 | 2 |
| **cold** | 143 | **76.9%** | **$2,835** | 2 | **22** |

**A cold market costs him 16× his average day.** Not his win rate — that only
falls from 94% to 77% — but the size of the win. He keeps showing up, halves his
trade count, and books a sixteenth of the money.

Two things follow for us:

- **The regime gate is worth more than any entry rule in this project.** Nothing
  else we have measured moves an outcome 16-fold.
- **Cold is the normal state.** 143 of 234 labelled recaps — 61% — are cold. A
  strategy validated on the hot 23% is not validated.

---

## 5. What actually causes his red days

Every mistake, by how much more often it appears on a red day than a green one.
This is the most useful table in the census because it is a **census**: the
denominators are all 317 recaps, not the ones with dramatic titles.

| mistake | red days | green days | **lift** |
|---|---:|---:|---:|
| **ignored_own_filter** | 38.5% | 3.6% | **10.7×** |
| **broke_ice_boredom** | 12.8% | 1.6% | **8.0×** |
| **oversized** | **46.2%** | 7.2% | **6.4×** |
| stop_widened | 7.7% | 1.6% | 4.8× |
| no_cushion | 7.7% | 1.6% | 4.8× |
| traded_low_quality | 30.8% | 7.2% | 4.3× |
| outside_window | 5.1% | 1.2% | 4.3× |
| reentry_after_stop | 28.2% | 9.2% | 3.1× |
| divided_attention | 12.8% | 5.2% | 2.5× |
| added_to_loser | 10.3% | 5.2% | 2.0× |
| chased_extended | 33.3% | 17.6% | 1.9× |
| didnt_bank_green | 43.6% | 28.8% | 1.5× |
| back_side | 2.6% | 2.4% | 1.1× |
| slippage | 10.3% | 10.0% | 1.0× |
| **no mistake named** | **5.1%** | **37.2%** | — |

**The single most common feature of a red day is oversizing — it appears on 46%
of them and 7% of green days.** The highest-lift is ignoring his own filter:
he identifies the disqualifier and takes the trade anyway, on 38.5% of red days
against 3.6% of green.

**Two things the title-selected sample got wrong**, and this is why the census was
worth doing:

- **`back_side` is not a red-day driver at all.** It looked like one of the top
  failure modes in the 7-video sample (4 of 7). Across 317 recaps its lift is
  **1.1×** — he trades the back side about as often on good days as bad.
- **`slippage` is not either** — lift 1.0×. It is a constant cost, not a cause.

And `didnt_bank_green`, the most-cited mistake overall, has a lift of only 1.5×.
**It is how a green day becomes a smaller green day, not how it becomes a red
one.** The things that turn a day red are size and filter discipline.

> **Every high-lift item is a position-sizing or gating decision. Not one is an
> entry rule.** The entry is not where his money is won or lost, and by extension
> it is probably not where ours is either.

---

## 6. Setups, ranked by frequency and by risk

| setup | mentions | red-day share | green-day share | **lift** |
|---|---:|---:|---:|---:|
| **micro_pullback** | **172** | 46.2% | 61.6% | **0.7** |
| **dip_buy** | **129** | 33.3% | 46.4% | **0.7** |
| half_whole_dollar | 94 | 41.0% | 31.2% | 1.3 |
| vwap_break | 58 | 15.4% | 20.8% | 0.7 |
| first_pullback | 41 | 12.8% | 14.4% | 0.9 |
| **flat_top** | 31 | 17.9% | 9.6% | **1.9** |
| **halt_resumption** | 26 | 17.9% | 7.6% | **2.4** |
| abcd | 12 | 7.7% | 3.6% | 2.1 |
| reversal | 7 | 5.1% | 2.0% | 2.6 |
| bull_flag | 7 | 0.0% | 2.8% | 0.0 |

**Three findings that change what should be built.**

**1. The micro pullback is both his most-used setup and his safest** — 172
mentions at a 0.7 lift. **MCL implements this one.** That is the strongest
endorsement of MCL's core in the whole exercise, and it is worth stating plainly
given how much of this analysis has been critical.

**2. Dip buying is his second strategy and we have entirely missed it.** 129
mentions — three quarters as often as the micro pullback — at the same 0.7 lift.
`warrior_1`–`warrior_4` barely cover it; MCL does not implement it at all. The
Humbled Trader work flagged dip-buy-versus-breakout as the open question and
concluded he "trades both". **The census says he does not merely trade both — dip
buying is half his book, and it is as safe as the breakout.**

**3. The risky setups are flat tops and halt resumptions**, at 1.9× and 2.4×.
`warrior_2_flat_top.md` treats the flat top as a straightforward variant of the
micro pullback. By his own record it is roughly three times as likely to appear
on a losing day.

---

## 7. Timing, and it is now conclusive

First trade of the day, stated on 87 recaps:

```
06:00  ███████ 7
07:00  ██████████████████████████████████████████████████ 50
08:00  █████████████████ 17
09:00  █████████████ 13
```

**57% of his stated first trades are in the 07:00 hour, and 8% are before it.**
Nothing at 04:00, 05:00 or after 10:00 in the entire census.

**MCL arms from 04:00 ET**, and its 04:00–06:00 block is −$2,166 against a
−$1,270 total. The census removes the last doubt about whether that window is
where he operates: it is not.

---

## 8. Schema

`census.csv`, one row per video, position-ordered newest first.

`pos` · `videoId` · `kind` (recap/watchlist/training/interview/promo/news/other) ·
`day_result` (green/red/flat/notrade) · `pnl_usd` · `account` (main/small/both) ·
`trades_n` · `symbols` · `setups` · `mistakes` · `market` (hot/mixed/cold) ·
`first_et` · `last_et` · `max_loss_hit` · `notable`

`setups` and `mistakes` use closed vocabularies so they aggregate; `?` means not
stated and is never a guess. Build method and worker spec: `CENSUS_SPEC.md`.

**Known limits.** Dates are position-ordered, not calendar-dated — the playlist
endpoint returns no date field, so the census can be ordered but not joined to
Ben's tape by date. Recovering real dates would need one metadata call per video
(401 calls, free) and is the obvious next step if a date-level join is wanted.
`trades_n` is stated on 175 of 317 recaps and `market` on 234, so those tables
have real denominators but not complete ones.

---

## 9. What this changes, in order

1. **Build the regime gate.** §4 — 16× on the mean day, and cold is 61% of the
   sample. Nothing else measured in this project moves an outcome that far.
2. **Implement dip buying.** §6 — half his book, same risk profile as the setup we
   already built, and absent from our code.
3. **Replace the per-day trade-count idea with a daily loss stop.** §3. The count
   rule was wrong and this document withdraws it.
4. **Re-read `warrior_2_flat_top.md` against a 1.9× lift** before building it.
5. **Keep MCL's micro pullback.** §6 — it is his most-used and safest setup, and
   we implemented the right one.
6. **Get real dates** if the day-level join to Ben's tape is wanted.
