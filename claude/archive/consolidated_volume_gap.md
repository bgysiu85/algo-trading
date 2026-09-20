# EQUS.MINI sees 4.7% of the tape at the close, 1.5% before the open

**Status: measured, both daily and intraday.** 8,636 screened symbol-days,
3,239 symbols, 548 dates, 2024-07-01 → 2026-09-04.

Two results carry consequences:

1. **RVOL is materially contaminated** and the contamination is noise, not
   drift, so it does not average out. A `min_rvol = 5.0` gate passes a name at
   true RVOL 5.0 only 43% of the time (§3.2).
2. **Pre-market capture is 1.5%, a third of the close figure**, with p05 at
   **0.0%** and a quarter of symbol-days having no pre-market reading at all.
   Any decision rule reading pre-market volume off EQUS.MINI is reading close
   to nothing (§3.3).

---

## 1. Capture through the session

| cutoff (ET) | n | p05 | p25 | **median** | p75 | p95 |
|---|---:|---:|---:|---:|---:|---:|
| 07:00 | 2,350 | 0.0% | 0.3% | **1.0%** | 2.5% | 7.0% |
| 08:00 | 4,706 | 0.0% | 0.5% | **1.3%** | 3.4% | 9.8% |
| 09:00 | 5,886 | 0.0% | 0.5% | **1.4%** | 3.1% | 7.6% |
| 09:30 | 6,354 | 0.0% | 0.5% | **1.5%** | 3.2% | 7.6% |
| 10:00 | 8,557 | 0.8% | 2.0% | **3.5%** | 5.2% | 9.7% |
| 11:00 | 8,616 | 1.2% | 2.6% | **4.1%** | 5.9% | 10.3% |
| 12:00 | 8,628 | 1.4% | 2.8% | **4.3%** | 6.2% | 10.8% |
| 16:00 | 8,636 | 1.6% | 3.2% | **4.8%** | 6.9% | 11.3% |
| 20:00 | 8,636 | 1.6% | 3.1% | **4.7%** | 6.6% | 10.8% |

Both sides cumulative from 04:00 ET, so every row compares the same window on
two tapes. Capture roughly **triples across the opening half-hour** and is
flat thereafter: EQUS.MINI's coverage of regular-hours exchange prints is
tolerable, its coverage of pre-market is not.

**The probe day was the worst possible sample.** 2025-04-09 came in at 9.6%
daily, the **100th percentile of 548 dates**. The preliminary 4.8%–19.6%
figures should not be quoted.

## 2. The confounds ruled out first

**Session definition.** `CLEARED_VOLUME` runs 04:00–20:00 ET. Had EQUS.MINI's
daily bar covered only regular hours, a naive ratio would have measured
*session definition* and reported it as *tape coverage*. `capture_ratio` sums
EQUS.MINI's own **minute** bars over each window against its **daily** bar —
same dataset both sides — and returned **FULL, median ratio 1.0000**. That is
also what licenses comparing the intraday ladder's last cutoff against the
daily figure: they are the same quantity.

**Selection at the early cutoffs.** A symbol-day appears at a cutoff only if
*both* tapes published something by then: 27% at 07:00, 74% at 09:30. The
excluded names are the ones EQUS.MINI saw least, so **the pre-market medians
are biased optimistic**. 1.5% is a ceiling, not a centre.

## 3. What this does to the screen

### 3.1 The dollar-volume floor is out by ~21×, and by a different factor per name

`min_avg_dollar_vol = $25,000` is applied to tape dollars, not true dollars:

| at capture | $25,000 tape floor means |
|---|---|
| p05 (1.6%) | $1,562,500 true |
| median (4.7%) | $531,915 true |
| p95 (10.8%) | $231,481 true |

Both ~21× tighter than intended **and** varying nearly 7× across names.
`max_pct_of_dollar_vol = 1.0` is sized against the same understated
denominator, so modelled fills believing they took 1% of volume took about
0.05% — **conservative**, but sizes were capped far tighter than intended.

### 3.2 RVOL is contaminated, and the contamination does not average out

`rvol = volume_today / mean(volume, prior 10 days)`, same symbol, both legs
from EQUS.MINI. Capture cancels only insofar as it is constant within a symbol:

| | log variance | 1 sd as a factor |
|---|---:|---|
| between symbols | 0.1869 | 1.54× |
| within a symbol, day to day | 0.1531 | 1.48× |
| ICC (share between) | **0.550** | between is 1.22× within |

**45% of the variation is within a name — and it is NOISE.** Median lag-1
autocorrelation of a symbol's log-capture series, over 471 symbols with 5+
observations: **−0.002**. Slow drift would largely cancel in a 10-day trailing
window. Independent noise does not cancel at all.

Simulating the measured within-symbol distribution through the actual RVOL
formula (one draw on top, the mean of ten underneath):

