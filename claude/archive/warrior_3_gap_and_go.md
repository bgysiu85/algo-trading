# Warrior 3 — Gap and Go

Assumes `warrior_0_universe_and_risk.md`. This is a **pre-market selection and
grading method** that feeds the entries in `warrior_1_micro_pullback.md`, not a
separate entry model.

Sources: W-GAP (`warriortrading.com/gap-go/`), W-PRE
(`warriortrading.com/premarket-trading/`), and the pre-market portions of V-3HR
(`A3sbJBOLGuI`, read in full 2026-09-09).

---

## 1. The grading rubric — and note that it grades, it does not gate

| Criterion | **Ideal** | **Marginal** | **Avoid** |
|---|---|---|---|
| Float | **< 20M** | 50–100M | **> 100M** |
| Short interest | **> 10%** | 5–10% | < 5% |
| Catalyst | news / earnings | technical breakout only | none |
| History | **former runner**, retail interest | not a hot stock | former pump-and-dump |
| Pre-market volume | **> 150k** | < 100k | < 50k |
| Gap | **> 4%** | — | **< 4%** |
| Price | — | > $20 | — |
| Sector | — | manufacturing, oil, consumer goods | — |

Gaps **under 4%** he expects to fill. Most Gap and Go opportunity is
**09:30–10:00 ET**.

The 4% figure is corroborated on a second page — `/how-to-use-stock-scanners/`:
"I consider a stock in play if it is surging up or down **more than 4%** with a
strong catalyst."

> **This is the fourth independent source in this project ranking rather than
> gating**, after the `oSznkl4ASaA` guest's ADF score, Shay's colour-coding, and
> his own deliberately-wide scanner filters (Warrior 0 §1). **Our screens gate.**
> That is a structural difference and it deserves a deliberate decision rather
> than an inherited default — particularly given the Humbled Trader finding that
> a filter on a nullable field silently drops exactly the newly-listed and
> recently-reverse-split names this universe exists to find.

---

## 2. Two variables here that we do not carry at all

**Short interest (>10% ideal).** Also flagged twice by Shay in the other channel
(>20–25% as her threshold). Three mentions across two independent sources and we
have no such field. Free sources are delayed (shortsqueeze.com, Finviz).

**"Former runner" status** — has this symbol run before, and did it hold?
**This is computable from our own bar cache** and it overlaps directly with the
daily-chart trust check in Warrior 0 §7.1, which is the same idea stated from the
opposite side: he wants a name that has run *and held*, and rejects one that ran
and gave it all back.

> Treat these as **one feature, not two**: for each candidate, find prior spikes
> in the daily history and measure retention. High retention = "former runner"
> (ideal). Low retention = "former pump-and-dump" (avoid). One computation
> answers both rows of the rubric and the §7.1 filter.

---

## 3. Pre-market session mechanics

From W-PRE. **This page turned out to contain no scanner criteria at all** — it
is execution mechanics, and it is useful for that.

- **Limit orders only** in pre-market
- **Orders do not carry into the regular session**
- **25,000 shares maximum per order**
- Matched through **ECNs**; wider spreads, thinner liquidity
- Session 04:00–09:30 ET, activity concentrated **07:00 onward**

> Consistent with what `PROGRAM_INDEX.md` §5 already records for IBKR — Day
> Limit only outside RTH, every stop software-managed. **Independent
> confirmation that the constraint is structural to the session rather than an
> IBKR quirk**, which is worth knowing before anyone proposes solving it by
> changing broker.

**The 07:00 concentration is checkable against our own fills.** MCL arms from
04:00. If his window starts at 07:00 because nothing before it is tradeable,
that is a claim our own data can test directly.

---

## 4. The volume-imbalance signature

V-3HR 9:05, and it belongs here rather than in Warrior 0 because it is a
pre-market selection rule.

**Prior session volume very low, today's volume enormous.** His worked example:
227,000 shares two sessions back, 2.5M the prior session (news broke at 16:00, so
that session's tail is already the move), then 34M on the day.

He walks through the sequence explicitly: nothing all day, then **over a million
shares within ten minutes of a 16:00 news release**, then a continued trend into
the next session.

> Two things here for the builder. First, this is a **session-pair ratio**, not a
> trailing average, so it does not decay as the runner extends — it sidesteps the
> continuation problem in Warrior 0 §2. Second, **the after-hours print is part of
> the signal**: the move begins at 16:00 the day before, not at 04:00. Our screen
> reads the pre-market session; a 16:00–20:00 catalyst window is a different
> lookback and `session_aware_screening.md` is the right place for it.

---

## 5. The catalyst, and the scoreboard on it is now 3–1 against

His position across both videos is more nuanced than the rubric:

- **Main account: preferred, not required** (V-3HR 10:05). A stock up 75–80% "in
  a way becomes its own catalyst" — but he warns those moves often do not hold.
- **Small account: required** (V-3HR 11:02), because the news is "what actually
  is justifying why the price is going up."
- **Continuation names may have no visible catalyst at all** (V-SCALP 22:34) —
  the catalyst was days ago and the name is still riding it. He accepts this.
- **A short squeeze counts as a catalyst** (V-SCALP 14:03): "the stock is up 400%
  in the last 30 days and some shorts are starting to get squeezed out."

He adds two multiplier notes: headlines keyword-stuffed with a large-cap name
(Nvidia, Amazon, Walmart) get faster algorithmic pickup even when the substance
is thin; and recent IPOs, SPACs and **recent reverse splits** are inherently more
volatile.

> **Scoreboard on catalysts for small caps: Evan Schunk says 98–99% irrelevant,
> Shay says reference point only, Cameron says preferred-not-required for the
> main account. Only Eduardo requires one.** Our screens do not read news. This
> is now three independent sources saying that omission costs less than it
> appears.

**Reverse splits are the third mention in this project** as the manufacturing
process behind these names, after the `oSznkl4ASaA` guest and Shay's RNN example.
V-3HR 21:34 shows the operational consequence directly: a 40:1 reverse split
whose float field **had not yet updated**, showing 23M when the true float was
500K. He caught it by hand.

> **A stale float field is a live selection bug in both directions** — it
> silently admits names that should fail and rejects names that should pass. We
> removed float from the MCL screen on 09-08 for a different reason. This is a
> third independent reason.

---

## 6. What the builder needs

1. **Decide gate versus grade** (§1). Four sources now rank; we gate.
2. **Build the prior-spike-retention feature** (§2). One computation, answers
   three separate rules, uses data already on disk.
3. **Test the session-pair volume imbalance** (§4) as an alternative to RVOL —
   it has no continuation problem.
4. **Check the 07:00 concentration** against MCL's own fill times (§3).
5. Short interest is **not** currently obtainable cleanly and should not block
   anything else here.

## 7. Gaps

- No entry model of its own — Gap and Go feeds Warrior 1's entries.
- **No performance data.** Warrior 0 §0.
- The sector row of the rubric ("manufacturing, oil, consumer goods" as marginal)
  is unexplained and unsupported anywhere else in the source set. **Ignore it**
  until something corroborates it.
