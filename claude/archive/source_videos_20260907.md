# Ten source videos, read 2026-09-07

Each video was read in full and reported on independently before anything below
was written, so the disagreements are the sources' and not a summary artefact.
Same method as `orb_strategy_spec.md` §1.

> **Addendum 2026-09-09: an eleventh video was added at §7.** It is from the same
> channel as videos 1 and 2 and it is the only source in this file with genuine
> published evidence behind it. Read §7's health warning before using it.
>
> **Addendum 2026-09-14: §8 adds an independent backtest of video 9.** It is not
> a twelfth strategy — it is a test of one already in this file, and it retires
> that source. Read it with §2.6.
>
> **Addendum 2026-09-15: §9 adds a second, much longer video from the same
> practitioner as video 7.** It is the only source in the collection whose track
> record has been checked against a primary register and found to be real.
> Read it with §2.5. It also carries a correction to §3.1 and §6 item 3.
>
> **Addendum 2026-09-16 (later): §12 adds the one source in this file that has
> produced a spec.** See `ma_trend_spec_20260916.md`. Its components are all
> already-measured features; what is new is the *shape* of the test it implies.
>
> **Addendum 2026-09-16: §10 and §11 add two channels assessed and rejected.**
> §10 (Percoco) carries the only large independent test of ICT/SMC concepts
> found anywhere — **0 of 648 variants beat buy-and-hold**. §11 (Graystone)
> adds a **fourth vote to the stop-placement conflict in §8.5**, which the
> table there now reflects.

**Three findings dominate, and the first two are unusual enough to lead with.**

1. **This source set falsifies itself internally, and it has now done so
   twice.** *(a)* Videos 2 and 4 both teach Donchian(96) + Larry Williams Trade
   Index(25) + Volume MA(30) on 5-minute charts. Video 2 sells it on two
   hand-picked winning charts. Video 4 backtests it over 100 trades and reports
   **30 winners, 70 losers, −10% net, profit factor 0.857** — and two
   "improved" filtered versions came out *worse*. *(b)* **2026-09-14:** video
   9's trend-line method was independently coded and backtested across seven
   instruments over five years by a source outside this set, and **not one was
   consistently profitable** (§8). Two of the eleven strategies here are now
   refuted by evidence that arrived through the same channel that sold them,
   and that is worth more than any rule in the set.
2. **Zero of the ten trade this project's universe.** The ORB set managed two
   of ten. This set is: not stated (×3), EUR/USD, crypto, DAX and oil, NQ/MNQ
   futures, platinum futures, gold and Bitcoin, and one general US equity scan
   with a liquidity floor and no price or float rule. **Nothing here is about
   $2–20 low-float small caps in pre-market.** That makes the universe question
   Ben raised the central one — see §5.
3. **Every practitioner in this set risks 0.2%–6% per trade. The compounding
   study in this project models 60%.** Nill: "I never risk more than 1%… often
   0.2%." Tori: 2–6%. Creamer: a fixed $100. That gap is three orders of
   magnitude in sizing philosophy and it deserves more attention than any entry
   rule below.

---

## 1. The set

| # | Video | Channel | Instrument | Signal TF | Sells |
|---|---|---|---|---|---|
| 1 | MACD Strategy [86% Win Rate] | TradingLab | **not stated** | **not stated** | paid indicator, Discord |
| 2 | The Strategy That Made Him $1.1M | TradingLab | **not stated** | 5m | paid indicator, premium signals |
| 3 | John Bollinger on Bollinger Bands | MetaStock | US equities (7,000-name scan) | daily | $49/mo toolkit, $249 system |
| 4 | Larry Williams Strategy Tested 100× | TradeSmart | EUR/USD | 5m | Patreon scripts |
| 5 | Volume Profile Is 10× Better | Trading Notes | **not stated** (futures-flavoured) | **not stated** | platform affiliate, email capture |
| 6 | AI Trading Bot, Even Better | DaviddTech | crypto (BTC/USDT) | 1h | paid Skool community |
| 7 | Patrick Nill, Exact Strategy | IQCapital | DAX, oil | 15m | prop challenges, academy |
| 8 | Won the World Trading Championship | Thraxx | NQ / MNQ | 5m + footprint | prop firm, webinar funnel |
| 9 | Simple TREND LINE Strategy ~~— **RETIRED 2026-09-14, see §8**~~ | Humbled Trader | platinum futures | **4h only** | host's scanner |
| 10 | Best 9 & 15 EMA Strategy | Trading Data | gold, BTC | 5m / 15m | **nothing** |
| **11** | **I Stole a Trading Strategy Worth $60 Billion** | **TradingLab** | **US equities (one name)** | **daily** | **Telegram funnel** — see §7 |
| **12** | **I Backtested Tori Trades' Strategy** | **IRONCLAD TRADING** | **7 instruments** | **1h–4h** | **paid community, Telegram** — see §8 |
| **13** | **12x CHAMPION Reveals His "3-TOUCH" Strategy** | **IQCapital** | **DAX, oil** | **15m** | **$9 prop challenge, Discord** — see §9 |

Video 10 is the only one in the set with no product attached. Video 3 is the
only primary source — John Bollinger presenting his own indicator — and it is
also the only one that makes **no performance claim of any kind**.

**Video 9 is retired.** It is kept in the file because §8 is only legible
alongside §2.6, but nothing in it should be built. Video 12 is not a strategy
source; it is the test that retired video 9.

**Video 13 is the same practitioner as video 7**, at 51:38 against video 7's
short cut, and it is the only source here whose credentials were checked
against the primary register rather than repeated. See §9.

---

## 2. What the sources actually say

### 2.1 The Larry Williams pair — a strategy and its own refutation

Both videos specify the same three indicators, and video 4 quotes video 2's
settings almost exactly:

```
Donchian Channel      length 96          (96 five-minute bars = 8 hours ≈ one session)
Larry Williams Trade Index (Loxx)  period 25, smoothing 20
Volume with MA        MA length 30
```

Long: price makes a new 96-bar high against the upper band, LWTI green, volume
above its 30-MA. Stop at the Donchian midline — or, in video 4's objectified
version, "the midline **or** the lowest of the last 10 candles, whichever is
closer to entry." Target 2R.

**The results, from the video that tested it:**

| version | trades | W/L | net | profit factor | win rate |
|---|---:|---|---:|---:|---:|
| basic | 100 | 30 / 70 | **−10%** | 0.857 | 30% |
| + resistance filter | 82 | 23 / 59 | −13% | 0.78 | 28% |
| + break filter | 61 | 19 / 42 | −4% | 0.905 | 31% |

Every figure reconciles arithmetically (30×2 − 70 = −10; PF = 60/70 = 0.857),
which means "net %" is a sum of R-multiples at an unstated 1% risk per trade.
The tester's own conclusion: "in this form this strategy is useless," and
"surprisingly the filtered version which should have made the strategy better
actually made it even worse."

**What the test does not report: any drawdown figure, any calendar dates, any
starting or ending balance, and any treatment of spread or commission** — on a
5-minute FX system where costs would be decisive against a PF of 0.9. Its own
description says "Used Paper Trading" while the video says backtest. So the
refutation is itself weakly evidenced; it is enough to stop us building the
thing, not enough to quote as a measurement.

**The $1.1M attribution does not survive contact either.** Video 2 credits
Larry Williams turning $10,000 into $1.1M in 1987 — then admits the rules are
its own reconstruction, "scavenging the internet for the strategy he used,"
with no citation. And $10,000 → $1,100,000 is +10,900%, not the "11,300%"
stated. The number attaches to a person, not to the rules taught.

### 2.2 Bollinger — the only primary source, and the only one claiming nothing

Settings, verbatim: Bollinger Bands **length 20, ±2 standard deviations**
("start with the defaults and only adjust them if you really need to"); trend
read from a **21-period moving average** used for slope, explicitly *not*
crossovers; volume against its **50-period MA**; **%b** = (price − lower) /
(upper − lower); **BandWidth** = (upper − lower) / middle, compared against its
own extremes over a **125-bar** window.

- **Squeeze** = BandWidth at its 125-bar low. **Bulge** = at its 125-bar high.
  "A squeeze is where trends are born and a bulge is where trends go to die."
  The squeeze is **direction-agnostic** — his own examples show one preceding a
  downtrend.
- **Method 3** (the only method he specifies): a tag of the lower band
  accompanied by a *positive* reading from a volume indicator (Bostian's
  Intraday Intensity, 21-period). Divergence, not agreement.
- **The one timing mechanic in 66 minutes**: "we then **wait one day**… so this
  first day up after the tag low is actually our buy signal." Buy *alert* and
  buy *signal* are deliberately separated by a bar.
