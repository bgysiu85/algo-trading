> **ARCHIVED 2026-09-08.** E15 is dormant: spec only, no code, and VW9's result lowered the prior considerably.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

# Six EMA / moving-average sources — where they agree and where they conflict

Compiled 2026-09-03, to sanity-check `claude/ema15_full_day_strategy_spec.md`
before any code is written. All six transcripts read in full.

## The sources

| # | Video | Channel | Length | Published | Views |
|---|---|---|---|---|---|
| **S1** | I Tried This EMA Trading Strategy for 30 Days (Results) | Trading Data | 10:18 | Jul 2026 | 8.4k |
| **S2** | 3 EMA Strategies That NEVER LOSE — EVER! | Trader DNA | 24:57 | Nov 2025 | 731k |
| **S3** | The Ultimate Step-by-Step Moving Average Trading Guide | Ross Cameron / Warrior Trading | 41:10 | Apr 2024 | 263k |
| **S4** | Live Trading on the 5-Minute Time Frame | Humbled Trader | 25:57 | Jul 2024 | 93k |
| **S5** | The Moving Average Trading Strategy You Need! | Ross Cameron / Warrior Trading | 59:58 | Jul 2024 | 110k |
| **S6** | The ONLY 2 Indicators I Use to Make $2,000/Day Trading | Jdub Trades | 16:21 | May 2026 | 85k |

S1 is the source the E15 spec was built from. **S3 and S5 are the only sources
trading Ben's actual universe** — US small-cap low-float momentum names on a
news catalyst, top percentage gainers, sub-1m floats. S4 and S6 trade liquid
large caps intraday. S2 is instrument-agnostic and leans forex.

### What each one is at a glance

| | Indicators | Primary TF | Entry trigger | Stop | Target |
|---|---|---|---|---|---|
| **S1** | 9/20 EMA | 1H (15m w/ 1H filter) | Close beyond swing body high after first pullback | Below pullback low | Fixed 1:2 |
| **S2** | 50 EMA (+20/100; test per market) | Any, leans higher | Candle confirmation at EMA ∩ horizontal S/R | Beyond the zone | Fixed 1:3 |
| **S3** | 9/20/200 EMA, 200 SMA (daily), VWAP, MACD | 10s / 1m / 5m / daily | First micro pullback to the 9 EMA | Below the pullback | Scale out |
| **S4** | 8 EMA, VWAP | 5m (2m to execute) | Candle **closes** back above both | Below VWAP + 8 EMA | Ride the 8 EMA |
| **S5** | 9/20/200 EMA, MACD, alligator 5/8/13 | 1m + 5m | Break of wedge at MA support | Low of last 5m candle | Scale out |
| **S6** | 9 EMA, VWAP | 1m + 5m | Candle closes back above 9 EMA at a marked level | Under that level | Fixed 1:2 |

---

## Part 1 — Convergence

### C1. The crossover is not the entry. Unanimous, and stated most forcefully by the people who trade for a living.

S1 builds its whole pitch on it. S2 calls "two MAs cross, that's my entry" the
single most dangerous of the three beliefs that blow accounts. S3 and S5 are
blunter still: **crossover-only is not a good strategy on its own, because by the
time the lines have crossed the trend shift is already obvious and well off the
highs.**

Nobody in this set enters on a cross. That is as close to consensus as six
independent sources get, and E15 already honours it.

### C2. The entry is a pullback into a fast MA, then resumption — not a breakout into space.

Every source. S3/S5 call it the micro pullback, S6 the 9 EMA retest, S4 riding
the 8 EMA, S1 the first controlled pullback into the 9/20 zone, S2 the EMA as an
"area of value". Same shape, five names.

### C3. Confirmation is a candle **close**, never a touch or an intrabar break.

