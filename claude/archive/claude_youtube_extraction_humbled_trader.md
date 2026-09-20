# YouTube extraction — method, tooling, and Humbled Trader shortlist

Started 2026-09-09. Channel: `@HumbledTraderOfficial` (`UCcIvNGMBSQWwo1v3n-ZRBCw`),
1,073 videos, 1.5M subs, active since 2018.

Purpose: mine trader interviews and strategy videos for rules that can be
tested against the existing MCL / VW9 / ORB work. Output is a **backtest
queue**, not strategies — see §5.

---

## 1. Tooling — two servers, different jobs

| Job | Tool | Cost |
|---|---|---|
| Channel/playlist enumeration, deep pagination | **TubeAlfred** (remote MCP) | 1 credit/call |
| Transcripts, transcript search, metadata | **YouTube MCP** (local, Claude Desktop) | free |

`claude-code-youtube-mcp` (github.com/wynandw87/claude-code-youtube-mcp) installed
as a Desktop **unpacked extension** at `C:\Users\bens8\claude-code-youtube-mcp`,
same route as `tradingview-mcp`. Needs a `manifest.json` (the repo ships none) and
a built `dist/index.js`.

**Transcripts cost zero API quota** — they go through YouTube's Innertube endpoint
and never touch the `YOUTUBE_API_KEY`. The key only gates metadata, channel and
playlist listing (10,000 units/day; the whole exercise below cost <10 units).
So there is no reason to spend TubeAlfred credits on transcripts, ever.

TubeAlfred: 5,000-credit plan bought 2026-09-09. Balance after this session ≈5,026.

### Gotchas hit

- **`get_channel_videos` caps at 50, no continuation parameter.** Cannot page a
  1,000-video channel. Orderings are `date` and `viewCount` only → ~100 max.
- **`search_videos` (local) has no channel filter.** Useless for enumeration.
- **TubeAlfred channel-scoped search returns ~30 results then stops** — the
  continuation token comes back empty. Coverage comes from *more queries*, not
  more pages.
- **`duration: over_twenty_mins` leaks badly.** Returned 8-second Shorts. It
  reduces noise, it does not filter.
- **TubeAlfred dates are derived from relative strings** ("1 year ago"), so dozens
  of videos share one fabricated timestamp. Use the local server's
  `get_video_metadata` for real publish dates.
- **TubeAlfred payloads are heavy** (thumbnails + repeated channel object per
  video). Credits are cheap; **context is the binding constraint**. Cap at 2-3
  pages per session and triage as you go.
- Date-ordered channel listings are dominated by Shorts — 1 interview per 50.
  **Playlists are the better handle**: the "Humbled Traders Podcast" playlist
  (`PL0u56lu3jgFdTr0KIlvfvype0T1CEJKcu`) returned all 38 episodes in one call.
- `get_clean_transcript`'s SponsorBlock stripping depends on community
  submissions. On this channel there are none — it returned the raw transcript
  unchanged. Do not rely on it.

---

## 2. The method that works, for any channel

1. **Enumerate** — playlist first if one exists (cheap, curated, free via local
   server). Then 2-3 TubeAlfred channel-scoped searches with varied queries to
   catch non-playlist content.
2. **Sweep** — `search_transcript` (free) with **distinctive single terms**, one
   per candidate. Returns only matching segments + context.
   - Multi-word phrases match only *within a single caption segment* — "position
     size" misses when it straddles a boundary. Use single words.
   - Topic words flood: "trend" in a trend-following interview returned 100 hits.
     Use terms that discriminate, not terms that describe.
   - A zero-match result should be validated with a second common term before
     concluding the episode is empty — it may just have no captions.
3. **Transcribe** only the hits. ~12-15k tokens each; **5-6 hour-long episodes
   per session** before extraction quality degrades.
4. **Write findings to a file as you go.** Credits and quota are not the limit;
   context is.

**Sweep terms that discriminated well here:** `float`, `backtest`, `statistics`,
`sizing`, `win rate`, `risk reward`, `crowded`.

---

## 3. Shortlist — 11 to transcribe

### Interviews (swept, confirmed)

| # | Video | ID | Len | Why |
|---|---|---|---|---|
| 1 | Verified 8-Figure Trader Explains Statistics & Trader Psychology | `cR7jWckuoXw` | ~55m | 20 hits. Densest methodology on the channel. Enumerates what he tracks; says biotechs don't follow small-cap stats; says the stats keep changing (regime drift) |
| 2 | Millionaire Trader developed his QUANT TRADING ALGORITHM (Evan Schunk) | `T3sCLOvsdus` | 56m | Gapper DB keyed on OHLC/float/market cap; tests which variables move win rate; rules like "float 1M-2M gapping up X" |
| 3 | Millionaire Trader explains Systematic Trading Strategies | `oSznkl4ASaA` | 1h21m | **Scores** float rather than filtering; rates sub-1M float as *dangerous*. Contradicts our V4 result — read for the disagreement |
| 4 | How to be the Top 5% Winning Trader (Lance Breitstein) | `qGU3DcvYLSw` | ~1h | "Exponential bet sizing" @14:37; concentrate size on highest-conviction trades; sizing is a late skill |

### Shay's own content (found via channel crawl, NOT in the podcast playlist, unswept)

