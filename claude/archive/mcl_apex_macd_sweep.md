> **Stale figures — the fill-model correction.** Every P/L number below predates
> the 2026-09-05 fix to gap-through fills and peak-seeding, and is overstated
> because of it: MCL's headline went +$1,567 → +$161 and MC5's +$20,156 →
> −$400, on identical trades. Only the price they were booked at changed.
>
> A crossing-cost scare on 2026-09-06 briefly suggested a second and much larger
> correction. **It did not survive its cross-check.** Measured on a fuller tape
> that includes off-exchange prints, the backtests charge ~$2.00 per 100-share
> round trip against a real ~$1.00 — they are slightly *conservative* on
> slippage, not wrong. See `execution_cost_measured.md`.
>
> So: overstated by the fill-model correction, and by that alone. The reasoning
> and the decisions recorded here stand.

# Apex / MACD>0 sweep — 2026-09-05

The 2x2 both changes needed, run offline over **376 cached sessions, 178
symbols**, all four cells on identical bars with the `$2-20` price band
enforced (entries $2.00-$19.66).

**Verdict: remove the apex exit. The evidence is strong and survives every
check that killed V8 and V9.**

---

## The four cells

| variant | trades | net | $/trade | win | drop3 | drop5 |
|---|---:|---:|---:|---:|---:|---:|
| V7 apex ON, MACD>0 | 561 | +$2,163.75 | +$3.86 | 37.6% | +$824 | +$316 |
| V10 apex ON, no MACD>0 | 640 | +$2,665.25 | +$4.16 | 36.7% | +$997 | +$364 |
| V11 apex OFF, MACD>0 | 496 | +$3,865.53 | +$7.79 | 44.2% | +$2,507 | +$1,883 |
| **V12 apex OFF, no MACD>0** | 560 | **+$4,749.10** | **+$8.48** | 42.7% | +$2,932 | **+$2,249** |

## The effects are independent and additive

| change | effect |
|---|---:|
| apex OFF, with MACD>0 kept | **+$1,701.78** |
| apex OFF, with MACD>0 dropped | **+$2,083.85** |
| drop MACD>0, apex ON | +$501.50 |
| drop MACD>0, apex OFF | +$883.57 |

V12 - V7 = +$2,585, and 1,702 + 884 = 2,586. **Essentially no interaction.**

That answers Ben's 2026-09-04 hypothesis directly. He proposed that `MACD > 0`
only looked harmful because bar-close entry destroyed the earlier signals it
admits, so the two changes would interact. They do not — each helps on its own,
by about the same amount regardless of the other. The hypothesis was
reasonable and it is now tested rather than argued.

## It survives the robustness checks

**Concentration, the thing that killed V8 and V9.** Those were rejected for
not surviving the loss of their best names. This is the opposite:

| | drop top 5 |
|---|---:|
| V7 | +$316 — barely survives |
| V12 | **+$2,249 — comfortable** |

Removing apex makes the strategy *less* dependent on a handful of names, not
more.

**Bootstrap over symbols, 10,000 resamples of the 178 names:**

| variant | net | 95% CI | P(net > 0) |
|---|---:|---|---:|
| V7 | +$2,164 | [+$174, +$4,520] | 98.5% |
| V11 | +$3,866 | [+$1,614, +$6,346] | 100% |
| V12 | +$4,749 | [+$2,055, +$7,726] | 100% |

**Paired by symbol** (the right test — same names, different rule):

| | delta | 95% CI | P(improvement > 0) |
|---|---:|---|---:|
| V11 - V7 | +$1,702 | [+$703, +$2,816] | 100% |
| V12 - V7 | +$2,585 | [+$981, +$4,351] | 99.9% |

## The finding that actually decides it: friction

The live session on 2026-09-03 measured about **$4.26 per round trip** of
slippage beyond the one-tick-each-way the engine already models.

| variant | $/trade | after real friction | total |
|---|---:|---:|---:|
| V7 | +$3.86 | **-$0.40** | **-$226** |
| V11 | +$7.79 | +$3.53 | +$1,753 |
| V12 | +$8.48 | +$4.22 | +$2,364 |

