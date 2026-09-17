# REGISTERED — ORB on the point-in-time universe, with the box pushed to 45

2026-09-17, **PRE-RUN**. No ORB P/L exists on `screen_pairs_pit.json`, and none on
the 120-cell grid. The runner changes this run depends on are in the commit that
follows this one; git's ordering, not a hash quoted here, is the claim that this
was written first.

Parent documents: `docs/research/REGISTERED_orb_grid.md` (§1–§7, amendments A, B,
C) and `claude/orb_first_results.md`. Nothing in them is loosened here. Where this
document is silent, they govern.

---

## D.0 Why this run, and why it comes before anything else

The first XNAS.BASIC run cleared §11 criteria 1–5 on the baseline cell
(+$3.33/trade over 4,875 trades, drop-top-5 +$13,571, bootstrap 1.000) **on the
stage-2-survivor universe**. On that same universe H0 read +$4.72/trade and on
the point-in-time universe −$15.78. Stage 2 screened with the day's own daily
bar; ORB trades a break that is part of that bar. `orb_first_results.md` §5
measured the leak and could not decide it. This run decides it. Until it has
run, no ORB figure is believed, no grid lead is pursued, and nothing is
"shipped" in any sense.

---

## D.1 What is run — two passes, one code version

Both passes use the same commit of `strategy/orb/`, the same cache root
(`bar_cache_xnas`, tape **XNAS.BASIC**, refused otherwise), 120 cells
(`GRID_MINUTES = (5, 15, 30, 45)` per C.2), 8 jobs.

| pass | `--pairs` | `--labels` | role |
|---|---|---|---|
| **PIT** | `var/state/screen_pairs_pit.json` | `pit` | **the result** |
| **SURVIVOR RE-RUN** | `screen_pairs_consolidated.json` `screen_rejects.json` | (default) | the control |

**The survivor pass is re-run, not quoted.** The first run's figures were
produced by a runner with three defects fixed since (C.1, C.3, D.2 below).
The leak is priced as SURVIVOR RE-RUN minus PIT on the baseline cell, with the
code held constant. Comparing PIT to a number in `orb_first_results.md` is a
defect of reading.

The two universes overlap on 3,643 symbol-days. That is expected — a name that
was knowable at 04:30 can also survive stage 2 — and is not removed from either.

### The universe, as checked before registration

- 6,170 symbol-days, 551 sessions, 2024-07-02 → 2026-09-11.
- **Cache coverage was 59%** on 2026-09-17: 2,537 symbol-days had no file in
  `bar_cache_xnas\3d_to_2000`, spread over every month. The present 59% were
  mostly present *because* they were also stage-2 survivors. **So the run is
  conditional on building the missing bars first** (`common.bar_cache_build`,
  `--dataset XNAS.BASIC --out bar_cache_xnas`). The runner now refuses any
  universe with more than **1.0%** of requested symbol-days missing a file, and
  prints requested / no file / no RTH bars in the provenance block.
  **Passing `--max-missing-pct` above 1.0 for this run voids it.**
  If the archive cannot supply the missing bars, the run does not happen on the
  remainder; that outcome is reported as "not run", not as a partial result.
- `first_seen` for every pair is at or before **09:30 ET** (latest: 09:30). The
  grid's earliest range end is 09:35 and its earliest fill 09:40, so no cell can
  act on a name before it was known, and no entry floor is applied. The runner
  refuses a universe where this stops being true.
- Population: one label, `pit`. **There is no reject arm.** §10.2b's leak cut is
  replaced by the SURVIVOR − PIT subtraction above, which is the better control.

---

## D.2 A defect in criterion 6, found reading the runner (POST-RUN on the first run)

`orb_first_results.md` §1.1 describes the §10.2 screen as *"`change_from_open` at
range end above 5%, price inside $2–20 … everything in it is known at 09:45"*.
The runner did not compute that. `grid._rth_screen` read
`sess["close"].iloc[-1]` — **the 15:59 bar, the day's RTH close**. The screen
was therefore "closed more than 5% above its open", which a working long breakout
satisfies by construction.

