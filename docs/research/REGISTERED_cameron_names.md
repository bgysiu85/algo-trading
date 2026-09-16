# REGISTERED — does his name selection beat our ranking?

Item **1c** of `intraday_candidates_20260915.md`. Written and committed BEFORE
`common/cameron_names.py` is run. The commit hash is the timestamp.

Rules, arms, thresholds and refusals are fixed here. Anything the run turns up
that is not in this document is a lead, not a result.

---

## 0. Why this is worth running at all

The census gives 630 symbol-day mentions across 242 sessions: names Ross
Cameron said he traded, on days our point-in-time universe also covers. Until
the publish dates were recovered on 2026-09-16 those mentions could be ordered
but not joined to anything.

The handover phrases the question as *"do Cameron's symbols beat our top-5
volatility ranking"*. Our ranking is not by volatility. It is
`premarket_change` descending, symbol ascending, capped at `max_symbols`
(`screen_sim.screen_frame`). The loose phrase is replaced by the real one
everywhere below, because a hypothesis that names the wrong instrument cannot
be tested against the right one.

---

## 1. THE TRAP, NAMED FIRST

**He names the symbol he traded, in a recap published after the close.** His
selection is made with the whole session known. Ours is made at a tick.

This project has already paid for exactly this leak once: in
`premarket_hypotheses_results_20260908.md` §3, the universe chosen with the
day known scored **+$4.72/trade** and the same rule on a point-in-time
universe scored **(9.81)**. That $14.53 gap was look-ahead, not edge.

So a P/L comparison between his names and ours is contaminated **by
construction** and cannot be repaired by any control listed below.

**Registered consequence, and it is the design:**

> A result in which HIS names beat OURS is **NOT** evidence that his selection
> is better. It is the expected outcome of a post-hoc pick and will be
> reported as uninformative.
>
> Only a **NULL** closes anything: if names he chose knowing the outcome do
> not beat our point-in-time top 5, then name selection is not where his edge
> lives, and item 1c is finished.

The inference runs one way only. That asymmetry is registered here so that a
favourable number cannot be read as a finding after the fact.

---

## 2. The primary test is COVERAGE, and it has no look-ahead in it

**H1c-A.** On the sessions where he named at least one symbol, does our
point-in-time screen surface that symbol, and at what rank?

`best_rank` and `first_rank` in `var/state/screen_pairs_pit.json` are computed
from the tape as it stood at each tick. Asking *"what rank did our screen give
the name he traded"* uses no information from after the tick. **This is the
real experiment.** The P/L arm in §4 is a heavily caveated secondary.

Reported, every bucket printed, nothing ranked:

- share of his 630 mentions present in our universe on the mapped session;
- of those present, the distribution of `best_rank` — every rank printed, not
  a top-5 summary;
- share reaching `best_rank <= 5`;
- share reaching `best_rank <= 5` **at `first_seen`** (`first_rank <= 5`),
  which is the stricter reading: best_rank is the best it ever got, and a name
  that reached rank 3 at 09:25 was not tradeable at 05:00.

### 2.1 The control

Presence alone means little without knowing what presence costs. The control
is a **random symbol drawn from the same session's PIT universe**, matched
one-for-one to his mentions, 2,000 draws.

If his named symbols are present at the same rate and rank as a random member
of our own universe, our ranking is **indifferent** to his selection and the
coverage result is null.

Pre-registered pass criterion for H1c-A:

> His mentions reach `best_rank <= 5` at a rate at least **15 percentage
> points** above the random-draw control, with the gap holding in BOTH halves.

Below that, or with the halves disagreeing, **the answer is that our ranking
already orders his names no better than chance, and there is nothing to
attack.**

### 2.2 The absent names are a result, not a shortfall

A mention our universe does not carry is not a missing row to be dropped. It
is our screen declining a name he traded, and it is counted and reported
separately with its cause, using `screen_miss`'s existing clause diagnosis
(NOT ON THIS TAPE / NO PRIOR CLOSE / VOLUME / CHANGE / PRICE / RANK ONLY).

Dropping them would compute the rank distribution over exactly the names our
screen likes and report that our screen likes them.

---

## 3. Mapping

Publish date to session: **the nearest session at or before the publish
date**, the rule validated in `tests/docs/test_warrior_census_dates.py` (233
direct hits against 194 at a one-day lag) and re-checked against the data in
`common/regime_labels.py` (AUC 0.730 against 0.668). Max 5 days back.

A mention whose session is outside the PIT universe is **counted and excluded**,
never silently dropped.

Multi-symbol cells split on `[;,/ ]+`. `SPACEX` is not a ticker and is
excluded by name, counted separately.

---

## 4. The secondary, contaminated arm

**H1c-B.** The same mechanical rule applied to both arms:

- **HIS** — his named symbols that our universe carries, entered at
  `max(04:30, first_seen)`, held to the regular close, `QTY = 100`.
- **OURS** — our `best_rank <= 5` names on the same sessions, same rule.

Held fixed across arms: entry rule, exit rule, size, session set.

Standing requirements, all of them:

1. All three frictions — **$1.00 / $4.26 / $8.92**. Never commission-only.
2. **Two denominators** — per trade and per symbol-day. **Disagreement is a
   refusal, not a result.**
3. **drop-top-N with DROP = 5**, on the level and on the delta. `n/a`, never
   `$0`, when an arm has 5 or fewer symbols.
4. **Both halves**, split derived from the mapped sessions. An empty half is
   not a sign flip.
5. The sample is **SESSIONS**, not trades. 242 sessions is the n.
6. Every bucket printed. Nothing ranked.

And §1 above governs how the output may be read, whatever it says.

---

## 5. What would make this run wrong

- **Scoring his names on a different universe than ours.** Both arms read the
  same `screen_pairs_pit.json` and the same bar files. A name cannot be ranked
  from one tape and scored on another.
- **Comparing `best_rank` against `first_rank`.** Two numbers that look
  comparable and are not — the project's recurring shape. Each is reported in
  its own column and never pooled.
- **A control drawn from the wrong pool.** The random draw must come from the
  *same session's* universe. Drawn from all sessions it would inherit the
  size distribution of busy days and beat his names on arithmetic alone.
- **Counting a session twice.** He can publish two recaps naming the same
  symbol-day. Mentions are de-duplicated on (session, symbol) and the
  duplicate count is printed.
- **Letting the P/L arm lead.** If §4 prints a favourable number and §2 is
  null, the registered reading is §2's.

---

## 6. What this cannot settle

Nothing here touches his P/L, which is self-reported on a channel that sells a
course. It measures only whether our screen's ordering finds the names he
names.

It also cannot say his *entries* were good — only that the name was or was not
on our list. Entry quality is `entry_place`'s question and is separate.

`var/state/holdout.json` is not touched. It was cut 2026-09-07 and remains
unspent.