- **W bottom**: a new absolute price low that is **not** a new low relative to
  the bands, confirmed by %b divergence, BandWidth turning down, and a volume
  spike on the first low.

**No stop rule and no target rule are stated anywhere in the video.** When
asked directly, he routes it to the paid product: "the methods, the kit and the
system actually do come with stops." He spends the opening ten minutes arguing
that a 2:1 average-winner-to-loser ratio is a pillar of performance, and then
never defines either leg of it.

Two internal problems his own reader flagged: his spoken %b thresholds for the
W bottom ("below less than one… above one") contradict his own formula, and
**Method 1 and Method 3 issue opposite orders on the same chart event** — an
upper-band tag is a breakout to follow under one and a fade under the other,
with no rule given for telling which regime you are in.

### 2.3 Volume profile — three independent sources converge

Videos 5, 7 and 8 all build on volume-at-price rather than candles, and they
agree on the mechanism even though they share nothing else.

- **High-volume nodes are zones, not lines**, and the entry belongs at the
  **edge** of the cluster, not at the point of control. Video 5's stated reason
  is concrete: "price would react just before reaching that exact line… you
  would sit there with your order resting at the perfect level, watching a
  profitable move take off without you."
- **Stops belong in the low-volume area beyond the node** — "stop-loss goes
  behind a barrier, take profit goes before a barrier." If price traverses a
  thick volume wall, the idea is wrong, which is a structurally different stop
  rationale from a percentage or an ATR multiple.
- **First touch only.** "You strike on the first contact, not the fifth."
  Subsequent retests decay as trapped participants exit.
- **Low-volume areas are traversed fast**, high-volume areas slowly. Nill:
  "here are all in freedom. There is nothing. But if we go down here, it goes
  faster."
- Video 8 anchors a **fixed-range profile to the swing pair that produced the
  impulse** and extends it forward, defining premium and discount for that leg
  specifically — rather than using a session or daily profile.

Video 5's one genuinely mechanical rule, and the only backtestable claim in it:
**price opens outside the prior RTH session's value area, re-enters it with
actual candle closes inside (not a wick), and then travels to the opposite
extreme of that value area** — "the vast majority of the time." No sample, no
instrument, no period is given.

### 2.4 The 9/15 EMA video — a crossover with a momentum veto

Directly comparable to this project's existing EMA work, so stated precisely.

- **EMA 9 and EMA 15 on the signal timeframe.** No higher timeframe anywhere.
  **Price source is never stated** — he sets length and colour only.
- **Stochastic Momentum Index at 7 / 2 / 2**, not the 10/3/3 default.
- **The trigger is a crossover, not a pullback**: "The EMA crossover is our
  entry… We only use the SMI to tell us whether that EMA crossover is worth
  taking or worthless." Entry on the **close** of the candle that closes beyond
  both EMAs.
- **The veto is a momentum ceiling, not a floor.** Take the cross if SMI is
  rising and below +60 (sweet spot +40 to +60, lower-and-climbing is stronger);
  **skip it if SMI is already above +60 and flattening, "no matter how clean
  the crossover looks."**
- **The thesis, and it is the interesting part:** in a strong trend a pullback
  only takes the oscillator to about −20 and never reaches oversold. "If you're
  sitting there waiting for minus 80 in a trend like this, you will never take
  a single trade." A deep −80 print is read as sellers *in control*, not
  exhausted.
- Stop: just beyond "the low of the candle right before our entry" — the bar
  *before* the signal bar, not the signal bar.
- **No exit rule of any kind.** Both examples are narrated to an outcome
  ("around 30 points", "several hundred points") with no rule that would have
  produced it. **The strategy as stated is not backtestable.**

Its reader also caught that the regime gate and the trigger contradict each
other: longs require EMA9 already above EMA15 with clear separation, but the
entry is the instant of the cross, when by definition there is none. In
practice "separation" functions as a chop veto, and it is never quantified.

### 2.5 The two discretionary practitioners

Nill (video 7) and Creamer (video 8) both say plainly that their entries are
judgement calls. Nill: "I am totally a discretionary trader… that's many years
of experience." Creamer treats the entry as trivial — "the last 5 to 10% of the
trade" — and puts the work in context and location. Neither states a stop
placement rule; Creamer states a **dollar** stop ($100) with no rule for where
it sits.

What is worth extracting from them is not entries.

**Creamer's gamma regime gate** is the most novel idea in the set. Before
looking at a chart he marks the call wall, the put wall and the gamma flip
level, and uses net gamma sign to decide *what kind of day it is*: "Above it,
in a positive gamma environment, moves could tend to be dampened… below it,
they can get amplified." In the example, being under the flip with negative net
gamma switched off his mean-reversion behaviour entirely — "this is not going
to be a day where I fade every extension at the open and expect a snapback."
That is a state variable, it is testable, and no strategy in this project has
any regime gate at all.

**Creamer's pyramiding rule** is more disciplined than the version this project
already rejected: never add to a loser, add only on pullbacks after the idea is
proven, and **only while the blended entry still allows the stop to be moved to
break-even**. His reader's caveat is correct though — between placing an add
and moving the stop, open risk exceeds the stated $100, and he gives no
add-size rule, no maximum number of adds, and no minimum favourable excursion.

> **See §9.** A second, far longer video from the same practitioner was read on
> 2026-09-15. It contains the structural model this section could only gesture
> at, a verified competition record, and **a contradiction of the win-rate
> figure quoted below**.

**Nill's risk numbers** are the most useful thing either of them says: 0.2–1%
of his own capital, 2–3% only in competition, where "you need at least 100 or
200% that you will be seen." He pairs a 50–60% win rate with "sometimes I have
10 to 20 losses after each other," and gives that as the *reason* for the
sizing rather than as a boast. Drawdown tolerance: 10% preferred, 20% the
ceiling — "20% is the maximum you can live."

### 2.6 Tori Trades — a trailing stop with no target

> **Retired 2026-09-14.** This method has since been coded and backtested
> independently across seven instruments and five years, and it does not work.
> **Read §8 before using anything below.** The section is kept because §8 only
> makes sense against it.

Platinum futures, **4-hour chart exclusively**, 8–9 trades a year.

- Two hand-drawn trend lines are maintained at all times, bullish and bearish.
  The one that breaks is the **"action line"**; the opposing one becomes the
  **"safety line"** the position is then trailed against.
- **A+ checklist**: three touch points, **spread over at least a week's worth
  of data** ("it can't have three touch points within the past three days"),
  and the break must occur **close to the opposing trend line** so the setup is
  low-risk.
- **The stop is the opposing trend line and there is no take-profit at all.**
  "I don't have a take-profit… when it breaks that, all right, transaction's
  closed." R:R is unknowable at entry by design.
- **Position size normalises the variable stop distance**: close to the safety
  line, full size (20 contracts); far away, half size (10). This is the most
  transferable idea in the video and it is nearly mechanical.
- Risk 2–6% of an account size she never states.

She is candid that she does not follow her own exit rule — "I have clipped out
of most of my trades early because we're up 30,000, close it" — which means the
reported P&L was not produced by the stated strategy. Her two catastrophes
(gold, Ethereum at −$30,000 unrealised, closed at +$48) both involved removing
or ignoring the stop and both were rescued by price retracing, which she twice
attributes to luck.

### 2.7 The AI bot video — not a strategy, and the most immediately useful

Video 6 is an automation pipeline: Claude Code with MCP servers generates Pine
Script strategies on a loop, backtests them, and the operator pastes the
survivors into TradingView, which alerts a webhook that places orders on Bybit.
The strategy content is nil — entries are whatever the model invents.

**What it carries that this project lacks entirely is strategy retirement.**

- The equity curve is bracketed by standard-deviation bands and **"if my equity
  curve goes below the lower standard deviation, I will turn off my bot… that
  is the ultimate stop that bot."** Plus rolling win rate and rolling profit
  factor to detect edge decay, plus abnormal loss streaks.
- **Incubation**: a strategy that passes backtest is *held*, not traded, and
  only goes live if forward data on unseen bars matches. He shows a two-year
  forward segment.
- **"Expect 99% of them to fail when you put them into live trading. I've
  backtested thousands and I'm currently trading only seven."**
- **Never run one bot.** Diversify across strategies.
- **No trailing stops**, for an infrastructural reason rather than a
  performance one: webhook latency means "by the time it gets to your broker,
  the position has completely changed."
- Automation asymmetry: the model may switch a bot **off** automatically;
  turning one back on stays a human decision.

