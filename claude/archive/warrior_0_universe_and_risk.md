# Warrior 0 — shared universe, regime gate and risk model

**The base document for the Warrior spec set.** The five strategy documents
(`warrior_1_micro_pullback.md`, `warrior_2_flat_top.md`,
`warrior_3_gap_and_go.md`, `warrior_4_reversal.md`,
`warrior_5_selection_in_practice.md`) all assume this one. Read it first; do not
re-state its parameters in them.

Compiled 2026-09-09 from Ross Cameron / Warrior Trading. Supersedes
`claude_warrior_momentum_spec.md`. **Revised 2026-09-10** — see §0.

---

## 0. Evidence status — read before building anything

**Everything here is *stated by the source*. Nothing is measured by us.** Per
`source_videos_20260907.md` §4 these are **hypothesis generators, not results**.

> ### Provenance, confirmed by Ben 2026-09-10
>
> *"MCL was my version of Ross Cameron's strategy. So I guess you can say
> loosely derived."*
>
> **This document is not an independent check on MCL. It is the thing MCL was
> built from.** Two consequences run through everything below:
>
> - **Agreement between this spec and our config is not corroboration.** It is
>   an echo. One source, not two.
> - **Disagreement between this spec and MCL is drift, not design.** Where the
>   two differ, this is the intent and MCL is the deviation — most sharply on the
>   exit, which is why he wins five trades in seven and MCL wins one in three.
>   `HANDOVER_TO_BUILD_20260910.md` §0.

**He is weighted more heavily than any other source in this project**, and the
reasons need stating precisely now that the derivation is confirmed:

1. ~~He trades our exact universe.~~ **This reason is circular and is withdrawn.**
   The universes agree because ours was built from his. It remains true that he
   is one of only two sources in the project trading US small-cap low-float
   momentum longs — but that fact can no longer be used to weight him.
2. **`archive/archive_early_ideas.md` records our bull flag algo as built from
   his style at second hand — and Ben has now confirmed it.** This set replaces
   that second-hand inference with his own numbers, which is its main value.
3. **He is the only source in this project who states both sides of his own
   ledger.** See §6. Every other headline win rate we have collected came without
   a paired reward figure; his does not. **This reason is unaffected by the
   derivation and is now the strongest of the three.**

**What he does not publish, anywhere:** a trade count, a sample period, a
drawdown, or any third-party verification. His own channel carries a
"results are not typical" disclaimer, and he repeats it on camera in both
videos read here. The self-reported metrics in §6 come from his own analytics
software shown on screen, which is better than an unsupported claim and is still
not an audited record.

**A census of 401 videos** (`warrior_census_20260910.md`) since removed
*selection* bias from the source reading — it is a census, not a title-picked
sample — but not *source* bias. Where the census contradicts this document, the
census wins; those points are marked below.

### Sources, and which is which

| Tag | Source | What it is |
|---|---|---|
| **W-MOM** | `warriortrading.com/momentum-day-trading-strategy/` | Universe + bull flag, written, updated 2025-01 |
| **W-BF** | `warriortrading.com/bull-flag-trading/` | The pattern with thresholds |
| **W-GAP** | `warriortrading.com/gap-go/` | The A/B/C grading rubric |
| **W-REV** | `warriortrading.com/reversal-trading-strategy/` | The fade |
| **W-PRE** | `warriortrading.com/premarket-trading/` | Session mechanics only |
| **V-SCALP** | `p1W8Mjl4kWs`, 57:22 — "High Accuracy 1 Minute Scalping Strategy" | **Read in full 2026-09-09.** Main-account method + 9-year metrics |
| **V-3HR** | `A3sbJBOLGuI`, 58:28 — "PROVEN 3hr Day Trading Strategy" | **Read in full 2026-09-09.** Small-account method + five pillars |
| **V-MACD** | `mfGQr2tHoX0`, 21:58 | MACD settings |
| **S3 / S5** | `eTUYXkAr6Pc`, `w2owyBNunDQ` | Read in earlier sessions — see `archive/ema_source_comparison.md` |
| **CENSUS** | 401 videos, all read in full 2026-09-10 | `warrior_census_20260910.md` |

