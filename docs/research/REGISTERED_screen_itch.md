# REGISTERED — the point-in-time screen rebuilt on the exchange-only tape, and the baselines re-run on it

`docs/research/REGISTERED_tape_compare.md` §3 held the universe fixed and
said rebuilding the screen on XNAS.ITCH was a separate registration. This is
it. `claude/tape_compare_RESULT_20260917.md` found the bars alone moved MCL
from (10.52) to (8.82) per trade on the same 6,170 symbol-days, closed the
before/after gap from (2.87) to +0.22, and left the 08:00 hour at (9.71)
instead of (18.45). XNAS.ITCH is the tape to quote. Everything downstream of
the universe is still on XNAS.BASIC, including the universe itself.

**Committed before `common/tape_capture`, the XNAS.ITCH `screen_sim` runs,
`pit_h0` and `pit_strategy` on the new universe have run.** This is a
re-baselining, not a strategy test: whatever comes out becomes the published
control and the published MCL/MC5 figures, in both directions. The one thing
that can stop it is §2.1.

## 1. What is run, in order

1. **`common/tape_capture`** — on every session both tapes cover, for every
   name with ≥ 10,000 XNAS.BASIC shares by 09:30, cumulative pre-market volume
   on XNAS.ITCH over the same on XNAS.BASIC at 07:00, 08:00, 09:00 and 09:30,
   bars closed by the cutoff. Three populations: the 6,170 PIT symbol-days,
   the **band** (BASIC 09:30 volume within 0.5×–5× the scaled threshold, the
   names the clause decides — the headline), and every active name. Split at
   2026-03-30. The chained capture for XNAS.ITCH is
   `0.552 × median ratio(09:30, band)`, with p10 and p90 of the ratio as the
   sensitivity band.

   Why chained: `screen_at.CAPTURE_P50 = 0.552` is XNAS.BASIC's share of the
   consolidated *daily* bar, and there is no XNAS.ITCH daily bar in the
   archive to repeat that against. The screen never read the daily bar
   anyway; it reads cumulative pre-market volume, which is what this
   measures. The chain inherits BASIC's approximation and adds one measured
   factor. It is not a consolidated-tape measurement and will not be quoted
   as one.

2. **`common/screen_sim --dataset XNAS.ITCH`** three times, at the chained
   p10, p50 and p90 capture, each to its **own** pairs file
   (`var/state/screen_pairs_pit_itch_{p10,p50,p90}.json`) and report.
   `var/state/screen_pairs_pit.json` is **not overwritten**: the BASIC
   universe stays on disk so the two can be compared and so every result
   already quoted against it remains reproducible. Prior close stays the
   repaired regular close (`var/state/regular_close.json`, an exchange
   auction print, unaffected by TRF reporting); the daily fallback stays
   XNAS.BASIC. Cadence 60 s, clauses imported from `tv_screener` unchanged.

3. **`common/pairs_overlap`** between the BASIC universe and the ITCH p50
   universe.

4. **`common/pit_h0 --dataset XNAS.ITCH --pairs <p50 file>`** to
   `var/reports/pit_h0_itch.txt` and, new, `var/reports/pit_h0_itch.json`.

5. **`common/pit_strategy --strategy mcl|mc5 --dataset XNAS.ITCH --pairs <p50
   file> --h0 var/reports/pit_h0_itch.json`**. The `--h0` flag is new: the
   control is read from `pit_h0`'s JSON for *this* universe rather than from
   the `H0_*` constants, which stay as the published XNAS.BASIC reference.
   Pasting over them would leave one block serving two universes.

Only the p50 universe is scored. p10 and p90 exist to say how much the
universe's *size* depends on the capture figure; they are not alternative
baselines to choose between afterwards.

## 2. What is read, fixed now

### 2.1 The diagnosis check, and the stop rule

If the 08:00 defect is what `trf_probe` said it is — the TRF opened at 08:00
until 2026-03-30 and released the overnight and early off-exchange trades
from 08:00 — then on the band population:

- **07:00: before the cut ≈ 1.00, after the cut materially below 1.** Until
  08:00 the two tapes were the same tape.
