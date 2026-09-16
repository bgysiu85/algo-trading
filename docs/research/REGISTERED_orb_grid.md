# REGISTERED — how ORB's grid is read

`orb_strategy_spec.md` §14 step 9 says "run the grid" and §11 says what a pass
is. Nobody wrote down how a ninety-cell search gets read, and that has to exist
**before `strategy/orb/orb.py` does** — not only so the bar cannot move, but
because it decides what the runner has to emit.

Written and committed before any ORB P/L exists.

---

## 1. §11's baseline cell is not a cell

§11 reads:

> in the baseline cell (`ORB_MINUTES=15`, **`RETEST_MODE` best-of-three**,
> `STOP_MODE=structure`, **`EXIT_MODE` best-of-five**)

Two of those four are searches. 1 × 3 × 1 × 5 = **fifteen cells**, and "the
best of fifteen" is not a cell — it is a maximum. A go/no-go evaluated at the
maximum of fifteen draws and then tested at a 95% bar is the multiplicity
problem with the bar written around it.

This is not a relaxation of §11 and nothing in §11's seven criteria changes.
It fixes a defect in how the cell was specified, and it makes the bar
**harder**, not easier.

---

## 2. The baseline, fixed from the sources and not from the data

Every value below is the modal or explicit choice of the ten source videos.
**None is chosen from a measurement**, because a baseline chosen from the data
is the search it was meant to anchor.

| parameter | value | source |
|---|---|---|
| `ORB_MINUTES` | **15** | modal, 6 of 10 |
| `TRIGGER_BAR_MINUTES` | **5** | V5, V6, V10 |
| `ENTRY_ON_CLOSE` | **True** | V5, V6, V10 |
| `RETEST_MODE` | **none** | V6, V8 — and the only value that adds no parameter |
| `STOP_MODE` | **structure** | V10 |
| `EXIT_MODE` | **r_2** | modal, V1 and V5 |
| `MAX_ENTRIES_PER_SESSION` | **1** | §5.5 |

**§11's seven criteria are judged on this cell and this cell only.**

Note what is deliberately *not* done: the pre-flight found 5-minute ranges
usable on 69.3% of symbol-days against 15-minute on 57.2%, and that is **not**
a reason to move the baseline. Availability is not edge, and moving a baseline
toward the biggest column is how a search result becomes a headline.

### 2.1 One value IS removed by data, and why that is legitimate

`STOP_MODE = opposite` is excluded. Its median R is **7.2–10.4% of price**
with p90 of 16–18% at every length, against `MAX_R_PCT = 12%` — a threshold
written in spec §6 **before** the measurement was made.

That is a pre-registered filter firing, not a search selecting. The
distinction is the whole point: a value eliminated by a threshold set in
advance costs no multiplicity; a value chosen because it scored best costs all
of it.

---

## 3. The grid, and what a winning cell is worth

Remaining cells: `ORB_MINUTES` {5, 15, 30} × `STOP_MODE` {structure,
rangefrac} × `RETEST_MODE` {none, required, zone} × `EXIT_MODE` {r_2, r_1_5,
r_3_trim, range_1x, trail_pct} = **90**.

All 90 run. Every one is printed — every bucket, nothing ranked, no "top
cells" table.

> **A cell that beats the baseline is a LEAD, NOT A RESULT.** It does not enter
> §11, it is not reported as ORB's performance, and it cannot become the
> shipped configuration without its own registration and its own out-of-sample
> test. `var/state/holdout.json` is not spent on a cell chosen from this grid.

### 3.1 Multiplicity is counted by family

The standing rule (`PROGRAM_INDEX` §4) counts by **family, not column**. Four
families here: length, stop, retest, exit. So the grid is four independent
choices, not ninety — and four is still four. Any claim made *from the grid*
rather than from the baseline carries that, and the report states the family
count beside any such claim rather than leaving a reader to supply it.

### 3.2 The search is JOINT on length × stop, never greedy

Measured in the pre-flight, XNAS.BASIC:

| mins | R structure p50 | R rangefrac p50 |
|---:|---:|---:|
| 5 | 3.46 | **2.61** |
| 15 | 2.98 | 3.82 |
| 30 | **2.65** | 4.47 |

