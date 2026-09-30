# REGISTERED — TL-v2: TL-v1's A+ breaks, entered on the retest (Tori Trades gap 9), S/R double confirmation as a reported variant (gap 10)

**Committed before any TL-v2 code exists, before its pre-flight is run, and before any retest or S/R
count or return has been computed.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W15-0029** (this registration), **W15-0030** (free steps: engine, guards, holdout ledger,
count-only pre-flight), **W15-0031** (backtest). Source: `claude/archive/w15_0017_tori_gap_analysis_RESULT_20260926.md`
gaps 9 (break-and-retest) and 10 (S/R double confirmation), listed as "not yet tested" on 2026-09-26.

Ben's decision, 2026-09-29, in his words: *"I would like to go with option 2"* (test the parts of her
method not yet coded). His answers to the three scope questions: **retest primary with S/R as a
reported variant; base = TL-v1 A+ entries; pass bar = beat random p99, not p95.**

Amendments are marked **PRE-RUN** or **POST-RUN**. A rule or threshold changed after seeing a result
is a new hypothesis.

---

## 0. Where this sits, stated plainly

- **Honest origin.** The two gaps were written down on 2026-09-26, before any TL-v0/TL-v1 result. But
  this registration was requested **after TL-v1 failed** (criterion 6, 5 of 10). `REGISTERED_tl_v1.md`
  §0 said a further trend-line registration needs "a reason that does not begin with a result". The
  gap-analysis reason is pre-result; the timing of the request is not. Ben chose to proceed knowing that.
- **Data already seen.** The training bars 2010-06 → 2021-12 have been read by TL-v0, TL-v0-rev,
  TL-bounce and TL-v1. A fifth look at them is a multiplicity cost. It is met in three ways:
  every parameter below is **fixed now with no grid selection**; criterion 6 is raised to **p99**; and
  the **holdout is the only evidence that counts** (§6). A training-side pass alone is not a finding.
- **What it is.** TL-v1 with **only the entry timing changed**: a qualified (A+, weekly-ok) break is
  not entered at the next open; it is entered only after price returns to the broken line and holds.
  Lines, A1–A3, weekly filter, safety line, exits, sizing, costs, series, rolls: **TL-v1's, word for
  word** (`REGISTERED_tl_v1.md` §2.1–§2.4, Amendments E–G).
- **Not a change to TL-v0, v0-rev, TL-bounce or TL-v1.** All stand; none is re-scored.
- **Fidelity caveat.** She takes the retest roughly once a year (self-reported, videos only); S/R
  placement is her eye. This tests a mechanical coding of both, not her judgement.

---

## 1. The hypothesis, in one sentence

**Entering TL-v1's A+ trend-line breaks only on a successful retest of the broken line makes money
after measured costs on the owned GLBX daily history of the TSMOM markets, beats a 20/10 Donchian
channel, and beats the 99th percentile of a random selection of the same number of retest entries of
the same lines.**

---

## 2. The rules

**None of these numbers comes from her, and none is tuned.** Chosen here, before any retest count.

### 2.1 Inherited unchanged from TL-v1

Everything in `REGISTERED_tl_v1.md` §2.1–§2.4 including Amendment E (ER thresholds), Amendment G
(coding choices). A **qualified break** at bar t = TL-v1's E1 break of the §2.2 line, passing A1–A3
and the weekly filter (E2).

### 2.2 The retest (gap 9)

After a qualified break at bar t, freeze **the broken line as in force at t**, extended flat in slope
(same slope, projected forward). For bars s = t+1 … t+N with **N = 10**:

