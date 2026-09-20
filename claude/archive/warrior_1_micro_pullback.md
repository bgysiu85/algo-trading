# Warrior 1 — micro pullback / bull flag / first pullback

**His primary setup, and the one our bull flag detector already implements.**
Assumes `warrior_0_universe_and_risk.md` — universe, regime gate, stop and
sizing model are all there and are not repeated here.

Sources as tagged in Warrior 0. **V-SCALP (`p1W8Mjl4kWs`) and V-3HR
(`A3sbJBOLGuI`) were read in full on 2026-09-09**; everything attributed to them
below is from the transcript, with timestamps.

> **Provenance, confirmed 2026-09-10:** MCL is Ben's own version of this method,
> loosely derived. So this document is not an independent check on MCL — it is
> the thing MCL was built from. Where the two disagree, **this is the intent and
> MCL is the deviation.** See §6 item 1.

---

## 1. They are all one pattern

This was an open question in `claude_youtube_extraction_ross_cameron.md` §1 and
it is now closed. **The micro pullback, the first pullback and the bull flag are
the same shape on different bar intervals.** He says so three ways:

- W-BF: he day trades bull flags on 1-minute and 5-minute charts and scalps
  "micro pullbacks" using **mini bull flag patterns** on 10-second and 1-minute.
- V-SCALP 34:33: he demonstrates the identical entry on the 5-minute and then on
  the 1-minute of the same name — "we could trade that on the one minute as well."
- V-3HR 25:35: **"the first candle to make a new high is the apex point of the
  bull flag or the flat top pattern."** One entry trigger, named once, serving
  both patterns.

> **So the detector does not need a second pattern.** What it needs is a bar
> interval and a scale. `archive/ema_source_comparison.md` D1 records that S5
> *ranks* his setups **micro pullback → bull flag → MA pullback**; since the
> first two are the same shape, that ranking is really "faster chart first."

**The census supports this one.** Across 401 videos the micro pullback is his
most-used setup at **172 mentions and his safest at a 0.7 red-day lift**
(`warrior_census_20260910.md` §6). Of everything in the spec set, this is the
part the derivation got right.

---

## 2. The pattern

| Element | Rule | Source |
|---|---|---|
| **Pole** | A squeeze up on **2–5 consecutive green candles**, on high relative volume | V-SCALP 40:35 "two three four green candles"; V-3HR 27:04 "one two three four green candles in a row"; W-BF |
| **Flag** | Consolidation near the top of the pole | W-BF |
| **Pullback length** | **2–3 red candles**, "up to three" | W-BF; V-3HR 27:04 "two candles of pullback" |
| **Pullback volume** | **Lighter than the pole.** Flag volume *above* pole volume = selling pressure, no trade | W-BF; V-3HR 32:02 "we generally prefer that there's lighter volume on the pullback" |
| **Max retracement** | **More than 50% of the pole is a sign of weakness** | W-BF |
| **Pullback low** | A **bottoming tail** is preferred and is what he points at repeatedly | V-SCALP 33:59; V-3HR 32:34 |
| **ENTRY** | **The first candle to make a new high after the pullback** | Everywhere. This is the trigger |
| **Stop** | `min(low of the pullback / bottoming tail, 10–20c)` — see Warrior 0 §5.1 | V-SCALP 34:03; V-3HR 45:31 |
| **First target** | 15–20c, or the next half/whole dollar; scale half | Warrior 0 §5.2 — **unresolved** |
| **Final target** | High of day, then beyond | V-3HR 32:34 |
| **Invalidation** | Break of the **9 EMA or VWAP**; MACD crossover; close below 20 EMA | W-BF; Warrior 0 §4 |

**Volume typically spikes as the first new-high candle prints** — retail and
covering shorts entering together. He treats that as confirmation, not as a
warning.

### The pattern repeats within one move, and that matters for trade count

V-SCALP 34:33, counting on a single chart: "first one-minute candle to make a new
high is right there, ... is right here, ... is right here — in fact on this one
we have **1 2 3 four** of that pattern that happened four times in a row," then a
fifth after a deeper pullback.

