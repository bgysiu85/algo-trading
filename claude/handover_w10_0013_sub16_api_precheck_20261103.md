# Handover — W10-0013 sub 16: pre-session API check for the NAS paper Gateway — 2026-11-03

Chat: Build & test / Portal work, Sonnet · Medium (board said Portal chat, Sonnet · Medium). Board: W10-0013 sub 16 (2896315161) **Working on it, Assignee Ben**. Parent W10-0013 (2869884333) In progress.

## In plain terms
On Sun 1 Nov the NAS paper Gateway refused every API session with IBKR error 10141 ("Paper trading disclaimer must first be accepted for API connection") while Docker still called it healthy, because the health check only tests that port 4002 accepts a connection. A new check now does what the trader does: it opens a real read-only API session, asks for the accounts and the server time, and messages Telegram if that fails. It is built and tested in the cloud and not yet deployed.

## What was built (repo D:\Trading, uncommitted until Ben runs step A on the sub 16 item)
| File | What |
|---|---|
| `deploy/nas_trader/api_precheck.py` | The check. Client id 95. Connects read-only, needs ≥1 account, all paper ("D…"), a server-time answer, and NO error 10141 while connecting (a 10141 counts even when connect returns). 3 attempts 20 s apart, then one Telegram message on failure (or on pass with `--notify-ok`). Refuses live ports. Exit 0 / 1 / 2. |
| `deploy/nas_trader/api_precheck.sh` | For DSM Task Scheduler (root). `check` = alert only. `check-restart` = on failure restart `trader-ib-gateway` ONCE, wait 240 s, check again; refuses to restart while `trader-trader` is running. Passes only the two Telegram values to the container. Logs to `/volume1/docker/trader/precheck.log`. Extra arguments after the mode go to the check (used for the safe alarm test). |
| `tests/deploy/test_api_precheck.py` | 34 tests: the 1 Nov replay, every verdict both ways, retries, Telegram failure never changes the result, and the wrapper run for real against a fake `docker` (restart count, running-trader guard, no secrets on the command line). The bash behaviour tests skip on Windows. |
| `deploy/nas_trader/NAS-TRADER-SETUP.md` | New part 8: files, steps, DSM tasks, undo, rules. |

Checks run: 34 new tests pass; with the neighbouring deploy tests 194 passed, 1 skipped. 17 deliberate breakages were each caught by a test.

## Decisions (mine, defaults; Ben can overrule)
1. Real handshake, not a TCP test, run **inside the Gateway's network** (the API is never published).
2. Retries before speaking, so a Gateway that is mid-reconnect does not cause a false alarm.
3. Restart only **before** the trader starts (16:50 NAS time, trader starts 17:00) and never under a running trader; the 19:45 task is alert-only. Reason: it is not known whether the trader reconnects by itself after a Gateway restart.
4. An "OK" Telegram message is on by default (`PRECHECK_NOTIFY_OK=yes`) so a task that silently stopped running is noticed. Set it to `no` in the DSM task once it has proved itself.

## NOT verified
- That a restart clears error 10141 every time (it did on 1 Nov, by hand).
- The text of the dialog. IBC's log recorded only its title "IBKR Gateway" (opened 2026-11-01 01:04:46 Chicago, 30 s after a "Connecting to server…" reconnect). Next time: read it on the Gateway screen (VNC 127.0.0.1:5901 on the NAS) and tell Claude; the real fix is an IBC setting, if one exists.
- Whether ib_async raises or only logs 10141 (the check handles both: the error event and the timeout path).
- The DSM task environment (PATH, root). The script appends the usual directories to PATH.
- The desk (W18) shares this Gateway: keep the `check-restart` time away from its runs.

## Seen while testing (not part of sub 16)
- In a Linux run of `tests/test_encoding_guard.py` the guard listed bare `read_text()`/`write_text()` calls in `tests/deploy/test_portal_db.py` and `tests/deploy/test_pull_nas_var.py`. Not touched here; worth a look on Windows before the next full-suite run.
- `tests/deploy/test_probe_gateway.py` fails in a Python without `ib_async` installed (environment, not code).

## Rules a later chat must not undo
- The check runs only with `--network container:trader-ib-gateway`; no `-p`, no `--env-file`, no `--privileged`.
- `docker restart` appears once, only in `check-restart`, and never while `trader-trader` runs.
- Client id 95 is not shared; live ports stay refused. `test_api_precheck.py` enforces these.

## Next steps (board AT-ids)
- **W10-0013 sub 16 (2896315161)** — Ben: steps A–E on the item (commit, copy, one run by hand, safe alarm test, two DSM tasks). Then Sonnet · Low reads the output; close after the first scheduled weekday run is seen in `precheck.log`.
- **W10-0013 sub 8 (2869862689)** — unchanged: session 2 tonight 17:00 Sydney start; Ben pastes `sudo docker logs --tail 200 trader-trader` after 01:30 Wed. Open: the "8 active symbols" warning; what to do with the dry-session fills files before the first promote.
- **W10-0013 sub 9 (2869871795)** — unchanged: waits for sub 8.
- **W10-0013 sub 12 (2887388365)** — Done; this check complements its watcher (part 6) and does not replace it.

## Token economy (rule 9)
| Step | Model · effort |
|---|---|
| Ben's copy-paste steps A–E (help only if wanted) | Haiku · Low |
| Reading his pasted output, closing sub 16 | Sonnet · Low |
| IBC dialog setting once the text is known | Sonnet · Medium |
| Sub 8 log review / close-out | Sonnet · Low |
| Sub 9 cutover | Sonnet · Medium |
