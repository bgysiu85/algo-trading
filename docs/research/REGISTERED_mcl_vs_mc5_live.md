# REGISTERED — is MC5 really better than MCL? The live book against the backtest, same sessions (W02-0002)

**H-L1.** Board item **W02-0002** (was AT-14). Written and committed 2026-09-23
(Sydney) by the Build & test chat **before `common/live_vs_sim.py` exists and
before any live-vs-sim P/L on 2026-09-18 → 09-22 has been computed**. Cost
$0.00 on the sessions already on disk; 2026-09-21/22 need a free-tier pull
(W02-0002 subitem 2). `holdout.json` is not involved. Nothing here can change
what the trader does.

## 0. What is known, said plainly — including what this chat has already seen

- **Ben's question** (`session_close_20260918.md` §5): he is not convinced MC5
  is better than MCL. The paper book shows MCL losing more; the backtest per
  symbol-day says the opposite (MCL (5.47) against MC5 (8.64), ITCH v2,
  `feed_delay_cost_RESULT` §1).
- **The backtest disagrees with itself across denominators, before any live
  trade is involved.** Per trade (ITCH v2, $4.26) MCL is (8.97) over 3,908 and
  MC5 (8.57) over 6,462 — MC5 marginally *better*. Per symbol-day MCL is
  better, because MC5 takes 1.65 trades for every one MCL takes on the same
  names. So "which is better" has at least two answers in the backtest alone,
  and the study reports both denominators every time and never one alone.
- **Already published, therefore not a prediction:** over 2026-09-08 → 09-17
  live MCL is 50 round trips at (7.13), live MC5 (apex-ON rows) 123 at (3.73);
  the simulation on those sessions reads MCL (4.63)/(3.62) at +0/+15 and MC5
  (3.51)/(4.13) (`feed_delay_cost_RESULT` §2).
- **What this chat has seen before writing this:** (a) `common.feed_delay` Arm B
  re-run from the device reproduces `var/reports/feed_delay_live_trades.csv`
  to the trade for 09-08 → 09-17 (554 of 554 rows), and the current
  `screen_pairs_pit_itch_ext.json` adds 2026-09-18 (12 symbol-days). Of 09-18
  it saw **trade counts only** (MCL 9 / 8 and MC5 17 / 11 at +0 / +15), no P/L.
  (b) Live round-trip **counts** per strategy per session (below), no P/L for
  09-18 onward. (c) The fill logs carry **154 BUY rows `SKIPPED_CONCURRENCY_CAP`
  "3 open, cap 3"** across the window.
- **Three regime facts fix how each session is compared:**
  1. **Feed.** Every session up to and including 2026-09-18 screened
     `delayed_streaming_900` (prod-20260918 predates the cookie path). The
     tagged `tv_feed` that writes `watchlist_arrivals_*.csv` ran from 09-21, and
     `var/feed_state.json` reads `streaming`, `authenticated`. So sessions
     ≤ 09-18 are compared with the **+15** book (as `feed_delay_cost_RESULT`
     §4 requires) and 09-21 / 09-22 with the **+0** book; the other offset is
     printed beside each as a sensitivity, never swapped in.
  2. **Apex.** MC5 live rows 2026-09-10 → 09-17 are apex-ON (`paper_fill.apex`,
     W02-0001, 37 signal exits). From 09-18 MC5 live runs the published rule.
  3. **Cap.** 2026-09-08 → 09-22 ran **one shared cap of 3 positions across both
     strategies**. The backtest has no cap at all. 2026-09-23 ran
     `cap_scope=strategy` (W02-0015) and is **excluded** — a different regime,
     and a session still in progress when this was written.
- **Live round trips per session** (FILLED SELLs = paired round trips, every
  session): MCL 09-08 2, 09-09 6, 09-10 6, 09-11 5, 09-14 8, 09-15 7, 09-16 9,
  09-17 7, 09-18 3, 09-21 10, 09-22 5 (**68**); MC5 apex-ON 09-10 16, 09-11 43,
  09-14 12, 09-15 12, 09-16 10, 09-17 30 (**123**); MC5 apex-OFF 09-18 12, 09-21 7,
  09-22 14 (**33**). **The apex-OFF MC5 sample is three sessions.** Nothing read
  from it alone is a verdict.
