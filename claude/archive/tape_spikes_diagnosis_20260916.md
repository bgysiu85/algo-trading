# The 08:00 tape defect, diagnosed — XNAS.BASIC minute bars carry reported prints

**2026-09-16.** Follows `pullback_break_v2_RESULT_20260916.md` ("259 symbol-days with
interleaved price scales, undiagnosed"). Tool: `common/tape_spikes.py`, bundle
`tape-spikes-20260916a`. Universe census pending Ben's run.

## What the bars show

ALTS 2025-08-11 (v2's worst trade, bought 19.76 @ 08:35, stopped 9.49 @ 08:36):
- 07:55–07:59: bars 8.64–8.93, 6–87k shares.
- **08:00: open 10.85, high 10.89, low 6.80, close 8.75, volume 1,159,128.**
- 08:02–08:35: opens/closes 8.6–9.5 while **highs print 16–20 and lows 6.5–6.8**,
  bar after bar (08:07 high 20.05, 08:35 high 20.08).
- One instrument_id (725), so NOT two instruments interleaved — the earlier guess was wrong.

SLGB 2025-10-27: closes 3.2, highs 12.00, lows 2.08, 08:00 bar 1.3m shares. Same shape.

Whole slices: 2025-08-11 — 60 spike bars (high > 1.25× max(o,c) or low < min(o,c)/1.25),
58 in the 08:00 hour; **1,162 of 1,771 names printed an 08:00 bar over 10× their 07:xx
median volume.** 2025-10-27 — 82 spikes, 81 in 08:00; 1,642/2,338 dumps.
2026-09-11 — 11 spikes, 92/584 dumps: much lighter, matching the monthly P/L pattern
(08:00 losses heavy 2025-05→2026-03, small from 2026-04).

## Mechanism (hypothesis, consistent with everything above)

08:00 ET is when FINRA's TRF opens for the day; off-exchange overnight trades and
late/as-of reports land on the tape stamped with the minute they were REPORTED.
Minute OHLCV cannot tell a reported print from an executed one, so from 08:00 the
high, low and volume are contaminated while open/close (first/last print) mostly hold.
Exactly the check `premarket_hypotheses_results_20260908.md` §1 named and never ran.

## Consequences

Every study on XNAS.BASIC since 2026-09-08 that reads highs, lows or bar volume:
MCL's `volume ≥ 3× prev` clause (fires on the dump), every trail exit (a fake low
reaches the stop), buy-stops (v2), MFE/MAE excursions, ORB ranges. MCL's 08:00 hour
being its worst ((14.76)/trade) is partly this.

## Next

1. Run `python -m common.tape_spikes --jobs 8 --ib-cache bar_cache/3d_to_2000`:
   spike census by minute/month, MCL's book split by touched/untouched, and the same
   symbol-days on IB's bars (if IB doesn't spike on the same minutes, it's the feed).
2. Then a REGISTERED cleaning rule (which bars/prints to distrust) and a side-by-side
   re-run of MCL as published. Trade-level data with sale-condition flags (Databento
   `trades` schema) would allow dropping reported prints properly.