| # | Video | ID | Len | Why |
|---|---|---|---|---|
| 5 | Trade Ideas Scanner Tutorial 2026 (settings download) | `e69ZES9xlI4` | 32m | An actual screen definition w/ downloadable settings. Closest thing on the channel to our universe spec |
| 6 | My new Premarket Routine made me $200K more in Swing Trading | `q3oSEjL_Tno` | 23m | Premarket process |
| 7 | Live Trading on the 5-Minute Time Frame (how I keep it simple) | `gn02_Ic9i5U` | 26m | **She abandoned the 1-minute.** MCL is 1-minute — want her reasoning |
| 8 | VWAP Trading Strategy Crash Course | `dgfQkFSzhiY` | 43m | VWAP carries our trailing logic |
| 9 | How To Find Profitable Stocks To Trade | `VDN4jp4Uf1k` | 21m | Selection process |
| 10 | How I Made $2200 in 30 Minutes using this Entry Technique | `ZjTYNf4-tpc` | 36m | Entry mechanics |
| 11 | How to Day Trade Gappers and Stock Gap Ups | `cgf0FjzdsKg` | 13m | Gapper handling |

### Ruled out by sweep — do not re-check

| Video | Reason |
|---|---|
| TRUTH about Trading Bot Algorithm ft. Quant CEO (`lx2zPCdH_1Y`) | 0 hits "backtest"; defines an algorithm as an if-then statement for beginners |
| Millionaire Trader … Penny Stocks (`13jbqQbPWec`) | 0 hits "float", in a penny-stock episode |
| From Beginner to $1.6M — Mari (`M5thAKMJsrw`) | 1 float hit: why she *quit* low-float shorting |
| $4.6M with Extreme Risk Management (`WYemFjnnj7s`) | 0 hits "position size"; risk talk qualitative. Title oversells |
| 8 Figures in Verified Profits (`5pJisejZrGg`) | 1 float hit: no longer follows low floats |
| Bao, 30-Year Veteran (`l4XWtxqiKQs`) | 2 hits, one metaphorical |
| 90% Win Rate (David Capablanca) (`kRrMz_aDuw4`) | See §5 — kept only as a cautionary datapoint |
| 9-Figure Futures / Crowded Market (`j0VwxawidR4`) | Edge is a COT positioning-crowding metric. No COT equivalent for small caps — not portable |
| Rayner Teo trend systems (`HtF7bmw6hZc`) | Genuinely systematic but futures/FX. Transferable *concepts* only: S&P-vs-200DMA trend filter gating exposure; breakout over pullback entries to guarantee participation; trailing stop as the entire profit mechanism |

**Duplicate:** `D_DWkbIoXYg` and `lFpXohf8ghk` share a title, one marked "Full
Podcast" — clip and parent. Don't transcribe both.

**Not swept:** ~24 Tier-3 podcast episodes (options, investing, mindset,
compilations) plus the bulk of the 1,073-video channel (mostly Shorts). Four
other playlists exist if needed: Day Trading for Beginners
`PL0u56lu3jgFf2gBxz7mMq7_0k0UvG7ZOe`, Advanced Strategies
`PL0u56lu3jgFcJSUYhmA77sttqG4Xmxu8X`, TA Masterclass
`PL0u56lu3jgFeaEnimp4pNLlEhShWnRIMq`, Swing for Beginners
`PL0u56lu3jgFcabKFkv6u6lfOox90djSii`.

---

## 4. Extracted so far

### Eduardo (`@edu_trades`) — `DE4z8dEBf5Y`, Jan 2024, 1h03m
Small caps only, ~9 years, Kinfo-verified. "Shares recycling."

**Long criteria (shorts are the inverse — he flips the chart with a `-` prefix in ThinkorSwim):**
- No dilution — checks filings for ATMs and warrants
- Gap up but **not** overextended: ~50%, explicitly not 100%+. Wants enough
  extension that shorts are attacking, not a parabolic
- Volume must **rotate the float** — 10M float wants ~20M volume
- **Pre-market volume × 7** as the full-day volume estimate (notes some use ×4)
- Strong catalyst — revenue-bearing (a contract), not general product PR
- **No overhead resistance** on the daily: look left, price must not sit below a
  high-volume shelf

**Position mechanics (the novel part):**
- Risk level = the chart level that invalidates the thesis
- Position so the **average** entry sits near it; size so a hit costs a fixed $
- Worked example: risk level $5, budget $1,000, avg $5.10 → 2,000 shares
- ~1,500 core / ~500 recycled — the traded sleeve is **~25%** of the position
- Trending: trail the risk level, **VWAP** as the reference on momentum names
- Consolidating: cut size (edge is in the trend)
- Midday: reduced size, specific setups only
- **Equity curve dictates size** — up on the month, push; drawdown, cut.
  Deliberately the inverse of revenge sizing

**Testable claim:** ~80% (he says 79-81) of small caps gapping 80-100%+ close red
on day one. Filter: *"if they're not red on the day, don't short them."* Also:
biotechs running 100% tend to fade ~15% open-to-close. First days have the most
volume, which is why he focuses there.

### Steven — `cR7jWckuoXw`, Nov 2023, ~55m
Verified 8-figure. **Short seller** of small-cap multi-day runners. The most
mechanically specific guest on the channel.

