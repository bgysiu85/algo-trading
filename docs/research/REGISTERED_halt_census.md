# REGISTERED — trading halts on the exchange tape: what the status schema holds, how often the universe is halted, and what it did to the books

`PROGRAM_INDEX` §7 item 24: "Model LULD halts. 36.4% of Tier 2 pauses fall
09:45–09:50 ET; ORB enters exactly there." Nothing in this project has ever
read a halt off the tape. The live trader's stops are software-managed Day
Limit orders (§5, IB / live); a halted name cannot be sold until it resumes,
and the resumption print is where a 5% trail becomes whatever the gap is.

**Priced before this was written: XNAS.ITCH `status`, 2024-07-01 → 2026-09-17,
27 monthly chunks, 1,063.5 MB, $0.00 (inside the free window).** Committed
before the pull and before `common/halt_census` has run.

## 1. What is run

1. `databento_universe --dataset XNAS.ITCH --schema status --start 2024-07-01
   --end 2026-09-17 --confirm` → `E:\Databento\XNAS.ITCH\status\<month>.dbn.zst`.
2. `common/halt_census` over those chunks, joined to
   `var/state/screen_pairs_pit_itch_v2.json`, with the MCL and MC5 baseline
   books from `first_entry_skip --pairs <v2> --dataset XNAS.ITCH` (which is
   also §7 item 1c's re-basing of H-B1, run once for both purposes).

## 2. What is read, fixed now

1. **What the schema holds.** A crosstab of `action` × `reason` over the
   whole pull, with `is_trading` / `is_quoting`, printed before anything is
   interpreted. A halt is `action ∈ {HALT, PAUSE, SUSPEND}`; a resumption is
   the next record for that instrument with `action = TRADING` or
   `is_trading = true`. A halt still open at 20:00 is counted as open, not
   dropped.
2. **On the v2 universe symbol-days** and, beside them, on every symbol the
   tape carries that day: halts starting in 04:00–09:30 and in 09:30–16:00,
   by reason; the share of symbol-days with at least one; halt start times by
   half hour; durations (p10/p50/p90); halts open at 09:30.
3. **On the books.** For each MCL and MC5 baseline trade: did a halt on that
   name begin between entry and exit, or was the exit bar the resumption bar?
   Count, share of trades, net per trade at $4.26 for those trades against
   the rest, exit reasons. Both denominators are not at issue — this is a
   description of a subset, not a comparison of rules.

## 3. Predictions

- **LULD pauses (reason 50) do not occur before 09:30** — the bands are not
  in force pre-market. Any pre-market halt is regulatory (news pending, 30) or
  administrative.
- Universe symbol-days with a halt starting in 04:00–09:30: **2–6%**; in
  09:30–16:00: **10–25%** (these are the day's biggest movers; LULD pauses
  cluster in them).
- Halt starts after 09:30 concentrate in the first half hour: **≥ 30% of RTH
  halts on universe names start 09:30–10:00**.
- Pre-market regulatory halts run long: median **≥ 30 min**; LULD pauses
  short: median **5–10 min**.
- MCL trades that span a halt: **under 1%**; those trades lose more than the
  book, by **$10 or more per trade**, and their exit reason is a stop or the
  window close, not a signal.

## 4. What this decides, and what it does not

- Decides nothing about a strategy. It sizes a live risk the backtests do
  not model (§4 universal caveats will gain a line) and gives the ORB chat
  the 09:30–10:00 halt density on the tape of record for item 24.
- If halted trades are common or catastrophic, a halt-aware exit is a
  *separate* registration with a predicted delta; it is not read off this
  census.
- No pull beyond the one priced above. `holdout.json` stays shut.