**V7 as currently traded does not clear its own friction.** That is consistent
with the 2026-09-03 live session losing $163.60 over 19 trades while the
backtest showed a profit — the gap was never mysterious, it was the friction
the model omits.

Removing apex is what moves the strategy from break-even-at-best to a real,
if thin, margin.

## Where the gain comes from, stated honestly

It is **not broad**. Paired by symbol, V11 vs V7:

- 51 symbols better, 51 worse, **76 unchanged**
- median delta **$0.00**, mean **+$9.56**

The improvement is carried by a minority with large gains (MRAM +$288,
OCG +$213, SKYQ +$150, PDYN +$133, RDW +$126) against smaller losses
(FSLY -$74, HCWB -$49, SGML -$47).

That is exactly what letting winners run looks like in a momentum strategy,
and the paired bootstrap says the mean is robustly positive anyway. But it
means the result depends on the tail, and a period without those runners
would look much flatter.

## What removing apex does mechanically

| | V7 | V12 |
|---|---|---|
| exits on trailing stop | 343 (+$2,680) | 533 (+$4,753) |
| exits on apex | 213 (**-$544**) | — |
| exits at window close | 5 | 27 |
| median hold | 2 bars | 2 bars |
| p90 hold | 4 bars | **24 bars** |
| p95 hold | 5 bars | **44 bars** |
| max hold | 9 bars | **238 bars** |

Apex exits were **net negative in both cells that used them** (-$544 in V7,
-$582 in V10) at a ~27% win rate. Every trailing-stop cut is positive. The
apex rule was closing positions while the trail was still intact, and it was
losing money doing it.

**The median hold does not move** — most trades still end in 2 bars. What
changes is the tail: 48 trades in V12 run 30+ bars, netting +$1,407. The
strategy now occasionally holds for hours.

**Worst single trade is identical in both: -$97.10.** Longer holds did not
create larger losses — the 5% trailing stop caps the downside either way.
That was the main risk of this change and it did not materialise.

---

## Recommendation

**Ship apex removal (V11). Hold `MACD > 0` for now.**

`USE_APEX_EXIT = False`, `REQUIRE_MACD_POSITIVE` stays `True`.

Dropping `MACD > 0` is also supported (+$884 on top, independent), but:

1. Apex removal is the larger, better-evidenced effect, and it alone clears
   friction.
2. The 2026-09-03 live session came in at -$8.61/trade against a backtest
   +$15.44 — live and backtest have diverged materially once already. One
   variable at a time keeps attribution clean when that happens again.
3. `MACD > 0` costs nothing to test next, on the same cached bars.

### What to change in live

`strategy/mcl/mcl.py`: `USE_APEX_EXIT = False`.

Since 3c, live and backtest both route through `signals()` /
`evaluate_last_bar()`, so the flag governs both — no separate live edit, and
no risk of the divergence the old hardcoded `macd_line > 0` created.

### Watch in the first live session

- **Hold times.** Expect the p90 to stretch from ~4 bars to ~24. A position
  open for hours is now normal, not a hung order.
- **The trailing stop is the only protection during those holds**, and it
  lives inside the running process. A crash with a position open leaves it
  unprotected — materially more likely now that positions stay open longer.
- **Sell-side slippage.** Trailing-stop exits fire into falling prices and had
  the worst measured slippage (BIAF -$0.66/share). More trailing exits means
  more exposure to that, and the flat -$4.26 adjustment above is a blunt
  instrument.

## Caveats

- Same 375-session contemporaneous set, still **IB split-adjusted** prices.
  The `$2-20` band filters the worst distortion but leaves a residual upward
  bias: filtering on adjusted price drops names that later reverse-split, and
  reverse splits follow collapses. Unadjusted prices remain the open question.
- One session (AKAN 2026-09-04) is a hindsight pick, added to test the cache
  pipeline. 1 of 376 — immaterial, but it is there.
- MC5 was not swept. Its exit is a different rule entirely.