Consequences, stated now:

1. The first run's criterion 6 (**passes +$31,103 / fails −$13,281**) is a split
   on the outcome and is **WITHDRAWN**. It was not a pass on three rules; it was
   not a test.
2. Criteria 1–5 and 7 of the first run are untouched — the screen feeds only the
   population split.
3. The fix reads the close of the last minute bar inside the **baseline** range
   (the 09:44 bar, closing 09:45), exactly as `preflight.measure_day` does, and a
   test fails if any later bar can change the answer.
4. §6's limitation stands on top of this: three of four rules
   (`relative_volume_10d_calc` not computable).

---

## D.3 How the PIT pass is read

All seven §11 criteria, **on the baseline cell only**
(`15 · structure · none · r_2`, flat 100 shares, §9 fills, IBKR Tiered):

1. drop-top-3 and drop-top-5 both > 0
2. symbol-cluster bootstrap P(total > 0) ≥ 0.95 (`common/breadth.py`, same seed
   and resamples)
3. per trade ≥ $1.00 — **and** per symbol-day reported beside it
4. trades ≥ 100
5. both halves > 0, **split at the median session date of the PIT pairs** as the
   runner derives it (2025-08-07 on the file as registered). Not the survivor
   run's 2025-08-06, not swept.
6. the §10.2 split (D.2 fixed, three rules) does not reverse the sign
7. no optimum on a boundary, **read as C.1 defines "wins"**: best readable
   per-trade cell over joint length × stop, `none` arm. 45 is now the upper edge;
   a win there is NOT MET and pushing past 45 needs its own registration. 5 is a
   hard lower edge (C.2); a win there is NOT MET and cannot be made met.

Criterion 7 is read on this run's PIT pass. It is **not** read on the survivor
re-run as a substitute.

**Round trips, not legs (C.3).** `trades` counts positions; `legs` is its own
column. `r_3_trim`'s per-trade figure is readable for the first time.

### Sample size, stated before seeing it

At the survivor run's baseline trigger rate (4,875 of 27,758, 17.6%), 6,170
symbol-days give roughly **1,085** baseline trades. That clears criterion 4 by an
order of magnitude, but the bootstrap and drop-top-5 have about a fifth of the
survivor run's sample, and many retest and 45-minute cells may fall under the
100-trade floor. Thin cells are printed and not read, as before.

---

## D.4 The decision each outcome leads to — fixed now

| PIT baseline | means | next |
|---|---|---|
| **fails 1 or 3** | the survivor edge was the stage-2 leak, as H0's was | ORB closed at baseline on this design. Grid leads (`trail_pct`, `zone`) are **not** rescued by re-reading them on PIT without a new registration |
| passes 1–6, **fails 7** | an edge whose length is not located | one push past the failing edge, registered, on PIT; still no paper |
| passes **all seven** | the first strategy to survive the leak | `var/state/holdout.json` is the next step, registered first. Paper trading is after the holdout, not instead of it |
| fails 2, 5 or 6 only | not an edge by this project's bar | closed as above; the failure is written up, not argued with |

The leak figure (SURVIVOR RE-RUN − PIT, per trade and per symbol-day, with
drop-top-N on the delta) is reported whatever the table row.

---

## D.5 The registered prediction (mine, scored whichever way it goes)

**The PIT baseline fails criterion 3: per-trade net below $1.00.**

Reason: H0 moved −$20.50/trade between the same two universes; ORB's exposure to
stage 2 was argued in spec §3.2 to be larger, not smaller, because ORB's trade is
part of the bar stage 2 read. A survivor edge of +$3.33 is far smaller than H0's
measured leak. Against this: ORB enters after 09:45 on a price break, which is
itself a point-in-time filter H0 did not have, and could select the same movers
stage 2 did without needing to see the day. If that is what happened, the
prediction fails, and that is the interesting outcome.

Secondary, weaker: with 45 in the grid, the joint `none`-arm winner is interior
(30) on the survivor re-run. Not predicted for PIT — the sample is too small to
say.

---

