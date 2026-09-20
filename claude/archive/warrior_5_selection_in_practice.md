# Warrior 5 — selection as he actually does it

Assumes `warrior_0_universe_and_risk.md`. This is the **executed** counterpart to
`warrior_3_gap_and_go.md`: not the published grading rubric, but what he picks
and — more usefully — **what he rejects and why**, watched live on seven
watchlist and recap videos.

Read in full 2026-09-10: `76gAPVfe-Uo`, `wB6ObQt__uI`, `yHrlQ5_Sc6c`,
`l7Z5aqS4zpk`, `50iICFBL5kA`, `coqONALABpo`, `x0qg5eGF7zc`.

**Why this document exists:** MCL's screen ranks on **top-2 pre-market gainer**,
computed once. He does something structurally different, and the difference is
cheap to test.

> **Correction 2026-09-11 — §8 item 4 only.** The prior-spike measurement that
> item cited as support has been **superseded and inverted** on a 9× larger
> sample. Everything else in this document is source extraction and is
> unaffected. Details at §8.

---

## 1. The rule this whole document is here for — hold 50%

`50iICFBL5kA` 16:29, and it is the most directly codeable thing extracted from
this channel:

> "**once a stock is holding up at 60% or 100% on the day, once it's holding
> that level, it's not doing that immediate round trip.** Then I'm like, okay,
> it's holding up here, let's watch this for the bull flag and the move higher…
> **the holding at least 50% of that initial gain is what I'm paying attention
> to.** And so when we have stocks that pop up and then go all the way back
> down, yeah, pretty much immediately I'm like, '**Nope, that's not going to
> work. I forget about that one.**'"

**Computable from minute bars with no new field:** for each candidate, measure
the first pre-market impulse, then test whether price is still holding ≥50% of
it at decision time. Reject if not.

> **MCL has no equivalent.** It ranks candidates by gap size and never asks
> whether the gap is *holding*. The regime work (`execution_gap_20260910.md` §5)
> independently identified round-trip rate as the best cold-market tell — this
> is the same measurement applied per-name instead of market-wide, which means
> **one computation serves both the screen and the regime gate.**

---

## 2. He ranks, then re-ranks. MCL ranks once.

Two mechanisms, both stated plainly.

**The "obvious" test** (`yHrlQ5_Sc6c` 12:40) — his actual ranking criterion:

> "you got to kind of look at the scan and ask **which of these right now is the
> best-looking stock that most other traders are going to look at and think,
> yeah, this is the one I want to trade.** Cuz that's the one that's going to be
> the cleanest. That's the one that's going to have the most volume, and that's
> where you'll have the liquidity to get in and out of it relatively easily."

**Musical chairs — the ranking rotates through the morning** (`yHrlQ5_Sc6c` 1:17):

> "the leading gainer, let's say 4:00 a.m., makes a really big move. And then…
> it's 7:00 a.m. here and it's on a pullback, then sometimes **that number one
> leading gainer, the one in the top spot, well, it's not really set up very
> well.** Maybe for a curl, but there's a **number two or maybe a number three
> leading gainer that has just come out with breaking news** and is really
> squeezing. And that's where people are going to focus… this one moves from
> position three up to two and then eventually could displace the leading gainer."

He applies it live in `coqONALABpo` 3:08: "when NAMI rolled over I felt that
attention was shifting… attention would likely shift to the **second leading
gapper**."

> **This is a direct conflict with MCL's screen.** Top-2-by-gap computed once
> selects the 04:00 leader; he explicitly says the 04:00 leader is often the
> *wrong* name by 07:00, because it has already made its move. Combined with §1,
> the rule he uses is closer to **"the top name that is still holding its gain
> at decision time"** than to "the top name."

---

## 3. What he rejects, and it is mostly the daily chart

Twenty-two rejections across seven videos. Grouped by reason, with the number
that failed.

