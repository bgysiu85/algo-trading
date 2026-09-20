# Six EMA / moving-average sources — the short-selling side

Compiled 2026-09-05, as a companion to `claude/ema_source_comparison.md`
(2026-09-03), which analyzed the same six sources for their long-side rules
only. This doc goes back through the same six transcripts specifically for
what each source says about shorting. All six transcripts re-read in full
(or, for the five that exceeded inline transcript limits, machine-extracted
to plain text and grep-verified against every occurrence of "short",
"bearish", "downtrend", "sell", and "VWAP" before being read in context).

## The sources

Same six as the long-side doc — see that doc for the full title/channel/length
table. Recap of the relevant split: **S3 and S5 are the only sources trading
Ben's actual universe** (US small-cap low-float momentum on a catalyst); S4
and S6 trade liquid large caps intraday; S2 is instrument-agnostic; S1 is what
the E15 spec was built from.

### What each one is at a glance — short side only

| | Has a real short methodology? | Entry trigger | Stop | Target |
|---|---|---|---|---|
| **S1** | Yes — full mirror of its long setup | Close below nearest minor swing low, after 9/20 EMA cross-under + rejection at the EMA zone | Above the pullback high + small buffer | Fixed 1:2 |
| **S2** | Yes | Shooting-star (or equivalent rejection candle) at a 20/50 EMA touch that also sits on an old support level now flipped resistance | Beyond that confluence zone | Fixed 1:3 |
| **S3** | **No** — shorting appears only as commentary on what *other* traders do at a well-respected resistance level | — | — | — |
| **S4** | Yes, but discretionary (live-traded, not ruled out) | Stock stays below VWAP + its moving average after repeated failed reclaim attempts, on a "first red day" after a parabolic run | **No stated fixed price** — managed by starter size, 5m bear-flag continuation, and bounce-volume comparison | Discretionary — covered in pieces near support/round numbers |
| **S5** | **No** — explicitly disclaimed | — | — | — |
| **S6** | Yes — full mirror of its long setup | Rejection candle at 9 EMA / VWAP, at a prior-day low or opening-range low | Break above the rejection candle's high | Fixed 1:2 |

Half the set — S3 and S5 — has nothing to contribute to a short-side spec.
That is the headline finding; see D1 below.

---

## Part 1 — Convergence

These hold across the four sources (S1, S2, S4, S6) that actually have a
short methodology.

### C1. Every short setup is presented as a mirror image of the long setup, never as an independently derived methodology.

S1 introduces its short walkthrough with "let's flip everything around and go
through a short setup" and then substitutes every long-side noun for its
opposite: EMA cross-under for cross-over, rejection at the zone instead of
reclaim, break of the nearest swing low instead of swing high. S2 says "let's
flip the script... a bearish version of this exact same setup." S6 literally
names its third long setup "the VWAP reclaim" and its short counterpart "the
breakdown, which is the opposite of a reclaim." Nobody who has a short
methodology built one from scratch — all four derived it by inversion.

### C2. A higher-timeframe or session-level directional gate accompanies every real short rule.

S1's 15-minute mode only takes shorts when the 1-hour trend is bearish. S6
states it as a blanket rule: "when we're above our VWAP, a good rule of thumb
is to not short; when we're below VWAP, a good rule of thumb is to not long."
S4's short only exists because the stock is below both VWAP and its moving
average on the higher (5-minute) timeframe — that's the pre-condition checked
before the starter position, not the trigger itself. No source shorts against
its own directional filter.

### C3. Confirmation is still a candle close or a named rejection candle — never a bare touch.

S1: the entry is the close below the swing low, not the touch of the EMA
zone. S2: a shooting star has to actually form at the confluence zone. S6:
"perfect rejection right off that 9 EMA... this is exactly where we can go
looking short" — the rejection candle is the trigger, not the level itself.
Same discipline as the long side's C3 in the companion doc.

### C4. Stops are structural, placed just beyond the rejection extreme — never a percentage.

S1: above the pullback high plus a small buffer. S6: "stop loss just a break
above" the rejection candle. S2: beyond the confluence zone. Identical
shape to the long side's C7. S4 is the one exception — see D5.

---

## Part 2 — Divergence

Ordered by how much each should weigh on a short-side spec.

### D1. Two of six sources have essentially no short-side content — and one says so explicitly, on the record.

This is a much starker split than anything found on the long side. S3 (Ross
Cameron, Ultimate MA Guide) never demonstrates a short trade of its own; the
only short-related material is Ross narrating that *other* level-2 sellers
were likely stacked at the 200-day moving average and would be shorting
against it — framed as color on why the stock paused there, not as his
trading rule. He goes on to say that waiting for a moving-average crossover
to short "is well off the highs" and is not something he'd act on.

S5 (Ross Cameron, The Moving Average Trading Strategy You Need) is more
direct still. Discussing the alligator/moving-average crossover system that
is the video's core setup, he says on camera: **"this wasn't really designed
for traders who are trading to the short side... this is really designed for
momentum trading to the long side."** Every subsequent mention of "shorts" in
that 60-minute video is about anticipating a short squeeze as fuel for a
*long* entry (stacked short interest getting forced to cover, à la GameStop,
adds buying pressure a long trader can ride) — never a short-side entry, stop,
or target of his own.

Both of these are the two sources in the set that actually trade Ben's real
universe (small-cap low-float momentum). **The practitioners who trade the
closest analog to what this project cares about are the ones who don't
short it.** That's not an oversight in the source material — it's a stated
trading philosophy, and it should be read as a genuine signal, not a gap to
be filled in by inference from the other four sources.