## D.6 What would make this run wrong

- **Running on a partial cache**, or raising `--max-missing-pct` to make it go.
- **Carrying the survivor split date** into PIT, or sweeping it.
- **Comparing PIT to `orb_first_results.md`** instead of the survivor re-run.
- **Quoting the first run's criterion 6** anywhere (D.2).
- **Reading criterion 7 on any arm but `none`**, or on the baseline row alone (C.1).
- **Substituting a grid winner into §11** (parent §7).
- **Reading `r_3_trim` from the old CSV** (C.3).
- **Spending the holdout** on anything but a PIT pass of all seven, registered.
- **Running from a checkout that does not contain this document's commit** before
  the runner commit.

Expect rejection.

---

# AMENDMENT D.7 — 2026-09-17, PRE-RUN. Still no ORB P/L on the PIT universe.

The bar fetch landed (`strategy.orb.pit_bars verify`: 536 dates, nothing lost)
and `common.bar_cache_build` wrote 2,404 more files. **133 of 6,170 PIT
symbol-days (2.2%) still have no cache file**, so the runner refuses, as D.1
says it must. This amendment is about why those 133 are missing, and it changes
what the cache has to hold for ORB. It does not change the 1.0% limit.

## Why they are missing

| reason | n | what it is |
|---|---:|---|
| **window short of warm-up** | 99 | the day's bars exist; one or both of the two PRIOR sessions do not |
| no window in calendar | 22 | 6 are 2024-07-02 (archive start); 16 are 2026-09-01..04 (below) |
| no source file | 12 | 2024-07-03 and -05, before the archive can supply a 5-day lookback |

**The 99.** Checked on the archive itself: 81 of the 82 outside September 2026
have a full target-day RTH session (e.g. MKDW 2024-08-02, QNTM 2024-08-16: 390
of 390 minutes) and are missing only prior sessions. They are a name's first or
second day on the tape: IPOs, uplistings, new tickers. The other 17 are
September dates hit by the calendar gap.

**The 3-session file is not an ORB requirement.** `bar_cache_build` refuses a
short window because MCL needs two sessions of warm-up, and a short file there
would be silently dropped. ORB reads `rth_session(df, day)`: 09:30–16:00 on the
target day and nothing else. No indicator in `orb.py` looks back past 09:30.

**And excluding them is not neutral.** A name's first days on the tape are among
the largest RTH movers in any small-cap universe. Dropping them for a warm-up the
strategy never uses would take out a group chosen by something tied to how it
trades, and call what is left point-in-time.

**The 16 September dates** have a separate cause. `E:\Databento\XNAS.BASIC\
ohlcv-1d\2026-09.dbn.zst` was re-pulled today for 2026-09-05 → 09-17 and now
holds 09-08 to 09-16 only. The bars for 09-01 to 09-04 are gone, so those
sessions dropped out of the trading calendar every cache build reads.
`databento_universe` takes a month chunk's start from `--start`, not from the
month. That is an archive defect in `common/` and is reported to its owner. It
is not fixed here.

## What changes

1. The PIT pass reads a **second cache**, `bar_cache_xnas_1s`, built by the same
   `common.bar_cache_build` from the same archive and tape with `--sessions 1`,
   for the PIT pairs only. `grid --fallback-cache` reads it **only for a
   symbol-day the primary cache has no file for**. The primary wins wherever
   both hold a file (tested). Every fallback read is counted in the provenance
   block and the header. A fallback on another tape is refused, even with
   `--anyway`.
2. The September calendar is repaired before either build, by re-pulling the
   full month's daily bars. If it cannot be repaired, the 16 remain skips.
3. **The survivor re-run does not use the fallback.** It is the control, and it
   runs exactly as D.1 registered it.

## What remains a skip, stated before the run

With the calendar repaired: the 6 symbol-days on 2024-07-02, the 12 on
2024-07-03 and -05, and 1 with no target-day bars. That is **19 (0.31%)**, under
the 1.0% limit, which is unchanged. Without the repair, 35 (0.57%). Either way
the provenance block prints the count. **A run needing `--max-missing-pct`
above 1.0 is still void.**

