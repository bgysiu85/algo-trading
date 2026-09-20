# MA-TREND — moving-average trend continuation, RTH

**Spec written 2026-09-16 in the research chat. No code exists and none should
be written until §8 is satisfied.** Synthesised from `2e4WayvjLJo` plus five
further videos from the same channel read in full 2026-09-16
(`source_videos_20260907.md` §12), with every blank the source leaves filled in
here and marked as ours rather than his.

> **Revision, same day — the channel pass supplied seven real numbers** and they
> replace guesses in §3.5, §3.8, §4, §6 and the new §6b. It also supplied the
> author's own verdict on this exercise, which belongs at the top:
>
> > *"That's why it's not really possible to program this strategy… because
> > there's so many criteria that go into identifying a high probability
> > breakout or retracement from a low probability one."*
>
> **He is describing the ceiling on this document.** A faithful implementation
> is not available; what §9 tests is a *specifiable subset*, and a failure
> cannot distinguish "the idea is wrong" from "the subset is not the idea."
> That limitation is registered here rather than discovered afterwards.

| | |
|---|---|
| Universe | $2–20, the point-in-time screened set — **same as ORB**, §2 |
| Direction | **Long only** initially; the short side measured and reported, not traded |
| Session | **09:45–15:55 ET.** Not pre-market — §8.2 says why |
| Indicators | **EMA9, SMA20, SMA200** on price, and nothing else |
| Setups | **retracement** and **base break**, both continuation |
| Bars | 1m / 2m / 5m / 15m, with a session-conditional map as one cell |
| Deliverable | this spec; §9 go/no-go fixed **before** any code |

> **Read §8 first.** Three of this document's requirements are not currently
> met, and one of them is a data-integrity defect sitting inside the window.
> §8 is not a caveats appendix — it is the gate.

---

## 1. What the source gives and what it withholds

