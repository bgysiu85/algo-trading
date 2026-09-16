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