**Bucketing method (how he built the stats).** Started with **25 buckets**
defined by market cap × float × gap%. Examples as stated: mcap 0-10M / float
0-1M / gap >50%; mcap 0-20M / float 1-3M / gap 50%. Hold every factor fixed,
**vary exactly one**, observe what changes. "Similar float, similar market cap,
if the volume is different, I'm supposed to do this."
→ This is a one-factor-at-a-time sensitivity design, and it is the same thing
our parameter sweeps do. Worth noting he needed ~25 cells before it was useful.

**Retail dollar capacity (his entry trigger).** There is a maximum dollar amount
retail can pour into a ticker, scaled to market cap. Measure it as
`volume × average traded price` on the day. When a runner hits that threshold,
it goes down the next day — the move has exhausted its buyer pool.

> **The threshold is not stationary: $1bn in 2021 → $200M in 2023.** A 5×
> collapse in two years. He states it flatly: "it still performs great, it's just
> the statistics keep changing."

**This is the most important thing in the transcript for us.** It is a
practitioner independently reporting that a core parameter moved 5× in 24
months. Any backtest that fits such a parameter on one period and applies it to
another is measuring the wrong thing. Cf. our own regime concerns.

**Resistance vs float — the anti-squeeze filter (novel, and computable).**
A price level that traded 50M shares is *not* 50M shares of trapped bagholders
if the float is only 3M. There can only be ~3M bagholders. So the level is far
weaker than its volume implies and is likely to break.
→ Most traders short into high-volume resistance; on low-float names that is a
trap. **Testable from data we already have** (volume-at-price + float). This is
the one idea from the whole channel I have not seen elsewhere.

**"First red day" — his favourite pattern, fully specified:**

| Element | Value |
|---|---|
| Universe | multi-day runner, **not** IPO, **not** biotech |
| Initial market cap | < 100M |
| Float | < 5M (says "under 10M works too") |
| Direction | short |
| Entry | when retail dollar capacity is met |
| Avg fade, first red day | **−26%** |
| Avg fade, second day | **−15%** |
| Typical low | **10:30 ET** |
| Management | hold overnight for the gap down, cover ~10:30 |

**Exclusions, both hard:**
- **Biotechs.** "They do not follow small cap statistics at all." He tracked
  stats on them and still lost, long or short, over years. Explicit no-go.
- **Initial market cap > 300M.** Below 300M it can run to billions and the stats
  still hold; starting above 300M they don't.
- Gap **>100%** is his highest win-rate bucket.

**Biggest loss — and it confirms §5.** A biotech, 13M float, hit the retail
number, then squeezed through it. **He sizes in big precisely *because* that
signal has a high win rate.** Liquidity was poor, exit took a long time,
~**$1M loss**. High accuracy → large size → one tail event. Third instance of
the same failure mode.

### Evan Schunk — `T3sCLOvsdus`, Jan 2025, 56m
Fully automated **short** seller of small caps. Six strategies. Algo handles
locates, entry, exit, notifications; he supervises for bugs.

**Data stack: Polygon.io** (primary) and Spikeet. Notes Polygon isn't
user-friendly and you must code to get data out.
→ **Directly relevant to our open source decision.** An independent practitioner
running exactly our use case — bulk historical gapper scanning — on Polygon.

**Origin of the edge.** Lost ~$10-12k over two years trading long, discretionary.
Started tracking gapper data by hand on paper (pre-Excel, literally), then found:

> **Large-percent gappers have ~80% (he says 79, "varies per year") chance of
> closing BELOW THE OPEN price that day.**

**Note the definition.** This is *below the open*, not "closes red versus prior
close" — which is how Eduardo stated the same statistic. **Those are different
measurements** and a gap-up name can easily do one and not the other. If we
backtest this, define it explicitly. Two independent sources now quote ~80%, and
both add that it moves year to year.

**What he tracks:** OHLC, **time of day the high is made**, market cap, float,
resistance, occasionally news. "Any variable I could think of." Then tests which
ones shift the win rate.

**Rules are fully quantified** — e.g. "only trade stocks with float 1M-2M gapping
up this much." Nothing enters the algo that isn't a number.

**News handling:** 98-99% irrelevant for small-cap shorts (recycled garbage PR).
The 1% exception is real mainstream-viral news, or a small cap tied to a major
name (his example: an Nvidia partnership). He will **manually override and not
short** those. Worth noting the one discretionary override he keeps is a
tail-risk veto, not an entry.

**Stops:** hard market stops, data-derived. Accepts slippage on squeezes as the
cost of guaranteed exit.

**Risk-reward, stated plainly: between 1:1 and 1:2 AGAINST him.** "Rarely do we
make more than we risk." He uses deliberately **wide** stops because the data
favours them, and pays for it in reward. Win rate correspondingly high.
→ Breakeven at 1:2 adverse is a **66.7%** win rate. Unlike Eduardo and
Capablanca, he states the reward side up front rather than leaving it vague — but
it is the same structure. **Third instance.**

**Sizing: fractional Kelly** (his third distinct framework in this file).
- Set a bankroll at the start of the year
- Risk a fixed % of *current* bankroll per trade — 10% typical, 14% his highest,
  varying by strategy
