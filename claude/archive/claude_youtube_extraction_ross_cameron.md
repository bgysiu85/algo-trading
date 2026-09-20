# YouTube extraction — Ross Cameron / Warrior Trading

Started 2026-09-09. Channel: `@DaytradeWarrior` (`UCBayuhgYpKNbhJxfExYkPfA`),
**3,618 videos**, 2.1M subs, active since 2013.

**Method, tooling and gotchas: `claude_youtube_extraction_humbled_trader.md`
§1-§2.** Evidence standards: `source_videos_20260907.md` §4 — source videos are
**hypothesis generators**, not results.

**Status: enumerated and triaged. Corrected 2026-09-09 after checking project
knowledge (see §0). No new transcripts pulled yet.**

---

## 0. METHOD FIX — search project knowledge BEFORE enumerating a channel

The first version of this file put **two videos on the shortlist that had
already been read in full** in earlier sessions. Both appear as sources in
`archive_ema_source_comparison.md` and `short_selling_source_comparison.md`:

| Video | ID | Already read as |
|---|---|---|
| The Ultimate Step-by-Step Moving Average Trading Guide | `eTUYXkAr6Pc` | **S3** |
| The Moving Average Trading Strategy You Need! | `w2owyBNunDQ` | **S5** |

**Add to the method in the other file's §2, as step 0:**
> Before enumerating any channel, search project knowledge for the channel name
> and for the presenter's name. This project already contains multi-source
> comparison files built from full transcripts; a shortlist assembled without
> checking them will duplicate work.

---

## 1. What we already know about Cameron (from existing project files)

**Do not re-derive any of this.**

- **Indicators:** 9/20/200 EMA, 200 SMA (daily), VWAP, MACD; S5 adds an
  alligator 5/8/13
- **Timeframes:** 10-second, 1-minute, 5-minute, daily (S3); 1m + 5m (S5).
  He is one of only two sources in that comparison trading **our actual
  universe** — small-cap low-float momentum on a news catalyst, top % gainers
- **Entry (S3): the first micro pullback to the 9 EMA.** Stop below the
  pullback, scale out
- **Entry (S5):** break of a wedge at MA support. **Stop = low of the last
  5-minute candle, giving 10-20c stops.** No fixed-percentage stops anywhere
- **The crossover is not the entry** — he is blunt that by the time the lines
  cross, the move is "well off the highs"
- **He avoids the MA setup in a "cold" market** — false breakouts
  ("jackknives") are far more common then
- **Short side: he effectively doesn't.** On camera in S5: the MA system
  "wasn't really designed for traders who are trading to the short side… this is
  really designed for momentum trading to the long side." Every later mention of
  shorts is about a squeeze as *fuel for a long*

### The finding that should shape what we do next

`archive_ema_source_comparison.md` §D1 records that **S5 ranks his setups**:

> **micro pullback → bull flag → MA pullback**, in that order.

**Our bull flag algo implements his number two, not his number one.** He gives
reasons for the ranking: by the time price pulls back to a moving average the
MACD has usually already crossed, the bull flag has already failed, and the
stock has shown real weakness.

→ **The open question is no longer "what is the micro pullback."** It is:
**does he anywhere specify the micro pullback tightly enough to code it
alongside the bull flag detector we already have?** We know it is "first
pullback to the 9 EMA." We do not have a retracement depth, a pullback bar
count, a volume condition, or an invalidation other than "below the pullback."

---

## 1b. THE WEBSITE BEATS THE VIDEOS — read `warriortrading.com` first

`https://www.warriortrading.com/momentum-day-trading-strategy/` (updated
2025-01, by Cameron) gave **more codeable parameters in one free page than the
entire Humbled Trader channel gave in 13 videos.** No PDF gate, no transcript,
no credits.

**Method note: for a channel with a content-marketing site, read the site
first.** The videos sell the course; the strategy pages *are* the course
marketing and therefore state the rules plainly.

### Universe — 4 criteria, "scan 5000 stocks → usually fewer than 10 a day"

1. **Float < 100M shares**, "under 20 million is ideal"
2. **Strong daily chart** — above the moving averages, **no nearby resistance**
3. **RVOL ≥ 2×**
4. **A fundamental catalyst** (PR, earnings, FDA, activist) — but he explicitly
   allows momentum with no catalyst, calling it a technical breakout

> **His RVOL is not our RVOL.** He defines it as "current volume for today
> compared to the average volume **for this time of day**." Ours is
> `volume_today / mean(volume, prior 10 days)` — a flat daily comparison.
> **These are different metrics.** Given `consolidated_volume_gap.md` §3.2 found
> our RVOL is substantially noise, a time-of-day-normalised denominator is worth
> considering on its own merits. **Concrete change, cheap to compute.**

The "fewer than 10 per day from 5,000" figure is also a **capacity/trade-count
benchmark** we can check our own screen against.