| Reason | Instances | Examples |
|---|---|---|
| **Float too high** | 5 | YDDL 18M · ZJYL 20M · SKYE 22M · MDXH 32M |
| **Daily chart untrustworthy — ran before and gave it back** | 4 | NCRA "popped up and reversed" · FIEE "popped up and came all the way back down" · AAN closed −7% |
| **In the shadow of an older high (back side)** | 3 | YJ "in the shadow of this high of 14" · XHLD · UPC |
| **Volume or gap too small** | 3 | SGLY "relatively light volume" · VIVK "only up about 13%" |
| **Price wrong** | 3 | HUDI "a bit too cheap" at $0.75 · MB "up a little bit too high" · NVDA at $200 |
| **Already double-topped** | 1 | MB 4→20→6 |
| **Halt risk on light volume** | 1 | YJ "back-to-back halts… you can get caught in a halt going the wrong way" |
| **Wrong theme / domicile for the current cycle** | 2 | TRUG "doesn't fit the theme" · a whole list dropped because "none of these are Chinese" |

**The float numbers matter and they are tighter than the spec.**
`warrior_0` §1 records his stated main-account cutoff as **<20M**. In practice he
rejects at **18M**, and calls 22M "a little on the higher side". **His working
float ceiling in live selection is closer to 10M than 20M.**

**Two flags that downgrade but never disqualify:** *no news* and *Chinese
domicile*. He put AEHL on the watchlist with no catalyst — "for lack of anything
else to trade" — and explicitly refuses to filter on country
(`yHrlQ5_Sc6c` 6:25): "if we just said, 'Oh, get rid of all the Chinese.' Well,
**you get rid of a lot of the winners**, and you'd get rid of this one loser."

---

## 4. Yield — how many he looks at versus keeps

| Video | Named candidates reviewed | Kept |
|---|---:|---:|
| `76gAPVfe-Uo` | 4 | **2** |
| `wB6ObQt__uI` | 4 | **3** (ranked 1/2/3) |
| `yHrlQ5_Sc6c` | 7 | **4** |
| `l7Z5aqS4zpk` | 9 | **1**, and lukewarm |
| `50iICFBL5kA` | 4 | **2** |
| `coqONALABpo` (recap) | 4 live | traded 2 |
| `x0qg5eGF7zc` (recap) | — | **1** — "there was only one obvious stock" |

He ranks "the top three or four leading gainers" (`76gAPVfe-Uo` 15:35), not the
top two. **Reject rate is roughly half**, and on a bad day it is eight in nine.

> `warrior_0` §1 records that he sets the scanner *wider* than his own criteria
> and rejects by hand. This is what that looks like: the screen is a funnel, the
> rejection is the work, and most of the rejecting is done on the **daily chart**
> — which MCL's screen never looks at.

---

## 5. Price band — his own metrics disagree with the published band

`50iICFBL5kA` 9:52:

> "**My sweet spot is really between this kind of 5 and $10 range**… between 2
> and 5 and between 5 and 10. Even between 10 and 15 or 10 and 20, **I really
> didn't do as well**."

> **This lands on top of a measurement already made here.** `cent_stop_decision.md`
> §3 found MCL makes all of its money **above $7** and loses below it: −$665 in
> $2–4, −$253 in $4–7, +$540 and +$539 in the two upper bands. He says $5–10; our
> tape says $7–20. **The two disagree about the top of the range and agree that
> the bottom of the band is the problem.** Neither is out of sample.
>
> **Caution added 2026-09-11:** that `cent_stop_decision.md` §3 figure is a
> 485-trade `bar_cache` result, and three separate findings from that same cache
> have since inverted on the screened universe (§8 item 4). Treat the price-band
> agreement as suggestive, not as a measurement, until it is re-run.

Sub-$1 has its own rule (`yHrlQ5_Sc6c` 7:13): "they've got to be **below a
dollar, then they squeeze, and when they hold above a dollar, pay attention**" —
which is §1's hold rule again, with $1.00 as the level.

---

## 6. Levels, and how he actually picks them

In frequency order across the seven videos:

