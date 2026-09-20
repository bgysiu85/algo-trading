# The execution gap — Cameron's recaps vs MCL vs Ben's real trades

**Measured 2026-09-10.** Three ledgers put on the same axes for the first time:
what Ross Cameron actually does day to day (not what he teaches), what MCL does,
and what Ben's own 1,658 real round trips did.

**The headline: MCL is not an implementation of Cameron's method, and Ben's real
trading is its mirror image. All three are different strategies.**

Sources: 28 of Cameron's videos read in full 2026-09-10 (7 losing-day recaps,
7 discipline/metrics, 7 regime, 7 timing/green-day), plus
`var/reports/flex_round_trips.csv` (1,658 round trips, 134 trading days,
2025-06-04 → 2026-08-31) and `var/reports/screened/backtest_trades_mcl.csv`
(2,413 trades, 505 sessions).

Spec set: `warrior_0_universe_and_risk.md` and siblings. This document is about
**execution**, and it supersedes nothing in those.

---

## 0. Read this before using any number below

- **Cameron's figures are self-reported**, from analytics software shown on
  screen. Better than an unsupported claim, not an audited record. His channel
  carries a "results are not typical" disclaimer and he repeats it on camera.
- **The counterfactuals in §3 and §4 are naive.** Capping a loss or truncating a
  day changes what happens next — re-entries that would not have occurred, slots
  that would have freed. They bound the damage; they do not predict a P/L.
- **Ben's trades are in-sample in the strongest possible sense** — they are what
  happened. No selection or fitting problem, but also no forward claim.
- **`entry_et` is confirmed US Eastern.** Checked 2026-09-10: entry and exit
  hours occupy 04–12 and 16–19 only, with **zero** timestamps outside 04:00–20:00.
  That is exactly the US extended session in ET and is impossible under UTC
  (04:00 UTC is midnight ET, market shut). The §7 caveat this once carried is
  withdrawn. Incidentally it also shows Ben takes **no** entries between 12:00
  and 16:00 ET — he trades the pre-market and the morning, then after-hours.
- **Video publish dates from the channel API are bucketed relative strings**
  ("1 month ago") and mostly fabricated. Dates below come from content, not the
  API, except where an agent verified them.

---

## 1. The three ledgers

Per-share figures, so account size drops out.

| ledger | win % | avg win | avg loss | R | breakeven | **margin** |
|---|---:|---:|---:|---:|---:|---:|
| **Ben, real, 1,658 RT** | **48.7%** | 11.9c | −20.6c | 0.58 | 63.3% | **−14.6 pts** |
| Cameron 2024, 5,400 trades | 65.5% | 12c | −12c | 1.00 | 50.0% | **+15.5 pts** |
| Cameron 2025, 3,300 trades | **71.1%** | 18c | −15c | 1.20 | 45.5% | **+25.6 pts** |
| **MCL, 2,413 backtest** | **32.4%** | 41.8c | −20.8c | 2.01 | 33.2% | **−0.8 pts** |

Three things fall out of this table and each one matters more than any entry
rule in the spec set.

**1.1 MCL is not Cameron's strategy.** He wins five trades in seven with
roughly symmetric size; MCL wins one in three and needs 2:1 winners to survive.
Same universe, same pattern name, opposite distribution. The difference is the
exit: MCL's 5% trailing stop produces many small stop-outs and a few runners —
**2,212 of MCL's 2,413 exits are `trailing_stop` at −$1.2/trade, and the 201
that reach `window_close` make +$6.9.** The trail is the loss; surviving it is
the edge. Cameron does not trail. He takes half off at a target and moves the
rest to breakeven.

**1.2 MCL sits exactly on its own breakeven** — 32.4% against 33.2% needed. It
is not a broken strategy; it is a strategy with no margin, which is why every
cost assumption flips its sign.

**1.3 Ben's ratio is inverted and Cameron's is not.** Cameron devotes an entire
video to this exact failure (`550XNdh4y5k` 0:14):

> "what happens for a lot of beginner traders is that they don't cut their
> losers quickly … now you've got an **inverted profit to loss ratio, which
> means you need to be right greater than 50% just to break even. And now,
> without knowing it, you've set the bar higher and higher and higher.**"

Ben's bar is 63.3%. He clears 48.7%.

### The mechanical cause, and it is a single number

| | winner share size ÷ loser share size |
|---|---:|
| **Cameron 2025** | **1.36** (19,000 vs 14,000) |
| **Ben, real** | **0.80** (1,963 vs 2,467) |

Cameron explains his own ratio in one sentence (`Lin4WAwzPNY` 25:23):