- Bankroll 50k → risk 5k; after a +2k day, bankroll 52k → next trade risks 5.2k
- Sizes **down** automatically on losses
→ Mechanically identical to Eduardo's "equity curve dictates size," but formal
and automatic rather than discretionary. **10-14% of bankroll per trade is
aggressive** even as fractional Kelly — worth checking what drawdown that implies
at his stated win rate before borrowing the number.

### "Systematic Trading Strategies" guest — `oSznkl4ASaA`, Apr 2024, 1h21m
**Short**-side small caps. Different in kind from Steven and Evan: a **weighted
scoring rubric**, not hard quantified rules. Discretion, disciplined.

**Four pillars.** Technicals, fundamentals, news (inherited from a nine-figure
trader) plus **cycle**, which he added himself.

**The ADF score** (credited to Old Day Faders). A grading rubric in a
spreadsheet: assign each pillar a weight summing to 100 — his example is
technicals ~40, fundamentals ~30, news ~5-10 — score a setup on each, output a
letter grade.
- **Calibration method:** reverse-engineer the best setup you have personally
  seen, define *that* as A+, then rank everything against it. Not the best trade
  in the world — the best you've seen.
- Purpose is to correct first-impression bias: he found setups he'd have rated
  low were often good trades, and vice versa.
- Eventually internalised; he no longer writes it down.

**Why he penalises sub-1M float — and why it does NOT contradict our V4 result.**
His reason is structural, not statistical: nano-floats are **prone to halting at
the open**, making extreme moves, then dumping supply. "No matter how good" the
fundamentals, the float structure dominates.

> **This is a short-seller's objection.** An extreme upward move is a blowup if
> you are short and the *win* if you are long. **MCL is long-only pre-market.**
> WVVIP (+783%, ~3,080 shares per 30s bar) is exactly the name he is warning
> shorts away from — which is consistent with it being our best long.
> **The disagreement with Evan's 1M-2M float band and with our data is
> directional, not factual.** Resolve float rules per side; do not import a
> short-side float floor into a long strategy.

**Supply-side mechanism worth knowing.** He observed in Dec 2023 more stocks
reverse-splitting under 1M shares than he had ever seen — "before 2020, before
2023, you almost never saw a stock under 1M float." So the sub-1M population is
*manufactured* by reverse splits and its prevalence swings with corporate-action
cycles. → A float screen is sampling a population whose composition changes.
Worth checking whether our universe is picking up reverse-split artefacts.

**Dilution nuance (he is emphatic this is where people go wrong):**
- Filing data goes stale — a January dilution figure may be void by March if an
  in-the-money ATM was tapped in February on heavy volume
- **Private placements are commonly misread as dilution.** The language mentions
  warrants and issued shares, but that supply is *not effective at that moment*.
  The market knee-jerks; the dilution isn't live
- He grades "good supply" — in-the-money, not recently tapped — as a *positive*

**Cycle / regime as an explicit scoring input.** When shorts are collectively
greedy, oversized and compounding, an A+ setup can be invalidated outright or
merely made hard to execute — it "has to squeeze first." He treats market
psychology state as a first-class variable rather than noise.
→ **Third independent source on regime dependence**, after Steven's 5× retail-
capacity shift and Evan's "varies per year."

**His data collection is manual and total.** Screenshots of every stock that
appeared in his strategy, every day — daily, 1-minute, 5-minute, 15/30-minute —
going back years, stored alongside the grade he assigned at the time. He can
reconstruct what he traded, what he should have traded, and what he passed on.

### Lance Breitstein — `qGU3DcvYLSw`, Oct 2023, ~1h
Verified 8-figure prop trader / mentor. Large caps and momentum, not small-cap
specific — but the sizing argument is the most transferable idea in the batch.

**Exponential bet sizing.** Vary size by **setup quality**, not by account state.
- The leap from unprofitable to consistently profitable comes, "nine out of ten
  times," from focusing on the easy trades and **sizing those up** — not from
  eliminating mistakes. Good traders still make dumb errors; the difference is
  what they do right outweighs it.
- The failure mode he names: a new trader sizes everything the same, then takes
  "double or a little bit more" on the one or two setups they actually have an
  edge on. Far too timid.
- In prop trading he says the debate doesn't exist. Good traders bet **10× to
  100×+ more** on the rare special events. "If you told me I had to bet the same
  on every single trade, I'm not sure I would even make money."
- Poker framing: if you can tell pocket aces from an average hand, of course you
  bet differently.

**The precondition, which he states explicitly and is the part that matters for
us:** this only works *if you can differentiate trade quality ex ante*. "There
are some traders where they're not able to differentiate whether that trade might
be better than the other options — if so, you have no choice but to assume the
same bet."

> **That precondition is a testable question, not a matter of opinion.** Does our
> signal carry information about *magnitude*, or only about direction? If
> per-trade features predict outcome size, variable sizing is justified and MCL's
> flat `min(100 shares, 40% equity)` is leaving money behind. If they don't,
> uniform sizing is correct and Breitstein's advice is inapplicable to us.
> **Check before adopting.**

**Sizing is a late skill.** For beginners: "forget about sizing, just trade one
share at a time and build up the reps." He is not recommending size variation to
someone still establishing whether they have an edge at all.

**Caveat on the examples.** He reaches for Buffett in 2008 and Soros/Druckenmiller
on the pound. Both are survivorship anecdotes about discretionary macro
conviction, and neither supports the claim about systematic per-trade sizing.
The prop-desk observation is the substantive part; the legends are decoration.

