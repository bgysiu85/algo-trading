# REGISTERED — H-S4: the session give-back cap (PRE-RUN)

**Author: research chat, 2026-09-17** (`claude/REGISTERED_giveback_cap_20260917.md`).
**Build: the build chat.** Reproduced here verbatim as §0–§7 so the commit hash
is the timestamp, per the standing rule; **amendment A is the build chat's and
is also PRE-RUN** — written before `common/session_stop.py` existed.

---

## 0. Provenance — two independent arrivals

| source | words |
|---|---|
| Malyarovich, channel pass 2026-09-16 (`source_videos_20260907.md` §12.6) | *"You have to protect at least 50% of the profit that you make on a day-to-day basis"* |
| Ross Cameron, `spaw93SAySQ`, 2026-09-16 (§13) | *"if I give back half my profit, I need to walk. Because by giving back half my profit, I'm almost inevitably, invariably, emotionally compromised"* |

Two unrelated practitioners, the same threshold, arrived at independently. This
project treats that pattern as worth a measurement — it is the same standard that
promoted the 40–60% retracement band after three arrivals.

**Why it is not a re-run of anything already closed.** Every mechanic tested on
MCL to date is **trade-level**: entry filters (22 features, 11 families, 88
buckets, 0 clear), entry margins (112 buckets, zero positive), stops (monotone),
exits (cent stop, profit floor, ladder, partials, confirm-N, hold cap), regime
gates (`luck_vs_edge`, `cold_veto`). This is a **session-level** rule conditioned
on the session's own realised path. Nothing in that family has been tested.

It is also distinct from `PROGRAM_INDEX` item 11, the **daily loss stop**, which
triggers on an absolute drawdown from zero. This triggers on a retreat from the
session's own **peak**, and can fire on a day that is still net green.

---

## 1. The rule

```
For each session, walking the closed trades in time order:
    realised      = cumulative realised P&L so far, net of friction
    peak          = running max of realised
    armed         = peak >= ARM
    if armed and realised <= GIVEBACK * peak:
        no further ENTRIES this session
```

- Open positions at the moment the cap fires **ride their normal exits**.
  Force-flattening them is a second, different rule and is not registered here.
- `peak` and `realised` are **realised only** — closed trades. Marking open
  positions to market makes the trigger depend on an unrealised number the live
  trader would have to poll, and makes the backtest path-dependent inside a bar.
  It also matches what both sources describe: profit you *had*.
- **`GIVEBACK = None` must be bit-identical** to today.

**Parameters, and the count is deliberate.** `GIVEBACK` is the hypothesis.
`ARM` exists only to stop the rule firing on a one-cent peak and is **not
swept as a free parameter** — it is fixed at one average winner, $41.53 per 100
shares from `pit_three_results_20260911` §3, rounded to **$40**, and that number
is recorded here so it cannot be chosen after seeing results.

---

## 2. The control that decides this, and why it is not optional

**On a book that loses money, any rule that removes trades improves the total.**
MCL is (10.52)/trade; stop it earlier and the session's loss is smaller by
construction. A naive reading of total P&L would score this rule a success on
arithmetic that has nothing to do with the hypothesis.

So the primary reading is **not** total P&L.

**H0 — matched random stop.** For each session, remove the *same number* of
trailing trades that the cap would have removed, but choose the stop point at
random within the session. 10,000 draws. The cap must beat the 95th percentile
of that distribution.

**The claim under test, stated so it can fail:** the trades that occur *after* a
50% give-back are worse than the trades that occur before it, by more than
friction, and by more than an equivalent random truncation would produce.

If the removed trades lose the same as the kept trades, this is the
dollar-volume-floor result again (`where_the_edge_is_20260913`) and the answer
is NOTHING.

---

## 3. Cells

| cell | GIVEBACK | status |
|---|---|---|
| **GB-50** | 0.50 | **PRIMARY** — both sources say 50% |
| GB-33 | 0.33 | boundary |
| GB-67 | 0.67 | boundary |
| **control** | None | must be bit-identical |
| **H0** | matched random truncation | required, 10,000 draws |

Best cell landing on GB-33 or GB-67 **fires the boundary check** and the range is
in the wrong place — the rule that closed the cent stop.

Reported, not scored: the same rule on MC5; a variant that force-flattens open
positions; `ARM` at $20 and $80 as a sensitivity, **not** as a choice.

---

## 4. Readings

Baseline must reproduce **MCL 3,955 trades / (10.52) per trade** on the v1 p50
point-in-time book before anything else is read.

At $4.26, then $1.00 and $8.92:

1. **Δ per *remaining* trade > 0** — this is the primary number, not total P&L;
2. Δ per symbol-day > 0 — **both denominators, disagreement is a refusal**;
3. both temporal halves;
4. drop-top-3 and drop-top-5 **on the delta**;
5. cluster bootstrap by session (the unit the rule acts on), 95% CI clear of zero;
6. **beats the 95th percentile of H0**, the matched random truncation.

All six. Any one failing → NOTHING.

**Also report, because they are how the result is read rather than scored:**

- sessions in which the cap armed, and in which it fired;
- trades removed, as a count and as a share of the book;
- **per-trade P&L of removed vs kept trades** — the whole mechanism in one row;
- the distribution of the fire time of day, against the `session_start` sweep's
  finding that later starts are monotonically worse;
- median trades per session before and after.

---

## 5. Registered prediction

- **NOTHING.** Δ per remaining trade (0.50) to +1.50, failing reading 1 or 6.
  Confidence: **moderate**.
