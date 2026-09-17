# REGISTERED — H-C2: a profit floor beside the 5% trail (MCL and MC5)

Ben, 2026-09-17: *"exit the position if the price reverses and comes within 10 ticks
from the entry price ... I want to make sure that for every trade, we can get something
back."* His settings: the floor arms once the trade is up **15 ticks**, sits at **entry
+ 10 ticks**, and is tested on **MCL and MC5**. **Committed before the engine parameter,
the study module or any result exists.**

## 0. Why this is not the rejected breakeven stop

Cameron's breakeven stop (`cameron_exit_result.md`, `ladder_and_regime_20260911.md` §2:
−$27,260 on 4,481 trades) **replaced** the 5% trail with a stop at entry once a +10%
target was hit. That gave winners more room: hold went 8.3 → 13.5 bars and the win rate
fell 9pp. This rule **keeps the trail** and exits at whichever of the two levels is
HIGHER, so it can only tighten the exit. Nothing in the project has measured it. The
prior that transfers is weaker: every exit change tried here has lost (the ladder,
Cameron's partial, Cameron's breakeven stop), and only 7.9% of MCL trades ever reach
+10%. The runners pay for the rest.

## 1. The rule, exactly

With `entry_px` = the modelled fill (signal close + 1 tick), `TICK` = $0.01:

- **Arming.** The floor arms at the close of the first bar AFTER the entry bar whose
  `high ≥ entry_px + 15 ticks`. The entry bar's own high cannot arm it: that high
  happened before the fill (§5 trap).
- **Active from the next bar.** The same no-same-bar-lookahead convention the trail uses
  (peak as of the previous bar).
- **Level.** `floor = entry_px + 10 ticks`. On every bar after arming, the effective stop
  is `max(trail, floor)`, with trail = previous-bar peak × 0.95 as today.
- **Exit.** When `low ≤ effective stop`, the fill is `min(stop, open) − 1 tick`
  (`gap_fills=True`, as the trail). The reason is **`profit_floor`** when the floor was
  the higher level on that bar, otherwise `trailing_stop`.
- **Unchanged:** window close, entries, sizing, band, commission, `not_before`, apex OFF,
  re-entry behaviour (a floor exit frees the name for MC5's/MCL's normal re-entry).
  H-C1's `rearm_after_exit` stays OFF, and the full-day window stays 09:30.

Implemented as `profit_floor: tuple[int, int] | None = None` (arm_ticks, floor_ticks) on
`strategy/mcl/mcl.backtest_session` and `strategy/mc5/mc5.backtest_session`. **None must
be bit-identical** to today on every session, and a test asserts it for both engines.
Hand-built bar tests pin at least these cases:

- no arming on the entry bar's high;
- arming on the next bar's high;
- activation one bar later;
- a gap below the floor fills at the open;
- the trail above the floor wins the label;
- a trade that never reaches +15 ticks is identical to the baseline.

Live parity is out of scope. A live change would need its own parity test against
this engine before it could run.

## 2. Universe, tape, baselines

- **Tape:** XNAS.ITCH `ohlcv-1m`. MCL trades 1-minute bars; MC5 resamples to 5-minute.
- **Universe:** the current published point-in-time universe at run time: the
  `screen_itch_v2` universe if its RESULT is committed before this runs, otherwise
  `var/state/screen_pairs_pit_itch_p50.json`. The report prints which, with its commit.
- **Baselines** in the same run must reproduce the published `pit_strategy` figures for
  that universe (v1 p50: **MCL (8.81), MC5 (8.49) per trade at $4.26**), or the run
  refuses a verdict.

## 3. Readings, per strategy

For the floored book against its own baseline, all five of:

1. **Δ per trade > 0 AND Δ per symbol-day > 0, at $4.26 AND at $8.92.** A sign
   disagreement between denominators at either level is a REFUSAL. $8.92 is scored
   because a floor exit converts trades into small gross wins, and the measured cost
   of a stop-type exit is the upper figure (`stop_fill_20260911.md`).
2. **Both halves** (`holdout.split_sessions`), each on both denominators, > 0 at $4.26.
3. **Drop-top-3 symbols on the delta** > 0. The level is printed beside it.
4. **Symbol-cluster bootstrap on the delta ≥ 0.95.**
5. **The mechanism is present:** floor exits ≥ 5% of the floored book's trades. A floor
   that almost never fires cannot be credited with a delta. That delta is noise from
   the cascade.

All five → **PASSES** for that strategy: a holdout candidate under its own
registration, not a rule to ship. Fewer → **NOTHING**, naming which. **The family is
two strategies:** a pass on one is reported as that one only and is not generalised.

The abstention control does not apply. This rule changes exits rather than removing
entries, and the trade count moves only through the cascade, which is printed.

**Printed every time (this is Ben's question, answered as a measurement):**

- the three friction levels ($1.00 / $4.26 / $8.92);
- trades that armed (count, share);
- floor exits (count, share);
- **the share of floor exits that net > $0 at $1.00, $4.26 and $8.92**;
- the fill distribution of floor exits vs the floor level (how many gapped below entry
  + 10 ticks, how many below entry);
- win rate, scratch rate, average winner, average loser and average hold, both books;
- **runners cut:** baseline trades that reached ≥ +10% whose floored twin exited on the
  floor, with their count and the P/L forgone;
- the cascade (new entries in the floored book that the baseline lacks);
- top-10 baseline trades absent or changed.

## 4. Written before the run

- **MC5:** 25–45% of trades arm; floor exits 15–30% of trades. **At least a third of MC5
  floor exits fill below entry + 10 ticks**, because 5-minute bars gap through levels
  (48% of MC5 trail exits opened below the trail).
- **MCL:** arms more often and gaps less; floor exits 20–35% of trades.
- **Both:** win rate UP, average winner DOWN, some runners cut. Δ per trade between
  (1.50) and +1.00; **NOTHING for both**, failing reading 1 at $8.92 at the latest.
- **The share of floor exits positive at $4.26: 40–65%**, not "every trade".
- If either passes, check reading 5 and the runners-cut line first. A pass carried by a
  handful of names is caught by drop-top-3 and the bootstrap.

## 5. What would make this run wrong

- `profit_floor=None` not bit-identical, in either engine.
- The entry bar's high arming the floor, or the floor active on the arming bar itself.
- A floor fill at the level when the bar opened below it.
- Arming computed from the signal close instead of the modelled fill.
- A baseline that does not reproduce its published figure.
- Running on XNAS.BASIC, or on a universe chosen after results.
- Changing 15 / 10 ticks after seeing the run, or running a second tick pair "to see".
  Any other pair is a new hypothesis. The percent form (arm +2%, floor +1%) was
  considered and not chosen, and is recorded here so it is not picked up afterwards.

## 6. What this cannot settle

- **Live fills.** Outside RTH every stop is software-managed and sent as a Day Limit.
  The backtest's one-tick slippage on a floor exit is not the measured −$0.0563/share
  stop median. Friction is carried by the $4.26 / $8.92 levels, not by the fill model.
- Interaction with H-C1 (re-arm) and with the full-day extension: each is measured
  alone first.
- `holdout.json` stays shut.
