# Handover: what the portal work put into `D:\Trading`

**For the chat that builds strategies in this repo.** Read this before touching
`brokers/ibkr/trader.py`, `common/notify.py`, or anything that writes the fill
log. Nothing here changes strategy behaviour, but four small edits live inside
functions you edit often, and one of them is easy to delete by accident.

Written 14 Sep 2026. Companion doc: `claude/ui_bridge_delivery_20260914.md`.

---

## 1. What landed, exactly

Delivered as a git bundle, not as copied files:
`D:\Trading\Claude outputs\claude-ui-bridge-20260914.bundle` → commit `a085154`
`D:\Trading\Claude outputs\claude-ui-bridge-20260914b.bundle` → adds `e307662`
(the fix in section 9) and this note. `git log --oneline a085154..claude-work`
lists exactly what it carries — a doc that names its own commit hash is wrong
the moment it is committed.

Both on branch `claude-work`. **`b` supersedes the first** — it is the same
branch, so merging it fast-forwards whether or not you merged the first.

| Path | State | Size of change |
|---|---|---|
| `common/ui_bridge.py` | **new** | the whole adapter |
| `tests/common/test_ui_bridge.py` | **new** | 31 tests |
| `brokers/ibkr/trader.py` | **modified** | 4 hooks, ~40 lines |
| `common/notify.py` | **modified** | 1 class attribute, 1 guarded call |

Nothing else in the repo was touched. No strategy module, no backtest, no
commission code, no data path.

Verified on Ben's machine after merging `a085154`: **2156 passed, 3 skipped,
0 failed.** `e307662` adds 5 tests on top of that.
(My sandbox lacks `databento`, so it reports 1337 passed / 5 failed there — the
5 are pre-existing and fail identically on `main`.)

---

## 2. The four hooks in `brokers/ibkr/trader.py`

Located by function, not line number, because line numbers drift.

### 2a. `MCLPaperTrader.__init__` — three attributes

```python
self.paused = False
self.disabled_strategies: set[str] = set()
self.ui = None                  # common.ui_bridge.UIBridge, or None
```

`self.ui` stays `None` unless the environment configures the portal, so every
other hook is a no-op by default.

### 2b. `MCLPaperTrader.step_symbol` — the entry gate

Sits **immediately after** `if not sig.long_entry: return` and **before** the
concurrency-cap check. When paused, or when this strategy is disabled, it writes
a fill-log row and returns:

```python
status="SKIPPED_PAUSED", reject_reason=why
```

**This is the hook most at risk.** `step_symbol` is where entry logic gets
edited, and the gate looks like something that could be moved or merged into a
neighbouring condition. Two properties must survive any edit:

- **It runs after the signal is evaluated, not before.** The bar must still be
  marked evaluated; a gate placed earlier would leave the signal unrecorded and
  re-fire it on the next pass.
- **It writes a row.** Silence would read, to any later analysis, as "the
  strategy never fired" — indistinguishable from a strategy defect. If you add a
  new declined-entry path of your own, write a row there too.

### 2c. `MCLPaperTrader.run` — one call in the loop

```python
if self.ui is not None:
    try:
        await self.ui.tick(self, now_et)
    except Exception as e:
        LOG.warning("portal tick failed: %s", e)
```

After the per-symbol `step_symbol` loop, before `await asyncio.sleep(...)`.
`tick` throttles itself to one push every 5 s, runs its HTTP off the event-loop
thread, and swallows its own failures — the `try` here is belt and braces.

### 2d. `main_async` — attachment, deliberately placed

```python
trader.ui = ui_bridge.UIBridge.from_env()
if trader.ui is not None:
    trader.ui.note_account(accounts[0] if accounts else "")
    tg.observer = trader.ui.record_message
```

**This must stay after the `DU` paper-account check.** Moving it earlier would
let a bridge exist on a session that failed that check. The import line at the
top also changed: `from common import notify, ui_bridge`.

---

## 3. The hook in `common/notify.py`

`Notifier` gains a class attribute `observer = None`, and `send()` calls it at
the very top:

```python
if self.observer is not None:
    try:
        self.observer(text)
    except Exception:
        LOG.debug("portal mirror failed", exc_info=True)
```

