# The first external check — built, not yet run

**2026-09-16.** `common/regime_labels.py`, commit `06cfaee`, bundle `20260916g`.

## What it is

Every number in this project so far has been checked against itself. The
regime classifier in `common/regime.py` reads hot / mixed / cold off the daily
archive, unsupervised, and has never been compared to anything outside the
project.

The census dates recovered yesterday change that. `warrior_census_dated.csv`
now carries **277 sessions Ross Cameron labelled himself**, in his own recaps,
watching the same tape, years before this project existed. There is finally a
right answer to check against.

## The three design decisions that make it a real test

**1. The headline is not three-way agreement.** `classify` cuts terciles, so
it is one-third hot by construction; his sample is 61% cold. Two classifiers
with different marginals disagree heavily even when they measure the same
thing perfectly. So the test is a **rank comparison** — on the days he called
hot, where does our composite sit, against the days he called cold? That is a
statement about ordering and is immune to where either side draws its lines.
Reported as an AUC: the chance a random hot day outranks a random cold one.
0.500 is no information.

The three-way table is printed underneath, with its caveat attached to it.

**2. The scale is shared, not copied.** `regime.composite` is now a function
and `classify` calls it. A second composite written inside `regime_labels`
would have agreed with itself forever — his hot days sitting high on a scale
built to make them sit high — and the report would have read the same whether
or not the classifier measures anything. Same reasoning for `halves`, which
calls `regime_study.halves_split`.

**3. The publish-date mapping is re-tested against the data.** It was measured
against the calendar (233 direct hits at offset 0, against 194 at a one-day
lag). The module measures it a second way: separation at offset 0 against
offset −1. If the lag separates materially better, the mapping is wrong and
the headline is void. There is a margin, because without one a 0.001 lead
prints a catastrophic verdict on a coin flip — and the report names the floor
under the whole check: regimes persist, so the lagged mapping separates
*somewhat* whatever the right day is.

## Reading the result

| AUC | what it means |
|---|---|
| well above 0.5 | our unsupervised reading tracks a human's, and the regime gate can be built on it |
| near 0.5 | it does not, and the 277 labels become a **supervised target** instead |
| halves disagree | no verdict, whatever the pooled number |

**None of these licenses trading on it.** A same-day label cannot be acted on
at 04:00. Only `regime.lagged` is a gate, and its ceiling is the label's
day-to-day autocorrelation, which `regime_study` prints separately.

And nothing here touches his P/L. The census fixed selection bias; it could
not fix source bias on a channel that sells a course. **The regime label is a
claim about the tape**, and the tape is in the archive — that is the half that
can be checked, so it is the only half used.

## A defect found on the way

Mutation testing turned up something that predates this work. `classify`'s
lower tercile cut is inclusive (`v <= lo`), and on a flat tape — every session
tied on the composite — an exclusive cut would call a market with nothing
moving in it "mixed". Ties are the normal case, not a contrived one:
`n_movers` is an integer and quiet stretches produce long runs of the same
value. The behaviour was already right; it was not tested, and is now.

## State

48 tests, 14 mutations killed including every boundary. Full suite **2,677
passed, 4 skipped**. No label moved in the extraction — there is a test
pinning `classify`'s output across it.

**The run needs Ben's machine.** The daily archive is 205 MB on `E:` and the
Linux side of the workspace cannot import `databento`.
