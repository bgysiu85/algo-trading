# Handover — the pre-market tape is XNAS.ITCH from here; what that changes for the ORB and swing work

From the MCL session, 2026-09-17. Read before quoting any pre-market figure
measured on XNAS.BASIC.

## What was found

Until **2026-03-30** the FINRA/Nasdaq TRF (Trade Reporting Facility — where
off-exchange trades are printed to the tape) opened at 08:00 ET. Off-exchange
trades executed 04:00–08:00 were reported from 08:00 on, **stamped with the
report time**, and XNAS.BASIC's minute bars carry those prints in high, low,
close and volume. Result: from 08:00 on every session before that date,
XNAS.BASIC pre-market bars contain prices from hours earlier. 89.5% of the
16,787 spike bars in the archive sit in the 08:00 hour; the 08:00 hour read
(18.45) per trade for MCL on that tape and (9.71) on the exchange-only one.
The prints cannot be picked out individually (no execution timestamp, no
condition flag); they can be removed as a class, because every one is a TRF
print.

Docs: `claude/tape_spikes_diagnosis_20260916.md`,
`claude/tape_spikes_RESULT_20260917.md`, `claude/trf_probe_RESULT_20260917.md`,
`claude/tape_compare_RESULT_20260917.md`.

## The clean tape is on disk

`E:\Databento\XNAS.ITCH\ohlcv-1m\<date>_0400_0930.dbn.zst` — Nasdaq's
matching engine only, no TRF. Same window, same file naming, symbology
sidecars present, 555 sessions 2024-07 → 2026-09, $0. `common.dbn_io.read_dbn`
and `common.screen_sim.window_slices(archive, "XNAS.ITCH")` read it as they
read BASIC. Every module that takes `--dataset` takes `--dataset XNAS.ITCH`.

## What to do

1. **Any pre-market (04:00–09:30) measurement: run it on `--dataset
   XNAS.ITCH`.** Ratio conditions (volume ≥ 3× previous bar, ≥ 50% of a
   trailing average, RVOL) survive the switch; **absolute** volume thresholds
   do not — exchange-only volume is a fraction of BASIC's, and the
   registration below measures the fraction before anything is re-scaled.
2. **Do not rebuild your own universe.** `docs/research/REGISTERED_screen_itch.md`
   rebuilds the point-in-time screen on XNAS.ITCH to **new** files —
   `var/state/screen_pairs_pit_itch_{p10,p50,p90}.json` — and re-runs
   `pit_h0` and `pit_strategy` (MCL, MC5) on the p50 one as the new published
   baselines. `var/state/screen_pairs_pit.json` (BASIC) stays on disk,
   superseded. Until the p50 file exists, a result on the BASIC universe with
   ITCH bars is what `tape_compare` did and is fine as a stop-gap; say which
   universe it was.
3. **`pit_strategy --h0 var/reports/pit_h0_itch.json`** is the new way to
   point a run at the control for its own universe. The `H0_*` constants in
   `pit_strategy.py` remain the BASIC reference; do not paste over them.
4. **Withdrawn, not reversed:** any conclusion that rested on the **08:00
   hour** or on a **before/after 2026-03-30 split** measured on XNAS.BASIC.
   That includes the time-of-day table and whatever cold_veto / range_rank /
   first_entry_skip read off the 08:00 hour. Those studies stay closed; they
   re-run only under their own registration on the new baseline if someone
   wants them.

## What is probably unaffected — check, do not assume

- **Regular-hours bars on XNAS.BASIC** (the ORB's 09:30+ window). The TRF
  reported in time during regular hours, and the 08:00 release queue was
  drained well before 09:30 on the sessions inspected. `common.tape_spikes`
  is the check: run its spike census over your window and quote the count.
  An RTH pull on XNAS.ITCH is the clean alternative if the count is not ~0.
- **Daily bars** (swing). A print stamped at the wrong minute is still in the
  right day; daily OHLC can carry a stale high/low but daily volume is
  intact. If a swing rule reads the daily high or low of a session before
  2026-03-30, note it.
- **The repaired regular close** (`var/state/regular_close.json`): built from
  the closing auction print, an exchange event. Unchanged.

## Things not to do

- Do not delete or overwrite `var/state/screen_pairs_pit.json`,
  `var/reports/pit_h0.txt`, `pit_strategy_mcl.txt`, `pit_strategy_mc5.txt`.
  Results already written cite them.
- Do not "fix" XNAS.BASIC bars by filtering spikes. `spike_mask` flags a bar
  whose high or low sits 25% beyond its body; a stale print inside that band
  is not flagged and still moves the bar's close and volume.
- Do not re-open a closed study because the tape changed. The bars moved MCL
  from (10.52) to (8.82) on the same universe; nothing crossed zero.
