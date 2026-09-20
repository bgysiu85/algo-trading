# Where the edge is — run census, separator, and the check that corrected them

**The finding, after correction: being selective AT ALL is worth ~15x and is
free. Beyond that the screen adds ~1.35x and the best entry feature ~2.34x.**

An earlier version of this doc said *"name selection is worth 20x, bar selection
2x"*. That was wrong. `common/universe_lift.py` — built the same day to attack
it — is what overturned it. The 20x compared screened names against EVERY name
in the archive pull, most of which nobody would trade. A one-line sort
(realised volatility at 05:00, top five) reaches 1.610%, which is 14.9x of the
20.2x. The screen's marginal contribution over that is 1.35x, which is *smaller*
than the best entry feature's 2.34x — the reverse of the original claim.

Neither is a dramatic lever. The big one is simply "don't trade the long tail",
and that is already done.

## How this came about

Ben's 2026-09-13 reframe: stop patching MCL, look at the MOVE (TNON 2026-09-11,
07:34→07:47, +11.7% in thirteen minutes) and ask whether a strategy can be built
to capture that shape.

The reframe was correct for a reason worth recording. `entry_features` had
searched 22 features over MCL's own 482 entries and found nothing — 0 of 11
families cleared. The likeliest explanation is not that the tape is featureless
but that **MCL's five conditions had already made all 482 entries alike**. A
search for variation inside a population built to be homogeneous comes back
empty close to by construction.

## `common/run_census.py` — count the shape, no strategy in it

