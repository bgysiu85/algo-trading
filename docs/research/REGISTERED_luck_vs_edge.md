# REGISTERED — Part A: luck or edge? MCL and MC5 by session regime on the point-in-time books

From `claude/handover_luck_vs_edge_and_entry_quality_20260917.md` Part A.
Ben's question: the 09-16 green day was the opportunity set (MEDS +149%), not
execution — so do MCL and MC5 make enough on the sessions that pay to cover
the ones that do not, over history rather than one morning? **Committed
before any number below exists.** This is a descriptive study with one
pre-stated reading, not a hypothesis with a pass bar; it says what would make
"edge" the answer and what would make it "luck", and reads whichever it is.

## 1. Inputs, all of which already exist

- **The books.** MCL and MC5 baselines from `var/reports/first_entry_skip_trades.csv`
  (`book` = MCL / MC5; 3,955 and 6,883 trades; entry times in ET), with its
  meta file for the sessions run (551) and the halves cut (2025-08-07). No
  engine runs. Per-trade outcome: engine `net` less friction at $1.00 /
  **$4.26** / $8.92.
- **Same-day regime** (the ceiling — not knowable at 04:00): `regime.classify`
  over `regime.series(dbn_io.daily_frame(archive, XNAS.BASIC))`, market-wide,
  as `regime_study` computes it, refused if the daily archive's median session
  carries fewer than `MIN_UNIVERSE` symbols. Labels hot / mixed / cold, with
  unrated days labelled cold as `classify` does.
- **Lagged regime** (actionable at 04:00): `regime.lagged` of the same.
- **The 07:00 reading** (actionable at 07:00): `var/reports/cold_veto_readings.csv`
  from H-B4 — kind ∈ {count, cold, warm, inert}.
- **The trend-day flag**, defined here and not moved: over the point-in-time
  names of the session, the **leader's pre-market move** is the maximum of
  (last close before 09:30 ÷ the session's first printed open − 1). A session
  is a **trend day** when that move is **≥ 0.50**. Fifty percent is chosen now
  for a universe whose names have already gapped 20%+: it is a name that ran
  a further half again and *held it into the open*, which is the shape of
  MEDS on 09-16, not the shape of a spike that gave itself back. The
  distribution of leader moves is printed so the choice can be seen against
  it; it is not changed after.

## 2. What is measured, per strategy and per labelling

For each of the four labellings and each bucket: sessions in the bucket
(**all** of them, traded or not — the opportunity denominator), sessions with
a trade, trades, net at the three frictions, **per trade**, **per session over
all sessions in the bucket**, per traded session, share of traded sessions
positive, median session, drop-top-3 *sessions* within the bucket, both halves
per session. A bucket with fewer than `MIN_SESSIONS_PER_BUCKET` (= 5) sessions
prints "n/a" rather than a number.

## 3. The reading — fixed now

**Luck or edge** is read on the same-day labelling's **hot** bucket and on the
**trend-day** bucket, at $4.26, per strategy, in this order:

1. **Does the strategy make money on the sessions that pay?** H = mean net per
   session over all hot (respectively trend) sessions. Edge requires H > 0, in
   **both halves**, and after dropping the bucket's top 3 sessions. If H ≤ 0
   on the same-day hot bucket — the most favourable label there is, one that
   cannot be known in advance — then **no regime gate, however good, rescues
   the strategy**, and the answer is *neither luck nor edge: the book loses in
   every weather.*
2. **If H > 0: the break-even frequency.** L = mean net per session over the
   other sessions. f* = −L / (H − L) is the share of sessions that would have
   to be hot for the book to break even. Printed beside the **observed** share
   f. f* > f is the handover's "luck" reading: the strategy is paid on the
   hot days and not often enough. f* ≤ f cannot hold while the whole book is
   negative and would mean an arithmetic defect; it is printed and flagged
   rather than trusted.
3. **The lagged and 07:00 labellings** are printed for what an actionable
   gate would have seen, with no reading of their own: H-B4 already read the
   07:00 veto as NOTHING, and `ladder_and_regime` read the lagged gate as not
   adoptable. They are here so the ceiling and the actionable readings sit in
   one table.

**Written before the run.** On the point-in-time books MCL loses $10.52 a
trade and MC5 $13.50. `ladder_and_regime` §4's ceiling on the survivor
universe had hot at −$2.95 a trade for MCL; the PIT books are worse than the
survivor books by $5 a trade. I expect **H < 0 for MCL on the same-day hot
bucket**, i.e. reading 1 fails and the answer is *neither*. I expect the
trend-day bucket to be small (a leader holding +50% into the open is not
common) and possibly positive per session for MCL — if it is, the drop-top-3
line will decide whether that is three sessions or a bucket. For MC5 I expect
H < 0 on both.

## 4. A1 and A3, stated rather than run

- **A1, the 09-16 replay**, needs `XNAS.BASIC ohlcv-1m` for six names on one
  session, which is not in the archive (it ends 2026-09-04). It is priced with
  `common.databento_fetch` **without `--confirm`**, and the price is reported
  before anything is bought. If the price is under $1 it is bought and the
  replay is run under this registration's §1 machinery on that one session;
  the day's read is then "the backtest agrees with the live green day" or "it
  does not", per strategy, and nothing else.
- **A3, how much of the live 09-09..09-16 loss the three fixes account for**,
  needs those six sessions' bars for the whole watchlist. That is the archive
  extension in `PROGRAM_INDEX` §7 item 1 and is **not runnable** until it is
  pulled. Stated here so that a partial answer built from the one session A1
  buys is not mistaken for A3.

## 5. What would make this run wrong

- The daily archive refused as a market and the run continuing anyway.
- Per session divided by traded sessions where the table says all sessions.
- A trade on a date the labelling does not cover defaulted into a bucket
  rather than dropped and counted (as `regime_study.group` warns).
- The trend threshold moved, or a second threshold run "to see".
- The leader move using any bar at or after 09:30, or a non-PIT name.

## 6. What this cannot settle

- Not out of sample: MCL was fitted on this calendar, and the point-in-time
  calendar runs through the sessions the consolidated holdout locks — every
  PIT figure in this project is in-sample and says so.
- Whether the hot days are *predictable* — that is the regime persistence
  question (45.8% against 33%), and H-B4's proxy has already read as random.
- Whether a *size* response on hot days (rather than a gate) would carry the
  book: not a veto, not here, and the natural next registration if reading 1
  passes on the trend bucket.
