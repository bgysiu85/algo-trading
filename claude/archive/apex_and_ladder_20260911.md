# MC5's signal exit, and the take-profit ladder — 2026-09-11

Two changes asked for on 2026-09-10 after the paper session. One is adopted, one
is rejected, and one produced a result **against a registered prediction**.

| | verdict |
|---|---|
| MC5's gradient-reversal exit | **TURNED OFF.** +$3,177, both halves, drop-top-3 nearly 5× better |
| Take-profit ladder on **MCL** | **Better, and I predicted otherwise.** +$272 → +$106 after friction. Not yet adoptable — see §3.3 |
| Take-profit ladder on **MC5** | **Rejected.** −$128 and the sign flips between halves |

Tools: `common/mc5_apex_sweep.py`, `common/ladder_study.py`,
`common/profit_ladder.py`. Reports: `var/reports/mc5_apex.txt`,
`ladder_mcl.txt`, `ladder_mc5.txt`. Shipped in `20260910t` + the flip.

---

## 1. MC5's gradient-reversal exit — off

The same mechanic MCL calls the apex exit, retired there on 2026-09-05. MC5
fired `exit_sig` unconditionally and had no switch, so it had never been
measured. 373 sessions, 5-minute bars, 100 shares, net of tiered commission and
$4.26/RT:

| | trades | net | per trade | win% | drop-top-3 |
|---|---:|---:|---:|---:|---:|
| apex ON | 762 | +$2,794 | +$3.67 | 30.4% | +$765 |
| **apex OFF** | 671 | **+$5,971** | **+$8.90** | 34.9% | **+$3,718** |

Positive in both halves (+$2.97 early, +$7.07 late) and the concentration check
improves nearly fivefold — the check that has killed most things in this
project.

**The direct measurement is the reason, not the total:**

| exit reason (apex ON) | n | net | per |
|---|---:|---:|---:|
| **gradient_reversal** | **138** | **−$1,687** | **−$12.23** |
| trailing_stop | 603 | +$4,404 | +$7.30 |
| window_close | 21 | +$78 | +$3.70 |

The rule was closing positions the trail had not stopped, and losing $12 each
time. Identical finding to MCL's, on a strategy with five times the bar
resolution. `USE_APEX_EXIT = False` in `strategy/mc5/mc5.py`, with the figures
recorded at the constant.

**Still in-sample**, and it does not rescue MC5 — which is −$8.93/trade on the
screened XNAS universe. It makes a closed candidate less bad on the set it was
fitted to.

### 1.1 A second implementation that had drifted

Flipping the constant broke `test_harness_equivalence`. `common/harness.py` is a
second implementation of MC5, and `mc5_rules()` — whose docstring says *"MC5's
own constants, read off the module rather than retyped — a copy here would
drift"* — passed `use_exit_signal=True` as a **hard-coded literal**. The one
copy in a function written to prevent copies.

It now reads `mod.USE_APEX_EXIT`. The test did its job: a constant the second
engine does not follow is a silent divergence, and that is exactly what it
exists to catch.

### 1.2 An exit label that could not be joined

Also found: `trader.py` hard-coded `"apex_reversal"` for **every** strategy,
while `mc5.py`'s backtest wrote `"gradient_reversal"` for the same rule. Both
now land in one `paper_fill` table beside `backtest_trade`, and a query grouping
the two on `reason` would have found no MC5 signal exits on one side and read it
as an **absence** rather than a mismatch.

The label is now `EXIT_SIGNAL_REASON` on each strategy, carried through the
adapter. MC5 live rows before 2026-09-11 say `apex_reversal` for what is now
`gradient_reversal` — six rows from one session, recorded rather than rewritten.

---

## 2. The ladder — what it is

Ben's rule, pinned before any code: **sell 50% of the current position on every
+10%, compounding from the last rung; at or below 20 shares the next rung takes
the whole remainder.** On 100 shares: 50 / 25 / 12 / 13 at +10.0% / +21.0% /
+33.1% / +46.4%.

**Not the scale-out rejected on 2026-09-05.** That sold into a *pullback* and
bought back on the recovery. This sells into *strength* and never re-enters.

Two ways it could have flattered itself, both closed before running: rungs test
against the **close**, never the bar's high (a rung tagged only by the high is
one the strategy could not have acted on — worse on MC5's 5-minute bars); and
`int()` truncates, so 25 → 12, and the position can never be oversold.

The ladder is **last** in the exit order on both engines: a bar that clears a
rung *and* trips the trailing stop resolves as the stop.

---

## 3. MCL — better, against a registered prediction

`profit_ladder.py` recorded the expected sign as **negative** before the run, on
`mcl_scale_out_decision.md` §4's argument: with size held constant, selling part
of a winner cannot earn more on a runner than holding it. `hold_cap_decision`
had just measured MCL's best bucket as 60+ bars at +$36.33/trade.

**That prediction was wrong.**