> "I generally on my winners am scaling in. **I'm adding to my winner**, but on
> some of the losers I get in, I'm immediately red and **I never had a chance to
> add to the position.**"

**Ben does the opposite.** His losers carry **26% more shares** than his winners
and take **12.1 fills against 10.3**. He adds to losers. That single asymmetry is
why his dollar R (0.56) is worse than his per-share R (0.58), while Cameron's
dollar R (1.67) is far better than his per-share R (1.20).

> **This is the cleanest, most actionable difference between the two ledgers,
> and it is a position-construction rule, not an entry rule.**

---

## 2. Trade count — PARTLY WITHDRAWN 2026-09-10

> **⚠ SUPERSEDED BY `warrior_census_20260910.md` §3.** This section read his
> "40% fewer trades, 3× the money" as support for a per-day trade budget. A full
> census of 401 videos — every recap in the window, not the 35 selected by title —
> shows **his green rate is flat across trade counts and his P/L rises 14× with
> them**: 1–2 trades average $1,392, 7+ average $19,453.
>
> **His trade count is a symptom of opportunity. Ben's is a symptom of tilt** —
> measured, he takes a median of 9 further trades after a losing start against 6
> after a winning one. Ben's numbers below stand exactly as measured; the
> *inference* that a per-day cap is the right instrument does not. The right
> instrument is the daily loss stop in §3.

### The original section, kept because Ben's figures are unaffected

Cameron's headline claim (`Lin4WAwzPNY` 17:20):

> "**I actually took 40% fewer trades in 2025. In 2024, I had over 5,400 trades.
> And in 2025, I about 3,300 trades.** The change was because of a commitment to
> focus on quality over quantity."

Profit went from ~$2M to ~$6.5M. He is careful about attribution — accuracy only
moved 65.5% → 71.1%, and he says the tripling came from **share size**, which
the higher quality bar let him carry. He also says he may have cut too far:
"it does call into question if perhaps I pulled back on the total number of
trades a bit too much."

**Ben's own data reproduces the relationship, and more strongly than Cameron
states it.**

| Ben's days | days | net |
|---|---:|---:|
| **≤ 8 trades** | 57 | **+$27,581** |
| **> 8 trades** | 77 | **−$142,564** |

Spearman correlation between trades-per-day and that day's net: **−0.570.**

By activity quartile:

| trades/day | days | avg day | total |
|---|---:|---:|---:|
| 1–5 | 38 | −$21 | −$780 |
| **5–10** | 33 | **+$610** | **+$20,119** |
| 10–18 | 31 | −$953 | −$29,535 |
| **18–46** | 32 | **−$3,275** | **−$104,786** |

**The top activity quartile is 91% of the entire loss.** Median day is 10 trades;
maximum is 46.

Truncating each day to its first N trades:

| | trades | net |
|---|---:|---:|
| first 5 per day | 607 | −$15,024 |
| **trades 6 and beyond** | **1,051** | **−$99,959** |
| all | 1,658 | −$114,983 |

Trades 6+ cost **−$95 each**; the first five cost −$25 each. The gradient is not
monotone at small N (trades 4–5 were net positive, on 219 trades — noise), so the
finding is the **first-five versus the rest**, not any particular cutoff.

> **Nothing in this project has ever measured trade count as a variable.** MCL is
> capped at `MAX_CONCURRENT_POSITIONS = 2` and takes a median of 4 trades a day,
> which is inside the range that survives here — but it caps *concurrency*, not
> *count*, and has no per-day budget at all.

Cameron's cold-market rule, for contrast (`wSSOmCN1DZY` 7:25):

> "**if it has to be just one trade a day, I'm totally okay with that. One good
> trade a day is more than enough.** … get in, get out, get green, and don't go
> back."

---

## 3. The loss tail — there is no enforced maximum anywhere in Ben's trading

| | |
|---|---:|
| worst 5 trades | −$24,498 (21% of the loss) |
| worst 25 trades | −$67,016 (**58%**) |
| worst 50 trades | −$93,622 (**81%**) |
| 254 losers worse than −20c/share | **−$142,083 — more than the entire net loss** |

Worst single trade: **−492c/share.** Cameron's average loser is 15c.

**A daily stop is the single largest counterfactual in this document:**

| stop the day at | result | delta |
|---|---:|---:|
| −$2,000 | −$59,900 | **+$55,083** |
| −$5,000 | −$84,057 | +$30,926 |
| −$10,000 | −$104,101 | +$10,882 |
| −$20,000 | −$114,983 | $0 — no day ever reached it |

