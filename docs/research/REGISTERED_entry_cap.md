# REGISTERED — H-C1: the entry-count cap, no 4th-or-later entry per strategy per symbol-day (PRE-RUN)

**Author: Research & spec chat, 2026-09-24, for W03-0008.** Committed before the
study module exists and before any backtest trade has been grouped by entry
number. The commit hash is the timestamp.

---

## 0. Where this comes from, and what is wrong with it already

Ben, 2026-09-23, after 09-22 gave back ~$70 of a +$304.22 peak in small MC5
re-entries: *"Can we compare between the losing trades with the winners and see
if we can identify any usable markers or indicators to help avoid entering
those trades?"*

The live pre-read (`claude/paper_cuts_20260924_RESULT.md`, 256 live trades,
10 sessions) tested none of it; it described. It found:

| live, entry number per strategy + symbol + day | trades | net | per trade | winners |
|---|---|---|---|---|
| #1 | 109 | (733.69) | (6.73) | 30% |
| #2 | 58 | +156.33 | +2.70 | 33% |
| #3 | 31 | (327.58) | (10.57) | 26% |
| #4 or later | 58 | (209.59) | (3.61) | 17% |
| all | 256 | (1,114.53) | (4.35) | 27% |

and "re-entry after a win" was **not** worse than a first entry ((6.55) vs
(6.73)), so that candidate is dropped here and not tested.

**Stated before the run, against this registration's own interest:** the
4th-or-later cell is weak on *win rate* and on *total*, but its **per-trade loss
(3.61) is smaller than the live book's average (4.35)**. On the live book,
removing those 58 trades would make per-trade *worse*, not better. The cell was
picked after seeing the trades, on the metric that looked worst. The only
reason to register it is that it is the one day/sequence-state cut the live
book pointed at, and the point-in-time backtest is ~40× larger. The backtest
is the test; the live table is not evidence for it.

**Why it is not a re-run of something closed.** H-B1 (`first_entry_skip`)
removed the *first* entry; this removes the *tail*. The give-back cap (H-S4)
stops a session on its P&L path; this stops a symbol on its entry count,
regardless of P&L. Bar-feature entry filters are a closed line
(`PROGRAM_INDEX` §4) and nothing here reads a bar feature.

---

## 1. The rule, exactly

```
For each strategy, each symbol, each session (ET date):
    count = entries already taken in this symbol today by this strategy
    if count >= MAX_ENTRIES: refuse the entry
```

**MAX_ENTRIES = 3** is the hypothesis ("no 4th entry").

**The capped book is exact without re-simulation.** Both published engines are
causal and hold one position per symbol at a time: trade *k* depends only on
bars up to its own exit. A rule that refuses every entry after the 3rd cannot
change trades 1–3 (they happened before the rule could act) and leaves nothing
after them. So the capped book **is** the baseline book with every trade whose
in-book `ordinal` is ≥ 4 removed. Unlike H-B1, the signal-ordinal form and the
accounting form are the same book here; there is no cascade, and the report
must print **0 capped-book entries absent from the baseline** — any other
number is a defect.

Scope: **per strategy.** MCL's count and MC5's count are separate, matching the
live cut (entry number per strategy + symbol + day) and matching how the
backtest books are built (one engine run per strategy per symbol-day).

---

## 2. The books — no new simulation

Source: `var/reports/dist_from_high_gate_trades.csv`, books `MCL` and `MC5`
only (the ungated baselines), written 2026-09-23 13:33 UTC by
`common.dist_from_high_gate` on `var/state/screen_pairs_pit_itch_v2.json`,
XNAS.ITCH, 550 sessions, **6,411 symbol-days**, 100 shares, commission in.
`git log -- strategy/mcl strategy/mc5 common/pit_strategy.py` shows no engine
change since 2026-09-18, so these are the current engines' books.

**Population check, or the run stops:** MCL **3,908** trades and MC5 **6,462**
trades — the published v2 baselines (`screen_itch_v2_RESULT`, and amendment A1
of `REGISTERED_giveback_cap.md`). Halves are cut once, at the meta file's
`cut` (2025-08-07). Per symbol-day divides by 6,411 for every book.

---

## 3. Cells

