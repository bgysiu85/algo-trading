# REGISTERED: the pre-market change clause at 50%, against the shipped 20%

Written and committed **before the first result exists**, per `PROGRAM_INDEX`
§1. The commit hash is the timestamp.

Asked for by Ben, 2026-09-17: *"Update the change % from 20% to 50% and run
backtests on current strategies to see if it makes them more profitable."*

## 0. Why 50, and why it is not a searched number

`warrior_0_universe_and_risk.md` §1 records two threshold sets from the same
trader. His **main account** takes "≥30% preferred, 10% absolute minimum"; his
**small-account** set — the one he states explicitly as the *higher-win-rate
subset* — takes **≥50% change on the day**. 50 is therefore a number with a
source and a stated reason, declared before any result, and not the winner of
a grid.

The shipped screen's 20 is Ben's own, live since 2026-09-08.

## 1. The rule

One clause moves. `premarket_change >= 50` replaces `premarket_change >= 20`.
Everything else is held fixed at the published point-in-time configuration:

```
tape                XNAS.ITCH           (pre-market bars; PROGRAM_INDEX §1)
price               premarket_close in [2.00, 25.00]
volume              premarket_volume >= 100,000 consolidated, scaled at capture 0.126
rank                top 40 by pre-market change, ties by symbol
cadence             60s, 04:00-09:30 ET
prior close         repaired (auction_else_last)
strategies          MCL and MC5, shipped configs, flat 100 shares
friction            reported at $1.00 / $4.26 / $8.92; the verdict reads $4.26
```

**The live screen does not move.** `tv_screener.PREMARKET_CHANGE_MIN` stays at
20.0. The threshold is passed to the simulation as `--change-min`, and
`screen_sim.change_min_refusal` refuses to write a variant universe over
`var/state/screen_pairs_pit.json`, which is the file every published figure
was decided on.

## 2. Why this is not a gate study, and what follows from that

The three gates of 2026-09-17 (H-B1, H-B3, H-B4) refused entry bars inside a
fixed universe, so the gated book was a **subset** of the baseline's trades.
A screen threshold is not:

