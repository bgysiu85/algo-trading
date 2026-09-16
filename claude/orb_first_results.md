# ORB first results — six of seven, on a universe that has lied before

2026-09-16. `python -m strategy.orb.grid --pairs var\state\screen_pairs_consolidated.json var\state\screen_rejects.json --cache bar_cache_xnas --jobs 8`
Raw: `var\reports\orb_grid.txt`, `var\reports\orb_grid_cells.csv`. Tape **XNAS.BASIC**,
27,758 symbol-days, split 2025-08-06, 296 s. Registration: `docs/research/REGISTERED_orb_grid.md`
and its two amendments, both committed before this ran.

**Read §0 before any number below.**

---

## 0. What this is and is not

**This is the first strategy in the project to clear §11 criteria 1 through 6 on the
baseline cell, including the replaced criterion 2 that MC5 failed.** Criterion 7 is not
met as the grid stands and requires a re-run with the box pushed. So ORB does **not**
ship to paper on this document — §11 says all seven — and the missing one is a re-run,
not a rejection.

**And it is measured on the stage-2-survivor universe, which has manufactured an edge
this size before.** `PROGRAM_INDEX` §2: H0 read **+$4.72/trade** on these survivors and
**−$15.78/trade** on the point-in-time universe. The screen's stage 2 used the day's
own bar, ORB trades a break that contributes to that bar, and spec §3.2 said ORB's
exposure to that leak is *larger* than a pre-market strategy's. §5 below measures the
leak and cannot decide it. **The point-in-time run decides it**, and nothing here is
believed until it has run.

Two more things a reader must carry:

- The first full grid ran on EQUS.MINI by mistake (`bar_trim`-style provenance defect,
  mine — the runner recorded no tape; fixed in `20260916w`). I saw those numbers before
  these. The registered predictions predate both runs; my reading below does not.
- Every number is **in-sample on a hindsight-selected calendar** (spec §13). Criterion
  5's halves are a split of one sample, not a holdout. `var/state/holdout.json` is
  unspent and stays so.

---

## 1. The baseline cell against §11

`ORB_MINUTES 15 · STOP structure · RETEST none · EXIT r_2` — fixed from the sources in
registration §2, flat 100 shares, §9 fills, IBKR Tiered.

| | value | bar | |
|---|---:|---|---|
| trades / symbols / symbol-days | 4,875 / 2,414 / 4,875 | | |
| net | **+$16,218** | | |
| **1.** drop-top-3 / drop-top-5 | **+$14,381 / +$13,571** | both > 0 | **pass** |
| **2.** cluster bootstrap P(total > 0) | **1.000** [+9,679, +22,614] | ≥ 0.95 | **pass** |
| **3.** per trade | **+$3.33** | ≥ $1.00 | **pass** |
| **4.** trades | 4,875 | ≥ 100 | **pass** |
| **5.** halves (median date 2025-08-06, not swept) | early **+$7,050** (2,214 d) · late **+$9,168** (2,661 d) | both > 0 | **pass** |
| **6.** §10.2 split does not reverse the sign | passing pop. **+$31,103** / failing **−$13,281** | | **pass, on 3 of 4 rules** |
| **7.** no optimum on a grid boundary | best length sits at **30** (and at 5, read the other way) | interior | **NOT MET — push required** |

Context, not criteria: win rate 43.7%; stop 52.6% / target 37.9% / session-end 9.6%;
79 bars held both stop and target (1.6%, the stop won every one); zero positions open
when bars ran out; per-trade interval [+1.99, +4.63] (withdrawn condition (b), printed
as context only).

For scale, the last strategy to be scored on this universe at flat 100: MC5 at
**+$1.11/trade, drop-5 +$2,537** over 7,403 trades — and then **−$8.93/trade** once
re-run on XNAS.BASIC, and closed. ORB's baseline is on XNAS.BASIC already.

### 1.1 Criterion 6, and the rule that is not there

Within survivors, a 09:45 screen built **only from the opening range** — `change_from_open`
at range end above 5%, price inside $2–20 — splits the sample cleanly:

| population (survivors) | symbol-days | net | per day |
|---|---:|---:|---:|
| passes the 09:45 screen | 2,912 | **+$31,103** | +$10.68 |
| fails it | 1,470 | **−$13,281** | −$9.03 |

That screen is point-in-time — everything in it is known at 09:45 — and it is doing the
work. The edge lives where an RTH screen would have looked, which is what criterion 6
asks. **But the screen simulated is three of its four rules.** `relative_volume_10d_calc`
is not computable from a cache holding three prior sessions, and
`largecap_evidence_20260911.md` finds the outside literature's entire stocks-ORB edge
came from ranking on first-5-minute relative volume. The rule we cannot test is the one
the literature says carries everything. Registered in advance (`REGISTERED_orb_grid.md`
§6) so this line cannot later be quoted as a full pass.

### 1.2 Criterion 7, and why "wins" needs a second amendment

Registration §4 says: if 5 or 30 wins, push the box. It did not say what *wins* means,
and the two natural readings land on **opposite edges**:

| reading | 5 | 15 | 30 | winner |
|---|---:|---:|---:|---|
| baseline row (structure / none / r_2), per trade | **4.74** | 3.33 | 2.28 | 5 |
| joint best (length × stop), per trade, `none` arm | 5.76 (structure) | 6.56 (rangefrac) | **6.60** (rangefrac) | 30 |