- **Reason for the prior:** `luck_vs_edge` measured per-trade P&L as flat across
  hot / mixed / cold sessions, and `cold_veto` found the same. If session state
  does not separate outcomes *between* sessions, a rule conditioned on session
  state *within* one has to find something those two missed.
- **Total P&L is expected to improve**, and that is predicted here precisely so
  it cannot be reported as a success. It is the arithmetic of removing trades
  from a losing book.
- **The interesting failure mode:** the cap fires late in the session, where
  `session_start` already showed per-trade results are worse. If the removed
  trades are worse *only* because they are late, the rule is a time-of-day filter
  wearing a different name — and time of day is closed. **Report the fire-time
  distribution so this is visible rather than inferred.**

---

## 6. If it passes

A PASS is not adoptable on its own. A session-level rule changes the *shape* of
the live day, so before it ships:

- confirm it is not the time-of-day filter in disguise (§5);
- confirm the live trader can compute `realised` the same way the backtest does
  — the project has been bitten three times by a constant the live path never
  reads (`mc5_apex_live_split_20260917.md` is the most recent);
- spend the holdout, once.

---

## 7. Go / no-go

**Adopt** only on all six readings at $4.26 *and* $8.92, with removed trades
measurably worse than kept trades, and a fire-time distribution that is not
simply "late in the session".

**Refuse** on any single reading. In particular, **a total-P&L improvement with a
flat per-remaining-trade delta is a refusal, not a finding** — that is the
signature this registration exists to catch.

---

# AMENDMENT A — 2026-09-17, PRE-RUN. Build chat, before any code exists.

Six clarifications. Every one is written before `common/session_stop.py` is
created and before any book has been produced. Nothing below changes the
hypothesis, the threshold, `ARM`, or the go/no-go.

**A1 — the baseline is the v2 book.** §4 asks the baseline to reproduce "MCL
3,955 trades / (10.52) per trade on the v1 p50 point-in-time book". Those two
figures are the **XNAS.BASIC** ones (`screen_pairs_pit.json`); v1 p50 reads
3,960 / (8.81). Both are superseded. The deciding file since
`screen_itch_v2_RESULT_20260917.md` is **`screen_pairs_pit_itch_v2.json`, 6,411
symbol-days**, on which the published baselines are **MCL 3,908 / (8.97)** and
**MC5 6,462 / (8.57)**. The baseline arm reproduces those or the run stops.

**A2 — two scopes, two rules, both scored.** §1 says "no further ENTRIES this
session" without saying whose session. Both readings are wanted and they are
different rules with different trip times:

- **SESSION scope** — one accumulator across every live strategy; the trip stops
  all of them. This is the account-level rule, and it is the one a live trader
  with a single shared account actually faces.
- **STRATEGY scope** — one accumulator per strategy; the trip stops only that
  strategy, and the other keeps trading.

Neither is a sensitivity of the other and neither is the primary: they answer
different questions and are reported side by side.

**A3 — MC5 is a scored cell, not a reported one.** §3 placed "the same rule on
MC5" under reported-not-scored. The ask is all strategies, so MCL and MC5 — the
two in `LIVE_STRATEGIES` — are both scored. VW9 is rejected on history and
cannot be paper traded; ORB is RTH and belongs to the ORB chat; H0 is the
control, not a strategy. **This doubles the family count and is declared here
rather than after the run.**

**A4 — the control, stated so it can be implemented.** §2's H0 is "remove the
same number of trailing trades … but choose the stop point at random", and
those two conditions cannot both hold: a session's tail of length *k* has
exactly one position. Fixed here, before any result:

- **Scored control — random cut, same session.** For each session in which the
  cap fired, draw a cut point uniformly over that session's own trades and drop
  everything after it. It matches the **shape** (a tail) and the **session**;
  it does not match the count. **10,000 draws, SEED 20260916.** The cap's Δ per
  remaining trade must beat the 95th percentile.
- **The mean number of trades removed by the cap and by the control is printed
  beside the verdict**, because they differ and the direction of the bias is
  only visible from that row: if the control removes *more*, the test is
  conservative; if *fewer*, it is not, and the reading has to say which.
- **Reported, not scored:** `gate_study.abstention`, the matched-count random
  removal at 2,000 draws, for continuity with the B-series.

**A5 — friction moves the trip.** `realised` is net of friction, so the trip
point is not the same at $1.00, $4.26 and $8.92. The cap is **recomputed at
each friction level**, never computed once at $4.26 and re-priced. Stated
because the cheap version of this is wrong in a way no downstream reading
would reveal.

**A6 — reading 1's bar, and the project standard beside it.** §4 reading 1 is
"Δ per remaining trade > 0", with no margin. The project standard since
2026-09-17 is a **$4.26 margin** against an abstention control (`PROGRAM_INDEX`
§4, "on a losing book, a total-based reading rewards abstention"). **The
registered six are scored exactly as written**, and the margin comparison is
printed beside reading 1 and labelled, so that a pass on "> 0" which fails the
margin cannot afterwards be quoted as the stronger claim.

**A7 — the combinations.** Scenarios 4 and 5 of the ask are H-S5 (the $5 entry
floor, `REGISTERED_price_floor.md`) composed with the SESSION and STRATEGY
scopes of this cap. A composition is **not a new hypothesis** and gets no
additional multiplicity, but it does get its own line: a combination that
passes where neither component passes is the B5 situation — two rules that each
read as random removal do not sum to selection — and would be reported as such
rather than adopted.