1. **Prior-day or after-hours high** — the most-used single level.
2. **Daily gaps and windows, chained upward.** ISPC: "around **2.96**… then
   another little window from **3.38**… room up towards **4.49**… then towards
   **five**." UPC: "resistance at **eight**, then a window up to **10.51**… then
   another window up to **17.96**, and then the 200 moving average."
3. **200 MA / 200 EMA — both target and wall.** He rejected SKYE because the
   200MA sat at $1.00 against a $0.63 price, and lost on DSY buying into a 200
   EMA at 7.60 he had already identified.
4. **Round numbers** — consistent with `warrior_2_flat_top.md` §3.
5. **Prior high-volume shelves.** SLE: "we really need to get over **7.37** to
   clear the high volume of these two 40–50 million share days."
6. **Measured move.** ZJYL: "the size of this move is about that big, so then
   the next leg up is sort of similar, so maybe **6.50-ish**."

**The dilution check is part of accepting a name, not optional.** He opens
filings on three of the accepted names and reads cash, quarterly burn and
runway. AEHL was downgraded on it: "with $1.9 million of cash, they didn't have
enough money to operate really even another 6 months." **We carry nothing like
this and it is not obtainable from price data.**

---

## 7. His own counter-example, and it should temper all of the above

`50iICFBL5kA` 15:33:

> "MSS, which has a **very low float, has lots of room to the 200, didn't work
> very well**. It's kind of a little bit hard to understand why some of them end
> up making such big moves and others struggle."

**That is the clearest admission in the whole source set that his numeric filters
do not discriminate on their own.** He passes a name on every stated pillar and
it fails. Any backtest of these rules should expect that, and should not treat a
low hit rate on the filters as an implementation error.

---

## 8. What to test, in order

1. **The hold-50% rule** (§1). Computable today from `bar_cache`, applies to
   both the screen and the regime gate, and MCL has no equivalent. **Highest
   value item in this document.**
2. **Re-rank at decision time instead of once** (§2). MCL takes top-2 by gap; he
   says the 04:00 leader is usually spent by 07:00. This is one change to the
   screen's ordering and it is testable on the existing screened universe.
3. **Tighten the float ceiling toward 10M** (§3) — but note `warrior_0` §1's
   standing warning that no float threshold from this source is a fitted
   parameter, and that `PROGRAM_INDEX.md` §7 item 11 records point-in-time float
   as absent anyway.
4. **A daily-chart trust filter.** ~~Already measured — `prior_spike_result.md`
   found any-prior-spike separates MCL's trades at +$4.67 against −$3.22 per
   trade, positive after drop-top-3 and same-signed in both halves.~~

   > **CORRECTED 2026-09-11 — that figure is superseded and it pointed the wrong
   > way.** `prior_spike_result.md` §6 re-ran it on the **screened universe,
   > 4,481 trades** — 9× the 485 it was found on — and **the separation
   > inverts**: any-spike **−$5.77** against no-spike **−$5.38** per trade. The
   > book overall is −$23,394 at a 26.2% win rate. That doc's own conclusion is
   > *"No subset rule rescues a strategy that loses on every subset."*

   §3 above is still the same idea arriving from the rejection side, and that
   remains interesting — **but it is now one route to this filter, not two.**
   The measured route has been closed. If a daily-chart trust filter is built it
   must be **registered as a fresh hypothesis** on `bar_cache_xnas`, not
   presented as the confirmation of an existing result.

   > **The general lesson, and the reason this correction is worth making at
   > all:** this is the **third** finding from the 485-trade `bar_cache` to
   > invert on the screened universe, after the take-profit ladder
   > (+$272 → **−$1,612**) and Cameron's partial (+$261 → **−$1,435**). All
   > three looked clean in-sample; all three were, in `ladder_and_regime`'s
   > phrase, *"373 sessions of noise agreeing with a wish."*
   > **No `bar_cache`-only result should be cited as support for anything until
   > it has been re-run on the screened universe.** That includes §5's price-band
   > figure above.
5. **Nothing on domicile or dilution.** He tracks both; we can compute neither,
   and he refuses to filter on the first anyway.