**A −$2,000 daily stop recovers 48% of the total loss.** Cameron reached the same
conclusion from his own August 2026 data (`Wd_iUsteoaw` 3:35):

> "**If I had stopped trading on both of those days when I was down only 15 or
> $20,000**, I would have an extra $100,000 of profit… None of these days where
> I'm green, I was down more than 20 grand before recovering to green."

His $20k is 2.5% of an ~$800k account. Scaled, not copied.

### The tension with `cent_stop_decision.md`, and it is not a contradiction

That study found a fixed 10–20c stop is **worse** than MCL's 5% trail at every
value tested. That stands. But it answered a different question.

> **MCL already has an enforced maximum loss — the trail is one.** The question
> that study asked was *which* cap. The question Ben's real ledger asks is
> whether there is a cap **at all**, and there was not. A −492c/share outcome
> cannot occur under either rule.

The two findings are complementary: **cap the loss; do not cap it in cents on a
$2–20 band.**

---

## 4. Time of day — real for MCL, not real for Ben

Cameron starts at **07:00 ET** and says so flatly (`BZwJFPk3cBM` 0:38):

> "my entire strategy shifted from beginning at 9:30 to **beginning at 7:00 a.m.,
> which is when I currently sit down and start trading**."

Across seven videos, **every timestamped trade is 07:00 or later.** Nothing in
04:00–07:00. He describes that window only as market structure, never as his own.
His reason is not session mechanics but where the news lands — 04:00–09:30 is
when small caps release, and there are no halt levels before the bell. He is
explicit that his start time is derived, not fixed: "if companies decide … they're
only going to put out news at 11:00 a.m., then you better believe I'm going to
start trading at 10:45."

His own metrics, from `Wd_iUsteoaw` 7:12:

> "**seven and eight is sort of building the cushion. Eight and nine is really
> stepping it up, and then 9 and 10 is cooling off, and then I'm losing money
> consistently after 10:00 a.m.**"

**MCL arms from 04:00 ET, and the hours before 07:00 are where it bleeds:**

| ET hour | trades | net | win % |
|---|---:|---:|---:|
| 04:00 | 288 | −$1,281 | 32.3% |
| 05:00 | 189 | −$885 | 27.5% |
| 06:00 | 287 | +$358 | 35.9% |
| **07:00** | 424 | **+$2,078** | 32.1% |
| 08:00 | 662 | −$1,094 | 33.7% |
| 09:00 | 451 | −$669 | 29.5% |

MCL's total is −$1,270. **The 04:00–06:00 block alone is −$2,166.** Removing it
would flip the sign. That is in-sample on data MCL was fitted to and is a
hypothesis needing registration, not a result — but it has an independent prior
from a practitioner who trades the same universe and refuses to trade that window.

**For Ben's real trades the same rule does NOT hold, and this is where I have to
correct an obvious-looking reading.** Before 07:00 he lost $42/trade; from 07:00
onward, $84/trade. His pre-07:00 hours are the *better* half per trade. The 06:00
hour looks outstanding at +$25,277 —

> **and it is one symbol.** PLYX alone is +$39,053. Drop the top symbol and
> 06:00 becomes **−$13,776**; the sign also flips between the two halves of the
> sample. It fails drop-top-1 and fails the temporal split.

**After drop-top-1, no hour of Ben's day is profitable.** There is no good window
to retreat into. The time-of-day finding belongs to MCL and not to him.

---

## 4b. MCL and Ben on the same symbol-days — the cleanest separation of strategy from execution

They overlap on **177 symbol-days** — 30% of Ben's 587, 12% of MCL's 1,457. On
that shared set, holding the names and the dates fixed:

| | trades | net | per share | win % | trades per shared symbol-day |
|---|---:|---:|---:|---:|---:|
| **Ben** | 598 | −$29,367 | **−4.8c** | 52.5% | **3.4** |
| **MCL** | 373 | −$620 | **−1.7c** | 33.2% | **2.1** |

**Both lose on the same names on the same days, and MCL loses about 3c per share
less.** Two things follow, and they pull in opposite directions:

- **Part of the loss is name selection, not execution.** These were bad
  symbol-days for anyone. A rule change alone would not have rescued them.
- **But MCL's rules do add something over the discretionary version** — roughly
  3c a share, and it takes 38% fewer swings at each name to get there.

**Day-level sign agreement is 57.6%** — 25 both green, 77 both red, 35 where Ben
was red and MCL green, 40 the reverse. Barely better than a coin flip.