> **A warning about the rest of `warriortrading.com`.** The pages named after a
> specific setup state his parameters. The **general-topic** pages on the same
> domain (`/mean-reversion/`, `/technical-analysis/`,
> `/how-to-build-morning-watchlist/`, `/how-to-use-stock-scanners/`) are SEO
> content: unparameterised, and in two cases describing methods he does not
> trade — `/mean-reversion/` teaches ConnorsRSI and a 90-day linear regression,
> which contradicts everything else here. **Do not treat a number from those
> pages as his.**

---

## 1. The five pillars, and there are two tiers of them

His own framing (V-3HR 4:33). Five criteria, every stock must meet all five.
**He states two different threshold sets** — one for his main margin account,
one for the cash small-account challenge he was running at the time. They are
not a disagreement; they are a deliberate risk-tier split, and the small-account
set is explicitly the higher-win-rate subset.

| # | Pillar | **Main account** | **Small account (3-hour strategy)** |
|---|---|---|---|
| 1 | Price | $0.50–$20 preferred; higher tolerated (traded GameStop at $200–400) | **≤ $9**, no minimum stated |
| 2 | Change on the day | **≥30% preferred, 10% absolute minimum** | **≥50%** |
| 3 | Relative volume | **≥5×** | **≥100× preferred** |
| 4 | News catalyst | preferred, **not required** | **required** |
| 5 | Float | **< 20M** | **< 5M**, "less is exponentially better" |

**He names float as the one pillar he cannot live without** (V-3HR 11:32,
16:33): "if I pull up a stock and the float's 180 million shares I'm not even
going to pull up the chart." His reason is structural rather than statistical —
above roughly that size the name is dominated by high-frequency market makers,
and he argues those algorithms deliberately avoid small caps precisely because a
50–100% daily move carries too much inventory risk for them.

> **The float thresholds are not a fitted parameter.** Six numbers from the same
> man: <100M and "<20M ideal" (W-MOM), the W-GAP grading bands, <50M on the
> watchlist page (**not his — SEO content**), **<10M** "I tend to do better"
> (V-SCALP 16:19), **<20M** main / **<5M** small (V-3HR). Treat as an
> order-of-magnitude hint. The V-3HR pair is the most credible because it is the
> only one stated *conditionally*, with a reason.
>
> **`warrior_5` §3 tightens this from live selection:** he rejects at 18M and
> calls 22M "a little on the higher side", so his **working** ceiling is nearer
> 10M than 20M.

### The screen is deliberately wider than the pillars

V-3HR 23:34: he sets the scanner filters **looser** than his own criteria and
rejects by hand, so that an exceptional name with one bad pillar still surfaces.
**Our screen gates.** This is the fourth independent source in this project
arguing for ranking over gating, after the `oSznkl4ASaA` guest's ADF score,
Shay's colour-coding, and W-GAP's A/B/C rubric.

---

## 2. Relative volume — he uses two different definitions, and one exception

**This is the single most important definitional item in the set, because our
own RVOL is a third thing again.**

| Source | Definition |
|---|---|
| **W-MOM** | "current volume for today compared to the average volume **for this time of day**" |
| **V-SCALP** 12:04 | "the volume is five times higher than its **14-day average**" — a flat daily mean |
| **ours** (`common/screen.py`) | `volume_today / mean(volume, prior 10 days)` — a flat daily mean, 10 days |

Our construction matches V-SCALP, not W-MOM. `consolidated_volume_gap.md` §3.2
found ours is substantially noise. **The time-of-day-normalised denominator is
therefore worth testing on its own merits** — it is a different metric, not a
tuning of the same one, and it is the one his written strategy specifies.

### The continuation exception — codeable, and it cuts against a hard RVOL floor

V-SCALP 12:32. A name that has been strong for several days has its **own recent
volume in the denominator**, so its RVOL reads low even while it is the most
active thing on the tape. He shows ZPP at RVOL 4 — below his own 5× floor — and
trades it anyway, calling it a *continuation setup*.

