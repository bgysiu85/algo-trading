# Handover — MEDS ghost position: a lost exit fill, then 3.5 hours of short-sale orders

From: live paper-trade analysis chat (read-only on production).
To: strategy build and test chat.
Written 2026-09-16 ~09:55 ET, after the session.

**Production was only read.** Tree `D:\TradingProd` @ `prod-20260916b` (`31b7184`),
clean. Line numbers refer to that commit. Operational steps Ben took, with no files
changed: stopped the trader (Ctrl+C) and cancelled all open paper orders with
`reqGlobalCancel` (account checked as `DU` first).

**Current state, confirmed by `show_trades.ps1` at 09:51 ET:** account `DUM215828` flat,
MEDS 0, no open orders, NetLiquidation 21,209.14.

**Severity: CRITICAL.** The trader's picture of the account and IB's disagreed for
3.5 hours. Every order it sent in that time would have **opened a short position**
if it had filled.

---

## 1. What happened

    06:16:04  MC5 MEDS BUY 100 @ 3.82 FILLED            (signal close 3.9103)
    06:17:07  SELL trailing_stop limit 3.68  NO_FILL_ABANDONED after 0.51s
              (bid 3.69/ask 3.70 at send; 3.67/3.68 when abandoned)
    06:17:08 → 09:30   806 more trailing_stop SELLs, every one NO_FILL
    09:30:24 → ~09:45  window_close SELLs, every one NO_FILL
    09:44 ET  IB: MEDS position 0; open order SELL 100 LMT 4.31 PreSubmitted (client 17)

Fill log `D:\Trading\var\fills\mcl_fills_20260916.csv`: ~500 `NO_FILL_ABANDONED` and
~390 `NO_FILL_CANCELLED` rows for MEDS, **zero `REJECTED`**. Every other exit in the
session filled first time (19 round trips). Many of the MEDS orders were priced a cent
**below the bid** on a 1-cent-spread, multi-million-share stock and still did not fill in
20 s. That is not a liquidity event.

The portal showed MEDS as an open MC5 position all morning, with a live Open P&L
(+59.50) and a Stop (4.55). Those numbers come from the trader's own state, not from IB.

## 2. Root cause (strongly supported; the exact exit fill is still to be read)

**The first exit order filled at IB after the trader had stopped listening for it.**

`marketable_limit()` in `brokers/ibkr/trader.py` ~L1262–1390:

