# Two tapes — MCL as published on XNAS.BASIC and XNAS.ITCH

`python -m common.tape_compare --jobs 8` (92s) · raw `var/reports/tape_compare_mcl.txt`, both
books `tape_compare_mcl.csv` · registration `REGISTERED_tape_compare_20260917.md` · bundle
`tape-compare-20260917a` · artifact "Two Tapes". XNAS.ITCH (Nasdaq matching engine only, no
TRF) pulled 2026-09-17, `databento_universe --dataset XNAS.ITCH --schema ohlcv-1m --window
04:00-09:30 --start 2024-07-01`, 555 sessions, 2.1 GB, $0.

Same 6,170 PIT symbol-days (universe NOT rebuilt), same engine, floor, size, costs.

## Result

| @ $4.26 | trades | per trade | net | drop-top-5 | early/t | late/t | win |
|---|---:|---:|---:|---:|---:|---:|---:|
| XNAS.BASIC (published) | 3,955 | (10.52) | (41,599) | (44,278) | (10.68) | (10.40) | 22.2% |
| **XNAS.ITCH** | 3,738 | **(8.82)** | (32,961) | (36,152) | (8.65) | (8.95) | 23.0% |

- **Before/after 2026-03-30:** BASIC (11.43) → (8.55), gap (2.87); **ITCH (8.76) → (8.98),
  gap +0.22.** The before/after difference was the tape.
- **08:00 hour, before 2026-03-30:** BASIC **(18.45)**; ITCH **(9.71)** — in line with other
  hours. The 08:00 anomaly was the tape. 07:00 also improves ((11.50) → (6.63)): late entries
  were exiting on 08:0x bars.
- Paired by symbol-day (2,788): ITCH better on 1,196, worse on 1,109; total **+8,638**,
  bootstrap 95% [+4,098, +13,032].
- Trail exits: 3,510 at (11.40) → 3,280 at (9.73). Fake lows did some of the stopping.
- Spike bars: 16,787 / 70.0M (BASIC) vs 881 / 37.8M (ITCH). Coverage: ITCH has 79% of
  BASIC's bars on the universe; 2 symbol-days without ITCH bars.

## Consequences

1. **XNAS.ITCH is the tape to quote from now on** (`--dataset XNAS.ITCH` on every study).
   The PIT universe stays as built (its 100k-share clause is absolute; exchange-only volume is
   ~79%); rebuilding the screen on ITCH is a separate registration.
2. `time_of_day` / 08:00 / before-after findings on XNAS.BASIC pre-2026-03-30 are **withdrawn
   as findings about the market** — they were the tape.
3. **The closed studies do not reopen on this.** $1.70/trade is real and crosses nothing:
   MCL (8.82), still negative both halves and drop-top-5. `stop_lever_closed_20260914.md` §4
   stands on a better measurement. Re-runs on ITCH would tighten numbers, not change answers.

Holdout unspent on either tape.