### Bull flag — the spec, and it is parameterised differently from ours

- Squeeze up on tall green candles (the pole)
- **Wait for 2-3 red candles** to form the pullback
- **Entry = the first green candle to make a new high after the pullback**
- **Stop = the low of the pullback**
- Volume typically spikes as that first candle makes the new high

> **He specifies the pullback as a BAR COUNT (2-3 red candles). Our
> `config.py` parameterises it as a retracement percentage.** Those are not the
> same constraint and will select different flags. This is the concrete
> comparison the whole channel was worth reading for — and it came from a web
> page, not a 57-minute video.

**Flat top breakout** — same, but the pullback has a flat top at a resistance
level. Mechanism he gives: a large seller parks there, shorts stack buy-stops
just above, and taking the level out triggers them.

### Risk — and our algo already matches him

- Tight stop **just below the first pullback**
- **If the stop is more than 20c away**, he may take a −20c stop and re-enter
- He uses ~20c because he wants **2:1** — "much easier with a 20c stop and 40c
  target than a $1.00 stop and $2.00 target"
- Sizing: risk ÷ stop distance. **20c stop, $500 max risk → 2,500 shares**

→ `archive_early_ideas.md` records our bull flag algo as **fixed $500 risk per
trade, 2:1 default**. **Those are Cameron's exact numbers.** Worth confirming
whether that was deliberate or coincidence — either way, the config is aligned
with the source.

### Time of day — a session-dependent timeframe rule

- Trades **09:30–11:30**, most active in the first hour, slows right down after
- **"After 11:30am I prefer to only trade off the 5-min chart. The 1-min chart
  becomes too choppy in the mid-day and afternoon."**

> **Third independent source on 1m→5m**, after Shay (`gn02_Ic9i5U`) and the EMA
> comparison's D2. But Cameron's version is **conditional on time of day**, not
> a blanket preference — which is a sharper, more testable claim, and it fits
> `session_aware_screening.md`.

### Exits — three rules, all codeable

1. **Sell ½ at the first target** (2:1), then move the stop to breakeven on the
   rest
2. **If ½ not yet sold, the first candle to close red is the exit.** If ½ *is*
   sold, hold through red candles while the breakeven stop holds
3. **Extension bar** — an outsized spike candle — sell into it

→ Rule 2 is a **state-dependent exit**: the same red candle means "get out" or
"ignore" depending on whether the first target was hit. MCL's exit is
apex-and-trailing with no such state. Cheap to add as a variant.

### Other written pages worth reading (same site, all free)

`/bull-flag-trading/` · `/gap-go/` · `/reversal-trading-strategy/` ·
`/mean-reversion/` · `/position-sizing/` · `/how-to-build-morning-watchlist/` ·
`/premarket-trading/` · `/how-to-use-stock-scanners/`

**Do these before any further video work on this channel.**

---

### 1c. The bull flag spec is now COMPLETE — and it answers the §1 question

From `/bull-flag-trading/` and `warriortradingnews.com`. Paraphrased.

**The micro pullback is a mini bull flag.** He states it directly: he day trades
bull flags on 1-minute and 5-minute charts, and scalps "micro pullbacks" using mini
bull flag patterns on the 10-second and 1-minute. **So it is not a separate
pattern — it is the same pattern on a faster chart.** The §1 question is
answered: our existing detector already implements the shape; the difference is
bar interval and scale.

**The full pattern definition, with the thresholds the momentum page omitted:**

| Element | Cameron's rule |
|---|---|
| Pole | Strong move up **on high relative volume** |
| Flag | Consolidation near the top of the pole **on lighter volume** |
| **Max retracement** | **More than 50% of the initial move is a sign of weakness** |
| **Volume condition** | Consolidation volume **above** the pole's volume indicates selling pressure |
| Pullback length | Up to **3 red candles** |
| Breakout | Continuation **on high relative volume** |
| Entry | First candle to make a new high |
| Stop | Low of the pullback |
| Target | Retest of the high, then beyond |
| **Invalidation** | Break of the **9 EMA or VWAP** is a sign of weakness |

**Universe for bull flags specifically:** price **$2–$20**, at least **10% up on
the day**, **5× relative volume**, news catalyst preferred.

> **That is MCL's universe almost exactly.** Ours: $2–$20 · RVOL ≥ 5× · float
> < 20m · top-2 pre-market gainer. His: $2–$20 · RVOL 5× · float under 20M
> "ideal" · 10%+ on the day. **The screens are the same screen.** Either it was
> derived from this source or it converged — worth knowing which, because it
> changes how much independent confirmation our universe actually has.

### What this gives `config.py` — direct comparisons

| `config.py` parameter | Cameron's stated value |
|---|---|
| flagpole % | not a % — "strong move on high RVOL"; the *universe* carries 10%/5× |
| retracement % | **≤ 50% of the pole** (beyond = weakness) |
| volume multiple | **flag volume < pole volume** — a *ratio between phases*, not a fixed multiple |
| (absent) | **pullback ≤ 3 red candles** |
| (absent) | **invalidate on 9 EMA or VWAP break** |
| risk $ / RR | $500, 2:1 — already matching |

