> **RETRACTED IN PART — 2026-09-08.** The headline below says MC5 "survives
> drop-top-5, the first result in this project ever to do so." Two things are
> wrong with that sentence, and the second is worse.
>
> **It was never after friction.** This run charged tiered commission only. The
> one live measurement of slippage — $4.26 per round trip, from 09-03 — takes
> MC5 from +$1.11 to **−$3.15 a trade on these same bars**, a net of about
> −$23,300. That was computable on 09-07 and was not computed.
>
> **It does not hold on the fuller tape.** On XNAS.BASIC over the 381 training
> sessions, MC5 is **−$97,335 over 10,905 trades, −$8.93 a trade, drop-top-5
> −$109,030** — negative on every subset. See
> `premarket_hypotheses_results_20260908.md` §1, which also names the one check
> (TRF print timing widening minute ranges) that should be made before the
> figure is treated as final.
>
> §3.2's order-fragmentation table and §4's leak finding stand and, if
> anything, understated the problem. Everything else below is left as written,
> because the method was right and the number was not.

# The screened universe: the first out-of-sample result

**2026-09-07.** Every strategy figure before this doc was measured on the 587
symbol-days Ben actually traded — days he chose in real time, on which every
parameter was then fitted. This is the first run whose universe was produced by
a rule rather than by a person, and it changes the ranking.

**Headline: on IBKR Tiered — the plan settled on, see §3 — MC5 nets +$8,209 and
survives drop-top-5, the first result in this project ever to do so. MCL and
VW9 are closed on any plan. The finding is real and it is fragile: §3.2 shows
it does not survive an execution model with more than about three orders per
round trip.**

---

## 1. What was run

| | |
|---|---|
| Universe | 22,882 stage-2 survivors + 4,995 sampled rejects = 27,877 symbol-days |
| Screen | `common/screen.py` on **EQUS.SUMMARY**, 548 sessions, 2024-07-01 → 2026-09-04 |
| Bars | `bar_cache_db`, built from the Databento archive (`EQUS.MINI ohlcv-1m`), raw prices |
| Engine | `common/backtest.py --offline`, 100 shares flat, **`ibkr_tiered`** commissions |
| Strategies | MCL, MC5, VW9_5M at their shipped configs |

Of the 27,877 requested, **27,383** reached the engine: `load_pairs` drops
dotted and non-alphabetic tickers, which are not US equities. Of those, 25,293
had bars and 2,090 did not. Symbols ran AAA through ZYXI, 6,684 distinct — the
run completed, which matters because a partial run of this engine used to print
a complete-looking summary (see §7).

---

## 2. The result

Survivor days only. Rejects are a control population, not a tradeable universe.

| | trades | symbols | win | gross | commission | **net** | per trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| **MC5** | 7,403 | 1,791 | 31.4% | +18,373 | 10,164 | **+8,209** | **+1.11** |
| MCL | 2,408 | 890 | 32.4% | +2,036 | 3,306 | −1,270 | −0.53 |
| VW9_5M | 1,477 | 699 | 22.7% | −5,291 | 2,034 | −7,325 | −4.96 |

### Concentration — the test that has killed everything else

| drop top | 1 | 3 | 5 | 10 |
|---|---:|---:|---:|---:|
| **MC5** | +6,982 | +4,700 | **+2,537** | −1,965 |
| MCL | −2,451 | −3,848 | −4,829 | −6,580 |
| VW9_5M | −8,483 | −10,243 | −11,775 | −14,334 |

MC5 stays positive through drop-top-5 across 1,791 distinct symbols and only
turns at drop-top-10. Every previous result in this project — MCL, MC5 and VW9
in-sample, every trail candidate, the scale-out, the pyramid, the scale-up —
failed at drop-top-3 or earlier.

MCL and VW9 need no qualification. MCL has a +$0.85/trade gross edge against
$1.37 of commission and one symbol (MBX, +$1,181) worth more than its entire
net loss; it is negative on every plan and every execution model tested. VW9 is
worse out-of-sample than in and fails drop-top-1 by a wide margin.

---

## 3. Commission: Tiered, settled 2026-09-07

### 3.1 The plan