> **On identical names and identical days the two ledgers disagree on direction
> nearly half the time.** Whatever MCL is doing, it is not a mechanised version
> of what Ben did. That is consistent with §1: the distributions were never the
> same shape.

---

## 5. Regime — and it does not explain Ben's losses

Cameron's regime model is unusually specific (`trcKOZnoPPs` 10:40):

> "**A quality setups produce 90% accuracy in a bull market. In a bear market, A
> quality setups produce 75%. B quality in a bull market, 80%; in a bear market,
> 65–70%. C quality in a bull market, 65–75% — in a bear market, you will be
> losing money.** … in a bearish market, **I can't trade B and C quality setups.
> I can only trade A quality setups.**"

In a cold market he cuts size ~5×, cuts trade count, drops to A-only, shortens
the target to ~20c, exits immediately if the trade does not move, and stops by
10:00. He does not stand aside for weeks: "I showed up every single day."

He dates the cycles, and September 2026 is cold by his account — the fortnight of
titles alone reads as a drawdown ("Max Loss Red Day", "Define a *Successful* Red
Day", and on 27 Aug "**Finally got a win in the main account**"). **MCL is being
paper traded inside that regime.**

**But regime does not explain Ben's ledger.** His worst month by a distance is
**June 2026, −$57,538** — and June 2026 is the month Cameron describes as
unambiguously hot: five stocks up over 1,000% with no news, a $120k pre-market
day, "this week has been pretty insane."

| month | days | trades/day | net |
|---|---:|---:|---:|
| 2026-02 | 13 | 8 | **+$29,740** |
| 2026-03 | 16 | 13 | −$31,991 |
| 2026-05 | 18 | 12 | −$16,324 |
| **2026-06** | 15 | **16** | **−$57,538** |
| 2026-07 | 20 | 9 | −$10,741 |
| 2026-08 | 20 | 17 | −$12,399 |

The only green month is the one with the **lowest trade count**. The worst month
is one of the highest, in the best conditions of the sample.

> **"The market was bad" is not available as an explanation.** Trade count tracks
> the outcome; the regime does not.

### Countable regime signals, for later

From the recaps, computable from daily bars: count of stocks up >100% on the day;
magnitude of the leading gainer (58% = cold, 300–500% = hot); **round-trip rate**
— fraction of top gappers giving the intraday move back; float of the leaders
(a 160M-float leader is a cold tell); share of movers under $1 versus $2–20.
He also notes the transition is asymmetric — "the shift from hot to cold is much
more subtle than the shift from cold back to hot" — which argues for a slow entry
into the cold state and a fast exit out of it.

---

## 6. What the recaps show him actually doing, versus what the spec set says

The spec set was built from his written pages and two long trainings. The recaps
show the executed version, and it differs.

| | Taught (Warrior 1) | Executed (recaps) |
|---|---|---|
| Entry | first candle to make a new high | often **anticipates** it; enters at a half/whole dollar or off level 2 |
| Position | one entry | **scales in on the way up**, adding at higher prices |
| Exit | half at target, breakeven stop on the rest | half at the round number, **rest on the topping tail** |
| Stop | `min(pullback low, 10–20c)` | frequently **discretionary**; a $3 hard stop named once |
| Trade count | not stated | **one or two a day**; five green days averaged ~1.6 trades |
| Hold | not stated | **minutes** — one $40k day was 8:05–8:15 |

A winning day is startlingly concentrated: +$19,323 from exactly two trades and
no losers; +$40,000 in a ten-minute window with ~55% from the first trade;
+$7,298 where one trade carried the day against three losers.

**The scale-in is the mechanic this project has already tested and rejected**
(`mcl_rejected_mechanics.md`, pyramid). Worth noting that his own largest losses
come from the same behaviour applied on the back side of a move — so his edge and
his catastrophes share a mechanism.

### His own failure modes, ranked across seven losing-day recaps

1. **Escalating size while already red** — 5 of 7. "You miss the beginning of the
   move, you take big size, increasingly bigger size as it gets higher, and then
   it drops. Then you trade the back side of the move."
2. **Re-entering after a stop, repeatedly, on the same symbol** — 5 of 7. Green
   $10k → red $15k on one name.
3. **Trading the back side of a move he already missed** — 4 of 7.
4. **Refusing or delaying the stop out of regret at earlier premature exits** —
   4 of 7. "I'm not going to stop out of this down here and then watch it rip
   right back up… And I went down with the ship."
5. **Breaking the ice after no-trade days, then spiralling** — 4 of 7.
6. **Not banking a green day** — 4 of 7. +$32k → −$64k in one session.
7. **Trading a setup that fails his own five pillars** — 3 of 7, and he names the
   disqualifier before entering every time.

> Note that these are **his** failures, at 71% accuracy and $6.5M a year. The
> presence of a documented failure mode is not evidence the method is unsound;
> it is evidence that the discipline layer is where the money is, which is the
> same thing his 40%-fewer-trades result says.

---

## 7. What this changes, in order

Nothing here is registered and nothing should be built from it before it is.

1. **Measure position construction on winners versus losers, in MCL and in the
   live path.** Ben's losers carry 26% more shares than his winners; Cameron's
   winners carry 36% more than his losers. This is one ratio, it is computable
   today from `flex_round_trips.csv` and any backtest trade list, and it is the
   cleanest difference in this document. **Adding to losers is the finding.**
2. ~~A per-day trade budget as a strategy parameter.~~ **WITHDRAWN** — see §2's
   banner and `warrior_census_20260910.md` §3. Ben's break at ~8 trades a day is
   real (≤8 is +$27,581, >8 is −$142,564) but a count cap is the wrong
   instrument: on a working method the same rule cuts the best days hardest.
   **Replaced by item 3, the daily loss stop.**
3. **A daily loss stop.** −$2,000 recovers 48% of Ben's loss. Note this is a
   *live-path* rule, not a backtest parameter — it governs the trader, not the
   strategy, and `PROGRAM_INDEX.md` §4 parity says whatever the backtest enforces
   the live path must, and vice versa.
4. **Register the 07:00 window for MCL.** −$2,166 sits in 04:00–06:00 against a
   −$1,270 total. In-sample, but with an independent prior from a practitioner
   who refuses that window and explains why (news timing, not mechanics).
5. **A setup-quality grade, even a crude one.** Cameron's regime numbers say C
   quality loses money in a cold market and MCL has no grading at all — it takes
   every mechanical signal, in every regime. `prior_spike_result.md` already found
   one binary that separates MCL's trades cleanly; that is a grade with one bit.
6. **The hold-50% rule**, from `warrior_5_selection_in_practice.md` §1 — reject a
   candidate that is not still holding half its initial pre-market impulse at
   decision time. Computable from `bar_cache` with no new field, serves the
   screen and the regime gate with one computation, and MCL has no equivalent:
   it ranks by gap size and never asks whether the gap is holding.
7. **Do not re-open the cent-stop question.** `cent_stop_decision.md` settled it.
   The finding here is about the *existence* of a cap, not its units.

---

## 9. Source coverage, stated plainly

**Videos read in full: 35**, across five extraction passes — 7 losing-day recaps,
7 discipline and metrics, 7 regime, 7 timing and green-day, 7 watchlist and
selection (`warrior_5_selection_in_practice.md`).

**Enumeration.** The channel feed paginates to 300 videos and then loops, which
reaches only ~Nov 2025. Searching within the channel for era-specific title
phrases reached **2025-07-01**, recovering **66 dated videos** across
Jul–Nov 2025. That window is a **representative sample, not exhaustive** — he
posts near-daily, so the true population for those five months is likely 150–250,
and there are real calendar gaps.

**A method note worth keeping:** title conventions on this channel turn over
roughly annually, so a phrase that dominates one year is nearly absent in
another. "Red Day Recap" and "Breaking News Sends Stock" returned almost nothing
from 2025; "Small Account Challenge" and "Watch List" returned most of it. Search
for the series names in use during the target era.

**One quantitative finding from the titles.** Explicit dollar P/L in a title runs
at ~7% of recent titles and **0 of 66** in Jul–Nov 2025 — the convention was
absent in that window and reappears either side of it, so it cannot be used to
build a P/L series. What *is* stable is the losing-day rate: **7 of 66 (11%)** in
2025 against **36 of 300 (12%)** recently. Both are titles, not accounting, and
both undercount — a red day only gets a red-day title when he chooses to make one.

---

## 8. The uncomfortable summary

Ben's ledger is not a version of Cameron's with worse execution. It is inverted
on the three things Cameron says decide the outcome:

- **He adds to losers; Cameron adds to winners.**
- **He trades more on bad days; Cameron trades less and made 3× more.**
- **He has no enforced maximum loss; every one of Cameron's rules is one.**

And MCL, which was built from Cameron's style, has a trade distribution nothing
like his — one win in three against five in seven — because a trailing stop is a
different strategy from a target plus a breakeven stop, whatever pattern triggers
the entry.

**None of that is a reason to abandon the universe.** It is a reason to stop
treating the entry rule as the thing that needs work.
