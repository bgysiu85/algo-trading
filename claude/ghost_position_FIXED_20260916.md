# The MEDS ghost, fixed — and the mirror image it exposed

2026-09-16. Answers `claude/handover_meds_ghost_position_20260916.md`. All seven items
done in `D:\Trading`, 17 new tests, 16 mutations caught, suite **3,055 green**.
**Promotion after the close — this session is over, so tonight, before tomorrow's 04:00.**

---

## What happened, in one paragraph

The abandon path (`971e88a`, first promoted this morning) broke out of its poll loop,
read `trade.fills` in that same instant, saw nothing, sent a cancel, and wrote
`NO_FILL_ABANDONED`. The fill landed at IB between the read and the cancel. The trader
kept 100 shares on its books the account no longer held, sent 850+ more SELLs into a
flat account over 3.5 hours — each a short sale had it filled — held a concurrency slot
the whole time, and declined nine real entries for it.

**Every one of those was a decision made on a snapshot IB had not confirmed.** That is
the one defect; D1 through D4 are its four faces.

---

## D1 — an order's outcome is not known until IB says it is finished

`marketable_limit` now calls `_settle(trade, order)` after any cancel: send the cancel,
wait up to **`CANCEL_CONFIRM_S = 3.0`** for `trade.isDone()`, and **only then** read
`trade.fills`. Three outcomes, three rows:

| IB says | row | position |
|---|---|---|
| filled during the cancel | `FILLED` (or `PARTIAL_FILL`) | closed — the MEDS case |
| cancelled, nothing filled | `NO_FILL_ABANDONED` / `NO_FILL_CANCELLED` as before | held |
| nothing terminal within the bound | **`ORDER_UNKNOWN`**, `st.unknown_order = True` | unchanged, and nothing is sent until IB's position has been read |

The partial-fill path had the same race for its remainder. Its own settle was written,
and then **removed when mutation showed it could never run** — every path reaching the
fill-count line already has a terminal status from the first settle. A guard that cannot
fire is the shape this whole fix exists to remove, so it is gone rather than kept as
reassurance.

## D2 — before any re-send, ask IB what the account holds

In `manage_position`, on **every attempt after the first**, and on any attempt following
an unknown outcome, `_ib_held(st)` reads IB's own position (a local snapshot of pushed
positions — no pacing cost):

| IB holds | action |
|---|---|
| unreadable | **send nothing.** A long-only book that cannot verify what it holds must not risk going short |
| 0 | `_reconcile_flat`: release the position, send nothing, free the slot |
| less than the trader thinks | `RECONCILED_QTY` row; size the exit to IB's number |
| at least what the trader thinks | proceed |

**The first attempt trusts local state**, deliberately: IB's position push can lag a fill
by a moment, and refusing a legitimate first exit would leave a real position unmanaged.
Tested in both directions.

`_reconcile_flat` looks for the sell in `ib.fills()`. When IB can show it, the row is an
ordinary **`FILLED`** with `reason=reconciled_flat` and the real price and P/L, so every
downstream reader that pairs BUY and SELL rows keeps working. When it cannot, the row is
**`RECONCILED_FLAT`** with no price: the position is gone and its P/L is unknown, and no
reader is told otherwise. **The MEDS exit price is still to be read from the Flex
statement** — this code would have booked it at 06:17:08.

## D3 — past five attempts with IB confirming the shares, alert once and slow down

Not stop: by then IB has confirmed the position is real and it still needs an exit. After
`MAX_EXIT_ATTEMPTS = 5` the trader sends one Telegram + `NEEDS ATTENTION` log line, marks
`pos.needs_attention` for the portal, and retries every `EXIT_RETRY_BACKOFF_S = 30`
instead of every second. Tested that it alerts once, throttles, and resumes.

## D4 — a released ghost frees its slot

Automatic once `st.position` is None; a test pins it with `max_positions=1`.

## D5 — every bar that closed during an order wait feeds the peak

`marketable_limit` can block for twenty seconds; bars close unseen; the bar path fed only
the newest. Now it feeds the max high of every bar after the later of `entry_time` and
`pos.last_bar_seen`. Ben's 4.96 against the trader's 4.79 was this.

## D6 — `window_close` is measured against the quote, from both loops

A flatten is triggered by the clock, not a bar. The bar path was passing a stale close
and the fast loop the quote, alternating row by row, so `slippage_vs_ref` meant two things
under one heading — and `friction.py` reads that column.

## D7 — `show_trades` no longer crashes on executions

`f.contract.symbol`, not `e.contract.symbol`. A test drives `snapshot()` with a real
Fill shape.

---

## The mirror image, found by the mutation pass

Testing D2's `or st.unknown_order` clause found it could never be the deciding factor:
every case that sets the flag already has `exit_attempts > 1`. Dead code — until you ask
when an **entry** goes unknown. A BUY whose cancel IB never confirms can leave 100 shares
in the account with **no position on the book**: unmanaged, untrailed, and free to be
bought again on the next signal. **The reverse ghost.**

`_adopt_unknown_entry` now runs after any unknown BUY: read IB; if it holds shares, adopt
them at IB's average cost with the flag left set, so the **first** exit reconciles. That
makes the clause load-bearing and testable, and it closes a hole the handover did not
list.

---

## Revert `971e88a`?

**No.** The abandon feature was right about the market (CRBP cost $241 waiting out a
20-second timeout) and wrong only in reading a snapshot. With D1 the snapshot is gone.
Reverting would restore the timeout path, which had the same race with a longer fuse.

---

## Commands — from `D:\Trading`, one line at a time

```
git -C D:\Trading pull "D:\Trading\Claude outputs\20260916y.bundle" main
```

```
python -m pytest tests/brokers/ -q
```

Then promote — **tonight, before 04:00 ET**, and only with the trader stopped:

```
git -C D:\Trading tag prod-20260916c
```

```
git -C "D:\TradingProd" fetch "D:\Trading" --tags
```

```
git -C "D:\TradingProd" checkout prod-20260916c
```

```
python -m common.provenance --expect-shared-var D:\Trading\var
```

The last line is the junction check from the runbook; it must say the shared `var/` is
in place. Tomorrow's session runs from `D:\TradingProd` as usual, and the first thing to
look for in the log is that no `ORDER_UNKNOWN` or `RECONCILED_*` row appears — if one
does, it worked, and the row says what IB actually did.

**Still to read:** the MEDS exit price from the Flex statement, and whether any earlier
session lost a fill the same way on the timeout path. Today's net of +212.95 over 19 round
trips excludes MEDS.
