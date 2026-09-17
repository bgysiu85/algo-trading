# REGISTERED — H-C3: the profit floor at entry + 5 ticks (arm unchanged at +15)

Ben, 2026-09-17, after H-C2 read MCL REFUSED / MC5 NOTHING: *"what if we reduce from 15
ticks to 5 ticks?"* — clarified as **arm at +15 ticks, floor at entry + 5 ticks**.
**Committed before the study flag, or any run of it, exists.**

## 0. Why, and the prior

H-C2 (`profit_floor_RESULT.md`, `(15, 10)`) decomposed as: losers rescued +12,343 / +8,332,
winners > $20 cut (9,988) / (9,514), re-entries and knock-on trades (1,656) / (2,103). A
lower floor leaves a 10-tick gap under the arming level instead of 5, so fewer armed
trades are stopped on ordinary noise and fewer runners are cut. Each floor exit also
books less.

**This is the second tick pair in a family registered as closed at one pair.** H-C2 §5
recorded that any other pair is a new hypothesis. That record stands: this is it, and the
family now counts **two cells, (15, 10) and (15, 5)**. A third pair is not run on the
strength of this one. H-C2's result is the prior: exit changes here have lost every time,
and the floor's mechanism was measured working and paying the money back.

## 1. The rule

Identical to `REGISTERED_profit_floor.md` §1 in every word, with `profit_floor=(15, 5)`:
arm at the close of the first bar after the entry bar whose high ≥ entry + 15 ticks,
active from the next bar, stop = max(5% trail, entry + 5 ticks), fill min(stop, open) −
1 tick, label `profit_floor`. The engines already carry it (`114779f`, tests pin the
arithmetic for any arm > floor ≥ 0).

## 2. Universe, tape, baselines

As H-C2 §2 and amendment A, and **the same universe file H-C2 ran on**
(`var/state/screen_pairs_pit_itch_p50.json`, sha256 1db006ca23d20065), so the two cells
compare on one population. Baselines must again reproduce MCL 3,960 / (8.81) and
MC5 6,630 / (8.49). Output `var/reports/profit_floor_15_5.txt`; H-C2's report is not
overwritten.

## 3. Readings

H-C2 §3 items 1–5 unchanged, per strategy against its own baseline, with amendment A's
halves and drop-top-3-symbols. Printed as H-C2, plus one line per strategy: **(15, 5)
against (15, 10)** per trade and per symbol-day at $4.26, reported and not scored.

**Multiplicity.** With two cells, a pass must also survive this: the bootstrap P on the
delta ≥ 0.975 (0.95 halved across the family) — added here as item 6.

## 4. Written before the run

- Floor exits fall: MCL 30.3% → 18–25%, MC5 17.8% → 10–15%.
- Floor exits positive at $4.26: well under half — MCL 10–30%, MC5 5–25% — since
  +5 ticks less a tick is $4 gross.
- Runners cut fall by roughly a third on both.
- Δ per trade against baseline between (1.00) and +0.75; **NOTHING or REFUSED for both.**
  MC5 remains worse than its baseline in the bootstrap (P < 0.5).

## 5. What would make this run wrong

As H-C2 §5; plus: a different universe file from H-C2's; reading (15, 5) against
(15, 10) as the verdict; overwriting H-C2's report.

`holdout.json` stays shut.
