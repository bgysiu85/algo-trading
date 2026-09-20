# MCL position mechanics — five rejected, one summary, 2026-09-08

**Do not relitigate any of these without new data.** Each was implemented,
measured against this project's standards of evidence, and rejected. The full
workings — grids, bootstrap CIs, regime tables — are in the archived originals
named against each section; nothing was deleted.

Consolidated from five documents on 2026-09-08 so that "has this been tried?"
is one read rather than five.

> **All P/L figures predate the 2026-09-05 fill-model correction** (gap-through
> fills, peak seeded from entry) and are therefore overstated. The correction
> pushes costs **up**, and the 2026-09-06 slippage correction is worth about the
> same $1 per round trip to every variant compared, so **no comparison below
> moves**. Do not reopen these on the grounds that the numbers are stale —
> re-derive if you must, and expect the same answer.

---

## The finding that unifies all five

Three mechanics changed position size during a trade. They fail for what look
like three different reasons and are one:

| mechanic | what it does to size | result |
|---|---|---:|
| scale-out | reduces on weakness, restores on strength | −$682 to −$1,625 |
| pyramid | adds on a recovered dip | −$268 vs a flat 200 |
| scale-up | reduces on strength, restores on weakness | −$142 to −$294 |

**In a strategy whose P/L is carried by a handful of big movers, anything that
reduces exposure to a runner costs more than any amount of round-tripping
earns — and anything that adds size does no better than simply starting with
that size.**

Flat size is the only thing that ever scaled P/L, and it scales it exactly:
100 / 150 / 200 / 300 shares all return **0.483% per dollar deployed, to three
decimals**. That is why every pyramid must be judged against a flat position of
the size it builds to, never against the size it starts from.

---

## 1. Scale-out / scale-back-in — REJECTED
*Archived: `archive/mcl_scale_out_decision.md`*

Ben's rule after Ross Cameron: on a pullback sell part of the position; buy back
on the recovery; repeat; only the full trailing stop closes the trade.

**At the 5% trail MCL actually runs: P(delta > 0) = 0.0%**, negative after
dropping the best five symbols, negative in both halves.

**The specification bug is the more valuable finding.** "Buy back once it
increases back to its previous candle high" was first implemented as the
*previous bar's* high rather than *the peak the pullback started from*. On
1-minute bars the previous bar's high is reclaimed by the first bar that fails
to make a lower high — i.e. during the decline. Measured over 4,359 re-entries:

| | share |
|---|---:|
| bought back **below its own sell price** | **82%** (median −2.99%) |
| bought back below the peak it sold off | 88% (median −3.69%) |

It was averaging down into a slide while claiming to buy strength. Both triggers
are kept in code (`rebuy_trigger="peak"` default, `"prev_bar_high"`) so the
wrong one stays reproducible. **"Previous candle high" is ambiguous and the two
readings are opposite trades — pin which one a spec means before implementing.**

## 2. Pyramid on a recovered pullback — REJECTED
*Archived: `archive/mcl_pyramid_decision.md`*

A dip of `pyramid_pullback_pct` below the running peak arms the position;
reclaiming that peak buys more. Nothing is sold, so none of the scale-out's
sell-low/buy-back-higher cost applies. Tested on its own terms.

**Delta −$268 against a flat 200 shares. 95% CI [−$2,142, +$1,502],
P(better) = 39.6%**, negative after dropping the best 1/3/5 symbols, sign flips
across the holdout.

At 100 shares MCL sits *exactly* on the Tiered per-order minimum
(100 × $0.0035 = $0.35), so it gets no volume discount and pays no penalty.
Adds of 100 are priced the same. Smaller orders are not — one reason the
scale-out was expensive.

## 3. Scale-up — REJECTED
*Archived: `archive/mcl_scale_up_decision.md`*

The mirror of the scale-out: reduce on strength, restore on weakness. Both legs
rest, so nothing is chased and the grid charges no crossing cost at all — the
one structural advantage any of these three had.

**−$142 to −$294.** Where the loss lands says the rest:

| bucket | n | baseline | with the mechanic | delta |
|---|---:|---:|---:|---:|
| top 10 winners | 10 | +$2,867 | +$2,741 | **−$127** |
| next 40 | 40 | +$2,542 | +$2,487 | −$55 |
| the rest | 124 | −$3,842 | −$3,803 | **+$39** |