> A trailing-average RVOL denominator is **self-defeating on exactly the
> multi-day runners this universe exists to find.** Same failure mode as the
> 6,000-share volume floor that removed ~$872 of MCL winners against ~$115 of
> losers. **Any RVOL gate needs a continuation carve-out or it will reject day 2
> and day 3 of every good name.**

### His alternative construction — the volume imbalance

V-3HR 9:05, offered as a "bonus" criterion and mechanically cleaner than RVOL:
**prior session volume very low (his example: under 100K) and today's volume
enormous (20M+).** He shows a name that traded 227K two sessions back and 34M on
the day.

This is a **ratio between two specific sessions**, not against a trailing mean,
so it does not decay as the runner extends. Computable from the existing bar
cache with no new field.

---

## 3. Session windows — and they differ per tier

| Strategy | Window | Source |
|---|---|---|
| Main account, momentum | **09:30–11:30 ET**, most active in the first hour | W-MOM |
| Main account, timeframe rule | **1-minute before 11:30, 5-minute after** | W-MOM |
| **Small account, 3-hour** | **07:00–10:00 ET, hard stop.** "If I haven't taken a trade by 10 a.m. I will not take any trades that day" | V-3HR 18:34 |
| Gap and Go | most opportunity **09:30–10:00 ET** | W-GAP |
| Pre-market session | 04:00–09:30 ET, activity concentrated **07:00 onward** | W-PRE |

> **Timezone is inferred, not stated.** He never says "ET" for the 07:00–10:00
> window. Warrior Trading operates on US Eastern and the window is coherent with
> a pre-market-into-open strategy, so ET is the reasonable reading — **but treat
> it as an assumption.**

**The census settles the behaviour even if not the timezone label.** Of 87
recaps stating a first-trade time: **50 in the 07:00 hour, 17 at 08:00, 13 at
09:00, 7 at 06:00, and nothing at 04:00 or 05:00 in 401 videos.**

**MCL's window is 04:00–09:30 ET.** His is 07:00–10:00. MCL's **04:00–06:00
block is −$2,166 against a −$1,270 total** — so the hours MCL arms in and he
does not are also the hours it bleeds. In-sample, needs registration, but given
§0 this is a drift worth measuring rather than a difference of opinion.

### The session-conditional timeframe is the sharpest claim here

Third independent source pointing 1m → 5m, after Shay (`gn02_Ic9i5U`) and the
EMA comparison's D2 — but **his version is conditional on time of day rather
than a blanket preference**, which makes it a narrower and more testable claim.
It fits `session_aware_screening.md` directly.

---

## 4. The regime gate — front side and back side

**This gates every strategy in the set and it is the most consistently repeated
rule in both transcripts.** He returns to it perhaps a dozen times.