| Step | Rule (long shown; short is the mirror) |
|---|---|
| **T1 Retest** | Bar s is a retest if low[s] ≤ line[s] + **0.25 × ATR[s]** (the A1 touch buffer) — price has come back to the line |
| **T2 Holds** | and close[s] ≥ line[s] − **0.10 × ATR[s]** (the break buffer) — it did not close back through |
| **T3 Fail** | If any close in t+1…s−1 (before a retest bar) is below line − 0.10 × ATR, or if the opposite raw break occurs, the setup is dead: **no trade, counted "failed"** |
| **T4 Timeout** | No retest bar by t+N → **no trade, counted "no retest"** (the move ran away) |
| **T5 Entry** | First bar s meeting T1 and T2 → enter at the **open of s+1** (as TL-v1's next-open rule). The setup is used once; the line is not re-armed |

**Exits, stop, safety line, sizing (1%, zero = skip, counted), friction:** TL-v1's. The safety line
is computed as of the entry bar, as TL-v1 computes it at entry. Opposite raw break exits at the next
open; **reverse only into another qualified retest entry** (never straight off a raw break); otherwise
flat. While a setup is pending (t+1…s) the strategy is flat in that market if it was flat.

### 2.3 Reported variants (fixed now, never ranked, cannot spend the holdout)

| Variant | Change | Tells us |
|---|---|---|
| **TL-v2 + S/R** (gap 10) | Retest entries only where a **horizontal zone** coincides with the broken line: a cluster of ≥ 2 confirmed pivots (L = R = 5, same side, in the last 250 bars before t) whose prices all lie within **0.25 × ATR** of each other, and the zone's mean is within **0.5 × ATR** of line[s] at the retest bar | whether her "double confirmation" adds anything (expected: far fewer trades, likely NOT READ) |
| **TL-v2 no-timeout** | N = 20 | whether the window matters |
| **Immediate entry (= TL-v1)** | reference only, from W15-0020's books (net $775 mid, 636 trades) | whether waiting for the retest helped or hurt |
| **Each pivot size alone** | R = 3, 5, 8 | as before |

Combining retest and S/R as the primary was rejected: the combination would very likely fall below
the 150-trade floor (power failure before any result).

**Known departures, not coded:** wick-based validity; her multi-timeframe ladder; news; volatility
overlay; one instrument at a time; her 4–15% risk; her judgement of which retests to take.

---

## 3. What every run must emit

`REGISTERED_tl_v1.md` §3 unchanged, for TL-v2 and every variant, plus:

- **Counts per market and year:** qualified breaks; retest entries; failed (T3); no retest (T4);
  skipped for size; median bars break→retest; median bars held.
- **Controls — same markets, bars, fills, sizing, costs, exits:**
  - **C1** Donchian 20/10 (as TL-v0/v1).
  - **C2** TL-v1 immediate entry (reference from W15-0020).
  - **C3** **Random selection:** the pool = the retest entries of **every** §2.2 line break (weekly
    filter on, **A+ not required**), thinned at random to TL-v2's entry count per market; 1,000
    seeded draws (`np.random.default_rng([crc32(str(d)), crc32(market), R])`); p5 / p50 / p95 / **p99**.
- **Neighbour grid (27 cells, unranked):** touch buffer {0.15, 0.25, 0.35} × window W {125, 250, 400}
  × N {5, 10, 20}; net at mid per cell, share positive. (N replaces the ER axis; ER stays at q25.)
- **Seen window** (2025-09-23 →), reported only, labelled "seen — not evidence".

**Nothing is ranked. No "best cell" table.**

---

## 4. The bar to clear — TL-v2, daily, ensemble, 1% sizing, mid friction, training side

Passes only if all hold:

1. Net > $0 at mid friction ($1.25/side).
2. Both halves net > $0 (split at the median entry date).
3. drop-top-1 and drop-top-2 by market still > $0.
4. Bootstrap by market and by calendar year (2,000 seeded resamples each): net > 0 in ≥ 95%, each.
5. Beats C1 on net and net per unit of realised volatility.
6. **Beats the p99 of C3** on net. *(Raised from p95 at Ben's decision.)*
7. No single year and no single market supplies more than 50% of net.
8. Still net > $0 at high friction ($2.50/side).
9. At least **18 of 27** neighbour cells net > $0.
10. **At least 150 trades.** Fewer → **NOT READ**, not failed. **No swapping in N = 20, another base or the
    S/R variant to rescue the count.**

**Failing 5 or 6 closes the study whatever else passes.** C2 is reported beside it, not a criterion.
*(Whether the retest beats immediate entry is reported, deliberately not a criterion: Ben's approved
bar was p99 only. If TL-v2 passes yet is below TL-v1's $775, the write-up says so in the first line.)*

---

## 5. Before the backtest — no P&L in this section

| # | Gate | Status |
|---|---|---|
| G1 | Data: TL-v0 daily archive; no new data | Reused |
| G2 | **Count-only pre-flight** on the training side: qualified breaks, retest entries, failed, no retest, sizeable share, per market/year/pivot size. Runner refuses any exit price or P&L | Open (W15-0030) |
| G3 | **Holdout ledger** `holdout_tl_v2.json` in code, mutation-tested; TL-v1's ledger marked **closed-unspent** in the same commit so no window is double-spent | Open (W15-0030) |
| G4 | **Look-ahead guards**, each broken by a one-bar shift in a test: the frozen line uses only pivots confirmed by t−1; T1/T2 use bar s's own high/low/close and entry is at s+1's open; S/R clusters use pivots confirmed before t | Open (W15-0030) |
| G5 | Engine reuses `strategy/tl_v1` signals and `strategy/tl_v0/sim.py`; TL-v1 and TL-v0 tests stay green | Open (W15-0030) |

**Stop rule, fixed now:** fewer than **150 TL-v2 retest entries** on the training side (all markets,
ensemble) → stop as underpowered, reported as the finding, back to Ben before any P&L. No parameter
is changed to fix it.

---

## 6. The holdout

- **Training:** 2010-06 → 2021-12-31. **Holdout:** 2022-01-03 → 2025-09-22, own ledger
  **`holdout_tl_v2.json`**, **spent once**, by TL-v2 (daily, ensemble, mid friction) **only if all ten
  criteria pass with criterion 6 at p99**. Refuses `--limit` and every narrowing flag; mutation-tested.
  All earlier ledgers are refused by name; TL-v1's is closed-unspent.
- **Overlap.** The window is the same one TL-v0-rev and TL-v1 could have spent. Neither did. If more
  than one candidate ever qualifies, all holdout results are reported together.
- **Seen window:** 2025-09-23 onward. Never scored.

---

## 7. Registered as NOT to be done

- Tuning N, buffers, W, ER percentile, S/R cluster rules, or any threshold to TL-v1's result, her
  trades, Ben's charts, or anything from 2022 on.
- Swapping in a variant or grid cell (N = 20, S/R, another base) after a result.
- Adding a target, news, pyramiding, or a second look at TL-v1's failed criteria under new names.
- Quoting gross, a variant, or a single market as the headline.
- Spending the holdout on anything but a full ten-of-ten pass.

---

## 8. Ways this could go wrong

- **Same bars, fifth look.** Even fixed parameters inherit whatever the training bars reward; p99 and
  the holdout are the guard, not a cure.
- **Too few trades.** A retest is rarer than a break; the pre-flight stop rule decides before any P&L.
- **Selection by survival.** A retest filter drops the fast runners (T4), which are often the winners.
  That is its economic cost and is reported (no-retest count).
- **Random control is weaker than it sounds** at p99 with ~1,000 draws (p99 ≈ the 10th-largest draw).
- **Costs.** More waiting means entries farther from the stop line or smaller size; sizing skips are counted.
- **Her judgement not coded**, as TL-v1 §8.

---

## 9. Multiplicity budget

One primary hypothesis (retest), one reported variant family (S/R, N = 20, each pivot size), one
holdout spend. This is **an exception** to the trend-line line's "no registrations left" (TL-v1 §9),
granted by Ben's decision above. **No further trend-line registration after this one.**

---

## 10. A prediction, written down now

**TL-v2 keeps roughly 30–55% of TL-v1's ~636 entries (about 200–350 trades). Win rate rises a few
points, net per trade rises slightly, but total net does not beat the p99 of random selection
(criterion 6), and it is not better than immediate entry after friction on the larger sample of
breaks. The most likely reading is *waiting for the retest removes the best runners about as often as
it removes the worst entries*.** The S/R variant most likely falls below 150 trades. I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0029** — this registration; Ben commits it.
- **W15-0030** — build engine, guards, holdout ledger, count-only pre-flight (Build & test chat).
- **W15-0031** — backtest, training side, Result doc (runs on Ben's PC).
- **W15-0028** — Ben commits the TL-v1 POST-RUN note (still open).
- **W15-0027** — CL 4-hour variant of closed TL-v1: keep or drop (recommend drop).

## Amendment 1 (PRE-RUN, 2026-09-30, W15-0033) -- cost basis switched to IBKR; before any TL-v2 P&L exists

Ben, 2026-09-30: *"please use the IBKR costs as that will be the broker i'm using"*. Only the G2 count pre-flight can exist for this study (sec 5); no exit price or P&L has been computed. This replaces "friction $0.50 / $1.25 / $2.50 per contract per side + one tick on every stop fill" everywhere in this file (sec 2.1, 4 criteria 1 and 8, controls C1-C3, the grid, the 27 neighbour cells):

- **Levels:** low = IBKR all-in fee, mid (headline) = fee + 1 tick, high = fee + 2 ticks, per contract per side, on every fill; the separate stop-fill tick is dropped (no double count).
- **Fees and ticks:** the 12-market table in `REGISTERED_crudele_3s.md` Amendment C (`strategy/futbt/costs_ibkr.py`), vehicles as TL-v0 (ES via MES, CL via MCL, etc.). ES/NQ/MES/MNQ, if ever used: OTF-G Amendment 2. Sources and dates as in those amendments.
- "Mid friction ($1.25/side)" now reads "IBKR mid"; "high friction ($2.50/side)" reads "IBKR high". The bars (criteria 1-9), p99 and the holdout rule are unchanged.
- **Code:** `strategy/tl_v2` must price through `strategy.futbt.costs_ibkr`, not TL-v0's flat $0.50 / $1.25 / $2.50. The Build & test chat checks this before G5 closes.
- For comparison only, the TL-v1 result re-quoted at IBKR is in `Claude outputs/w15_0033_requote_ibkr_20260930.txt` (v1 ensemble: $775 old mid -> $606 IBKR mid).

## Amendment 2 (PRE-RUN, 2026-09-30, W15-0030) -- coding choices where sec 2.2-2.3 are silent; written before the pre-flight is run and before any retest count exists

No rule, number or bar above changes. These fix how the registered text is coded so the count-only pre-flight and the backtest read one reading. Code: `strategy/tl_v2/retest.py` (docstring C1-C5), `strategy/tl_v2/signals.py`, `strategy/tl_v2/costs.py`.

- **C1 One live setup per market.** While a setup is pending, another qualified break in the SAME direction is ignored and counted ("ignored_pending"); the first setup keeps its frozen line. (An opposite qualified break is an opposite raw break: it kills the pending setup by T3 and starts its own.) Consequence, reported not corrected: N = 20 can start fewer setups than N = 10, because a longer-pending setup blocks a later break.
- **C2** On a bar where the opposite raw break and a retest coincide, T3 wins: no trade.
- **C3** A bar whose close is through the line (close < line - 0.10 x ATR for a long) fails the setup even if no retest bar came before it.
- **C4** A retest on the last available bar cannot be filled: counted "open_at_end", not an entry.
- **C5 S/R zone (sec 2.3).** Pivots of the SAME KIND as the pivots that drew the broken line (highs for a resistance break, lows for a support break), L = R = 5, confirmed before t, pivot bar in the 250 bars before t. A zone = at least 2 such pivots within 0.25 x ATR[t] of each other; it passes if its mean is within 0.5 x ATR[s] of the frozen line at the retest bar. Any qualifying zone passes. The S/R variant only FILTERS the T5 entry (the first retest bar); it never creates an entry and a setup whose first retest bar has no zone is used up.
- **Frozen line.** The line at t is TL-v1's (built from pivots confirmed by the close of t, as TL-v1's code and cleared G5 do; this file's G4 wording "confirmed by t - 1" is read the same way: nothing after t enters). Slope = (line[t] - the anchor pivot's price) / (t - A's bar), projected forward. ATR for T1-T3 is the repo's ATR(14) at bar s.
- **Weekly filter** is applied at the break bar t (part of "qualified", sec 2.1) and not re-applied at the retest bar.
- **Entry stop** is TL-v1's v0-rev safety line as of the retest (signal) bar; sizing, 1% of $22,129 fixed equity, zero contracts = skip, counted.
- **Pre-flight (G2) definitions.** "Retest entries" = T5 signals (setups that reach a retest bar with a following bar to fill on), all 12 markets x pivot sizes 3/5/8, N = 10; this is the number the 150-entry stop rule reads. "Sizeable" = integer contracts >= 1 at 1% of $22,129 (ensemble sleeve 1/3 risk, and alone at full risk), using the stop known at the signal bar and the next open as the fill; no later bar is read.
- **Costs** are Amendment 1's, implemented in `strategy/tl_v2/costs.py` from `strategy.futbt.costs_ibkr`; TL-v0's flat friction and stop-fill tick are not used anywhere in `strategy/tl_v2`.

## Amendment 3 (PRE-RUN, 2026-09-30, W15-0049) -- how the backtest layer codes C3, the grid, criteria 6/10 and the runner gate; written before the pre-flight is run and before any TL-v2 P&L exists

No rule, number or bar above changes. Code: `strategy/tl_v2/controls.py`, `report.py`, `run.py`.

- **C3 pool.** Per market and pivot size R: the retest ENTRY signals (T1-T5, N = 10, buffer 0.25) of every sec 2.2 line break with the weekly filter ON and A1-A3 OFF, from the same scan TL-v2 uses. Amendment 2 C1 (one live setup) applies to that scan too, so a non-A+ break can occupy the slot an A+ break would have used; TL-v2's own entries are therefore not guaranteed to be a subset of the pool. The report prints how many are.
- **C3 count.** n = TL-v2's own retest entry signals for that market and R (matched on signals, not filled trades, since an entry inside an open position is ignored by the simulator). Draw d picks min(n, pool) signals without replacement with `np.random.default_rng([crc32(str(d)), crc32(market), R])`, feeds them through the same simulator, sleeves (1/3 risk, fractional, $22,129) and IBKR mid costs. Result: p5 / p50 / p95 / p99 of the 1,000 totals. Criterion 6 reads p99.
- **Grid.** 27 cells = touch buffer {0.15, 0.25, 0.35} x window W {125, 250, 400} x N {5, 10, 20}, ER stays q25; the buffer moves both A1's touch buffer and T1's. The centre cell must equal the verdict book exactly (checked in tests and printed).
- **Criterion 10 / NOT READ.** Fewer than 150 trades in the verdict book (fractional ensemble): every criterion is printed "for information only" with pass/fail withheld and the verdict is NOT READ, never FAILED. Criterion 2 splits at the median entry date (as TL-v1).
- **C2 reference** is TL-v1's immediate entry re-quoted at IBKR (v1 ensemble, fractional $22,129: $606 mid, 636 trades; `w15_0033_requote_ibkr_20260930.txt`). Reported, not a criterion. If TL-v2 passes yet is below it, the first line of the verdict says so.
- **Seen window.** Sec 3 says "reported only", sec 6 says "never scored". The runner reads only training bars, so it reports the label and confirms 0 seen sessions in the sample; it does not score 2025-09-23 onward.
- **Runner gate.** `strategy.tl_v2.run` refuses to start until a full 12-market count-only pre-flight csv (`w15_0030_tl_v2_preflight_*.csv`) shows >= 150 primary (N = 10) retest entries (sec 5 stop rule). No override flag. `--holdout` and `--limit` are refused.