It buys a little protection on the losers and pays for it on the runners.

**And the numbers are generous to it.** A resting limit at a level price merely
touches need not fill; pre-market books are thin. The cost moves from spread to
queue position, which a bar model cannot see and this one does not model. It
loses anyway.

## 4. Confirm-N trailing stop — REJECTED, and it was the strongest lead
*Archived: `archive/mcl_stop_timing_study.md`*

Require the price to stay below the trail for N bars before exiting. Delta
**+$8,300**, beating the cheap way of conceding room (a 10% trail's +$3,113),
and its drop-top-5 survives at +$1,255. It was still rejected, for two reasons
that are not about P/L:

**91% of the gain is one quartile.** Early half delta +$7,781, late half +$519 —
and the late half's drop-top-1 is already negative (−$23). 80 of 174 symbols
improve: worse than a coin flip.

**The risk cost is real and is not in the P/L.** Worst trade −$102 → **−$253**;
median hold 2 bars → **12**. Outside RTH there is no broker-side stop — the
trail lives in the running process — so every extra bar is unprotected, and a
crash or disconnect leaves the position naked. The backtest cannot price that.

**The bug in the first run of this study is why "read the rule back as a
measurement" is a standard.** The trail chain was written `if
trail_confirm_bars > 0:` — a test on a *parameter*, not on price — so whenever a
variant was enabled the `elif last_of_session` below became unreachable.
Positions open at 09:30 were never closed and their trades vanished: 450 rows
instead of 496, the missing P/L *absent* rather than zero. Every figure was
wrong and every figure looked plausible. Trade **count** catches it; P/L does
not.

The lead that survives is a live measurement, not a backtest: log the 5 bars
after every trailing-stop exit in the live session and see whether the bounce is
in the real tape.

## 5. Trail width — 5% STAYS
*Archived: `archive/mcl_trail_decision.md`*

Six candidates (2, 3, 4, 8, 10, 15%) against 5%, 10,000 paired resamples
zero-filled over all 275 symbols.

**Every confidence interval straddles zero.** The best is P = 94.9% at 10%,
against the 100% and clear-of-zero CI the apex removal reached. On this
project's own standard, none is a result.

**Not one width survives drop-top-N on the *delta*.** Every trail change on this
dataset is five names, and largely the same five — WLDS is the single largest
contributor at every width; the 15% column is close to "WLDS and BATL had two
very good days".

The net column hides a sign asymmetry: **widening makes more symbols worse than
better** (8%: 61 better, 111 worse); tightening does the opposite (2%: 121
better, 52 worse). The wide end's headline is a minority against a majority
moving the other way.

**Two things follow that are still open.**

*2% as a risk decision, not a return one.* Better concentration robustness in
both halves, half the worst-case trade, a quarter of the hold-time exposure,
for a return difference indistinguishable from zero. That is a legitimate reason
to change a parameter, and it must be argued on those terms rather than smuggled
in on the net column. At 2% the break-even is $7.48/trade.

*Apex and the trail are substitutes.* Apex removal is worth **+$1,702 at a 5%
trail but only +$311 at 2%** — a tight trail already cuts what the apex rule
cut. So **do not quote +$1,702 as the value of apex removal in general**, and
note that a trail change is not the single-variable move it looks like: it
silently re-prices a decision already shipped.

---

## What is NOT closed by any of this

- **Intrabar entry.** `mcl_robustness_analysis.md` §5 — still current, not
  archived — measured the perfect-entry ceiling at +$44.08/trade against an edge
  of +$7.79. Large. It also found winners' and losers' close-minus-low gaps
  effectively identical ($0.456 vs $0.429), so better fills are a **level**
  improvement, not a tail one. `entry_latency_20260908.md` re-derived exactly that on the screened
  universe. Both say the same thing; the second was measured without knowing
  the first existed, which is part of why these docs were consolidated.
- **Anything that changes which trades are taken.** Every mechanic above
  changes size *within* a trade the entry rule already chose. The
  screened-universe result says the entries are the problem, and none of these
  touch them.