### Shay (host) — Trade Ideas scanner setup — `e69ZES9xlI4`, Feb 2026, 33m
Her actual production screens, stated as numbers. Not an interview.

**Small-cap gap scanner:**

| Filter | Value |
|---|---|
| Change from close | **≥ 10%** |
| Price | **≥ $1** ("I don't trade penny stocks") |
| Volume today (from pre-market) | **≥ 20,000 shares** |
| Relative volume | **≥ 1** |
| Market cap | **≤ $1bn** |
| Float / short float | **deliberately blank** |

**Large-cap gap scanner:** gap ≥3%, price ≥$1, pre-market volume ≥20,000, market
cap ≥$1bn, relative volume left at **0** pre-market, everything else blank.

**Multi-strategy alert filters (large-cap breakout):** ≥$1, volume today
≥100,000, RVOL ≥1, ≥3% from previous close, market cap ≥$1bn.

**Her five live strategies:** small-cap high-volume breakout (<$1bn cap);
large-cap new-high-of-day breakout; large-cap 52-week-high breakout (365d); gap
reversal; trend long; plus a daily SMA cross for swings.

---

#### The important finding: **a float filter is also a data-availability filter**

Trade Ideas does not have float for every symbol. She demonstrates it live: with
no float filter, a set of gappers appears. She sets a 1M float minimum and
**those stocks vanish — not because their float failed the test, but because
their float was undefined.** Removing the filter brings them back.

> **Any filter on a sparse field silently drops rows where the field is null,**
> and the dropped names are not random — they skew toward newly listed, recently
> reverse-split and thinly covered symbols, which is exactly the population a
> small-cap momentum screen exists to find. This is a *selection* bug, not a
> data-quality nuisance.

We already removed float from the MCL screen on 09-08 for a different reason (the
TradingView CSV is a static proxy). **This is a second, independent reason**, and
it generalises: check every screen for filters on fields that can be null.
Our own `watchlist.txt` header still advertises a float filter that no longer
exists — worth confirming nothing downstream reintroduces one.

**Her alternative: colour-code instead of filter.** She colour-codes float,
volume and relative volume by range (half-million float one colour, 1M orange,
up to 200M at the top) so a null value still shows the row. **Same "score, don't
filter" philosophy as the `oSznkl4ASaA` guest** — arrived at independently, and
for a different reason. Two of the seven sources now argue for ranking over
gating.

#### Definitional trap: "gap %" vs "change from close"

- **Gap %** = previous close → pre-market price. **Stops updating at the open.**
- **Change from close** = stays live *after* the open.

She uses change from close for this reason. → Our screens and any backtest of the
80% gap-fade claim need to state which one they mean; they diverge intraday and
the divergence is largest on exactly the names that run.

#### Smaller but useful

- **Historical replay:** Trade Ideas can set the scanner to a past date and time
  and show what it *would* have surfaced pre-market. That is precisely what the
  screener simulation is trying to reconstruct — worth knowing a commercial tool
  treats point-in-time replay as a basic feature.
- **Alert dedup:** "don't repeat symbol for 5 minutes," because a breaking-out
  name otherwise fires 20+ times. Relevant to our alerting.
- **Half-million float:** "micro float, very dangerous to trade." **Third source**
  warning off nano-floats — again from a discretionary/short-aware view (see the
  directional caveat under `oSznkl4ASaA`).
- She tried Trade Ideas' "Holly" AI alerts a couple of years ago and didn't like
  them; trades her own strategies manually.
- Wide-net philosophy generally: "I prefer to cast a really wide net, especially
  pre-market," and leave most filters blank.

### Shay — 5-minute vs 1-minute — `gn02_Ic9i5U`, 2024, 26m
"I almost never use the one minute time frame anymore." ~10 years trading.

**Her entry rule (stated precisely):** a candle must **close** above *both* VWAP
and the **8 EMA**. Not touch, not wick through — close. Risk goes below both.
**Management:** ride the 8 EMA; she stays in while no candle closes below it,
even when price is under a daily key level.

**Context first:** previous day's high and low are checked on the daily *before*
looking at any intraday chart. Most volatile window 09:30–11:30.

**Her evidence.** On the 1-minute she counts *six* failed VWAP breakouts before a
clean one (NVDA), and a double-bottom that fires on the 1-minute and doesn't
exist at all on the 5-minute. The 1-minute gave a false reversal signal; the
5-minute gave no signal, which was correct.

> **Read her argument carefully — it is psychological, not statistical.** Her
> stated reason is always some version of *"there's no way I could have sat
> through that."* Patience, FOMO, revenge trading, stopping out early. Those are
> costs a **discretionary** trader pays. **MCL is automated and has infinite
> patience**, so her reasoning does not transfer even if her conclusion might.

**What does transfer, as testable claims:**
1. **Close-above vs cross.** Requiring a *close* beyond the level is a
   confirmation filter distinct from a touch or an intrabar cross. We hit this
   already going V1 (MACD *crosses*) → V2 (MACD state). Worth checking whether
   MCL's conditions are close-confirmed or bar-touch.
2. **Coarser bars → fewer, better trades.** Our own data already points this way:
   V4 at 1 min averaged **$9.47/trade** vs Control A at 30s at **$2.88**. Her
   claim is the same gradient extended one step further.
