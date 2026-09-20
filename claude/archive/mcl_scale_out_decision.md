> **ARCHIVED 2026-09-08.** Superseded by `mcl_rejected_mechanics.md`, which carries the verdict.
> Kept because the workings are the evidence for a decision that still stands.
> **Do not quote figures from this file as current.** See `PROGRAM_INDEX.md` §6.

> **Stale figures — the conclusion is unaffected.** The P/L numbers below
> predate the 2026-09-05 fill-model correction (gap-through fills, peak-seeding)
> and are overstated because of it.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check** — measured on a fuller tape
> the backtests turn out slightly *conservative* on slippage, by about $1 per
> 100-share round trip. See `execution_cost_measured.md`.
>
> Neither correction rescues what was rejected here. The fill-model fix pushes
> costs **up**, and the slippage correction is worth roughly the same $1 to
> every variant compared, so it moves no comparison. Do not reopen these on the
> grounds that the numbers were stale — re-derive them if you must, and expect
> the same answer.

# Scale-out / scale-back-in exit — decision, 2026-09-05

Ben's rule, after Ross Cameron: on a pullback sell part of the position; when it
recovers, buy back; repeat; only the full trailing stop ever closes the trade.

**Verdict: do not ship it. At the trail MCL actually runs (5%), the mechanic is
significantly NEGATIVE — P(delta > 0) = 0.0%, negative after dropping the best
five symbols, negative in both halves of the sample.**

> **This document supersedes an earlier version that was wrong.** That version
> was written against a mis-implemented re-entry trigger and its numbers should
> not be quoted. §0 explains what changed. The verdict is the same; almost
> nothing else is.

Code: `strategy/mcl/mcl.py` (`rebuy_trigger`, default `"peak"`),
`strategy/vw9/backtest.py` (same four knobs, for parity).
Tools: `common/scale_grid.py` (grid), `common/scale_regimes.py` (the three
regimes), `common/scale_verdict.py` (bootstrap + holdout),
`common/scale_report.py` (boundary/holdout read-out).
Tests: `tests/strategy/mcl/test_scale_out.py`.
Output: `var/reports/scale_grid_peak.csv`, `scale_regimes.txt`,
`scale_verdict.txt`, `scale_report.txt`.

---

## 0. The specification bug, and how it was found

Ben's rule is "buy back once it increases back to its previous candle high" —
meaning **the peak the pullback started from**. The first implementation read
that as the **previous bar's high**, which is a completely different trade: on
1-minute bars the previous bar's high is reclaimed by the first bar that fails
to make a lower high, i.e. *during* the decline.

Measured over 4,359 re-entries under the old trigger:

| | share |
|---|---:|
| bought back **below its own sell price** | **82%** (median −2.99%) |
| bought back below the peak it sold off | 88% (median −3.69%) |

It was averaging down into a slide while claiming to buy strength — which is
why it needed a 15% trail to survive, why it earned most on the *flattest*
names, and why it ran away without limit as cycles accumulated.

Both triggers are kept as `rebuy_trigger="peak"` (default) and
`"prev_bar_high"`, so the wrong one is reproducible rather than deleted.

A second bug was found while fixing the first: hitting `max_cycles` stopped the
buy-back but **not** the partial sell, so a capped trade kept shedding half its
position on every subsequent pullback and never bought any back — bleeding to
nothing on a trade that was never stopped out. Hitting the cap now retires the
whole mechanic for the rest of the trade.

Neither bug was visible in the P/L. The backtest just reported a different,
plausible-looking number. `tests/strategy/mcl/test_scale_out.py` pins both as
behavioural invariants.

## 1. The grid still walks to the corner

All 4,900 combinations Ben specified, re-run on the corrected trigger:

| | trades | REAL net | REAL/trade | drop5 |
|---|---:|---:|---:|---:|
| baseline (5% trail, no scaling) | 496 | +$1,567 | +$3.16 | +$1,707 |
| grid winner — trail 15 / pull 0.5 / portion 20 / rebuy 150 | 382 | +$29,365 | +$76.87 | +$11,528 |

