# RESULT — H-C2 profit floor: MCL REFUSED (a wash), MC5 NOTHING (reliably worse)

Repo copy: `docs/research/profit_floor_RESULT.md`, commit `4bd3a5d` (on top of `114779f`).
Report: `var/reports/profit_floor.txt`.

**Setup.** XNAS.ITCH, v1 p50 point-in-time universe, 551 sessions, 6,564 symbol-days.
Both baselines reproduced exactly: MCL 3,960 / (8.81), MC5 6,630 / (8.49).

**Rule.** Once a bar after entry reaches +15 ticks, exit at max(5% trail, entry + 10 ticks).

## Verdicts

- **MCL: REFUSED.**
  - Δ per trade +0.28, per symbol-day (0.01); at $8.92, +0.28 / (0.11).
  - Cluster bootstrap P = 0.470.
  - Floor exits 30.3%. Whole book (93.37).
- **MC5: NOTHING.**
  - Δ per trade (0.36), per symbol-day (0.60).
  - Fails readings 1–4. Bootstrap P = 0.003, interval wholly below zero.
  - Floor exits 17.8%. Whole book (3,923.22).

## Mechanism

- **Floor exits net > $0 at $4.26:** MCL 71.6%, MC5 56.1%. At $8.92 it is 0% by
  construction ($9 gross less commission).
- **Gapped below the floor:** MCL 509, MC5 675. Below the entry price: 205 and 353.
- **Runners (reached +10%) cut:** MCL 148, (8,059.77); MC5 154, (7,411.22).
- **Win rate:** MCL 23→36%, MC5 23→28%.
- **Average winner:** MCL 37.30→17.75, MC5 50.03→36.09.

## Decomposition

Descriptive, computed after the run; paired floor exits:

| | MCL | MC5 |
|---|---:|---:|
| losers rescued | +12,343 | +8,332 |
| winners > $20 cut | (9,988) | (9,514) |
| small winners cut | (792) | (639) |
| re-entries and knock-on trades | (1,656) | (2,103) |

## Predictions

- **NOTHING for both, Δ per trade (1.50) to +1.00:** held.
- **MC5 gaps ≥ a third of floor exits:** held, 56%.
- **Floor exits positive at $4.26 (40–65%):** MC5 held; MCL came in above, at 72%.

## What it closes

(15, 10) is closed for both strategies. Any other tick pair is a new hypothesis, with this
result as the prior against it.

Artifact page published.
