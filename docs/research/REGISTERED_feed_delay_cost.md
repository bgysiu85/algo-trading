# REGISTERED — what the live feed's 900 seconds cost, and whether they are the shape of the live book

**H-D1.** `PROGRAM_INDEX` §7 item 1d(a). Written and committed 2026-09-19
(Sydney) before `common/feed_delay.py` exists and before any book with a
delayed floor has been run. **Cost $0.00** — two passes over bars already on
disk. `holdout.json` is not involved. Nothing here can change what the trader
does.

## 0. What is known, said plainly

- **The delay is measured and vendor-stated.** Until 2026-09-18 the live
  watchlist was built from `scanner.tradingview.com` polled without a login;
  TradingView labels that row `update_mode = delayed_streaming_900`. Signed in
  it reads `streaming` (`feed_freshness_probe_RESULT.md`). The block-stamp
  clock had already put the median at +15.6 minutes from the other direction
  (`screen_validate_itch_RESULT.md` §4). **Every live session before 09-18
  traded a screen exactly 900 seconds behind the tape.** With the login the
  future trader does not; this study is about the sessions already traded.
- **The simulation enters at `first_seen`**, the first minute the tape
  qualifies a name (`not_before`, `pit_strategy.py`). The live trader could
  not have seen the name until `first_seen + 900 s`, and from then on it read
  IB's real-time bars. So the live condition is a floor on the first entry,
  not a shift of every bar — and `not_before` already models exactly that.