The honest part of the video is that its own headline bot round-tripped its
gains — "I pretty much round tripped this trading bot" — because he had these
rules and ignored them.

---

## 3. What is genuinely new to this project

| Idea | Source | New? | Testable on data we already hold? |
|---|---|---|---|
| **Strategy retirement rules** — SD bands on the equity curve, rolling PF and win rate | 6 | **Yes, entirely** | Yes — from any backtest's trade list |
| **Incubation before going live** | 6 | **Yes** | Yes, and directly applicable to MC5 |
| **Volume profile levels** — HVN/LVN, value area, POC | 5, 7, 8 | **Yes** | **Yes** — derivable from the minute bars in `bar_cache_db`, no new feed |
| **Value-area re-entry rule** (open outside, close inside, target far extreme) | 5 | **Yes** | Yes, and it is the only fully mechanical rule in the set |
| **Gamma regime gate** (net gamma sign, flip level, call/put walls) | 8 | **Yes** | **No** — needs options open-interest data we do not have |
| **BandWidth squeeze as a volatility regime** | 3 | **Yes** | Yes, from daily bars |
| **"Wait one bar" after the signal** as an odds filter | 3 | **Yes** | Yes — cheap to add as a cell to any existing strategy |
| **Momentum ceiling veto** (skip a valid cross when the oscillator is spent) | 10 | **Yes** | Yes — MCL already has `REQUIRE_MACD_POSITIVE`; this is its mirror image |
| **Inverse-volatility position sizing** | **11** | **Yes** | **Yes** — see §7 |
| **Multi-horizon agreement as a scalar** | **11** | **Yes** | **Yes** — see §7 |
| **Mechanism test: add the filter the method claims to embody and see if anything changes** | **12** | **Yes** | **Yes** — see §8.3 |
| **Adherence audit as the first retirement gate** — was it the edge, or was it us? | **13** | **Yes** | **Yes** — see §9.4 |
| **Required R conditioned on the bucket's own hit rate** | **13** | **Yes** | **Yes** — see §9.4 |
| **Stop granularity chosen by distance to target** | **13** | **Yes** | Yes — a grid cell |
| **Per-instrument standdown rather than a global kill switch** | **13** | **Yes** | Yes |
| Trend-line trailing stop, no target | 9 | **No — tested and refuted** (§8) | — |
| Size used to normalise stop distance | 9 | Partly | Yes |
| Pyramiding into winners | 8 | **No — tested and rejected** (`mcl_parameter_decisions.md`) | — |
| MACD cross + 200 MA trend filter | 1 | No — MCL already uses MACD with a trend condition | — |
| Donchian + LWTI + volume | 2, 4 | Yes, and **refuted in this very set** | Not worth the bars |

### 3.1 The three worth acting on

**Strategy retirement, and it is overdue.** MC5 is the only surviving candidate
and there is no rule anywhere in this project for when to stop trading it. The
SD-band construction is simple, computable from a trade list, and it answers a
question we will face within weeks rather than months. Nill's drawdown numbers
give the thresholds a sanity check: 10% preferred, 20% the ceiling. Note the
compounding study measured MC5's in-sample max drawdown at **77.4%**.

**Volume profile, because the data is already on disk.** `bar_cache_db` holds
three full sessions of 1-minute bars for 25,769 symbol-days. Volume at price,
value areas, POC and high/low-volume nodes are all computable from that with no
new feed and no cost. Three unrelated sources in this set converge on the same
mechanism, which is the only convergence in the set. Whether small-cap gappers
build meaningful volume profiles at all is an open question and a cheap one to
answer — a measurement before a strategy.

> **Corrected 2026-09-15, and the correction is severe.**
> `consolidated_volume_gap.md` measured EQUS.MINI's tape capture at **4.7% of
> prints at the close and 1.5% before the open**, with p05 of **0.0%** at every
> pre-market cutoff and 26% of symbol-days carrying no pre-market reading at
> all. A volume profile is a distribution of volume across price; **built from
> 1.5% of prints, drawn from a venue subset rather than at random, it is not
> one.** The regular-hours shape may still survive sampling and is worth
> measuring. **The pre-market shape almost certainly does not — and 04:00–09:30
> is the window MCL and MC5 trade.** Run the measurement, but expect it to come
> back negative in the session that matters, and do not design around a value
> area until it comes back positive.

**The "wait one bar" filter**, because it is nearly free. Bollinger delays entry
by one bar purely to shift the odds. MCL and MC5 both enter at the next bar's
open after a signal; a variant that waits one more bar is a one-line change and
a single grid cell. It may do nothing. It costs almost nothing to find out.

### 3.2 The one that needs data we do not have

The gamma regime gate is the most interesting idea in the set and it needs
options open interest by strike, which no Databento tier in this project's plan
carries and which does not meaningfully exist for $2–20 small caps anyway.
Recorded, not actionable.

---

## 4. What this set says about evidence

Applying the standing rule that source videos are hypothesis generators:

- **Two of ten give any performance statistics.** Video 4 gives full trade
  counts and profit factors for three variants and reports **no drawdown, no
  dates and no balances**. Video 10 gives two chart outcomes and no statistics
  at all, and — unusually — over-claims nothing.
- **Six of ten specify no exit rule, no target, or no stop.** Bollinger states
  neither stop nor target in 66 minutes. Video 10 states no exit at all. Video
  8 states no stop location and no target. Video 5 has two mutually
  inconsistent target rules and demonstrates only one.
- **Every worked example in the set is a winner**, including in the video whose
  own measured win rate is 30%. Video 4 says so explicitly: "of course these
  were cherry-picked examples."
- **Three titles are not supported by their own content.** "86% Win Rate" is
  never mentioned in the video body. "NEVER Read Candlesticks Again" describes
  a strategy whose trigger is a doji, hammer or shooting star. "$100K A Year" is
  the host's number; the guest says "hundreds of thousands."
- **The strongest source claims the least.** Bollinger makes no performance
  claim at all, and the only video with no product attached (10) is also the
  only one that repeatedly tells the viewer to test before risking money.
- **Neither of the two videos that ran a backtest priced friction** (§2.1,
  §8.4). Both nonetheless reached the right sign, because both results were
  losses — friction only makes a loss worse. That is luck, not method: had
  either come out marginally positive, the omission would have been decisive.

---

## 5. The universe question

Ben offered to adjust the universe to suit a strategy. This set makes that a
real decision rather than a hypothetical, because **none of these ten
strategies is about the universe this project is built for.**

**What changing the universe would cost.** The entire measured infrastructure —
the Databento archive, `common/screen.py` and its 22,882 candidate symbol-days,
`bar_cache_db`, the commission model, the crossing-cost measurement on 18,552
real fills, the leakage control — is specific to US small-cap equities. A move
to futures or FX invalidates the cost measurements, the screen, and the entire
bar cache, and there is no equivalent archive on hand.

**What it would buy.** Access to instruments where these methods were actually
developed. Volume profile on NQ is a different and better-behaved object than
volume profile on a $3 stock that gapped 300%. Futures have no borrow problem,
no SSR, native stops around the clock, and no split-adjustment trap.

**The honest reading of where this project is.** MC5 is the only strategy that
has ever cleared drop-top-5, it did so on the small-cap universe, and its
result currently hangs on an execution question (`screened_universe_results.md`
§3.2) rather than on the rules. Switching universes now would abandon the one
positive result the project has, and would do so in favour of strategies whose
best-evidenced member in this set was measured at a profit factor of 0.86.

**So the recommendation is: do not change the universe yet.** Settle MC5's
execution question first — it is days of work, not weeks. If MC5 dies on order
count, the case for changing universes becomes strong and this doc is where to
start. If MC5 survives, the three items in §3.1 are all buildable on the
existing universe with the data already on disk.

---

## 6. What to do with this, in order

1. **Nothing here changes MC5's priority.** `screened_universe_results.md` §6
   item 1 stands: measure orders per round trip and settle whether IBKR bills
   per order or per execution.
2. **Build strategy retirement rules** (§3.1). They are needed before MC5 goes
   to paper regardless of what else happens, and nothing in this project has
   them.
3. **Measure whether volume profile is meaningful on this universe** before
   designing anything around it — value area width, POC stability, whether
   high-volume nodes are revisited at all on low-float gappers. A measurement,
   not a strategy. The bars are on disk. **Read the §3.1 correction first:
   pre-market tape capture is 1.5%, so the measurement should be run
   regular-hours and pre-market separately and is expected to fail in the
   pre-market window.**
4. **Add a "wait one bar" cell** to the MCL and MC5 grids. One line, one cell.
5. **Do not build** the Donchian/LWTI strategy. It was tested inside this very
   source set and lost money in all three versions.