**Decision: IBKR Tiered.** It is what the strategies' `COMMISSION_PLAN` already
declared, what this run charged, and the correct plan at this size.

Fixed only becomes cheaper at **150 shares**, and that crossover is
price-independent — it holds at $2 and at $20, because Fixed's $1.00 order
minimum dominates until the per-share rate catches it. At 100 shares Tiered
costs **$1.3647–$1.4018** per round trip against Fixed's **$2.0242–$2.0613**:
$0.6595 cheaper, flat across the band.

**This was verified, not assumed.** Every one of MC5's 7,403 commissions was
recomputed from `common/commissions.py` and compared with what the run
recorded: $10,158.77 against $10,164.30, a difference of $5.53 across 7,403
trades, entirely explained by the CSV storing two decimal places (largest
per-trade difference exactly half a cent). The same trades priced on Fixed come
to $15,040.92. **The run used Tiered. No re-run was required.**

**One action follows.** The real Flex report shows $19,033 across 18,621
executions — **$1.0221 each**, which is the Fixed $1.00 minimum, not Tiered's
$0.35. The live account therefore appears to be on **Fixed**, while every
backtest in this project prices Tiered. At a 99-share median execution that is
costing roughly 66 cents a round trip for nothing, quite apart from the
modelling mismatch. Confirm the plan from a statement and switch it.

### 3.2 What Tiered does NOT settle, and this is now the live threat

The engine models **one buy and one sell**. The real report is 18,621
executions across 1,658 positions — about **11 orders per round trip** — and
each one that IBKR bills separately pays an order minimum. MC5's edge is
$1.11/trade against $1.37 of modelled commission, so this is not a rounding
concern:

