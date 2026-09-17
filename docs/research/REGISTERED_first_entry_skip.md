# REGISTERED — H-B1: skip the first entry of each symbol-day

From `claude/handover_luck_vs_edge_and_entry_quality_20260917.md` Part B, B1.
Live paper, 09-09..09-16, all strategies: the first entry in a name-day lost
(812.80) over 37 trades at 13.5% wins; later entries in the same name-day made
50.96 over 97 at 25.8%. The handover says what that table is — suggestive, in
sample, six sessions, and circular: a second entry only exists if the name
kept signalling after the first, which is partly conditioned on the move
continuing. **Committed before the code that runs it exists.** Nothing on the
point-in-time universe has been looked at through this rule.

The same run carries a second, descriptive table asked for by
`handover_time_of_day_20260916.md`; §4 registers what it is and what it is
not, so that its one named cell cannot be quoted afterwards as a discovery.

## 1. The rule, exactly

**`skip_entries = 1`**, a new engine parameter on both `mcl.backtest_session`
and `mc5.backtest_session`, default `0`, and `0` bit-identical to the engines
as published (pinned by a test, as `not_before` is).

The first entry the engine **would otherwise have taken** in the session — a
bar on which the rule fires while flat, at or after the `first_seen` floor,
inside the price band, with a size of at least one share — is passed over and
no position is opened. The engine then runs exactly as the rule says: the next
such bar opens a position, and every later entry, exit, trail and flatten is
the published engine's. This is the **signal-ordinal** form: it is what a live
trader would do, it is implementable in real time with no look-ahead, and it
has a consequence that must be read into every number below — **the skip
book's entries are not a subset of the baseline's.** With the first position
never opened, bars that the baseline was in a trade for become live signal
bars, so the skip book's first trade need not be the baseline's second.

A band-refused signal is not an entry and is not counted; the skipped entry is
therefore, bar for bar, the baseline's first trade of that symbol-day.

**The accounting form is reported beside it, and does not decide anything.**
"Baseline book minus each symbol-day's first trade" is how the live table was
built, it is a pure filter on one book (no re-run, no cascade), and it is the
only form under which "which of the baseline's top-10 winners does the rule
remove" is exactly answerable. It is printed under its own heading, labelled
as the live table's construction, and the verdict does not read it. It will
look better than the signal-ordinal form wherever the cascade costs money; if
it looks better by a lot, that gap is the circularity the handover named,
measured.

**The variant is named and not run.** "Skip until the name has made a new
session high after its first signal" is a different rule with a parameter in
it. If H-B1 reads NOTHING the variant is not tried on the same run; it would be
its own registration.

## 2. Cells and controls

Four books from one `run_day` per session, same tape (`XNAS.BASIC` archive
slices), same warm-up frames, same `first_seen` floor, `QTY = 100`, engines as
`pit_strategy.engine("mcl")` / `("mc5")`:

| book | engine | `skip_entries` |
|---|---|---|
| MCL | `strategy.mcl.mcl`, LIVE config | 0 |
| **MCL-skip1** | same | **1** |
| MC5 | `strategy.mc5.mc5` | 0 |
| **MC5-skip1** | same | **1** |

Universe: `var/state/screen_pairs_pit.json`, 6,170 symbol-days over 551
sessions. Population check: MCL's book must count **3,955** trades
(`entry_shares.PUBLISHED_TRADES`) or the report says so in capitals and the MCL
line is not quoted as the published figure. All-or-none: a symbol-day that
raises in any of the four calls is dropped from all four.

Outcome per trade: the engine's `net` (IBKR tiered commission in) less a
round-trip friction, at $1.00 / **$4.26** / $8.92. The verdict reads $4.26.
Halves cut once, at the median session of the sessions run, all books split
on that date.

## 3. Readings — fixed now

Two verdicts, one per strategy, same form; a rule is adoptable for a strategy
only where it passes for that strategy. For **skip1 against its baseline**, at
$4.26, all four of:

1. **Both denominators improve.** Δ per trade > 0 **and** Δ per symbol-day > 0,
   where per symbol-day divides by the symbol-days the run covered (the same
   number for every book). A sign disagreement between the two deltas is a
   **refusal** — reported as such, not read as a partial pass.
2. **Both halves**, each on both denominators, > 0.
3. **Drop-top-3, on the level and on the delta.** Level: the skip book's net
   after dropping its own top 3 trades exceeds the baseline's net after
   dropping its own top 3. Delta: after dropping the 3 symbol-days whose
   delta (skip net − base net) is largest, the remaining delta is still > 0.
