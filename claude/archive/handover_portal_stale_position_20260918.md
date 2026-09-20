# Handover — the portal showed a position that neither IB nor the ledger had

From: live paper-trade analysis chat (read-only on production).
To: the portal / UI build chat.
Written 2026-09-18, after the session. Nothing was changed anywhere.

## What Ben saw

After the 2026-09-18 session closed, the portal still showed **BIAF as an open position**.

It was not open. Checked both ways:

- **IB** (`show_trades.ps1`, 09:38 ET): every symbol 0, no open orders, BIAF bought once
  (100 @ 10.18) and sold once (100 @ 11.00). 30 executions.
- **The fill log**: 30 fills, 15 round trips, nothing unpaired. BIAF closed 09:30:26
  for +80.62.

So this is the opposite of the MEDS ghost: there, the trader believed in a position IB did
not have. Here, **the portal believes in a position the trader does not have**. Harmless to
trading — the portal cannot place an order — but it is the same class of defect: a display
that cannot be distinguished from the truth by looking at it.

## Why it happens (read from `common/ui_bridge.py` at `prod-20260918`)

1. `build_state()` reads `trader.states[*].position` and emits a **full snapshot** every push.
2. `tick()` is called **from the trading loop** and throttles to one push every `push_every_s`
   (5 s).
3. When the loop ends — session over at 09:30, Ctrl-C, or a crash — **nothing pushes a final
   state**. There is no shutdown hook in `ui_bridge` and none in `trader.main`'s `finally`.
4. The relay therefore keeps serving the last snapshot it received, indefinitely.

BIAF's exit filled at **09:30:26**, in the same handful of seconds as the loop's last pass.
If the last successful push happened before that fill, the final state on the relay has BIAF
open — and it stays that way forever, because nothing follows it.

A second detail, possibly relevant: a `CONFIG session_open` row was written at **09:36:03 ET**,
six minutes after the session ended, so a trader process started again. If that process
attached its bridge and then idled outside the session window, whether it pushes at all
before the first loop iteration is worth checking — a fresh process with no positions should
have corrected the display within 5 s, and evidently did not.

## What the state document already carries

`build_state()` emits `sent_at` (UTC) at the top level, and `health` with
`broker_connected`, `data_stale_seconds: None` and `uptime_s: None`. So the page **can**
already tell how old its data is; it just doesn't say.

## What to fix, in the order I'd do it

1. **The page must show its own age.** `sent_at` is in every document. A snapshot older than
   a few pushes is not "the current state of the account", and the positions table is exactly
   where that matters. Anything from "updated 3s ago" to a banner when it exceeds ~30 s.
2. **A final push on shutdown.** `trader.main`'s `finally` (or a `ui_bridge.close()`) pushes
   one last state with the positions as they ended and a flag saying the agent has stopped —
   `session.state` already exists for that shape. Then "the trader is not running" is a thing
   the page can say, instead of a stale position looking live.
3. **Populate `health.uptime_s` and `data_stale_seconds`** rather than leaving them null, so
   the page has something to render besides `sent_at`.
4. **Consider marking positions as unverified when the agent is gone.** The portal's positions
   come from the trader's own state, never from IB. When the agent has stopped, the honest
   rendering is "last known, unverified", not a live row.

## What NOT to do

- Do not have the portal read IB directly. The trader owns the broker connection and the
  session lock, and a second client id polling positions is a new failure mode for a display.
- Do not paper over it by hiding positions when the feed is stale — a position that really is
  open and unmanaged (the process died holding it) is the one thing the page must never hide.
  Show it, and say it is unverified and how old it is.

## Two other display defects, for the trading-repo chat rather than this one

These are in `common/report_trades.py`, not the portal, and are recorded here only so they
are not lost:

- **IB execution times print in UTC** while the fill log is ET — a flat four-hour shift today
  (13:00:01 UTC = 09:00:01 ET). The same screen prints the local Sydney clock in its header.
- **Realized P/L and commission print 0.00** on every row because IB's paper account does not
  populate `commissionReport`. The viewer should name the fill log as the P/L source rather
  than print a zero that reads like a result.

## The evidence, if you want to reproduce it

```
D:\Trading\var\fills\mcl_fills_20260918.csv    BIAF rows at 09:00:02, 09:30:08, 09:30:14, 09:30:26
                                               CONFIG session_open rows at 03:33:02 and 09:36:03
show_trades.ps1                                IB flat, 30 executions, BIAF 1 buy / 1 sell
claude/session_review_20260918.md              the session's numbers and the BIAF sequence
```