> **This is the window model, not the one-trade-per-signal model.**
> `archive/ema_source_comparison.md` D10 flagged the distinction: our engines arm
> once per signal, he re-arms on every pullback for as long as the front side
> holds. **Four to five entries from one move is his normal case**, and it
> produces a very different trade count from the same tape. It is already
> recorded as `ALLOW_REARM_SAME_TREND` and should be first-class here.

**But note the census figure before sizing this up:** his median day is **2
trades** and his mean is 2.7. Four to five entries from one move is his normal
case *within a move he is trading*, not a normal day.

---

## 3. Entry timing — he describes two entries and states the trade-off

This is the most useful thing in the two transcripts and it is not on the website
at all.

### 3a. Confirmation entry (the published rule)

Wait for a candle to actually make a new high above the pullback's origin. V-3HR
26:03: "you pay a higher price for confirmation… in exchange you get higher
accuracy."

### 3b. Early entry (what he does in his main account)

Enter *before* the new high, anticipating it. V-3HR 26:34 names the two triggers:

1. **A break through a psychological level just below the apex** — a half dollar
   or a whole dollar.
2. **A surge of buying on the level 2 and the time & sales.**

His stated reason is not speed for its own sake: **"I would always prefer to have
an early entry because it offsets the risk of a bull trap or a false breakout."**
The early entry gives a tighter stop, so a failed breakout costs less.

V-SCALP 41:03 shows the cost of not doing it: "by the time the price broke I'd be
getting in *right here*; if I waited for the price to break I would have been
getting in *right here*" — pointing at a materially worse fill.

> **`PROGRAM_INDEX.md` §7 item 3 already licenses an intrabar-entry hypothesis
> and says it needs a harness entry mode with the same gap-through logic the
> exits have.** This is that hypothesis, from a practitioner, with a stated
> mechanism and a stated cost. **Trigger 1 is fully codeable from bars** —
> `price mod 0.50` against the pullback high. Trigger 2 is not; we have no level
> 2 in the backtest.

**He drops the early entry in the small account** and takes only confirmation
entries, because accuracy is worth more than fill quality when trade count is
capped. That is a clean statement of the trade-off in both directions.

### 3c. The ABCD degradation — a named failure mode

V-3HR 38:04. If the first-new-high candle fires, stalls, drops back, and *then*
breaks through the high later, the setup "turned from a first candle to make a
new high into an **ABCD pattern**." He trades ABCD in his main account but
**states a lower success rate on it** and excludes it from the small account —
"the problem with an ABCD pattern is that it requires an initial failure to work."

> Codeable, and it is a *classifier* rather than a filter: the same bars produce
> a first-pullback entry or an ABCD depending on what happened after the trigger.
> Worth labelling in a backtest's trade list so the two can be scored separately.
> The census puts ABCD at a **2.1× red-day lift** on 12 mentions — small n, right
> direction.

---

## 4. Exits

The three published rules are in Warrior 0 §5.3 and are not repeated. What the
transcripts add, in his order of use:

| Indicator | Codeable? |
|---|---|
| **Green candles getting progressively smaller** — "the trend is getting exhausted" | **Yes** — decreasing sequence of green-bar ranges |
| **Topping tail, doji, shooting star, gravestone** | **Yes** — upper wick to body ratio |
| **"Breakout or bailout"** — if it does not move up immediately, the timing was wrong | **Yes** — an N-bar time stop |
| Burst of red on the time & sales | No — no tape in the backtest |
| Big sellers appearing on level 2 | No |
| Price reaching the next half/whole dollar — take half | **Yes** |

V-3HR 46:33 adds a **recovery rule** rather than an exit: if a trade goes red
almost immediately he switches objective to getting out at breakeven — either by
adding near support and selling the bounce, or simply exiting at his entry price.
**Not recommended for porting** — it is a discretionary hold-and-hope with a
better name, and this project has already rejected the adjacent mechanic
(`mcl_rejected_mechanics.md`).

