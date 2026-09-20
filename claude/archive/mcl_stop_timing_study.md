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

# Is the 5% trailing stop selling into noise? — 2026-09-05

Ben's question: with a 5% trail, how much is left on the table because we sold
too soon — does price rally back within the next 2–5 bars?

**Answer: yes, measurably and not by chance — the stop sells into local lows at
about six times a random bar's give-back. But no rule that waits it out
survives scrutiny, because the bounce is a wick rather than a recovery. The
shipped stop is unchanged.**

Tool: `common/stop_timing.py`. Engine: `strategy/mcl/mcl.py`
(`trail_on_close`, `trail_confirm_bars`, both default off).
Tests: `tests/strategy/mcl/test_trail_timing.py`.
Output: `var/reports/stop_timing.txt`, `confirm_quartiles.txt`.

---

## 1. What happens after a stop — with a null, because it needs one

474 trailing-stop exits. For each, the forward window of 1/2/3/5/10 bars.

The raw numbers mean nothing on their own: a stop fires on a decline, and
declines in a noisy series bounce. So the same measurement is taken from
**random in-trade bars** — bars where a position was open but no stop fired.
That is the control, and it is what makes the result readable.

| bars after | exits: high > exit | exits: median max | **null: high > exit** | **null: median max** |
|---|---:|---:|---:|---:|
| 1 | 76% | +1.96% | 62% | +0.30% |
| 2 | 80% | +2.82% | 70% | +0.48% |
| 3 | 83% | +3.85% | 75% | +0.64% |
| 5 | 86% | +4.50% | 80% | +0.93% |
| 10 | 88% | +6.57% | 85% | +1.47% |

**The frequency is barely different from the null. The magnitude is ~6× it.**
So it is not that price bounces after a stop more *often* than usual — it is
that it bounces *harder*. The stop is landing near local lows.

Exits at a loss bounce slightly harder than exits in profit (86% / median
+3.19% at 3 bars, against 78% / +4.27%).

### The qualifier that decides everything

| bars after | **close** above the exit price |
|---|---:|
| 1 | 54% |
| 2 | 52% |
| 3 | 50% |
| 5 | 49% |
| 10 | 49% |

**A coin flip.** The high recovers; the close does not. The give-back is a
spike, not a recovery — so it cannot be captured by simply holding through.
Capturing it means selling the bounce, which is a different and far more
execution-sensitive trade.

The hindsight figure — $24,812 "left on the table" over 3 bars against a
strategy netting $1,567 — is the sum of those spikes at their peak. It is an
upper bound assuming perfect exits and should never be quoted as recoverable.

## 2. Rules that wait it out

Two looser tests of the same level were added:

- `trail_on_close` — require the bar to **close** below the level. A wick that
  recovers within the bar is ignored; the fill is then the close, which can be
  well below the level.
- `trail_confirm_bars` — the low may breach, but the position closes only if
  price is **still below N bars later**. A breach that recovers is forgotten.

Both are strictly looser than the intrabar default, so neither can be judged
against the 5% baseline alone — **they have to beat a wider intrabar trail that
concedes the same room.** That control is in the table.

| rule | trades | net | delta | 95% CI | P(>0) | drop5 of delta |
|---|---:|---:|---:|---|---:|---:|
| baseline, 5% intrabar | 496 | +$1,567 | — | — | — | — |
| *control:* 8% intrabar | 449 | +$3,643 | +$2,077 | [−871, +5,747] | 90.3% | −$898 |
| *control:* 10% intrabar | 426 | +$4,680 | +$3,113 | [−293, +6,908] | 96.3% | +$222 |
| 5% on the close | 480 | +$3,318 | +$1,751 | [−1,699, +5,716] | 82.2% | −$1,178 |
| 8% on the close | 427 | +$6,722 | +$5,155 | [−235, +12,121] | 96.7% | +$617 |
| 5%, confirm 3 bars | 442 | +$8,802 | +$7,236 | [−272, +19,026] | 96.7% | +$299 |
| **5%, confirm 5 bars** | 425 | **+$9,867** | **+$8,300** | **[+820, +20,220]** | **99.0%** | **+$1,255** |
| 5%, confirm 8 bars | — | — | +$6,953 | — | 97.7% | +$683 |
| 5%, confirm 12 bars | — | — | +$1,937 | — | 81.3% | −$1,022 |
| 5%, confirm 40 bars | — | — | −$501 | — | 41.8% | −$4,858 |

