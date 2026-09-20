# The regime classifier agrees with a human — AUC 0.730

`python -m common.regime_labels --archive E:\Databento --dataset XNAS.BASIC`
Raw: `var/reports/regime_labels.txt`, run 2026-09-16 14:16 AEST. Module
`common/regime_labels.py`, commit `06cfaee`.

**The first external validation of anything in this project.**

## The result

277 labelled recaps mapped to sessions, **none lost**. 124 census rows carry
no label and are not counted. 551 sessions in the daily archive.

| his label | n | our composite median |
|---|---:|---:|
| hot | 63 | 0.621 |
| mixed | 46 | 0.580 |
| cold | 168 | 0.475 |

**gap +0.145 · AUC 0.730** — the chance a day he called hot outranks a day he
called cold on our composite. 0.500 is no information.

Not an agreement rate, and deliberately so: `classify` cuts terciles (a third
hot by construction) against his 61% cold, so agreement measures the marginal
mismatch rather than the match. This compares ordering and has no buckets in
it.

## All three controls passed

**Halves.** early gap +0.131, AUC 0.707 (hot 31, cold 80); late gap +0.177,
AUC 0.760 (hot 32, cold 88). Same direction, similar size, both sides well
over the 15-a-side floor.

**Mapping.** Offset 0 scores 0.730 against 0.668 at a one-day lag. Had the lag
won by more than `LAG_MARGIN`, the whole headline would have been void.

**Coverage.** 0 of 277 unmapped.

One honest limit: regimes persist, so the lagged mapping separates *somewhat*
whatever the right day is. `regime_study` puts that floor at **45.8%**
day-to-day label agreement against 33% chance. Offset 0 winning by 0.062 is
the part attributable to same-day specificity — not the whole 0.730.

## The three-way table

```
his \ ours      hot   mixed    cold    total
hot              35      21       7       63
mixed            18      18      10       46
cold             47      54      67      168
total           100      93      84      277
```

Raw agreement 120/277 = 43%, depressed by the marginals.

Two derived figures matter more than the diagonal:

- **Of the 84 days we call cold, 67 are days he called cold — 80% against a
  61% base rate.** Calling it cold is the strong direction, and the veto is
  what a regime gate is for.
- **7 of his 63 hot days we called cold (11%).** The costly error for a gate
  is sitting out a live session, and that error is uncommon. The reverse — 47
  of his 168 cold days called hot — is the tercile construction showing
  through.

## What this does NOT say

`regime_study` (2026-09-11) already applied the only actionable form —
yesterday's reading gating today — to our own trades:

| yesterday's label | sessions | trades | net | per trade | win |
|---|---:|---:|---:|---:|---:|
| cold | 101 | 892 | (7,791) | (8.73) | 24.6% |
| mixed | 126 | 1,392 | (2,239) | (1.61) | 27.7% |
| hot | 151 | 2,197 | (13,364) | (6.08) | 25.9% |

**Not adoptable as measured** — a shuffle reproduces the spread 29.6% of the
time and the ordering is not monotone.

The two results are not in conflict. The classifier reads the tape the way a
human watching it does; MCL loses in every bucket, and choosing buckets cannot
rescue something negative gross in all of them. **The 0.730 validates the
instrument, not the trade.**

## What it is worth

1. **Regime becomes a usable denominator.** "This held only on cold days"
   now has an externally checked meaning behind it. Every study in this
   project can be cut by regime and the cut means something.
2. **The 16x is reframed.** The census figure is over *his* discretionary
   trading — in a cold market he cuts size ~5x, drops to A-only setups and
   stops by 10:00. The gate failing on MCL is evidence about MCL, not about
   regime.
3. **No supervised target needed.** Had the AUC come back near 0.500, the 277
   labels would have become a fitting target. At 0.730 with both halves
   agreeing, the unsupervised reading stands and the labels stay a *check*.

Item **1b** in `intraday_candidates_20260915.md` ("fit a computable regime
classifier against the human-labelled recaps") is closed — and closed without
fitting anything, which is the better outcome.

`var/state/holdout.json` remains unspent.

## Published

Artifact page: **Our Regime Reading vs His**.
