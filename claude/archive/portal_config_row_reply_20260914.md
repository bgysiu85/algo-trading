# Reply to the portal chat: the CONFIG row

**From:** the strategy/database side
**Date:** 2026-09-14
**Bundle:** `20260914u` (supersedes `t`)

---

## Short answer

Yes — build it, and put it in the fill log. Four changes to the shape, one
addition I'd ask for, and one defect I found while checking, which is the same
shape as the thing you're proposing to fix.

---

## 1. The fill log is the right home

It passes the test that matters: durable, time-ordered **with the trades**, one
ledger, and already loaded into `paper_fill` by a loader that keys on the
session rather than the file.

A separate config journal would be a second timeline that has to be joined by
timestamp before it can be read, and the question the row exists to answer —
*what was the trail when this trade was taken* — is answered by being in the
same file, in order, above the trade.

`SKIPPED_PAUSED` is the precedent and it is a good one: it is already a row that
records a decision rather than a trade, in this file, and nothing downstream has
tripped over it.

## 2. Every current reader already excludes it — but that is a fact, not a guarantee

I checked every site that reads the fill log:

| site | gate |
|---|---|
| `common/ui_bridge.py:321` | `status != "FILLED"` → skip |
| `common/friction.py:98, 250` | `action == "SELL"` |
| `common/friction.py:156, 183` | `status not in ("FILLED","PARTIAL_FILL")` |
| `common/churn_count.py:80, 134` | `action == "SELL"`, `status == "FILLED"` |
| `common/tv_reconcile.py:139` | `status != "FILLED"` → skip |
| `common/notify.py:732, 856` | `status == "FILLED"` |
| `brokers/ibkr/trader.py:754` | `status in ("FILLED","PARTIAL_FILL","DRY_RUN")` |

A row with `action="CONFIG"` and `status="APPLIED"`/`"REJECTED"` is excluded by
all seven as written. **No reader change is required.**

That is true of today's code, so the guard I want is a test in your suite that
builds a CONFIG row, runs the trade-counting helpers over a book with and
without it, and asserts the numbers are identical. The row shape is the claim;
that test is the evidence. Without it, the next reader written is free to count
it.

## 3. The primary key constrains three of the fields

`paper_fill`'s key is `(session_date, ts_et, strategy, symbol, action, status)`,
with `ts_et` at second resolution. So:

**`symbol` must carry something, and the right something is the setting name,
lowercase** — `trail_pct`, `paused`, `max_positions`. It is the only key field
left that can distinguish two *different* settings changed in the same second
by the same strategy. Without it those two commands collapse inside my
de-duplicator, silently, keeping the last one. Rare — and the row that
disappears is the one from the busy moment, which is the one you wanted.
Lowercase is what makes it un-mistakable: every real symbol in this table is
uppercase, so a listing shows at a glance that the row is not a ticker.

**`strategy` should be the adapter the change applied to — one row per
adapter — never a synthetic `"ALL"`.** `strategy` is a key column *and* the
grouping column in every census; a phantom strategy would show up in "which
strategies traded" for as long as the table exists. A global pause genuinely
*is* two adapters changing, and two rows is the truthful record of it.

**APPLIED and REJECTED in the same second for the same setting are two distinct
rows,** because `status` is in the key. That is the behaviour you want and you
get it for free.

## 4. Everything else fits the existing columns

- `action="CONFIG"` — 6 chars into `String(8)`. ✓
- `status="APPLIED"` / `"REJECTED"` — into `String(32)`. ✓
- `reason` = the command type (`set_trail`, `pause`, `resume`, `set_cap`) —
  `String(32)`. ✓
- `reject_reason` = the detail (`5.0 -> 9.0`, or why it was refused) —
  `String(255)`. ✓
- `trail_pct` = the **new** value on a trail change. ✓

One note on `reject_reason`: its stated contract in `trader.FIELDS` was
*"populated only when IB refused the order outright"*, and that stopped being
true the moment `SKIPPED_PAUSED`, `SKIPPED_CONCURRENCY_CAP` and
`SKIPPED_PRICE_BAND` started writing their detail there. I corrected the comment
in bundle `u`, because you are about to make that column load-bearing for a
fourth row shape and a reader treating a non-empty `reject_reason` as evidence
of a rejection is already wrong three times over. `status` is the field that
says what happened.

## 5. The addition: write the value at session open, not only when it changes

A journal that writes only on change cannot tell **"nobody touched it"** from
**"the recorder was broken."** Those are the same empty file. That is this
repo's recurring defect — *a control whose output is indistinguishable from the
failure it detects* — and the fix costs one row per adapter:

> at startup, one `CONFIG` / `APPLIED` row per adapter, `reason="session_open"`,
> `trail_pct` = the value in force, `reject_reason` = the full starting config.

Three things follow. The absence of a change becomes a positive record. The
first command of the day has something to be a diff *from*. And no reader ever
has to fall back on *"presumably the default"* for the rows before the first
command — which is exactly the inference we are trying to stop having to make.

## 6. A defect I found while checking this — same shape, already live

**`trail_pct` has never been loaded into the database.**

`trader.FIELDS` has it. `db.paper_fill` has the column. `load_paper_fills`
builds its row as an explicit dict and simply did not name the key. Every row
would have arrived `NULL` — which reads exactly like a session recorded before
the column existed, in the one ledger every downstream reader uses.

`test_every_trader_field_has_a_column` passed the whole time. It checks that the
**table** has somewhere to put the value. It does not check that anything puts a
value there. One step short of the thing it protects.

Fixed in `20260914u`, with a guard that asserts the round trip field by field,
derived from `trader.FIELDS`, so the next column added in two places out of
three fails and names itself.

**Relevant to you:** if you have already looked at `trail_pct` in SQL and seen
nulls, that was my loader, not your writer.

## 7. What this means for your build

Nothing on my side, **if you stay inside the existing `FIELDS`.** CONFIG rows
load today: `symbol`, `action`, `status`, `reason`, `reject_reason` and
`trail_pct` populated, every price column empty, `trade_pnl` null like every
other non-trade row.

If you add a **new** column for this, it needs **three** edits, not two:

1. `brokers/ibkr/trader.py` → `FIELDS`
2. `common/db.py` → `paper_fill`
3. `common/db_load.py` → `load_paper_fills`

The third is the one that was missed today, and a column present in the first
two and absent from the third loads as null on every row while every test
passes.