4. **Cluster bootstrap on the delta.** Per symbol, the list of its
   symbol-day deltas; `common.breadth.cluster_bootstrap` at RESAMPLES 2000,
   SEED 20260916; the share of resampled total deltas above zero ≥ 0.95
   (`BOOT_MIN_P`). Read on totals; the per-trade column of the bootstrap is
   not read (it carries the total's sign and cannot fail independently).

All four → **PASSES** for that strategy, and it becomes a candidate for the
holdout under its own registration — not a rule to ship. Any fewer →
**NOTHING**, naming which failed. Two more numbers are printed every time so
the cost is visible whichever way it goes: how many of the baseline's top-10
trades at $4.26 (keyed symbol, date, entry time) are absent from the skip
book; and, under the accounting form, the removed first trades split into
losers avoided and winners lost, each summed.

**Written before the run:** I expect the accounting form to read better than
the signal-ordinal form for both strategies. I expect the skip to cut the
loss on the `≤ 1 minute` trades the handovers listed and to cut the
concentrated winners with them, and my prior for the signal-ordinal reading
on MCL is NOTHING on criterion 3 or 4. If it passes, the second thing to check
is item 3's delta line, because the live record says the effect, if any, is
carried by a handful of names.

## 4. The time-of-day table — descriptive, on the same books

`handover_time_of_day_20260916.md` asks for one re-run: the ET 30-minute block
table on the point-in-time trade list, with the four checks its stale run
lacked. It is produced from the MCL baseline book above (MC5's printed after
it), no re-run, in `common/time_of_day.py` reading the run's CSV.

Per block, 04:00–09:30 ET by the trade's entry bar: trades; net at all three
frictions; per trade; drop-top-3 at $4.26; both halves at $4.26; and the
session denominator — sessions with at least one entry in the block, the
share of those sessions positive at $4.26, mean and median per session.

**Named now, before the numbers:** the cell of interest is **07:45–08:00**, and
the hour 07:00–08:00. The stale run had 07:45 at +$20.98/trade on 80 trades
and drop-top-3 taking it from +1,678 to −537. This table has **no pass bar and
settles no hypothesis.** If 07:45–08:00 is positive at all three frictions, in
both halves, after drop-top-3, and its session median is above zero, the
window becomes registrable as a hypothesis in a *new* registration with the
window pre-committed; if any of those fails, the time-of-day question closes
and the 07:00-window backlog item comes off. Nothing else in the table is read
as anything but description. Every timestamp column in the CSV carries `_et`
in its name; the table says "ET" in its header.

## 5. What would make this run wrong

- The MCL book not counting 3,955, unremarked.
- A skip book whose entries are all present in the baseline: that would mean
  the signal-ordinal form was not implemented and the accounting form ran
  twice. The report prints the count of skip-book entries absent from the
  baseline; zero across 6,170 symbol-days is a defect, not a finding.
- Counting a band-refused signal as the skipped entry (§1 says it is not).
- Entry timestamps bucketed in UTC. The stale run's CSV was UTC; reading it as
  ET moved every conclusion four hours and still looked coherent.
- Halves cut per book rather than once.
- A threshold in §3 changed after the run. Each is a new hypothesis.

## 6. What this cannot settle

- **Not out of sample.** MCL was fitted on this calendar. `holdout.json`
  stays shut.
- **The concurrency cap is not modelled** (B2, §7 item 15). Live, a skipped
  first entry frees a slot for another name; here each symbol-day is run
  alone, so the rule's interaction with the cap — which is where a live
  benefit could also come from — is not in these numbers.
- **Order count is unmodelled**, as everywhere here.
- The live table's 134 trades are not used for anything but the motivation
  above. Live is for checking the backtest, not fitting.

# AMENDMENT A — 2026-09-17, POST-RUN. Written after `first_entry_skip_RESULT_20260917.md`.

Found by reading a result; changes nothing already read. Items 3 and 4 held
for both strategies with bootstrap P = 1.000 while the per-trade delta was
+0.03 (MCL) and −1.05 (MC5). On a book whose average trade loses, a delta
built from totals cannot fail for a rule that removes trades: per-symbol-day,
drop-top-N on the delta and the bootstrap on the delta all measure *trades
less*. The verdict here stands (NOTHING and REFUSED), because items 1 and 2
demanded per trade too. The defect is that +0.03 a trade was able to satisfy
item 1 at all. The next registrations (H-B3, H-B4) carry a margin of $4.26 on
Δ per trade and an abstention control — the same number of trades removed at
random, 2,000 seeded draws, the filter's per-trade delta above the 95th
percentile. Not applied here retroactively.

# AMENDMENT B — 2026-09-17, PRE-RUN. Re-based on the ITCH v2 universe.

The published point-in-time baselines moved to `screen_pairs_pit_itch_v2.json`
(6,411 symbol-days, 550 sessions, XNAS.ITCH bars) on 2026-09-17
(`REGISTERED_screen_itch_v2.md`). This registration was run on the BASIC
universe (6,170 symbol-days) and its verdict is a BASIC result. It is re-run
once on the v2 file with `--pairs var/state/screen_pairs_pit_itch_v2.json
--dataset XNAS.ITCH`, writing to `first_entry_skip_itch.txt` and
`first_entry_skip_itch_trades.csv` (the BASIC files are not overwritten).

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
- The time-of-day block table off the ITCH trades CSV is reported (it was
  withdrawn with the tape, not with the books); its named 07:45 cell is read
  under the four pre-stated checks of §3 exactly as before.
