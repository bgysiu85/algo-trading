# MCL-PB v3 result — break must close on volume, green-hold exit

`python -m common.pullback_break --jobs 8` (202s) · raw `var/reports/pullback_break_mcl.txt`,
trades `pullback_break_trades.csv` (top/level/armed per trade) · registration
`REGISTERED_pullback_break_v3_20260916.md` · bundle `mcl-pb-20260916d` (e fixes the
2025-06-09 duplicate-timestamp error) · artifact "Closing on Volume". Supersedes v2.

551 sessions, 6,159 symbol-days (11 on 2025-06-09 dropped — runner tripped on repeated
timestamps; fixed in `e`, MCL will read 3,955 next run).

## Verdict: NOTHING. PRE-07 DOES NOT HOLD.

| @ $4.26 | trades | per trade | net | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|
| MCL | 3,945 | (10.49) | (41,371) | (10.61) | (10.40) | 22.2% |
| PB3-g3 (primary) | 20,077 | (10.06) | (201,961) | (10.49) | (9.76) | 22.8% |
| PB3-g5 | 19,479 | (10.55) | (205,514) | (10.87) | (10.33) | 22.1% |
| PB3-g0 (no time exit) | 16,472 | (11.76) | (193,638) | (12.04) | (11.54) | 21.1% |

**First version to beat MCL per trade in both halves.** Fails on total (5× the trades)
and drop-top-5. Pre-07: (7.62) vs (8.76) overall but early half (7.43) vs (7.06).

## The finding: the exit payoff

PB3-g3 exits: green_hold 9,308 at **+4.31 mean, median (2.63)**; trailing_stop 9,709 at
**(23.42)**; window 1,060 at (13.87). Winners capped at 3 bars, losers ride to −5%: ~1:5
payoff at 22.8% wins. No entry filter fixes that ratio. Green hold adds $1.70/trade and
3,600 trades (positions freed sooner), net (8,323) worse than g0.

Breaks 163,180: entered 20,077; refused — closed below level 48,232, volume ≤ prior-20
avg 49,527, MACD closed 9,913; crossed while busy/before floor 58,708.

08:00 hour (14.27) vs MCL (14.76) — closing on volume avoids most interleaved-price bars
(134 trades >25% in one bar, (10,573), vs 290 / (31,178) in v2). Defect still undiagnosed.

Ben's 2026-09-11 examples in this run (with floor): TNON 06:48 7.41, 07:31, 07:42 7.95,
08:15 8.10 (inside his box — the case for a consolidation filter volume did not catch),
FTFT 07:16 2.31 taken. Holdout unspent.
