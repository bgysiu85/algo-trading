# §13 — Ross Cameron, the 46-day small-account challenge (companion to `source_videos_20260907.md`)

> **This is §13 of `source_videos_20260907.md`.** It is filed separately only
> because that document is 32,000 characters and lives solely in the project;
> appending would mean re-emitting all of it. **Read it as part of that file.**
> The §-numbering, the standing rules and the title-mismatch tally referenced
> below are all that document's.

**"How I Turned $2,000 into $105,951.28 in 46 Days (My Small Account Day Trading
Strategy)"** — Ross Cameron / Warrior Trading, `spaw93SAySQ`, **59:38**,
published 2026-09-16. 57,967 views, 2,199 likes, 350 comments. Sells study-guide
PDFs (email capture), a $20 two-week trial, and courses. **Read in full
2026-09-17** — all 11,284 words.

---

## 13.0 Why this one gets a section at all

Every other Cameron document in this project (`warrior_0`–`warrior_5`,
`claude_youtube_extraction_ross_cameron.md`, the 401-recap census) was built
from his teaching material. **This is the first one that is a complete, dated,
self-reported track record of a single strategy run end to end** — 113 trades,
46 days, stated accuracy, stated profit-to-loss ratio, stated broker, stated
leverage. That makes it checkable against our own book in a way a teaching video
is not, and §13.4 is the result of doing so.

It is also the source of the belief Ben raised on 2026-09-17 — *"if Ross Cameron
can grow a $2,000 account into $100k in 2–3 months, why can't we replicate it?"*
— so the file should carry the answer rather than leave it in a chat.

**Transcript defect, and it is the known one.** The auto-captions strip decimal
points from prices: his ZTG entries read *"$155 and $161"* (actually $1.55 /
$1.61) and his exits read *"260… 230, 223, 212"* ($2.60 → $2.12). Confirmed
against his own narration that the stock was *"a little on the lower side"* of
the $2–20 band. **This is the same defect that would have produced fictional
timestamps in the recap probe** (`time_of_day_RESULT_20260916.md`). Any figure
lifted from a Warrior auto-transcript must be sanity-checked against the stated
price band.

---

## 13.1 What he says, in full

**The five pillars of stock selection.** Up **≥10%** on the day · RVOL **≥5×**
the 50-day average · **news catalyst** today · price **$2–20** · float **<20M**.
He states these are derived from his own 10-year trade data, not opinion, and
shows the RVOL split.

**The tighter "highest quality" filter.** Up **≥30%** · breaking news preferred
but *"that can be an exception"* · price **$5–10** (*"my real sweet spot"*) ·
5× RVOL *"a must"* · **07:00–10:00 ET** · float **<10M**.

**Two further 10-year regularities**, stated as his own data: volume today
**>25M shares** does better, consistently and monotonically; and gap up **>2%**
is where *"pretty much all of my profit has come from"*.

**Time of day.** Better earlier, declining through the session. *"Time between
7:00 a.m. and really 9:30 for the cleanest action."* His stated mechanism for
why after 09:30 is harder is specific and worth recording: **market orders,
stop orders and halt levels** all appear at the open, and *"these all give the
market makers the upper hand against us."*

**Selection heuristic beyond the pillars.** Trade the **leading gainer**; prefer
the stock that is *"obvious… that I feel other traders are also likely looking
at."* And a cross-session one: after a big move, look for the name that
**resembles yesterday's big move** — he took ZTG partly because it was, like the
previous day's 2,117% mover, a low-priced foreign-listed China-connected name.

**Entry — step two.** Wait for the **first pullback**. Do not buy the squeeze,
because the nearest support is then far away and the R:R is unworkable. Enter on
the **"crossing candle"**: the first candle that breaks over the prior red
candle, *"the moment that candle breaks over the red candle, I'm in."*
**Stop = the low of the pullback.** First target = **retest of high of day**,
*"at least the same size as the risk but often higher."* Then: conservative
sells half at HOD, aggressive holds, very aggressive adds — *"only if we're in a
really hot market."*

**Exit indicators — step three.** Four, in his order: a **big seller on the
level 2**; a **hidden seller** (buying prints going through with the price not
budging); a **large burst of red on the tape**; and a **topping tail / doji** at
the top of a move. Plus the **volume profile of the move itself** — rising
volume is healthy, *"if volume starts high and is getting progressively lower as
the price goes higher, we call that a divergence"* and the move is likely to
roll over.

**Walk-away rules.** *"If I give back half my profit, I need to walk"* · hit max
loss, stop · time window closed, stop · no A-quality setups, stop · theme of the
day bearish, stop · and **do not come back**, which means not watching, *"because
if I keep watching on my phone… I'll just get FOMO."*