**Before** the `self.enabled` check and **before** the rate limiter, on purpose:
the portal shows what the trader *said*, not what Telegram happened to accept,
and it is the only copy when Telegram is unconfigured. If you rework batching or
rate limiting, keep the mirror above them.

---

## 4. Invariants — things that will break quietly if changed

1. **A closed fill publishes its own arithmetic.** Contract 1.4 adds
   `entry_price` and `gross_pnl` to a fill, and fills in `commission`. Gross
   comes from the prices on the row; commission is `gross - trade_pnl`, DERIVED
   rather than recomputed from `common/commissions.py`. A second calculation of
   the same fee agrees with the first until someone changes a schedule and only
   one of them follows — this way the three figures reconcile by construction,
   which is the property a reader checks by eye. Commission is published
   positive, as a cost; the page renders the sign.
2. **The fill log is the only source of trade truth.** `ui_bridge` reads today's
   fills out of the trader's own fill-log CSV. It keeps no parallel ledger. If
   you change the fill log's columns or its `status` vocabulary, `ui_bridge`
   follows — do not add a second store for the portal's benefit.
3. **`SKIPPED_PAUSED` is a `status` value now.** Anything that aggregates the
   fill log (session reviews, backtest parity checks, P&L) must treat it as a
   non-fill, exactly like the existing cap-skip rows.
4. **Paper-only, checked three times.** `from_env()` returns `None` without a
   relay URL and token; `note_account()` sets `is_paper` from the `DU` prefix
   and publishes no commands otherwise; `apply()` refuses again at the point of
   use. Three, because one will eventually be edited by someone who does not
   know why it is there. Do not consolidate them.
5. **`tick()` must never raise into the run loop and must never block it.** Every
   network call is `asyncio.to_thread` with a 3 s timeout; failures go quiet
   after 3 consecutive complaints. A relay that is down must be invisible from
   inside the trader.
6. **`paused` stops new *entries* only.** Open positions keep their trail and
   their exit. A button in a browser must never be able to leave a position
   unprotected. If you add a new "stop everything" path, it must not reach the
   exit logic.
7. **`StrategyAdapter` stays frozen, and the trail change respects that.**
   Changing a trail does not mutate an adapter — `_rebind_adapter` builds the
   next value with `dataclasses.replace` and rebinds **both** references:
   `trader.strategies[i]` and every `SymbolState.strategy`. Miss the second and
   the portal would report the new trail while entries kept stamping the old
   one onto `Position`. If you change how adapters are held — a dict instead of
   a list, a per-symbol copy, a rebuild each loop — update `_rebind_adapter`
   with it.
8. **A CONFIG row is not a trade.** `action="CONFIG"` rows carry no price and
   no `trade_pnl`. Every current reader excludes them on `status` or `action`,
   and a test proves it by running those readers rather than describing them. A
   new reader of this file must gate on one of those two columns.
9. **`trail_pct` changes apply to new positions only**, by construction: the
   trader copies `trail_pct` into `Position` at entry (`step_symbol`), so an
   open position carries the trail it was opened with. The portal states this
   to the user, so it has to keep being true.

---

## 5. What the portal can change at runtime

Only these. Everything else is read-only and says so in the state document.

| Command | Effect |
|---|---|
| `stop` / `start` | `trader.paused` — new entries only |
| `set_strategy_enabled` | adds/removes a name in `trader.disabled_strategies` |
| `set_setting` `max_concurrent_positions` | `trader.max_positions`, 0–10 whole |
| `set_setting` `trail_pct:<strategy>` | that adapter's `trail_pct`, 0.5–20 |

The entry price band is published as **read-only** — changing it is a repo
change, by design.

**Every command writes a CONFIG row to the fill log**, applied and rejected
alike, plus one row per adapter at session open. Shape agreed with the
strategy/database side (`claude/portal_config_row_reply_20260914.md`):

| column | value |
|---|---|
| `action` | `CONFIG` |
| `status` | `APPLIED` or `REJECTED` |
| `symbol` | the setting name, **lowercase** — `trail_pct`, `paused`, `enabled`, `max_positions` |
| `strategy` | the adapter it applied to, **one row per adapter**, never a synthetic `ALL` |
| `reason` | the command type, or `session_open` |
| `reject_reason` | the detail, or the full starting config |
| `trail_pct` | the new value, on a trail change that took effect |

