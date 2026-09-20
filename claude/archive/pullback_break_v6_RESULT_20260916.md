# MCL-PB v6 result — v3 on five-minute bars; the pullback line closed on both timeframes

`python -m common.pullback_break --jobs 8` (147s) · raw `var/reports/pullback_break_mcl.txt`,
trades `pullback_break_trades.csv` (MC5's book included) · registration
`REGISTERED_pullback_break_v6_20260916.md` · bundle `mcl-pb-20260916h` · artifact
"Five-Minute Bars". 551 sessions, 6,170 symbol-days. MCL 3,955 and **MC5 6,883 at (13.50)
both match their published PIT figures.**

## Verdict: NOTHING vs MCL, NOTHING vs MC5, NOTHING vs v3. Pre-07 does not hold.

| @ $4.26 | trades | per trade | net | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|
| MCL (1m) | 3,955 | (10.52) | (41,599) | (10.68) | (10.40) | 22.2% |
| MC5 (5m control) | 6,883 | (13.50) | (92,904) | (14.89) | (12.44) | 21.2% |
| PB3-5m-g3 (primary) | 2,801 | (13.59) | (38,080) | (12.41) | (14.42) | 22.0% |
| PB3-5m-g0 | 2,746 | (14.19) | (38,976) | (13.40) | (14.75) | 21.0% |
| PB3-g3 (1m, v3) | 20,132 | (10.08) | (202,858) | (10.53) | (9.76) | 22.8% |

What the timeframe changed: levels/symbol-day 19 → 6; fill above the level (median) 1.60% →
**3.17%**; trail exits 48% → **78%** (2,171 at (19.15)); green-hold exits 9,336 at +4.30 →
418 at +11.51; median hold 3 min → 10 min. The 5-minute break bar closes far above the
level, so the entry starts 3% into the move under a 5% trail.

Cosmetic: the "AGAINST MC5" line's reason text says "MCL" (shared verdict function); the
comparison is against MC5.

## The line, closed

v1 (11.07) · v2 (16.11) · v3 (10.06) · v4 (9.90) · v5 (10.96) on 1m — MCL's (10)–(11);
v6 (13.59) on 5m — MC5's (13.50). Six registrations, six NOTHINGs, two timeframes, each
landing on that timeframe's own control. The figure is a property of the tape and the fill,
not of the rule. Recommendation stands: stop tuning; diagnose the 08:00 interleaved-price
defect; scope the data the tape lacks (`data_scoping_20260914.md`). Holdout unspent.
