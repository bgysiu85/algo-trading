# W05-0019 · Running Up universe, Tier-1 SCORED — RESULT

2026-09-23. Registered first: `docs/research/REGISTERED_running_up_universe_scored.md`
(before `common/running_up_universe_gate.py` existed, commit `712d1a7`). Continues the Tier-1
preflight (`claude/running_up_universe_preflight_RESULT_20260923.md`, Done). No engine re-run,
no tape read — a symbol-day mask applied directly to the already-published book. 11/11 unit
tests passed. Raw: `var/reports/running_up_universe_gate.txt`,
`var/reports/running_up_universe_gate_trades.csv`.

## In plain terms

The preflight found that a simple "already running fast" proxy (`ret_5m`) would have had room
to fire before the strategy's own first trade on 85% of the days it traded — the question left
open was whether ONLY trading the days that proxy would have flagged actually makes more money.
It does not. Nine thresholds were tested, from loose (keeps ~71% of MCL's trades) to strict
(keeps ~7-9%), on both trading books (MCL and MC5) — 18 tests in total. In every single one, the
per-DAY number looks better after the mask, but that is the same effect deleting days at random
would produce on a book that loses money on average — you are throwing bad days away, not
finding something. Eleven of the 18 fail outright on the random-deletion check built into the
project's rules; the other seven show the per-trade and per-day numbers pointing in OPPOSITE
directions (better per day, WORSE per trade), which the rules treat as an automatic fail, not a
partial credit.

## Verdict / what Ben must decide

**CLOSE.** None of the 18 `(book, cut)` combinations passes all five required readings — see
the table. This does not reopen the closed entry gate
(`running_up_preflight_RESULT_20260918.md`), and on this evidence it does not support opening a
further, independent registration for the universe-selector idea on `ret_5m` alone either.
Decide one of:

  - **(a) Close W05-0019** outright — this is the recommendation below.
  - **(b) Try `rvol_5m` instead of / alongside `ret_5m`** — the volume half of "climbing fast on
    a burst of volume" was deferred at the preflight stage and has never been scored.
  - **(c) Price Tier 2** (`REGISTERED_running_up_universe.md` §6) — the 2,508 scanned-but-never-
    traded symbol-days, still untested at any tier.

## Table — all 9 cuts × 2 books, in dollars, negatives bracketed

MCL baseline: 3,908 trades, 2,299 symbol-days, net at $4.26 friction **(35,063.12)**, (8.97)/trade.
MC5 baseline: 6,462 trades, 3,444 symbol-days, net at $4.26 friction **(55,364.07)**, (8.57)/trade.

| book | cut | trades kept | net $ (gated) | Δ per trade | Δ per symbol-day | verdict |
|---|---:|---:|---:|---:|---:|---|
| MCL | 0.045 | 2,766 | (23,140.57) | +0.61 | +1.86 | NOTHING (fails 1, 5) |
| MCL | 0.067 | 2,442 | (20,147.54) | +0.72 | +2.33 | NOTHING (fails 1, 5) |
| MCL | 0.089 | 2,073 | (16,422.67) | +1.05 | +2.91 | NOTHING (fails 1, 5) |
| MCL | 0.117 | 1,734 | (13,961.22) | +0.92 | +3.29 | NOTHING (fails 1, 5) |
| MCL | 0.148 | 1,398 | (11,460.53) | +0.77 | +3.68 | NOTHING (fails 1, 5) |
| MCL | 0.188 | 1,060 |  (9,702.53) | (0.18) | +3.96 | **REFUSED** (signs disagree) |
| MCL | 0.243 |   777 |  (7,025.60) | (0.07) | +4.37 | **REFUSED** (signs disagree) |
| MCL | 0.336 |   530 |  (5,301.85) | (1.03) | +4.64 | **REFUSED** (signs disagree) |
| MCL | 0.542 |   273 |  (3,318.35) | (3.18) | +4.95 | **REFUSED** (signs disagree) |
| MC5 | 0.045 | 4,737 | (41,658.44) | (0.23) | +2.14 | **REFUSED** (signs disagree) |
| MC5 | 0.067 | 4,281 | (36,535.59) | +0.03 | +2.94 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.089 | 3,796 | (30,562.77) | +0.52 | +3.87 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.117 | 3,302 | (26,394.94) | +0.57 | +4.52 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.148 | 2,771 | (20,953.98) | +1.01 | +5.37 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.188 | 2,205 | (16,965.38) | +0.87 | +5.99 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.243 | 1,675 | (13,417.87) | +0.56 | +6.54 | NOTHING (fails 1, 2, 5) |
| MC5 | 0.336 | 1,122 | (12,931.92) | (2.96) | +6.62 | **REFUSED** (signs disagree) |
| MC5 | 0.542 |   556 |  (6,036.05) | (2.29) | +7.69 | **REFUSED** (signs disagree) |

Cluster-bootstrap P(total delta > 0) reads 1.000 for all 18 — expected on a book that loses
money on average: removing trades almost always raises the total, which is exactly why reading
5 (the abstention control, not the bootstrap) is the one every "NOTHING" row fails here.

**Sample trades cost at the anticipated "moderate" cut (0.148):** MCL loses UPC ($401.36 net),
XCUR ($302.34), GLTO ($269.34) from its top-10; MC5 loses NKTR ($1,191.33), WHLR ($619.35),
ADXN ($537.36), LHAI ($448.85) — none were entered on a bought-on-sight day; the mask removed
them because their SYMBOL-DAY's peak pre-entry `ret_5m` fell short of 0.148, not because of
anything about the trade itself.

## Method

`common/running_up_universe_gate.py`, registered in
`docs/research/REGISTERED_running_up_universe_scored.md` before it existed. For each of the
3,903 traded symbol-days, kept iff `pre_bars > 0` AND pre-entry peak `ret_5m >= cut`, for the
nine cuts the Tier-1 preflight itself printed as deciles (`var/reports/running_up_universe_preflight.txt`,
2026-09-23) — no cut chosen after seeing a P&L. A kept symbol-day keeps EVERY trade in it, in
both books; a dropped one loses all of them. No engine re-run: masked directly onto
`var/reports/session_scenarios_trades.csv`, so every surviving trade is bit-identical to the
published book. Read on `gate_study`'s five criteria (`REGISTERED_range_rank.md` §3): delta per
trade ≥ $4.26 AND delta per symbol-day > 0 (sign disagreement = REFUSED); both halves positive;
drop-top-3 on level and delta; symbol-cluster bootstrap P ≥ 0.95; abstention control (2,000
draws) beaten.

## Caveats

  - **Per-symbol-day denominator is the scanned PIT universe (6,411), not a fresh engine
    recount** — `E:\Databento` is not reachable from the environment that ran this; disclosed
    in the registration §5 before the run.
  - **A mask, not a re-simulated gate.** Cascade is 0 for every cut, by construction — trades
    are only removed, never shifted or added — so this cannot say anything about a bar-level
    entry gate (`running_up_preflight_RESULT_20260918.md`, unaffected).
  - **`ret_5m` alone.** `rvol_5m` untested (option (b) above).
  - **Restricted to traded symbol-days.** The 2,508 scanned-never-traded ones are still Tier 2,
    unpriced (option (c) above).
  - Descriptive population only; `holdout.json` untouched.

## Next steps / board

  - **W05-0019 — Done** (this result). Registration, code, tests and run are all in this
    session's commit.
  - Recommendation to Ben: close, unless (b) or (c) above is wanted as a new item.