| cell | MAX_ENTRIES | status |
|---|---|---|
| **CAP-3** | 3 | **PRIMARY** — scored, for MCL and for MC5 separately |
| CAP-2 | 2 | boundary — scored by the same readings, reported beside |
| CAP-4 | 4 | boundary — scored by the same readings, reported beside |
| CAP-1 | 1 | reported, not scored (first entry only; H-B1's mirror image) |
| baseline | none | must match §2's counts |

**Multiplicity declared:** one hypothesis (CAP-3), two strategies, two boundary
cells. If CAP-3 fails and a boundary passes, that is **not** a finding; it
would be a new registration with its own cap fixed in advance. If CAP-3 passes
and **both** boundaries fail badly, the pass is a knife-edge and is read as
NOTHING for adoption.

---

## 4. Readings — the five, inherited unchanged

`common/gate_study.verdict`, as fixed in `REGISTERED_range_rank.md` §3 and
used by every gate since, at **$4.26** friction:

1. Δ per trade **≥ $4.26** (the margin) AND Δ per symbol-day > 0; a sign
   disagreement is a REFUSAL;
2. both temporal halves, both denominators, > 0;
3. drop-top-3 on the level and on the delta;
4. symbol-cluster bootstrap on the delta, P(total > 0) ≥ 0.95
   (RESAMPLES 2000, SEED 20260916);
5. **abstention control**: the same number of trades removed from the baseline
   at random, 2,000 seeded draws; the cap's Δ per trade must beat the 95th
   percentile.

All five → PASSES for that strategy. Any fewer → NOTHING, naming which failed.

**Reported beside the verdict, not scored:**

- **Positional control** (the sharper null for *this* rule): for every
  symbol-day the cap touches, remove the same number of trades *from that same
  symbol-day* but at random positions, 2,000 draws, SEED 20260916. Random
  removal (reading 5) asks "is this better than trading less?"; the positional
  control asks "are *late* entries in a busy name worse than *any* entries in a
  busy name?". If the cap beats reading 5 but not this, what it found is that
  busy symbol-days lose, not that late entries do — still only actionable
  through a cap, and said so plainly.
- **Removed vs kept, per trade**, at all three frictions — the whole mechanism
  in one row.
- **The ordinal table** (entries #1, #2, #3, #4, #5+) per strategy at $4.26,
  so the live table has its backtest counterpart.
- **Entry time of day** of removed vs kept trades (ET, 30-minute blocks
  summarised as median and share after 08:00). If removed trades are worse only
  because they are late in the morning, this is the time-of-day filter again,
  and time of day is closed.
- How many symbol-days the cap touched, and how many of the baseline's top-10
  trades at $4.26 it removes.
- The books at $1.00, $4.26 and $8.92.

---

## 5. Registered prediction

**NOTHING for both strategies**, confidence **moderate-to-high**, failing
reading 1's $4.26 margin and most likely reading 5.

Reasons, written now:

- The live cell's per-trade loss is already *smaller* than the live average (§0).
- H-B1 (skip the first entry), re-based on these same v2 books, read REFUSED
  for both strategies: removing first entries made per trade *worse* (MCL
  (0.41), MC5 (0.78)) while per symbol-day improved — the removal-from-a-losing-
  book signature (`halt_census_RESULT.md` §6). Entry order has not separated
  trades before. `luck_vs_edge` / `cold_veto` found session state does not
  separate per-trade results either.
- Arithmetic of reading 1: for kept trades to gain $4.26 each, the removed
  trades must be worse than the book by about $4.26 × (kept ÷ removed). If the
  cap removes ~10% of trades, removed trades would need to lose ~$38 a trade
  *more* than average. Nothing in the live table is near that.
- **Total P&L will improve** on both losing books, and Δ per symbol-day will be
  positive, by the arithmetic of removing trades from a book that loses before
  costs. That is predicted here so it cannot be reported as a success.

---

## 6. Go / no-go

**Adopt (as a holdout candidate, not a ship)** only if CAP-3 passes all five
readings for that strategy at $4.26, the removed trades lose more per trade
than the kept ones at $8.92 as well, and the removed trades are not simply the
late-morning ones (§4 time-of-day row).

**Refuse** on any single reading. A total-P&L improvement with a Δ per trade
below the margin is a refusal, not a finding.

Live-trader note, for if it ever passes: the trader must count entries per
strategy per symbol per ET date from its own fills, including entries that
were stopped out within the same minute — the project has been bitten three
times by a constant the live path never reads.

---

## 7. What this cannot settle

- It cannot say anything about **MCL being profitable**: MCL's backtest loses
  before costs, so a filter can only shrink a loss.
- It does not test the give-back cap (H-S4, done; W02-0019 is Ben's decision
  on MC5) and is not stacked with it.
- It is in-sample on the point-in-time universe; `holdout.json` is not touched.
