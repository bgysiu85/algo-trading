# RESULT — MC5 04:00–20:00 reads NOTHING: every hour of the day loses

Repo copy: `docs/research/mc5_full_day_RESULT.md`, commit `88343c8`. Reports:
`var/reports/mc5_full_day.txt`, `var/reports/screen_day.txt`. Universe:
`var/state/screen_pairs_pit_itch_day.json`. Registered `REGISTERED_mc5_full_day.md`
(`5a52b9c`, amendments A–D). XNAS.ITCH, 546 sessions. Holdout untouched.

## Verdict — NOTHING, all five readings fail

- Per trade at $4.26: **(8.27)** over 38,503 added trades; net (318,377.46).
- Halves: (8.52) / (8.04).
- Drop-top-5 symbols: (332,318.82).
- Cluster bootstrap: **P = 0.000**, interval [(343,446.68), (292,528.54)] over 3,152 symbols.
- Session median: (616.80).

Arm A reproduced the published book on the run's own population exactly: 6,425 trades,
(8.62)/trade (amendment D, via `pairs_restrict` + `pit_strategy`).

## By block

| block | trades | gross | @ $4.26 | @ $8.92 | win | bars |
|---|---:|---:|---:|---:|---:|---:|
| PRE | 8,572 | (5.05) | (8.31) | (12.97) | 23.3% | 4.2 |
| RTH | 30,155 | (4.42) | (7.68) | (12.34) | 25.7% | 10.5 |
| POST | 8,348 | (7.13) | (10.39) | (15.05) | 21.0% | 5.9 |

**Every hour of entry loses at $4.26 and every block loses gross.** Best hour 10:00 at
(5.55); worst 16:00 (11.39) and 15:00 (11.09). RTH loses $4.42 a trade before any cost,
so this is not friction.

## The books

| arm | window | universe | trades | per trade |
|---|---|---|---:|---:|
| A published | 04:00–09:30 | v2 | 6,425 | (8.62) |
| A′ control | 04:00–09:30 | v2 | 8,347 | (8.34) |
| B frozen | 04:00–20:00 | v2 | 23,435 | (8.49) |
| C running | 04:00–20:00 | day | 47,075 | (8.28) |

Warm-up (A′ vs A) +0.28/trade. Carried trades: 773 exits moved, +343.20 total. 226
pre-market entries only C has — the engine's last-bar rule, (1,954.92).

## Universe

`screen_day`: 23,235 symbol-days over 549 sessions — 27.6% PRE, 63.2% RTH, 9.2% POST;
median 40 names a session. PRE reproduces `screen_sim` tick for tick (330 ticks, 0
disagreements).

## What it does not close

- RTH/POST volume threshold **carried from 09:30, not measured** (amendment B): too easy,
  so the after-open universe is too big.
- No concurrency cap modelled; 47,075 trades is far past a 3-slot book.
- Live trader unchanged: still 09:30, no RTH/POST screen.
- Four dates (09-10, 09-11, 09-14, 09-15) have no RTH pull and cannot be run.

Artifact page published.
