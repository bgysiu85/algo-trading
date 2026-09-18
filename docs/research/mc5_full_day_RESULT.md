# RESULT — MC5 04:00-20:00 reads NOTHING: every hour of the day loses

Run 2026-09-18: `python -m common.screen_day --dataset XNAS.ITCH --capture-ladder
var/reports/itch_capture.json` then `python -m common.mc5_full_day --jobs 8 --expect
6425:-8.62`. XNAS.ITCH, 546 sessions. Reports `var/reports/screen_day.txt`,
`var/reports/mc5_full_day.txt`; universe `var/state/screen_pairs_pit_itch_day.json`;
trades `var/reports/mc5_full_day_trades.csv`. Registered
`REGISTERED_mc5_full_day.md` (`5a52b9c`, amendments A-D). Holdout untouched.

## The verdict (§4, on arm C's entries at or after 09:30)

**NOTHING — all five readings fail.**

| reading | value |
|---|---:|
| 1. per trade at $4.26 | **(8.27)** over 38,503 added trades, net (318,377.46) |
| 2. halves | (8.52) / (8.04) |
| 3. drop-top-5 symbols | (332,318.82) |
| 4. cluster bootstrap | **P = 0.000**, [(343,446.68), (292,528.54)] over 3,152 symbols |
| 5. session median | (616.80) |

Arm A reproduced the published book on the run's own population exactly — **6,425 trades,
(8.62)/trade** (amendment D; `pit_strategy` on `screen_pairs_pit_itch_v2_fullday.json`
gives the same). So the comparison is like-for-like.

## By block, and by hour

| block | trades | gross | @ $4.26 | @ $8.92 | win | avg bars |
|---|---:|---:|---:|---:|---:|---:|
| PRE 04:00-09:30 | 8,572 | (5.05) | (8.31) | (12.97) | 23.3% | 4.2 |
| RTH 09:30-16:00 | 30,155 | (4.42) | (7.68) | (12.34) | 25.7% | 10.5 |
| POST 16:00-20:00 | 8,348 | (7.13) | (10.39) | (15.05) | 21.0% | 5.9 |

**Every hour of entry loses at $4.26, and every block loses GROSS.** The best hour is
10:00 at (5.55)/trade (5,162 trades); the worst are 16:00 (11.39) and 15:00 (11.09).
Regular hours are the least bad and still lose **$4.42 a trade before any cost at all**,
so this is not a friction result.

## The books

| arm | window | universe | trades | per trade | net @ $4.26 |
|---|---|---|---:|---:|---:|
| A published frames | 04:00-09:30 | v2 | 6,425 | (8.62) | (55,385.07) |
| A' the control | 04:00-09:30 | v2 | 8,347 | (8.34) | (69,613.86) |
| B frozen | 04:00-20:00 | v2 | 23,435 | (8.49) | (199,052.58) |
| C running screen | 04:00-20:00 | day | 47,075 | (8.28) | (389,582.40) |

Warm-up (A' against A) is worth **+0.28/trade** — the price of full-day frames, not a
finding. Carried trades: 773 of 8,346 pre-market entries exited at a different time once
09:30 stopped flattening, moving P/L by **+343.20** in total. 226 pre-market entries exist
only in C, worth (1,954.92): the engine's last-bar rule, not the extension.

## The universe

`screen_day` built **23,235 symbol-days over 549 sessions** (23,135 in the study's 546):
**27.6% first seen PRE, 63.2% RTH, 9.2% POST**, median 40 names a session against the
pre-market list's ~12. The PRE block reproduces `screen_sim` tick for tick (330 ticks, 0
disagreements; the run exits if it does not).

## What this does and does not close

- **Closes:** MC5 is not a pre-market-only problem. Giving it the whole day, and three
  times the names, multiplies the loss roughly in proportion to the trade count. There is
  no hour, and no block, that clears the cost of trading. Trading later is not the fix.
- **Does not close:** the RTH/POST volume threshold is **carried from 09:30, not
  measured** (amendment B) — too easy, so the after-open universe is too big; a measured
  ladder would shrink RTH toward the pre-market count. No concurrency cap is modelled and
  47,075 trades is far past a 3-slot book. The live trader is unchanged: it still stops at
  09:30 and has no RTH/POST screen.
- **Four dates** (2026-09-10, 09-11, 09-14, 09-15) have no regular-hours pull and cannot
  be run at all.