**All four parameters sit on the boundary** — widest trail, tightest pullback,
*smallest* portion sold, *largest* quantity bought back. Read literally that is
"sell as little as possible and buy back as much as possible on every 0.5%
wiggle", which is not an exit rule. It is an accumulator, and its position
compounds: **peak 734 shares** on a 100-share entry, ~$3,670–$14,680 notional
against **$4,131.89 net liq**.

The holdout passes (early +$15,038 edge, late +$7,454), and that is precisely
the point made in the previous version and still worth keeping:

> **A holdout tests whether a pattern is stable, not whether it is real. Both
> halves contain the same fill model, so both halves agree. Statistical
> robustness cannot detect a bad cost model — it certifies one.**

## 2. Splitting the mechanic from the leverage

A search free to add size will always find size. So the mechanic was re-run in
three regimes, changing one thing:

| regime | `rebuy_qty` | what it measures |
|---|---|---|
| **NEUTRAL** | `None` — restore exactly what was sold | the idea, and nothing else |
| **CAPPED 2×** | fixed 100, position capped at 200 | a pyramid with a risk limit |
| **UNCAPPED** | fixed, no cap | what the grid searched |

Only NEUTRAL answers Ben's question. The others are decisions about position
size, which belong to the sizing study and should not arrive disguised as an
exit rule.

### At the 5% trail MCL actually runs — every setting loses

Size held constant, 496 trades either way, compared against the *same* trail
with no scaling:

| sell % at −pullback | REAL net | vs baseline |
|---|---:|---:|
| baseline | +$1,567 | — |
| 20% at −0.5% | +$885 | **−$682** |
| 50% at −0.5% | +$371 | −$1,196 |
| 75% at −0.5% | −$58 | −$1,625 |
| 20% at −1% | +$697 | −$870 |
| 20% at −2.5% | +$508 | −$1,059 |
| 75% at −2.5% | −$1,880 | −$3,447 |

Judged to the project's usual standard:

| | 20% at −0.5% | 75% at −0.5% |
|---|---:|---:|
| delta | −$682 | −$1,625 |
| 95% CI (paired bootstrap by symbol, 10,000 resamples) | [−$950, −$418] | [−$2,553, −$722] |
| P(delta > 0) | **0.0%** | **0.0%** |
| delta after dropping best 5 symbols | −$788 | −$2,040 |
| early half / late half | −$210 / −$471 | −$460 / −$1,165 |

Not marginal, not tail-driven, and not a sample-half artefact. Capping cycles
does not rescue it (best is `max_cycles=1` at +$554 vs +$1,567), and neither
does letting the position grow to 150 or 200 shares (+$1,518 at best, still
below doing nothing).

### It IS positive at wide trails — and that is the interesting part

| trail | baseline | + sell 75% at −0.5%, size constant | delta | P(>0) | drop5 of delta | early / late |
|---|---:|---:|---:|---:|---:|---|
| 5% | +$1,567 | −$58 | −$1,625 | 0.0% | −$2,040 | −$460 / −$1,165 |
| 10% | +$4,680 | +$6,307 | +$1,627 | 98.3% | +$773 | +$305 / +$1,322 |
| 15% | +$6,873 | +$12,958 | **+$6,085** | **100.0%** | +$3,971 | +$1,386 / +$4,699 |

At 15% the delta passes everything: bootstrap interval excludes zero, survives
dropping the best five symbols, positive in both halves. This is a real effect
and it has a plain reading — **at a loose stop the position is bleeding
giveback, and the mechanic acts as a tighter effective stop.** Note the sign of
the portion coefficient flips with the trail: at 5% selling *more* hurts more;
at 15% selling more helps more.

## 3. Why that positive result still does not become a strategy

Push the parameters past the grid's box and the mechanic does not find an
interior peak — it runs to a degenerate limit:

| trail | pullback | portion sold | REAL net |
|---|---|---|---:|
| 15% | 0.5% | 50% | +$10,679 |
| 15% | 0.5% | 75% | +$12,958 |
| 15% | 0.5% | 95% | +$14,811 |
| 15% | **0.25%** | **99%** | **+$17,465** |
| 20% | 0.25% | 99% | +$30,697 |

