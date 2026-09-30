# REGISTERED — CHARTMARK-CLONE: learning Ben's take/skip selection on CHARTMARK-v1 long candidates (CL 1H) from blind historical labels

**Committed before the candidate queue is built, before any label exists, and before any code for this line.** `PROGRAM_INDEX` §1: a hypothesis is registered before it is run. Board: **W15-0050** (item 2870871640; subitems 1–6). Handover: `claude/handover_w15_0050_clone_20260930.md`.

Amendments are marked **PRE-LABEL** (before Ben's first label), **PRE-RUN** (after labels, before the outcome run of §9) or **POST-RUN**. A rule, threshold or feature changed after an outcome has been read is a new hypothesis.

---

## 0. In plain terms

Every coded version of Ben's chart method has found his entry trigger but not his judgement: on the year Ben marked 14 trades, CHARTMARK-v1 took 250. The difference is the ~236 he skipped. This study shows Ben about 500 of CHARTMARK-v1's historical long candidates (2010–2021) one at a time, with the chart cut off before the trade, the date and the instrument hidden, and no result ever shown. He presses Take or Skip and gives a one-key reason. Claude turns the reasons into rules (or, if the rules don't match Ben well enough, a small model), freezes them, and only then runs one backtest: the rule's picks against Donchian and against dropping the same share of trades at random. If the rule's picks beat random dropping by a clear margin after IBKR costs, Ben decides whether to let it trade paper unattended.

---

## 1. Where this comes from

**Ben, 2026-09-30:** *"get the machine to trade like a human. I would very much like not to have to be in front of the PC pulling triggers as the emotion is a big factor to it."* On the plan: *"yes this sounds great."*

**Evidence the plan rests on (all training-side or seen-window; nothing from the holdout):**
- W15-0032 G6 fidelity: 250 engine fills on the TradingView year where Ben marked 14 entries; 9 of his 14 matched within one bar. The trigger was found; the selection was not. **5 of his 14 entries are not in the candidate pool at all** — see §13.
- CHARTMARK-v1 base (`claude/w15_0032_chartmark_long_backtest_RESULT_20260930.md`): 2,670 trades, gross ($3,867), net ($13,422) per 1 MCL at IBKR mid; worse than random in-session entries with the same exits.
- CHARTMARK-v2 step C (`claude/w15_0036_chartmark_v2_stepC_RESULT_20260930.md`): K1 +$533 net on 317 trades 2016–21; failed C1 and C3. Closed.
- Ben's NinjaTrader paper record ($50k → $77.6k, 10 CL, ~2 weeks to 2026-09-25): the only positive number in the program; short, unverified against luck, and made with emotion in the loop.

**Ben's decisions for this registration, 2026-09-30 23:40 (multiple-choice, his selections):**
- Skip/take reason list (§5): *"Use this list."*
- Price axis: *"Dollars from the order"* (level = 0.00; absolute price hidden).
- Sample size: *"allow me to stop and resume when i want to. That way, some days i can spend more time and some days i can spend less."* → §3.4: no fixed sittings; the stop rule is by count only.
- Sides: *"Long only now."* Shorts get their own registration only if the long clone works.

**Two corrections to the handover, made here (Claude):**
1. **The chart stops at the bar before the fill, not at the fill bar.** The fill bar's close comes after the fill; showing it would tell Ben whether the breakout held. The decision point is the close of bar t = j−1, where j is the fill bar, with the buy-stop working for bar j drawn on the chart.
2. **"Agreement ≥ 80%" is not a usable bar.** If Ben skips ~92% of candidates, a clone that always skips scores 92%. The fidelity test (§8.3) is built on his takes: how many of them the clone also takes, and how many of the clone's takes are his.

---

## 2. Hypotheses

- **H1 — Ben's blind selection (reported, not a criterion).** Among the candidates Ben labels, the ones he takes make more per trade than randomly chosen subsets of the same size.
- **H2 — Fidelity (gates which clone is used, §8).** A rule set from Ben's reason tags — or failing that, a small model on fixed chart features — reproduces his takes on candidates it did not see: take-recall ≥ 75% and take-precision ≥ 50% in cross-validation.
- **H3 — Primary.** **The CHARTMARK-v1 long engine, gated by the frozen clone, makes money after IBKR costs on 2010-06 → 2021-12, beats a 20/10 Donchian channel, and beats the 99th percentile of random gating at the clone's own take rate.**

---

## 3. Candidate pool, queue and sample

### 3.1 Pool
- CHARTMARK-v1 base long fills, training window 2010-06-06 → 2021-12-31, as produced by `strategy/chartmark` at repo commit `92d6d25` and recorded in `Claude outputs/w15_0032_chartmark_trades_base_20260930.csv` (the handover's filename was slightly off): **2,670 fills**. Per entry year: 2010 132 · 2011 230 · 2012 240 · 2013 226 · 2014 219 · 2015 223 · 2016 217 · 2017 236 · 2018 220 · 2019 246 · 2020 231 · 2021 250. (Counted from `entry_t`/`year` only.)
- **Candidate manifest** `clone_manifest_w15_0050.csv`, built by re-running the v1 engine (not by reading the trades CSV's outcome columns): `candidate_id` (fill-bar timestamp, NY), `decision_t` (bar j−1 timestamp), `decision_idx`, `level` = the buy-stop price working for bar j as held in the engine's order state at the close of j−1 (**not** `entry_px`, which can be the gap open of bar j), `year`, `daily_trend` (F1, §6). The manifest must contain exactly the 2,670 fill bars of the trades CSV (join on timestamp; mismatch = stop).
- **Outcome columns** (`exit_t`, `exit_j`, `exit_px`, `gross`, `cost`, `net`, `exit_reason`, `phase`, `bars_held`, `n_rolls`, `entry_px`) are never read by the manifest builder, the sampler, the labelling tool or the clone fit. A test asserts it (the modules load no file containing those columns).

### 3.2 Queue order (fixed before the first label)
- Strata = entry year × F1 daily trend (up/down) = 24 strata.
- Within each stratum, candidates are permuted with `np.random.default_rng([zlib.crc32(b"W15-0050"), zlib.crc32(b"CHARTMARK-CLONE")])`. Each candidate gets key = (rank within stratum + u) / stratum size, u ~ U(0,1) from the same generator; the queue is sorted by key. Every prefix of the queue is then close to proportional across years and trend states, so wherever Ben stops, the labelled set is a stratified sample.
- The queue is written to `clone_queue_w15_0050.csv`; its SHA-256 goes into the ledger (§11 G7) before the first label.

### 3.3 Repeats (consistency check, not announced to Ben)
- After every 10 new candidates, the tool shows one **repeat** of a candidate Ben labelled at least 100 queue positions earlier (chosen by the seeded generator). Repeats are rendered identically and are not marked on screen.
- The **first** label of a candidate is the one used for fitting. Repeats measure how consistent Ben is with himself — the ceiling for any clone.

### 3.4 How much labelling (Ben stops and resumes when he likes)
- There are no fixed sittings. The tool saves after every decision and resumes where Ben left off. A "sitting" = one launch of the tool to its close; the id is recorded.
- **Enough** = at least **500 unique** candidates labelled **and** at least **60 takes**, or **1,000 unique**, whichever comes first. The tool shows progress against both and says when it is enough.
- This stop rule uses **label counts only**, never outcomes.
- If Ben stops for good before "enough": fewer than **40 takes** → fidelity and the clone are **NOT READ**, back to Ben; 40–59 takes → run, reported as underpowered.
- Suggested, not enforced: short sittings (fatigue drift is measured, §8.3).

---

## 4. Blinding — what Ben sees and does not see (fixed; the tool is tested against it, §11 G3)

**Decision point:** close of bar t = j−1. Ben is deciding whether the buy-stop for bar j should be working.

**Shown:**
- **1H panel:** the last 120 bars ending at t; candles; EMA9, EMA21; the **buy-stop level as a horizontal line**; the high and low of the current and previous trading day (18:00 NY roll) as dotted lines, using bars ≤ t only.
- **Volume** sub-panel with SMA(20) of volume.
- **MACD(12,26,9)** sub-panel: MACD, signal, histogram.
- **Daily panel** above: the last 60 completed daily bars plus today's partial bar built from 1H bars ≤ t; daily EMA9 and EMA21.
- **Price axis:** dollars relative to the buy-stop level (level = 0.00), per Ben's choice. ATR(14) of the 1H series at t shown in dollars as a text line.
- **Time axis:** weekday and hour (New York) only.
- Progress (unique labelled / 500 minimum; takes / 60).

**Never shown:** date, month, year; the instrument name or contract month; absolute price; roll markers; any bar after t; the fill; the stop; any exit, P&L or outcome — not even at the end of a sitting.

**Order:** queue order (§3.2), which is shuffled in time, so neighbouring candidates are not consecutive in history.

**Undo:** Ben may undo only the decision just made, before the next candidate is confirmed. No going back further, no browsing.

**Residual leakage, stated:** famous moves may still be recognisable from shape and volatility alone. Labels and results for entries in **2014-07-01 → 2015-01-31** (the 2014 collapse) and **2020-02-01 → 2020-06-30** (the COVID crash and negative-price period) are reported separately, and a variant excludes them (V-NOFAMOUS, §9.4).

---

## 5. Label schema (Ben's list, approved 2026-09-30)

| Key | Skip reason (one required on a skip) |
|---|---|
| 1 | Against the daily trend |
| 2 | Already run too far (extended) |
| 3 | Chop / quiet (tangled EMAs, low volume) |
| 4 | Momentum weak or fading (MACD) |
| 5 | Order too far above price / risk too big |
| 6 | Scheduled event hour (e.g. Wed inventory report) |
| 7 | Other (type a few words) |

| Key | Take reason (optional) |
|---|---|
| A | Fresh momentum turn (EMA/MACD cross) |
| B | Breakout from a range |
| C | Trend continuation |
| D | Other |

Confidence 1–3 optional. Keys: **T** take / **S** skip, then the reason key, then Enter.

`labels_chartmark_clone.csv` (append-only, written after every decision): `candidate_id, queue_pos, is_repeat, label, skip_reason, take_reason, note, confidence, ms_to_decide, sitting_id, labelled_at_utc`. An undo appends a row with `label = UNDO` for that `queue_pos`; the fit uses the last non-UNDO row per `queue_pos`.

---

## 6. Chart features (fixed now; computed at t from bars ≤ t and the level L)

ATR = ATR(14) Wilder on 1H at t. H = MACD − signal (12,26,9). Daily bars close at 17:00 NY (18:00 roll); "last completed day" excludes today.

| | Feature |
|---|---|
| F1 | Daily trend: last completed daily close > daily EMA21 → +1, else −1 |
| F2 | (daily EMA9 − daily EMA21) / daily ATR(14), last completed day |
| F3 | (EMA9 − EMA21)[t] / ATR |
| F4 | H[t] / ATR |
| F5 | (H[t] − H[t−2]) / ATR |
| F6 | (L − close[t]) / ATR — how far the order sits above price |
| F7 | (close[t] − min low over t−19…t) / ATR — run-up |
| F8 | (L − EMA21[t]) / ATR — stretch above EMA21 |
| F9 | Number of sign changes of (close − EMA21) over t−19…t — chop |
| F10 | Share of bars t−9…t with volume < SMA(20) volume |
| F11 | (max high − min low over t−19…t) / ATR — range width |
| F12 | Session bucket of bar j's open (NY): Asia 18:00–01:59, London 02:00–07:59, US-AM 08:00–11:59, US-PM 12:00–17:59; plus weekday |
| F13 | Upper wick of bar t as a share of its range |
| F14 | Bars since the last EMA9/EMA21 cross, capped at 50 |
| F15 | Percentile of ATR[t] within the prior 500 1H bars |

---

## 7. What the clone may use

Only §5's labels, §6's features and the queue. **No outcome, no exit, no P&L, no future bar.** The fit chat does not open the trades CSV.

---

## 8. The clone — fit and fidelity (labels only)

### 8.1 Rules clone R (fitted first)
Each skip reason used at least **15 times** becomes one rule on the features mapped to it below. Direction is fixed; the threshold is fitted on the training fold only. Where a reason maps to several features, the one with the best separation on the training fold is used.

| Reason | Features (fires when…) |
|---|---|
| 1 Against daily trend | F1 = −1; or F2 < θ (whichever separates better) |
| 2 Extended | F7 > θ, or F8 > θ |
| 3 Chop / quiet | F9 ≥ θ, or F10 ≥ θ, or F11 < θ |
| 4 Weak momentum | F4 < θ, or F5 < θ |
| 5 Order too far | F6 > θ |
| 6 Event hour | bar j opens in a weekday × hour cell where reason 6 was used ≥ 3 times in the training fold |
| 7 Other | not coded; its share of skips is reported |

- **Threshold fitting:** for each rule, the value that maximises Youden's J (share of that reason's skips caught minus share of Ben's takes caught), over the training fold's candidates.
- **The clone takes a candidate only if no rule fires.**
- Reason 7 used on more than 25% of skips → reported as "selection partly outside the list".

### 8.2 Model clone M (only if R misses the fidelity bar)
- L2 logistic regression on standardised F2–F11, F13–F15, F1 and F12 one-hot.
- Regularisation C ∈ {0.01, 0.1, 1} and the decision threshold (maximising F2 score, which weights recall on takes twice as heavily as precision) are chosen by inner 5-fold CV inside each training fold. Labels only.
- **M-GB** (reported, never selected): scikit-learn HistGradientBoostingClassifier, max_depth 3, 100 iterations, same features and threshold rule.

### 8.3 Fidelity scoring
- **5 × repeated stratified 5-fold cross-validation** over unique labelled candidates (stratified by label), seeds `crc32("W15-0050-cv") + repeat`. Out-of-fold predictions are pooled.
- **Headline measures:** **take-recall** = share of Ben's takes the clone also takes; **take-precision** = share of the clone's takes that Ben took. Also reported: overall agreement, Cohen's κ, the confusion table, and each rule's hit counts by reason.
- **Bar: take-recall ≥ 75% and take-precision ≥ 50%.**
- **Ceiling:** Ben's own consistency on repeats = share of first-time takes he took again. If it is below 75%, the recall bar becomes Ben's consistency (a clone cannot be held to more than Ben agrees with himself). This depends on labels only.
- **Order, fixed:** R is scored first. R meets the bar → **R is the clone**; M is not fitted. R misses → fit M. M meets the bar → **M is the clone**. Both miss → **M is the clone, marked "fidelity not met"**. The backtest runs either way; the deployment decision (subitem 6) carries the mark.
- **Also reported, labels only:** take rate by year, trend stratum, session and sitting position (fatigue drift); take rate on the famous windows vs the rest; ms per decision.

### 8.4 Freeze
The final clone is refitted on all unique labels and written to `clone_frozen_w15_0050.json` (type R or M, thresholds or coefficients, feature code hash, label-file SHA-256, queue SHA-256, git commit). The file is committed **before** §9 runs. The outcome runner refuses to start without it and checks the hashes.

---

## 9. The outcome run (one run, after the freeze)

### 9.1 Costs and sizing
IBKR Pro (v1 Amendment A.3; W15-0033): MCL $0.77 per side + 0 / 1 / 2 ticks (low / **mid = headline** / high); CL $2.37 + same ticks. 1 MCL headline, 1 CL reported, $10,000 account framing as v1.

### 9.2 H1 — Ben's own picks (reported)
- On the unique labelled candidates: net of Ben's takes, each as the v1 trade actually recorded, vs **10,000 random subsets of the same size** drawn from the labelled candidates (seeded). Percentile reported; the average net of takes vs skips reported.
- The same for the clone's picks on labelled candidates (**V-BENLAB**).
- No pass/fail. A result below the random median is written as "no better than chance on these bars".

### 9.3 H3 — the gated engine (headline)
- **Gate:** the CHARTMARK-v1 base engine runs unchanged over the training window. At every bar close t where v1 would have a buy-stop working for bar t+1, the frozen clone scores the §6 features with that level. **Take** → the order works in bar t+1 as normal. **Skip** → no order in bar t+1; v1's order state (level re-set, E3 timeout count, E5 re-arm) otherwise carries on as if bar t+1 did not fill. The clone's decision on bars that would not have filled has no effect, so this matches the labelling (decisions at fill bars only).
- Skipping changes the path (the engine is flat when v1 would have been in a trade), so the gated run can produce fills that are not among the 2,670. They are scored like any other.
- **Controls, same bars, fills and costs:**
  - **C1** Donchian 20/10 long (v1's C1 code and session filter).
  - **C3** random gate: at each would-be fill, take with probability p_y = the clone's take rate in year y from the headline run; 1,000 draws, `np.random.default_rng([zlib.crc32(str(d).encode()), zlib.crc32(b"CL-clone"), N])`; p5 / p50 / p95 / **p99**. This is the control that matters: dropping trades at random changes the numbers too.
  - CHARTMARK-v1 ungated beside it.
- **Emitted, per year and in total, headline and variants:** would-be fills, takes, skips, trades, wins/losses, gross, costs, **net at low/mid/high**, per 1 MCL and 1 CL, average win and loss, largest loss, worst losing run, max drawdown, both halves, exits by type, and a sample of 20 real trades (entry/exit time and price, net $). Negative figures in brackets.

### 9.4 Variants (fixed now, reported, never selectable, cannot spend the holdout)
| Variant | Change |
|---|---|
| V-OTHER | The other clone type (R if M is headline; M if R is headline and M was fitted anyway for this report after the freeze — fitted on labels only, frozen with the headline) |
| M-GB | Gradient-boosting gate (§8.2) |
| V-EXIT2 | CHARTMARK-v2 exits (§2.4–§2.5 of that registration: $0.60 backstop, EMA21 two-breach rules) instead of v1's |
| V-NOFAMOUS | Entries in 2014-07 → 2015-01 and 2020-02 → 2020-06 excluded |
| V-BENLAB | §9.2: clone vs Ben on labelled candidates only |

**Neighbour grid (27 cells, unranked):** v1's grid (E1 lookback {2,3,5} × P1 arming {0.75, 1.0, 1.5 A₀} × stop lookback {3,5,8}) with the frozen clone as the gate.

---

## 10. The bar to clear — headline gated engine, training 2010-06 → 2021-12, 1 MCL, IBKR mid

Passes only if all hold:
1. Net > $0 at mid.
2. Net > $0 at high friction.
3. Both halves net > $0: 2010-06 → 2015-12 and 2016-01 → 2021-12.
4. Drop-top-1 and drop-top-2 calendar years still > $0.
5. Bootstrap by year (2,000 seeded resamples): net > 0 in ≥ 95%.
6. Beats C1 on net and on net ÷ standard deviation of daily net.
7. **Beats the p99 of C3** (random gating at the clone's take rate) on net.
8. No single year > 50% of net. *Flagged as a known failure mode of trend methods:* if this is the **only** failure, the result reads "PASS except concentration"; the holdout is not spent, and Ben may still choose forward paper (new data) at subitem 6.
9. At least 18 of 27 grid cells net > $0.
10. At least **100 trades**. Fewer → NOT READ.

**Failing 6 or 7 closes the study** whatever else passes. A variant passing where the headline fails is a new registration, not a rescue.

---

## 11. Gates before any outcome is read (no P&L in this section)

| # | Gate | Who |
|---|---|---|
| G1 | Data: CL 1H GLBX archive (W15-0002), cut before 2022-01-01 before resample/back-adjust, as v1 | Build & test |
| G2 | Manifest: re-run of v1 reproduces all 2,670 fill timestamps; levels taken from order state; a test proves no module opens a file with outcome columns | Build & test (sub 2) |
| G3 | Blinding tests: no rendered text or metadata contains a year, month, date or "CL"/contract code; the last drawn bar is t; the price axis is relative; **truncation invariance** — mutating every bar after t leaves the rendered image byte-identical; a one-bar-shift mutation must change it | Build & test (sub 2) |
| G4 | Labels file append-only, one row per decision, sitting id, undo rows; resume picks up at the right queue position; repeats inserted per §3.3 | Build & test (sub 2) |
| G5 | Feature look-ahead guards: truncation invariance on F1–F15; a one-bar shift must break each test | Build & test (sub 4) |
| G6 | Gate parity: the gated engine with an always-take clone reproduces v1's 2,670 trades exactly; always-skip → 0 trades | Build & test (sub 5) |
| G7 | Ledger `clone_ledger_w15_0050.json`: queue SHA-256 before the first label; label-file SHA-256 and `clone_frozen` hash before §9; the §9 runner refuses a second run | Build & test (subs 2, 4, 5) |

---

## 12. The holdout

- Training 2010-06 → 2021-12-31. **Holdout 2022-01-03 → 2025-09-07**, own ledger `holdout_chartmark_clone.json`, **spent once, by the headline clone only, only on a ten-of-ten pass.** The clone is applied mechanically — **no holdout candidate is ever shown to Ben.**
- Trades with entries in 2025-02-19 → 2025-03-04 and 2025-06-22 → 2025-07-03 excluded from scoring (v1 Amendment A.2; Ben has seen those charts).
- Seen window 2025-09-08 → never scored. CHARTMARK-v1's holdout was never touched and is not touched here.

---

## 13. Registered as NOT to be done

Showing Ben any outcome of any candidate before §9; labelling candidates from 2022 onward; letting outcomes influence the stop rule, the queue, the features, the rule mapping or the model; adding features after the first label; re-fitting after §9; quoting H1, a variant, the labelled subset or gross as the headline; spending the holdout on anything but a full pass.

---

## 14. Ways this could go wrong

- **Few takes.** If Ben takes ~6% (as 14 of 250 suggests), 500 labels give ~30 takes — too few to learn from; §3.4 extends to 60 takes or 1,000 labels. Even 60 takes make recall estimates rough (±10 points).
- **The pool misses a third of Ben's entries.** On the seen year 5 of his 14 entries were not v1 fills. The clone can only choose among v1's candidates; whatever made those 5 is not tested here.
- **v1's exits lose before costs.** The clone changes entries only. If Ben's edge is in his exits (his ratcheting stop), the clone cannot show it. V-EXIT2 is one check; a clone of his exits would be a separate line.
- **Off-chart edge.** News, tape feel and the day's headlines are hidden or absent. If his paper profit came from those, the clone won't have it; §9 shows it.
- **Replay Ben vs live Ben.** Labels are Ben with no position open and no P&L ticking — the unemotional trader he wants to build, but not the trader who made the paper P&L. A feature, and a stated difference.
- **Recognition.** Shapes of famous moves may leak the future; §4 and V-NOFAMOUS are the check.
- **Relative price axis.** Round-number levels ($50, $100) are hidden; if Ben uses them, some of his reasoning is lost. His choice, recorded.
- **Claude's feature coding.** §6's features and §8.1's mapping are Claude's translation of Ben's reasons. Reason-7 share and the per-rule hit counts show where the translation is thin.
- **Fatigue and drift.** Take rate by sitting position and by labelling date is reported.
- **Path dependence.** The gated run creates fills that were never labelled; they come from the same engine and are scored by the same frozen clone.

---

## 15. Multiplicity budget

One labelled set; one fit path fixed in advance (R → M); labels read by the fit once (inside CV) and once for the final refit; **one outcome run** covering H1, H3, controls, variants and grid; variants reported, never promoted; one holdout spend. Tuning on labels is allowed (thresholds, C, decision threshold) because labels contain no outcome.

---

## 16. Prediction, written now

- Ben takes **8–20%** of candidates (more than 14 of 250, because each candidate is put in front of him deliberately); consistency on repeated takes **60–80%**.
- The rules clone meets the fidelity bar: about **40%**.
- H1: Ben's blind takes above the random 95th percentile: about **one in three**.
- H3: gated engine **250–550 trades**, net at mid between **($3,000) and +$2,000** per MCL; beats C3 p99 about **one chance in five**.
- Most-used skip reasons: 3 (chop) and 1 (against daily trend).

I'd be glad to be wrong.

---

## Next steps (board)

- **W15-0050 sub 1** — Research & spec chat: this registration, committed. **Done.**
- **W15-0050 sub 2** — Build & test chat (Sonnet / Medium): manifest + queue + repeats + labelling tool, gates G1–G4, G7 (queue hash); delivered to `D:\Trading\Claude outputs`; commands for Ben on sub 3.
- **W15-0050 sub 3** — Ben: label until the tool says enough (§3.4); stop and resume any time.
- **W15-0050 sub 4** — Build & test chat (Sonnet / High): features + G5, fit R (then M if needed), fidelity report, freeze.
- **W15-0050 sub 5** — Build & test chat (Sonnet / High): G6, the one outcome run → Result doc.
- **W15-0050 sub 6** — Ben: unattended forward paper or close.
