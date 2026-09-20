# The five scenarios — the $5 floor is nothing, and the give-back cap is the first rule here to pass its own readings

2026-09-18. Under `docs/research/REGISTERED_price_floor.md` (H-S5, scenario 1) and
`docs/research/REGISTERED_giveback_cap.md` (H-S4 + amendment A, scenarios 2–5), both
committed in `454870c` before any code existed. Run on
`screen_pairs_pit_itch_v2.json` (6,411 symbol-days, 550 sessions) with XNAS.ITCH bars;
the population check matches the published MCL count of 3,908. Raw:
`session_scenarios_v2_20260918.txt`; the first run, before three corrections to the
readings, is kept as `session_scenarios_20260918.txt`. Figures at **$4.26** unless
stated.

---

## 0. In one paragraph

**Scenario 1, the $5 entry floor: nothing.** REFUSED for MCL (the denominators
disagree) and NOTHING for MC5. **Scenarios 2 and 3, the 50% give-back cap: MC5 passes
all six registered readings, under both scopes, at every friction level — the first
rule in this project to do that** — while MCL fails, and under session scope is made
*worse*. **Scenarios 4 and 5, the combinations: nothing**; once the floor has removed
the cheap names, the cap no longer beats its control. The pass is real and it is
narrow: MC5 still loses **$7.79 a trade** after the cap, against $8.57 before. This
reduces a loss. It does not create an edge, and §6 of the registration says a pass is
not adoptable on its own.

---

## 1. Scenario 1 — the $5 entry floor

| | trades | per trade | Δ per trade | Δ per symbol-day | verdict |
|---|---:|---:|---:|---:|---|
| MCL baseline | 3,908 | (8.97) | | | |
| MCL at $5 | 1,742 | (9.17) | **(0.20)** | +2.98 | **REFUSED** — denominators disagree |
| MC5 baseline | 6,462 | (8.57) | | | |
| MC5 at $5 | 2,758 | (7.64) | **+0.93** | +5.35 | **NOTHING** — fails 1, 2, 5 |

MC5's +0.93 lands inside the band predicted in §5 (+0.50 to +2.00) and inside random
removal's, whose p95 is +1.97. MCL's is negative: the names it refuses were, if
anything, slightly better than the ones it keeps.

**The registered mechanism does not operate as written, and the arithmetic says so.**
§2 argued that friction is 2.13% of a $2 stock and 0.85% of a $5 one, so a floor
should buy back some of the cost. But the per-trade delta between two books is a
difference of means, and a flat per-trade friction cancels out of it exactly — which is
why the floor's per-trade delta is **identical at $1.00, $4.26 and $8.92**. At flat 100
shares the dollar friction is the same whatever the price; only its *share* of the move
differs, and that shows up per symbol-day, not per trade. The mechanism was stated
before the run and is corrected here rather than quietly dropped.

## 2. Scenarios 2 and 3 — the give-back cap

The rule, from §1 of the registration: walking each session's closed trades in time
order, once realised P&L has peaked at $40 or more and then fallen to half that peak,
no further entries. Open positions ride their own exits.

**MC5, every cell:**

| scope | friction | Δ per remaining trade | random cut p95 (scored) | matched-count p95 (reported) | verdict |
|---|---|---:|---:|---:|---|
| session | $1.00 | +0.53 | +0.50 | +0.59 | PASSES |
| session | **$4.26** | **+0.78** | +0.51 | +0.57 | **PASSES** |
| session | $8.92 | +0.76 | +0.33 | +0.50 | PASSES |
| strategy | $1.00 | +0.67 | +0.57 | +0.48 | PASSES |
| strategy | **$4.26** | **+0.68** | +0.51 | +0.47 | **PASSES** |
| strategy | $8.92 | +0.60 | +0.33 | +0.47 | PASSES |

Six of six on the scored control. Five of six also clear the reported matched-count
control; the exception is session scope at $1.00, where +0.53 sits under its +0.59 —
the least relevant friction, since the measured figure is $4.26 and the honest one is
nearer $8.92.

**§7's other two conditions are met.** Removed trades are measurably worse than kept
ones: (10.57) against (8.36) under session scope, (11.58) against (8.37) under
strategy scope. And the fire time is spread across the morning — 10 fires at 04:00, 22
at 05:00, 19 at 06:00, 31 at 07:00, 22 at 08:00, 4 at 09:00 — so this is **not the
time-of-day filter under another name**, which §5 named as the way this result would
most likely be fake.

