# REGISTERED: a time cap on holds, with and without the position-slot cap modelled

**Committed before the runner is coded and before any result from it has been seen.**
`PROGRAM_INDEX` §1: a hypothesis is registered before it is run.

Board: **W03-0004** (this study), step 1. It also delivers **W03-0003** (model the slot cap in
backtests), which is built as step 3 of W03-0004. Motivation: `claude/handover_holds_misses_levers_20260919.md` §3 and §4.3.
Ben's decision, 2026-09-27, in his words: *"Run the full study"* (chosen over closing the item
or running a slim version, after he saw the scoping check in §6).

---

## 1. The claim, exactly

A **time cap** force-sells any position that has been open for **N minutes**, at the close of
the bar where the N minutes run out. On its own it can only cut trades short. The case for it
(handover §4.3) is that it **frees a position slot**, so a signal that the slot cap would
otherwise have turned away can be taken instead.

So there are two arms:

- **Arm 1: no slot cap.** Each symbol-day runs on its own, as every published backtest does.
  This measures the pure cost (or gain) of cutting holds short.
- **Arm 2: slot cap modelled.** Both books (MCL + MC5) run as one account on each date, in time
  order, and an entry is turned away when the slots are full, as `brokers/ibkr/trader.py` does.

**Slot value = (Arm 2 change) minus (Arm 1 change)** at the same N. If the time cap only helps
with slots modelled, it is a portfolio rule, not an exit rule (handover §4.3).

## 2. What is fixed now

| setting | value | why |
|---|---|---|
| universe | `var/state/screen_pairs_pit.json`, bars `XNAS.BASIC` ohlcv-1m | the spread-gate study's book (W03-0002), same sessions, same entry floor (`first_seen`) |
| engines | `strategy/mcl/mcl.py` (LIVE config) and `strategy/mc5/mc5.py` (defaults), via `common.pit_strategy.engine` | the published books |
| size / costs | 100 shares, tiered commission, $4.26 friction per round trip | the project standard |
| **time-cap grid (minutes)** | **none, 5, 10, 15, 30, 60, 120** | MCL: N bars. MC5: N/5 bars (1, 2, 3, 6, 12, 24) |
| **primary cell** | **30 minutes** | roughly the 90th percentile hold in both books (MCL 28 min, MC5 30 min in the W03-0002 trade list): it cuts the long tail that holds a slot (the AEHL case, 154 min) and leaves the typical trade alone. The rest of the grid is a boundary check, not a menu |
| **slot scopes** | **(a) 3 per strategy** (live since 2026-09-23, `cap_scope=strategy`, primary) and **(b) 3 shared** (live before 09-23, `cap_scope=account`) | both have run live |
| tie order | at the same moment exits are processed before entries (an exit frees its slot for an entry in the same minute: optimistic, flagged). Among simultaneous entries, MCL goes before MC5 (the `--strategy MCL+MC5` order), then the universe file's order | the backtest can't know the live watchlist's ranking. **Sensitivity: the same run with the reverse universe order**, reported next to it |
| after a refusal | the turned-away bar is blocked for that symbol and that book **only**. The engine re-runs that symbol-day, so the book can enter on a later bar exactly as the live trader can. The walk then restarts from the start of the day | a simple "drop the trade" pass misses the re-entry the live trader would make |
| event times | entry = signal bar close; exit = close of the exit bar (1-min for MCL, 5-min for MC5) | a stop inside a 5-min bar is treated as holding the slot to the bar's end (conservative for freeing slots) |

**Not in this study:** the live spread gate (`SPREAD_GUARD_PCT`, W03-0002). Its quote windows
only cover the baseline's entry bars, and the gate refuses a bar with no quote. So any arm that
moves an entry onto a different bar would be refused by missing data, not by spread. The live
book, with the gate on, takes about a quarter of these entries, so live slot pressure is **lower**
than modelled here. That can only make the slot case weaker, not stronger. The MC5 give-back
cap (a trader-level rule) is also not modelled.

## 3. What the run must report

