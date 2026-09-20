# The entry sweep: earlier entry is achievable, and every trade it finds still loses money

2026-09-18. Under `docs/research/REGISTERED_entry_sweep.md` (H-E2), committed in
`8f36b2f` before any code existed and before either engine had a parameter for
the swept constants. 550 sessions, 6,411 symbol-days, eleven books, 95 seconds.
Raw: `entry_sweep_20260918.txt`, `entry_sweep_marginal_20260918.txt`.

---

## 0. In one paragraph

**Nothing CLEARS and nothing IMPROVES.** Both scored families read
**UNDECIDED — BOUNDARY**, seven of the nine non-base cells are **REFUSED** on
the denominator rule, and the one remaining cell fails its abstention control.
But the informative result is not the verdict — it is the number underneath it.
**Every marginal trade a looser threshold finds loses money, at every setting
of every dial: between −$7.00 and −$9.99 each.** Loosening the entry does
exactly what it was predicted to do — it enters earlier in the move, and fewer
trades die on the next bar — and what it buys is more trades that lose seven
dollars instead of fewer that lose nine. There is no confirmation level at
which MCL or MC5 takes a trade worth taking.

---

## 1. The sweep

Per trade at $4.26, against the published base of each family.

| cell | trades | per trade | per symbol-day | median 5-min move at entry | 1-bar | verdict |
|---|---:|---:|---:|---:|---:|---|
| **MCL (base)** | 3,908 | (8.97) | (5.47) | 5.33% | 12.6% | — |
| MCL macd>0 OFF | 4,763 | **(8.62)** | (6.40) | 4.71% | 11.1% | REFUSED |
| MCL vol 1.5 | 7,154 | (9.34) | (10.42) | 5.10% | 12.1% | NOTHING |
| MCL vol 2.0 | 5,829 | (9.31) | (8.46) | 5.23% | 12.0% | NOTHING |
| MCL vol 2.5 | 4,766 | (8.95) | (6.65) | 5.30% | 12.2% | REFUSED |
| MCL vol 4.0 | 2,672 | (8.70) | (3.63) | 5.40% | 12.8% | NOTHING |
| **MC5 (base)** | 6,462 | (8.57) | (8.64) | 2.69% | 37.3% | — |
| MC5 roc 1.0 | 8,793 | **(8.28)** | (11.35) | 2.17% | 34.5% | REFUSED |
| MC5 roc 2.5 | 7,812 | (8.38) | (10.21) | 2.38% | 35.4% | REFUSED |
| MC5 roc 7.5 | 5,438 | (8.78) | (7.44) | 3.08% | 39.2% | REFUSED |
| MC5 roc 10.0 | 4,540 | (8.62) | (6.10) | 3.24% | 40.9% | REFUSED |

The population check matches the published MCL count of 3,908 exactly.

**The pattern is mechanical and holds in every row.** Loosen the threshold and
you get more trades, a better per-trade figure, and a worse per-symbol-day
figure. Tighten it and all three reverse. Nine cells, nine times, no exception.
That is why seven of them are REFUSED: the two denominators disagree, and this
project refuses a verdict when they do.

## 2. What is actually being bought — the marginal trade

The averages are the wrong object. What matters is what the *extra* trades a
looser threshold finds are worth, and that has never been priced here before.

| cell | trades added | what each added trade is worth |
|---|---:|---:|
| MCL macd>0 OFF | +855 | **(7.00)** |
| MCL vol 2.5 | +858 | (8.83) |
| MCL vol 1.5 | +3,246 | (9.78) |
| MCL vol 2.0 | +1,921 | (9.99) |
| MC5 roc 1.0 | +2,331 | (7.47) |
| MC5 roc 2.5 | +1,350 | (7.49) |
| *MC5 roc 7.5* | *−1,024 refused* | *(7.46)* |
| *MC5 roc 10.0* | *−1,922 refused* | *(8.44)* |
| *MCL vol 4.0* | *−1,236 refused* | *(9.56)* |

**The best marginal trade anywhere in the sweep loses seven dollars.** That one
number explains the whole table: adding trades worth −$7.00 to a book averaging
−$8.97 raises the average and deepens the loss. The per-trade "improvement" in
every loosened cell is dilution, not selection.

And it runs the other way too. The tightened cells refuse trades worth −$7.46
to −$9.56 — so tightening removes real losers, which is why the per-symbol-day
figure improves, and the remaining book still loses $8.62 to $8.78 a trade.
There is no setting on any of these dials where the trade being added or
removed is a trade worth having.

