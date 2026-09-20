# MCL-PB v2 result — swing high, two red bars, buy the break

`python -m common.pullback_break --jobs 8` (216s) · raw `var/reports/pullback_break_mcl.txt`,
trades `pullback_break_trades.csv` (level / top_et / armed_et per trade) · registration
`REGISTERED_pullback_break_v2_20260916.md` · bundle `mcl-pb-20260916c` · artifact
"Buying the Break". Supersedes v1 (`pullback_break_RESULT_20260916.md`, NOTHING).

551 sessions, 6,159 symbol-days (11 raised in the runner and were dropped from every
book → MCL 3,945 here vs 3,955 published; like-for-like inside the run).

## Verdict: NOTHING. PRE-07 HOLDS.

| @ $4.26 | trades | per trade | net | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|
| MCL | 3,945 | (10.49) | (41,371) | (10.61) | (10.40) | 22.2% |
| PB2 (no target) | 15,880 | (16.11) | (255,798) | (15.99) | (16.20) | 22.2% |
| PB2-10c | 18,508 | (14.21) | (263,077) | (14.44) | (14.06) | 51.2% |
| PB2-25c | 16,917 | (14.92) | (252,334) | (15.03) | (14.84) | 32.8% |

Pre-07: PB2 (5.50) on 5,228 vs MCL (8.76) — beats MCL per trade in both halves, still
negative. 07:00+: PB2 (21.31) vs MCL (11.57).

Levels 138,295 (median 19 per symbol-day): bought 11.5%, band 4.4%, MACD closed 19.2%,
crossed while already in a trade 32.2%, expired 19.7%, live at 09:30 13.1%.

10c cell: 9,431 targets at +10.33 vs 7,850 stop-outs at (43.83) — half the trades win
and it still loses; the target is 1:2.5 against a 5% stop.

## The 08:00 hour, and a tape defect

08:00–08:59 entries: 5,265 trades at (33.74) = 69% of the loss. Inside it, **290 PB2
trades moved >25% in one bar, 235 of them in the 08:00 hour** — e.g. ALTS 2025-08-11
bought 19.76 @ 08:35, stopped 9.49 @ 08:36, (1,032). Two price scales interleaved on
259 symbol-days (suspect: two instrument_ids → one symbol, or a split seam). MCL has 21
such trades. Dropping those symbol-days: PB2 (13.68) on 14,651; MCL (11.57) on 3,768 —
verdict unchanged. 08:00 remains (24.68) after the drop. **Open data question**, not yet
diagnosed; an "avoid 08:00" filter would be post-hoc.

Holdout unspent.