**Given:** three moving averages; two setups; eight state gates in words; a
session→timeframe map; an entry trigger demonstrated once (*"I timed my entry
above this doji bar… and placed my stop loss below the doji bar"*); a target
(the SMA200).

**Withheld or unquantified — the blanks this document fills:** the slope
measure, the slope band, the extension threshold, what counts as a touch and
over what lookback, what "accelerated" means, what "first retracement" means,
which timeframe governs which decision, the sizing, and every exit other than
"target the 200."

**And one thing he states that cannot be coded at all.** *"Ideally you have a
45 degree slope."* Slope in degrees is a function of the chart's price-axis
scaling and bar width; the same series renders at any angle you like. §3.2
replaces it.

---

## 2. Universe and session

Identical to `orb_strategy_spec.md` §3 — the point-in-time screened set, price
band enforced at entry, test symbols excluded, `first_seen` floor honoured.
Reusing ORB's universe is deliberate: it makes MA-TREND and ORB comparable on
one tape, and it inherits ORB's leak cut, which **passed** at 84% (rejects
trigger at 52.2% against survivors' 62.1%).

**RTH only, 09:45–15:55 ET, flat at the close.** The source's own session map
starts at 09:30. We start at 09:45 for the same reason ORB does: before that the
SMA20 on any intraday timeframe has fewer than 20 bars of the session and is
carrying the prior day.

---

## 3. The gates, defined so they can be computed

Every definition below is **ours**. Each is stated so that a different
implementer gets the same number.

### 3.1 Structure

```
long_structure  =  EMA9  > SMA20  and  close > EMA9
```
evaluated on the **signal timeframe** (§5). The source's "SMA20 below price and
rising" is the conjunction of this and §3.2.

### 3.2 Slope — scale-free, replacing "45 degrees"

```
sigma_bar   = stdev of 1-bar log returns over the trailing 60 bars
slope20_n   = ( SMA20[t] / SMA20[t-k] - 1 ) / ( k * sigma_bar )        k = 5
```

Dimensionless, invariant to price level, bar width and axis scaling. **The band
is not assumed.** `slope20_n` is bucketed into quintiles over the population and
the band is read off the result — the source's claim is only that the
relationship is **non-monotone with an interior optimum**, and that is the
hypothesis, not the threshold.

> **This is the central hypothesis of the document.** `ma20_slope` was measured
> at **1.37×** and `ma20_dist` at **1.46×** against a **1.86×** break-even
> (`entry_split_result_20260914.md`) — but those were read directionally, and
> `REGISTERED_bar_shape_20260916.md` is explicitly *"median split, HIGHER IS
> BETTER"*. **A middle-is-best optimum is invisible to a monotone test.** If the
> quintile profile is monotone, this strategy has no premise and §9 should not
> be reached.

**Free pre-check, and it runs before anything else:** re-read the existing
`entry_split` quartile tables for an interior peak. No new run, no new data. If
there is no interior peak anywhere in the trend family, **stop here**.

### 3.3 Flat-MA veto

```
skip if  |slope20_n|  <  SLOPE_MIN                      (candidate: 20th pctile)
```

### 3.4 Extension

```
ext_n = ( close / SMA20 - 1 ) / sigma_bar
skip if ext_n > EXT_MAX                                 (candidate: 80th pctile)
```

**`ext_n` and `slope20_n` are ONE family, not two.** `entry_place_built_20260915.md`
makes this rule explicit for `ema9_dist`: *"counting it separately would inflate
one idea into two."* The multiplicity count in §7 treats trend as one family.

### 3.5 Touches — registered two-sided, deliberately

```
touches(W) = count of bars in the last W where  low <= SMA20 <= high     W = 60
require touches >= TOUCH_MIN                                    TOUCH_MIN = 2
```

**`TOUCH_MIN = 2` is his, stated:** *"you want to make sure that the trend
you're looking at has at least two touches on these moving averages… respected
either the nine EMA or the 20 SMA at least twice, then you can begin trading off
of it."*

**But the direction is contested three ways and he is on both sides of it.** In
`2e4WayvjLJo` he says *"as many touches as possible… the more touches, the more
reliable"*; in `bwJc32pCFYM` it is a floor of two. `source_videos_20260907.md`
§2.3 — three converging sources — says **first touch only**, with a mechanism:
retests decay as trapped participants exit.

> Registered as a **two-sided** test with no pre-committed direction, because
> the source contradicts itself and an independent source family predicts the
> opposite sign. This costs a factor of two in the multiplicity budget and that
> cost is paid explicitly rather than hidden.

> Registered as a **two-sided** test with no pre-committed direction, because
> two independent source families predict opposite signs. This costs a factor of
> two in the multiplicity budget and that cost is paid explicitly rather than
> hidden.

### 3.6 Acceleration veto — "skip the first retracement"

```
accelerated[t] = slope20_n[t] is in the top decile of its own trailing 100 bars
retracement    = first bar closing back inside [SMA20, EMA9] after >= M bars
                 closing above EMA9                                     M = 3
veto           = skip retracement #1 in an episode that began accelerated;
                 take #2 onward
```

An episode ends when price closes below the SMA20.

### 3.8 Retracement depth — the golden zone, and the best find in the channel

```
depth = ( swing_high - retrace_low ) / ( swing_high - swing_low_of_impulse )
require  DEPTH_MIN <= depth <= DEPTH_MAX          candidates: 0.40 and 0.60
```

His, stated twice and quantified: *"I always want to see a 40 to 60%
retracement… I want to see it retrace into this area, which is like 40 to 60% of
the first rally. And I call that the golden zone."* Counter-example given: *"it
retraced over 100% of this move… usually not a good quality."*

> **This is the third independent arrival at the same band**, and the other two
> are already in this project:
>
> | source | band |
> |---|---|
> | V4 / Raghee Horner, `orb_strategy_spec.md` §5.3 `RETEST_MODE = zone` | **38–62%** of the range |
> | Reddit ORB+fib post, `orb_retest_depth_20260916.md` | 50% and 61.8% |
> | **this source** | **40–60%** of the impulse |
>
> Three unrelated practitioners, one band. **And the anchor disagreement is the
> same one `orb_retest_depth` §2 identifies** — Raghee measures the retracement
> of the *opening range*, these two measure the retracement of the *impulse*.
> That is the `zone_impulse` cell already proposed for ORB.
>
> **So this parameter should not be swept independently here.** Whatever ORB's
> §10.3 count returns for `zone` against `zone_impulse` governs both documents.
> One measurement, two consumers.

### 3.7 SMA200 — target and overhead veto

```
skip if  ( SMA200_daily - entry ) / entry  <  MIN_HEADROOM     (candidate: 1.5 R)
target_1 = SMA200_daily
```

**The SMA200 requires full-day bars and does not currently exist — §8.1.**

---

## 4. Entries

**Setup A — retracement.** After §3.1–3.6 and §3.8 hold, the signal bar is the
first bar that closes back inside `[SMA20, EMA9]` **and is one of three shapes**
— his, stated: a **narrow-range bar**, a **doji**, or a **bottoming tail**
(topping tail on the short side):

```
narrow_range : (high - low) <= NR_MULT * median(high-low, prior 20 bars)   NR_MULT = 0.6
doji         : |close - open| <= DOJI_MAX * (high - low)                   DOJI_MAX = 0.25
bottom_tail  : (min(open,close) - low) >= TAIL_MIN * (high - low)          TAIL_MIN = 0.5
```

The three thresholds are **ours**; the three shapes are his. Note these are
`close_in_bar` and `body_ratio` under other names — the columns
`REGISTERED_bar_shape_20260916.md` is already testing. **If that registration
fails, this clause is unlikely to add anything**, and the spec should say so
before the run rather than after.

**When several qualifying bars cluster**, his rule is explicit: *"find the
highest one. You want to place your entry above the highs of all four of these
entry bars."* So the trigger level is `max(high)` over the contiguous run of
qualifying bars.

Entry is a **stop order at `trigger_level + 1 tick`**, valid for
`ENTRY_VALID_BARS` (candidate 3) bars. **He states no buffer and no order type
in any of the six videos**; both are ours.

**Setup B — base break.** After §3.1–3.6 hold and price has held a range of
width `< BASE_MAX_PCT` for `>= BASE_MIN_BARS`, entry is a stop order at
`base_high + 1 tick`.

**One entry per symbol-day by default.** Adds are the source's practice and this
project has rejected pyramiding twice (`mcl_rejected_mechanics.md`); `ADDS = 0`
is the baseline and `ADDS = 1` runs as a single cell, never as the default.

---

## 5. Timeframes

| ET | signal | confirm |
|---|---|---|
| 09:45–10:00 | 1m | 2m |
| 10:00–12:00 | 2m | 5m |
| 12:00–16:00 | 5m | 15m |

**Alignment cell** (his, optional): require `|SMA20(signal) − EMA9(confirm)| /
close < ALIGN_EPS`.

**The map is one cell and a fixed 5-minute bar is the control.** It is a
parameter set from a video, not a finding — but it is the **fourth independent
arrival** at a session-conditional timeframe and the **second** that makes it
conditional on time of day (Cameron: *"1-minute before 11:30, 5-minute after"*,
`warrior_0` §3). That is why it is a cell and not a footnote.

---

## 6. Stop and exits

**Stop:** `low(signal) − 1 tick`, gap-through honoured (`gap_fills=True`, peak
seeded from the entry price — `PROGRAM_INDEX` §1). `R = entry_fill − stop`.
**Report `R / entry_price`, median and p90, in the pre-flight** — ORB's own
pre-flight eliminated `STOP_MODE = opposite` on exactly this measurement before
a line of entry logic existed.

**Exits, all in one pass:** `prior_high` (**his stated target** — *"the prior
high was target"*); `sma200` (his target when no prior high is overhead); `r_2`;
`trail_pct = 5.0` (the rule this project actually ships); `ema9_close` (exit on
the first close below the EMA9 on the signal timeframe); `session_close`.

**`bar_trail` is his actual demonstrated exit** and is added as a sixth cell:
*"I went bar by bar on the five. So I just raised my stop loss to every
candlestick's low until it took my stop out."* A per-bar structure trail is not
the same object as a percentage trail and this project has never run one.

`ema9_close` is included because a signal exit fills at the reference
(`gradient_reversal` **$0.0000/share**) while a stop fills through it
(**−$0.0563/share**) — the exit *mechanic* carries a friction advantage
independent of the P&L path.

---

## 6b. Sizing and the live-path risk rules — new, from the channel pass

**Fixed dollar risk, size derived from the stop.** His, with the formula stated
and worked twice: *"Share size equals risk divided by entry minus stop-loss
price… $100 risk divided by $5 entry minus $4.80 stop… $100 divided by 20 cents,
which is about 500 shares."*

> **Fourth independent arrival at variable-stop-normalised sizing**, after
> Tori (§2.6, contracts halved when the stop is far), Nill (§9.2, *"sometimes I
> have a stop from 30 points sometimes from 200 points and then I decide how
> many contracts I take"*), and Graystone (§11.2, *"reduce the position size so
> that the monetary risk stays the same"*). **It is the single most corroborated
> mechanic in the whole source collection and this project has never tested it**
> — `sizing_and_capacity.md` compared flat-100 against capital-based, not
> against risk-normalised.
>
> Report it as a **third sizing model** beside flat 100 and capital-based.
> `sizing_and_capacity.md` found capital-based sizing can flip a strategy's
> sign; expect the same sensitivity here and read the price-decile table before
> concluding anything.

**A stated R floor, used as a rejection rule:** *"It's less than 2:1 R-to-R
because I'm risking 15 cents to make 20 cents. It doesn't make sense."* So
`MIN_R_TO_TARGET = 2.0`, evaluated at entry against `prior_high`. This is a
**pre-trade veto computable from knowable quantities**, which is rarer than it
sounds — `PROGRAM_INDEX` §4 requires discrimination on features knowable *at*
entry.

**Two live-path rules, not backtest parameters.** These govern the trader, so
`PROGRAM_INDEX` §4 parity applies — whatever the backtest enforces the live path
must, and vice versa:

| rule | his words |
|---|---|
| **halve risk after a losing streak** | *"If you have two to three consecutive losing days in a row, then you have to lower your risk by 50%… from $100 to $50"* |
| **restore only after three green days** | *"you don't re-raise it until you have three consecutive green days in a row"* |
| **give-back cap** | *"You have to protect at least 50% of the profit that you make on a day-to-day basis. You cannot give back more than 50%"* |
| never add to a loser | stated flatly |

These belong with `execution_gap_20260910.md` §7 item 3 — the daily loss stop,
where **−$2,000 recovers $55,083, 48% of Ben's total loss**. The give-back cap
is a different instrument aimed at the same failure Cameron's census ranks as
most-cited (`didnt_bank_green`, lift 1.5×), and **a state-dependent risk ladder
is not the same thing as a daily stop** — it should be measured as its own arm.

---

## 7. Parameters, and the multiplicity budget

| name | candidate | calibrated? |
|---|---|---|
| `SLOPE_MIN` / slope band | quintiles | **NO** — §3.2 sets it |
| `EXT_MAX` | 80th pctile | **NO** |
| `TOUCH_W`, `TOUCH_MIN`, direction | 60, **2** (his), **two-sided** | **NO** |
| `DEPTH_MIN` / `DEPTH_MAX` | **0.40 / 0.60** (his) | **governed by ORB §10.3** |
| `NR_MULT`, `DOJI_MAX`, `TAIL_MIN` | 0.6 / 0.25 / 0.5 | **NO** — shapes his, thresholds ours |
| `MIN_R_TO_TARGET` | **2.0** (his) | **NO** |
| sizing model | flat-100 / capital / **risk-normalised** | report all three |
| `ACCEL_DECILE`, `M` | top 10%, 3 | **NO** |
| `MIN_HEADROOM` | 1.5 R | **NO** |
| `ENTRY_VALID_BARS` | 3 | **NO** |
| `BASE_MAX_PCT`, `BASE_MIN_BARS` | — | **NO** |
| `ALIGN_EPS` | — | **NO** |
| timeframe map vs fixed 5m | map | **NO** |
| `EXIT_MODE` | five | **NO** |
| `ADDS` | 0 | baseline |
| `PRICE_MIN/MAX` | 2.0 / 20.0 | **mandatory** |

**Twelve of sixteen are uncalibrated**, and four now carry a number he actually
stated rather than a guess of ours — `TOUCH_MIN`, `DEPTH_MIN`/`DEPTH_MAX`,
`MIN_R_TO_TARGET`, and the sizing formula. Worse than ORB's fifteen of twenty in
proportion, and the honest reason is the same: the source specifies almost no
numbers.

> **The search space is the risk, and it is pre-committed here.** Two setups ×
> slope band (5) × extension (2) × touches (2 directions) × accel veto (2) ×
> alignment (2) × exits (5) = **800 cells** before the timeframe map. §9's
> standard applies with force: **report where the chosen cell sits in the
> distribution of cells**, and **run the equal-weight ensemble** — ReSolve's
> 1,226 GEM variants had the published spec beating only 61%, and the ensemble
> drew down 13.2% against the median single spec's 17.4% at no cost.
>
> **A primary cell is named before the run:** slope quintile 3, `EXT_MAX` at the
> 80th percentile, touches two-sided and reported both ways, accel veto ON,
> alignment OFF, `EXIT_MODE = trail_pct`, the timeframe map. Everything else is
> the distribution, not a candidate.

---

## 8. THE GATE — three things that are not currently true

### 8.1 The SMA200 does not exist on this cache

`entry_place_built_20260915.md`: the archive holds **04:00–09:30 slices only**,
so `ema200_dist` on the 1-minute view is a 200-bar mean of **pre-market only**,
and on the 5-minute view *"it does not exist here and is reported **absent**."*
A daily SMA200 needs full-day bars.

**§3.7 and the `sma200` exit cannot be computed until full-day `ohlcv-1m` is
pulled.** Do not approximate it from the pre-market slice; that is a different
quantity wearing the same name.

### 8.2 The tape has an undiagnosed defect inside the window

`pullback_break_v2`–`v6` carry an open item: **two price scales interleaved on
259 symbol-days**, with **290 trades moving more than 25% in a single bar, 235
of them in the 08:00 hour**. The v6 verdict is explicit:

> *"Stop tuning; diagnose the 08:00 interleaved-price defect; scope the data the
> tape lacks."*

**Any strategy run on this tape inherits it.** A trend-continuation rule reading
moving averages is *more* exposed than a break rule, because one bad print
poisons the MA for the next twenty bars.

### 8.2b The source contradicts itself on five points

Found by reading six videos rather than one. None is fatal on its own; together
they say the method is **held in the operator's head, not in the rules**, which
is also what he says himself (see the banner at the top).

| # | contradiction |
|---|---|
| 1 | **Two indicators or three.** *"Those are the only two indicators that I use"* against *"I use the 20 SMA and I also use the 200 SMA, but I also use the 9 EMA."* |
| 2 | **"20 EMA" said repeatedly for what he sets up as a 20 SMA**, across two videos. The setup instructions are unambiguous; the narration is not. **An implementer following the spoken word builds a different indicator.** |
| 3 | **Touch count**: *"as many touches as possible"* against *"at least two touches."* §3.5. |
| 4 | **Reversals**: *"I do occasionally trade reversals"* against a framing in which eliminating reversal trading was the original breakthrough. |
| 5 | **Earnings**: titles claim **$34,194/month** and **$18,432/month** four weeks apart; in-video claims are *"just shy of half a million dollars in 2025"* and *"$700,000 from mid 2024 to late 2025."* Neither monthly figure is derivable from the annual ones. |

### 8.2c The evidence base, counted

Across six videos: **15 winning or neutral worked examples against 1 losing
one.** Only one video shows a loss at all — BYND, about $1,000: *"I really sized
up on this trade… I thought it was super high probability… and unfortunately, it
just didn't work."*

That single loser is the most informative example in the set, because it is a
loss on an **upsized, high-conviction** trade — which is the failure Cameron's
401-recap census ranks first by lift (`oversized`, present on **46.2% of red
days against 7.2% of green**). The one loss he shows is the archetype.

**No win rate, no sample size, no trade count, no average loss and no drawdown
appear in any of the six videos.**

### 8.3 The prior is poor, and it should be stated before the run, not after

- **Six registrations, six NOTHINGs** on the pullback line
  (`pullback_break` v1–v6), best case **(9.90)/trade at $4.26**. None of them
  used any of this source's components — no EMA9, no price SMA20, no SMA200, no
  slope, no extension, no touch count, no alignment — so **this is genuinely
  untested**. But it is the same *family* of idea on the same universe, and that
  family has just failed six times.
- **All of this source's features were individually measured below the bar** —
  1.37× and 1.46× against 1.86× needed.
- **MCL loses ~$6.26/trade gross of all friction**, so the universe itself has
  yet to show an edge any rule can harvest.

**The premise that survives all of that is narrow and specific: that the edge is
in the *shape* of the relationship (an interior optimum) and in the
*conjunction*, neither of which has been tested.** If §3.2's free pre-check
finds no interior peak, the premise is gone and nothing below should be built.

---

## 9. Go/no-go — fixed before any code exists

Ships to paper only if **all** hold, in the primary cell of §7, flat 100 shares,
honest fills:

1. **Net positive after drop-top-3 AND drop-top-5**, on the level and on the
   delta against a no-gate control.
2. **Breadth** — the sample-size-independent test that replaces ORB §11
   criterion 2. **That replacement must be decided and written down before this
   runs**, and applied to MC5 in the same pass, exactly as
   `orb_strategy_spec.md` §11.1 requires.
3. **Net ≥ $1.00 per trade at flat 100 shares**, reported at all three friction
   levels ($1.00 / $4.26 / $8.92).
4. **≥ 100 trades**, and **≥ 60 sessions** — the sample is sessions, not trades.
5. **Positive in both halves** of a temporal holdout split at the median date,
   split point not swept.
6. **No optimum on a grid boundary.**
7. **The mechanism test passes.** Per `source_videos_20260907.md` §8.3: if the
   SMA20 is genuinely capturing trend, adding an **explicit** higher-timeframe
   structure filter (higher highs and higher lows on the confirm timeframe)
   should not change the result much. **If it improves materially, the moving
   average is not doing its stated job** and the strategy is trading something
   else. Cheap, and it is the only check here that tests the *premise* rather
   than the P/L.
8. **The chosen cell beats the median of the 800-cell distribution**, and the
   equal-weight ensemble is reported beside it.

**Any single failure is a rejection**, written to `claude/ma_trend_first_results.md`
whichever way it goes. No partial pass, and no "promising, worth another sweep."

**The locked holdout is not spent by this.** It remains reserved.

---

## 10. Order of work

1. **The free pre-check** — re-read `entry_split`'s quartile tables for an
   interior peak in the trend family. No run. **If none, stop.**
2. **Diagnose the 08:00 interleaved-price defect** (§8.2). It gates this and
   everything else on the tape.
3. **Pull full-day `ohlcv-1m`** (§8.1), which also unblocks `ema200_dist` for
   `entry_place` and the RVOL rule ORB is waiting on — **one pull, three
   consumers**.
4. **Settle the breadth criterion** (§9.2) and re-score MC5 under it.
5. Pre-flight: `slope20_n` and `ext_n` quintile profiles, touch distribution,
   trigger counts per setup, and **`R / entry_price` per stop rule**.
6. Only then write `strategy/ma_trend/`, unit-test the state machine on
   hand-built bars, and run the grid under §9.

---

*Every definition in §3 and §4 is ours, not the source's. The source supplies
the idea, one demonstrated entry, and eight gates in words. It supplies no win
rate, no sample, no average loss, no drawdown, and not one losing example in
37 minutes. Nothing here is validated until step 6, and §9 says what validation
means.*