The structure stop prefers shorter ranges; the range-fraction stop prefers longer. That
is exactly the coupling the pre-flight predicted (registration §3.2: *the structure stop
tightens as the range lengthens, the range-fraction stop widens*), now measured. Length
and stop are one question, and this grid's box does not contain its answer.

- **Push to 45**: required, and constructible. Registered below as amendment C.
- **Push to 3**: **not constructible** under a 5-minute trigger bar — the range would end
  mid-bucket — without changing `TRIGGER_BAR_MINUTES`, which is a fifth family. The lower
  edge is a hard boundary of the design, like `STOP_MODE`'s two values, and is recorded
  as such rather than pushed.

---

## 2. The registered predictions, scored

**§B — `r_2` beaten by another exit at 15 minutes: HELD.** `trail_pct` +$5.78 against
`r_2` +$3.33. **And held for the wrong reason.** I named the mechanism as the stop
resolving faster than 2R, and predicted `r_1_5` or `trail_pct`. `r_1_5` did *worse*
(+$2.35): moving the target closer did not help. The spec's own §7.1 prior was the right
one — *a fixed target caps exactly the runners this universe is screened to produce* —
and every fixed target lost to no target, at every length and both stops.

**§A — MCL-PB does not transfer as a prior on the retest arms:** the direction I declined
to predict came out **against** retest at the structure stop and roughly neutral at
range-fraction:

| 15 min, `none` arm | r_2 per trade | `required` r_2 | `zone` r_2 |
|---|---:|---:|---:|
| structure | 3.33 | **1.37** | 4.38 (478 trades) |
| rangefrac | 4.89 | 4.15 | 0.72 |

The damage is concentrated where the stop anchors on the *retest* candle. Hypothesis,
not a result: a retest candle's low sits close to the reclaim, so R is tiny and the 2R
target is inside noise. Checkable from the R-per-cell distribution, which this run did
not write. **`zone`/structure at +$4.38 is a 478-trade lead** (drop-5 +$1,064, boot
0.991), and a lead is all it is.

**Registration §3.2's length × stop coupling: confirmed.** See §1.2.

---

## 3. Every cell, in three sentences

Ninety printed, none thin, nothing ranked. `trail_pct` is the best exit in **all 18**
(length × stop × retest) combinations at `none` and `required`; `range_1x` and `r_1_5`
are the worst nearly everywhere. Within the `none` arm every one of the 30 cells is
net-positive except three at 5/rangefrac, and the `zone` arm is where the drop-top
columns turn negative.

**One comparison refused:** 15/structure/none/`r_3_trim` reads +$2.70 per *trade* and
+$3.72 per symbol-day against the baseline's 3.33 both ways — the deltas point opposite
ways. The refusal fired on the one exit that changes the trade count by construction,
because `Trade` records a **leg** and `r_3_trim` books two. That is a definition problem
in the runner, recorded in amendment C; until it is fixed, `r_3_trim`'s per-trade column
is per-leg and is not read.

---

## 4. When it enters, how it leaves

63.8% of baseline entries land 09:45–10:29, a spike and a long thin tail to 15:30 —
the shape §12 says the trigger must produce. Exits: stop 52.6%, target 37.9%, session
end 9.6%.

---

## 5. The leak, measured and undecided

§10.2b, baseline cell:

| | symbol-days traded | net | per traded day |
|---|---:|---:|---:|
| survivors | 4,382 | +$17,822 | +$4.07 |
| rejected (control) | 493 | −$1,604 | −$3.25 |

Rejects trade about half as often per symbol-day and lose. That is consistent with the
screen finding real movers, **and equally consistent with stage 2's look-ahead
manufacturing the survivors' edge** — the two are not separable from this cut, and the
pre-flight's trigger-rate cut (84% of survivors' rate) only says stage 2 is not selecting
on the *break*, not that it is not selecting on the *day*. H0 went from +4.72 to −15.78
between these two universes. The point-in-time run is the decider.

---

## 6. What §12 requires that this run did not produce

Listed so the gap is visible rather than implied closed:

- **capital-based sizing via `compound_sim` and the price-decile table** — the number that
  flipped MCL's sign; not run;
- **per-ticker table** and **per-exit-reason friction break-even** — not written;
- **the downside break and the V2 fade** — measured per symbol-day by `orb.py`, **not
  aggregated** by the runner;
- **R as % of price per stop mode** per cell — in the pre-flight, not here;
- **§10.2b entry rate on usable ranges** by population — the CSV carries traded days,
  not usable ranges.

---

## 7. Next, in order — and none of it is "ship"

1. **Register and run the point-in-time universe** (`screen_pairs_pit.json`, 6,170
   symbol-days). This is the run that says whether §1 is real. Registered before it runs;
   the seven criteria re-read on the baseline cell there.
2. **Push the box to 45 minutes** and re-run (amendment C). Criterion 7 is read only then.
3. **Fix the `r_3_trim` leg count** and add the §6 gaps to the runner — one pass.
4. Only if 1 and 2 both hold: the paper-trading question, which starts with
   `strategy_adapter` and the live gate, and with the fact that the trader has never
   placed an RTH order.

What would make this document wrong: reading §1 as a result before step 1 has run.