1. A symbol-day that never reaches 50% disappears with every trade on it.
2. A symbol-day that reaches 20% at 05:10 and 50% at 07:40 **survives with a
   later entry floor**. Its trades are not the baseline's trades — bars the
   baseline was mid-position on become live signals ("signal-ordinal is not
   book-ordinal", §4).

So the variant book is not a subset, and the share of it that *is* the
baseline's trades is reported (`survivor_block`) rather than assumed.

What survives the difference is the reading that killed all three gates:
**on a book whose average trade loses, any rule that removes trades improves
every total-based figure.** That is what the verdict is built around.

## 3. The readings, and the pass criteria

The five readings of `REGISTERED_range_rank.md` §3, unchanged, via
`common/gate_study.verdict`, read at $4.26:

1. **delta per trade ≥ $4.26** (one measured round trip) **and delta per
   symbol-day > 0**. A sign disagreement between the two denominators is a
   **REFUSAL**, not a fail.
2. **Both halves, both denominators, > 0.** One cut date, taken from the
   baseline's session list, applied to both books.
3. **drop-top-3** on the level and on the delta.
4. **Symbol-cluster bootstrap on the delta**, P(total > 0) ≥ 0.95, 2,000
   resamples.
5. **The abstention control.** The same number of trades removed from the
   baseline at random, 2,000 seeded draws; the per-trade delta must beat the
   draws' **95th percentile**.

**Deltas are divided by the BASELINE's symbol-day count.** The variant's own
count is smaller by construction, and dividing by it would price a smaller
programme as a better one.

**PASSES means the tighter screen SELECTS rather than abstains. It does not
mean profitable.** Whether either book crosses zero after friction is reported
separately and is the only thing that would make this a candidate to ship.

## 4. Predictions, fixed now

- The universe falls to **15-35%** of the baseline's 6,564 symbol-days.
- The entry floor moves **later** on a clear majority of the symbol-days both
  screens keep, so **under 70%** of the variant's trades are also in the
  baseline's book.
- Per-symbol-day is **strongly positive** for both strategies, and reading 5
  shows most of it is abstention.
- **Per trade lands inside random removal's band: the verdict is NOTHING for
  both.** `range_pct` did not separate winners from losers at signal time
  (H-B3) and pre-market change is a near relative of it.
- **Neither book is positive after $4.26 at any threshold.**

## 5. Stop rules

- **The baseline arm must reproduce the published baseline.** MCL@20 here must
  read **3,960 trades at (8.81)/trade** and MC5@20 **6,630 at (8.49)**
  (`screen_itch_RESULT_20260917.md`). If it does not, the arm is not the
  published baseline and nothing downstream is read.
- **A tighter screen cannot ADD symbol-days.** If the variant universe
  contains a symbol-day the baseline does not, the two runs did not screen the
  same sessions and the run stops.
- **A half must not be empty** in either book, or reading 2 is inert.

## 6. Declared descriptive, not registered

A ladder at **30 / 40 / 60** is run for the universe counts and the headline
per-trade figures only, to show where 50 sits rather than to choose it. It is
**four cells of one family** and is reported as such; no verdict is taken from
it, and reading it as a grid would carry a multiplicity this registration does
not spend (§4, "multiplicity is counted by FAMILY").

## 7. What this cannot answer

- **The concurrency cap is not modelled.** Live, 29% of buy attempts were
  refused by it. A tighter screen frees slots, and that is the one mechanism
  by which it could help that this run cannot price (open item 15).
- **The simulated screen is still unvalidated against the live one** (open
  item 1), so this compares two simulations, not two watchlists.
- **The capture ladder defect (item 1b) is inherited**, identically by both
  arms: a single 09:30 capture applied to a pre-08:00 window. It biases *when*
  names become knowable, in the same direction in both books.
- **Not out of sample.** `holdout.json` is untouched.

## 8. The commands

```
python -m common.screen_sim --dataset XNAS.ITCH --capture 0.126 --change-min 50 \
    --out var/state/screen_pairs_pit_itch_chg50.json \
    --report var/reports/screen_sim_itch_chg50.txt
python -m common.pairs_overlap var/state/screen_pairs_pit_itch_p50.json \
    var/state/screen_pairs_pit_itch_chg50.json --out var/reports/pairs_overlap_chg50.txt
python -m common.pit_h0 --dataset XNAS.ITCH --pairs var/state/screen_pairs_pit_itch_chg50.json \
    --out var/reports/pit_h0_itch_chg50.txt --json var/reports/pit_h0_itch_chg50.json
python -m common.pit_strategy --strategy mcl --dataset XNAS.ITCH \
    --pairs var/state/screen_pairs_pit_itch_chg50.json --h0 var/reports/pit_h0_itch_chg50.json \
    --out var/reports/pit_strategy_mcl_itch_chg50.txt
python -m common.pit_strategy --strategy mc5 --dataset XNAS.ITCH \
    --pairs var/state/screen_pairs_pit_itch_chg50.json --h0 var/reports/pit_h0_itch_chg50.json \
    --out var/reports/pit_strategy_mc5_itch_chg50.txt
python -m common.change_threshold --dataset XNAS.ITCH \
    --baseline var/state/screen_pairs_pit_itch_p50.json \
    --variant var/state/screen_pairs_pit_itch_chg50.json \
    --out var/reports/change_threshold_50.txt
```

---

## Amendment A (PRE-RUN, before any strategy result was read)

The §5 stop rule fired on the universe: **9 symbol-days pass at 50% and are
absent from the published 20% universe**, which a tighter screen cannot do.

The cause is not the threshold. `var/state/screen_pairs_pit_itch_p50.json` was
written at 05:47 on 2026-09-17; `var/state/regular_close.json` was rewritten at
07:36 and `XNAS.BASIC/ohlcv-1d/2026-09.dbn.zst` at 06:26, both after it. The
prior closes the screen measures `premarket_change` against have moved:

```
published p50 run   daily=474,729  repaired=5,812,430  92.4% of 6,287,159
inputs at this run  daily=474,635  repaired=5,812,544  92.5% of 6,287,179
```

Seven of the nine fall on 2026-09-14 and 2026-09-15 — sessions the published
run skipped for having no prior close and the extended archive now covers. Two
(BIAF, CHPT on 2026-09-04) sit on a session both runs screened, so their
computed change moved with the closes.

**The amendment.** The baseline arm is REBUILT at `--change-min 20` from the
inputs on disk at this run, and that rebuild — not the published file — is what
the 50% arm is compared against. Both arms then read the same closes, the same
daily archive and the same sessions, which is the only way the delta is
attributable to the threshold.

The published file is kept and reported beside the rebuild (`pairs_overlap`),
because the difference between them is a finding of its own and belongs to
whoever owns the archive extension: **the published H0 (11.90), MCL (8.81) and
MC5 (8.49) were measured on inputs that no longer exist on disk.**

**Consequence for §5.** The reproduction check against 3,960 / 6,630 published
trades can no longer be a stop rule, because the baseline arm is deliberately
not the published one. It is demoted to a **reported comparison**: the rebuilt
MCL@20 trade count and per-trade figure are printed against the published pair,
and a large divergence is a finding about the archive change, not about 50%.
The other two stop rules stand unchanged, with the added-symbol-days rule now
read against the rebuilt baseline.
