# REGISTERED — the Nasdaq order book at entry (H-L2) on the MCL and MC5 books

2026-09-23, **PRE-RUN, PRE-DATA.** No order-book record for this study has been priced, pulled or read. No feature
code exists. This document is committed to git before any of that. Git's ordering is the claim (`PROGRAM_INDEX` §1:
a hypothesis is registered before it is run).

Board: **W02-0013**, subitems 5–10 (monday "Algo Trading", group W02). Ben, 2026-09-23, in his words: *"can we look
into the L2 market data in conjunction with the OHLCV data to see if a pattern or condition will emerge, especially
when comparing with other smaller wins or losses"*, then *"I would like to proceed with your recommended option A
(live comparison and the 12-month backtest test). I think this test should be folded in as a subitem of W02-0013"*.
Parents: `claude/grml_20260922_momentum_entry_context_20260923.md` (W02-0013 steps 1–4); `session_close_20260918.md`
§5 item 3 (Ben's order-book idea, 2026-09-18); `docs/research/REGISTERED_10sec.md` (H-Q1, the same idea on ORB);
`docs/research/REGISTERED_spread_gate.md` (W03-0002, the spread at entry); `common/quote_price.py` (the window
pricer this study reuses). Where this document and `PROGRAM_INDEX` §4 disagree, §4 wins and this file is the bug.

---

## In plain terms

GRML on 09-22 was one of the best trades MCL and MC5 have made. W02-0013 tried to find something on the price
chart that marked it before entry and found nothing. The tight-base filter it tested did no better than dropping
trades at random, on 10,838 backtest trades and 374 live signals. Every entry filter this project has tested was
built from the same price-and-volume bars, and every one read as random removal. This study uses a different
input: **Nasdaq's order book**, meaning the buy and sell orders queued at each price. It asks whether that book,
in the minute before the order goes out, separates winners from losers. Three simple readings of the book are
scored on about 4,900 backtest trades from the last 12 months. A deeper 10-level book is described for the 448
live signals, set out by outcome so the GRML-type runs can be compared with smaller wins and losses. That live
part is looked at, never scored. I expect all three scored readings to fail the $4.26 bar, and §9 says why. The
data is inside Ben's plan, and the point is to settle the idea in one pass.

---

## 0. PRE-RUN GATES — nothing is scored until each is cleared, in order

| # | Gate | Why it blocks |
|---|---|---|
| **G1** | **This document is committed to git** (W02-0013 subitem 6). | Registration before data. |
| **G2** | **Both pulls are priced, then landed** (W02-0013 subitem 8), with `common.quote_price` in windows, never whole days. **(a) Live, first:** XNAS.ITCH `mbp-10` for every live signal symbol-day 2026-09-02 → 09-22 (95 symbol-days, 448 signals), window 10 min before the first signal to 5 min after the last. **(b) Backtest:** XNAS.ITCH `mbp-1` for every in-plan window of the published ITCH book (§2), same window rule. Each run goes without `--confirm` first and reports the vendor's number. **If either is not $0.00 it stops for Ben.** | The MBP-10 entitlement is one month (per the 2026-09-18 entitlement check) and has never been priced on this project. The live days start leaving it around 2026-10-02, so (a) goes first. The MBP-1 window is the last 365 days and loses a session a day. |
| **G3** | **The feature extractor is tested and mutation-checked** (W02-0013 subitem 7). Hand-built record streams for: no record stamped at or after the order instant *t* is ever read; the time-weighting of F1 weights each state by how long it stood; F2 matches hand-computed Cont–Kukanov–Stoikov values on a five-event case, including a price improvement and a level being wiped out; F3's buy/sell classification agrees with the quote rule (print at or above the standing ask = buyer-initiated) on ≥ 95% of prints where the quote rule applies; MC5's *t* is its 5-minute bucket close, not the bucket start (the H-R1 grain defect); `NO_BOOK` and `NO_TRADES` are buckets, never zeros. Reverting any one of these must fail a test. | This project has found the same shape of timing defect by test twice (amendment D on ORB; the MC5 four-minute window shift). A feature that reads one record past *t* is look-ahead and would pass every control. |
| **G4** | **The positive control passes** (§5.3). | If book imbalance does not even predict the next 10 seconds of the Nasdaq mid at these instants, the construction or the tape is broken and nothing in §5.1 is scored. |

---

## 1. Why this, and why now

1. **Bar features are exhausted on these books.** Chase gate (H-P1), consolidation, thin tape (H-T1), pullback
   cell, one-bar death rate, and W02-0013's tight base all read as random removal. `PROGRAM_INDEX` §4: *a lower
   failure rate is not a better book.* The order book holds information the bars do not.
2. **The hold is short enough for the book to matter, in principle.** On the ITCH book inside the plan window, MCL's
   median hold is **4 minutes** (p75 11) and MC5's **10 minutes** (p75 15). That's far shorter than ORB's hours,
   where H-Q1 predicts the horizon mismatch kills the signal. Top-of-book imbalance is known to forecast seconds to
   a minute.
3. **The data is inside the plan.** The XNAS.ITCH MBP-1 tapes were sample-priced at $0.00 projected for every entry
   window (`var/reports/quote_price.txt`, 2026-09-19; 7.6–10.2 GB). MBP-10 is expected to be $0.00 inside its
   month but has never been priced (G2).
4. **Live parity is possible later.** Ben holds IBKR Nasdaq TotalView, which is the same Nasdaq book.

**The prior against, stated first.** Both books lose money before costs as well as after. Friction break-even is
below zero (MCL (0.96), MC5 (4.67) a round trip; `REGISTERED_10sec.md` §1.2). So a selector has to find a subset
that makes money gross, not just trim losses. None of this project's entry selectors has done that. GRML's 30–70×
volume surge came at 06:35–06:50, about 30 minutes after MCL's entry and 15 after MC5's, past anything the book
at *t* can see.

---

## 2. Populations

### 2.1 Scored: the ITCH book, inside the MBP-1 plan window

The published point-in-time ITCH baselines, `var/reports/chase_gate_trades.csv`, rows `book ∈ {MCL, MC5}` only (the
same 10,370 entries as `var/reports/thin_tape_entries.csv`). Prices and fills are unchanged, and friction is
**$4.26** a round trip. **In sample:** every trade on a session inside the MBP-1 plan window on the day the G2(b)
pull runs, through the book's last session 2026-09-15. The report prints the first date. Today that is about
2025-09-25 → 2026-09-15: **241 sessions, MCL 1,840 + MC5 3,052 = 4,892 trades**. It loses about one session a day
until the pull lands.

**Why the ITCH book and not XNAS.BASIC.** The book features come from Nasdaq's own feed (XNAS.ITCH), and the ITCH
book's prints come from the same exchange. Features and fills on one venue's tape avoid pairing one venue's book
with a consolidated tape's prints.

**No holdout exists for these books.** `holdout.json` says the locked sessions are not out of sample for MCL or
MC5, which were built before the cut. Everything here is in-sample on books that have been cut many times, which is
why §7 carries a multiplicity bar.

### 2.2 Described, never scored: every live signal, 2026-09-02 → 09-22

The 448 live entry signals (filled and skipped) on 95 symbol-days in `Claude outputs\w02_0013_live_signals_features.csv`.
*t* is the signal's logged timestamp. The outcome is live net for filled signals and the W02-0013 simulated net
(`pnl_sim`) for all of them. Signals from a session still open when the study runs are left out.

---

## 3. The features, exactly

Every feature is read from XNAS.ITCH records stamped strictly before the order instant *t*. The window is
**W = [t − 60 s, t)**.

- **Backtest *t*** = the signal bar's close: `entry_et + bar_min` (MCL 1 minute; MC5 its 5-minute bucket close).
- **Live *t*** = the logged signal timestamp.

### 3.1 Scored (MBP-1, backtest and live)

- **F1 — quote imbalance.** QI = (bid size − ask size) / (bid size + ask size) at Nasdaq's best bid and offer,
  **time-weighted over W**. **Rule: keep iff QI > 0.**
- **F2 — order-flow imbalance** (Cont, Kukanov & Stoikov 2014). OFI = Σ over MBP-1 top-of-book updates in W of
  e_n = 1{b_n ≥ b_{n−1}}·q^b_n − 1{b_n ≤ b_{n−1}}·q^b_{n−1} − 1{a_n ≤ a_{n−1}}·q^a_n + 1{a_n ≥ a_{n−1}}·q^a_{n−1}.
  Here b and a are the best bid and ask prices and q their sizes. **Rule: keep iff OFI > 0.**
- **F3 — aggressor share.** Buyer-initiated shares ÷ all shares printed on Nasdaq in W. Buyer-initiated is the
  trade record's side field as documented by Databento, cross-checked in G3. **Rule: keep iff share > 0.5.**

Each rule is a sign with no threshold. That's the same parameter-free form as H-Q1 and amendments H and I on ORB, for
the same reason: a threshold makes it a grid, and a grid on these books is a search.

**Buckets outside the rule, reported with count and P/L, in neither side:** `FLAT` (exactly 0 or exactly 0.5);
`NO_BOOK` (no two-sided Nasdaq quote at any point in W, or locked/crossed for all of W; F1, F2); `NO_TRADES` (no
Nasdaq print in W; F3). **In accounting form, a trade in these buckets is let through**, as W02-0013 let through
trades without bars. If any of these buckets exceeds 10% of a book's trades, the report says so at the top.

### 3.2 Described only (MBP-10, live signals only)

F1–F3 as above, plus:

- **D1 — depth imbalance over 10 levels**, time-weighted over W: (Σ bid size − Σ ask size) / (Σ bid size + Σ ask size).
- **D2 — ask-depth change**: total ask size over 10 levels at *t* ÷ the same at t − 60 s.
- **D3 — spread at *t*** in % of mid. W03-0002 is where spread is scored. It appears here only so the live table
  isn't read without it.

---

## 4. Friction and fills

$4.26 a round trip, charged on every trade, as in every MCL/MC5 gate study. Fills are the book's own, unchanged: this
is the accounting form (the baseline minus refused trades), as in W02-0013 and the chase gate. The engine form, where
the engine re-enters after a refusal, is not run here; a pass earns it (§8).

---

## 5. Controls and readings

### 5.1 Scored — per rule (F1, F2, F3), per book (MCL, MC5): six readings

1. **`common.gate_study.verdict`, unchanged**, as in W02-0013 and the chase gate: per-trade gain ≥ $4.26 and
   per-symbol-day gain > 0; both halves split at the median session of §2.1's own sample, derived once; drop-top-3;
   symbol-cluster bootstrap; random removal of the same number of trades (reading 5).
2. **Multiplicity bar.** Six readings on books with no holdout give about a 26% chance that at least one passes
   reading 5 at p95 by luck. So the rule's per-trade gain must also beat random removal's **99.2nd percentile**
   (0.05 / 6), from **5,000 draws, seed 20260923**.
3. **What it removes among the winners**, reported: winners refused, their net, and how many of the book's 20 best
   trades are refused (W02-0013's reading).

### 5.2 Reported, never scored

- The three rules on the 374 out-of-sample live signals (W02-0013's non-first-pass days), with the same
  random-removal control.
- **The outcome comparison Ben asked for:** live signals in four buckets by net — **big runs** (≥ +$100, which
  includes both GRML fills), **small wins** (0 to +$100), **small losses** (0 to −$25), **big losses** (< −$25) —
  with the median and interquartile range of F1–F3 and D1–D3 in each. GRML's six signals are listed on their own.
  **Nothing seen in this table is a rule.** A pattern here earns a new registration, scored on the backtest book,
  with the reason stated.
- Composition, the time-of-day proxy lesson: kept share by session phase (04:00–07:00, 07:00–09:30, 09:30 on), by
  spread in ticks, and by book.
- Overlap between each rule's refusals and the 2.0% spread gate's (W03-0002), so the two are not double-counted.

### 5.3 Positive control (G4) — must pass before §5.1 is scored

At each backtest *t*, take the Nasdaq mid m0 and the mid 10 seconds later, m1. Among instants where m1 ≠ m0, the
share where the mid moved the way F1 pointed must exceed 50% with a one-sided binomial p < 0.01. This is the most
replicated short-horizon fact in market microstructure. If it doesn't hold here, the construction or the tape is
broken, §5.1 is not scored, and the report says so and stops.

---

## 6. Order of work, and the shrinking windows

G2(a), the live MBP-10 pull, runs as soon as G1 clears, because the live days start leaving the one-month
entitlement around 2026-10-02. The pulled records are not read until G3 passes. G2(b) follows, then G3 and G4,
then §5.

---

## 7. The bar — a rule is carried forward only if all of it holds, on at least one book

1. `common.gate_study.verdict` passes all five readings (§5.1.1);
2. the per-trade gain beats random removal's 99.2nd percentile (§5.1.2);
3. G4 passed;
4. the rule refuses **fewer than half** of the book's 20 best trades (a filter that refuses the fat tail refuses
   the thing the strategies exist to catch; W02-0013 refused 15–16).

### 7.1 Retirement clauses, fixed now

- **If H-L2 fails,** QI, OFI and aggressor share are retired as MCL/MC5 entry selectors: no threshold on them, no
  other window length, no combination of the three, no MBP-10 version of a failed rule. A §5.2 pattern can still be
  registered, but only with a stated reason why it isn't one of these three with a knob.
- **Relation to H-Q1** (`REGISTERED_10sec.md` §7.1, which retires top-of-book imbalance project-wide if H-Q1 fails
  on ORB): H-L2 is registered **before H-Q1 has read**, on a different host (small-cap momentum, mostly
  pre-market, long only, holds of minutes). Its result stands on its own either way. H-Q1 failing later does not
  cancel it, and H-L2 failing does not decide H-Q1.

### 7.2 What this registration does not claim

1. **Priced before bought.** G2 runs without `--confirm` first. A non-zero number stops for Ben; the study doesn't
   silently switch tapes or windows.
2. **Nasdaq's book, not the market's.** XNAS.ITCH and IBKR TotalView are both Nasdaq only. Most names these
   strategies trade are Nasdaq-listed, where Nasdaq's quote is usually the best, but not all. The report splits
   by listing venue, reported only.
3. **Displayed size is not committed size.** Hidden and reserve orders don't show. Fleeting quotes, cancels and
   spoofing do, and small caps are where spoofing is most common. Time-weighting over 60 s damps fleeting quotes,
   and nothing here models intent.
4. **Pre-market books are thin.** That is where most of these entries are. `NO_BOOK` is counted, not hidden.
5. **Backtest *t* is modelled.** The live order goes out after the bar closes plus processing and, before
   2026-09-19, TradingView feed delay. The live table (§5.2) reads the book at the live timestamp.
6. **The 448 live signals are a description.** W02-0013 showed what reading an outcome-picked sample does.
7. **Live parity is not tested.** IBKR's depth stream is not tick-by-tick, and a pass earns a live-parity
   registration, not a deployment.

---

## 8. What a pass would buy

Nothing is deployed. A pass earns (a) the engine-form backtest of the passing rule, where refused entries free the
concurrency slot and re-entry is allowed, and (b) a live-parity registration using TotalView depth in the trader,
recorded in shadow mode (logged, not acted on). Then Ben decides (W02-0013 subitem 10): live parity, study only, or
close.

---

## 9. Predictions, scored either way

- **G4 positive control: PASSES.** High confidence.
- **F1, F2, F3 on both books: NOT ADOPTABLE.** Each fails reading 1 (per-trade gain < $4.26). None beats the 99.2nd
  percentile of random removal. Mechanism: the book forecasts about a tick over seconds, while these trades are
  decided over minutes on books that lose money gross, so a one-bit selector can at best shave losses. It can't turn
  the gross positive, and shaving losses is what random removal already does. **No secondary "real but
  insufficient" prediction is made.** That form was wrong twice in a row on ORB (amendments H and I).
- **Live description:** GRML's two winning entries will not look unusual on F1–F3 against the small-loss bucket.
  If they do, that's a finding for a new registration, not a rule.

---

## 10. What would make this run wrong

- Pulling or reading any MBP record before this document is committed.
- Reading the G2(a) live records before G3 passes.
- Scoring anything after a failed G4.
- Changing the 60-second window, the sign rules, *t*, the buckets, the population rule or the friction after seeing
  any result. Each is a new registration, and §7.1 has refused the obvious ones.
- Quoting a rule without random removal and its 99.2nd percentile beside it.
- Turning any §5.2 observation into a threshold in this study.

---

## 11. Timeline — board item W02-0013, one subitem per step

| # | Step | Who | Rec. model / effort |
|---|---|---|---|
| 5 | Register (this document) | Research & spec chat | Opus / High — done 2026-09-23 |
| 6 | Commit this document to git, before any data or code | Ben (commands on the subitem) | — |
| 7 | Live-signal entries file; G3 feature extractor with mutation-checked tests | Build & test chat | Sonnet / High |
| 8 | G2: price then pull, (a) live MBP-10 first, (b) backtest MBP-1 | Ben (commands on the subitem) | — |
| 9 | G4, then §5.1 and §5.2; Result doc, raw `.txt`, artifact page | Build & test chat | Sonnet / Medium |
| 10 | Decide, per §8 | Ben | — |

Steps 7 and 8(a) can overlap: the live-signal entries file needs no code beyond a CSV. If the Build & test chat can't
start within a few days, the pricing half of G2(a) can run first, as long as nothing pulled is read before G3.