Sell 99% at 0.25% below the peak and buy it all back when the peak is
reclaimed **is a 0.25% trailing stop with automatic re-entry**. The optimiser
is not tuning the scale-out; it is telling you to throw it away and replace the
trail. And 0.25% on a $5 pre-market small cap is **1.25c — one to two ticks,
inside the spread** — which is exactly where a 1-minute-bar fill model is
worthless. The model fills those perfectly. Nothing will.

The wide trail carrying the effect is not trustworthy either. Extending the
baseline sweep past the grid's 15% ceiling:

| trail | 5% | 10% | 15% | 20% | 25% | 30% |
|---|---:|---:|---:|---:|---:|---:|
| REAL net | $1,567 | $4,680 | $6,873 | $12,013 | $12,527 | $11,679 |
| **drop5** | **$1,707** | $3,586 | $3,119 | $1,798 | $726 | **−$411** |

Net keeps rising to 25%, but drop-top-5 collapses and goes negative — the extra
money is a handful of symbols. **5% is the only trail where drop5 exceeds the
level**, i.e. the only region where profit is not carried by the tail. That
independently re-confirms `mcl_trail_decision.md` and it is why the honest
comparison for the mechanic is at 5%, where it loses.

## 4. Why the original intuition does not hold

Ben's reasoning was "more chance to capture profit while securing a certain
profit". The arithmetic says otherwise, and it is not obvious:

With size held constant, the mechanic **cannot** earn more on a runner than
simply holding. A stock that never pulls back behaves identically; one that
does has had a piece sold cheap and bought back dearer. What it buys is a
better exit on trades that end at the stop — part of the position leaves
earlier. So it trades runner profit for stop-out profit: **a risk-shaping
change, not a return change.** Whether that trade is worth making depends
entirely on how much giveback the stop is already allowing, which is exactly
what the 5%-vs-15% split above shows.

The extra *return* only appears when the buy-back exceeds what was sold. That
is adding size into strength — a different bet, with different risk, and not
what "securing profit" describes.

## 5. What stays in the code

The mechanic ships **inert**. `scale_out_pct=None` is the default and
reproduces the plain engine bit-for-bit (pinned by a test). All four of Ben's
parameters plus `rebuy_trigger`, `max_cycles`, `max_position_shares` and
`rebuy_slip_bps` are call arguments on both MCL and VW9, with no module state,
so any future re-test is one call away. **`brokers/ibkr/trader.py` is
untouched — the live path has no scale-out.**

## 6. What would change the verdict

Not another backtest on 1-minute bars. Everything interesting the mechanic does
happens inside the bar.

1. **Sub-minute data.** The one live idea to come out of this is *tight trail
   with re-entry*, which the grid found by accident. It cannot be evaluated at
   1-minute resolution. Databento `tbbo` (trades carrying the BBO) would settle
   it and the unadjusted-price question at once — noting EQUS.MINI is an
   anonymised partial-tape composite, so its BBO is a bound, not the NBBO.
2. **Your own fill log.** `trader.py` already records bid, ask, spread, limit
   sent, fill price and seconds to fill on every order. Three or four paper
   sessions answer "would *my* order have filled" better than any dataset.

Neither is urgent, since the mechanic is negative at the trail actually run.

---

## Caveats

- Same 373-session hindsight-selected set; still IB split-adjusted prices. The
  selection bias cuts toward wide trails (symbols were chosen for having moved).
- Costs charged: measured slippage $0.0213 per share **transacted**, real IBKR
  Tiered commission **per order** (so the per-order minimum makes extra cycles
  genuinely expensive), and a 40 bps re-entry chase — the measured effective
  cross on this universe after tick rounding roughly doubles `trader.py`'s
  `LIMIT_CROSS_BPS = 20`. Not modelled: depth, partial fills, or whether a
  limit at a computed level fills at all.
- `common/scale_grid.py` duplicates the position loop for speed (~40× faster).
  It verifies trade-for-trade **and share-for-share** against
  `strategy/mcl/mcl.py` across both triggers, two cycle caps, the size-neutral
  form and a capped-growth form before every run, and refuses to proceed on a
  mismatch.
