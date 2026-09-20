# Session start sweep — starting later makes MCL and MC5 worse per trade

**Research chat, 2026-09-17. Read-only: a filter on the existing point-in-time
trade lists; no program logic touched.** Raw report:
`D:\Trading\Claude outputs\session_start_sweep_20260917.txt`.

Ben asked for the backtest with the session start moved from 04:00 to 06:30.

> **Starting later makes every per-trade figure worse, monotonically, on both
> books.** The total shrinks only because there are fewer trades. And the block
> a 06:30 start removes — 04:00–06:29 — is the **least bad** part of either
> book: MCL's early trades lose **(5.43)** against **(6.56)** for what remains;
> MC5's lose **(3.19)** against **(11.57)**. **The cut removes the better
> trades.**

---

## 1. Source and conventions

`var/reports/first_entry_skip_trades.csv`, `book ∈ {MCL, MC5}` — the point-in-
time baselines: **MCL 3,955 trades, MC5 6,883, 550 sessions 2024-07-02 →
2026-09-11**, `entry_et` in ET. **`net` is commission-only** (gross of the
measured friction): MCL's file mean of (6.26) is the published "loses ~$6.26/
trade gross," and (6.26) − 4.26 = the published **(10.52)** at $4.26. The ladder
below subtracts $1.00 / $4.26 / $8.92 per 100-share round trip.

Per-session divides by **all 550 sessions**, traded or not (`luck_vs_edge`
convention). drop-N is by symbol. H1/H2 are the temporal halves at the median
date.

## 2. MCL

| start | n | net | /trade | /session | win% | drop-3 | drop-5 | H1 | H2 | sess+ | @4.26 | @8.92 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **04:00 baseline** | 3,955 | (24,751) | **(6.26)** | (45.00) | 27.0% | (26,859) | (27,645) | (10,817) | (13,934) | 23.5% | (10.52) | (15.18) |
| 05:00 | 3,760 | (24,517) | (6.52) | (44.58) | 26.7% | (26,627) | (27,413) | (10,724) | (13,793) | 23.7% | (10.78) | (15.44) |
| 06:00 | 3,230 | (20,860) | (6.46) | (37.93) | 27.3% | (22,932) | (23,747) | (8,804) | (12,056) | 24.4% | (10.72) | (15.38) |
| **06:30** | 2,897 | (19,007) | **(6.56)** | (34.56) | 26.6% | (21,079) | (21,894) | (8,978) | (10,030) | 23.5% | (10.82) | (15.48) |
| 07:00 | 2,430 | (17,793) | (7.32) | (32.35) | 26.0% | (19,581) | (20,369) | (8,874) | (8,918) | 23.7% | (11.58) | (16.24) |
| 07:30 | 1,887 | (16,046) | **(8.50)** | (29.17) | 25.0% | (17,812) | (18,506) | (8,430) | (7,616) | 22.9% | (12.76) | (17.42) |
| *removed 04:00–06:29* | 1,058 | (5,743) | **(5.43)** | (10.44) | 27.8% | (6,480) | (6,831) | (1,839) | (3,904) | 30.1% | (9.69) | (14.35) |

Per trade: (6.26) → (6.52) → (6.46) → (6.56) → (7.32) → (8.50). Session-positive
rate flat at ~23.5%. Drop-3 and drop-5 negative in every row; both halves
negative in every row.

## 3. MC5 — same shape, twice the size

| start | n | net | /trade | /session | win% | drop-3 | drop-5 | sess+ | @4.26 | @8.92 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **04:00 baseline** | 6,883 | (63,582) | **(9.24)** | (115.60) | 24.6% | (70,466) | (71,363) | 20.3% | (13.50) | (18.16) |
| 05:00 | 5,835 | (62,309) | (10.68) | (113.29) | 24.3% | (64,199) | (65,035) | 21.1% | (14.94) | (19.60) |
| 06:00 | 5,244 | (58,930) | (11.24) | (107.15) | 24.2% | (60,567) | (61,337) | 20.9% | (15.50) | (20.16) |
| **06:30** | 4,967 | (57,477) | **(11.57)** | (104.50) | 24.1% | (59,137) | (59,874) | 21.5% | (15.83) | (20.49) |
| 07:00 | 4,561 | (56,725) | (12.44) | (103.14) | 23.7% | (57,933) | (58,629) | 20.9% | (16.70) | (21.36) |
| 07:30 | 3,824 | (53,662) | **(14.03)** | (97.57) | 23.1% | (54,898) | (55,574) | 18.6% | (18.29) | (22.95) |
| *removed 04:00–06:29* | 1,916 | (6,105) | **(3.19)** | (11.10) | 26.1% | (12,583) | (13,443) | 27.4% | (7.45) | (12.11) |

## 4. What this settles

**It closes the caveat in `time_of_day_RESULT_20260916.md`.** That run was on
the superseded screened list, where 07:45–08:00 read **+$20.98/trade** and
07:00–08:00 was the only positive stretch. On the point-in-time books, **a 07:30
start is the worst row at (8.50)**. The screened list's mid-morning edge was the
intraday leak — buying before the screen would have surfaced the name — and
07:00–08:00 is when that leak was worth most. Removing the leak removed the
edge. **The 07:45 cell does not exist. The time-of-day question is closed**, and
the 07:00-window item (`execution_gap` §7 item 4 / `HANDOVER_TO_BUILD` item 6)
comes off the backlog.

**A filter on entry time is not a re-run.** The early trades occupied
concurrency slots; removing them frees slots for additional later trades. But
those would fire at the post-cut per-trade rate — **worse than baseline in every
row** — and H0's late-qualifier finding put late names at (1.35). **The caveat
cuts against the hypothesis, not for it.** A true re-run in the engine would
make this worse, not better, and is not worth the slot.

**It is consistent with everything else this week.** `luck_vs_edge`: per-trade
loss is flat across regimes and hot days just mean more trades. Here: per-trade
loss is roughly flat across start times, and a later start just means fewer
trades. **The strategies lose the same amount on whatever they trade; the only
lever that has ever moved the total is how much they trade.**

## 5. Standing

Nothing changes. The reset stands. Do not register a session-start variant.
