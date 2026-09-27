# W05-0005 — dist_from_high as an entry gate, on its own registration — RESULT

**Registered:** `docs/research/REGISTERED_dist_from_high.md` (2026-09-23) · **Built + run:** `common/dist_from_high_gate.py`, `tests/common/test_dist_from_high_gate.py` · **Raw report:** `claude/raw/w05_0005_dist_from_high_gate_report_20260923.txt` · **monday Result doc:** https://ben-siu.monday.com/docs/5031517200

## In plain terms

- `dist_from_high` beat its own random-removal control once before, in the chase-gate study (`chase_gate_RESULT_20260918.md`) — but that number was deliberately fenced off from ever being scored, because it was the one cell in a five-value sweep that happened to look best.
- This registration reran the exact same threshold-solving procedure, this time scoring it properly against the project's standard five-reading bar, across 10 variants (5 thresholds x MCL and MC5), on the full 550-session, 6,411-symbol-day universe.
- **None of the 10 cells pass.** Every one still fails reading 1 -- the gate never removes at least $4.26 of loss per trade, the one round-trip of friction. A few come reasonably close and point the right way (best: MC5 at the 35th-percentile threshold, +$1.21/trade, beats its own random-removal control, both halves positive) -- but "close and right-direction" is not the bar this project ships on.
- One cell (MCL, 10th-percentile threshold) is inconclusive by construction: its per-trade and per-symbol-day deltas disagree in sign, so it's read as REFUSED rather than scored.
- The gate is mostly refusing a different set of trades than the existing chase gate (only 15-29% overlap at the matched budget) -- so this was a real second look, not a repeat of the first one.

## What Ben must decide (REGISTERED §6)

- **(a) Study-only** -- a direction confirmed a second time, not promoted -- the consistent positive sign across all 10 cells (vs. both books' own -$8.57/-$8.97 baseline) is filed as informative, nothing built on it.
- **(b) Close** -- no cell clears the five-reading bar; the idea is done here.
- **(c) Second registration** -- only applies if a cell had passed cleanly and independently of the chase gate -- none did, so (c) is not on the table from this result.

**Flag before treating this as final:** REGISTERED_dist_from_high.md §3 named 3 of the 5 budgets exactly (the solved ret_5m-ceiling matches) but left the other 2 ("direct" thresholds, spaced over dist_from_high's own range) unpinned. This build picked the 10th and 35th percentile -- a judgment call, documented in the module docstring, never solved against P&L. A different pair of percentiles could read somewhat differently, though the overall picture (no cell clears $4.26/trade) is unlikely to flip.

## The books, in dollars ($4.26 friction, negatives bracketed)

| Book | Trades | Net | Per trade | vs. baseline per trade |
|---|---:|---:|---:|---:|
| MCL (baseline) | 3,908 | ($35,063.12) | ($8.97) | -- |
| MCL-c033 (ret_5m-matched, ceil 0.033) | 1,296 | ($10,839.98) | ($8.36) | +0.61 |
| MCL-c083 (ret_5m-matched, ceil 0.083 -- reproduces the fenced -0.1594) | 2,790 | ($22,478.31) | ($8.06) | +0.92 |
| MCL-c100 (ret_5m-matched, ceil 0.100) | 3,047 | ($25,584.59) | ($8.40) | +0.58 |
| MCL-q10 (direct, p10) -- REFUSED, denominators disagree | 3,538 | ($31,918.46) | ($9.02) | (0.05) |
| MCL-q35 (direct, p35) | 2,610 | ($21,266.93) | ($8.15) | +0.82 |
| MC5 (baseline) | 6,462 | ($55,364.07) | ($8.57) | -- |
| MC5-c033 | 4,027 | ($30,895.98) | ($7.67) | +0.90 |
| MC5-c083 (reproduces the fenced -0.1993) | 5,259 | ($41,970.97) | ($7.98) | +0.59 |
| MC5-c100 | 5,469 | ($46,023.03) | ($8.42) | +0.15 |
| MC5-q10 | 5,940 | ($49,238.93) | ($8.29) | +0.28 |
| MC5-q35 -- closest to passing (fails only reading 1) | 4,567 | ($33,608.91) | ($7.36) | +1.21 |

Every cell is still net-negative on its own -- the gate only ever makes a losing book less losing, never a winner.

### Sample trades refused by the best-reading cell (MC5-q35)

2,262 of MC5's 6,462 baseline entries refused: 1,789 losses avoided (avoiding $45,628.13 of loss) against 473 winners lost ($22,588.32 given up) -- net effect +$1.21/trade vs. the unfiltered book.

## Method (unchanged from REGISTERED_dist_from_high.md)

- Population: `screen_pairs_pit_itch_v2.json`, same point-in-time XNAS.ITCH universe as the chase gate -- 6,411 symbol-days, MCL 3,908 / MC5 6,462 baseline entries, confirmed to match the features file exactly, 0 errors.
- Three thresholds solved by reusing `chase_gate.solve_distance` unchanged, matched to how many trades `ret_5m <= 0.033 / 0.083 / 0.100` refuses -- blind to any P&L. The 0.083 match reproduces the 2026-09-18 fenced thresholds (-0.1594 MCL, -0.1993 MC5) exactly, confirming the solve is the same procedure.
- Two thresholds read directly off `dist_from_high`'s own 10th/35th percentile at signal time (this build's choice -- see the flag above).
- All five standard readings scored for all ten cells (delta >= $4.26/trade AND per-symbol-day > 0; both halves; drop-top-3; symbol-cluster bootstrap P>=0.95; beats 2,000-draw random-removal abstention control at p95).
- Overlap with the chase gate, at the matched 0.083 budget: MCL 28.5%, MC5 15.6% -- mostly a different mechanism, not a re-refusal of the same trades.

## Caveats

- Not out of sample -- `holdout.json` untouched.
- Not a cap model -- each symbol-day scored alone.
- Not a search -- the five budgets were fixed before the run (three solved against a constraint, two read off the distribution), and every one of the ten is reported, not just the best-looking.
- `dist_from_high` itself separates weakly by the earlier pre-flight (AUC 0.494 MCL / 0.443 MC5) -- this result is about the money, not about separating one-bar deaths.

## Source files

- `docs/research/REGISTERED_dist_from_high.md` -- registration
- `common/dist_from_high_gate.py` -- the study
- `tests/common/test_dist_from_high_gate.py` -- 18 tests, all passing
- `var/reports/dist_from_high_gate.txt` / `var/reports/dist_from_high_gate_trades.csv` -- local outputs (gitignored)
- `claude/raw/w05_0005_dist_from_high_gate_report_20260923.txt` -- committed raw copy
- `D:\Trading\Claude outputs\w05_0005_dist_from_high_gate_RESULT_20260923.txt` -- delivered copy
