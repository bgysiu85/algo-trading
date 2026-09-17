# REGISTERED — H-C1: MC5 re-arms only after its entry signal has switched off

Ben, 2026-09-17, after asking how to make MC5 avoid bad trades: *"yes please"* to
registering the first candidate. **Committed before the engine parameter, the study
module or any result exists.**

## 0. Why this rule, and what is already known about it

MC5's entry is **level-triggered**: it buys on any closed 5-minute bar where all three
conditions hold (RSI(14) rate of change ≥ +5% over 3 bars, EMA9 > EMA21, MACD >
signal). After an exit, the next bar on which the conditions still hold is a new entry
on the same, unchanged signal. There is no cooldown and no per-name limit.

Counts known at registration, from `var/reports/first_entry_skip_trades.csv` (the
XNAS.BASIC point-in-time MC5 book, 6,883 trades on 3,731 traded symbol-days). These are
**counts only, with no P/L read**:
- **3,152 of 6,883 trades (45.8%) are re-entries** into a symbol-day already traded;
- gap from exit to re-entry, in 5-minute bars: 1 bar 379, 2 bars 604, 3 bars 365,
  4 bars 322, 5 bars 224.

The CSV cannot say whether the signal stayed on across those gaps. Only the run can say
how many re-entries the rule refuses.

## 1. The rule, exactly

A per-(symbol, session) **armed** flag:

- **Armed at the start of the session.** The first entry of a symbol-day is unchanged:
  it is taken on the first eligible bar with `entry` true, exactly as today, including
  after `first_seen` and the price band.
- **Disarmed by any full exit** (`trailing_stop`; `window_close` ends the session anyway).
- **Re-armed by the first closed bar at or after the exit bar on which `entry` is
  False.** "At or after" means the exit bar itself counts: a stop on a bar whose own
  signal has already switched off re-arms immediately.
- **An entry needs `entry` true AND armed.** A bar refused for being disarmed does not
  re-arm anything.

Implemented as a new `rearm_after_exit: bool = False` parameter on
`strategy/mc5/mc5.backtest_session`. **False must be bit-identical** to the current
engine on every session, and a test asserts it. The flag is position-state dependent,
so it is NOT expressed as an `entry_gate` mask. This is the live-deployable form: a
refused re-entry is never opened, and the bars it would have held stay free for later
signals. The "delete re-entries from the finished book" form is not run.

Everything else is MC5 as shipped: 04:00–09:30 ET, 5% trail, `gap_fills=True`, peak
seeded from entry, $2–20 band at entry, flat 100 shares, tiered commission, one tick
each side, apex OFF, `not_before = first_seen`.

## 2. Universe, tape, control

- **Tape:** XNAS.ITCH `ohlcv-1m` (`handover_tape_switch_20260917.md`).
- **Universe:** the **current published point-in-time universe at run time**, meaning
  the `screen_itch_v2` universe if its RESULT has been committed before this runs,
  otherwise `var/state/screen_pairs_pit_itch_p50.json`. The report prints the pairs file
  and its commit. The choice is made by that rule, not after seeing either result.
- **Baseline:** MC5 ungated on that universe in the same run. It must reproduce the
  published `pit_strategy --strategy mc5` figure for that universe (for p50 v1:
  **(8.49)/trade at $4.26**), or the run refuses a verdict.
- **MC5 only is scored.** MCL has the same flaw, but MC5 is the question asked.
  Adding MCL doubles the family; it can be registered separately.

## 3. Readings — the gate_study five, inherited unchanged

For the re-armed book against its baseline, at $4.26, all five of:

1. **Δ per trade ≥ $4.26 AND Δ per symbol-day > 0.** A sign disagreement between the
   two is a REFUSAL.
2. **Both halves** (`holdout.split_sessions`), each on both denominators, > 0.
3. **Drop-top-3 on the level and on the delta.**
4. **Symbol-cluster bootstrap on the delta ≥ 0.95.**
5. **The abstention control:** remove from the baseline, uniformly at random, the same
   number of trades the rule removed (baseline trades − re-armed trades, floored at
   zero), 2,000 draws at SEED 20260916. The rule's Δ per trade must exceed the draws'
   **95th percentile**.

All five → **PASSES**, a candidate for the holdout under its own registration, not a
rule to ship. Fewer → **NOTHING**, naming which.

**Printed every time:**
- the three friction levels ($1.00 / $4.26 / $8.92);
- re-entries refused (the exact count of baseline entries whose bar was disarmed), and
  that as a share of all baseline trades and of baseline re-entries;
- losses avoided and winners lost among the refused trades;
- the cascade (re-armed-book entries the baseline lacks);
- top-10 baseline trades absent from the re-armed book;
- the refused re-entries' gap-in-bars distribution.

**Reported, not scored: (a) edge-only.** Enter only on a bar where `entry` is true and
the previous bar's `entry` was false, first entry included. It is a precomputable
`entry_gate` mask and is the stricter reading of "first turns on". It is reported so
the two forms can be compared. It is not a second chance to pass.

## 4. Written before the run

- **The rule binds on 15–35% of MC5's baseline trades.** Many re-entries come after
  gaps of several bars, and MACD-over-signal plus EMA9 > EMA21 often stays true through
  a 5% pullback, so a large share of re-entries should be refused, but not all.
- **Δ per trade between (1.00) and +2.00: NOTHING on reading 1's margin.** It will
  probably land inside the abstention band, like H-B1, H-B3 and H-B4.
- **Per symbol-day improves, because it trades less.** Reading 5 is there to discount
  exactly that.
- A pass that rests on the few names with many re-entries is a pass on those names;
  drop-top-3 and the cluster bootstrap are the check.

## 5. What would make this run wrong

- `rearm_after_exit=False` not bit-identical to the current engine.
- Re-arming reading any bar before the exit bar, or the flag persisting across sessions.
- A disarmed-refused bar re-arming the flag.
- A rule that never binds, unremarked. The refused count is printed, and zero is a defect.
- The baseline not reproducing the published figure for its universe.
- Running on XNAS.BASIC, or on a universe chosen after seeing results.
- Changing the re-arm condition (e.g. "RSI only switches off") after the run. That is a
  new hypothesis.

## 6. What this cannot settle

- Whether the rule helps MCL (not run) or the full-day MC5 (`REGISTERED_mc5_full_day.md`,
  whose rule stays MC5 as shipped).
- Live effect on the concurrency cap: a refused re-entry frees a slot. No backtest
  models the cap (§7 item 15).
- `holdout.json` stays shut.