- **Known live-log defects carried, not repaired here:** the MEDS 09-16 exit
  fill is lost (W02-0008; that trade is absent from the paired book); the CRML
  09-21 double sell left the account short 100 and was closed by hand outside
  the log (W02-0014) — the log's own MCL and MC5 CRML rows are used as logged.
  Live P/L is price-only as logged; IB paper commission reads 0 (W02-0007).

## 1. What is run

`common/live_vs_sim.py`, new, research only (the trader never imports it).
Sessions: **2026-09-08 → 2026-09-22**, the shared-cap window, those with ITCH
tape and a universe row.

**Universe.** `screen_pairs_pit_itch_ext.json` for 09-08 → 09-18. For 09-21/22 a
new file `screen_pairs_pit_itch_ext3.json` from the same `screen_sim`
invocation as ext (`--dataset XNAS.ITCH --capture-ladder
var/reports/itch_capture.json`, `--after 2026-09-07`), after Ben's pull and
`regular_close --emit`. **Control C2** below decides whether ext3 may stand in
for ext on the overlap.

**Sim books**, `pit_strategy` engines through `backtest_session`, 100 shares,
all-or-none per symbol-day, `feed_delay.run_universe`'s structure:
- MCL +0, +15; MC5 +0, +15 (published rule, apex OFF);
- **MC5-apexON +15** on 09-10 → 09-17 only (`engine("mc5", use_apex=True)`) —
  the like-for-like book for the apex-ON live rows.
- The **feed-matched book** per session = +15 for ≤ 09-18, +0 from 09-21.

**The shared cap, replayed.** On each session's feed-matched MCL + MC5 sim
trades together, in minute order: a position is open on [entry, exit); exits at
minute t release their slot before entries at t are considered; an entry is
admitted only if fewer than 3 positions are open. Same-minute entries of the
two strategies are ordered **both ways** (MCL-first, MC5-first) and both
printed — a bracket, never one chosen. Also replayed: **cap 3 per strategy**
(W02-0015's rule), reported only. *Approximation, stated:* a refused sim trade
does not release later entries on the same symbol that the engine suppressed
while it was "held"; the replay can only remove trades, never add them.

**The population.** The same replays on `feed_delay_trades.csv` books `MCL +0` /
`MC5 +0` (ITCH v2, 550 sessions) — no new tape pass.

**The live book.** `churn_count.round_trips` over `var/fills/*_fills_*.csv`,
per strategy, by exit session. MC5 split by `paper_fill.apex`'s rule (apex-ON ⇔
session ≤ 2026-09-17). Printed as logged, and again with an IBKR-tiered
commission from `common.commissions.round_trip(100, price, "ibkr_tiered")` per
trade.

**The join (live ↔ sim).** Same strategy, symbol and session; a live BUY fill
matches a sim entry if it lies within **two of that strategy's bars** of the
sim `entry_et` (MCL 2 min, MC5 10 min); one-to-one, chronological, nearest
first. One bar is printed as a sensitivity. Against the feed-matched,
**uncapped** book (the cap is a reason a sim trade is unmatched, so the
unmatched side must still contain it).

**The decomposition, an identity.** Per strategy and regime:
`live total − sim total = Σ matched (live − sim) + Σ live-only − Σ sim-only`,
printed with its residual, which must be 0.00.
- **Matched** — execution: live P/L minus sim gross P/L per matched trade,
  split into entry price difference and exit price difference (×100 shares).
  This is the measured round-trip friction and is set beside the $4.26 assumed.
- **Sim-only**, classified from the live log (first match wins): `cap` (a
  `SKIPPED_CONCURRENCY_CAP` row, same strategy and symbol, within two bars),
  `other skip` (any other SKIPPED_* / NO_FILL / REJECTED BUY row within two
  bars), `live busy` (the live strategy already held that symbol then), `never
  signalled` (none of those).
- **Live-only**: `not in sim universe` (symbol absent from that session's
  universe row set), `sim no entry near` (present, no sim entry within two
  bars).

