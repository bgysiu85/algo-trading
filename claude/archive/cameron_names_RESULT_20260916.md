# Item 1c — our screen already ranks his names first

`python -m common.cameron_names --archive E:\Databento`
Raw: `var/reports/cameron_names.txt`, run 2026-09-16 15:39 AEST.
Registration `docs/research/REGISTERED_cameron_names.md` (`f1fa64c`), amended
twice (`01dfd67` pre-run, `2be04e9` post-run).

**587 de-duplicated (session, symbol) pairs across 241 sessions. 0 unmapped.
42 duplicate mentions counted once.**

## The registered primary

| | |
|---|---:|
| his names, mean rank-AUC | **0.688** (n=451) |
| random draw from the same session's universe | **0.500** (90% of draws 0.476–0.523) |
| exact expectation, by symmetry | 0.500 |
| draws reaching his figure | **0 of 2,000** |
| early half | 0.676 (n=259) — passes |
| late half | 0.704 (n=192) — passes |

**PASSES the registered 0.60 bar, both halves the same side.**

The rank-AUC is the chance one of his names outranks a randomly chosen *other*
name on our own list that day, ties at a half. It has no look-ahead: rank was
computed from the tape as it stood at each tick.

The control agreed with its exact expectation to three decimals — which is the
check that says it drew from each session's own universe rather than the pool.
A wrong-pool draw would still have returned a plausible number.

## Coverage and rank

**451 of 587 (76.8%)** were in our universe on the day.

| rank | best reached | when first seen |
|---:|---:|---:|
| 1 | **265** | 131 |
| 2 | 94 | 109 |
| 3 | 41 | 77 |
| 4 | 27 | 53 |
| 5 | 8 | 33 |
| 6–11 | 16 | 48 |

**When he traded a name our screen carried, our own ordering had already put it
first 59% of the time.** At first sight rather than at its best, 131 were still
rank 1.

## Why we declined the other 136

| cause | n | share |
|---|---:|---:|
| NOT ON THIS TAPE | 52 | 38.2% |
| CHANGE | 22 | 16.2% |
| CHANGE+VOLUME | 22 | 16.2% |
| PRICE | 16 | 11.8% |
| CHANGE+VOLUME+PRICE | 13 | 9.6% |
| CHANGE+PRICE | 4 | 2.9% |
| NEVER SIMULTANEOUS | 3 | 2.2% |
| NO PRIOR CLOSE | 2 | 1.5% |
| VOLUME | 2 | 1.5% |

**38% never print on XNAS.BASIC at all** — a data-coverage limit, not a
threshold. No screen setting reaches those. The change clause, alone or
combined, accounts for 45%.

## What this closes

Not a null, so 1c is not dismissed — but the pass has a narrow meaning, and it
is the useful one:

> **Our list is not the problem.** Our screen finds the names he trades and
> ranks them at the top. If there is a gap between his results and ours, it is
> not in which names reach the watchlist.

That redirects the remaining effort to entry and exit, where `entry_place` and
`won_vs_lost_20260916` already sit.

This leg is also **not** contaminated the way the P/L is: his hindsight is
about outcomes, and the rank-AUC asks whether he and our screen select on the
same premarket signal. They do.

## §6 — the money table, which settles nothing

At $4.26:

| arm | trades | symbols | per trade | per symbol-day | win% |
|---|---:|---:|---:|---:|---:|
| HIS | 433 | 306 | (7.16) | (10.12) | 29.8 |
| OURS-5 | 1,008 | 643 | (14.22) | (22.29) | 24.8 |
| OURS-ALL | 2,372 | 1,170 | (13.85) | (28.09) | 25.2 |

HIS is less bad at every friction on both denominators. **Registered as
uninformative before the numbers existed** — it is the expected outcome of a
pick made after the close.

**And the one uncontaminated comparison here REFUSES.** OURS-5 against
OURS-ALL is our own point-in-time selection against itself, and the two
denominators disagree in direction: tightening to five names is *worse* per
trade (14.22 vs 13.85) and *better* per symbol-day (22.29 vs 28.09). A
denominator disagreement is a refusal, not a result.

A further reason not to read the HIS row: at $1.00 its halves flip sign —
(7.83) early against +1.05 late. Every arm loses at every friction regardless.

## What the registration cost, and bought

The criterion registered that morning **could not have passed**: a random name
from our own universe is already inside the top five 93.7% of the time,
because `best_rank` is the best rank a name ever reached and the median session
carries eleven names. Beating that by fifteen points needs 108.7%. Amended
before the run, in its own commit.

The same tie problem was then sitting one section further down: `best_rank <=
5` selects 90.5% of every symbol-day, so the first run's "our top 5" arm was
our whole list. Corrected in a second, post-run amendment touching §6 only.

**Finding a defect shape once did not sweep the file for it.** Worth adding to
the list beside *a sentinel that is also a legal value*.

## Published

Artifact page: **His Names, Our Ranking**.

`var/state/holdout.json` untouched and unspent.
