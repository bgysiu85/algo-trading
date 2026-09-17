# RESULT — H-C2 profit floor: MCL REFUSED (a wash), MC5 NOTHING (reliably worse)

Run 2026-09-17 on Ben's machine: `python -m common.profit_floor_study --jobs 8`, code
`114779f`, XNAS.ITCH, `screen_pairs_pit_itch_p50.json` (sha256 1db006ca23d20065), 551
sessions, 6,564 symbol-days. Report: `var/reports/profit_floor.txt`, trades
`var/reports/profit_floor_trades.csv`. Registered: `REGISTERED_profit_floor.md` (`2b1620a`,
amendment A). Holdout untouched. Both baselines reproduced exactly: MCL 3,960 / (8.81),
MC5 6,630 / (8.49).

## Verdicts (§3, $4.26)

| | Δ/trade | Δ/symbol-day | Δ/trade @ $8.92 | Δ/symday @ $8.92 | halves (trade) | drop-3 symbols Δ | bootstrap P | floor exits | verdict |
|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| MCL | +0.28 | (0.01) | +0.28 | (0.11) | +0.05 / +0.46 | (482.31) | 0.470 | 30.3% | **REFUSED** (denominators disagree) |
| MC5 | (0.36) | (0.60) | (0.36) | (0.72) | (0.82) / +0.03 | (4,261.58) | 0.003 | 17.8% | **NOTHING** (fails 1–4) |

Whole book: MCL (93.37), MC5 (3,923.22). The MC5 bootstrap interval lies wholly below
zero, [(7,375.57), (995.68)]: the floor makes MC5 worse, not merely no better.

## The mechanism (the question Ben asked)

| | MCL | MC5 |
|---|---:|---:|
| trades that armed | 44.3% | 35.8% |
| floor exits | 1,243 (30.3%) | 1,212 (17.8%) |
| floor exits net > $0 at $1.00 / $4.26 / $8.92 | 78.0 / 71.6 / 0.0% | 64.0 / 56.1 / 0.0% |
| filled at floor / gapped below / below entry | 734 / 509 / 205 | 537 / 675 / 353 |
| runners (≥ +10%) cut, P/L forgone | 148 of 524, (8,059.77) | 154 of 1,389, (7,411.22) |
| win rate base → floor | 23.3 → 36.0% | 23.1 → 28.2% |
| avg winner base → floor | 37.30 → 17.75 | 50.03 → 36.09 |

At $8.92 no floor exit can be positive by construction ($9 gross less commission).

**Decomposition, computed after the run from the trades CSV (not registered; descriptive).**
Floor exits paired with the same trade in the baseline:

| | MCL | MC5 |
|---|---:|---:|
| baseline losers rescued | 829, +12,343.22 | 839, +8,331.75 |
| baseline winners > $20 cut | 147, (9,988.00) | 125, (9,513.65) |
| baseline small winners cut | 205, (792.21) | 192, (638.72) |
| paired floor exits, net | +1,563.01 | (1,820.62) |
| re-entries and knock-on trades | (1,656.38) | (2,102.60) |
| whole book | (93.37) | (3,923.22) |

## Predictions

NOTHING for both and Δ/trade in (1.50)..+1.00: **held** (MCL refused rather than nothing).
MC5 floor exits 15–30%: held (17.8%). MC5 ≥ a third gapped below the floor: held (56%).
MCL floor exits 20–35%: held (30.3%). Floor exits positive at $4.26 40–65%: MC5 held
(56.1%), MCL above (71.6%).

## What it closes

A profit floor at +10 ticks does what it says on losers and gives the same money back on
winners and in re-entries. On 5-minute bars more than half its exits gap through the level.
Closed for both strategies at (15, 10); any other pair is a new hypothesis, and this
result is the prior against it.