- **09:30: before and after similar.** By 09:30 the same trades have printed
  either way.

**If the 07:00 line does not step at the cut, or the 09:30 line does, the
diagnosis is wrong and nothing further in this registration runs.** The
result is written up as that and the tape question is reopened.

### 2.2 The universe

1. Symbol-days and sessions at p10 / p50 / p90 against 6,170 over 551.
2. Overlap with the BASIC universe: in both, each only, Jaccard, knowable by
   04:30 on each, and the shift in `first_seen` on the shared symbol-days.
3. The `screen_sim` agreement check (fast path vs `screen_at`) must still
   pass on the ITCH slices — the report prints it.

### 2.3 The control

`pit_h0` on the p50 universe at $4.26: AS SCREENED per trade and per
symbol-day (published: (15.40) / (13.99) over 5,606 trades on 6,170), KNOWABLE
AT 04:30 (published: (14.06) over 1,258), halves, drop-top-5, and where the
like-for-like lands between the stage-2 brackets +4.72 / (9.81).

### 2.4 The strategies

`pit_strategy` for MCL and MC5 on the p50 universe with XNAS.ITCH bars, read
exactly as the module reads them: POINT-IN-TIME floored per trade and per
symbol-day, **vs H0 on both denominators** (the module refuses a verdict when
they disagree), halves, drop-top-5, the friction ladder, the floor's bite,
EARLY vs ALL. Published on BASIC: MCL (10.52) over 3,955, +4.88/trade vs H0;
MC5 (13.50) over 6,883, +1.90/trade vs H0 but (1.06) per symbol-day.

## 3. Predictions, so the result cannot be read as whatever it turns out to be

- ratio(09:30) p50 on the band between **0.55 and 0.75** (tape_compare
  counted 79% of BASIC's *bars* on ITCH; volume runs below bar count). Chained
  capture therefore **0.30–0.41**, scaled threshold ~30k–41k ITCH shares.
- ratio(07:00) before the cut **≥ 0.97**; after, **≤ 0.85**.
- Universe at p50 within **±15% of 6,170**: the threshold scales with the
  tape so the count should roughly hold, and the cleaner last print should
  remove some names that reached +20% only on a stale TRF price — so if
  anything, smaller. Jaccard with the BASIC universe **0.6–0.8**;
  `first_seen` on shared names mostly unchanged before 08:00 and moving
  either way after it.
- H0 as screened still **negative, with the rejects**: (12) to (16) per trade.
  The universe is not the edge on either tape.
- MCL **(7) to (10)** per trade — near tape_compare's (8.82) — still negative
  in both halves and after drop-top-5; MC5 **(10) to (14)**. Both still
  beating H0 per trade. None of it clears $4.26.

If MCL or MC5 clears zero on the ITCH baseline, that is the first time on an
honest universe and it wants the holdout before it is believed — the same
sentence `pit_strategy` prints for that case. It is not a result of this
registration; this registration produces baselines.

## 4. What this decides, and what it does not

- **Decides:** the published control and the published MCL/MC5 point-in-time
  figures move to the XNAS.ITCH universe and bars. `PROGRAM_INDEX` pointers
  are updated to the `_itch` reports. The BASIC files stay for comparison and
  are labelled superseded, not deleted.
- **Does not decide:** anything about a strategy variant. The closed studies
  (stop lever, pullback line v1–v6, first_entry_skip, range_rank, cold_veto,
  time_of_day) stay closed; a study whose conclusion rested on the 08:00 hour
  or the before/after split on BASIC is withdrawn as *unmeasured*, not
  reversed, and re-runs only under its own registration on the new baseline.
- **Not a before/after of the fix for the strategies.** Between the BASIC
  figures and the ITCH figures two things change at once — the universe and
  the bars. `tape_compare` already isolated the bars on a fixed universe;
  this does not repeat that and its MCL figure is not to be subtracted from
  (10.52) to price "the tape".
- `holdout.json` stays shut. Baselines are scored the way the BASIC ones
  were, on the same sessions; no go/no-go is being decided.