**Front side** = from the moment the catalyst hits until the first MACD
crossover (V-3HR 37:34: "the front side of the move is from when news comes out
until we have our first MACD crossover"). The first leg on the front side is
"usually where I do the best."

**Back side triggers — any one of these ends it** (V-SCALP 30:32–32:02):

| Trigger | Wording |
|---|---|
| MACD crossover down | "when the MACD crosses over… we just sit on the sidelines and wait" |
| Moving-average crossover | "a moving average crossover" |
| **Close below the 20 EMA** | "once we broke below that 20 exponential moving average there is no doubt that this is the back side" |

**On the back side he takes no trades at all.** Not smaller size — none. "Leave
it alone, stop, wait for the next setup, wait for the next time either this
stock goes back to the highs… or wait for the next stock."

> **MCL has `REQUIRE_MACD_POSITIVE = True`, which is the same idea.** What MCL
> does **not** have is the 20-EMA close as a second, independent back-side
> trigger, nor any concept of the move being *over* as distinct from a position
> being stopped. This is a cheap variant and it is his most-repeated rule.

> **Census caveat, and it is a real one.** Across 317 recaps, `back_side` has a
> red-day lift of **1.1×** — he trades the back side about as often on good days
> as bad. His *stated* rule is emphatic; his *measured* behaviour says breaking
> it is not what turns a day red. Build the gate for the mechanism, not because
> the census supports it, because the census does not.

**There is a separate, market-wide regime gate that the census does support and
that is worth far more.** Hot days average $46,481 and cold days $2,835 — a 16×
difference, with cold making up 61% of the sample. See
`warrior_census_20260910.md` §4.

### Indicators, and he argues against tuning them

| Indicator | Setting | Source |
|---|---|---|
| MACD | **12 / 26 / 9, platform default** | V-MACD 6:19 |
| EMA | **9, 20, 200** | S3, S5, V-SCALP |
| SMA | 200, daily chart only | S3 |
| VWAP | standard | S3 |
| RSI | "standard indicator settings" | `iS5lvJGMM8E` 5:31 |

V-MACD 6:59 gives the reason and it is a Schelling-point argument, not a
performance one: "you want to see the same signals that everyone else sees… you
might be the only person in the world using these settings." He compares it to
traffic signals — the value is that every driver reads the same red light.

> **Do not sweep indicator periods per symbol.** If the mechanism is
> self-fulfilling coordination, per-name optimisation destroys the thing that
> made it work and fits noise instead. `archive/ema_source_comparison.md` D6
> reached the same conclusion, and two of this project's own failed experiments
> (the 6,000-share floor, the 5-bar arming window) failed by relaxing a rule
> whose restrictiveness was doing the work.

---

## 5. Risk model

### 5.1 The stop — his rule, and our measurement of it

The written pages say **stop = the low of the pullback**. On camera he says the
opposite. Both transcripts, read in full, reconcile them:

> **V-SCALP 34:03:** "I set a tight stop. **I don't stop at the low of this
> pullback, that's too far.** I use an arbitrary stop generally of 10 to 15
> cents, because I don't want my average losers to be bigger than that."

> **V-3HR 45:31**, on a different trade: "your max loss on this is the low of
> this pullback which is around 740" — an 11c stop on a $7.51 entry — "it's a
> little bit of a bigger stop, which is not ideal."

**His rule is:**

```
stop_distance = min(structure_stop, cents_cap)
    structure_stop = low of the pullback / bottom of the bottoming tail
    cents_cap      = 10-20c, and he uses 15c most often
```

**The cap is calibrated to his own average loser, not to the chart.** He is not
deriving a stop from market structure and accepting whatever it costs; he is
asserting a maximum loss he will carry and rejecting any setup wider than it.

> ### MEASURED AND REJECTED, 2026-09-10
>
> This was called "the single largest structural difference between his method
> and our code" and was tested first for that reason. **The cent stop loses at
> every value tested — 10c, 15c and 20c — the loss shrinks monotonically as the
> cap loosens, and the boundary check fails because the best cell sits at the
> edge of his stated range.** The gradient points away from cents entirely, not
> toward an untested cent value. `cent_stop_decision.md`.
>
> The arithmetic explains it: across a $2–20 band, 15c is **7.5% at $2 and 0.75%
> at $20**. On his 10,000-share size a 15c stop is a $1,500 risk unit; at our 100
> shares it is $15, of which the measured $4.26 round-trip friction eats 28%.
> **The rule is his, and it does not survive the transplant. Do not re-open it.**

**The corollary is a screen filter and it was not rejected** (V-SCALP 20:04): if
the stock cannot plausibly move 30c he does not take it, because he captures at
best half a move and his average winner is 14c. And V-SCALP 21:04: he abandoned
ZPP mid-session *because the spread was 18–20c* and he could not hold a 15c stop.
**Spread is an entry gate for him.** `PROGRAM_INDEX.md` §7 item 7 already wants
one; this is an independent practitioner using one.

### 5.2 Targets — three different statements, unreconciled

| Source | Target |
|---|---|
| W-MOM / W-BF | **2:1** — prefers a 20c stop / 40c target to a $1.00 stop / $2.00 target |
| V-SCALP 25:02 | first profit target **15–20 cents** |
| V-3HR 32:34 | **high of day**, then scale out at the next half or whole dollar |
| V-3HR 52:03 | small account: **20c profit on 10c risk** = 2:1 |

**Still genuinely unresolved.** 2:1 and "first target 15–20c against a 15c stop"
are not the same rule. Note that §5.1's rejection removes the cent stop these
targets were scaled against, so the target question has to be re-posed against a
percentage stop before it can be answered at all.

### 5.3 Exits — three rules, and rule 2 is state-dependent

From W-MOM, and consistent with both transcripts:

1. **Sell half at the first target**, then move the stop to **breakeven** on the
   remainder.
2. **If half is not yet sold, the first candle to close red is the exit.** If
   half *is* sold, hold through red candles while the breakeven stop holds.
3. **Extension bar** — an outsized spike — sell into it.

> **This is the biggest untested gap in the whole spec set, and §0 is why.**
> MCL trails at 5%; he takes half off at a target and moves the rest to
> breakeven, and never trails. **That single difference produces the
> 32.4%-versus-71.1% win rate** — 2,212 of MCL's 2,413 exits are the trail at
> −$1.2 each, and only the 201 that reach `window_close` make money. If MCL was
> meant to be his strategy, the exit is where it stopped being one. **Nothing in
> this project has tested his exit as specified.**

**Additional discretionary exit indicators**, V-SCALP 49:04:

- **Green candles getting progressively smaller** — codeable as a decreasing
  sequence of green-candle ranges.
- **Topping tail, doji, shooting star, gravestone doji** — codeable as an
  upper-wick to body ratio.
- Big sellers on level 2, or a burst of red on the tape. **Not codeable.**
- **"Breakout or bailout"** — if price does not move up immediately, the timing
  was wrong; exit.

> **Do not implement "breakout or bailout" as a bar count.** A maximum hold time
> was measured and rejected 2026-09-10: every cap loses, the loss shrinks
> monotonically as the cap loosens, and the boundary check fails
> (`hold_cap_decision.md`). His rule is a discretionary read of whether price is
> moving; an N-bar cap is not the same object.

### 5.4 Sizing

| Context | Rule |
|---|---|
| General | **risk ÷ stop distance.** 20c stop, $500 max risk → 2,500 shares (W-MOM) |
| Main account, historical | average **10,000 shares**; range **3,000–20,000** across a day |
| Main account, current | reduced to **250–500 share** clips "in a lighter volume market" (V-SCALP 51:03) |
| Small account | full buying power, **one entry and one exit**, target 20c on 10c risk |
| Scale-up rule | **one trade a day until the account is over $25,000**; then increase *position size* on A-quality setups before increasing trade *count* (V-3HR 52:03) |

> **The $500 / 2:1 figures are a teaching example, not a considered parameter.**
> `/position-sizing/` states his size runs 3,000–20,000 shares; the W-MOM worked
> example gives 2,500, below his own stated floor. **And per §0 our `config.py`
> matching those figures is now most likely inheritance rather than agreement —
> it cannot be cited as corroboration in either direction.**

**The one sizing rule the data does support** is asymmetric position
construction: his winners carry **1.36×** the shares of his losers because he
scales into winners and never gets the chance on losers. Ben's real trading is
**0.80×** — he adds to losers. `execution_gap_20260910.md` §1.

**A setup-quality sizing ladder is stated but never quantified** (V-3HR 51:32):
A-quality 85–90% accuracy, B ~70%, C 50–60%; grow by sizing up A setups first.
No rule for assigning the grade. Recorded, not buildable.

---

## 6. His self-reported performance — the one source that states both sides

**Main account, "nine years of trading history" (V-SCALP 18:03–19:03, 52:33),
from analytics software shown on screen:**

| Metric | Value |
|---|---|
| Accuracy | **68.5%** |
| Average winner | **14c/share**, ≈ **$1,400** |
| Average loser | **18c/share**, ≈ **$1,500** |
| Average share size | ~10,000 |
| Implied P/L ratio | **0.93 in dollars**, 0.78 in cents |
| **Breakeven win rate** | **51.8%** in dollars, 56.2% in cents |
| **Margin over breakeven** | **~12–17 points** |

He corrects himself mid-video — he says 15c, then checks and says the average
loser is really 18c — and notes his losing positions carry *smaller* share size
than his winners, which he reads as lower conviction going in.

> **Apply the project's standing rule and he passes it.** `p = R/(R+1)`. Every
> other headline win rate this project has collected came without a paired
> reward figure, or with one that left a two-point margin (Eduardo, 77% against
> 3:1 adverse). His is the first that clears breakeven with room. **That is not
> verification — it is self-reported — but it is a materially better-formed
> claim than anything else in the source set.**

**A fuller year, from `Lin4WAwzPNY`:** 2025 was 3,300 trades at **71.1%**
accuracy, average winner 18c/$3,500, average loser 15c/$2,100, **P/L ratio
1.68:1**; 2024 was 5,400 trades at 65.5% and 1.5:1.

**Small account, 9 days (V-3HR 56:02):** 90% win rate, $622 average winner, $154
average loser, 4:1 P/L. **n ≈ 9 trades.** By this project's own "an n = 1
measurement is not a constant" rule, this is not a sample and should not be
quoted. He says so himself.

---

## 7. Two universe filters we do not carry at all

**7.1 The daily-chart trust check** (V-3HR 17:34). Before trading a name he zooms
out on the daily and rejects it if it has a history of popping and giving the
whole move back. His CNE example: up ~300% two weeks earlier, fully retraced —
"that's a little shady… if it had gone up 300% and held that level, that'd be
different."

> **Measured 2026-09-10 and partly supported.** His fine-grained
> runner-versus-pump split is not supported, but the cruder "did it ever run at
> all" split is: any-prior-spike is **+$4.67/trade against −$3.22**, positive
> after drop-top-3 and same-signed in both halves. `prior_spike_result.md`.
> **Not to be turned on** — nothing there is out of sample yet.

**7.2 Half-dollar and whole-dollar levels.** Both transcripts treat these as the
dominant intraday structure — "most stocks trade with a great deal of respect to
half dollars and whole dollars" (V-3HR 42:33). He shows resting size stacked at
$6.00, $7.50 and $8.00 on the same name all morning, and describes the space
*between* levels as traversed fast because there are no orders there.

> This makes his entries partly a **price-grid** problem rather than a
> pattern-matching one, and it is trivially computable — no new data, just
> `price mod 0.50`. **But the census puts `half_whole_dollar` at a 1.3 red-day
> lift on 94 mentions** — slightly over-represented on losing days, so treat it
> as a level map rather than as an edge.

**Also not carried:** short interest (>10% ideal, W-GAP) and **"former runner"**
status. The latter is §7.1 and is now measured.

---

## 8. Before any of this becomes code

Per §4 of `PROGRAM_INDEX.md` — state the bar before the result, and register
before you run.

1. **Nothing in this set has been measured by us** except where marked. Every
   remaining parameter is a hypothesis and inherits the pre-registration rule.
2. ~~The fixed-cent stop is the first thing to test.~~ **DONE — rejected.**
   §5.1, `cent_stop_decision.md`. **The exit shape (§5.3) is now the largest
   untested gap**, and §0 is why it matters: MCL was meant to be this method.
3. **Do not port the $500 / 2:1 figures as corroboration** (§5.4) — per §0 they
   are most likely inherited.
4. **Resolve the target rule** (§5.2), and re-pose it against a percentage stop
   now that the cent stop is gone.
5. **Any RVOL gate needs the continuation carve-out** (§2) or it rejects day 2
   of every runner.
6. **The 07:00–10:00 ET window is an inferred timezone** (§3) — but the census
   makes the *behaviour* unambiguous: nothing before 06:00 in 401 videos.
7. **Selection bias is unchanged** in the source's own demonstrations. He shows
   every rule on charts chosen after the fact. The census fixes which *videos*
   were read, not which *charts he chose to show*.
8. **Read `warrior_census_20260910.md` §9 before picking what to build.** The
   regime gate outranks everything in this document.