**The stated result.** 113 trades over 46 days · **70% accuracy** · average
winner ≈ $2,000 · average loser ≈ $2,000 · **profit-to-loss ratio ≈ 1:1** ·
career figures given as 35,000+ trades at ~70% and ~1:1.

**Two disclosures that matter more than the rules**, and he volunteers both:

- **Commission-free broker (Charles Schwab), cash account, no leverage.** He is
  explicit that this was a downgrade from the previous challenge, where he used
  margin: *"they didn't extend leverage for pretty much any of these lower-priced
  stocks."* He argues the growth is therefore *better* on a like-for-like basis.
- **For a small account, commissions are the binding constraint.** *"The
  commissions can be hundreds of dollars a day potentially. So, if you're trading
  in a small account and your goal is 200 a day, you want to keep as much of that
  as you can."* He recommends commission-free up to ~$50k, then a direct-access
  broker.

**He names his own mistakes**, unusually for this file: trading lower-RVOL names,
trading low-volume names, trading gap-*down* reversals, being impatient and not
waiting for the pullback, holding losers too long, and not walking away.

---

## 13.2 Almost all of it is already in this project, and four items are closed

This is the important section. **Nothing below should be re-proposed from this
source.**

| What he says | Status here |
|---|---|
| Five pillars ($2–20, RVOL ≥5×, float <20M, top gainer) | **Already our screen.** `vw9_strategy_spec.md` §1 is this, almost verbatim |
| Wait for the first pullback; enter on the crossing candle | **CLOSED.** `pullback_break` v1–v6 — six registrations, six NOTHINGs, two timeframes, every version landing on that timeframe's own control |
| Stop at the low of the pullback | **CLOSED.** That is v4's structure stop. NOTHING |
| Sell half at high of day | **REJECTED twice.** Cameron partial +$261 → −$1,435; ladder +$272 → −$1,612 |
| Breakeven stop on the remainder | **REJECTED.** −11.3 pts win rate, −$4,271 → −$27,260 on 4,481 trades |
| Cent-scale stops (his 10–20c elsewhere) | **CLOSED.** Monotone worse at 10/15/20c; boundary check fires |
| Topping tail / doji as an exit | Already codeable and already catalogued — `warrior_0` §5.3, `warrior_1` §4, `REGISTERED_bar_shape_20260916` |
| "Breakout or bailout" / time cap | **REJECTED.** `hold_cap_decision.md` — every cap loses, monotone, boundary check fails |
| Big seller / hidden seller / burst of red on the tape | **Not codeable.** No tape in the backtest. Already recorded as such in `warrior_1` §4 |
| Float <10M or <20M | **Removed from the screen 2026-09-08, for two independent reasons** — the TradingView CSV is a static proxy, and filtering a sparse field silently drops nulls toward exactly the population the screen exists to find. Re-adding needs point-in-time float, which is an open PROGRAM_INDEX item |
| RVOL ≥5× | **Not computable on the current tape.** `relative_volume_10d_calc` needs ten sessions of intraday volume by time of day; each cache file holds three. `orb_preflight_RESULT_20260916` reports it NOT COMPUTABLE rather than approximating it |

### 13.2.1 And one of his rules is refuted by our own data

**His trading window makes MCL worse, monotonically.** He says 07:00–09:30 is
cleanest and that he regrets trading past the open. `session_start_RESULT_20260917.md`
swept exactly this on the point-in-time books:

| session start | MCL per trade, gross |
|---|---:|
| 04:00 | (6.26) |
| 06:30 | (6.56) |
| 07:00 | (7.32) |
| 07:30 | (8.50) |

Every later start is worse, and the 04:00–06:29 block that his rule would discard
is the **least bad** one in the book. Both temporal halves negative in all twelve
rows; drop-3 and drop-5 negative throughout.

**This is the file's first case of a source rule being contradicted by our own
measurement of the same universe he trades**, rather than by an outside tester
(§2.1, §8) or by a class argument (§10.4). It is the strongest kind of negative
this project can produce, and it should be quoted whenever the time-of-day
question is reopened.

---

## 13.3 What is genuinely new — two things

**(a) The give-back cap, and it is a second independent arrival.**

> *"if I give back half my profit, I need to walk. Because by giving back half my
> profit, I'm almost inevitably, invariably, emotionally compromised."*

Malyarovich, §12.6, two days earlier: *"You have to protect at least 50% of the
profit that you make on a day-to-day basis."* Two unrelated practitioners, the
same threshold, no shared lineage.

**It matters because of the family it belongs to.** Every mechanic tested on MCL
is trade-level — entry filters, entry margins, stops, exits, regime gates. This
is **session-level**, conditioned on the session's own realised path, and it is
distinct from the daily loss stop (PROGRAM_INDEX item 11), which triggers on
absolute drawdown from zero rather than on a retreat from the session's peak.
**Nothing in that family has been tested.**