1. Places the SELL, then polls every 0.25 s.
2. **New today** (commit `971e88a`, "an exit does not wait out the timeout when its
   limit cannot fill", first promoted in `prod-20260916`): if the bid is below the limit
   for `EXIT_ABANDON_POLLS = 2` consecutive polls, it breaks out.
3. Right after the break it computes
   `filled = int(sum(f.execution.shares for f in trade.fills))`. That's a
   **snapshot at that instant**.
4. `filled == 0`, so it calls `self.ib.cancelOrder(order)`, writes `NO_FILL_ABANDONED`
   and returns `None`. **It never waits for the cancel to be confirmed.** An execution
   that is in flight, or that IB matched before the cancel arrived, is never counted.
5. `st.position` stays at 100. The next loop sends another SELL 100 into an account that
   is already flat. IB treats it as a **short sale** and holds it unfilled
   (`PreSubmitted`), which accounts for every no-fill that followed.

This was the **only abandonment of the day**, on the first session the feature ran, and
it is the one that lost its fill. The feature exists because of CRBP 09-14. The idea is
right, but it is unsafe as built.

## 3. Defects to fix (in `D:\Trading`, with tests)

**D1 — Never decide an order's outcome before IB confirms it is finished (CRITICAL).**
After any cancel (abandon, timeout or partial remainder), wait for
`trade.isDone()` / a terminal `orderStatus` (`Cancelled`, `Filled`, `ApiCancelled`,
`Inactive`) with a bounded wait. **Then** read `trade.fills`. A cancel that comes back
as `Filled`, or partly filled, must be recorded as a fill. If no terminal status arrives
within the bound, the outcome is **unknown**. Treat it that way (D2), never as a no-fill.
The partial-fill path (`if filled < qty: cancelOrder`) has the same race for the
remainder.

**D2 — Check against IB's position before every exit re-send (CRITICAL).**
Before sending another SELL for a position whose previous exit didn't fill, compare
`st.position.qty` with `ib.positions()` for that contract. It's already fetched at ~L904
for adoption.
- IB flat → close the position locally as filled at an unknown price (from
  `ib.fills()` / `reqExecutions` if available), write a distinct fill-log row (for
  example `status=RECONCILED_FLAT`), and send nothing.
- IB shows less than the trader thinks → size the sell to IB's number.
- **Never send a SELL for more than IB says is held.** A long-only trader must be
  unable to go short.

**D3 — Bound the retry loop (HIGH).**
858+ attempts on one position with no escalation. After N consecutive exit no-fills (for
example 5), stop sending, raise a loud alert (Telegram + portal) and mark the position
`NEEDS_ATTENTION`, not open. Also check IB order status for `PreSubmitted` held orders on
a SELL. A held sell for a long-only book is itself a signal that the position is gone.

**D4 — Ghost positions consume the concurrency cap (MEDIUM, a consequence).**
MEDS held one of the 3 slots from 06:17 to 09:30. **9 entry signals** were logged
`SKIPPED_CONCURRENCY_CAP` after that (09:20, 09:23, 09:26 among them). D2 fixes this, but
a test should pin it.

**D5 — Peak misses bar highs while an order is waiting (MEDIUM).**
Ben saw a 4.96 high; the trader's peak reached 4.79 (stop 4.55 = 4.79 × 0.95). The bar
path feeds only `df["high"].iloc[-1]` (~L1618–1626), and the fast loop feeds only the
ask. While `marketable_limit` blocks for up to 20 s, bars close unseen, and a skipped
bar's high is never read. Fix: feed the max high of **all** bars closed after the later
of `entry_time` and the last bar consumed. This had no effect today (exit was already
triggered), but it makes every trailing stop looser or tighter than Pine at random.

**D6 — `window_close` rows alternate between two references (LOW, logging).**
From 09:30 every other row has `ref_close = 4.04` (a stale bar close from the bar path)
and the others use the current quote. Prices sent to IB weren't affected, but
`slippage_vs_ref` on those rows is meaningless and `common/friction.py` will read it.

**D7 — `show_trades.ps1` crashes on executions (LOW, tooling).**
`common/report_trades.py` L111: `e = f.execution`, then `e.contract.symbol`. `Execution`
has no `contract`; it's `f.contract.symbol`. This hid today's executions exactly when
they were needed.

**Also still open from this morning** (`claude/handover_session_open_bugs_20260916.md`):
the peak seeded from the signal close. MEDS was seeded at 3.9103 against a 3.82 fill, so
the stop started at 3.7148 instead of 3.629. It made no difference to today's outcome.

## 4. Tests to add

- A fake IB whose `cancelOrder` results in `Filled` (fill event after the abandon
  break) → position closed, row `FILLED`, no further SELL sent.
- The same with a cancel that confirms nothing within the bound → outcome unknown, IB
  position checked, no blind re-send.
- A partial fill whose remainder fills during cancel → both fills counted.
- IB position 0 while local qty 100 → no SELL placed; reconciliation row written; cap
  slot released.
- A SELL quantity can never exceed IB's position (property test).
- N consecutive exit no-fills → alert raised, sending stops.
- Peak: bars closed during a 20 s order wait still update the peak.
- `report_trades.snapshot` with a real `Fill` object → no crash.

## 5. Still unknown / to read

- **The MEDS exit price.** IB executions weren't visible (D7). Pull from the IB Flex
  statement or a fixed `show_trades`. The limit was 3.68, so the fill was probably ~3.68–3.70,
  roughly (12)–(15) after commission. **Today's fill-log net of 212.95 over 19 round trips
  excludes MEDS.**
- Whether any other order across past sessions was lost the same way. Only MEDS was
  abandoned today, and the feature didn't exist before today, but the timeout and partial
  paths have the same race (D1). Reconcile past fill logs against Flex executions.

## 6. Promotion

Nothing mid-session. Until D1 and D2 are in, **consider reverting the abandon feature
(`971e88a`) for tomorrow's session.** The old 20 s timeout cost CRBP (241.37) once in
two weeks; this cost 3.5 hours of unmanaged short-sale orders on its first day.
