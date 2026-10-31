# NAS trader runbook (W10-0013 sub 9)

Daily operation of the trader on the DS1819+. Setup is in `NAS-TRADER-SETUP.md`; this is what you do after it.
Paper account only. Never a live port. One IBKR paper username = one session: while the NAS Gateway holds it, the
ProArt trader and the PC's paper Gateway stay OFF.

## What runs by itself
| What | When | Where |
|---|---|---|
| `Algo - start trader` (DSM Task Scheduler, root) | Mon-Fri 17:00 Melbourne (01:00-03:00 New York, before the 04:00 window in every daylight-saving combination) | NAS; runs `cd /volume1/docker/trader && /usr/local/bin/docker compose up -d trader` |
| Trader session | 04:00-09:30 New York; it exits itself at 09:30 once flat | container `trader-trader` (`restart: "no"` on purpose: a restart would be a second session) |
| `Algo - pull NAS var` | every 2 h | ProArt: copies NAS fills into `var\nas_mirror`, never overwrites |
| `Algo - shadow check` | Tue-Sat 02:00 | ProArt: read-only snapshot into `Claude outputs\shadow_check_latest.txt` |

The Gateway container (`trader-ib-gateway`) stays up and restarts itself at 16:30 Chicago, clear of the window.
Days the US market is shut still start the trader; it finds nothing to do (dry or paper).

## Mode: dry or paper
`TRADER_MODE` in `/volume1/docker/trader/.env`. Missing or `dry` = signals logged, NO orders. `paper` = real paper orders.
The first log lines say which: `DRY RUN - signals are logged, NO orders are placed` or `LIVE PAPER ORDERS`.

### Flip to paper (the cutover)
Do it only when `cutover_preflight.py` says GO, and with the container stopped and the book flat.
1. ProArt (PowerShell):
   ```
   Set-Location D:\Trading
   .\.venv\Scripts\python.exe deploy\nas_trader\cutover_preflight.py --expect-commit <commit on the NAS>
   ```
2. NAS (admin SSH, `bash` first), outside 04:00-09:30 New York:
   ```
   sudo docker stop trader-trader
   sudo sed -i 's/^TRADER_MODE=.*/TRADER_MODE=paper/' /volume1/docker/trader/.env
   grep -c '^TRADER_MODE=paper' /volume1/docker/trader/.env
   sudo chmod 600 /volume1/docker/trader/.env; ls -l /volume1/docker/trader/.env
   ```
   Expected: `1` and `-rw-------`. If the count is 0 there is no `TRADER_MODE=` line yet: add one with
   `echo 'TRADER_MODE=paper' | sudo tee -a /volume1/docker/trader/.env`.
3. The 17:00 task starts it next weekday. To start it now (inside the window only):
   `cd /volume1/docker/trader && sudo docker compose up -d trader`, then
   `sudo docker logs --tail 15 trader-trader | grep -i -E "LIVE PAPER|DRY RUN|accounts"` and check the account starts `DU`.

### Back to dry (rollback)
Same steps with `TRADER_MODE=dry`. Stopping with a position open leaves it with no trailing stop (the stop lives in the
process): check the book is flat in the log first, or stop only after 09:30 once the trader has exited by itself.

## After a paper session
- Fills: `var\nas_mirror\fills` fills in every 2 h. To put the NAS fills where the journal and `db_load` look:
  ```
  .\.venv\Scripts\python.exe deploy\nas_trader\pull_nas_var.py --promote
  ```
  It copies only files `var\fills` lacks and reports a `CONFLICT` (exit 1) for a name that exists with different content,
  leaving both alone. A conflict means the PC and the NAS both wrote that day: decide which is the record before merging.
- Log: `sudo docker logs --tail 200 trader-trader` (the trader logs to Docker only).
- Telegram messages go to the trade chat; the ProArt trader must be off, so there is one sender.

## Stop, start, check
| Need | Command (NAS admin, `bash`) |
|---|---|
| Graceful stop (SIGTERM, 90 s to flatten its view and write the fill log) | `sudo docker stop trader-trader` |
| Start | `cd /volume1/docker/trader && sudo docker compose up -d trader` |
| Is it up? | `sudo docker ps --filter name=trader` |
| Lock and heartbeat (from the ProArt) | `.\.venv\Scripts\python.exe -m common.session_lock` |
| Release on the NAS | `cat /volume1/docker/trader/app/RELEASE.json` |

Never `docker kill` or power off with a position open. Never edit `/app` on the NAS: unpack a new tar (every unpack
command ends with `sudo chmod 600 /volume1/docker/trader/.env`).

## If something is wrong
- No session opened by 04:30 New York: `sudo docker ps -a --filter name=trader` and the task's last result in DSM Task
  Scheduler; start by hand (above) if it is before 09:30.
- `watching nothing` all session: the feed is not filling the watchlist; check the log for `update_mode` and the TV cookie.
- PC backtest or `main.py` refuses with "LIVE SESSION": the NAS lock is held; that is correct while the trader runs.
- Anything touching a live port or a non-`DU` account: stop the container and tell Ben.