Confirming after 5 bars is the **only interior optimum found anywhere in this
project** — it rises to 5 and falls away by 12, which is what a genuinely
tuned parameter looks like rather than a boundary the search ran to. It beats
the cheap way of conceding room (+$8,300 against the 10% trail's +$3,113) and
its delta survives drop-top-5.

## 3. Why it is still rejected

**The gain is one period.** Quartiles of the delta:

| period | baseline | confirm-5 delta | 10% trail delta |
|---|---:|---:|---:|
| 2025-09-02 → 2026-02-13 | −$53 | **+$7,542** | +$1,966 |
| 2026-02-13 → 2026-03-20 | +$418 | +$240 | −$214 |
| 2026-03-20 → 2026-05-20 | +$1,383 | +$455 | +$105 |
| 2026-05-20 → end | −$182 | +$64 | +$1,257 |

**91% of it is in the first quartile.** The 10% trail control, for all its
faults, at least spreads its gain across the sample.

**And within the second half it is one symbol.** Drop-top-N on the delta:

| half | delta | drop 1 | drop 3 | drop 5 | symbols improved |
|---|---:|---:|---:|---:|---|
| early | +$7,781 | +$3,023 | +$1,792 | +$977 | 36 / 80 |
| **late** | **+$519** | **−$23** | **−$965** | **−$1,566** | 44 / 100 |
| all | +$8,300 | +$3,542 | +$2,311 | +$1,255 | **80 / 174** |

80 of 174 symbols improve — worse than a coin flip. The all-sample drop5 looks
healthy only because the early half carries it.

**The risk cost is real and is not in the P/L.**

| | worst trade | median hold | p95 hold | trades |
|---|---:|---:|---:|---:|
| baseline 5% | −$102 | 2 bars | 35 | 496 |
| confirm 5 bars | **−$253** | **12 bars** | 57 | 425 |
| 10% intrabar | −$181 | 7 bars | 90 | 426 |

Worst trade 2.5×, median hold 6×. Outside RTH there is **no broker-side stop** —
the trail lives in the running process — so every one of those extra bars is
unprotected, and a crash or disconnect during them leaves the position naked.
The backtest cannot price that.

## 4. The bug, because the first version of this study was wrong

The trail chain was written as `if trail_confirm_bars > 0:` — a test on a
**parameter**, not on price. So whenever either variant was enabled that branch
was always taken and the `elif last_of_session` below became **unreachable**.
Positions still open at 09:30 were never closed, and their trades vanished from
the results entirely — 450 rows instead of 496, with the missing P/L absent
rather than zero.

Every figure in the first run was wrong. The tests caught it, not the numbers,
which looked perfectly plausible. `test_every_variant_still_closes_the_position_at_the_window`
pins it: a confirmation longer than the session must still return a
`window_close` trade.

That is the third bug this week whose only symptom was a different, believable
P/L. The pattern is now explicit in PROGRAM_INDEX §4: **read the rule back as a
measurement, not as a return.**

## 5. What to do with this

Nothing to the shipped stop. But this is the strongest lead of the day and it
converts into a live measurement rather than another backtest:

1. **Log the 5 bars after every trailing-stop exit** in the live session. The
   trader already records the bar stream; the question is whether real fills
   land where the model says and whether the bounce is there in the live tape.
   Three or four sessions answers it on data with no selection bias.
2. **Selling the bounce, not holding through it**, is the rule the data
   actually supports — exit on the breach as now, then work a limit back out
   into the spike. That is a genuinely different mechanic and it is
   execution-bound, so it needs sub-minute data to evaluate honestly. It joins
   the tight-trail-with-re-entry idea in the same queue.
3. Do **not** re-tune the trail on this sample. The wide-trail direction was
   already rejected in `mcl_trail_decision.md` for concentration, and confirm-5
   is that same concentration wearing a better-looking parameter.

---

## Caveats

- Same 373-session hindsight-selected universe; the selection cuts toward names
  that moved, which is exactly the bias that flatters any looser stop.
- Costs charged: measured slippage $0.0213/share transacted and real IBKR
  Tiered commission per order. The confirmation rule's fill is the close of the
  confirming bar, which the model takes at close − 1 tick.
- The null model resamples in-trade bars, not all bars, so it already conditions
  on "a position was open". It does not condition on being in a decline, which
  would be a stricter null and would narrow the gap.
