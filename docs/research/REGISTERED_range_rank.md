# REGISTERED — H-B3: take a signal only if the name ranks top-N by session range at that minute

From `claude/handover_luck_vs_edge_and_entry_quality_20260917.md` Part B, B3.
`universe_lift` found that ranking the whole archive pull on within-session
`range_pct` at a cutoff lifts the run rate **14.85× at top 5, 3.18× at top 50**
— the separation is in the first handful. This is name selection, not bar
selection: B0's table of failed filters is about the entry bar's features, and
this is a different lever. The caveat carried from `won_vs_lost_20260916.md`:
`range_pct` describes Ben's selection and did NOT separate his winners from
losers. **Committed before the code that runs it exists.**

## 1. The rule, exactly

At the bar on which the engine would otherwise take an entry, the name is
ranked among the point-in-time names **visible at that minute** on that
session — every record of the session with `first_seen ≤ t` — on the running
`range_pct` as `universe_lift.measure` defines it: **the mean of
(high − low) / close over the session's bars printed so far**, from 04:00 ET,
in percent. The entry is taken only if the name's rank is **≤ N**. Ties rank
equal (a tie at N is inside the cut). Nothing about the exit changes.

**The competitor set is the watchlist, not the tape.** Ranking against every
symbol in the archive slice is what `universe_lift` measured and it is not
implementable live: the trader has bars for the names the screen surfaced and
for nothing else. Ranking within the surfaced names is what a live trader could
do at that minute with the data it has. It follows — and is said now — that on
this universe (a median of ONE name by 04:30, 9.1 candidates a session) the
gate is **inert wherever fewer than N names are visible**, and the report
prints, for every signal, whether the gate *could* have bound (at least N
competitors visible). A gate that never fires is indistinguishable from its
absence; the share of signals where it could fire is printed beside every
number so that NOTHING cannot be read as "selection does not help" when it
means "there was nothing to select from".

**Mechanism.** A new engine parameter on both `mcl.backtest_session` and
`mc5.backtest_session`: `entry_gate: pd.Series | None`, a boolean series on
the bar index that is AND-ed with the rule's own entry signal (unlike MCL's
`entry_bars`, which replaces it). `None` is bit-identical to the engines as
published, pinned by a test. Signal-ordinal, as H-B1: a gated-off entry leaves
the engine flat, and later bars fire as the rule says. Under a gate the skip
book is not a subset of the baseline, and the cascade count is printed.

## 2. Cells and controls

Six books from one `run_day` per session, same tape, warm-up, floor, `QTY =
100`, published configurations:

| book | `entry_gate` | role |
|---|---|---|
| MCL, MC5 | None | baselines; MCL must count 3,955 |
| **MCL-top3, MC5-top3** | rank ≤ 3 | **the registered cell, N = 3**, the handover's example, fixed here |
| MCL-top1, MC5-top1 | rank ≤ 1 | **reported, not registered** — the strongest form of the same rule, declared now so it is not a post-hoc search; its verdict is printed and does not decide |

No other N is run. Universe `var/state/screen_pairs_pit.json`. All-or-none
per symbol-day. Outcome per trade: engine `net` less friction at $1.00 /
**$4.26** / $8.92. Halves cut once at the median session run. Per symbol-day
divides by the symbol-days the run covered, the same number for every book.

## 3. Readings — fixed now, and two added after H-B1

For **top3 against its baseline**, per strategy, at $4.26, all five of:

1. **Both denominators improve, with a margin on per trade.** Δ per trade
   **≥ $4.26** (`MIN_MARGIN`, one round trip, as v5 used it) **and** Δ per
   symbol-day > 0. A sign disagreement between the two deltas is a refusal.
   H-B1's amendment A is why the margin is here: +$0.03 a trade satisfied the
   old form.
