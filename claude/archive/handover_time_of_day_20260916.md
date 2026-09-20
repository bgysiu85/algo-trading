# Handover to the build chat — time of day, 2026-09-16

**From:** the research chat. Read-only analysis; no program logic touched.
**Docs:** `claude/time_of_day_RESULT_20260916.md` · raw report at
`D:\Trading\Claude outputs\time_of_day_20260916.txt`.

---

## What was asked, and what came back

Ben asked whether Ross Cameron's recaps could give us trade times paired with
outcomes, to find a time-of-day pattern. **Two of the three routes are closed
and the third has one run left in it.**

### 1. The recaps do not contain the data — probed, not assumed

Twelve recaps read in full before committing to a 317-video pass:

| | |
|---|---:|
| clock times stated | **31** (23 hour-level, 8 minute-level) |
| times attributable to a trade with a known outcome | **0** |
| videos yielding one usable pair | **0 of 12** |

He anchors entries to chart position and price — *"right here"*, *"on that
pullback"* — never to the clock. The minute-level times he does give attach to
**scanner hits**, to moves he explicitly did not trade, or to his desk sit-down
time. In one recap he is asked the time of his own trade and cannot recall it.

**Please do not commission an extraction pass over the recaps for trade times.**

### 2. The census day-level pattern is the regime, not the clock

`warrior_census_dated.csv` states a first-trade time on 88 of 401 rows. Raw, the
pattern is striking — 06:30 starts average **$69,663**, 09:00 starts **$2,035**.
It does not survive the control:

- he **starts earlier on hot days** (median first trade 07:00 hot, 07:30 cold);
- the **regime label alone moves the mean day 14×** (hot $46,481 / cold $3,258);
- **within cold days only** the curve goes non-monotone — 100% / 85% / **50%** /
  100% / 67% / 67% on cells of 1, 20, 4, 5, 3, 9;
- he states a time on days with median |P/L| **$10,855** against **$7,550**
  otherwise, so the timed subsample is selected.

Same error the census already caught once with trade count: *a symptom of
opportunity, not an input.*

---

## The one thing to run

**Re-run the ET block table on the point-in-time trade list.**

I ran it on `var/reports/screened/backtest_trades_mcl.csv` (2,413 trades, 505
sessions), which books MCL at **−$0.53/trade**. The repaired PIT universe books
it at **−$10.52** (`pit_strategy_result_20260914.md`), so **the levels below are
stale and must not be quoted.** The *shape* should survive — it is about
concentration, not level.

What the stale run found, so you know what to look for:

- **Four 30-minute blocks positive** — 06:30, 07:00, 07:30, 10:00 ET. **Not one
  survives drop-top-3.** Only 07:30 clears $4.26 friction (+3.66), and it dies
  at $8.92 (−1.00).
- **Everything before 06:30 ET loses at every friction level** — the window
  Cameron refuses to trade and MCL arms in.
- **`07:45–08:00 ET` is the standout cell**: +$20.98/trade on 80 trades over 69
  sessions, positive in both halves, the only block anywhere still positive at
  $8.92 (**+12.06**), and a **26.2% win rate** — the lowest in the table.
  **Drop-top-3 takes it from +1,678 to −537.**
- **Session level, 07:00–08:00 ET**: 259 sessions, **35.5% positive**, mean
  +8.02, **median −9.42**. Top five symbols +3,930 against a block total of
  +2,078 — **five names out of 191 are worth more than the whole hour.**

Keep all four checks on the re-run: **drop-top-N, both halves, the friction
ladder ($1.00 / $4.26 / $8.92), and the session-level denominator.** The
published hour table in `execution_gap_20260910.md` §4 had none of them.

**Either outcome is worth having.** If 07:45 survives all four on the PIT list it
becomes a registerable hypothesis with a pre-committed window. If it fails
drop-top-3 again, **the time-of-day question closes** and the 07:00-window item
(`execution_gap` §7 item 4 / `HANDOVER_TO_BUILD` item 6) comes off the backlog.

---

## Two data traps, both of which return a plausible wrong answer

**1. `entry_time` in `screened/backtest_trades_mcl.csv` is UTC, not ET.**
ET = UTC − 4. Verified against `execution_gap`'s published hour counts
(288 / 189 / 287 / 424 / 662 / 451), which reconcile exactly once shifted.
Reading those blocks as ET moves every conclusion four hours and still looks
coherent. **Check the timezone of every timestamp column before bucketing it**,
and consider printing the tz in the column header.

**2. Auto-generated transcripts render dollar prices as clock times.**
`6:20`, `8:81`, `9:50`, `7:05`, `5:30` are all *prices* in these recaps. A regex
harvest of `H:MM` across 317 videos would have returned a large, clean-looking
table of **fictional timestamps**. Excluding them was decisive in the probe. If
any future pass mines a transcript corpus for times, it needs a price filter and
a manual audit of a sample.

---

## Standing requirements

Register before you run. All three friction levels. Two denominators, and a
disagreement is a refusal. drop-top-N on the level and the delta. Both halves.
**Sessions, not trades** — that is the check that decided this one.

Nothing here is out of sample; MCL was fitted on this data. `holdout.json`
remains unspent.