3. **8 EMA as a trailing reference** instead of a fixed 5% trailing stop.

> **We already have MC5** — the 5-minute strategy, 27 tests passing, never run on
> real data. Her argument is not evidence, but it is a reason to move MC5 up the
> queue: it is the natural test of the one claim here that could matter to us,
> and it costs only a backtest.

**Note her live example is a short** — waiting for a first red day on a parabolic
name (ZAP), scaling in, holding through a bounce because the bounce candle's
volume was lower than the preceding red candle's. That volume-asymmetry read is a
reasonable discretionary tell but is not specified tightly enough to code.

### Shay — pre-market routine — `q3oSEjL_Tno`, 2025, 23m
Four steps: scan gappers → news → technical key levels → watchlist.

**Her scans here differ from the Trade Ideas video** (different tool, her own
Stocks.io). Small-cap pre-market: market cap **< $1bn**, volume **≥ 100K**, gap
**≥ 15%** overnight, then narrow to **RVOL ≥ 2**. Large-cap: cap ≥$1bn, gap ≥3%,
≥$1M volume, sort by gap %, **take the top 5**.
→ Note the small-cap thresholds moved (10% / 20K in the Trade Ideas video vs
15% / 100K here). **Her numbers are not precise constants** — treat any single
quoted threshold from any of these sources as an order-of-magnitude hint.

**Two small-cap setups named:**
- **Bagholder daily short** — shorting names gapping up *into* recent daily
  resistance.
- **Short-trap consolidation long** — long low-float names with a catalyst on the
  **first or second day** of the gap-up/breakout. **This is MCL's territory**,
  described from the discretionary side.

**Hard rule: no swing trading small caps, ever.** Overnight risk exceeds large
caps — "you either wake up rich or you wake up broke." Consistent with MCL being
intraday/pre-market only; a point in favour of not extending it overnight.

**News, and it cuts against Eduardo.** For small caps she says news is a
*reference point only*, never the determining factor — stocks rally with no news
at all. What actually matters: **float, relative volume, short interest**
(>20-25% short interest is high). For large caps, catalysts are much more
important and reliable.

> **Scoreboard on catalysts for small caps:** Eduardo requires a strong,
> revenue-bearing catalyst for a perfect long. **Evan (98-99% irrelevant) and Shay
> (reference point only) both disagree.** Two of three say the catalyst is not
> the edge. Our screens don't read news anyway — this is evidence that omission
> costs less than it appears.

**Technical filter (step 3):** long only if breaking out *above* key daily
resistance with a "staircase" of room to the next levels. Dislikes a gap-up that
sells off back under resistance. Echoes Eduardo's no-overhead-resistance rule
from the opposite direction. Speed: **10-15 seconds per chart, 20-30 charts**.

**Watchlist format (step 4)** — worth stealing verbatim for `var/watchlist.txt`:
strategy name · news catalyst · key level to watch · nearest resistance and
support · plan of action.

### Shay — VWAP crash course — `dgfQkFSzhiY`, 2023, 43m
**"VWAP is a very key indicator for me — it's the only one I use pretty much."**
She strips the upper/lower bands off and trades the raw VWAP line.

**The VWAP reclaim (her core long trigger):**
1. Stock breaks below VWAP, fails a reclaim once or twice
2. **Mid-day, typically 10:30–11:00**, it breaks back above
3. Confirm with **higher lows** on the 5-minute *and* **rising buying volume**
4. Enter on pullbacks

She notes the **third or fourth** reclaim attempt is often the one that works —
prior failures are not evidence against.

**The mirror (weakness):** repeated failed retests of VWAP *from below*, VWAP now
acting as resistance, with selling volume increasing into the close. Sellers in
control; no long.

**The short trap — most useful piece here.** Higher lows forming **below** VWAP,
around midday/lunchtime, on **low volume**, is a trap for shorts. It resolves as
a reclaim and a breakout. Her own stop-out example is exactly this shape.

> **Time-of-day convergence worth testing.** Shay puts the VWAP reclaim at
> **10:30–11:00**. Steven independently puts the first-red-day *low* at **10:30**.
> Two unrelated sources, opposite sides of the trade, same clock. Our intraday
> work already intends to look at time-of-day effects — this is a specific
> hypothesis to test rather than a general sweep: **is there a structural
> reversal window around 10:30 ET on high-RVOL small caps?**

**Directly relevant to MCL** — VWAP already carries our trailing logic, and the
"higher lows below VWAP on falling volume" pattern is codeable: swing-low
sequence + VWAP relation + volume trend. Worth checking whether MCL's exits fire
inside this pattern.

### Shay — stock selection, gappers, entry timing — `VDN4jp4Uf1k` /
### `cgf0FjzdsKg` / `ZjTYNf4-tpc`
Grouped: heavy overlap, one strong idea between them.

**Overnight gapper scan (large cap), `VDN4jp4Uf1k`:** price $5-400 · change from
close **≥2%, no cap** · **float ≥10M minimum** · market cap ≥$1bn · pre-market
volume ≥20,000 (deliberately low, because large-cap gappers don't get real volume
until after the open). Note the float filter here is a **minimum, to exclude low
floats** — the opposite use from ours.