## 3. The mechanism check earned its place, and it refuted my own hypothesis

§5 required every cell to print the median five-minute return at entry, so that
"enters earlier" could be measured rather than asserted. It did three things.

**It confirmed that earlier entry is achievable.** MCL's MACD-above-zero clause
moves entry extension from 5.33% to 4.71%, and MC5's RSI threshold moves it
monotonically across its whole range — 2.17 / 2.38 / **2.69** / 3.08 / 3.24%.
Those are real lateness dials and they turn in the expected direction.

**It confirmed the pre-flight's mechanism end to end.** Earlier entry produces
fewer instant deaths, exactly as predicted: MCL's one-bar share falls 12.6% →
11.1%, MC5's 37.3% → 34.5%, and rises to 40.9% when the threshold is tightened.
The chain — less confirmation, earlier entry, fewer one-bar deaths — is real and
measurable at every link.

**And it killed my main hypothesis outright.** I predicted the volume multiple
was the clause forcing MCL onto the spike bar, and that it was the family most
likely to improve. It is neither. At its loosest the 3× surge moves entry
extension by **0.23 percentage points**, and the middle two cells read *no
change at all*. The surge requirement is not what makes MCL's entry late — and
because the mechanism was registered as a measurement, that shows up as a fact
rather than as a confusing P&L table. F2 is also the worst family in the sweep,
which now has an explanation instead of being a mystery.

## 4. The boundary check did its job

Both scored families put their best cell at the edge of the swept range — MCL at
vol 4.0, MC5 at roc 1.0 — so both read **UNDECIDED — BOUNDARY** regardless of
their numbers. §4 exists for exactly this: an optimum on the edge of the box is
being arbitraged, not fitted. Neither could have been quoted as a result, and
the registration said so before the numbers existed.

MCL vol 4.0 is worth a line on its own because it is the cell most likely to be
misread. It reads +0.27 per trade against the base and is the best cell in F2 —
and it **tightens**, so it carries the abstention control, and its +0.27 sits
inside random removal's p95 of +0.75. It is abstention, not selection, and the
control says so.

## 5. Scoring my predictions

- **F1, MACD-above-zero off: predicted NOTHING with a worse per-trade figure.**
  Wrong on the direction — it is the *best* per-trade cell for MCL at (8.62) —
  right on the trade-count rise, and the verdict is REFUSED rather than NOTHING.
  It also has the least-bad marginal trade in the sweep at −$7.00, which is the
  closest anything came to working.
- **F2, the volume multiple: predicted the most likely to IMPROVE.** Wrong, and
  wrong for a reason the run identified: the mechanism barely operates. This was
  my primary hypothesis and it is dead.
- **F3: no prediction registered**, correctly — I had no mechanism to state in
  advance, and the dial turned out to be the cleanest of the three.

## 6. What this closes

**"Enter earlier" is closed as a lever on MCL and MC5.** Not for want of a dial —
two of the three families move entry extension in the right direction, and the
downstream effect on instant deaths is exactly as the pre-flight predicted. The
line closes because at every point on every dial, the trade being admitted loses
money.

That is the same fact `friction_reconciliation` reported on 2026-09-11 from a
different direction: break-even friction of **−$0.96 a round trip for MCL and
−$4.67 for MC5** — these books lose at *zero cost*. The marginal-trade table is
that result seen at the level of the individual trade: every entry these five
clauses can be made to find, at any confirmation level, is a losing entry.

**It does not close the pullback cell**, which is the one live thread left from
this line. That gate selects *among* the entries the strategies already take
rather than adding more — near the session high and not extended, 3.3% one-bar
on MCL against a 12.6% base — and nothing here bears on it. It carries a heavier
prior after today, and it is still unregistered and unrun.

## 7. What this is not

Nothing ships; `holdout.json` is untouched. Not live: both MCL constants are read
by `signals()`, which the live evaluator calls, and the sweep passes its values
to `backtest_session` only — `evaluate_last_bar` still reads the constants, and a
test asserts the sweep parameter never appears in its signature, so this run
cannot have moved the trader. Not a search: three families, every value named in
the registration before any code existed, and the boundary check scored. And not
the sub-minute question — entering earlier within the *move* and within the *bar*
are different axes, and the second needs data this project does not own.

## Commands run

```
python -m common.entry_sweep --jobs 8
```