6. **Do not build** the trend-line strategy either. Same reason, arrived at the
   same way — see §8.
7. **Build the adherence audit** as the first gate of the retirement rules in
   item 2, before the equity-curve band — §9.4. It is a few lines and it is the
   difference between retiring a working strategy and retiring a broken
   operator.

---

## 7. Addendum, 2026-09-09 — video 11, and it inverts this file's usual problem

**"I Stole a Trading Strategy Worth $60 Billion"** — TradingLab, `JRRc63tUdy8`,
10:51, published 2026-08-24. **Read in full 2026-09-09.**

Same channel as videos 1 and 2, both of which are among the least reliable
sources in this file. **This one is different in an instructive way: the
underlying strategy has more published evidence behind it than anything else in
the set, and the video's own demonstration of it is worthless.** Those two facts
need to be held apart.

### 7.1 The strategy, as stated

A **multi-horizon time-series momentum** system on daily bars, rebalanced weekly.

**Signal.** Score four trend lines, each ±1 — today versus 1 week ago, 2 weeks
ago, 1 month ago, 2 months ago. Up = +1, down = −1. Sum them. The score can
therefore only take five values:

| Score | Position |
|---|---|
| **+4** | fully long |
| **+2** | half size long |
| **0** | no position |
| **−2** | half size short |
| **−4** | fully short |

Re-score every week and adjust. That is the entire entry model: **a count of how
many of four lookback horizons agree on direction.**

**Sizing.** `position size = score × target risk ÷ volatility`.

- *Target risk* is chosen by the trader (his example: 10% of a $100k account).
- *Volatility* is the average daily percentage move over 30 days, annualised.

Higher volatility → smaller position. He gives the analogy directly: a long
leash for the calm dog, a short leash for the dangerous one.

**There is no stop loss anywhere in the strategy.** Risk control is entirely
position sizing plus the weekly re-score.

### 7.2 What it is actually a retelling of

He credits **Man AHL** (founded 1987, ~$60bn). The specific claims — data back
to **1880**, ~140 years, **positive in every decade**, dozens of markets — are
the signature of **"A Century of Evidence on Trend-Following Investing"**
(Hurst, Ooi and Pedersen), which is an **AQR** paper, not AHL, though Man AHL
publishes closely related work. Attribution is therefore uncertain and the
video's "55-page research paper" is not identified.

> **The lookback horizons do not match.** The paper family uses **1-, 3- and
> 12-month** time-series momentum. His are **1 week to 2 months** — an order of
> magnitude shorter. **The video borrows the paper's evidence for a different
> system.** This is the same defect as video 2's Larry Williams attribution
> (§2.1): a real track record attached to rules that did not produce it.

He raises the obvious objection — "if it's that good, why release it?" — and
never answers it. The answer is standard and worth recording: trend-following is
a capacity-rich risk premium, not an arbitrage, so publication does not compete
it away the way publishing a mispricing would.

### 7.3 Three arithmetic problems, and the third is the one that matters here

1. **He annualises with 19.1 = √365.** For an equity trading ~252 sessions a
   year the factor is √252 ≈ 15.87. √365 is the calendar-day (crypto)
   convention, and he applies it to Charles Schwab.
2. **He uses the average absolute daily move, not the standard deviation.**
   These are different statistics. For normally distributed returns, mean
   absolute deviation ≈ 0.798σ.
3. **The two errors run opposite ways and very nearly cancel** — his figure
   lands within about 4% of a correct σ√252. **So it is approximately right for
   the wrong reasons, and the approximation depends entirely on returns being
   normal.**

> **On our universe that cancellation fails.** The MAD ≈ 0.798σ relationship is
> a normal-distribution result. `$2–20` names moving 50–800% in a session are
> about as far from normal as equities get, and the fat tail is precisely where
> the two errors stop offsetting. **If inverse-volatility sizing is ever tested
> here, compute σ properly; do not copy the video's shortcut.**

### 7.4 The demonstration tests nothing

One trade: SCHW, $60,000, entered at a +4 score, closed about a month later at
+12% (+$7,200).

**He closed it discretionarily "at the all-time highs", not on a score change.**
The strategy says re-score weekly and adjust; he did not. So the $7,200 was not
produced by the stated strategy — **the same failure as Tori Trades in §2.6**,
and it is now two for two in this file that a demonstrated P&L came from
deviating from the demonstrated rules.

Also note the risk architecture does not survive the transplant. A system with
no stop loss is coherent for a fund holding **58 markets simultaneously**, where
diversification is the risk control. **Applied to a single name it is not the
same strategy**, and the video never acknowledges the difference.

### 7.5 What actually transfers

Nothing as a strategy — daily bars, weekly rebalancing, multi-asset, long
horizon, the opposite end of every axis from pre-market small-cap scalping. Two
ideas transfer, and neither carries a parameter with it:

**Inverse-volatility position sizing.** MCL sizes flat at 100 shares.
`sizing_and_capacity.md` found capital-based sizing can flip a strategy's sign
(+$0.33/trade flat-100 → −$6,158 at 60% of $5,000 buying power). Inverse-vol
sizing is a **third** option that neither of those tested, and it is the only
sizing framework anywhere in this project's source material with published
long-horizon evidence behind it rather than a practitioner's habit. Note it
points the opposite way to Breitstein's exponential sizing, which scales *up* on
conviction; this scales *down* on volatility. **They are not the same axis and
could both apply.**

**Multi-horizon agreement as a scalar.** Counting how many lookbacks agree and
**sizing on the count** rather than gating on a boolean is the **fifth
independent instance of rank-don't-gate** in this project's source material,
after the `oSznkl4ASaA` guest's ADF score, Shay's colour-coding, Cameron's
A/B/C rubric and his deliberately-wide scanner filters
(`warrior_0_universe_and_risk.md` §1). **Every screen we run gates.** Five
independent sources arriving at ranking is now the best-corroborated
architectural claim in the whole collection, and we have never tested it.

### 7.6 Standing on this source

**Treat the strategy as worth a literature check and the video as worth
nothing.** If inverse-vol sizing or multi-horizon scoring is ever built here,
read the actual paper — this retelling has the wrong horizons, the wrong
annualisation, a single-name transplant of a diversified system, and a
demonstration that broke its own rules.

---

## 8. Addendum, 2026-09-14 — video 9 is backtested by an outsider, and it fails

**"I Backtested Tori Trades' Strategy"** — IRONCLAD TRADING, `2T-1REPS-Qk`,
13:45, published 2026-07-10. 60,854 views, 2,723 likes, 719 comments. Sells a
paid community and a Telegram channel. **Read in full 2026-09-14.**

This is the **second internal falsification** in this file. §2.1 was the first:
video 4 tested video 2's strategy and found it lost money. This one is stronger
in one way and weaker in another — **stronger** because it tests seven
instruments over five years rather than 100 FX trades, and because it isolates
the *mechanism* rather than just the P&L; **weaker** because the tester is
selling something and his own conclusion is tuned in-sample. Both halves matter.

### 8.1 What he tested

Tori's top-down trend-line method (§2.6) coded in Python and run over **five
years** on **Bitcoin, ES, NQ, gold, euro, crude oil and platinum**. Stop
distance was swept as a variable rather than fixed. The **three-touch rule was
tested both on and off**, which is the right way to treat a discretionary
checklist item — as a parameter, not a given.

### 8.2 The result

**With the three-touch rule:** *"not one of them was consistently profitable."*
Gold returned **+2%** and NQ **+6%** — over **five years**, i.e. under half a
percent annualised on each. **Platinum — the instrument she actually trades —
loses money.**

**Without the three-touch rule:** only platinum turns profitable, at roughly
**20% over five years** (~3% annualised). His own verdict: *"better to just
leave your money in a bank account."*

Two things follow directly. First, the one instrument the source demonstrates
on is the one instrument that fails her own filter. Second, the filter she
presents as the quality bar (**"A+ setup"**) is inverted by the test on six of
seven instruments — it is not selecting quality, it is selecting a subset.

### 8.3 The mechanism test — this is the part worth keeping

Everything above is a P&L result and could be a coding artefact. What raises
this above §2.1 is that he ran a **causal-mechanism test**, and the logic is
clean enough to steal:

> *"If her top-down trendline itself was actually capturing higher timeframe
> structure, adding an explicit higher timeframe market structure filter
> shouldn't make much difference. The results should have been similar. But
> they were not."*

Returns went from ~20% to **40%+** when an explicit higher-timeframe structure
filter was bolted on. **A filter that is already doing its stated job cannot be
improved much by adding an explicit version of itself.** The improvement is the
measurement: the trend-line was not capturing what it claimed to capture.