| | trades | net | per trade | win% | drop-top-3 |
|---|---:|---:|---:|---:|---:|
| hold (baseline) | 485 | +$161 | +$0.33 | 34.0% | −$923 |
| **ladder** | 485 | **+$433** | **+$0.89** | 34.0% | **−$598** |
| ladder, linear | 485 | +$430 | +$0.89 | 34.0% | −$602 |

+$272, positive in both halves (+$0.93 early, +$0.35 late), and drop-top-3
improves. Same trade count, same win rate — it changes the size of outcomes, not
which trades are taken, which is what a profit-taking rule should do.

**The linear control lands within $3.** So the result is not about rung spacing;
it is about taking profit at all. That strengthens it — a finding true of one
spelling of the rule and not the other would have been about the spacing.

### 3.1 Why it works here, when the time cap did not

| | reached +10% | of those, reached +21% |
|---|---:|---:|
| MCL | 53 of 485 (10.9%) | 15 (**28.3%**) |
| MC5 | 88 of 762 (11.5%) | 40 (**45.5%**) |

**On MCL, seven in ten trades that reach +10% never reach +21%.** Selling half
at the first rung banks a gain the trail would mostly have surrendered. A time
cap cut winners and losers alike; a ladder only ever sells a winner, so the left
tail is untouched.

MC5's runners go substantially further, which is why the same rule costs it
money (§4). The asymmetry is the explanation, not a coincidence.

### 3.2 The friction correction, which halves it

`ladder_study` deducts `MEASURED_FRICTION = $4.26` **once per round trip**,
regardless of how many slices the exit took. The ladder issues more orders, so
that approximation favours it. Measured exactly by instrumenting `plan()`:

| | |
|---|---:|
| ladder slices fired | 78 |
| extra exit orders vs baseline | **78** |
| break-even cost per extra order | **$3.49** |
| MEASURED_FRICTION per order ($4.26 / 2) | $2.13 |
| **gain after charging that** | **+$106** |

The edge survives the obvious correction but loses 60% of itself. Per-share
slippage is unchanged (the same 100 shares leave either way); what the extra
orders cost is per-order crossing and commission minimums on odd lots, which
this only approximates.

**Zero trades were finished by the ladder.** It never completed all four rungs —
it de-risks and the trail or the 09:30 close takes the remainder. So this is a
partial-de-risking result, not a "take profit and go" one.

### 3.3 Why it is NOT adopted yet

- **drop-top-3 is still −$598.** Better than −$923, but MCL's profit is still
  carried by three trades. The ladder improves concentration; it does not fix it.
- **In-sample**, on the 373 hindsight-selected sessions MCL was fitted to.
- **The holdout does not apply.** `ladder_mcl.txt` says "spend the holdout on
  it" and **that instruction is wrong for this cache**: `holdout.json` was cut
  over the **screened** universe, not `bar_cache`. Spending it on a `bar_cache`
  result is the dataset-mixing error caught in `consolidation_filter_test.md`
  and again in `prior_spike_result.md`. The report's verdict text needs that
  guard added.
- **The right next step is `bar_cache_xnas`**, where the holdout is meaningful
  and where MCL is −$5.22/trade. A rule that improves a losing strategy on the
  screened universe would be worth far more than one that improves a
  marginally-positive one on the fitted set.

---

## 4. MC5 — rejected

| | trades | net | per trade | drop-top-3 |
|---|---:|---:|---:|---:|
| hold (baseline) | 762 | +$2,794 | +$3.67 | +$765 |
| ladder | 762 | +$2,666 | +$3.50 | +$706 |

−$128, and **the sign flips between halves** (+$0.47 early, −$0.73 late). Worse
on the total, worse after drop-top-3, and not stable across the sample. Rejected
on all three counts.

Note this baseline is apex ON, since the run predates the flip. The ladder
should be re-run against apex OFF before the rejection is treated as final —
the two rules interact, because both cut a winner short.

---

## 5. What is in the code

- `strategy/mc5/mc5.py`: `USE_APEX_EXIT = False`, `EXIT_SIGNAL_REASON`,
  `use_apex` and `ladder` call parameters. Exit accounting rewritten to
  accumulate realised P/L and commission — pinned bit-identical with no ladder.
- `strategy/mcl/mcl.py`: `EXIT_SIGNAL_REASON`, `ladder` parameter.
- `common/profit_ladder.py`: the rule, its pinned parameters, and the registered
  prediction that turned out wrong.
- **Neither ladder is enabled anywhere.** `ladder=None` on both engines and
  nothing in `brokers/ibkr/trader.py` touches it.

A bug worth recording: when the ladder took the last share in MCL, `pos = None`
fell through into peak maintenance and dereferenced it. It raised `TypeError`
rather than returning a plausible wrong number — the one merciful way for that
to fail — and its own test caught it.

## 6. Next

1. **Re-run the MC5 ladder against apex OFF.** The current rejection compares it
   to a baseline that has since changed.
2. **Run both ladders on `bar_cache_xnas`**, where the holdout applies and where
   both strategies actually lose money.
3. **Fix `ladder_study`'s verdict text** so it cannot tell anyone to spend a
   holdout that was cut over a different universe.
4. Only then consider registering the MCL ladder.
