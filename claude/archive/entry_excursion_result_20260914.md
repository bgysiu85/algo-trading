# Is there anything for an exit to capture? — 2026-09-14

`python -m common.entry_excursion --strategy mcl` (19.5s, 32 workers) · raw:
`var/reports/entry_excursion_mcl.txt` · bundles `20260914g`–`l`

## 0. The disagreement this was built to settle

Ben, 2026-09-14: *"Only the right entry can give you the right exit. No matter
how great your exit strategy is, if the entry is bad, we will not be
profitable."*

Three measurements already supported the first half — `entry_features` 0 of 11
families; `run_signal` 0.108% base rate with a 1.94x best predictor;
`universe_lift` best entry feature 2.34x against the screen's 1.35x. What was
unmeasured was the step after it: `mfe_exit_mcl.txt` found the median trade
exits BELOW its entry despite having traded above it, so the post-entry high IS
above the entry — but nobody had asked how far.

Pre-registered before the run: the bar is friction. A trade whose best moment
never covered its own round trip could not have been profitable under any exit.

## 1. The headline verdict fired, and it was the wrong question

551 sessions, 6,170 symbol-days, **3,955 trades** — the same book `pit_strategy`
reports, cross-checking to **−$10.52/trade** from an entirely separate code path.

| in-trade, per 100 shares | p10 | p25 | p50 | p75 | p90 | mean |
|---|---:|---:|---:|---:|---:|---:|
| MFE (up) | $0.00 | $4.00 | **$14.00** | $36.01 | $79.00 | $31.77 |
| MAE (down) | $4.00 | $8.14 | $16.00 | $31.00 | $56.98 | $27.42 |

27.4% of trades never covered friction at any moment. Median MFE $14.00 against
$4.26 — 3.3x — so the pre-registered rule returned **THE EXIT IS WORTH
ATTACKING**.

**That verdict is withdrawn as under-specified.** It took a median over a
bimodal book and treated it as one population. The registration asked only
whether there was room for an exit to matter; it never asked whether the room is
where the losses are.

## 2. The split is the finding

Per trade — not per percentile, because the trade at the median of MFE is not
the trade at the median of MAE:

| | trades | med MFE | med MAE | **+30 bars** | to close | bars held | per trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| drawdown first | 1,156 (29.3%) | $38.12 | $8.00 | **$44.00** | $62.00 | 7 | **+$19.13** |
| move first | 2,794 (70.7%) | $8.46 | $21.00 | **$15.30** | $31.00 | 3 | **−$22.73** |

**MCL already makes money on trades that dip a little then run.** It loses on
trades that pop, fade through the trail, and stop out — and that is 70.7% of the
book.

On an equal 30-bar window from each trade's own entry, the losing group had
**$15.30** available and the winning group **$44.00**. Nearly 3x, and the
difference is a property of the situation entered, not of how it was exited.

**Read the +30-bar column, not `to close`.** `to close` runs to the session's
last bar, so a trade stopped out after 3 bars is handed 108 bars of remaining
tape and collects the largest figure for it. On that uncontrolled measure the
losing group reads $31.00 and looks like a move we were cut out of; on equal
ground it is $15.30. The bias is the one `dip_entry.excursions` already warns
about, one level out.

## 3. What this says about the argument

**Ben's position is the better-supported one.** The deficit is concentrated in a
population where roughly $15 is available over the next half hour — 3.6x
friction, requiring a near-perfect exit to bank meaningfully — while the
profitable population sits at $44 and is already being captured at 87% of its
in-trade peak.

The exit is leaving something on the losing group ($8.46 captured of $15.30
available). It is not leaving enough to change the sign.

**The caveat that keeps this from being finished:** "drawdown first" is defined
by what happens AFTER entry. It is not an entry rule, it is hindsight. Whether
anything observable AT the entry bar predicts which group a trade lands in is
now the single most valuable open question in the project.

## 4. Why that question is more tractable than the ones before it

`run_signal` failed against a **0.108%** base rate. This label is **29.3%**.
`entry_features` tested 22 features against trade P/L — a noisy continuous
target; this is a clean binary one with a mechanical definition, and the
machinery to test it already exists.

That is not a promise it will separate. `entry_features` cleared 0 of 11
families on MCL's entries, and the honest prior is that it clears 0 again. But
it is a different target on the same data, it costs one run, and a negative
result closes the entry question as firmly as a positive one opens it.

## 5. Three defects found on the way

1. **A different population than `pit_strategy`.** 3,521 trades against 3,955 —
   the module read a single day's slice while `pit_strategy` prepends a warm-up
   session, and MACD is an EMA with unbounded memory. Under a caveat that said
   *"same tape and warm-up as pit_strategy"*. Fixed, plus a printed count of
   trades produced against trades measurable, because `measure()` returning None
   is DROPPED — the symptom is a quietly smaller book, not a crash.
2. **Marginal percentiles read as a pair.** I wrote "the median trade goes $16
   against and $13 for" — describing no trade that exists. Two values that look
   comparable and are not, committed while arguing about that exact failure.
   The per-trade ordering split replaced it.
3. **A window-length confound in `to close`.** Above. Controlled with a fixed
   30-bar horizon, registered as a module constant with its reasoning beside it,
   and a test asserting the reasoning is there — a horizon chosen after seeing
   the split is a parameter fitted to the answer.

Also applied: `portal_bridge_handover_20260914.md` §9's lesson. Every test here
built a `SimpleNamespace` trade, which is more permissive than the real
`Trade` — so a renamed field would have passed the suite and produced a smaller
book at runtime. Two tests now build each engine's own `Trade`.

2,176 tests passing.

## 6. Next

1. **Is the dip-then-run group identifiable at entry?** `entry_features`
   machinery, new binary label, 29.3% base rate. One run. Pre-register that the
   honest prior is another null.
2. If it separates: an entry filter, registered and validated, then `pit_delta`.
3. If it does not: the entry is not identifiable from minute OHLCV, and the
   question becomes what data would make it so — float, short interest, halts,
   news, Level 2 — or whether this game is playable at all on this data.
4. `--strategy mc5` has never been run through this module.