| measured ÷ true RVOL | | | true RVOL | clears `min_rvol = 5.0` |
|---|---|---|---:|---:|
| p05 | 0.48× | | 3.0 | 7.9% |
| p16 | 0.62× | | 4.0 | 23.9% |
| median | 0.93× | | **5.0** | **43.4%** |
| p84 | 1.41× | | 6.0 | 61.0% |
| p95 | 1.84× | | 8.0 | 83.6% |

The gate does not separate RVOL 4 from RVOL 6 with any authority — 24% against
61%. A name on the threshold passes 43% of the time, not half, because a mean
of ten in the denominator sits above the median of a single draw. **The screen
is selecting substantially on which prints EQUS.MINI happened to see.**

### 3.3 Pre-market volume on EQUS.MINI is not usable as a gate

Median capture 1.5% at 09:30 against 4.7% at the close, **p05 of 0.0%** at
every pre-market cutoff, and 26% of symbol-days with no reading at all. The
$25,000 tape floor becomes roughly **$1.67M** of true pre-market dollar volume
at the median — and for the bottom ventile, EQUS.MINI sees essentially nothing
while the consolidated tape sees real volume.

This matters for a change that has not been made yet. The screen's known
look-ahead problem (PROGRAM_INDEX: the watchlist is picked at 04:00, a daily
bar is not known until 20:00) has an obvious fix — decide on volume so far
today. **That fix is not available on EQUS.MINI.** It would be implemented
against a tape that sees 1.5% of pre-market activity, unevenly, and a
gate built on it would be close to arbitrary.

## 4. What has NOT been established

- **Nothing has been recalibrated.** No threshold in `common/screen.py` has
  moved. Do not restate the floors from a median — the per-name spread is the
  point, and §3.2 suggests rescaling is the wrong remedy anyway.
- **Whether rebuilding on consolidated volume is feasible end-to-end.** The
  statistics archive starts 2024-07-01; the screened universe starts
  2023-03-28. **Fourteen months of the backtest have no consolidated volume**,
  and that gap cannot be bought now that the plan is being cancelled.
- **Whether XNAS.BASIC closes the gap.** It carries the FINRA TRFs and is on
  disk from 2024-07-01 as daily bars only. Whether its capture is materially
  better than EQUS.MINI's is unmeasured, and the same tools would answer it.

## 5. What the schema contains

**194,099 of 194,139 records (99.98%) are `CLEARED_VOLUME`**, a cumulative
running total (verified monotonic non-decreasing), published 04:00–20:00 ET by
a single consolidated publisher (id 90). The other 40 are official daily marks
— `OPENING_PRICE`, `TRADING_SESSION_HIGH_PRICE`, `TRADING_SESSION_LOW_PRICE`,
`CLOSE_PRICE` — two per symbol, `quantity = 2147483647` (INT32_MAX,
"undefined"), so price is the payload.

## 6. Errors on the record

**The join was wrong and produced a complete, plausible report.** Daily bars
are stamped at UTC midnight; converting to ET gives 20:00 the *previous* day,
so every symbol-day matched the wrong session. Nothing raised. Out came a
median capture of 1.2%, a considered ICC of 0.405 and a reasoned verdict — all
against the wrong days, roughly a fifth of the truth. `dbn_io.daily_frame`
documents this exact trap in its docstring. What caught it was the session
check reporting the daily bar at **22.8% of the sum of its own minute bars** —
not a surprising number but an impossible one.

**An over-correction.** The `overnight_pull` job justified this schema as
"consolidated volume normalised on every trade; the same figure intraday
rather than end-of-day". That was called probably wrong and replaced with an
assertion that the schema was just exchange stat messages. The original was
right. An unverified claim was replaced with a differently unverified one, and
the second presented as a correction.

**A banded verdict describing its band rather than its data.** At ICC 0.675
the report said "roughly as much within as between" while between was 2.1×
within. The prose now quotes the actual split.

**A size projection from an outlier-dominated sample.** ~7 GB was projected
from five symbols on one day, where one symbol carried 84% of the records.
The pull came to 10.8 GB on disk against a 33.7 GB estimate.

## 7. Next

1. **Decide the remedy, not the calibration.** Rescaling `min_avg_dollar_vol`
   fixes the floor and does nothing for §3.2 or §3.3. The real options: (a)
   compute volume inputs from consolidated data, losing 2023-03 → 2024-06; (b)
   keep EQUS.MINI and accept a gate that admits RVOL-4 names a quarter of the
   time and cannot see pre-market at all.
2. **Measure XNAS.BASIC's capture** before choosing — it is already on disk and
   may sit between the two.
3. **Re-check anything already fitted on RVOL.** Every parameter tuned against
   the screened universe was tuned on a selection that is 45% tape noise.

Tools: `common/capture_ratio.py` (daily; `--from-csv` re-renders in seconds),
`common/capture_intraday.py` (the cutoff ladder),
`common/statistics_probe.py`, `common/databento_probe.py --size`,
`common/archive_inventory.py`.
