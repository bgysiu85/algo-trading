> **ARCHIVED 2026-09-08.** VW9 is rejected on history and paper-traded only for live data; its rules live in `vw9_strategy_spec.md`.
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

# VW9 Setup B, standalone — 2026-09-05

The one open question that could have reopened VW9. `vw9_first_results.md` §6:
Setup A is 81% of triggers and is where the damage is; Setup B had never been
run on its own with the price band on.

**Verdict: it fails the same test, and the one check it passes is a single
stock. VW9 is closed rather than pending.**

Code: `strategy/vw9/backtest.py` (`only_setup`), `strategy/vw9/setup_b_study.py`.
Output: `var/reports/vw9_setup_b.txt`.

---

## 1. Why this is not the slice already reported

§6 quoted Setup B at +$24.67/trade by filtering `kind == "B"` out of a mixed
run. `only_setup` filters **before** the entry cap and **before** the
no-overlap block, so B is no longer competing with A for either.

The expectation was that this would materially free B up. It did not:

| | trades | real net | per trade |
|---|---:|---:|---:|
| Setup B, sliced from the mixed run | 86 | +$1,723 | +$20.03 |
| **Setup B, run standalone** | **97** | **+$1,284** | **+$13.23** |

Eleven extra trades, and the per-trade figure got **worse**. Setup A was not
suppressing a better strategy; it was crowding out a handful of marginal
trades. **The premise for running this was largely wrong** — recorded because
the reasoning was plausible and still incorrect, which is the kind of thing
that otherwise gets quietly forgotten.

## 2. The result, against the bar that rejected VW9

374 sessions, 5m, `trail_atr`, VWAP exit off, band on, MCL's friction applied
per share transacted.

| | trades | real net | per trade | drop3 | drop5 | profitable |
|---|---:|---:|---:|---:|---:|---|
| mixed (as rejected) | 407 | +$7,118 | +$17.49 | −$5,610 | −$6,441 | 46/150 |
| **Setup B only** | 97 | +$1,284 | +$13.23 | **−$1,857** | **−$2,225** | **18/58** |
| Setup A only (control) | 337 | +$4,689 | +$13.92 | −$7,034 | −$7,797 | 45/143 |

| check | | |
|---|---|---|
| drop-top-3 positive | **FAIL** | −$1,857 |
| drop-top-5 positive | **FAIL** | −$2,225 |
| majority of symbols profitable | **FAIL** | 18/58 (31%) |
| RTH profitable on its own | **PASS** | +$1,650 |

## 3. The one PASS, opened up

That check was the entire reason to run this. §9 is explicit that pre-market
fills are the ones the model cannot support — Day Limit orders only, no market
order, no resting stop — so RTH is the only window where the numbers mean
anything. B is the only VW9 variant with profit there:

| block | trades | real net | per trade |
|---|---:|---:|---:|
| PRE | 36 | −$202 | −$5.61 |
| **RTH** | **54** | **+$1,650** | **+$30.56** |
| POST | 7 | −$164 | −$23.49 |

Then look inside it. RTH is 54 trades across 40 symbols:

| | RTH net |
|---|---:|
| all 40 symbols | +$1,650 |
| **drop the best 1 (AEHL, +$2,228)** | **−$578** |
| drop the best 3 | −$1,005 |
| drop the best 5 | −$1,254 |
| profitable symbols | **14 / 40** |

**One stock is the entire believable-window result.** AEHL is +$2,228 against
a total net of +$1,284 — 174% of the strategy. That is the same failure that
rejected the mixed version, where WLDS and PLYX together were $11,290 of a
$9,005 result. Setup B is not a different outcome; it is the same outcome at
a quarter of the size.

## 4. What this closes

VW9 has now been tested on everything §6 listed as capable of changing the
verdict, except the stop structure. It is not worth running that either, and
the reason is arithmetic rather than judgement: the stop question is about
sizing the loss on losing trades, and this strategy's problem is that its
*winners* are two or three names. A better stop cannot manufacture breadth.

**VW9 moves from "rejected, pending one more test" to closed.** Reopening it
needs a different kind of evidence, not another parameter:

1. **A universe that is not hindsight-selected.** Every VW9 number rests on
   374 pairs chosen because they ran. Concentration is exactly the metric that
   bias distorts most, and it is the metric VW9 fails on.
2. **Measured pre-market fills.** Still unmeasured for VW9 specifically; every
   figure above borrows MCL's friction, itself n=2.

Neither is a VW9 task. Both are the same blockers standing in front of
everything else in this project.

## 5. A bug this run hit, and it is the documented one

The first run used `common.analysis.load_sessions`, which slices **MCL's**
window — two sessions ending 09:30. VW9 needs **one session ending 20:00**
(`strategy/vw9/preflight.load`). With MCL's slice, every VW9 trade lands in
pre-market **by construction**, because the frame contains no RTH bars at all.

It reported 176 trades, 100% PRE, 0 RTH, against the documented 407. No error,
no warning — a smaller, entirely plausible, meaningless answer. The only tell
was that "all of Setup B is pre-market" flatly contradicted §6's own finding
that B's profit was in RTH.

PROGRAM_INDEX §3 already says "any offline consumer must read the superset and
SLICE it". The refinement worth adding: **slice it to that strategy's own
window**, and sanity-check the trade count against a published run before
reading anything into the result.

---

## Caveats

- Same 374-session hindsight-selected pair set; 33 pairs have no cached bars.
- Friction is MCL's $0.0213/share transacted, measured on two sessions under an
  exit mix that no longer exists. VW9's own friction remains unmeasured.
- `only_setup` has no test coverage yet, and neither do the nine other exit
  knobs ported to VW9 from MCL on 2026-09-05. Dormant code, but real debt.