His diagnosis: *"The strategy isn't filtering out noise, it's trading the
noise."*

**This construction is new to this project and it is cheap.** We have several
components whose stated rationale is a proxy for something we can compute
directly — RVOL as a proxy for "unusual interest", MACD-positive as a proxy for
"momentum intact", the screen's price band as a proxy for "the kind of name
that runs". For each, the test is the same shape: add the explicit thing the
proxy claims to stand for, and if the result moves materially, the proxy was
not doing the job. Registerable, one cell each, no new data. **Added to §3 as
the only new idea in this addendum.**

He also catches a presentation tell worth recording: she draws on a real chart
for the setup, but *"the moment she gets to the actual entry and exit rules,
she switched to an animation, not a real chart."* An idealised diagram at
precisely the point where a real chart would show slippage, gaps and ambiguity.

### 8.4 What is wrong with his own test

He is not a clean source and the file should say so.

- **No transaction costs anywhere in 13:45.** Not spread, not commission, not
  slippage. On a method whose best result is ~3% annualised, friction is
  decisive. It does not change the sign here — every headline result is a loss
  or near-zero, and costs only make those worse — but the test is not one we
  could quote as a measurement. **Same defect as video 4 (§2.1).**
- **He then tunes in-sample and reports the winner.** *"I tested around 23k
  combinations, and through this, I finally found a strategy that's
  consistently profitable on NQ"* — with **no multiple-testing correction and
  no holdout**. The winner is a **five-way in-sample choice**: 1-hour entry,
  draw only down to 4-hour, drop the three-touch rule, stop exactly on the
  line, and trade NQ rather than platinum. By this project's §4 standards
  (`PROGRAM_INDEX.md`) that is not a result, it is the maximum of 23,000 draws.
- **41% win rate quoted with no paired reward figure.** He does give 11% annual
  return and 14% max drawdown, which is more than most sources here manage, but
  the win rate on its own is the exact pattern `win_rate_and_r.md` documents.

### 8.5 A three-way stop conflict this raises, and it is unresolved

His tuned winner places the stop **exactly on the trend line**, and he reports
it beat placing it beyond the line. That contradicts **two** things at once:

| Source | Rule |
|---|---|
| Tori (§2.6) | stop at the **opposing** trend line, i.e. deliberately far beyond |
| Cameron & Shay (`warrior_4_reversal.md` §2) | **10–15c below the level, never at it** — "if you put your stop right at support you're always going to get stopped out" |
| **Graystone (§11)** | **2 pips beyond the level on the 60m, 4 on the 4h** — a buffer that scales with timeframe, placed *"slightly beyond the crowd"* |
| IRONCLAD (§8.4) | stop **exactly on the line** beat placing it beyond |

**Updated 2026-09-16.** Three independent practitioners now say *beyond the
level*, against one 23,000-combination in-sample winner saying *on it*. **The
practitioners win on evidence quality**, and nothing here should move
`warrior_4_reversal.md` §2.

**And one half of it is now settled from our own data, from the other
direction.** `orb_preflight_RESULT_20260916.md` eliminated `STOP_MODE =
opposite` — the *far* beyond version, which is Tori's — at every range length:
median R of **7.2–10.4% of price** against `MAX_R_PCT` of 12%, p90 16–18%, the
same shape that cost VW9 a month. So "far beyond" is dead on measurement;
"slightly beyond versus exactly on" remains open and is a one-parameter sweep
we could register against our own trade list at any time.

### 8.6 His alpha-decay argument, and the one place it over-reaches

He tests the trend-line method on NQ back to **1999**: strong 1999–2010, and
*"from 2016 onward the edge became extremely weaker."* His general statement is
the sharpest line in the video and it is correct:

> *"The fact that a strategy is 100 years old isn't evidence that it works.
> It's evidence that millions of traders have already tried to use it."*

**But he then uses it to sell**, and it does not generalise as far as he takes
it. The distinction is the one §7.2 already makes: **an arbitrage-type edge is
competed away by publication; a capacity-rich risk premium is not.** Trend
following at 1–12 month horizons has survived 140 years of publication for
exactly that reason. Chart-pattern trend lines on a 4-hour futures chart are
much closer to the arbitrage end, so his decay finding is plausible *for this
method* and should not be read as a general law.

### 8.7 To his credit

Three things separate him from most of this file:

- **He tested a strategy he had no stake in, and published a negative result.**
- *"If you ask me whether I actually trade this myself, probably not."* He calls
  his own tuned winner *"not that good."*
- He diagnoses **why** the method sits badly: it occupies an awkward middle
  ground between day trading and swing trading — too slow to compound, too fast
  to ride a real trend.

### 8.8 Standing on this source

**Video 9 is retired.** Do not build the trend-line method, and do not carry
forward the "A+ three-touch" checklist as a quality filter — it was tested and
it is not one. The **variable-stop-distance position sizing** from §2.6 is
untouched by this test and survives on its own logic; keep it.

**Video 12 is a method source, not a strategy source.** Take §8.3 — the
mechanism test — and nothing else. Do not take his NQ parameters, his stop
placement, or his 41% win rate.

**And note what just happened to this file.** Of eleven strategies here, two
have now been refuted by evidence that surfaced through the same medium that
sold them, and in both cases the refuting video is a better source than the
selling video. The generalisation worth carrying: **for any strategy in this
collection, search for someone who has tested it before building it.** That
search cost 14 minutes of video and retired a source.

---

## 9. Addendum, 2026-09-15 — video 13, the long cut of video 7, and the only verified track record in the collection

**"12x CHAMPION Reveals His '3-TOUCH' Strategy That Won Robbins Cup"** —
IQCapital, `2hyqdVF0JVk`, **51:38**, published 2026-08-28. 296,164 views, 3,833
likes, 486 comments. **Read in full 2026-09-15** — all 1,206 transcript
segments.

Same guest and channel as video 7, which is a short cut of the same interview
series. This is the whiteboard version and it contains the structural model
that §2.5 could only record as "judgement calls."

### 9.1 The credential, checked rather than repeated

This is the first source in the collection whose record was verified against a
primary register. Patrick Nill appears repeatedly in the World Cup Trading
Championships **historical standings**:

| Year | Division | Place | Net return |
|---|---|---|---:|
| 2022-23 | Global Cup, **Forex** | **1st** | 219.1% |
| 2021-22 | Global Cup, **Forex** | **1st** | 94.5% |
| 2022 | World Cup, Forex | 2nd | 245.7% |
| 2021 | World Cup, Forex | 2nd | 229.2% |
| 2023-24 | Global Cup, Forex | 2nd | 72.2% |
| 2021-22 | Global Cup, **Futures** | 3rd | 94.5% |
| 2020-21 | Global Cup, **Futures** | 4th | 125.7% |

Source: `worldcupchampionships.com/world-cup-trading-championship-historical-standings`,
read 2026-09-15. He does not appear in the year-by-year *champions* list, which
is consistent with his own stated claim (top five twelve times) and not with
the video's title.

**Three observations, and the first is the one that matters.**

1. **The record is overwhelmingly Forex; the strategy taught here is DAX and
   oil futures.** Two futures placings, both outside the top two. The
   credential and the lesson are not from the same asset class, and the video
   never mentions this.
2. **The title inflates.** "12x CHAMPION" versus the intro's "placed top five
   in this competition 12 times." Logged against §4's title-mismatch tally,
   which now stands at four.
3. **The returns are consistent rather than spectacular** — 72% to 246%, where
   outright championship winners in recent years posted 324% to 601%. That is
   *corroborating* rather than damning: it is what a 2–3% competition risk
   budget (video 7) produces, and it is the profile of someone finishing top
   five repeatedly rather than winning once with size.

This is the strongest sourcing in the file. It is still not evidence that the
rules below work — it is evidence that the person describing them can trade.

### 9.2 The model, as far as he states it

**Market premise.** ~70% of days are ranges in which large participants source
liquidity; 20–30% trend. *"70% the markets they are searching liquidity… and
you see here 70% of the days you're in ranges."*

**Structure.** After an impulse, he marks the consolidation zone and labels it
**P / B / D** — market-profile day shapes, **never defined in 51 minutes**.

**Timeframes, and the hierarchy is explicit.** 4-hour for context → **15-minute
for every decision** → 5- or 3-minute *only* for execution. A zone needs *"more
than one day or one day"* to form. He is a swing trader: *"the real nice setups,
they often took two or three days."*

**Two trades out of one structure.**

