# H0 on the repaired point-in-time universe — 2026-09-14

`python -m common.pit_h0` · raw: `var/reports/pit_h0.txt` · bundles `20260913n`,
`20260913o`, `20260914a`

## Why it was re-run

`prior_close_repair_RESULT_20260913.md`: Databento's `ohlcv-1d` close is the
last print of the EXTENDED day (20:00 ET), TradingView's `premarket_change`
divides by the official 16:00 close. `regular_close` reconstructs the 16:00
close from the minute tape; `screen_sim --prior-close repaired` rebuilt the
universe on it.

Universe: **5,021 symbol-days / 550 sessions → 6,170 / 551** (+23.5%).
Provenance: **repaired 6,132 (99.4%) · daily 38 (0.6%)**.
Knowable by 04:30: **1,394 symbol-days** (1,258 traded) — was 798 of 5,021.

## The verdict did not move

At $4.26 friction:

| | 5,021-day | 6,170-day repaired | moved |
|---|---:|---:|---:|
| Knowable at 04:30 — offered | 798 | 1,394 | +596 |
| Knowable — trades | 722 | 1,258 | +536 |
| Knowable — net | (10,612) | (17,682) | (7,070) |
| Knowable — per trade | (14.70) | (14.06) | +0.64 |
| Knowable — win rate | 24.8% | 25.1% | +0.3pp |
| As screened — trades | 4,590 | 5,606 | +1,016 |
| As screened — net | (72,306) | (86,346) | (14,040) |
| As screened — per trade | (15.75) | (15.40) | +0.35 |
| As screened — win rate | 22.7% | 23.4% | +0.7pp |

Sign STABLE across $1.00–$8.92 on both arms. **Drop-top-5 deepens the loss on
every row** — removing the five best symbols makes the net worse, so this is not
a handful of names dragging an otherwise flat result.

**THE +$4.72 WAS THE LEAK** still stands. The like-for-like lands at
**(14.06)/trade against a rejects bracket of (9.81)** — below it, **−29% of the
way** from rejects to survivors, against −34% before. The universe grew by a
quarter, 99.4% of it got a repaired 16:00 close, and H0 moved 64 cents in the
strategy's favour without approaching the survivors bracket.

That matters more than the size of the move. This was the largest data repair
the project has done, it was made in the direction that should have helped, and
the conclusion is where it was. `pit_h0_result_20260911.md` survives unchanged.

## Two things the refresh exposed

**The KNOWABLE share rose.** 798/5,021 = 15.9% of the universe was on the list
by 04:30; now 1,394/6,170 = 22.6%. The repair did not add late stragglers — it
added proportionally MORE early qualifiers, which is consistent with the defect
being a deflated premarket change on names that ran after hours the night
before. Predicted direction, again.

**Late qualifiers are worth (1.35)/trade.** AS SCREENED (15.40) against
KNOWABLE (14.06): the early names carry what little there is, and re-ranking
through the session destroys value rather than adding it. Both are deeply
negative, so this ranks two losses.

## Downstream

`common/pit_strategy.py` constants updated in `922ebf7` (bundle `20260914a`),
**copied from the report's own constants block** rather than transcribed:

    H0_PIT_NET = -86_346.1
    H0_PIT_TRADES = 5_606
    H0_PIT_OFFERED = 6_170
    H0_KNOWABLE_NET = -17_682.1
    H0_KNOWABLE_TRADES = 1_258
    H0_KNOWABLE_OFFERED = 1_394
    H0_REFERENCE_SOURCE = "var/reports/pit_h0.txt, 2026-09-14, daily=38/repaired=6,132"

**MCL and MC5 must be re-run** (`pit_strategy --strategy mcl` / `mc5`) before any
verdict on them is quoted again.

## Three defects found on the way

1. **`pit_h0` was a 20-minute serial loop.** Sessions are independent — no
   warm-up, no carried state, no randomness — so `--jobs` splits them. 20 min →
   **11.5s on 32 workers**. The merge is explicitly DAY-ordered: unlike
   `regular_close`'s dict-of-closes this module SUMS floats, and a net that
   shifted in the last cents when `--jobs` changed would not be a constant.

2. **`H0_KNOWABLE_OFFERED` was a denominator its producer never printed.**
   `run_day` skips names whose `first_seen` is after 04:30, so it is not the
   universe size — the 798 was arrived at by hand. It is computed now (1,394),
   and the whole `H0_*` block renders as the literal lines to paste, provenance
   string included. No control constant crosses modules by transcription again.

3. **The two-denominator guard's own test read a historical case against the
   LIVE constants.** The 2026-09-11 MC5 pair (−77,662 over 5,451 trades /
   4,997 offered) was checked against whatever `P.H0_PIT_*` happened to be — so
   refreshing H0 made the pair stop disagreeing and the regression test went
   quiet. Both sides of that case are now literal, and the rendering-level check
   has its own fixture built against the current constants, with an assert that
   fails loudly if it ever stops disagreeing.

Item 3 is the same shape as everything else this project keeps finding: **a
control whose output is indistinguishable from the failure it detects**. A
regression test that passes because the scenario evaporated looks exactly like a
regression test that passes because the bug is fixed.

2,116 tests passing.

## Still open, in order

1. **Capture on the 9 remaining missed names.** The 55,200 threshold is scaled
   by a 0.552 capture measured across the WHOLE tape; low-float small caps trade
   more off-exchange, so it may be mis-scaled for exactly the names this screen
   exists for. `capture_sensitivity()` exists and has never been pointed here.
2. **`pit_strategy` for MCL and MC5**, then re-read the 2026-09-11 conclusions
   with "indicative of a related universe" (76%, PARTIAL) attached.
3. Re-state the **58% figure from `screen_lag`** and every other screen figure.
4. From earlier: the `mins_since_open` forced-flatten confound; the `c_vol`-alone
   population (15,956 bars, unpriced); the name-level separator, which must now
   beat top-5-by-volatility rather than the universe.