| orders per round trip | comm/trade | MC5 net | drop 3 | drop 5 |
|---:|---:|---:|---:|---:|
| **2** (as modelled) | $1.37 | **+8,215** | +4,706 | +2,543 |
| 4 | $2.07 | +3,029 | −480 | −2,643 |
| 6 | $2.77 | −2,107 | −5,616 | −7,780 |
| 11 (Ben's observed rate) | $4.17 | **−12,528** | −16,037 | −18,200 |

**MC5's edge disappears somewhere between three and four orders per round
trip.** Choosing Tiered buys real headroom here — the same table on Fixed goes
negative at four orders and reaches −$39,666 at eleven — but it does not make
the question go away.

Two things are unknown and both are cheap to settle:

1. **Whether Ben's 11-per-round-trip rate is a property of the market or of his
   order handling.** Market orders into thin small caps fragment; a single
   marketable limit for 100 shares often does not. An algo's rate could be near
   2. Nobody has measured it.
2. **Whether IBKR bills per order or per execution.** Partial fills of one
   order are normally aggregated, which would make the table above far too
   pessimistic. But $19,033 across 18,621 executions is ~$1 each — consistent
   with per-execution billing, or with ~18,621 genuinely separate orders. The
   statement will say which.

Until both are answered, **+$8,209 is the optimistic end of a range whose
pessimistic end is −$12,528**, and the sign of MC5's edge is an execution
question rather than a strategy question.

### 3.3 The crossing-cost adjustment, stated separately on purpose

`execution_cost_measured.md` measured crossing at **$1.00** per 100-share round
trip against the **$2.00** the engine charges, so §2 is conservative by about
$1.00 per trade — MC5 would be roughly +$15,600.

**Do not stack it with §3.2 to rescue a marginal case.** It is arithmetic
applied on top of a completed run, not a re-run; it was measured on MCL's
pre-market $2–20 subset and applied to MC5 on the assumption the two trade the
same window; and a conclusion needing two favourable adjustments to clear a
threshold is exactly what this project's standards of evidence exist to catch.
The right move is one re-run at the settled plan, the measured slippage, and a
measured order count.

---

## 4. The leakage control

Stage 1 of the screen is decidable at 03:59. Stage 2 uses the session's own
daily bar — today's RVOL and today's range — and therefore reads the answer
first. The control asks how much of the result that explains, by running the
same strategies over symbol-days the screen **rejected**.

| | survivor days | entries/day | rejected days | entries/day | ratio |
|---|---:|---:|---:|---:|---:|
| MCL | 21,407 | 0.112 | 3,886 | 0.001 | 1% |
| MC5 | 21,407 | 0.346 | 3,886 | 0.024 | 7% |
| VW9_5M | 21,413 | 0.069 | 4,007 | 0.012 | 18% |

All three pass the ratio test at `SMALL_LEAK_RATIO = 0.25`. On the entry side,
stage 2 is mostly discarding days the strategy would have skipped anyway — the
filter agrees with the strategy rather than informing it.

(The day counts differ slightly for VW9 because it slices a different window —
one session to 20:00 rather than two to 09:30 — so a different set of days has
adequate bars. Same universe, different coverage.)

### The cut the tool does not make, and it is the sharper one

The ratio test counts entries. It does not ask whether the days stage 2
discarded were different in **kind**:

| | survivor days | rejected days | n rejected |
|---|---:|---:|---:|
| MCL | −0.53/trade | +0.02/trade | 5 |
| **MC5** | **+1.11/trade** | **−7.21/trade** | **92** |
| VW9_5M | −4.96/trade | −6.17/trade | 50 |

**On the days stage 2 threw away, MC5 loses money.** n = 92 and the total is
only −$664, so this is a signal rather than a measurement. But the sign and the
size say stage 2 may be selecting the days MC5 works on rather than merely
agreeing with it — and stage 2 is precisely the part that cannot be evaluated
at 03:59.

With §3.2, this is what stands between MC5's result and being believable.
`common/leak_control.py` does not measure it and should.

---

## 5. What this result does not establish

- **The execution model** (§3.2). Decisive, and unmeasured.
- **It is one universe definition.** The screen's RVOL ≥ 5 and range ≥ 10%
  thresholds are unmeasured guesses, and the 60/day cap binds on 53 of 548
  sessions. A different screen is a different experiment.
- **It is 100 shares flat.** Capital-based sizing has flipped a strategy's sign
  in this project before. The compounding replay has not been re-run here.
- **The dates overlap the fitting window.** The screen covers 2024-07-01 to
  2026-09-04; MC5's parameters were chosen on days inside it. The universe is
  out-of-sample, the calendar is not.
- **No temporal holdout has been applied to this result.**

---

## 6. What to do next, in order

1. **Measure orders per round trip for an algo-placed 100-share position**, and
   establish from a statement whether IBKR bills per order or per execution.
   §3.2 says the sign of MC5's edge hangs on this, and nothing else on this
   list matters until it is answered.
2. **Switch the live account to Tiered** if the statement confirms it is on
   Fixed. Worth ~66c a round trip on real trading regardless of MC5.
3. **Measure the survivor-vs-rejected P/L gap properly**, with enough rejected
   days to say whether MC5's −$7.21/trade is real. Extend `leak_control.py` to
   report it rather than computing it by hand.
4. **Temporal holdout on MC5** over this universe: split 2024-07-01→2025-08-31
   and 2025-09-01→2026-09-04, require the effect in both.
5. **Re-run the compounding replay** on the screened MC5 trades. In-sample it
   turned $10,000 into $24,464 at 60/100; that was the hindsight universe and
   means nothing until re-run here.

---

## 7. A note on how nearly this went wrong

The first attempt at this run died at pair 511 of 27,877 with a Windows
`PermissionError` on the state-file rename, **and printed a complete-looking
result**: 61 trades, NET +190.54, a concentration table, best and worst
symbols. Every symbol in it began with A, because pairs process in list order.
Nothing in the output said the run had covered 1.8% of the universe.

Three fixes shipped the same day: the state file checkpoints every 50 pairs
instead of every one (it grows with the run, so per-pair is O(n²) bytes and
27,877 chances for the rename to lose a race with a virus scanner); the rename
retries and, if it truly cannot proceed, says what holds the file; and
`report()` now knows how many pairs it was asked for, leads with a PARTIAL RUN
banner, and writes a partial run's trades to `.partial.csv` — a name nothing
downstream reads.

The figures above were computed from the trades CSV by a separate script rather
than taken from the engine's own summary. Given the above, one code path was
not enough — and it was that second pass that turned up the commission
question in §3, which the engine's summary would never have shown.