| | Range trade | Breakout / reclaim |
|---|---|---|
| Entry | limit at the zone extreme | limit into the pullback after the reclaim |
| Trigger | none — the level is the trigger | one candle exits the zone, the next **closes back beyond** it |
| Target | the opposite extreme | next zone, or a **measured move** — *"the initial move I take and copy this"* |
| Partials | *"normally no partials"* | ~30% at 1R to reach break-even, rest runs in multiples of 3 |

**The zone-width conditional, and it is the only near-mechanical rule in the
video.** A **narrow** zone after a **large** impulse is a breakout trade (he
claims R:R ~8). A **wide** zone is a range trade only — *"the breakout trade,
not so much. I wouldn't trade."* Separately, **two zones at the same price on
different days** *"works better."*

**Three touches.** *"I love when it has the third confirmation… I wait very
long because then the probability is bigger for the breakout."* He names the
cost himself: *"sometimes you are not in the market."*

**Stop.** Structure first (zone extreme, or a volume-profile node when he is at
his desk); if no structure, sized so that R ≥ 3. **Position size is then derived
from stop distance** — *"sometimes I have a stop from 30 points sometimes from
200 points and then I decide how many contracts I take."* Same construction as
Tori §2.6, from a far better source, and it survives §8's demolition of the
rest of her method.

**Vetoes.** No new range entries late in the European session, because the
position would be unsupervised overnight — *"you go to bed, you have 8 hours
till you see the market."* Nothing immediately before news. 14:00 CET (US open)
changes character.

**The one non-negotiable: never widen a stop.** *"It's one of my biggest rules…
it's a red flag."* Learned from holding crude into April 2020 without a stop —
*"it falls down till minus 42."*

### 9.3 Why it cannot be built, and the reason is unusual

**He withholds the zone-drawing rules.** Three separate refusals: how a zone is
marked (*"that's in the secrets"*), how it is widened or narrowed as price
develops (*"these rules are secret"*), and further order-flow confirmations.
When asked what would make a viewer fail with the strategy, his own answer
includes *"the drawing, the right zones."*

**Every other source in this file withholds the exit. This one withholds the
input.** Bollinger routes stops to a paid product (§2.2); video 10 states no
exit at all (§2.4). Those are strategies with a hole at the end. This is a
strategy with a hole at the *beginning* — the zone is the object from which
entry, stop, target, size and the range-versus-breakout choice are all derived.
Nothing downstream of it is specifiable, and unlike §8 there is no independent
tester to fall back on.

No transaction costs, no sample, no dates, no backtest anywhere in 51:38. The
60–75% win rate is recollection.

### 9.4 What transfers anyway, and one of these is the most useful thing in the file

**(a) He states the breakeven identity, unprompted, and is the first source in
the collection to quote a win rate with its reward figure attached.**

> *"The win rate, it doesn't matter so much, because when you have a risk
> reward from three or four then the win rate is not so important."*

60–75% at R ≥ 3, profit factor target ~2. `win_rate_and_r.md` documents ten
project docs reporting a win rate with no paired R; this is external
corroboration of that document's central argument from a verified practitioner,
and it is worth more than the citations already in it.

**(b) Required R conditioned on the bucket's own hit rate — he uses the
identity prospectively.** On wheat, where his hit rate is lower, he takes
*only* setups offering R > 3–4: *"there I have not so high win rate and so I
wait till the signal comes with a risk reward more than three or four or five."*

The transferable form: **the minimum acceptable R at entry should vary by
bucket, where the buckets are the screen's own strata** — price band, RVOL
decile, float bucket, gap size. Our engines apply one uniform entry gate across
all of them. This is the **sixth independent arrival at rank-don't-gate** in
the project's source material (after the `oSznkl4ASaA` guest's ADF score,
Shay's colour-coding, Cameron's A/B/C rubric, his deliberately-wide scanner
filters, and video 11's multi-horizon score). It should be checked against
`where_the_edge_is_20260913.md` before anything is designed.

**(c) The adherence audit, and it fills a hole this file created.** Asked what
he would do after fifteen consecutive losses:

> *"I would stop and I would look if I traded on my rules the last 15 trades."*

Not *is the edge gone* but *was it me*. **The retirement rules §3.1 calls for —
DaviddTech's standard-deviation bands on the equity curve (§2.7) — cannot tell
those two apart.** An equity curve breaching its lower band looks identical
whether the edge decayed or the execution drifted. The algorithmic analogue is
cheap and needs no new data: **when the curve breaches, first reconcile live
fills against what the backtest says should have happened on those same bars.**
If they diverge, the strategy is not broken, the execution is — and switching it
off is the wrong response. **Two gates, adherence first, decay second.**

**(d) Per-instrument standdown rather than a global kill.** He stopped trading
crude — his best market — for four months after the Iran war broke his read, and
kept trading everything else. *"I stopped trading my favourite asset, oil…
it's only to secure me."* Retirement applied at the symbol or regime level, not
the system level.

**(e) Stop granularity chosen by distance to target.** He drops to 5- or
3-minute charts *only* to tighten the stop when the target is close — *"when I
only want to have 50 points, [a 50-point stop] is too much."* Our stops are
percentage-based and timeframe-fixed. One grid cell.

### 9.5 Two contradictions to log

**Three touches, six days after §8 retired a three-touch rule.** IRONCLAD found
Tori's three-touch filter inverted the result on six of seven instruments
(§8.2). They are not the same object — hers validates a **diagonal** trend line
over at least a week; his counts touches on a **horizontal** boundary and is
justified by breakout probability rather than line quality — so §8's test does
not refute him. But **the number three is now unvalidated folklore in two
independent sources and tested-and-failed in one of its two forms.** Treat the
touch count as a parameter to sweep, never as a constant. This is the same
error pattern as the 20-cent stop in `warrior_4_reversal.md` §3: a round number
that recurs across sources is evidence of shared folklore, not of a constant.

**He contradicts his own earlier video.** §2.5 records, from video 7, a **50–60%**
win rate and *"sometimes I have 10 to 20 losses after each other."* Video 13
says **60–75% every year** and that in thousands of trades he never exceeded
**15** consecutive losses. Same trader, same period, two different sets of
numbers, neither audited. **Treat both as anecdote.** It is the cleanest
illustration in the collection of the standing rule that an n=1 recollection is
not a constant — and a caution about the seven verified returns in §9.1, which
are the only numbers here that came from a register rather than a memory.

### 9.6 To his credit

- He takes the **harder** side by his own account and says why: *"I know it's
  more easy to go with a trend… for me I don't feel comfortable."* A source
  admitting its chosen edge is the less efficient one is rare here.
- He is explicit that he is discretionary and does not pretend otherwise.
- He distinguishes a bad stretch from a broken strategy, which is §9.4(c).

### 9.7 Standing on this source

**Do not attempt to build the entry model.** The zone rule is withheld, and the
substitute he names himself — volume profile — is the one the §3.1 correction
shows our tape cannot support in the pre-market window. Two independent
blockers, either of which is sufficient.

**Take §9.4(c) and build it into the retirement rules.** Take (b) and (e) as
registerable experiments. Record (a) as corroboration of `win_rate_and_r.md`.

**And note the structural mismatch before anyone revisits this.** His premise is
that 70% of days are ranges. **Our universe is selected for the other 30%** —
`common/screen.py` filters for names gapping hard on RVOL ≥ 5, which is to say
it is a machine for finding the days Nill stands aside from. A fade-the-range
model imported onto a universe screened for violent trending is fighting its
own selection. If the model is ever wanted, it belongs on liquid large caps or
index futures, where the 70/30 premise is plausible and the consolidated tape
is complete — which is the §5 universe question, and §5's answer still stands.


---

## 10. Addendum, 2026-09-16 — Craig Percoco, and the only large test of ICT/SMC we have found

**"Once You Master Price Action, Trading Becomes Ridiculously Simple"** — Craig
Percoco, `jVs9BMIWyn4`, 11:33, published 2026-08-23. 316,911 views. **Read in
full 2026-09-16** (354 segments). Channel also assessed: 1.35M subscribers, 798
videos, 73.3M views since 2015.

Smart Money Concepts under a "price action" label — break of structure, change
of character, fair value gap, break-and-retest.

### 10.1 It is more codeable than almost anything in this file

The entry model at [9:19] is specified to a degree six of the ten original
videos never manage:

1. 15-minute for structure, **1-minute for entry**
2. Wait for the **New York session open**
3. **Change of character** on the 1m — first push out of the current trend
4. A **fair value gap** in the direction of that CHoCH
5. Price pulls back into it; **enter at the midpoint of the gap**
6. Stop **outside the FVG-producing candle**
7. Target **3–4R**