1. **The slot cap itself (W03-0003's deliverable)**, with no time cap: for each scope, how many
   entries are turned away, on how many days, what those trades would have netted, and the
   book's net with and without the cap. Checked against the live refusal counts (35, 5, 2, 0, 0
   on 09-21 → 09-25).
2. **For every time-cap cell, in both arms and both scopes:** trades, gross, commission,
   friction, net, wins/losses, the change against the same arm with no time cap, exits by
   reason, and slot refusals.
3. **Paired view** in Arm 1: the same entry under both rules. How many trades the cap changes,
   how many got better or worse, and the total.
4. **Controls on the primary cell's change:** both halves (split at the median scored date),
   drop the 3 best days, and a day-level bootstrap P(change > 0).
5. **Tie-order sensitivity:** the primary cell under the reverse universe order.
6. The standard deliverables: raw `.txt`, CSV of every trade, a monday Result doc in dollars
   and trades, and a published page.

## 4. The decision rule, fixed now

The time cap is put forward for adoption **only if all of these hold at the primary 30-minute
cell under the live scope (3 per strategy):**

1. Arm 2's net change against Arm 2 with no time cap is **above $0**;
2. it is above $0 in **both halves**;
3. it stays above $0 after **dropping the 3 best days**;
4. the day-level bootstrap gives **P(change > 0) ≥ 0.95**;
5. the best cell in the grid is **not at an edge** (5 or 120 min). If it is, the range is in the
   wrong place and no cell is adopted.

If it passes and slot value is above $0, it's argued as a **portfolio rule**. If it passes and
slot value is about zero, it's an exit rule and must also pass the concentration gates the exit
mechanics have always faced. If it fails, **the lever closes**, and any further cap work moves
to ranking which signal gets the slot (`PROGRAM_INDEX` §7 item 4), not to arrival order.

Ben decides after the result: adopt / study-only / close.

## 5. Predictions, written down before the run

- **Arm 1 loses money at every cap, in both books.** The 2026-09-10 MCL study
  (`claude/archive/hold_cap_decision.md`) lost at every cell from 3 to 30 bars, and the loss
  shrank as the cap loosened. The same mechanism applies to MC5: a trailing stop closes losers
  fast, so the trades a time cap reaches are the ones that are still running, which is mostly
  the winners.
- **With 3 per strategy, Arm 2 is almost the same as Arm 1**, within a few hundred dollars at
  every cell. The slot cap barely bites (§6: 2.9% of trades), so a freed slot is rarely needed.
- **With 3 shared, slot value is small and more likely negative than positive.** The trades the
  cap turns away net about the book's average (about $(10)–(14) a trade), so a freed slot
  mostly lets in another average, losing trade.
- **More trades look worse here, whatever the rule.** Every book in this universe loses per
  trade (W03-0002: (131,237) over 10,696 trades with no cap), so any arm that trades more will
  look worse simply for trading more. Trade counts are shown next to every net figure for
  that reason.

If the run disagrees with any of this, the run is the evidence.

## 6. Scoping already done (read-only, 2026-09-27, before this registration)

Taken from the W03-0002 trade list (`var/reports/entry_gates.csv`, MCL + MC5, 549 sessions,
10,696 trades). A simple walk that doesn't re-enter after a refusal, where an exit in the same
minute frees the slot:

| scope | turned away | days affected | net of turned-away trades | per trade |
|---|---:|---:|---:|---:|
| 3 per strategy | 310 (2.9%) | 119 of 549 | (4,446) | (14.34) |
| 3 shared | 1,034 (9.7%) | 260 of 549 | (10,882) | (10.52) |

This is why the predictions in §5 are what they are. The full study replaces these numbers
with the exact walk in §2.

## 7. Timeline

1. **Step 1 (this document):** registered and committed before the runner exists.
2. **Step 2:** `max_hold_bars` on the MC5 engine (MCL already has it), unit-tested, and
   `None` gives exactly the same results as before.
3. **Step 3:** `common/slot_book.py` (the slot walk, W03-0003) and `common/time_cap_study.py`
   (the runner), unit-tested on constructed sessions.
4. **Step 4 (Ben):** run locally.
5. **Step 5:** Result doc, page, raw `.txt`.
6. **Step 6 (Ben):** decision.