A run = close rises R% within N bars, never having first dipped 5% (read off
MCL's own `TRAIL_PCT`). Whole R×N grid printed; no cell chosen.

- 552 sessions, 45,041,524 bars, **67,814** runs at 8%-in-15 = **122.85/session**
- median run **$42** per 100 shares, at the ORACLE's entry and exit
- savagely concentrated: top 1% carry 27.5%, top 5% carry **56.5%**
- so a rule catching the *typical* run earns ~nothing after friction, and the
  real question is what precedes a BIG one

## `common/run_signal.py` — does anything precede a run

Both-halves discipline; precision and recall, not just lift; holdout shut.

| population | base rate | 1 bar in |
|---|---|---|
| whole premarket tape | **0.108%** | 926 |
| screened names (traded_pairs) | **2.179%** | 46 |

Best features, whole tape:

| feature | precision | recall | lift | \|r\| vol |
|---|---|---|---|---|
| range_pct | 0.51% | 81.4% | 4.68x | **1.00** (tautology) |
| ma20_slope | 0.21% | 43.7% | 1.94x | 0.02 |
| extension | 0.18% | 38.4% | 1.66x | 0.02 |
| vol_over_trail | 0.17% | 35.4% | 1.61x | 0.17 |

A run is *defined* as a percentage move, so a volatility measure predicting one
is the definition looking at itself — hence the `|r| vol` column. The best
volatility-independent signal (`ma20_slope`) takes you from 1-in-926 to
1-in-476 while firing on a quarter of all bars. Real, small, not a condition.

## `common/universe_lift.py` — the check that overturned the headline

Ranks every name WITHIN its session at a 05:00 cutoff, takes the top N, counts
runs that START after the cutoff. Criteria read only bars at or before it; a
test replaces every post-cutoff bar with noise and demands no criterion moves.

Baseline (names with ≥20 bars before 05:00): **0.108%** — identical to the
whole-universe rate, so merely being *alive* before 05:00 predicts nothing. It
is the magnitude that matters.

Lift over baseline, ranked within session:

| criterion | top 5 | top 20 | top 50 | top 250 |
|---|---|---|---|---|
| range_pct | **14.85x** | 6.91x | 3.18x | 1.14x |
| gap_pct | 10.79x | 4.65x | 2.20x | 0.93x |
| volume | 6.47x | 3.12x | 1.88x | 1.05x |
| bars_traded | 2.62x | 1.88x | 1.43x | 1.03x |
| dollar_vol | **0.29x** | 0.68x | 0.90x | 0.95x |
| price *(control)* | 0.05x | 0.06x | 0.12x | 0.84x |

Three things fell out:

1. **A one-line volatility sort gets 74% of the way to the screen's level** —
   1.610% against 2.179%.
2. **`dollar_vol` is INVERTED.** Sorting by most dollars traded selects big
   liquid names, and size suppresses percentage moves. It is the sort I would
   have guessed at, and it is worse than useless.
3. **Watchlist SIZE is its own lever.** 14.85x at five names, 3.18x at fifty,
   1.14x at 250. Nearly all the separation lives in the first handful and is
   gone by a hundred.

## Defects found and fixed along the way

Each produced a number that looked like a measurement:

1. **Base rate 15.6x too high.** Controls were sampled as a multiple of each
   symbol-day's own run count, so a day with no run left the population
   entirely — 369,098 of 388,873 symbol-days on the archive (95%), vs 2 of 407
   on the screened cache, which is why it stayed invisible for a day. The
   "base rate" had silently become the rate *within days that had a run*.
   Fixed: flat per-bar sampling, two passes. The report now computes the base
   rate by two routes and refuses the precision column if they disagree by >5%.
2. **`tape_density` read 100.00 for all 482 entries** — I assumed a dead minute
   was an absent row; this cache gap-fills, so it is present with volume 0.
3. **A constant was bucketed anyway**, printing (10.97) across four buckets all
   labelled `[100.00–100.00]` — that number was the pairs file's entry order
   wearing a feature's name.
4. **$54,313,602 ceiling** from reverse-split prices: the tape is adjusted
   backwards, so HUBC arrives at $207,533/share. Percentages sound, dollars
   fiction.
5. **No upper bound on the start window** — cache frames run to 20:00, so cases
   came from the regular session under a header claiming 04:00–09:30. It
   manufactured "runs happen early" (0.27x); bounded, 0.96x.
6. **Rank ties given distinct ranks**, so a constant feature correlated with
   everything (its "ranks" were row order).
7. **Greedy run-walk crossing the cutoff** in `universe_lift`: `runs_in` opened
   a run at bar 60 for a jump at bar 75, skipped past the cutoff at 61, and
   reported zero post-cutoff runs. Slicing AT the cutoff removes it.

## Performance work

- `features_at` was O(i) per bar. `frame_ctx()` precomputes the per-frame parts:
  **3.91 ms/bar → 0.017 ms/bar, 229x**. Equivalence tested bar-for-bar; the
  optimised run is byte-identical to the one before it.
- `MCL.signals` costs ~12 ms regardless of frame size (pandas per-call
  overhead) and was computed for every symbol-day then discarded for the ~85%
  with no run start. Labelling needs only close and low, so it is now a thunk
  past that gate.
- `--jobs` parallelises the archive. Needed a correctness fix first: the control
  draw was order-dependent, so the answer depended on worker count. Now seeded
  per (seed, day, symbol) via `zlib.crc32` — `hash()` is salted per process.

## What this does not say

- **Not that the moves aren't there.** 67,814 of them; the money is real and
  concentrated in the top few percent.
- **Not a P&L.** "Started a run" is not "made money" — that needs an exit.
- **Not the screen's ceiling.** And the naive sort it is measured against is
  close to a volatility tautology, so "volatile names keep being volatile" is
  most of what the 14.9x measures. That is not alpha.
- **Not like-for-like.** The screened figure covers 90 sessions and was selected
  using the defective `prior_close`; the universe figure covers 552. Close
  enough to correct a 20x claim, not close enough to settle 1.35x.
- **Not out of sample.** `holdout.json`, cut 2026-09-07, is untouched.

## A pattern worth naming

Twice in two days a first reading was too strong and the next measurement pulled
it back — the 15.6x base-rate error, then the 20x screen claim. Both were caught
by checks built specifically to attack the preceding result. **The first number
off a new instrument has been wrong more often than right**, and the practice
that keeps working is to build the check before building on the finding.

## Standing corrections to earlier notes

- "Name selection 20x, bar selection 2x" (this doc, first version) — wrong, see
  above.
- `ma20_slope` at 3.23x (2026-09-12) was the screened population only; whole
  tape it is 1.94x and fails the shape test.
- `dollar_vol_session` was the "nearest miss" in `entry_features`. The TNON
  07:35 bar sits in its *losing* quartile — that feature as a condition would
  have vetoed the exact trade it was meant to catch.
- MCL is not good: 34% win rate, +$0.37/trade over 482 entries. `c_floor` being
  profitable in isolation is a much narrower claim and was stated badly.