The FVG is defined exactly: three candles, bullish gap where candle 1's high
wick does not overlap candle 3's low wick. One line of code. **Entry price, stop
and target all stated** — §4 records that six of ten specify none of the three.

### 10.2 Four structural problems

1. **The "three keys" are two.** He defines change of character as *"effectively
   the opposite signal to our earlier break of structure."* Direction and
   invalidation are one measurement with opposite sign.
2. **Variable stop, no sizing rule.** Stop distance scales with the impulse
   candle — a volatility proxy — and position sizing is never mentioned in
   11:33, so **risk per trade is not constant**. Nill (§9.2) has the identical
   stop and closes the loop; this source does not.
3. **The chain of "wait fors" hides the number that decides everything.**
   CHoCH → an FVG in that direction → a retrace to its midpoint → without
   stopping out first. Each step discards cases. The conditional probability is
   never given, and one winning trade is shown instead.
4. **No performance data and no costs.** Zero win rate, zero sample, zero dates,
   on a 1-minute entry model where costs are decisive.

### 10.3 Someone has tested the family, and the result is worth more than the video

Applying §8.8's rule — search for a test before building. StatOasis ran **648
backtests** of ICT entries (order blocks, FVGs, and controls) across SPY from
1993, QQQ from 1999, DIA from 1998 and IWM from 2000:

> **"Exactly zero of 648 beat buy-and-hold on net profit."**

And the detail that matters most: **100% of order-block variants "made money"**
on SPY — while the **frequency-matched coin flip, with no entry logic at all,
averaged $46,270**. Only 1 of 32 market-horizon scores reached significance.

That is exactly the failure `PROGRAM_INDEX.md` §4 names: *a control whose output
is indistinguishable from the failure it detects is not a control.* Absolute
profit on a drifting instrument is not evidence of anything.

**Two caveats, stated because §8.5's discipline requires them.** It is
frictionless, and it is index ETFs over long horizons — **not 1-minute futures
or crypto**, so it does not refute this source's exact model, the same way
IRONCLAD's test refuted only the diagonal version of Tori's trend line. It is
also published by a vendor selling a masterclass. Separately, Build Alpha
publishes a guide to testing SMC that reports **no results at all**: *"I am not
telling you these concepts work and I am not telling you they do not."*

### 10.4 What it means for this project specifically

**A fair value gap is a three-bar pattern computed from minute OHLCV** — the
class already closed on our tape: `entry_split_result_20260914.md`, 22 features
across 11 families, **0 clear**, 88 buckets none profitable, break-even needing
a 1.86× lift against a best of 1.56×. On the wider 45M-bar census the best
volatility-independent feature reached 1.94× against a 0.108% base rate.

**FVG is not new information. It is a member of a class we have tested and
rejected**, and that is a stronger answer than the ETF study because it is our
data.

### 10.5 The channel

**20 of the 30 most recent titles carry a dollar figure**, and **nine are
"LIVE DAY TRADING — How I Profit $X Risking $2k"**: $4,717, $7,215, $9,273,
$9,691, $10,570, $10,589, $10,999, $14,832, $17,183. **Not one published session
is a loss.** Nine consecutive winners is a selection, not a sample — §4's
"every worked example is a winner" industrialised into a content format. The
scale claims do not reconcile either: $3,496/day is ~$70k/month against another
video's $27,000/month.

Five revenue streams attached — mentorship, an indicator bundle, a Discord, two
crypto-exchange affiliate links, a prop-firm discount code — more than any
source here. The description states the content is *"for entertainment purposes
only."*

### 10.6 Standing on this source

**Do not build it and do not spend a registration slot on it.** Not because it
is vague — it is the most precisely specified entry model in the collection —
but because it is a minute-OHLCV bar pattern, which is the one class our own
data has closed, and the only independent test of the family found 0 of 648
variants beating buy-and-hold with a coin flip as a live control.

Take one thing: the **sunk-cost observation** at [2:34] — abandoning analysis
you have invested hours in — which is a real bias and the one useful minute in
the video.

---

## 11. Addendum, 2026-09-16 — Jason Graystone, a method source with one priced rule

**"Why I Place Every Forex Order EARLY"** — Jason Graystone, `kpmJNVw4RhM`,
16:03. **Read in full 2026-09-16** (438 segments). Channel: 576K subscribers,
**1,044 videos since 2012**, 23.2M views, ~22k views per video.

### 11.1 The channel is the cleanest in the collection on marketing hygiene

**Zero of the 30 most recent titles carry a dollar figure** — against Percoco's
20 of 30 (§10.5). No "live trading $X profit" format at all. Roughly 11 of 30
are explicitly about trader behaviour rather than setups.

**But he makes no performance claim anywhere, so there is nothing to verify** —
the exact inverse of Nill (§9.1), whose seven World Cup placings were checked
against the register. Absence of over-claiming is not evidence of skill.

Two cautions: it is **forex on the 60-minute and 4-hour**, so nothing transfers
as a strategy; and one content family is unsound — **"The Bat Pattern Trading
Strategy"**, harmonic Fibonacci-ratio patterns with no independent evidence
base, the same family flagged in `orb_retest_depth_20260916.md` §5. A mid-video
broker plug and two broker-choice videos indicate an affiliate line.

### 11.2 The one rule, and he is the first source here to price one

A fill-probability execution rule:

| leg | placement | effect on R |
|---|---|---|
| Entry | **2 pips early** (60m), **4 pips** (4h) — before the level | worse |
| Target | **2 pips early** — before the level | worse |
| Stop | **2 pips beyond** the obvious level | worse |

All three legs cost R, and he says so:

> *"That will reduce the reward to risk profile… over time that can have a major
> impact on your overall performance on your strategy."*

And he closes the sizing loop that §10.2 leaves open:

> *"If your stop loss becomes 22 pips rather than 20 pips, you shouldn't risk
> more money just because you added a buffer. You should reduce the position
> size so that the monetary risk stays the same."*

He also says the buffer must scale with the instrument's volatility and spread,
and that *"the number itself is less important than the logic."*

### 11.3 What transfers

1. **The practitioner case for posted limits, on a different axis from the fee
   case.** Our measured argument is cost — ≈0.0021/share passive against
   ≈0.0067 marketable, a 3× swing. His is **fill probability**: a limit resting
   *at* the level frequently does not fill because the queue ahead absorbs the
   move. Independent reasons, same direction.
2. **A fourth vote on stop placement** — §8.5's table, now updated.
3. **A testable exit variant.** A signal exit fills at reference
   (`gradient_reversal`, **$0.0000/share**) while a stop fills through it
   (**−$0.0563/share**). "Target placed early" is the same trade: accept a
   slightly worse price to guarantee the fill. One grid cell.

### 11.4 What does not transfer

**The concept transfers; the number is meaningless here.** Two pips on EURUSD is
about 0.002% of price. Our measured pre-market spread is **83 bps** — roughly
400× that — and on a $3 stock a one-cent tick is already ~33 bps, so the
smallest expressible buffer is a third of a typical spread. The buffer is
quantised by the penny tick into a far blunter instrument than he is describing.

No performance data, no sample, no backtest. The 2- and 4-pip figures are
explicitly *"my rule of thumb"* — an n=1 practitioner habit, and §4 says that is
not a constant.

### 11.5 Standing on this source

**A method source, not a strategy source** — the same category as IRONCLAD in
§8, but for execution rather than falsification. Take the one priced rule and
the fourth stop vote. Take no numbers, build nothing forex, and skip the
harmonic-pattern material.


---

## 12. Addendum, 2026-09-16 — Emmanuel Malyarovich, and the first source to produce a spec

**"The ONLY 2 Indicators I've Used to Make $843,886 Day Trading"** —
`2e4WayvjLJo`, **37:19**, published 2026-09-12, 61,961 views. Sells a mentorship
application and a free 10-hour course. **Read in full 2026-09-16** (903
segments).

### 12.1 What separates it from §10 and §11

Three things, and they are real:

1. **He denies the premise of his own title, twice.** Opening: *"There is not a
   single indicator in existence that's going to tell you exactly when to buy
   and exactly when to sell… stop trying to find one."* Closing: *"I am never
   taking trades solely because price is pulled back into the 20 SMA."* Correct
   framing — and it means **the video contains a component, not a strategy**,
   by his own account.
2. **He shows a brokerage account** with net contributions and withdrawals
   alongside the gain, which is the right disclosure *shape*. Unverifiable from
   a screen recording, and a period is easy to choose — against §9.1, where the
   record came from a public register.
3. **He raises the hindsight objection himself** — *"you might be thinking, oh,
   obviously it's going to look like that because this candle has already
   formed"* — then answers it by scrolling back one chart. Better instinct than
   the rest of this file; still one chart, not a count.

