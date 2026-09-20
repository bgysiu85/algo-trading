# Warrior 2 — flat top breakout

Assumes `warrior_0_universe_and_risk.md`. This is a **variant of
`warrior_1_micro_pullback.md`, not a separate strategy** — same universe, same
regime gate, same stop and target model, same entry trigger. Only the shape of
the pullback differs.

Source pages: W-BF, W-MOM, plus `4jes2_N3m2I` (14:03, **not yet transcribed**).
Transcript detail below is from V-3HR (`A3sbJBOLGuI`), read in full 2026-09-09.

---

## 1. The difference from a bull flag

In a bull flag the pullback's highs **descend**. In a flat top they are
**level** — price repeatedly tags the same price and fails there.

V-3HR 25:35 confirms the entry is shared: **"the first candle to make a new high
is the apex point of the bull flag *or the flat top pattern*."** One trigger,
two flag shapes.

| Element | Bull flag | Flat top |
|---|---|---|
| Pullback highs | descending | **flat — low dispersion** |
| What is at the level | nothing in particular | **a large resting seller** |
| Entry | first candle to make a new high | same |
| Everything else | — | same |

> **Programmatically distinguishable, and cheaply:** measure the dispersion of
> the pullback bars' highs. **Our detector may currently treat both as one
> pattern, or reject flat tops outright if it requires a descending flag.
> This needs checking before anything else in this document matters.**

---

## 2. The mechanism he gives, and why it is worth taking seriously

W-MOM and W-BF: a large seller parks at the level. Short sellers stack buy-stop
orders just above it. When buyers absorb the seller and the level breaks, those
stops trigger and accelerate the move.

V-SCALP 47:33 extends it to the market-maker side: on a surge, "they pull the
offers, they pull the bids — that creates slippage, which is basically worse for
retail traders but better for them, **and it amplifies the move**."

> This is a **supply-exhaustion** mechanism, not a chart-pattern mechanism. It
> predicts something specific and testable: the move after a flat-top break
> should be **faster and larger** than after a descending-flag break of the same
> size, because there is a stop cascade behind it and nothing resting above.
> That is a measurement we could make on the existing bar cache without building
> the strategy at all.

---

## 3. Where the flat tops actually are — the price grid

**This is the most useful thing the transcripts add, and it is not on the
website.** Both videos treat half-dollar and whole-dollar prices as the dominant
intraday structure on these names.

V-3HR 42:33: "most stocks trade with a great deal of respect to half dollars and
whole dollars." V-SCALP 38:34 shows resting size on one name, unchanged all
morning: **45,000 shares bid at $6.00**, sellers stacked at **$7.40–7.50**, and a
wall at **$8.00**.

His description of the resulting price behaviour (V-3HR 43:03) is mechanical:

> "There's a lot of orders clustered right around these levels and there's not a
> lot of orders in between… so where are the areas where you think a stock would
> move faster? In between the areas where there's lots of orders."

And the level's role flips once broken — V-3HR 44:02: price breaks $7.50, comes
back and retests it, and **prior resistance becomes support**. He shows the same
sequence at $8.00 within one trade.

> **Flat-top detection on this universe may be substantially a price-grid
> problem rather than a pattern-matching one.** If the flat tops sit at
> `price mod 0.50 == 0`, we do not need to detect flatness at all — we can
> anticipate the level. That is trivially computable, needs no new data, and is
> the sort of rule that either shows up immediately in the bars or does not
> exist.

**The measurement to make first, before any strategy work:** on our own bar
cache, do intraday highs, lows and consolidation prices cluster at half and whole
dollars more than chance? On a $2–20 universe with sub-dollar moves this is a
strong claim and it is cheap to falsify.

---

## 4. The half/whole-dollar entry is a setup in its own right

V-SCALP 47:33 lists his preferred patterns as three, not two: "the micro
pullback, the first pullback, **or an entry under a half or whole dollar**."

V-3HR 42:04 shows it worked: he buys at $7.99 for the break of $8.00, and takes
profit into the break. V-SCALP 46:34: "I actually added at $7.99 too for the
break of eight, then taking profit as it breaks through that level — **that's a
scalp at the half dollar and whole dollar, that by itself is a trade**."

> Note what this is: **entering a cent below a round number and selling into the
> break.** It is the early entry of `warrior_1_micro_pullback.md` §3b with the
> psychological level as the trigger, and it is the one early-entry variant that
> is fully codeable from bars alone. **It is also the cheapest thing in this
> whole spec set to test.**

---

## 5. What the builder needs

1. **Check first whether the existing detector rejects flat tops.** If it
   requires descending flag highs, every flat-top result to date is a null by
   construction.
2. **Measure the price-grid claim before building anything** (§3). It is a
   measurement, not a strategy, and it gates the value of the rest.
3. **Then** the dispersion classifier: label each detected flag as flat or
   descending and score them separately on the existing trade set. No new
   strategy, one new column.
4. Only then the half/whole-dollar entry as a standalone trigger.

## 6. Gaps

- **`4jes2_N3m2I` ("Flat Top Breakout Pattern", 14:03) has not been
  transcribed.** It is the only dedicated video on this setup and it is short.
  It is the obvious next extraction if this document turns out to matter.
- **No retracement or bar-count threshold is stated for the flat-top variant
  specifically.** Warrior 1's ≤3 red candles and ≤50% retracement are assumed to
  carry over; he never says so.
- **No performance data of any kind**, for this setup or any other. Warrior 0 §0.