Friction at $1.00 / $4.26 / $8.92 for every sim figure. A per-trade
difference *between the two strategies* is friction-invariant; per session and
per symbol-day are not.

## 2. What is read, fixed now

**The question has one answer per denominator, and three verdict words fixed
here:** for the difference **MCL − MC5**, a session-clustered bootstrap
(10,000 resamples of sessions with replacement, seed 20260923, per-trade figures
as ratio of sums within each resample): **"MCL better"** if the 90% interval is
entirely above 0, **"MC5 better"** if entirely below, **"can't tell"** if it
spans 0.

Read on four books, per trade and per session (and per symbol-day where the
book has symbol-days):
1. **Live**, shared-cap window, MC5 all rows; then MCL vs MC5 apex-OFF only
   (09-18 → 09-22), and MCL vs MC5 apex-ON (09-10 → 09-17), each on the sessions
   both strategies were running.
2. **Sim, feed-matched, uncapped**, same sessions. MC5 apex-ON sessions also
   read on the apex-ON book.
3. **Sim, feed-matched, shared cap replayed**, same sessions (both orderings).
4. **Population**, ITCH v2 +0: uncapped (published), shared cap replayed,
   per-strategy cap replayed.

Then, per strategy: the decomposition (§1) and the cap census — how many sim
trades each strategy loses to the replayed shared cap, and what they were worth
(the marginal trade), live refusals by strategy beside them.

**Agreement.** Live and sim "agree" on a denominator if they give the same word.
"Can't tell" against a directional word is reported as **not a disagreement** —
it is a sample too small to disagree with.

## 3. Predictions

- **P1 (live).** Per trade, live MCL − MC5 over the window is negative (MCL
  worse, as Ben saw) and the verdict is **"can't tell"**. Per session the same.
- **P2 (sim, same sessions).** "can't tell" on both denominators, uncapped and
  capped.
- **P3 (population).** Per trade **"can't tell"** (the published gap is $0.40);
  per symbol-day **"MCL better"**. The shared cap does not flip either word.
- **P4 (cap census).** On the population the replayed shared cap refuses a
  **larger share of MCL's trades than MC5's** (MC5 signals early after
  qualification and fills the slots first), and moves each strategy's per-trade
  figure by **less than $1.00**.
- **P5 (execution).** Matched live − sim gross is negative for both strategies,
  **between (1.00) and (8.00) a trade**, i.e. of the order of the $4.26 assumed.
- **P6 (the disagreement).** The live-vs-backtest disagreement Ben raised is
  **the denominator plus sampling noise** — no book that has the sample to
  speak (the population) says MC5 is better per symbol-day, and none says
  either is better per trade.

If P6 fails — a live or same-session sim book says "MC5 better" per trade or
per session with the interval clear of zero — the decomposition says which
component carries it, and that component is the next item.

## 4. Controls — a failed control stops the reading it guards

- **C1.** The +0 and +15 books on 09-08 → 09-17 reproduce
  `feed_delay_live_trades.csv` to the trade.
- **C2.** ext3 reproduces ext's rows (symbol, date, first_seen) on 09-08 → 09-18.
  If not, ext is used for those sessions and the difference is printed.
- **C3.** Paired live round trips per strategy per session equal that
  session's FILLED SELL count; the decomposition residual is 0.00 everywhere.
- **C4.** The cap replay with cap = ∞ returns the uncapped book exactly; with
  cap = 1 no two admitted trades overlap.
- **C5.** The population `+0` books read 3,908 at (8.97) and 6,462 at (8.57).
- **C6.** The apex-ON book differs from the apex-OFF book on 09-10 → 09-17 by at
  least one trade (else it measured nothing, and says so).

## 5. What this decides, and what it does not

- Decides how to answer Ben's question, per denominator, and which part of the
  live-vs-sim gap is execution, which is the cap, and which is universe.
- Informs W02-0015 (per-strategy cap) through the population replay; decides
  nothing about it.
- No strategy change, no threshold, no live change. `holdout.json` stays shut.
  `D:\TradingProd` untouched.

## 6. Amendments

None yet. PRE-RUN / POST-RUN marked when they come.