### 12.2 The method, as stated

**Indicators: EMA9, SMA20, SMA200.** (Title says two; he uses three and says so.)

**Two setups only**, both directions: **retracement** into the EMA9/SMA20 zone,
and **base breakout / breakdown**. Trend-following — *"95% of the time I am
trading in the direction of where prices are already going."*

**State gates, and these are the content:**

| gate | as stated |
|---|---|
| flat-MA veto | never trade when the SMA20 is flat or waving sideways |
| structure | SMA20 **below** price and rising; EMA9 above the SMA20 |
| touches | *"as many touches as possible… the more touches, the more reliable"* |
| **slope band** | *"ideally 45°"* — steeper = overextended, flatter = no momentum |
| extension | distance from price to the SMA20; further = more overbought, exit zone not entry zone |
| acceleration veto | **skip the first retracement** after the trend has accelerated |
| SMA200 | target when above; **veto the entry if it sits directly overhead** |
| entry zone | between the EMA9 and the SMA20 |

**Session → timeframe map:** 09:30–10:00 ET on 1m and 2m; 10:00–12:00 on 2m and
5m; 12:00–16:00 on 5m and 15m; SMA200 read off hourly / daily / weekly.

**Entry trigger, from the worked LASE example:** *"I timed my entry above this
doji bar… and placed my stop loss below the doji bar."* Adds on subsequent
retracements, stop raised under each new pivot. Target: the daily SMA200 — the
example ran to $2.24 against a daily SMA200 at $2.27.

### 12.3 The three connections to this project

**(a) Every one of his indicators is already a measured feature, and none
cleared.** `ma20_dist` **1.46×**, `ma20_slope` **1.37×** (1.94× whole-tape),
against a break-even requirement of **1.86×**. `ema9_dist` and `ema200_dist`
were added in `entry_place_built_20260915.md`, which notes explicitly that
`ema9_dist` *"is `ma20_dist` at a different lookback — counting it separately
would inflate one idea into two."*

**(b) But he uses the slope as a two-sided BAND, and every test here has been
one-sided.** `REGISTERED_bar_shape_20260916.md` is *"median split, HIGHER IS
BETTER"*; `entry_split` used quartiles read directionally. **A middle-is-best
optimum is invisible to a monotone test.** This is not a claim that the band
works — it is that the shape of the test and the shape of the rule have never
matched. `entry_split` already hints at it: on two of three best features the
best-rate bucket had the *worst* P/L. **Re-reading the existing quartile tables
for a middle peak costs nothing and needs no new run.**

**(c) Session-conditional timeframe is now a fourth arrival and the second
time-conditional one.** Cameron: *"1-minute before 11:30, 5-minute after"*
(`warrior_0_universe_and_risk.md` §3, which already calls it *"the sharpest
claim here"*). Two practitioners now make bar size a function of time of day.
It does not transfer to MCL, which trades 04:00–09:30. **It maps onto ORB**,
which fixes `TRIGGER_BAR_MINUTES = 5` across the whole session.

### 12.4 What is wrong with it

**"Ideally 45°" is not a quantity.** Slope in degrees is a function of chart
scaling — price-axis zoom and bar width. A 45° line on his screen is a different
slope on another, and a different slope again at a different vertical range.
**It cannot be coded as stated.** The scale-free version is the MA's fractional
change per bar normalised by per-bar volatility, which *is* `ma20_slope`, already
measured at 1.37×. `ma_trend_spec_20260916.md` §3.2 fixes the definition.

**Every example is a winner.** LASE +$4,368 and +$7,144, ANF, DKS (*"a lot of my
students caught this and absolutely printed"*), SHOP (*"almost picture
perfect"*). **Not one losing trade in 37 minutes** — §4's standing pattern, and
what makes these demonstrations rather than evidence however detailed they are.

**$843,886 with no win rate, no average loss, no sample and no drawdown.** The
inverse of the usual failure here: normally a win rate with no R; this is a P/L
with neither.

**One direct contradiction to log.** *"You want to see as many touches as
possible… the more touches, the more reliable."* §2.3's three converging sources
say the opposite and give a mechanism — *"you strike on the first contact, not
the fifth"*, because retests decay as trapped participants exit. **Two opposite
claims about touch count, neither measured.** The spec registers it as a
deliberately two-sided test for this reason.

### 12.5 Standing on this source

**The only source in this file to produce a spec** — see
`ma_trend_spec_20260916.md`, which fills the blanks he leaves and fixes a
go/no-go before any code exists. Read that document's §8 before building
anything: its prior is poor, its data requirements are not currently met, and it
sits behind an unresolved tape defect.

**Take nothing else.** Not the account screenshot as evidence, not the degree
measure, not the examples as a base rate.


### 12.6 The channel pass, 2026-09-16 — five more videos read in full

170K subscribers, **117 videos since April 2024**, 6.5M views. Read in full:
`XZubPrrdYww` (32:13), `bwJc32pCFYM` (15:38), `iw_RnGTH1UU` (28:44),
`F7sv2geCmkE` (36:17), `OjPMmzwC3d8` (15:20).

**Title census of the 30 most recent: 10 carry a dollar figure**, and **five are
"The ONLY X You'll EVER Need"** — the only entry model, the only two setups, the
only support-and-resistance strategy, the only beginner's guide, the only two
indicators. **The set refutes itself**: if the entry model were the only one you
ever needed, the support-and-resistance strategy would not also be.

**It was worth the pass.** Seven numbers came out that the headline video does
not contain, and they are folded into `ma_trend_spec_20260916.md`:

| finding | his words |
|---|---|
| **40–60% retracement "golden zone"** | *"I always want to see a 40 to 60% retracement… I call that the golden zone"* |
| minimum MA touches | *"at least two touches on these moving averages"* |
| entry-bar shapes | narrow-range bar, doji, bottoming/topping tail; cluster → take the highest high |
| R floor as a rejection | *"It's less than 2:1 R-to-R because I'm risking 15 cents to make 20 cents. It doesn't make sense."* |
| sizing formula | *"Share size equals risk divided by entry minus stop-loss price"* |
| risk ladder | *"two to three consecutive losing days… lower your risk by 50%"*, restored only after *"three consecutive green days"* |
| give-back cap | *"You have to protect at least 50% of the profit that you make on a day-to-day basis"* |

**Two of these are convergences, and they are the reason the pass paid.**

**(a) The golden zone is the third independent arrival at one band.** V4/Raghee
gives **38–62%** (`orb_strategy_spec.md` §5.3, `RETEST_MODE = zone`); the Reddit
ORB+fib source gives 50% and 61.8% (`orb_retest_depth_20260916.md`); this source
gives **40–60%**. Three unrelated practitioners, one band — **and the same
anchor disagreement**, range versus impulse, that `orb_retest_depth` §2 already
proposes as `zone_impulse`. **One measurement, two documents.**

**(b) Risk-normalised sizing is now the fourth arrival and the most corroborated
mechanic in this entire file** — after Tori (§2.6), Nill (§9.2) and Graystone
(§11.2). All four size *from the stop distance* so that dollar risk is constant.
`sizing_and_capacity.md` compared flat-100 against capital-based and **never
tested this third model**.

### 12.7 What the pass also settled against the source

**He says the method cannot be programmed**, in his own words:

> *"That's why it's not really possible to program this strategy… because
> there's so many criteria that go into identifying a high probability breakout
> or retracement from a low probability one."*

That is the ceiling on `ma_trend_spec_20260916.md` and it is registered in that
document's banner: a faithful implementation is unavailable, so a failure cannot
distinguish *the idea is wrong* from *the subset is not the idea*.

**Five self-contradictions across six videos** — two indicators or three; *"20
EMA"* narrated repeatedly for what he sets up as a 20 SMA; *"as many touches as
possible"* against *"at least two"*; reversals traded or eliminated; and monthly
earnings titles of **$34,194** and **$18,432** four weeks apart, neither
derivable from the stated annual figures ($461k for 2025; $700k for mid-2024 to
late-2025).

**And the evidence base, counted across six videos: 15 winning or neutral worked
examples against 1 loss.** The single loss is the most useful thing in the set —
BYND, ~$1,000, *"I really sized up on this trade… I thought it was super high
probability"* — because it is a loss on an **upsized, high-conviction** trade,
which is exactly the failure the 401-recap census ranks first by lift
(`oversized`: 46.2% of red days against 7.2% of green). **The one loser he shows
is the archetype.** No win rate, sample size, trade count, average loss or
drawdown appears anywhere in six videos.

**Standing: the channel is closed.** The pass extracted what it had.
