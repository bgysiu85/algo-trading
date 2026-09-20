# H0 on the refreshed point-in-time universe — 2026-09-12

`python -m common.pit_h0` · raw: `var/reports/pit_h0.txt`

## Why it was re-run

The daily Databento archive was stale: `2026-09.dbn.zst` had been pulled on
09-05 and then frozen forever by skip-if-present, so the point-in-time universe
was missing four sessions. Fixed with `chunk_ends_before` + symbology-sidecar
deletion on re-fetch (`common/databento_universe.py --refresh-partial`).

Universe: **4,997 symbol-days / 546 sessions → 5,021 / 550**.
Knowable by 04:30: **798 symbol-days** (722 traded).

## The control barely moved

At $4.26 friction:

| | 4,997-day | 5,021-day | moved |
|---|---:|---:|---:|
| Knowable at 04:30 — trades | 713 | 722 | +9 |
| Knowable — net | (10,440) | (10,612) | (172) |
| Knowable — per trade | (14.64) | (14.70) | (0.06) |
| Knowable — win rate | 24.7% | 24.8% | +0.1pp |
| As screened — trades | 4,568 | 4,590 | +22 |
| As screened — net | (72,086) | (72,306) | (220) |
| As screened — per trade | (15.78) | (15.75) | +0.03 |
| As screened — win rate | 22.7% | 22.7% | 0.0pp |

Sign STABLE across $1.00–$8.92 on both arms. Drop-top-5 deepens the loss on
every row.

## What it rules out

The simulation and the live record disagree about the **shape** of the deficit,
not only its size. One available explanation was that the backtest universe was
simply short of days. Four more sessions and 24 more symbol-days moved the
per-trade figure by six cents. **Sample size at the backtest end is not the
explanation**, and the disagreement stands — which points the search at the
screen (see `screen_miss_result_20260912.md`) and at execution, not at coverage.

Every other conclusion in `pit_h0_result_20260911.md` survives unchanged: H0
lands with the stage-2 REJECTS (−34% of the way from rejects to survivors), so
the +$4.72 was the leak and the universe — not the rule — was the edge.

## Downstream

`common/pit_strategy.py` constants updated in commit `e494872` (bundle
`20260912g`):

    H0_PIT_NET = -72_306.0
    H0_PIT_TRADES = 4_590
    H0_PIT_OFFERED = 5_021
    H0_KNOWABLE_NET = -10_612.0
    H0_KNOWABLE_TRADES = 722
    H0_KNOWABLE_OFFERED = 798
    H0_REFERENCE_SOURCE = "var/reports/pit_h0.txt, 2026-09-12"

**MCL and MC5 must be re-run** (`pit_strategy --strategy mcl` / `mc5`) before any
verdict on them is quoted again. The "Point-in-Time Audit" artifact carries a
staleness banner until they do — refreshing H0's numbers there while leaving
MCL's at the old universe would put two non-comparable figures side by side,
which is the exact defect class this project keeps finding.