Unanimous where addressed. S4 is the sharpest illustration: an entry was skipped
entirely because no candle ever *closed* above VWAP and the 8 EMA, even though
price traded above them repeatedly. S1: the close is what matters, not how many
bars it took. S6: candle confirmation closing back above the 9. S2: needs a
strong bullish candle or a hammer/engulfing before acting on an EMA touch.

E15 already uses closes throughout. Keep it.

### C4. Never enter an extended move — wait for price to come back to the MA, or the MA to come to price.

S3 states it as an explicit check on the 5-minute chart before every re-entry.
S1: an entry inside an extended move gives a bad price and a very wide stop, so
skip that section of the chart. Identical rule, independently arrived at.

### C5. Chop is the enemy; a trend filter exists to keep you out of it.

Unanimous. The filters differ (S2: higher-high/higher-low "1-2-3" structure;
S3/S5: MACD above signal = "window open"; S4: identify the range on the 5m and
stand aside; S6: don't trade consolidation), but the purpose is identical — most
of the day is untradeable and the job of the indicator is to say so.

### C6. A fast MA of 8–9 periods is the near-universal short-term reference.

9 EMA in S1, S3, S5, S6. 8 EMA in S4. Only S2 prefers 50, and it is not trading
intraday momentum. **Five of six converge on 8–9 as the line price "rides".**

### C7. The stop is structural and tight — just beyond the pullback's extreme.

S1: below the pullback low. S5: the low of the last 5-minute candle, giving
10–20c stops. S6: under the marked level. S4: below VWAP and the 8 EMA. No one
uses a fixed percentage stop. E15 matches.

---

## Part 2 — Divergence

These are the disagreements, ordered by how much they should change the E15
spec.

### D1. The MA pullback is ranked *third* by the only sources trading this universe — and they explain why.

**This is the most important finding in the set.**

S1 presents the pullback-to-EMA setup as the whole strategy. S5 ranks the same
setup **behind** the micro pullback and the bull flag, and states the cons
plainly: by the time price has pulled all the way back to a moving average, the
MACD has usually already crossed over, the bull flag has already failed, and the
stock has shown real weakness. S5 also avoids the setup entirely in a "cold"
market because false breakouts ("jackknives") are far more common then.

So on Ben's exact universe, the practitioner's view is that **E15's setup is the
late entry** — the one you take after the good ones have gone, when you already
have a profit cushion, in a hot market only.

That does not kill it. But it reframes the expected result: E15 should be
expected to underperform a micro-pullback entry on the same names, and any
backtest that shows otherwise deserves suspicion.

### D2. Nobody in this set trades a 15-minute chart intraday. Nobody.

| Source | Intraday timeframes used |
|---|---|
| S1 | 1H primary; 15m only with 1H alignment; **explicitly avoid 1m and 5m** |
| S3 | 10-second, 1-minute, 5-minute, daily |
| S4 | 5-minute primary, 2-minute to execute; **abandoned the 1-minute** |
| S5 | 1-minute and 5-minute |
| S6 | 1-minute and 5-minute |

The one source that recommends 15m is the one that doesn't trade this universe,
and it recommends 15m as a *subordinate* frame to a 1H trend that E15 has
already established cannot be computed in a single session.

Meanwhile S1's advice to avoid 1m/5m is contradicted by all three live-trading
sources, one of whom (S4) migrated *up* from 1m to 5m and explains exactly why:
fewer false confirmations, better risk-reward, more patience to hold a winner.
**The converged answer across the practitioners is 2–5 minutes, not 15.**

Combined with the §0 warm-up arithmetic — 15m bars put the first possible EMA20
reading at 09:00 ET and the first realistic entry near 10:30 — this is a
substantial argument that 15 minutes is the wrong timeframe for this universe,
and that 5-minute (MC5's frame) is where the same rules belong.

### D3. VWAP is absent from S1 and S2, and is one of only two indicators in S4 and S6.

S3 calls VWAP one of the most respected intraday indicators there is. S6 makes
it a hard directional gate: **do not go long below VWAP, do not go short above
it.** S4 uses VWAP + 8 EMA as its entire indicator set.

E15 inherits S1's blind spot and has no VWAP at all. Two reasons that matters:

1. It is the most widely watched intraday level on small caps, so it is where
   other traders' orders actually sit.
2. **VWAP requires no warm-up.** It is defined from the first bar of the
   session. Where a 20-period EMA cannot say anything until 09:00 ET, VWAP is
   meaningful at 04:15.

That second point is the direct answer to the E15 spec's central problem. A
VWAP + 9 EMA configuration (S4/S6) can trade the 04:00–06:30 window that Ben's
own session-window test identified as carrying 93% of the measured edge. The
9/20 crossover configuration cannot.

### D4. Levels from outside the setup: four of six mark them, S1 marks none.

| Source | External levels marked before entry |
|---|---|
| S3 | Daily 200 EMA/SMA — checked pre-market as the first resistance; 5-min 200 MA |
| S4 | Previous day high and low |
| S5 | Daily gap edges, daily 200 EMA, whole and half dollars |
| S6 | Previous day high/low, opening 5-minute range high/low |
| S1 | **None** — only the swing high inside the impulse leg |
| S2 | Horizontal S/R zones tested multiple times |

S3's routine is instructive: the first thing checked on a gapping small cap
pre-market is where the daily 200 MA sits, because a nearby one is a reason
*not* to buy, and the break-and-hold above it is the trade. E15 has no equivalent
and would enter straight into such a level without knowing it was there.

### D5. Fixed R:R vs riding the trend — 3 v 3, and Ben's own data has already voted.

Fixed targets: S1 (1:2), S6 (1:2), S2 (1:3).
Discretionary/trailing: S3 and S5 (scale in and out continuously off level 2),
S4 (hold while no candle closes below the 8 EMA, even through a violated daily
level).

The MCL work already tested this: V3 → V4 replaced a 6% fixed stop with a 5%
trailing stop and went from +$339 to +$931. A fixed 1:2 on a universe screened
for names that run 200–800% caps the exact outcome the screen exists to find.
The E15 spec keeps 1:2 as the faithful baseline, which is right — but the
trailing variant should be run in the same pass, not "after".

### D6. Optimise the MA per instrument (S2) vs deliberately use the standard settings (S3/S5).

S2 devotes its final section to testing 20/30/50/75/100/150/200 per market and
picking whichever one price visibly respects most often.

S3 and S5 argue the opposite, and the reasoning is better: these levels work
*because* everyone watches them. The analogy used is traffic signals — the value
is in every driver reading the same red light. S5 explicitly keeps MACD on stock
settings so as to see the same signal everyone else sees.

If the mechanism is a self-fulfilling Schelling point, then per-symbol
optimisation destroys the thing that made it work and fits noise instead. Given
that two of Ben's last three experiments (the 6,000-share volume floor, the
5-bar arming window) failed by relaxing or re-tuning a rule whose restrictiveness
was doing the real work, **the S3/S5 position should win here: keep 9/20 fixed
and do not sweep EMA lengths per name.**

### D7. Volume is central to the practitioners and near-absent from S1.

S3/S5: high-volume red candles are a warning sign; a breakout needs volume
behind it; float, relative volume and the news catalyst are part of stock
selection; 300k shares in a first 1-minute candle is called out as significant.
S4 judges a bounce by comparing green-candle volume against the preceding
red-candle volume, and stays short when the bounce volume is weaker.

S1 mentions volume essentially not at all. E15 currently has one volume rule —
the $20k dollar-volume gate on the trigger bar — and nothing that reads volume
*within* the pullback.

### D8. Market regime: S3/S5 change the rulebook, S1/S2/S4/S6 don't.

S5 is explicit that in a hot market it trades more setups including MA
pullbacks, and in a cold market it trades only micro pullbacks and bull flags —
because that is when the jackknife false breakout appears. S6 checks SPY/QQQ
context. S1, S2 and S4 have no regime concept.

E15 has none either, and the setup S5 drops first in a cold market **is E15's
setup.**

### D9. One direct contradiction: body or wick?

S1: draw the trigger level at the candle **body**, not the wick — a wick shows
where price was rejected, a body shows where it was accepted.
S2: when marking the consolidation zone around an EMA touch, always adjust the
lines out to the extreme **wick**.

These are reconcilable and the reconciliation is a useful rule:
**use the body for a level you must close beyond (a trigger); use the wick for a
boundary that defines containment (a range).** E15's `swing_body_high` is a
trigger, so the body is correct.

### D10. Trade-per-cross vs a trading window.

S1's model: one crossover arms one sequence which yields at most one trade.
S3/S5's model: the cross (read through MACD) opens a *window*; inside it every
micro pullback is tradeable and S5 shows seven entries inside a single move;
outside it, nothing is.

These produce very different trade counts from the same tape. E15 implements
S1's model and files S3/S5's as an optional flag. Given that the practitioners
on this universe use the window model, it deserves to be a first-class variant.

---

## Part 3 — Source quality

Worth stating plainly, because it should weight how much any of this moves the
spec:

- **S3, S4 and S5 show live executions**, including losing trades and trades
  they held through drawdown. S4 shows a short scaled in and covered in pieces.
  S6 shows a setup that stopped out immediately before the re-entry worked.
  That is the honest end of this material.
- **None of the six presents a verifiable track record** — no logged sample
  size, win rate, or drawdown. S3/S5 cite a cumulative profit figure and attach
  a "results are not typical" disclaimer.
- **S2's title claims strategies that "never lose."** It has by far the largest
  audience of the six and the least verifiable content.
- **Every source sells something** — courses, scanners, PDFs, a stock-screening
  product. Rules are demonstrated on hand-picked charts after the fact, which is
  the same selection bias already flagged against Ben's own 21-name set.

Treat all six as **hypothesis generators, not evidence.** The convergences (C1–C7)
are worth more than any single source, precisely because they were arrived at
independently.

---

## Part 4 — What should change in the E15 spec

Ordered by expected value. None of these are done yet.

| # | Change | Driven by | Effort |
|---|---|---|---|
| 1 | **Add a VWAP + 9 EMA variant that can trade pre-market.** No warm-up, so it reaches 04:00–06:30 where the measured edge lives. Arguably a better strategy for this universe than E15 itself. | D3, and §0 of the spec | New spec section |
| 2 | **Test 5-minute alongside 15-minute.** Nobody in the set trades 15m intraday; the practitioners converge on 2–5m. Would also make E15 directly comparable to MC5. | D2 | Parameter |
| 3 | **Add prior-day high/low and the daily 200 EMA as context.** Veto or de-weight a trigger that fires straight into one. | D4 | Data + one rule |
| 4 | **Add a volume test inside the pullback** — reject if the largest down bar's volume exceeds the largest impulse up bar's. | D7 | One rule |
| 5 | **Promote the trailing exit to the same run as the 1:2 baseline**, not a later pass. | D5, plus V3→V4 | Parameter |
| 6 | **Promote `ALLOW_REARM_SAME_TREND` to a first-class variant** — it is the practitioners' actual model. | D10 | Already specified |
| 7 | **Do not sweep EMA lengths per name.** Keep 9/20 fixed. | D6, plus the arming-window and volume-floor failures | Discipline |
| 8 | **Consider a market-regime flag** (hot/cold) — the setup S5 abandons first in a cold market is exactly this one. | D8 | Needs a proxy |

Items 1 and 2 are large enough that they change what gets built. They should be
settled before the pre-flight measurements in the spec's §7 are run, because
they change which measurements matter.

---

*Sources listed in the table above. All six read in full from transcript.
Nothing here is validated; it is a comparison of claims, not of results.*