2. **Both halves**, each on both denominators, > 0.
3. **Drop-top-3 on the level and on the delta**, as H-B1 §3 item 3.
4. **Cluster bootstrap on the delta** ≥ 0.95, as H-B1 §3 item 4.
5. **The abstention control.** Remove from the baseline, uniformly at random,
   the same number of trades the gate removed (baseline trades − gated-book
   trades, floored at zero), 2,000 draws at SEED 20260916. The gate's Δ per
   trade must exceed the **95th percentile** of the random draws' Δ per trade.
   This is the null for *trades less*: on a losing book random removal moves
   per symbol-day up and per trade not at all, and a filter that cannot beat
   it is not selecting names, it is declining trades. The random draws' Δ per
   symbol-day is printed beside the gate's so the abstention share of the
   total is visible.

All five → **PASSES** for that strategy, a candidate for the holdout under its
own registration, not a rule to ship. Fewer → **NOTHING**, naming which.

Printed every time: entries removed (baseline − gated, and the exact count of
baseline trades whose entry bar the gate refused); losses avoided and winners
lost among those refused trades; top-10 baseline trades absent from the gated
book; the cascade (gated-book entries the baseline lacks); and **the share of
baseline entries at which the gate could bind**, with the distribution of
visible-name counts at signal time.

**Written before the run.** On a watchlist with a median of one name, I expect
the top-3 gate to bind on a minority of signals, mostly after 07:30 and on hot
sessions, and to read NOTHING on item 1's margin for both strategies. I expect
top-1 to remove far more and to fail the abstention control, because
`range_pct` did not separate Ben's winners from losers. If top-3 passes, the
first thing to check is item 5, then the binding share: a pass carried by the
few sessions with a deep watchlist is a pass on the hot-day regime, which is
Part A's question, not this one.

## 4. What would make this run wrong

- Ranking against the tape rather than the visible names.
- Competitors not masked by `first_seen ≤ t` — a name the screen had not
  surfaced yet cannot be in the list the trader ranks.
- `range_pct` computed from any bar at or after the signal bar's close, or
  from warm-up sessions. Bars strictly before the signal bar, session-day
  only.
- A gate that never fires, unremarked: the binding share is printed and a
  share of zero is a defect.
- N changed after the run; a third N run "to see".
- The MCL baseline not counting 3,955.

## 5. What this cannot settle

- Not out of sample; `holdout.json` stays shut.
- The concurrency cap is not modelled; this gate is the ranking rule the cap
  would need (§7 item 15) and that combination is B2/B5, not this.
- `range_pct` is one of six criteria `universe_lift` fixed; `dollar_vol` and
  `gap_pct` are not run here. Each would be its own registration.

# AMENDMENT A — 2026-09-17, PRE-RUN. Re-based on the ITCH v2 universe.

Run once more on `screen_pairs_pit_itch_v2.json` with XNAS.ITCH bars
(`--pairs var/state/screen_pairs_pit_itch_v2.json --dataset XNAS.ITCH`,
output `range_rank_itch.txt` / `range_rank_itch_trades.csv`). The running
range is read from the ITCH bars, so the ranks can move where BASIC's 08:00
prints moved a name's high; that is the one mechanism by which this could
read differently.

- Same rules, same readings, same thresholds, same seed. Nothing in the
  verdict is re-tuned; the universe file and the bars change and nothing else.
- The population check compares MCL's count against the number published
  for THE FILE run (3,908 on v2), never against the BASIC 3,955.
- Prediction, written before the run: the verdict stands (NOTHING for both,
  and for H-B1 NOTHING / REFUSED). On the ITCH v2 books every trade still
  loses $8–9 on average, so a total-based reading rewards abstention exactly
  as it did on BASIC, and the abstention control is what decides. If a gate
  clears the control here having not cleared it on BASIC, that is a tape
  effect on the gated trades and wants the same reading on the hybrid
  post-change universe before it is believed — it is not a pass.
- Reported beside the BASIC figures, not in place of them. The BASIC result
  docs stay as written and are not edited.