The structure stop **tightens** as the range lengthens — it is the trigger
candle's low and does not scale with the range. The range-fraction stop
**widens** — it is a fraction *of* the range and does. So the better stop
changes with the length, and picking a length first would fix the wrong
confound, which is the same error §5.3 warns about for retest-versus-stop.

Length and stop are searched together. Reporting the best length at a fixed
stop, or the best stop at a fixed length, is refused.

---

## 4. The boundary rule, made checkable

§11 criterion 7: no optimum on a grid boundary.

- **`ORB_MINUTES`**: if 5 or 30 wins, the box is pushed (3, or 45) and the
  grid re-run. An interior win at 15 needs no push.
- **`STOP_MODE`**: two values remain, so **both are boundaries and the rule
  cannot apply**. The report says so explicitly rather than passing silently —
  a criterion that cannot fail is not a criterion, and one that quietly
  reports "no boundary optimum" over a two-value family is claiming a check it
  did not perform.
- **`RETEST_MODE`** and **`EXIT_MODE`** are unordered, so the rule does not
  apply and the report says that too.

---

## 5. What every cell must emit

Fixed here because the runner is written after this document:

1. trades, symbols, net, **per trade and per symbol-day** — disagreement
   between the two denominators is a refusal, not a result;
2. **drop-top-1, -3 and -5**, on the level **and on the delta against the
   baseline cell**;
3. **both halves**, split at the median session date, split point not swept;
4. the **symbol-cluster bootstrap** of `common/breadth.py` — criterion 2 as
   replaced, same seed and resample count as MC5 was scored with;
5. win rate, and the count of bars containing **both stop and target**
   (§7.2 — the stop wins, and the count says how often that assumption bit);
6. entry-timestamp histogram, which should spike at 09:45–10:15;
7. the **§10.2 population split** and the **§10.2b reject arm**.

A cell with **fewer than 100 trades is not read at all** (§11 criterion 4:
below that, drop-top-5 removes 5% of the sample and stops meaning what it
says). It is printed with its trade count and no verdict.

---

## 6. A limitation recorded now, not discovered later

**§11 criterion 6 cannot be fully tested.** It requires the §10.2 population
split, and §10.2's fourth screen rule — `relative_volume_10d_calc` — is not
computable: only **2 of 27,777** symbol-days have all ten prior sessions in
the cache, and `bar_minute` is that same cache, so no query closes it.

So criterion 6 is tested on **three of four rules** until a Databento pull of
the 09:30–09:45 window exists. That matters more than it sounds:
`largecap_evidence_20260911.md` finds **100% of the stocks-ORB paper's claimed
edge came from ranking on first-5-minute relative volume**, not from the
trigger. The rule we cannot simulate is the one the outside literature says
carries everything.

This is written down now so that a report passing criterion 6 on three rules
cannot later be quoted as having passed it.

---

## 7. What would make this run wrong

- **Substituting a grid winner into §11.** The baseline is the baseline.
- **Moving the baseline toward a pre-flight finding.** §2 above exists to stop
  exactly that, and the 5-minute availability result is named there so it
  cannot be re-argued.
- **Searching length and stop separately.** §3.2.
- **Reading a thin cell.** §5.
- **Reporting a "best cell" table.** Nothing ranked; every bucket printed.
- **Spending the holdout on anything from this grid.** §3.

Expect rejection. §11.1's base rate for clearing this bar in full is zero of
four, and MC5 — the only strategy ever to clear criterion 1 — is still being
re-scored under criterion 2 as replaced.

---

# AMENDMENT — 2026-09-16, PRE-RUN. No ORB P/L exists.

Two things arrived after this document was written and before the runner did.
Both are recorded here so that neither can be quoted afterwards as something
the grid discovered.

## A. MCL-PB does NOT transfer as a prior on the retest arms, and here is why

`claude/pullback_break_RESULT_20260916.md` ran the wait-for-a-pullback shape on
MCL's universe and returned NOTHING: 72.5% of setups cancelled on depth, a
median **+2.86%** entry premium over the signal close, and a per-trade result
that stayed negative while the total shrank. The obvious move is to read that
as a prior against ORB's `required` and `zone` arms.

**It is the wrong prior, because the entry moves in the opposite direction.**

