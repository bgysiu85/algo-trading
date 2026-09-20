# REGISTERED HYPOTHESIS — bar shape at entry

**Registered 2026-09-16, before any test was run against it.**
Commit `9fa812a` is the timestamp. Nothing below may be changed after a result
is seen; a revision is a NEW registration with its own date.

---

## 0. Why this one, and not the one that looked better

The 24 labelled samples produced two candidate ideas. Only one of them is
registerable, and it is **not** the one that looked strongest.

**`range_pct` (volatility) is NOT registered.** It separates Ben's takes from
his passes cleanly and on both timeframes (88.3% vs 54.2% on 1-minute, 92.3% vs
68.8% on 5-minute), and it matches the reason he wrote by hand on three samples
collected *after* the measurement. It is the best available description of what
he selects.

**And it does not separate his winners from his losers** — 88.3% vs 83.7% on
1-minute, and the 5-minute view disagrees in sign. Describing a selection rule
and predicting an outcome are different claims. Registering volatility would
have conflated them.

**Bar shape is registered instead, for a reason that does not come from the
samples at all: two instruments in this project disagree about it.**

| instrument | what it says about `close_in_bar` |
|---|---|
| `entry_features` / `entry_split` | MCL's **losses** are the trades that paid the top tick — a HIGH `close_in_bar` |
| the 24 labelled samples | Ben's **winners** are the ones that closed near the high — 68.2% against 32.1%, agreeing on both timeframes |

A disagreement between two measurements is a finding about the measurements,
and it is the only thing here worth spending a test on. The samples are what
surfaced it; they are not the evidence for it.

## 1. The claim, stated so it can fail

**H1.** Among the bars MCL enters on, entries in the **upper half of
`close_in_bar`** have a higher mean net than entries in the lower half.

**H1b (the companion, same family).** The same holds for `body_ratio`.

`close_in_bar = (close - low) / (high - low)` of the entry bar.
`body_ratio = |close - open| / (high - low)`.
Both from `common/entry_features.py`, unchanged.

**Direction: HIGHER IS BETTER.** Fixed here. This is the direction the samples
point and the OPPOSITE of the direction `entry_features` points, which is the
whole point of running it.

## 2. The threshold, and why it is not a number

**The cut is the MEDIAN of MCL's own entry population** on each feature,
computed from the population being tested. Not a number taken from the samples,
not a round figure, and not a quantile chosen after looking.

A threshold picked from 17 hindsight-labelled points would be a fitted
parameter wearing a hypothesis's clothes. A median split has no free parameter
at all.

## 3. The population, fixed before running

- MCL's point-in-time trades from `var/state/screen_pairs_pit.json` — the
  repaired universe, 6,170 symbol-days, 551 sessions, 2024-07-02 .. 2026-09-11.
- **Not** the 24 samples. They suggested the question; they cannot answer it.
- **`var/state/holdout.json` STAYS SHUT.** Cut 2026-09-07, unspent. This
  hypothesis is not ready to spend it and will not be, whatever the result
  below.

## 4. Pass criteria — ALL of them, or it fails

1. **Both halves agree.** Split by date, derived from the data being tested.
   An empty half is not a sign flip.
2. **The effect exceeds friction in both halves**, reported at all three levels
   — $1.00 / $4.26 / $8.92 — and never commission-only.
3. **Two denominators**, per trade and per symbol-day. **A disagreement between
   them is a refusal, not a result.**
4. **drop-top-5 on the level and on the delta.** `n/a`, never `$0`, when an arm
   has 5 or fewer symbols.
5. **Counted by FAMILY.** `close_in_bar` and `body_ratio` are one family (bar
   shape) in `entry_features.FAMILIES`. Two columns agreeing is ONE piece of
   evidence. If they disagree with each other, the family fails.
6. **The sample is SESSIONS**, not trades.

## 5. Kill conditions — any one of these ends it

- The halves disagree in direction.
- The upper half is worse, or indistinguishable, at $4.26.
- `close_in_bar` and `body_ratio` point opposite ways.
- The per-trade and per-symbol-day denominators disagree.
- The effect is carried by fewer than 5 symbols (drop-top-5 removes it).
- **The result reproduces `entry_features`' original finding** — that high
  `close_in_bar` marks the losers. That is a real possible outcome and it
  closes the question rather than leaving it open.

## 6. What a pass would and would not mean

A pass would say the two instruments disagree because they are measuring
different things: a human selecting *among* strong-closing bars, against a rule
that takes *all* of them. That is a hypothesis about selection versus
mechanism, and it would point at rank-don't-gate (PROGRAM_INDEX §7 item 3)
rather than at a new MCL clause.

**A pass would NOT license adding a condition to MCL.** MCL loses **$6.26 per
trade gross of all friction**; no entry filter rescues a strategy that is
negative before costs. Four independent measurements closed that on 2026-09-14
and this does not reopen it.

## 7. What is already known and must travel with any result

- 22 features × 11 families over 88 buckets: **0 clear**.
- 112 clause-margin bucket means: **zero positive**.
- Break-even needs a **1.86× lift** (29.2% → 54.3%); the best feature reached
  1.56×.
- The live paper record is **138 round trips, (1,203.13), 16.7% win**, and it
  needs no friction assumption because the fills are real.

Against that background the prior on H1 is low, and it is registered because
the disagreement is worth closing — not because it is expected to hold.

---

## Provenance

The samples that surfaced this: 24 labelled bars from Ben, 2026-02-06 to
2026-09-15, screenshots and hand-written notes, with a won/loss column added
2026-09-16. Eleven won, six lost, six passed, one unlabelled. Placed against
MCL's own 8,300 entry bars by `common/entry_place.py --reference entry`.

The measurement that produced H1's direction is in
`claude/won_vs_lost_20260916.md` §1. The correction that had to be made first —
reading a pooled median as "where Ben buys" when a quarter of the population
were bars he declined — is in `claude/entry_place_result_20260916.md` §0, and is
the reason this document splits by label everywhere.
