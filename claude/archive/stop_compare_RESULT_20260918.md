# The give-back's shape against a flat daily stop — UNDECIDED at every cell, and the holdout is not spent

2026-09-18. Under `docs/research/REGISTERED_stop_compare.md` (H-S6), committed in
`4ce32d3` before `common/stop_compare.py` existed. Run off
`session_scenarios_trades.csv` — the same 14,870 trades over 550 sessions H-S4
passed on, no second pass over the tape. Raw: `stop_compare_20260918.txt`.
Figures at **$4.26** unless stated.

---

## 0. In one paragraph

**No cell survives.** Three of the four read **UNDECIDED** and one reads **THE
SHAPE ADDS NOTHING**, and §4 says the holdout is spent on neither rule. The
difference is not small — on MC5 the matched flat stop captures almost *none* of
the give-back's gain (+0.03 a trade against +0.68), which is the opposite of
what I predicted — but it is **not distinguishable from zero across sessions**:
the session-clustered bootstrap reads 0.932 and 0.934 where §4 requires 0.95,
and at **$8.92, the friction this project believes, MC5 strategy scope collapses
to +0.21 with P = 0.665.** On MCL the flat stop is the better of the two rules
outright. **The give-back's own H-S4 pass stands; what is now unsupported is the
attribution** — that the *50% peak-relative shape* is what did the work.

---

## 1. The four cells

| | | D_give | D_flat | difference | bootstrap P | verdict |
|---|---|---:|---:|---:|---:|---|
| **MC5** | strategy $4.26 | **+0.68** | +0.03 | **+0.64** | 0.932 | |
| **MC5** | strategy $8.92 | +0.60 | +0.39 | **+0.21** | 0.665 | **UNDECIDED** |
| **MC5** | session $4.26 | +0.78 | +0.07 | +0.71 | 0.934 | |
| **MC5** | session $8.92 | +0.76 | +0.13 | +0.63 | 0.891 | **UNDECIDED** |
| **MCL** | session $4.26 | (0.35) | (0.65) | +0.30 | 0.709 | |
| **MCL** | session $8.92 | (0.33) | (0.61) | +0.28 | 0.666 | **UNDECIDED** |
| **MCL** | strategy $4.26 | (0.16) | **+0.24** | **(0.40)** | 0.210 | |
| **MCL** | strategy $8.92 | +0.34 | +0.26 | +0.08 | 0.590 | **ADDS NOTHING** |

§4 requires `D_give > D_flat` **and** the bootstrap ≥ 0.95, at **both** $4.26 and
$8.92. `D_flat >= D_give` at either level ends it, which is what MCL under
strategy scope does at $4.26.

**The first thing to check was that this reproduces H-S4 exactly, and it does.**
Every `D_give` and every removal count in the report is identical to
`session_scenarios_RESULT_20260918.md` — +0.78 / +0.68 for MC5, (0.35) / (0.16)
for MCL, 1,022 trades removed at $4.26 under session scope. That is the "no
second pass over the tape" property working: the two studies cannot disagree
about the incumbent, because they are reading one book.

**And the budgets really are matched.** The solved stop removes 666 where the
give-back removed 667, 1,022 against 1,022, 320 against 321, 807 against 804 —
never more than three trades apart out of hundreds. Both rules spend the same
abstention budget and the only thing that differs is which trades they spend it
on, which was the whole design.

## 2. My prediction was wrong in an interesting direction

Registered, before the run: *the shape survives narrowly, `D_give − D_flat` of
+0.10 to +0.50, bootstrap marginal, moderate confidence*, on the reasoning that
*"I expect the flat stop to capture most of the give-back's 78 cents and the
residual to be small."*

**The residual is not small. The flat stop captures essentially nothing** — +0.03
a trade against the give-back's +0.68, and +0.07 against +0.78. The magnitude
came in *above* my band on MC5, not inside it. What I got right was the word
"marginal", and it is the bootstrap, not the magnitude, that killed it.

So the honest scoring is: **wrong on the mechanism, wrong on the verdict, right
on the fragility.** A large per-trade difference sitting at P = 0.93 means the
difference lives in relatively few sessions — the give-back fires on 126
sessions, the flat stop on 119, and they **share only 35**. Three-quarters of
each rule's fires are its own. That is §1's "genuinely different rules" borne
out far more strongly than the registration expected, and it is also why the
effect cannot be pinned down: it rests on the ~91 sessions where only the
give-back fires.

## 3. What kills it is $8.92, and the reason is the flat stop, not the give-back

MC5 under strategy scope, across the friction ladder:

| friction | D_give | D_flat | difference |
|---|---:|---:|---:|
| $1.00 | +0.67 | +0.04 | +0.63 |
| $4.26 | +0.68 | +0.03 | +0.64 |
| **$8.92** | +0.60 | **+0.39** | **+0.21** |

**The give-back barely moves. The flat stop gets thirteen times better.** At
higher friction more sessions reach a given dollar drawdown, so a stop solved to
the same removal count sits deeper and fires on sessions that genuinely went
wrong rather than on sessions that merely paid friction. The give-back has no
equivalent gain because its arm is already a dollar threshold.

This matters more than the arithmetic. §4 required both levels precisely because
the measured $4.26 is known to be too small by roughly half, and **$8.92 is the
level the project treats as honest.** A rule that clears at $4.26 and reads +0.21
at $8.92 has not cleared. This is not a near miss at the level that counts.

## 4. MCL: the flat stop is the better rule

Under strategy scope at $4.26, MCL's give-back reads **(0.16)** a trade and the
matched flat stop reads **+0.24**. The flat stop's removed trades are worth
**(11.63)** against the give-back's **(7.18)** — it is picking genuinely worse
trades to refuse. Neither clears anything: MCL still loses about $9 a trade
either way. But between the two, the peak-relative shape is the worse one on the
strategy that is actually live, and §4's rule ends that cell on the spot.

## 5. The give-back is the *less* time-of-day-like of the two

H-S4 §5 named the time-of-day filter as the most likely way its result would be
fake, and the scenarios run cleared the give-back on a spread fire clock. The
comparator lets that question be asked of both rules at once, and the answer is
one-sided. MCL, strategy scope, $4.26:

| ET hour | 04:00 | 05:00 | 06:00 | 07:00 | 08:00 | 09:00 |
|---|---:|---:|---:|---:|---:|---:|
| give-back fires | 10 | 24 | 24 | 42 | 34 | 10 |
| flat stop fires | 8 | 22 | 33 | **86** | **82** | 24 |

**A flat stop needs losses to accumulate, so it fires late by construction** —
two-thirds of its fires land in the 07:00 and 08:00 hours. The give-back, which
needs a peak first and then a retreat, is spread across the morning. Whatever
else is true, the peak-relative rule is not the one that is secretly a clock.

## 6. The loudest number in the report, and why it is not a result

`FLAT-40` on MC5 at $4.26 under session scope reads **+3.93 a trade**. It is the
biggest per-trade improvement anywhere in this project's gate work, it is close
to the $4.26 margin, and **it is not a result**:

- It removes **4,606 of 6,462 trades** — 71% of the book. Nothing in this report
  compares two rules at different removal counts, because a per-trade delta
  scales with the share removed; that is exactly why the comparator is
  count-matched.
- **It has no control.** The matched-count random removal that H-S4 amendment A4
  runs against the give-back was never run against a fixed stop.
- §3 of the registration says the fixed stops are **reported and never scored**,
  and that no fixed stop may be quoted as the comparator afterwards. That
  sentence was written before anyone had seen this number, which is the only
  reason it can be trusted now.

What it is: a hypothesis for a future registration — *a very tight daily stop on
MC5*, with its own abstention control and its own pre-stated bar. It is not
adoptable, it is not quotable, and a 71%-abstention rule on a losing book is
precisely the shape §4 warns about.

## 7. What this decides, and what it does not

**`holdout.json` is not spent.** §4 is explicit: the difference positive and the
bootstrap short is UNDECIDED, and neither rule earns the spend. It stays shut,
untouched, as it has since 2026-01-12.

**H-S4's pass is not withdrawn.** MC5's give-back cap still clears all six of its
registered readings against a random cut in the same sessions. What this run
removes is the *attribution*: the claim that the **50% peak-relative shape** is
what produces those 78 cents is now unsupported at the friction that matters.
The cap is doing something; that it is doing it *because* it is peak-relative is
not demonstrated.

**And the practitioners' 50% is still a number without a mechanism.** Cameron and
Malyarovich arriving independently at the same figure was the reason H-S4 was
registered at all. This test was the cheapest way to find out whether the shape
carried information, and the answer is that it might, in about ninety sessions,
at a confidence this project does not accept.

## 8. What is not decided by any of this

Not out of sample — `holdout.json` is untouched. Not live: the trader has no
session-state rule of either kind, and H-S4 §6's parity requirement stands for
whichever rule ever ships — the live path must compute `realised` exactly as the
backtest does, and this project has been bitten three times by a constant the
live path never read. Not a cap model: each symbol-day runs alone, and a stop
that frees concurrency slots is priced by neither rule. Not a search — one
give-back, one solved comparator, three fixed stops named and fenced off before
the run.

## Commands run

```
python -m common.stop_compare
```