**Frequency observation worth keeping:** "If you only focus on small caps there
will be months you don't see any good gappers; large caps are way more
consistent." → A capacity/trade-count constraint on any small-cap-only system,
ours included.

**Key-level decision rule (binary, codeable).** Mark the daily key level
pre-market. If price **cannot hold** it → short setup. If it **holds and breaks
above** → long, with the next daily levels as targets. Her worked examples: BBIO
gapped +67% but kept losing the $18 daily level → short; AZUL held $5.30 and
broke $5.60 → long.

**Free-tool notes:** Webull and ThinkorSwim have usable pre-market scanners.
Finviz is **15-minute delayed** — she says it's fine for swing/evening planning
but "not all that useful" for pre-market. Relevant if we ever consider it.

---

#### The bagholder thesis (`cgf0FjzdsKg`) — and it converges with Steven

Penny-stock gap-ups are usually **short** setups, and the reason is trapped
supply, not the chart. Look left on the daily for prior gap-downs; everyone
stranded above is desperate to exit at breakeven. A big gap-up hands them the
exit, and they sell into it. Her RNN example: a reverse-split penny stock, +80%
gap on "license/agreement" fluff, heavy bagholders above $10 → short, target the
**gap fill**, risking ~$0.50 to make ~$2.

**Large caps invert it.** A gap on a *real* catalyst (earnings beat, genuine
product news) → long the pre-market high break, or the consolidation once it
proves it holds. A gap on hype with no real catalyst (her example: a recent IPO)
→ short toward the gap fill.

Her unifying question: *who is in this stock, and do they have more incentive to
buy more or to sell?*

> **This is Steven's resistance-vs-float idea arrived at from the chart side.**
> Steven: a level that traded 50M shares on a 3M float has only ~3M possible
> bagholders, so the resistance is weaker than it looks. Shay: find where
> bagholders are trapped by reading prior gap-downs on the daily. **Both are
> modelling trapped supply**; Steven's version is the one that quantifies, and
> therefore the one we can code. Two independent sources landing on the same
> mechanism is the strongest signal in this whole exercise.

Also note RNN was a **reverse-split** penny stock — third mention of reverse
splits as the manufacturing process behind these names.

---

#### Entry timing (`ZjTYNf4-tpc`) — bagholder short, and a session note

Her short entry uses **first red day** as confirmation — **the same trigger as
Steven's headline pattern**, independently. Risk is defined at **pre-market
highs** (e.g. short $11, risk $11.50). She talks in terms of a **supply zone**.

**Session-aware scanning, stated explicitly:** she runs *different scan criteria*
for pre-market, midday, and after-hours — the midday scan is a separate
configuration and after-hours uses **much lower volume thresholds**. → Direct
support for the approach in `session_aware_screening.md`; a practitioner
treating one threshold set across the session as simply wrong.

### Shay — buy-the-dip small-account long — `TzGQE8d0f18`, 2020, 12m
**Read this one because it argues against MCL's entry, with a mechanism.**

**Her three criteria for the "morning panic / dip / bounce" long:**
1. **Parabolic daily chart** — up multiple days with no major pullback (her CLVS
   example: six straight up days after an earnings/guidance beat)
2. **Support drawn from the DAILY chart**, not intraday. Broken resistance
   becomes support. **Stop goes 10-15c *below* the level, never at it** — "if
   you put your stop right at support you're always going to get stopped out."
   She notes daily levels won't align to the cent (her example missed by 7c) and
   should be treated as **zones of supply and demand**, not lines
3. **Bonus: high short interest.** >20% is heavily shorted, **>50% better**
   (CLVS). Trapped shorts must buy to cover on any pullback, so their covering
   plus fresh dip-buyers supplies the bounce volume

**The argument against breakouts — this is the part that matters to us:**

> "Don't buy high-of-day or hold-the-breakout." On **low-float penny stocks**
> breakouts frequently become fakeouts — the name "pops for 10 or 20 cents and
> immediately dumps 50 cents." She calls the risk-reward "often terrible,"
> "not consistent and very risky." She explicitly says breakouts are **more
> acceptable on mid/large caps with higher float**.

**MCL is a low-float small-cap breakout long.** That is precisely the entry she
argues has bad risk-reward, and she gives a mechanism (asymmetric pop vs dump on
thin float) rather than just an opinion.

> **Our own numbers are arguably consistent with her.** MCL win rates: V4 27.2%,
> V7 29.8%, V5 35.0%. Most breakout entries fail; the strategy survives on a
> small number of large winners, not on hit rate. That is what "breakouts often
> become fakeouts" looks like in a P/L table. **It does not make her right** —
> a low-win-rate/high-tail profile can be perfectly sound — but it does mean her
> claim is not contradicted by our data.

**The testable version.** Her setup runs on *the same universe we already screen*
— parabolic multi-day low-float runners — with the **opposite entry**: buy the
morning panic at a pre-drawn daily support level instead of buying the breakout.
Same names, same session, different trigger. **That makes it a clean A/B on our
existing bar cache**, not a new strategy needing a new universe. Arguably the
single most actionable idea to come out of this channel for MCL specifically.

**Secondary notes:** short interest is now flagged by Shay in two separate videos
as a key small-cap variable (>20% / >25%) — we don't currently carry it. Her
worked bounce happens ~10:00-10:30, consistent with the time-of-day cluster
above. Free short-interest sources: shortsqueeze.com and Finviz, both delayed.