**Two of these are things our detector may not encode at all:** the bar-count cap
on the pullback, and the 9 EMA / VWAP invalidation. And our volume test is a
fixed multiple where his is *relative between the pole and the flag* — a
different and arguably more robust construction, since it self-normalises per
setup rather than against a trailing average.

---

## 2. Shortlist — genuinely unread

### Tier 1 — the micro pullback and MCL's indicators

| Video | ID | Len | Why |
|---|---|---|---|
| High Accuracy 1 Minute Scalping Strategy (Full Training) | `p1W8Mjl4kWs` | 57:22 | MCL's timeframe; longest unread training |
| How I Nailed Trading with the MACD Indicator | `mfGQr2tHoX0` | 21:58 | MCL's MACD conditions came from this style |
| The Ultimate RSI Trading Strategy | `iS5lvJGMM8E` | 27:45 | MCL uses RSI rising as a gate |

### Tier 2 — named setups adjacent to the bull flag

| Video | ID | Len |
|---|---|---|
| The "Sub VWAP Trap" Strategy (Big Breakout Setup) | `W3jXQlgGbBc` | 29:53 |
| The "Stair Step" Day Trading Strategy | `S3vYOE9d6nU` | 15:10 |
| Flat Top Breakout Pattern | `4jes2_N3m2I` | 14:03 |
| BASE HIT Strategy | `mBT72-bFlPM` | 29:17 |
| Master Supply & Demand Trading | `BFH-0N8S-IA` | 29:26 |
| How to Day Trade BREAKING NEWS with a Scalping Strategy | `SLMXOd13uqI` | 59:52 |
| PROVEN 3hr Day Trading Strategy (Highest Win Rate) | `A3sbJBOLGuI` | 58:28 |

`BFH-0N8S-IA` also touches volume-at-price, which `source_videos_20260907.md`
§3.1 already flags as computable from `bar_cache_db` and worth measuring.

### Tier 3 — dip entries (settles an open disagreement)

| Video | ID | Len |
|---|---|---|
| Master the Dip Trading Strategy | `ORWJzImSTdE` | 1:05:05 |
| Dip Trading was HARD Until I Learned These 3 Tricks | `hz7vhSIXXSc` | 51:55 |

→ Shay argues dip-buying beats breakout-buying on low-float small caps
(`TzGQE8d0f18`). Cameron trades **both** and ranks his own setups. How he
decides which applies is the natural cross-check.

### Recent / broad
`xGIa8Vg0PWM` $2k→$65k in 30 days (59:09, Aug 2026) ·
`oKlhUSSHe2Q` How To Start Day Trading in 2026 (1:14:37) ·
`js25lIZMUSY` Simplest Day Trading Strategy (1:54:59)

---

## 3. Cautions specific to this channel

- **Heavy course/PDF funnel.** Most descriptions gate a "Micro Pullback Strategy
  PDF." Expect the videos to withhold exactly the parameter we want. **Sweep for
  numbers before transcribing.**
- **"$583 → $18M"** — his own channel description says results are not typical.
  Per `source_videos_20260907.md` §4: a headline P/L or win rate without a
  paired reward figure is not a result. **"Highest Win Rate" in a title is a
  flag to check, not a finding.**
- **3,618 videos, largely daily recaps** ("+$100,176 TODAY…"). They show
  execution, not rules. Filter to the named-strategy trainings.
- **`type: playlist` was ignored** by the channel-scoped search — it returned
  videos. Playlists may still exist; try `get_playlist_items` if an ID appears
  in a description, as one did on the last channel.

---

## 4. Next — revised, website first

1. **Read the remaining `warriortrading.com` strategy pages** (§1b). Free, fast,
   denser than the videos. `/bull-flag-trading/` first — it should carry the
   pole and volume conditions the momentum page leaves out.
2. **Then** sweep the videos for what the site does *not* state: the **micro
   pullback's** retracement depth and volume condition. `search_transcript` for
   **numbers** (`percent`, `cents`, `9 EMA`) rather than topic words.
3. Transcribe only the hits, 5-6 per session.

### Actionable already, without another video

- **Bar-count vs percentage pullback** in the bull flag detector. He says 2-3 red
  candles; `config.py` uses a retracement %. Test both.
- **Time-of-day-normalised RVOL** instead of the 10-day flat mean, given
  `consolidated_volume_gap.md` §3.2.
- **State-dependent red-candle exit** (§1b Exits rule 2) as an MCL variant.
- **1m before 11:30, 5m after** — a session-conditional timeframe rule, testable
  against MCL and MC5 on the existing bar cache.
- **Confirm** whether our $500 / 2:1 config was taken from Cameron deliberately.
