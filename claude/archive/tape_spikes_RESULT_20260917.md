# The 08:00 tape defect — census, cause, and the date it ends

`python -m common.tape_spikes --jobs 8 --ib-cache bar_cache\3d_to_2000` (92s) · raw
`var/reports/tape_spikes.txt`, marked MCL trades `tape_spikes_mcl.csv` · bundle
`tape-spikes-20260916b` · artifact "The 08:00 Tape". Follows
`tape_spikes_diagnosis_20260916.md`.

## Census (551 sessions, 69,988,872 bars, 04:00–09:30, XNAS.BASIC)

Spike bar = high > 1.25× max(o,c) or low < min(o,c)/1.25. **16,787 spike bars, 15,017
(89.5%) in the 08:00 hour**; worst minutes 08:00 (1,530), 08:05, 08:01, 08:02. By month:
15–59 per 100k bars Jul 2024 → Mar 2026, then **3–5 from Apr 2026**. 08:00 volume dump
(a name's 08:00 bar > 10× its 07:xx median): 55–68% of names every month to Mar 2026,
**15–17% from Apr 2026**.

## Cause — confirmed against the regulator's own notices

**The FINRA/Nasdaq TRF extended its hours from 08:00–20:00 to 04:00–20:00 ET on
30 March 2026** (Nasdaq Data Technical News 2026-4). Before that, off-exchange overnight
and early pre-market trades could not be reported until 08:00 and went on the tape stamped
with the report minute at hours-old prices. Minute OHLCV cannot tell a reported print from
a live one → high/low/volume contaminated from 08:00, open/close mostly intact. The
residual 15–17% dump is FINRA Notice 26-07's temporary exception (qualifying overnight
/ .W batch trades reportable by 08:15).

IB's bars on the same 267 symbol-days: 429 spikes/100k vs XNAS.BASIC 969 — both feeds
carry the prints; a market-data-plumbing fact, not one vendor's error.

## Effect on the books (net/trade at $4.26; before 30 Mar 2026 = 426 sessions, after = 115)

| book | before | after |
|---|---:|---:|
| MCL all | (11.43) · 2,706 | (8.55) · 1,249 |
| MCL 08:00 hour | **(18.45)** · 503 | (8.47) · 302 |
| MCL other hours | (9.83) · 2,203 | (8.58) · 947 |
| MC5 | (16.14) · 4,981 | (6.57) · 1,902 |
| MCL-PB v3 1m | (10.94) · 13,998 | (8.10) · 6,134 |
| MCL-PB v3 5m | (14.28) · 1,863 | (12.24) · 938 |

MCL's 08:00 hour stops being its worst hour on the clean tape. Everything is less bad;
nothing turns positive; 115 sessions is a quarter of the sample. Marked-trade floor: 81 of
MCL's 3,955 trades touched a spike bar by the 25% definition, (2,525) — a floor, since a
5%-off reported print reaches a 5% trail without being a "spike".

## Standing consequences

1. **Every XNAS.BASIC result before 2026-03-30 that reads a high, low or bar volume from
   08:00 on is contaminated**, in the direction of making trailing-stop strategies look
   worse: MCL's entry clause, every trail exit, entry_excursion / stop_timing, ORB ranges,
   pullback v1–v6. `stop_lever_closed_20260914.md` and `premarket_hypotheses_results` §1
   were measured on this.
2. **Repair needs trade-level data**: pull one contaminated day's Databento `trades` schema
   and check whether as-of / out-of-sequence prints are flagged; if so, rebuild clean bars
   for the 426 sessions under a registered rule. A bar-level clip is a guess.
3. **Until then the 115 sessions since 2026-03-30 are the honest test set**; quote which
   side of the date any figure comes from.