---

## 5. Cross-cutting findings

### 5.0 Four sizing frameworks — and they vary on different axes

| Source | Size varies with | Mechanism |
|---|---|---|
| Eduardo | **recent P&L** | discretionary: equity curve up → push, drawdown → cut |
| Evan Schunk | **bankroll** | fractional Kelly, 10-14% of current bankroll, automatic |
| Breitstein | **setup quality** | 10-100× on rare A+ setups; flat otherwise |
| MCL (ours) | nothing | `min(100 shares, 40% equity)` |

**These are not competing answers to one question.** Eduardo and Evan both scale
with *account state* — Evan's Kelly is simply Eduardo's rule made mechanical.
Breitstein scales with *per-trade edge*, which is orthogonal: you could do both.
Before borrowing either, note Evan's 10-14% per trade is aggressive even as
fractional Kelly, and Breitstein's approach is gated on ex-ante edge
differentiation we have not established.

**The win-rate trap — 2 for 2.** Every guest who leads with a headline accuracy
figure has an unexamined or unfavourable reward side.
- **Eduardo:** 77% win rate, risk-reward ~**3:1 against** him (risks 3 to make 1),
  which he volunteers is bad. Breakeven at 3:1 adverse is **75%**. He is running
  on a **two-point margin** — 74% puts him underwater regardless of setup
  quality. He also discloses a **40% drawdown over three weeks** while scaling
  size. Those are the same fact. The "$1.9K → $1M" framing hides it.
- **Capablanca:** states 90% (Business Insider verified), then when asked
  directly about risk-reward at 1:06:08 says he isn't looking at exact numbers.

→ **Rule for this exercise: a win rate without a paired reward figure is not a
result.** Compute breakeven `p = R/(R+1)` before treating any of it as an edge.

**The two systematic guests disagree on float**, and our own data sides with
neither cleanly:
- Quant (#2): filters to a **1M-2M float band**
- Systematic (#3): **penalises sub-1M float** as dangerous
- **Our V4:** the standout winners were the *thinnest* names — WVVIP (+$458,
  +783% session) at ~3,080 shares per 30s bar, ADXN (+$272). The 6,000-share
  floor removed ~$872 of winners against ~$115 of losers, because a share-count
  threshold penalises exactly the names the strategy exists to find.

**Eduardo's extension cap contradicts our screen.** MCL ranks on top-2 pre-market
gainer — selecting the *most* extended. He caps extension for longs. We have
evidence against him, not the other way round.

**Float rotation is probably not computable for us.** His float-rotation test and
the ×7 multiplier both need pre-market volume, and `consolidated_volume_gap.md`
puts EQUS.MINI pre-market capture at **1.5% median, p05 of 0.0%**, with a quarter
of symbol-days showing nothing. Same gap that made the pre-market RVOL gate
unusable. Note his formulation does sidestep RVOL's contaminated denominator by
comparing against float instead — but only with a tape that sees pre-market.

---

## 6. Next — 13 videos extracted (2026-09-09)

**Ranked by what would actually change our work:**

1. **Dip-buy vs breakout A/B on MCL's existing universe.** Her three criteria
   (parabolic daily · daily-derived support zone · short interest >20%) define an
   entry we can test on the *same names and same bar cache* we already have.
   Cheapest high-value test on this list, and it targets MCL's core assumption.
2. **Resistance-vs-float trapped-supply filter.** Two independent sources
   (Steven quantitatively, Shay from the chart). Best-corroborated idea here.
3. **Audit every screen for filters on nullable fields.** Live selection bug,
   demonstrated on camera.
4. **Move MC5 up the queue.** Built, 27 tests passing, never run on real data.
5. **Test the ~10:30 ET reversal window.** Now three converging mentions:
   Shay's VWAP reclaim, Steven's first-red-day low, her dip-buy bounce.
6. **Check whether our features predict outcome *magnitude*.** Breitstein's
   precondition for variable sizing; decides whether MCL's flat sizing costs us.
7. **Pin the gap-fade definition** (below open vs red on day) before backtesting
   the ~80% claim.
8. **Consider carrying short interest** — flagged by Shay in two videos as a key
   small-cap variable; we don't have it.
9. Session-aware scan thresholds; steal the watchlist format.

**Not actioned, deliberately:** first-red-day short and bagholder short are both
short-side — gate on `short_selling_feasibility.md` and
`ibkr_small_cap_restriction.md`.

**Channel status — effectively exhausted for our purposes.**
- All 14 Tier-1/Tier-2 podcast episodes swept; 5 extracted, 9 ruled out
- 8 of Shay's own videos extracted
- **Negative result:** the penny-stock gap-up *long* video she promises in
  `cgf0FjzdsKg` does not appear to exist. Best candidate
  ("GAP UP TRADING STRATEGY — Golden Setup", `n-SEsjdZaMo`) is large-cap: one
  float mention contrasting *against* low floats, **zero** mentions of "penny."
  Ruled out with two free searches, no transcription.
- Remaining unread: ~24 Tier-3 podcast episodes (options/investing/mindset),
  four playlists (§3), and the long tail of ~950 mostly-Shorts. Later videos were
  producing overlap rather than new claims — expect low yield.

**Method is reusable for the next channel — see §1 and §2.**