> **Caution on the "breakout or bailout" row.** It reads like a time stop, and a
> time stop was measured and rejected on 2026-09-10 — every cap loses, the loss
> shrinks monotonically as the cap loosens, and the boundary check fails
> (`hold_cap_decision.md`). His rule is a *discretionary* read of whether price
> is moving, not an N-bar cap, and the two are not the same thing. **Do not
> re-implement it as a bar count.**

---

## 5. What this changes in our detector

`config.py` comparisons. **None of these are validated; each is a hypothesis
needing its own registration.**

| Our parameter | His stated value | Status |
|---|---|---|
| flagpole % | No percentage given. The *universe* carries the strength test (10%+ on the day, 5× RVOL) | **Consider moving the strength test into the screen** |
| retracement % | **≤ 50% of the pole** | Direct comparison, cheap |
| volume multiple | **flag volume < pole volume** — a ratio *between phases* | **Ours is a fixed multiple against a trailing average. His self-normalises per setup** and is arguably more robust |
| — | **pullback ≤ 3 red candles** | **May not be encoded at all** |
| — | **pole = 2–5 green candles** | **May not be encoded at all** |
| — | **invalidate on 9 EMA / VWAP break** | **May not be encoded at all** |
| stop | `min(structure, 10–20c)` | **MEASURED AND REJECTED 2026-09-10.** The cent stop loses at every value tested, monotonically, and the boundary check fails. `cent_stop_decision.md`. Ours stays percentage-based |
| **exit shape** | **half off at target, breakeven stop on the rest — no trail** | **NEVER TESTED, and see §6 item 6 — this is the real gap** |
| re-arm | 4–5 entries per move while the front side holds | `ALLOW_REARM_SAME_TREND`, currently not first-class |
| entry | early entry at a half/whole dollar below the apex | Needs an intrabar entry mode |

> **The bar-count constraint and the retracement percentage are not the same
> constraint** and will select different flags. He specifies both — ≤3 red
> candles *and* ≤50% retracement — so they are complements, not alternatives.
> Our detector parameterises only the percentage.

---

## 6. Open questions for the builder

**Two of these are now answered. Kept, with their answers, because the answers
change how the rest of this document should be read.**

1. ~~**Is our universe derived from him, or convergent?**~~ **ANSWERED —
   derived.** Ben, 2026-09-10: *"MCL was my version of Ross Cameron's strategy.
   So I guess you can say loosely derived."* So the universe match is an **echo,
   not corroboration** — one source, not two agreeing. And more importantly the
   distribution divergence (he wins 5 trades in 7, MCL wins 1 in 3) is **drift
   from intent, not a different design**. Where this document and MCL disagree,
   this document is the intent. `HANDOVER_TO_BUILD_20260910.md` §0.
2. ~~**Does the fixed-cent stop survive the price band?**~~ **ANSWERED — no.**
   Measured across 373 sessions: 10c, 15c and 20c all lose, the loss shrinks
   monotonically as the cap loosens, and the best cell sits at the edge of his
   stated range so the boundary check fails. The gradient points away from cents
   entirely. `cent_stop_decision.md`. **Do not re-open.**
3. **Does the ≤3-red-candle cap change the trade set** versus the retracement
   percentage alone, and in which direction?
4. **What is the re-armed trade count on our own tape?** He gets 4–5 per move,
   on a median of 2 trades a day. Given item 1 this is a *drift* measurement
   rather than a comparison between two systems.
5. **Does the early entry survive execution cost?** It fills before confirmation,
   so it takes more false breakouts in exchange for a tighter stop. Net of the
   $4.26/RT measured friction, that trade may not be worth making at 100 shares.
6. **The exit is the real gap, and item 1 is why.** MCL trails at 5%; he takes
   half off at a target and moves the rest to breakeven, and never trails. That
   single difference produces the 32.4%-versus-71.1% win rate — 2,212 of MCL's
   2,413 exits are the trail, at −$1.2 each, and only the 201 reaching
   `window_close` make money. **Nothing in this project has tested his exit as
   specified.** If MCL was meant to be his strategy, this is the largest
   unexamined place it stopped being one.
