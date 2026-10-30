# Handover — W10-0013 sub 5: the trader as a container on the NAS — 2026-10-28

Chat: Portal chat (Sonnet · Medium). Board: W10-0013 sub 5 (2869863011) Working on it, Assignee Ben. Parent W10-0013 (2869884333) In progress.

## In plain terms
The trader now runs as a container on the NAS, in **dry mode** (logs signals, places no orders). It is a plain `python:3.12-slim` container with three folders mounted in: the code (`/app`, read-only), the Python packages (`/deps`, read-only) and the trader's data (`/app/var`). A Python launcher, `run_trader.py`, replaces `run_paper.ps1`. It starts in dry mode unless `.env` says `TRADER_MODE=paper`. It shares the Gateway's network (`network_mode: "container:trader-ib-gateway"`), so it connects to `127.0.0.1:4002` and the API is still published nowhere. On 2026-10-28 Ben ran it on the NAS: the packages run on the NAS CPU (no AVX), the self-check passes, the trader connected to the NAS Gateway as client 17 on the paper account, and it stops cleanly on `docker stop`.

## Results on the NAS (Ben, 2026-10-28)
| Step | Result |
|---|---|
| T1/T2 PC | 148 tests pass; commit 1cc53d4 pushed; tar built with dirty=False (checksum matched) |
| T3 | app/RELEASE.json: commit 1cc53d4, dirty false |
| T4 | ib_async 2.1.0, pandas 3.0.5, numpy 2.5.2, tzdata 2025.3 installed (cp312 x86_64 wheels) |
| T5 selfcheck | SELFCHECK PASS (19 checks). CPU flags: avx=False avx2=False sse4_2=True; numpy/pandas import and run: audit risk C resolved |
| T6 | `docker compose --profile trade config` OK; Gateway untouched (Up, healthy) |
| T7 | First start FAILED: `network service:ib-gateway not found`. After the fix: connected to 127.0.0.1:4002 as clientId 17, server version 178, data farms OK, Telegram OFF, max_positions=2 cap_scope=account dry_run=True bridge=off, "entering main loop — DRY RUN" |
| Stop test | `docker stop` -> "stop requested", session summary, disconnected, Exited (0), watchlist untouched, no lock file left in var/state |

## What was built (repo D:\Trading)
| File | What |
|---|---|
| deploy/nas_trader/run_trader.py | Launcher + --selfcheck + --print-command. Settings from env. Refuses live ports, non-paper ports, modes other than dry/paper, strategy lists with spaces, --sleep-on-exit. Creates var/ subfolders and an empty watchlist; refuses with a chown hint when var/ is not writable. Removes a lock left by an earlier run of this container. |
| deploy/nas_trader/build_release.py | Finds main.py's import closure with ast (33 files), packs it with the project files into `Claude outputs\w10_0013_sub5_nas.tar`, with RELEASE.json (commit, dirty flag). |
| deploy/nas_trader/requirements.nas.txt | ib_async 2.1.0, pandas 3.0.5, numpy 2.5.2, tzdata 2025.3 — the ProArt's versions. |
| deploy/nas_trader/compose.yaml | Service `trader`: network_mode container:trader-ib-gateway, profile `trade`, restart "no", user 1000:1000, init true, stop_grace_period 90s, mounts as above. |
| deploy/nas_trader/.env.example | TRADER_* settings (defaults safe), folders, empty secrets. |
| deploy/nas_trader/NAS-TRADER-SETUP.md | Part 2, steps T1–T7. |
| common/provenance.py | With no .git, reads RELEASE.json (source "release"). Git wins when present. |
| tests | tests/deploy/test_run_trader.py (48), test_build_release.py (11), test_nas_trader_compose.py (18), tests/common/test_provenance.py (+4). |

## Lessons
- `network_mode: "service:ib-gateway"` fails on this NAS when the trader is started with `up -d --no-deps`. Use `container:trader-ib-gateway`. A test enforces it.
- The trader's session window is 04:00–09:30 New York. Before 04:00 it connects and waits; it only stops by itself after 09:30 when flat.
- Windows tests must not run subprocesses with a stripped environment (missing SYSTEMROOT breaks sockets, WinError 10106).
- Do not run long pytest/git runs with a timeout: a killed git run left .git/index.lock.
- trader.py calls sys.exit("ib_async not installed") at import; selfcheck catches SystemExit.
- Ben's pasted NAS commands often show transcription slips; check them.

## Not verified (as of 2026-10-28)
Behaviour inside the 04:00–09:30 window (dry run left running; the log is to be read); the TradingView feed from the NAS (anonymous, no cookie); Telegram and portal paths (secrets empty); DSM Build with the new compose file.

## Decisions
1. Dry by default; paper is an explicit .env edit (sub 9). In paper mode the launcher passes --yes.
2. Strategy: Ben decided "run mcl and mc5 with a cap of 3" -> TRADER_STRATEGY=mcl,mc5, TRADER_MAX_POSITIONS=3. Then Ben: "3 positions should be to each strategy" -> TRADER_CAP_SCOPE=strategy (up to 6 open at once, 3 each). Applies when the container is recreated (command was posted on the board item 2026-10-28).
3. Started on purpose (profile `trade`, no restart policy); sub 9 puts the start in a DSM scheduled task.
4. Stale-lock clearing at container start, because container PIDs repeat. Safe only while var/ is private; sub 6 must replace it before var/ is shared.
5. Same package versions as the ProArt, not the newest.

## Rules a later chat must not undo
- The trader service publishes nothing and joins the Gateway with network_mode "container:trader-ib-gateway"; the API stays unpublished (tests enforce it).
- TRADER_MODE defaults to dry in the launcher, compose and .env.example (tests enforce all three).
- The code folder is replaced by unpacking a new tar; never edit /app on the NAS. RELEASE.json says which commit it is.
- restart: "no"; a second automatic session after 09:30 is not wanted.
- One IBKR paper username = one session: the PC's paper Gateway and the ProArt trader stay off while the NAS Gateway holds it.

## Next steps (board ids)
- W10-0013 sub 5 — Ben: confirm the log shows cap_scope=strategy, max_positions=3; paste `sudo docker logs trader-trader` after a full 04:00–09:30 New York window; then close sub 5 (Sonnet · Low).
- W10-0013 sub 6 (Opus · High): replace the PID lock before var/ is shared.
- W10-0013 sub 8 (Sonnet · Medium): shadow run; dry mode is the shadow mode.
- W10-0013 sub 9 (Sonnet · High): DSM scheduled start, TRADER_MODE=paper, runbook.
- Still to write (on sub 8/9): a script to add the secrets to .env without an editor.
