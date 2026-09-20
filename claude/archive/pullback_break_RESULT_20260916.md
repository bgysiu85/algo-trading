# MCL-PB result — wait for the pullback, buy the break of the peak

`python -m common.pullback_break --jobs 8` · raw `var/reports/pullback_break_mcl.txt`,
trades `var/reports/pullback_break_trades.csv` · registration
`REGISTERED_pullback_break_20260916.md` · bundle `mcl-pb-20260916a` (commits
63fb67b, a539198, e951691 on top of a702244) · artifact "Waiting for the Pullback".

551 sessions, 6,170 PIT symbol-days, halves cut 2025-08-07. MCL book 3,955 trades =
published count.

## Verdict: NOTHING. PRE-07 HOLDS.

| @ $4.26 | trades | per trade | net | early/t | late/t |
|---|---:|---:|---:|---:|---:|
| MCL | 3,955 | (10.52) | (41,598.92) | (10.68) | (10.40) |
| MCL-PB | 903 | (11.07) | (9,999.09) | (9.83) | (12.13) |
| MCL pre-07 | 1,525 | (8.82) | (13,454.58) | (7.21) | (10.04) |
| MCL-PB pre-07 | 351 | (6.85) | (2,405.93) | (6.28) | (7.45) |
| MCL 07-09:30 | 2,430 | (11.58) | (28,144.34) | (12.94) | (10.62) |
| MCL-PB 07-09:30 | 552 | (13.76) | (7,593.16) | (12.52) | (14.67) |

Fails IMPROVES on the late half per trade. Smaller total is abstention (a quarter of the
trades). Pre-07 beats MCL per trade in both halves, by $0.93 / $2.59 — less than one round
trip of friction, and still negative.

Setups 4,692: triggered 903 (19.2%), band refused 73, **cancelled on depth 3,400 (72.5%)**,
MACD 148, window 168. Entry premium over signal close: median +2.86%, p90 +11.72%.

## Descriptive, post-run, not registered

MCL on symbol-days where MCL-PB also traded: (4.46)/trade over 1,583; on all other days
(14.56)/trade over 2,372. MCL-PB on its own days: (11.07). So the pullback-and-break
shape marks MCL's better days, and buying the break gives it back through the premium
against a 5% trail — the "confirmation is the cost" pattern again. **Hindsight**: a day
that later breaks its peak is partly good by definition; not usable as a gate on MCL.

"MCL-PB before 07:00 only" would be a post-hoc rule, still negative; needs its own
registration if ever pursued. Holdout unspent.