- **The shape gap this exists to test.** Live MCL, 2026-09-12: 47.1% win, R
  0.72, (4.79)/trade over 17 round trips; the point-in-time simulation on the
  same screen specification: 21.7% win, R 1.67 (`PROGRAM_INDEX` §2, "The
  live record disagrees with the point-in-time backtest about the shape of
  the deficit"). The live book has since grown to 180 round trips through
  09-18, and the tool prints the current live shape rather than quoting this.
- **Two facts that lean against the delay explaining it.** The early names
  (`first_seen ≤ 04:30`) are slightly *better* per trade than the rest — MCL
  (8.73) against (8.97), MC5 (7.48) against (8.57) on ITCH v2 (index item
  13) — so removing the first quarter-hour after qualification is not
  expected to help. And the dying trades are the *most* extended entries
  (`running_up_preflight_RESULT`, median +11.43% five-minute move against
  +4.90%); entering later after qualification is more likely to enter more
  extended, not less.
- **A second live-feed effect points the other way and is out of scope.** The
  first poll served yesterday's screen, so the live trader could enter a
  carried-over name at 04:00 that the simulation never sees that day (VEEA on
  09-16, +$72.74). That is H-F1's gate, not this study; it is named so a
  reader does not credit the delay with what the carry-over did.
- **Live MC5 rows from 2026-09-10 to the `prod-20260918` promotion are
  apex-ON rows** (`live_defects_FIXED_20260917` §D) and are not the published
  strategy. The live MC5 shape is printed with that caveat and is not scored.

## 1. What is run

`common/feed_delay.py`, one tape pass per universe, `entry_sweep.py`'s
structure: every book on the same symbol-days, all-or-none per symbol-day,
day-ordered sums.

**Books.** For each of MCL and MC5, the entry floor at
`first_seen + Δ` for Δ ∈ {0, 5, 15, 30} minutes. Δ = 0 is the published v2
baseline and **must reproduce it exactly** — MCL (8.97)/trade over 3,908
trades, MC5 (8.57) over 6,462 on `screen_pairs_pit_itch_v2.json` — or the
run stops (a floor that silently did nothing is §4's recurring control
failure). Δ = 15 is the measured delay. 5 and 30 bracket it so the reading
is a curve, not a point. A floor past 09:30 admits nothing.

**Arm A — the population.** `screen_pairs_pit_itch_v2.json`, XNAS.ITCH bars,
6,411 symbol-days. What the delay costs and how it moves the shape.

**Arm B — the live sessions.** `screen_pairs_pit_itch_ext.json` (2026-09-08 →
the latest validated session), the sessions the live book actually traded,
beside the live round trips from `var/fills/mcl_fills_*.csv` over the same
dates (`churn_count.round_trips`). Per strategy: n, per trade, win rate, R,
median hold, share of holds ≤ 2 minutes.

Friction at $1.00 / $4.26 / $8.92 as every study here. Per-trade deltas
between two books are friction-invariant; per-symbol-day are not.

## 2. What is read, fixed now

Per strategy, per Δ against Δ = 0:

1. **Per trade and per symbol-day**, both denominators, both halves of the
   sessions. A disagreement between the denominators is reported, not
   refused — this is not a gate and nothing is being promoted.
2. **Trade count**, and **the marginal trade**: `(tot(Δ) − tot(0)) / (n(Δ) −
   n(0))` — what the entries the delay removed were worth.
3. **The shape**: win rate, R (mean win / mean |loss|), median hold in bars,
   one-bar death share, median five-minute return at entry (`running_up.ret_at`,
   the mechanism read back: a later floor that does not raise it did not
   enter later in the move).
4. **The live comparison (Arm B).** For MCL only (MC5's live rows are
   apex-ON): the distance from the simulated shape to the live shape, in win
   rate (points) and R, at Δ = 0 and at Δ = 15. **The delay "is the shape" if
   the Δ = 15 book closes at least half of both distances; "part of it" if
   one; "not it" if neither.** The three words are fixed here so the result
   cannot choose them.
5. **Monotonicity** across 0 / 5 / 15 / 30 — a sanity read on the mechanism,
   never a verdict.

Nothing PASSES here. The output is a cost and a classification of the shape
gap.

## 3. Predictions

- **P1.** Δ = 15 removes **10–25%** of MCL's trades and **5–15%** of MC5's
  (MC5 signals on five-minute bars and is later anyway).
- **P2.** The per-trade delta at Δ = 15 is **small and negative** (the delayed
  book is slightly worse per trade): MCL **(0.20) to (1.00)**, MC5 **(0.30) to
  (1.50)** — because the removed entries are the early ones, which read
  slightly better. Per symbol-day *improves* for both (fewer trades on a
  losing book), which is the abstention arithmetic and not a finding.
- **P3.** The shape barely moves: win rate by **< 5 points**, R by **< 0.3**,
  for both strategies. **The delay is "not it"** — moderate confidence. The
  alternative that would falsify this: MCL's win rate at Δ = 15 **≥ 35%** and
  R **≤ 1.1**, which would make the delay "the shape" and mean the live
  record before 09-18 was never evidence about the published strategy's
  shape.
- **P4 (Arm B).** On the live sessions the Δ = 15 book's total lands within
  **±30%** of the Δ = 0 book's, and the live MCL win rate stays **≥ 15
  points** above both.
- **P5 (mechanism).** Median five-minute return at entry **rises** with Δ for
  both strategies — the later floor enters more extended — by at least
  0.5 pp from Δ = 0 to Δ = 30.

If P3 holds, the shape gap is somewhere else — the concurrency cap (29% of
live buys refused), fills, IB's bars against the tape, or the apex-ON MC5
rows — and the next candidate is the cap (index item 15). If P3 fails, the
live book's shape is the feed's, and the comparison to make going forward is
against the post-09-18 sessions only.

## 4. What this decides, and what it does not

- Decides how to read the live record before 2026-09-18 against the
  simulation: as the same strategy seen late, or as a different question.
- Decides nothing about a strategy, a threshold, or a live change. No
  amendment to any engine; `not_before` is used as it exists.
- `holdout.json` stays shut. `D:\TradingProd` untouched. $0.00.

## 5. Amendments

None yet. PRE-RUN / POST-RUN marked when they come.
