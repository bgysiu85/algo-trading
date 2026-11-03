# W18-0002 · IBKR paper bridge — RESULT (2026-11-02)

Commit 8f42cf5 on main. Deployed to the NAS desk copy (`/volume1/docker/desk/app`, RELEASE.json = 8f42cf5). Never connected to the Gateway yet.

## What it does
`python -m desk.bridge` reads `decisions.csv`, keeps only rows dated today's US date, and turns Buy / Overweight rows into PAPER bracket orders: day limit buy at `entry`, GTC take-profit at `target`, GTC stop-market at `stop` (exits cancel each other), 1 share, orderRef `desk:<date>:<TICKER>`. Hold watch plans are never acted on.

| Command | Connects? | Can place? | Writes |
|---|---|---|---|
| `python -m desk.bridge` | no | no | nothing |
| `... --check` | yes, read-only | no | nothing |
| `... --place [--ticker X]` | yes | yes | `var/desk_runs/orders.csv` |

## Rules re-checked per row
ticker on the list; rating Buy/Overweight; long-only; stop < entry < target (cents); 1 share; horizon 1–180 days; entry no more than 2% above last close; max 15 positions using the desk's ranking (held desk-list stocks and pending desk entries count); skip if held, other open order, already placed today, funds short or unknown.

## Safety
Ports other than 4002 / 7497 refused (exit 2); connection dropped unless every managed account starts with `DU`; client id 92; any refused bracket leg cancels the whole bracket; PLACED rows in orders.csv are never overwritten (second run is a no-op). Exit codes: 0 ok, 1 no decisions file, 2 guard refused, 3 broker error.

## Tests
`tests/desk`: 207 pass (55 new in `test_desk_bridge.py`, fake IB, offline mode proven never to touch the broker). Nine deliberate breakages: eight caught, one equivalent (covered by an added test). `tests/test_encoding_guard.py` fails on `tests/deploy/test_portal_db.py` and `test_pull_nas_var.py` with or without this work.

## Not done
- Closing a position at `hold_until` (logged, not acted on).
- Fill / exit tracking for the W18-0004 scorecard.
- Daily schedule (W18-0003).
- First `--check` / `--place` waits for a Buy/Overweight decision. Container tzdata unverified: if absent the date falls back to UTC, which fails safe ("no decisions dated X").

## Next steps
Board ids: W18-0003 (schedule, was blocked by this), W18-0004 (scorecard; needs fill tracking), plus two proposed follow-ups: time-exit at `hold_until`, fill/exit tracking. Ben runs NAS Step A (offline dry-run) and reports the US date line; Step B (`--check`) once a Buy exists.

## Update 2026-11-03 — first live paper orders
The 2026-11-01 buys went stale at the 16:00 Sydney rollover, so the desk was re-run for 2026-11-02 (BTSG Overweight 6, GM Overweight 5, CNC Hold 4). Step B (`--check`) passed: 0 positions, 0 pending, funds $19,423.12.

| Ticker | Entry | Take-profit | Stop | Risk | Order ids (parent, TP, stop) | Broker status |
|---|---|---|---|---|---|---|
| GM | 83.40 | 91.85 | 76.45 | $6.95 | 4, 5, 6 | PreSubmitted |
| BTSG | 62.50 | 73.75 | 57.50 | $5.00 | 10, 11, 12 | PreSubmitted |

Both logged PLACED in `var/desk_runs/orders.csv`. IBKR returned Warning 399 on each parent ("not placed at the exchange until 2026-11-03 09:30 US/Eastern"): informational, the bridge correctly did not cancel. The BTSG run saw the pending GM entry (`1 desk entry orders pending`), so the cap/idempotency logic works against the live account.

Not yet confirmed: Ben checking the six orders in the IBKR paper account, and what happens at the 2026-11-03 open (fills, expiry of unfilled day orders).