## What would make this amendment wrong

- Using the fallback for anything but a pair the primary lacks.
- Using it on the survivor re-run.
- Adding any indicator to `orb.py` that reads before 09:30 on the target day. A
  one-session file would then be a short file after all, and this amendment would
  need to be withdrawn.

---

# AMENDMENT E — 2026-09-17, PRE-RUN on the XNAS.ITCH universe. POST-RUN on the XNAS.BASIC one.

The D.1–D.7 run is done (`claude/orb_pit_RESULT_20260917.md`): baseline
**−$4.58/trade**, criteria 1, 2, 3, 5 and 6 failed, 0 of 110 readable cells
positive, D.4 row 1, ORB closed. While it ran, the PIT universe was rebuilt on
XNAS.ITCH (`REGISTERED_screen_itch`; `PROGRAM_INDEX` §1 rule added
2026-09-17), and `PROGRAM_INDEX` §7 item 2 now names
`var/state/screen_pairs_pit_itch_p50.json` as ORB's universe. The universe this
run read, `screen_pairs_pit.json`, was selected on pre-market bars that are
TRF-contaminated from 08:00 before 2026-03-30. No ORB result exists on the ITCH
universe. This amendment registers that run so the close rests on the named
universe and not on a superseded one.

## E.1 What changes, and what does not

- **Universe:** `screen_pairs_pit_itch_p50.json`: 6,564 symbol-days, 551
  sessions, 2024-07-02 → 2026-09-11. It shares 5,922 with the BASIC PIT file;
  642 are new to it. Latest `first_seen` is 08:23 ET, inside the 09:35 limit.
  Label `pit_itch`.
- **Bars stay XNAS.BASIC, RTH only.** ORB reads 09:30–16:00. The TRF defect is
  the overnight release at 08:00, which is before the session ORB reads. Measured
  before registering, not assumed: `common.tape_spikes.spike_mask` over every RTH
  bar of the 6,120 ITCH symbol-days already in the cache finds **90 spike bars in
  2,233,659 (0.40 per 10,000)**. No 15-minute bucket is above 1.4 per 10,000, and
  the 09:45 bucket is 12 of 87,789. Pre-cut 0.48 per 10,000, post-cut 0.16. The
  pre-market 08:00 hour on BASIC was the defect because it held 89.5% of 16,787
  spikes. The RTH window carries no such concentration. The grid keeps refusing
  any tape but XNAS.BASIC.
- **Code, criteria, D.7 fallback and the 1.0% coverage limit: unchanged.** The
  missing bars (443 symbol-days at registration) come in by the D.7 route:
  `pit_bars` plan → fetch → verify → `bar_cache_build` (3 sessions), then the
  1-session fallback for whatever is left.
- **Split date derived by the runner:** 2025-08-07 on the file as registered.
- **No survivor re-run.** The control is the one already run
  (`orb_grid_survivor_v2.txt`), with identical code and bars. The survivor
  universe does not depend on the pre-market tape in the way the PIT one does.

## E.2 How it is read

All seven §11 criteria, baseline cell, exactly as D.3. **D.4 applies unchanged,
and the ORB close is overturned only by D.4 row 2 or 3 on this run** (passing
1–6). A pass of 1 and 3 alone does not reopen ORB: under D.4 it is still "not an
edge by this project's bar", and the write-up says so. The BASIC-universe result
is reported beside this run, not averaged with it, and not replaced by it if they
disagree.

## E.3 Prediction

**The baseline fails criterion 3 again, below $0.00/trade.** 90% of the
symbol-days are shared, and on the BASIC run the shared-with-survivors group was
already negative (−$2.35/trade). The 642 new names were surfaced by a
threshold that is looser before 08:00 (PROGRAM_INDEX §7 item 1b). If anything,
that adds early, thin names.

## E.4 What would make it wrong

Everything in D.6 and D.7, plus: reading this run on any tape but XNAS.BASIC RTH;
quoting whichever of the two PIT runs reads better; re-opening grid leads from
either run.
