# REGISTERED — MCL as published on the reporting-contaminated tape and on the exchange-only tape

`claude/tape_spikes_RESULT_20260917.md` and `claude/trf_probe_RESULT_20260917.md`:
until 2026-03-30 the TRF released overnight and early off-exchange trades from
08:00, stamped with the release minute, and XNAS.BASIC's minute bars carry
them in high, low and volume. The reported prints cannot be picked out
individually (no execution timestamp, no condition flag); they can be removed
as a class, because every one of them is a TRF print. XNAS.ITCH is the Nasdaq
matching engine alone — no TRF — pulled 2026-09-17 for the same 04:00–09:30
window, same file layout, $0.

**Committed before `common/tape_compare` has run.** This is not a strategy
test. It is a measurement of how much of every published figure was the tape.

## 1. What is run

MCL exactly as published (`common.analysis.LIVE`, 100 shares, `first_seen`
floor, $2–20, tiered commission, $4.26 friction) on the **same 6,170
point-in-time symbol-days** (`var/state/screen_pairs_pit.json`, built on
XNAS.BASIC — deliberately not rebuilt, so the only thing that differs is the
bars), once on each tape, in one process.

## 2. What is read, fixed now

1. **Per trade, all sessions**, both tapes. The published figure is (10.52).
2. **The split at 2026-03-30.** On the contaminated tape MCL reads (11.43)
   before and (8.55) after. If the tape is the cause, the exchange-only tape
   should show the two periods **much closer together**; if the market is the
   cause, the gap should survive on both.
3. **The 08:00 hour.** (18.45) before / (8.47) after on XNAS.BASIC. Same test.
4. **Paired by symbol-day**: the delta, its bootstrap interval, and how many
   symbol-days ITCH has no bars for (a coverage fact, printed, not hidden).
5. **Spike bars on ITCH**, same definition as `tape_spikes`, to confirm the
   exchange-only tape does not carry the defect.

No verdict about MCL follows from this. If MCL is still negative on the clean
tape, `stop_lever_closed_20260914.md` §4 stands with a better measurement under
it. If MCL turns positive on the clean tape, that is a reason to re-run the
closed studies on it, under their own registrations, not a result.

## 3. What else changes if the tape does

Exchange-only volume is roughly two thirds of XNAS.BASIC's. MCL's `volume ≥ 3×
previous bar` and `≥ 50% of the 60-bar average` are ratios and survive; the
screen's `≥ 100,000 pre-market shares` is absolute and was applied on
XNAS.BASIC when the universe was built. That is why the universe is held fixed
here. Rebuilding the screen on the clean tape is a separate registration.
