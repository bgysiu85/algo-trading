# Portal milestones 2 and 3 — delivered 14 Sep 2026

Two bundles, one per repo. Both are self-contained (full history), so a
fetch works regardless of what the local clone has.

| Repo | Bundle | Branch | Head |
|---|---|---|---|
| `D:\Trading UI` | `Claude outputs\claude-20260914a.bundle` | `claude-work` | `20c5913` |
| `D:\Trading` | `Claude outputs\claude-ui-bridge-20260914.bundle` | `claude-work` | `a085154` |

## Milestone 2 — the relay starts itself

`tools/install_relay_task.py` registers a Windows scheduled task that runs
`tools\run_relay.py --port 8000 --log` at logon.

**ONLOGON, not ONSTART.** `pip` installed uvicorn and fastapi into the user
profile. The SYSTEM account cannot see them, so a boot-time task would die on
the import with nothing to show for it. A logon task runs as Ben, with Ben's
packages, and needs no stored password.

**pythonw.exe, not python.exe**, so no console window appears at every logon.
That is why `run_relay.py` grew `--log`: under `pythonw` both `stdout` and
`stderr` are `None`, and uvicorn's first log line would raise. `--log` opens
real files (`var\relay.log`), which also leaves a trail to read when something
goes wrong.

The trade-off, stated plainly: the portal is up while Ben is logged in and down
when he signs out. Fixing that is not a better scheduled task — it is moving the
relay to the cloud, which is milestone 4.

## Milestone 3 — the live trader is the publisher

The portal has been fed by `agent/replay.py`, which reads yesterday's fill log.
That proved the contract; it proved nothing about the trading repo.
`common/ui_bridge.py` is the adapter that makes the real trader publish.

It builds a contract-1.3 state document out of the trader it is handed —
session clock, per-strategy P&L, open positions with stop levels, today's fills,
watchlist, the settings safe to change — pushes it every 5 s, and applies
commands that come back.

Three things it deliberately does not do.

**It keeps no second copy of anything.** Fills come from the trader's own
fill-log CSV, positions from the position book, parameters off the
`StrategyAdapter`. A number in the browser that disagrees with the log would be
worse than no browser at all.

**It never touches a live account.** `from_env()` returns `None` unless relay
URL and token are both set; `note_account()` reads the `DU` prefix and publishes
no commands otherwise; `apply()` refuses again at the point of use. Three checks
because one of them will one day be edited by someone who does not know why it
is there.

**It never fails loudly.** Every call is in `asyncio.to_thread` with a 3 s
timeout, failures are swallowed after three consecutive complaints, and `tick()`
cannot raise into the run loop.

### The hooks in the trader

Four lines of state in `__init__`, one entry gate, one `tick()` in the run loop,
one attachment in `main_async` *after* the `DU` check.

`paused` stops **new entries only**. An open position keeps its trail and its
exit, because a button in a browser must not be able to leave a position
unprotected. A declined entry is written to the fill log as `SKIPPED_PAUSED`
beside the existing cap rows — an absence there would read as "the strategy
never fired".

`Notifier` grows an `observer`, called *before* the enabled check and the rate
limiter, so the portal shows what the trader **said** rather than what Telegram
happened to accept — and still shows it when Telegram is unconfigured.

### Switching the portal from replay to live

Stop `agent/replay.py`, then set these before starting the trader:

    UI_RELAY_URL        http://127.0.0.1:8000
    UI_AGENT_TOKEN_FILE D:\Trading UI\var\agent_token.txt
    UI_AGENT_ID         (optional; defaults to the hostname)

Unset `UI_RELAY_URL` and the trader runs exactly as it did before this file
existed.

## Tests

- `D:\Trading UI` — 87 passed.
- `D:\Trading` — 1337 passed, 44 skipped, 5 failed. The 5 are the same
  `databento`-missing failures that fail identically on `main` (baseline: 1306
  passed, same 5 failed). Nothing regressed; the 31 new tests are
  `tests/common/test_ui_bridge.py`.

## Next

Milestone 4: the relay in the cloud, so the portal survives signing out.
Then: daily loss stop with backtest parity, the Claude panel, config-edit audit
trail.