| | what "confirmation" does to the entry price | what it does to R |
|---|---|---|
| MCL-PB | buys the break of a peak — **higher**, +2.86% median | larger |
| ORB retest | buys back near the level after a pullback — **lower** | **smaller** |

MCL-PB paid a premium to be confirmed. ORB's retest is paid a discount to be
confirmed, and §5.3 says so outright. Carrying the direction across would be
reasoning from a shared word rather than a shared mechanism.

**What DOES transfer is the abstention, and only that.** Confirmation trades
far less often, in both. The pre-flight already prices it here: at 15 minutes
a zone retest follows only **27.0%** of up-triggers, so requiring one discards
**73%** of them. Registered consequence: **retest cells will frequently fall
under §5's 100-trade floor and must be printed with their trade count and NO
verdict**, exactly like any other thin cell. A thin retest cell that looks good
is a thin cell.

## B. A stated prediction, on the one race the pre-flight has already measured

`orb_preflight_RESULT_20260916.md` §10.5: **6,001 triggers touched the
structure stop at a median of 4 bars; 5,787 reached 2R at a median of 6.** With
§7.2's stop-wins-the-shared-bar, the stop is nearer in time than the modal
source's target.

> **Prediction, registered before any cell runs: at the baseline length,
> `EXIT_MODE = r_2` will be beaten on per-trade net by at least one of the four
> other exits — most likely `r_1_5` or `trail_pct`.**

This is a prediction about the GRID, not about §11. §11 is judged on the
baseline cell and nothing here changes that; a cell that beats the baseline is
still a LEAD (§3).

Why write it down: I predicted MC5 would clear the replaced criterion 2 and it
failed at 90.2% against a 95% bar, and that prediction being on record is what
made the failure informative instead of a shrug. A prediction that turns out
right is worth more than the same number unregistered, and one that turns out
wrong is worth more still.

**If `r_2` wins anyway**, that is evidence the stop/target race does not decide
the exit, and it is reported as a surprise rather than quietly dropped.

---

# AMENDMENT C — 2026-09-16, POST-RUN. Written after `orb_first_results.md`.

Three things the first XNAS.BASIC run exposed in this document. Each is a
defect in the registration, none changes a criterion, and all are marked
POST-RUN because they were found by reading a result.

## C.1 "Wins" in §4 was undefined, and its two readings disagree

§4 says *if 5 or 30 wins, the box is pushed*. Read on the baseline row
(structure / none / r_2), **5 wins**. Read jointly on length × stop as §3.2
demands, **30 wins**. Opposite edges. The joint reading is the registered one
— §3.2 forbids reading length at a fixed stop — and it is now the rule:

> **"Wins" means the best readable per-trade cell over the joint length × stop
> search within the `none` retest arm.** Retest arms are excluded from the
> boundary read because they change the trade population.

The runner's `_boundary_block` reads across all readable cells including
retest arms; it must be narrowed to the `none` arm. Recorded as a defect.

## C.2 The lower edge cannot be pushed

§4 says push to 3 minutes if 5 wins. A 3-minute range does not end on a
5-minute trigger-bar boundary, and `orb.Config` refuses it. Pushing the lower
edge means changing `TRIGGER_BAR_MINUTES`, which is a fifth family and a
different grid. **5 is therefore a hard boundary of this design**, reported
the way `STOP_MODE`'s two values are: the rule cannot apply there, and the
report says so rather than passing silently.

**45 minutes is constructible and is added.** `GRID_MINUTES` becomes
(5, 15, 30, 45), 120 cells. Criterion 7 is read only after that run.

## C.3 A leg is not a trade

`Trade` records one closing leg, and `r_3_trim` books two per position, so
its `trades` column counts legs (6,722 on 4,875 symbol-days at the baseline
length). Its per-trade figure is per-leg and is not comparable to any other
cell's — which is exactly what the comparison-level refusal caught. The fix
is to count round trips in `Cell.add` (one per symbol-day under
`MAX_ENTRIES_PER_SESSION = 1`) and keep legs as a separate column. Until
then `r_3_trim`'s per-trade column is not read.

## What C does not do

It does not touch the baseline, any threshold, the split rule, the bootstrap
parameters, or the 100-trade floor. It does not re-score anything. The
first-run figures in `orb_first_results.md` stand as written, with §1.2 and
§3 of that document already reading them under C.1–C.3.