**MCL fails, and the scope matters.** Under strategy scope MCL reads (0.16) a trade;
under session scope (0.35). The account-level cap fires largely on MC5's give-back and
then removes MCL trades that were better than its average — so pooling the strategies
damages the one that did not give back. Strategy scope is the safer form and the only
one that passes for MC5 without that cost. (MCL does pass at $8.92 under strategy
scope, +0.34 against +0.26; it fails at $1.00 and $4.26, and §7 requires both $4.26
and $8.92.)

## 3. Scenarios 4 and 5 — the combinations

Scored against scenario 1, which is what the cap adds *on top of* the floor (amendment
A7); the against-baseline totals are printed in the report as descriptive only, because
that delta carries the floor's contribution while the control never saw it.

| | MC5 Δ per trade | random cut p95 | verdict |
|---|---:|---:|---|
| 4, floor + session cap | +1.59 | +1.66 | NOTHING — fails 6 alone |
| 5, floor + strategy cap | +1.18 | +1.28 | NOTHING — fails 6 alone |

Both fail on the control and nothing else. MCL fails five of six in each. This is the
B5 situation the registration anticipated: **once the floor has already removed the
cheap names, the cap is no longer doing anything the floor was not** — its remaining
trades are fewer and better, and cutting their tail is no better than cutting anywhere.

## 4. Three corrections to the readings, and why they are the story

The first run produced the same pass. Reading its output against the registration
rather than against itself found three things, all of which cut toward the pass:

- **Reading 5 was clustered by symbol.** §4 says "by session (the unit the rule acts
  on)" and means it: a gate decides per trade, so the B-series clusters by symbol; this
  cap decides once a day, and symbol clustering treated 1,447 symbols as independent
  draws of a rule that fired on 108 days. Corrected, MC5 still reads P = 1.000 over 546
  sessions, so it did not overturn the result — but it could have, and it was wrong.
- **The matched-count control promised in amendment A4 was never implemented.** It
  matters precisely here: the scored random cut matches the tail's *shape* and not its
  *count*, and it removed fewer trades than the cap in nearly every reading — 880
  against 1,022 at $4.26. The per-trade delta scales with the share removed, so that
  mismatch flatters the cap. With the count matched exactly, MC5 still clears (+0.78
  against +0.57). **This is the check that could have overturned the pass, and it did
  not.**
- **The leading alternative explanation is now measured rather than argued.** MC5's
  2,412 one-bar trades at (31.95) are 139% of its net, and a give-back fires after
  losses accumulate — which on MC5 is when it has been re-arming into a falling name.
  If the cap were mostly a one-bar filter it would be a proxy for
  `REGISTERED_mc5_rearm`, not a session-state rule. Measured: one-bar trades are 30.8%
  of removed against 27.5% of kept under session scope, 34.7% against 27.2% under
  strategy scope. A gap of three to seven points — real, but nowhere near enough to be
  the mechanism.

## 5. What this does and does not license

**It does not reopen MC5.** MC5 has been closed as a candidate since 2026-09-08 and
still loses $7.79 a trade after the cap. A rule that recovers 78 cents on a book losing
$8.57 is a loss reduction, not an edge, and the $4.26 margin the project applies to
every gate is nowhere near cleared — amendment A6 exists so that the registered "> 0"
cannot be quoted as the stronger claim.

**It does not generalise to MCL**, which is the strategy still live. That asymmetry is
the most important limit on the finding: one strategy of two, and the one already
closed.

**What it has earned is the holdout** — §6's three conditions, in order:

1. *Not the time-of-day filter.* Checked above, and it is not.
2. *The live trader can compute `realised` the same way the backtest does.* Not built.
   This project has been bitten three times by a constant the live path never read, most
   recently MC5's own apex exit; a session-level rule needs the parity test before it
   goes anywhere near a live session.
3. *Spend the holdout, once.* Not done, and it should not be done yet — see below.

**One test belongs before the holdout.** `PROGRAM_INDEX` §7 item 11 is the **daily loss
stop**, an absolute drawdown from zero, and it has never been run. The give-back cap
fires on sessions selected for having declined, where stopping is close to
tautologically better than continuing; what is not yet known is whether the *give-back
shape* beats a simpler stop on the same sessions. If a flat daily stop-loss captures
the same 78 cents, the peak-relative rule is an ornament. That is one registration and
one cheap run, and the holdout is spent once.

## 6. What this is not

Not out of sample — `holdout.json` is untouched. Not a cap model: each symbol-day runs
alone, and a give-back stop frees concurrency slots this cannot price (§7 item 15). Not
live: `strategy_adapter`'s price band is unchanged and the trader has no give-back rule.
Not a search — one floor, one give-back, both named before the run.

## Commands run

```
python -m common.session_scenarios --jobs 8
```