`symbol` carries the setting because `paper_fill`'s key is
`(session_date, ts_et, strategy, symbol, action, status)` at second resolution:
it is the only key field left that separates two *different* settings changed in
the same second by the same strategy. Without it the loader keeps one and drops
the other, and the row that vanishes is the one from the busy moment.

The session-open row exists because a journal that writes only on change cannot
tell "nobody touched it" from "the recorder was broken" — both are an empty
file.

Every field is one that already exists, so there is **no schema change and no
loader change**. If a future row shape needs a NEW column it takes three edits,
not two: `trader.FIELDS`, `db.paper_fill`, **and** `load_paper_fills`. The third
is the one that gets missed — a column in the first two and absent from the
third loads as null on every row while every test passes. That happened to
`trail_pct` on 14 Sep.

`tests/common/test_config_row_is_invisible_to_readers.py` drives the real
`load()` functions of churn_count, friction, tv_reconcile and ui_bridge over the
same book with and without CONFIG rows, and asserts the trades and the P/L come
back identical. It drives the readers rather than restating their gates,
because a restatement passes while the reader it describes changes.

If you add a parameter you want controllable from the portal, add it to
`UIBridge._settings` with a `set_command`, and handle its key in
`_set_setting`. The UI renders whatever the state document advertises; it needs
no change and knows nothing about this repo.

---

## 6. Turning it on and off

Off unless both of these are set:

```
UI_RELAY_URL        http://127.0.0.1:8000
UI_AGENT_TOKEN_FILE D:\Trading UI\var\agent_token.txt
```

Optional: `UI_AGENT_TOKEN` (inline instead of a file), `UI_AGENT_ID` (defaults
to the hostname), `UI_PUBLISH_DRY=1`.

**A dry run does not publish.** `main_async` passes the session's mode to
`from_env`, which returns `None` for `--mode dry` unless `UI_PUBLISH_DRY` is
set to an affirmative value. The relay holds one state document, so a dry
session and the production session both publishing would flip the dashboard
between two traders and send a command to whichever polled first. That gate is
what lets the settings live at machine level instead of being two lines someone
has to remember to type.

Unset `UI_RELAY_URL` and the trader runs exactly as it did before
`common/ui_bridge.py` existed. For a strategy or backtest session, leave them
unset and ignore all of this.

---

## 7. The other repo, and why it is separate

The portal lives in `D:\Trading UI` (`github.com/bgysiu85/algo-trading-ui`) and
is deliberately independent — MVC, at Ben's request. It knows nothing about
trading: it renders whatever state document arrives and offers whatever commands
that document advertises.

The only coupling is a versioned JSON contract, currently **1.4**, declared in
`ui_bridge.CONTRACT_VERSION`. If you change the *shape* of what `build_state`
emits, that is a contract change and belongs in the UI repo's
`contract/schema/`, not here.

Running: relay on `127.0.0.1:8000` (Windows logon task "Trader relay"), behind a
Cloudflare Tunnel at `https://trader.thesiuz.com`, behind a Pocket ID passkey at
`https://id.thesiuz.com`.

---

## 8. If you hit a merge conflict

The four hooks are small and self-describing. In a conflict, keep both sides:
the strategy change and the hook are never solving the same problem. The one to
read carefully is the `step_symbol` gate — check it still sits after the signal
evaluation and still writes its row.

To see exactly what the commit did:

```powershell
cd "D:\Trading"
git show a085154 --stat
git show a085154 -- brokers/ibkr/trader.py common/notify.py
git show e307662 -- common/ui_bridge.py
```

---

## 9. One defect already found and fixed, worth knowing about

`e307662` fixes a bug that every test in `a085154` passed over. `apply()` did
`adapter.trail_pct = value` on a **frozen** dataclass, which raises
`FrozenInstanceError`. The test double for the adapter was an ordinary object,
and an ordinary object accepts any attribute you set on it — the fake was more
permissive than the real class, so the tests agreed with each other and
disagreed with production.

Worth carrying into this repo's own testing: a double that is more permissive
than the thing it stands in for can hide a defect completely. The new tests use
real `StrategyAdapter` instances via `SA.build_all`, and one of them fails if
anyone unfreezes the class to make a future change easier.