### D2. Where a short methodology does exist, it splits the same way the long side did: mechanical fixed-R:R (S1, S2, S6) vs. discretionary scale-in/scale-out (S4).

No new information here beyond what the companion doc already found on the
long side (its D5) — but worth confirming the split reproduces on the short
side rather than being an artifact of the long-only setups. It does. S1's
1:2, S2's 1:3, and S6's 1:2 are all one-shot fixed targets set at entry. S4's
short is worked exactly like a real position: starter size, add on 5-minute
bear-flag continuation, judge each bounce by comparing its volume against the
preceding red candle's volume, and cover in pieces near round numbers and
support — by his own account leaving money on the table by covering before
the stock's eventual close near its lows.

### D3. S2 demands an extra layer of confluence (an old support level now flipped resistance) that S1 and S6 don't require.

S2 calls its short setup a "sniper setup" specifically *because* it stacks
three things: the EMA touch, a structure zone tested multiple times in the
past now acting as resistance, and the rejection candle. S1 and S6's short
triggers only need the EMA/VWAP zone itself plus the rejection — no
requirement that the zone coincide with a previously-established S/R level.
This is a real design choice for anyone building a mechanical short spec: S2's
extra requirement should produce fewer, higher-quality signals; S1/S6's
looser requirement produces more signals at (presumably) lower quality. None
of the four sources tests this trade-off quantitatively — it's asserted, not
measured, in every case.

### D4. Fixed target disagreement reproduces exactly: 1:2 (S1, S6) vs. 1:3 (S2).

Same split as the long side (companion doc's D5), same lack of resolution.
Nothing short-specific changes this; it's the identical open question,
independent of direction.

### D5. S4's short has no stated invalidation price at all — the one source that departs from C4.

Every other short setup in this set is stopped by a specific, statable price
(above the rejection candle, above the pullback high, beyond the zone). S4's
real-money short is risk-managed entirely by conviction and position sizing:
starter size first, confirmation from price action and relative volume before
adding, no level named as "if we get back above this, I'm wrong." That's
consistent with how discretionary traders actually manage losers (cut early
on deteriorating evidence rather than waiting for a fixed price), but it is
the one piece of source material in this whole set — long or short — that
cannot be turned into a mechanical stop-loss rule without inventing one that
was never stated on camera.

---

## Part 3 — Source quality (short-side specific additions)

The companion doc's Part 3 caveats all still apply (no verified track record
anywhere in the set; every source sells something; S3/S4/S5 show live,
including losing, executions; S2's "never lose" framing is the least
verifiable of the six). Two additions specific to the short side:

- **The effective sample size for a short-side spec is four sources, not
  six.** S3 and S5 contribute nothing usable (D1). Any confidence claim built
  from "6 sources converge on X" should be re-derived for shorts as "4 sources
  converge on X," which is a meaningfully weaker base rate.
- **The two sources that don't short are also the two closest to Ben's actual
  traded universe.** That should raise, not lower, the bar for building a
  short-side variant of any strategy modeled on this project's low-float
  momentum names — the practitioners with the most relevant experience chose
  not to build a short methodology for that universe at all, for reasons that
  (per S5) are about trade quality and structure, not mere preference.

Treat this doc the same way as the companion: **hypothesis generators, not
evidence.** The convergences (C1–C4) are worth more than any single source
precisely because S1, S2, S4, and S6 arrived at them independently; the single
biggest finding (D1) is not a convergence at all, and is worth more than any
of the convergences.

---

## Part 4 — What this means for any short-side spec

Ordered by expected value, mirroring the companion doc's Part 4 format. None
of these are done yet, and none of this project's strategies currently has a
short-side spec to amend — this is groundwork for whenever one is written.

| # | Implication | Driven by |
|---|---|---|
| 1 | **Don't assume a short-side variant is a free mirror of an existing long spec.** Build it as a mirror mechanically (C1 says that's how all four real sources did it), but treat the *decision to build one at all* as a separate question — the two sources closest to this project's universe answered it "no." | D1 |
| 2 | **If a short-side VW9/EMA15 variant is built, decide explicitly whether to require S2's extra structure-zone confluence** or accept S1/S6's looser EMA/VWAP-only trigger. This is an open design choice, not something the sources resolve for you. | D3 |
| 3 | **Fixed target is still an open 1:2 vs 1:3 question**, unresolved on both the long and short side alike. Whatever gets decided for the long side should probably just carry over rather than being re-litigated per direction. | D4, companion D5 |
| 4 | **Any backtest of a short-side variant deserves more skepticism than the long-side backtest**, precisely because the evidence base behind it is thinner (4 real sources, not 6) and the two most relevant practitioners opted out of shorting this kind of name entirely. A short-side result that looks *better* than the long side on the same universe is a reason to check the code before believing it. | D1 |
| 5 | **S4's discretionary volume-comparison idea (weak bounce volume vs. the preceding down-candle's volume) is worth stealing as a mechanical filter**, even though it can't be turned into a stop-loss price. It's the closest thing in this set to a testable, direction-agnostic rule that isn't already covered by the EMA/VWAP gates. | D5, and the long-side companion's D7 |

---

*All six sources are the same six read for the companion long-side doc.
Nothing here is validated against real data; it is a comparison of claims
about shorting, not of short-side backtest results.*
