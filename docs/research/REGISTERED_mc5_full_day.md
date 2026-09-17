# REGISTERED — MC5 extended to 04:00–20:00 ET, with the screen running all day

Ben, 2026-09-17: *"Extending the MC5 strategy to full day (4am to 8pm)."* His
choices: backtest first (the live trader is not touched), price the pull before
anything is fetched, and **the screen keeps running after 09:30**, so names can
join during regular hours and after-hours. **Committed before any code or data
for it exists.**

## 0. Priors, written first

- MC5 is CLOSED as a candidate. Point-in-time: −$13.50/trade, −$15.06/symbol-day
  (6,883 trades). Fails the replaced criterion 2 at 90.2%.
- VW9, the only 04:00–20:00 strategy built here, was rejected at −$4.96/trade.
- **Expectation:** the trades the extension adds are negative per trade at $4.26,
  but less negative than PRE (RTH median spread 60 bps against PRE 83 / POST 87,
  and no TRF hold before 08:00). POST is expected to be the worst block.

## 1. The strategy rule

MC5 exactly as shipped: signals, 5% trail, $2–20 band at entry, flat 100 shares,
`gap_fills=True`, peak seeded from entry, tiered commission, one tick of slippage
each side, apex OFF, `not_before` = the name's `first_seen`. **One change:** the
window is 04:00–20:00 ET, and the forced window exit moves from 09:30 to the
20:00 close. Indicators run continuously across 09:30 and 16:00, with no reset
and no separate warm-up.

A position open at 09:30 is no longer closed there. Pre-market ENTRIES are
therefore unchanged, and their outcomes are not. Those trades are reported as
**carried**. They are not scored (§4).

## 2. The screen, run forward 04:00–20:00

Cadence 60 s, bars visible only after they close, ties broken by symbol, top
`MAX_SYMBOLS` = 40 by the block's change column at each tick. That is
`screen_sim`'s mechanism unchanged. Volume thresholds are scaled by the tape's
capture, p50 0.552, so 100,000 → 55,200. The capture sensitivity at p10/p90 is
printed beside the headline.

| block | change column | price | volume |
|---|---|---|---|
| PRE 04:00–09:30 | last close vs the prior regular close (repaired, `regular_close.json`) ≥ 20% | 2–25 | cumulative from 04:00 ≥ 100k |
| RTH 09:30–16:00 | last close vs the prior regular close ≥ 20% | 2–25 | cumulative from 09:30 ≥ 100k |
| POST 16:00–20:00 | last close vs **today's** 16:00 regular close (same construction) ≥ 20% | 2–25 | cumulative from 16:00 ≥ 100k |

PRE is exactly the existing screen, and it must reproduce `screen_pairs_pit.json`
first_seen for first_seen (a test asserts this). **One cap all day:** a name enters
the universe the first tick it makes the top 40 and is never dropped; it stays
armed until 20:00. A name's `first_seen` is the entry floor.

## 3. Arms, one run, one tape (XNAS.BASIC)

| arm | window | universe |
|---|---|---|
| **A: control** | 04:00–09:30 | PRE screen |
| **B: frozen** | 04:00–20:00 | PRE screen only |
| **C: running** (primary) | 04:00–20:00 | PRE + RTH + POST screens |

A must reproduce the published PIT MC5 figure (6,883 trades, −$13.50) or the run
refuses a verdict.

## 4. Readings

Every table: blocks PRE / RTH / POST (by ENTRY time) plus carried; all three
friction levels ($1.00 / $4.26 / $8.92); both denominators; session medians; trade
counts; symbols; coverage (sessions with bars past 16:00).

**The added trades are arm C's entries at or after 09:30.** The extension PASSES
only if ALL of these hold on the added trades:

1. per trade > $0 at $4.26 friction;
2. positive in both temporal halves (`holdout.split_sessions`), where an empty half
   is a failure;
3. drop-top-5 symbols total > 0;
4. symbol-cluster bootstrap total > 0 in ≥ 95% of 2,000 resamples;
5. the session median per session is > 0.

RTH and POST are reported separately. **A pass by one block alone is a new
hypothesis, not a pass.** Arm B's added trades are reported against the same five
criteria but not scored. Carried trades: the delta against arm A is reported and
not scored. This adds trades rather than removing them, so the abstention control
does not apply; the added set must stand on its own sign.

**Otherwise NOTHING**, and MC5 stays at 04:00–09:30 in `LIVE_STRATEGIES`.

`holdout.json` locked slice is untouched.

## 5. Data

ALL_SYMBOLS XNAS.BASIC `ohlcv-1m`, windows 09:30–16:00 and 16:00–20:00, the same
550 sessions as the PRE slices (2024-07-01 → 2026-09-09). One-day probe on
2026-08-04: RTH 136.7 MB billable, POST 11.0 MB, PRE 11.0 MB, all $0.0000.
Estimated ~81 GB billable, ~24 GB on disk. Priced in full before `--confirm`.

---

## Amendment A — PRE-RUN, 2026-09-17: the tape is XNAS.ITCH

Made before any data for this study was pulled or any code written, after
`claude/handover_tape_switch_20260917.md` and `REGISTERED_screen_itch.md` moved the
pre-market tape to XNAS.ITCH. On XNAS.BASIC, TRF prints released at 08:00 carry
prices from hours earlier. A study that runs through 09:30 on one tape and past it
on another would have a volume and price discontinuity at 09:30 inside MC5's
indicators. So:

1. **Every window (PRE, RTH, POST) reads XNAS.ITCH `ohlcv-1m`.** §5's pull is
   XNAS.ITCH 09:30–16:00 and 16:00–20:00, not XNAS.BASIC. The BASIC size probe stays
   quoted as the only probe run, and the ITCH pull is priced in full before `--confirm`.
2. **PRE universe = `var/state/screen_pairs_pit_itch_p50.json`**, not
   `screen_pairs_pit.json`. §2's reproduction test is against that file.
3. **Volume thresholds in every block use the chained XNAS.ITCH p50 capture** that
   `common/tape_capture` produces under `REGISTERED_screen_itch.md`, not 0.552. The
   p10/p90 sensitivity uses that registration's p10/p90.
4. **Arm A must reproduce `pit_strategy --strategy mc5 --dataset XNAS.ITCH`** on the p50
   universe (the new published MC5 baseline), not −$13.50 over 6,883.
5. **This study does not run until those ITCH baselines exist.** If
   `REGISTERED_screen_itch.md` §2.1's stop rule fires, this study stops with it.

Nothing in §1, §3 or §4 changes.