Registered as **H-S4**, `REGISTERED_giveback_cap_20260917.md`. Note the control
that decides it: on a book losing (10.52)/trade, *any* rule that removes trades
improves the total, so the primary reading is per **remaining** trade against a
matched random-truncation H0.

**(b) His price sweet spot converges with ours, from the opposite direction.**

He says $5–10 within a $2–20 band. `cent_stop_decision.md` §3 found, from our own
trade list and for an entirely unrelated reason (comparing cent stops against the
percentage trail):

| entry price | MCL, 5% trail |
|---|---:|
| $2–4 | −$3.89/trade |
| $4–7 | −$1.67 |
| **$7–12** | **+$5.40** |
| **$12–20** | **+$8.70** |

*"The 5% trail makes all of its money above $7 and loses below it."* Two
independent roads to the same conclusion about the low end of the band. **Not
actionable as a filter on its own** — `where_the_edge_is_20260913` closed
dollar-volume floors because the removed trades lost the same as the kept ones,
and a price floor must clear the same bar. But it is a convergence, and this file
records those.

---

## 13.4 The comparison the challenge invites, done properly

His figures against MCL's measured point-in-time book
(`pit_three_results_20260911` §3):

| | Cameron, 46-day challenge | MCL (PIT book) |
|---|---:|---:|
| trades per day | 2.46 | **7.18** |
| win rate | **70.0%** | 21.7% |
| average winner | ≈$2,000 | $41.53 |
| average loser | ≈$2,000 | $24.87 |
| R (win ÷ loss) | 1.00 | 1.67 |
| breakeven win rate at that R | 50.0% | 37.5% |
| **cushion over breakeven** | **+20.0 pts** | **−15.8 pts** |

**The deficit is accuracy, not reward.** Our R is *better* than his. To reach
breakeven MCL needs **+15.8 points of win rate**, or R to rise from 1.67 to
**3.61** — a 116% improvement. This restates `win_rate_and_r.md` on the
point-in-time book, and it is the cleanest external calibration of that document
the project has.

**And then the structural difference he states himself.** He ran the challenge
at **zero commission**. Our friction ladder is $1.00 / $4.26 / $8.92 per
100-share round trip. At MCL's trade rate:

| friction | per day | over 46 days | vs a $2,000 starting account |
|---|---:|---:|---:|
| $4.26 | $30.58 | $1,407 | **0.7×** |
| $8.92 | $64.03 | $2,945 | **1.5×** |

**Forty-six days of MCL's trade rate costs between seventy percent and one and a
half times the entire starting account, in friction alone, before any P&L.** He
pays none of it. He also trades **2.9× less often** than MCL, which compounds the
difference rather than diluting it.

That is the answer to the replication question, and it is arithmetic rather than
opinion: **we are not failing to find his setups — the screen found all five of
his watchlist names on 2026-09-14 (`session_review_20260914_15.md` §5). We are
paying a toll he does not pay, three times as often, on the long side of a
universe he frequently shorts.**

---

## 13.5 Standing on this source

**A track-record source and a calibration source, not a strategy source.** Take
§13.3(a) — the give-back cap — which is registered. Record §13.3(b) as a
convergence. Use §13.4 whenever the small-account challenge is raised again.

**Do not re-propose** anything in §13.2's table. Four of those lines are closed
registrations and two are data-availability blocks, not open questions.

**And log the title.** *"How I Turned $2,000 into $105,951.28 in 46 Days"* is
accurate to his own account and unusually precise; the video's body also states
plainly that results are not typical, that he has traded since 2001, and that
the viewer should prove profitability in a simulator first. **This is the
best-disclosed source in the file** — which is worth saying, given how §4's tally
runs. Against that: the FTC sued Warrior Trading over its marketing in 2022, the
company settled for **$3 million** without admitting wrongdoing, and the FTC
returned **$2.9 million** to customers; the settlement order restricts how
earnings claims may be made. Both facts belong next to each other.

---

### Sources

- Video: https://www.youtube.com/watch?v=spaw93SAySQ (read in full, 2026-09-17)
- FTC v. Warrior Trading: https://www.ftc.gov/legal-library/browse/cases-proceedings/2023198-warrior-trading-inc-ftc-v
- FTC press release, April 2022: https://www.ftc.gov/news-events/news/press-releases/2022/04/federal-trade-commission-cracks-down-warrior-trading-misleading-consumers-false-investment-promises
- FTC refunds, January 2023: https://www.ftc.gov/news-events/news/press-releases/2023/01/ftc-returns-more-29-million-consumers-harmed-warrior-trading
