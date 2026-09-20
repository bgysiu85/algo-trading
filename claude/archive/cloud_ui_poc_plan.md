# Cloud UI — proof-of-concept plan

**Status 2026-09-13: milestones 1 and 2 are done.** Replay → relay → UI works, the command
round-trip is acknowledged end to end, and the portal is reachable from the iPad at
`https://trader.thesiuz.com` — behind a Pocket ID passkey rather than Cloudflare Access,
which §7 below still names. **Milestone 3, the real trader, is next.** Written 2026-09-13. Companion to
`cloud_ui_design.md`, which holds the architecture and the open design questions.
PoC code and files live in `D:\Trading UI`; `D:\Trading` stays reference-only until
milestone 3.

---

## 1. What the PoC is for

**The question:** does the relay pattern work — the trader pushing state *outbound* to a
web app, a browser showing it, and a command coming back and being acknowledged?

**Not the question:** whether any strategy makes money, whether fills are good, or which
broker to use. The PoC deliberately touches no broker and no market data, so it costs
nothing and can be run at any hour instead of at 04:00 ET.

**Budget: $0 through milestone 2.** ~$10/yr only if a personal domain is preferred over
Cloudflare's throwaway URL. Hosting cost starts at milestone 4 and is
$2–6/mo (`cloud_ui_design.md` §4).

## 2. Non-goals for the PoC

Config edits · the Claude panel · passkeys · flatten / kill switch · charts · multi-strategy
views · the VPS move · any change to `D:\Trading`'s trading logic.

Each is deliberately deferred; none of them changes whether the pattern works.

## 3. Shape

```
milestones 1-2                          milestone 3                 milestone 4
replay.py  ──push──▶ relay+UI (laptop)  trader ──push──▶ relay+UI    relay+UI on Fly.io
           ◀─poll──  (localhost, then   (ProArt)         (ProArt)    trader still at home
                      Cloudflare Tunnel)
```

One FastAPI app throughout: relay API + the single UI page. The only thing that changes
between milestones is *who pushes* and *where the app runs* — never the app itself. That is
the property the PoC is testing.

## 4. Milestones and done criteria

| # | Milestone | Done when | Cost |
|---|---|---|---|
| **1** | **Replay → relay → UI, all local** | `replay.py` pushes a recorded session; the page at `localhost:8000` shows connection status, open positions, today's fills and session P/L, and updates without a manual refresh | $0 |
| **2** | **Command round-trip + reachable from the phone** | Pressing **Pause** in the UI is picked up by the replay client, which reports back `applied` (or `rejected` + reason); the UI shows *pending → applied* and never shows a state the client didn't confirm. Reachable over a Cloudflare Tunnel with Cloudflare Access login | $0 (~$10/yr with own domain) |
| **3** | **Real trader instead of replay** | The paper trader on the ProArt pushes the same messages; Pause actually stops new entries; killing the relay mid-session leaves the trader trading normally and the UI shows *stale, last contact HH:MM:SS* | $0 |
| **4** | **Same app in US-East** | Identical app deployed to Fly.io; the trader reconnects to the cloud URL with no code change; survives an overnight run and a laptop reboot | $2–6/mo |

**Stop-and-rethink criteria:** if milestone 2's acknowledgement path needs special cases per
command, or milestone 3 shows the trader's loop stalling while it pushes, the design is
wrong and gets revisited before more is built.

## 5. Message contract (draft — to settle before coding)

Three endpoints, JSON both ways, bearer token in a header.

| Direction | Endpoint | Carries |
|---|---|---|
| trader → relay | `POST /api/state` | `sent_at`, `account` (must be `DU…`), `mode` (`paper`/`dry`), `strategy`, `paused`, `positions[]`, `fills_today[]`, `pnl` with `friction_charged: true|false`, `watchlist[]` |
| trader → relay | `GET /api/commands` | returns queued commands, each `{id, type, args, issued_at}` |
| trader → relay | `POST /api/commands/{id}/ack` | `{status: applied\|rejected, detail}` |

Rules baked in from the start, because they are cheaper now than later:

- **Full state each push, not deltas.** A missed push then costs nothing.
- **Every P/L figure carries `friction_charged`** — `PROGRAM_INDEX.md` §1.
- **The relay refuses to hand out commands** unless the last state said a `DU` paper
  account. Second guard behind the trader's own.
- **Command types are an allowlist.** PoC ships `pause` and `resume` only.
- **Push cadence:** every 5 s while a session is open, 60 s otherwise. Push must never block
  the trading loop — fire-and-forget with a short timeout, like `common/notify.py` does for
  Telegram.

## 6. `replay.py` — the stand-in trader

Lives in `D:\Trading UI`. Reads a finished session and replays it as if live:

- Input: a fill log CSV from `D:\Trading\var\fills\` (columns `ts_et, symbol, action,
  fill_price, filled_qty, trade_pnl, …`) plus a `watchlist.txt` snapshot.
- Rebuilds positions over time from the buy/sell rows, and pushes the same `/api/state`
  shape the trader will.
- `--speed 60` replays an hour a minute; `--speed 1` runs in real time for an overnight
  soak test.
- Polls `/api/commands`; on `pause` it stops emitting new entries, acks `applied`, and keeps
  managing the positions already open — the same semantics the trader will implement.
- Read-only on `D:\Trading`; copies nothing into it.

It stays useful after milestone 3, as the way to exercise the UI without waiting for a
session — including cases a live session rarely produces (a rejected command, a stale feed,
a position held over a disconnect).

## 7. Which open questions the PoC answers

From `cloud_ui_design.md` §6:

| # | Question | Answered by |
|---|---|---|
| 1 | Relay unreachable — what does the trader do? | Milestone 3, by unplugging the relay mid-session. PoC's answer: keep trading, show stale in the UI |
| 2 | Command lifecycle | Milestone 2 — the whole point of it |
| 4 | Paper-only guard on the command channel | Milestones 2–3; the relay refuses non-`DU` |
| 5 | Login and secrets | Milestone 2, with Cloudflare Access + a bearer token |
| 9 | Thin hook vs sidecar | Milestone 3 decides it in practice, having already proved the contract against the replay |

Left open: config edits (3), the Claude panel (6), the VPS move (7), backtest parity for a
daily loss stop (8), and whether `D:\Trading UI` becomes its own git repo (10) — worth
deciding before milestone 1, since it decides how the PoC code is version-controlled.

## 8. Risks

- **Windows + a long-running outbound connection.** Sleep settings on the ProArt will end a
  session quietly. Milestone 3 should run once overnight before anything is concluded.
- **Cloudflare's throwaway tunnel URLs are public and unauthenticated.** Use them only with
  the replay's fake data, never with the real trader — or put Access in front first.
- **Scope creep into the trader.** Milestone 3 adds a push and a command poll, nothing else.
  Any trading-logic change belongs to a separate, registered piece of work.
