# D:\Trading — notes for Claude Code

Ben (Australia, Windows, PowerShell) builds systematic trading systems on Interactive Brokers (IBKR). Repo: D:\Trading.

## How to work with Ben
- Ben is not proficient in PowerShell or git. Run commands and git yourself where you can; when Ben must run something, give exact copy-paste PowerShell with full absolute paths, starting with `Set-Location D:\Trading`.
- Files made for Ben to collect go in `D:\Trading\Claude outputs`.
- State tool limits and risks up front, before proposing a solution.
- Pick the cheapest model/effort that can do the job well and say which you recommend (Haiku/Sonnet/Opus; Low/Medium/High). Suggest splitting work into separate sessions when steps need different models.

## Safety
- Paper account only. Never use a live port. Never place real orders.
- One IBKR paper username = one session. The PC's paper Gateway and the ProArt trader stay off while the NAS Gateway holds it. Ask before running anything that logs in to IBKR.
- Do not run long pytest or git runs with a timeout that can kill them: a killed git run leaves `.git/index.lock`.
- Windows tests must not run subprocesses with a stripped environment (missing SYSTEMROOT breaks sockets, WinError 10106).
- Ben's pasted NAS commands often contain transcription slips (e.g. `--no-eps`, `100:1000`). Check them before relying on them.

## Handover docs
Handover and RESULT docs live in `claude/` (named `handover_wXX_nnnn_*` / `wXX_nnnn_*_RESULT_*`). Read the one for the item you are working on before starting. Each ends with next steps listing board ids.

## NAS trader (workstream W10-0013) — rules not to undo
- Trader runs as a container on the NAS: files in /volume1/docker/trader, containers `trader-trader` and `trader-ib-gateway`. Code is `deploy/nas_trader/` (run_trader.py, build_release.py, compose.yaml, NAS-TRADER-SETUP.md).
- The trader service publishes nothing and joins the Gateway with `network_mode: "container:trader-ib-gateway"` (NOT `service:ib-gateway`, which fails on this NAS). Tests enforce it.
- `TRADER_MODE` defaults to dry in the launcher, compose and `.env.example` (tests enforce all three). Paper is an explicit `.env` edit.
- The code folder on the NAS is replaced by unpacking a new tar; never edit /app on the NAS. `app/RELEASE.json` says which commit it is.
- `restart: "no"`; no second automatic session after 09:30 New York.
- Since sub 6 (2026-10-31) var/ is /volume1/trader-data/var (TRADER_VAR_DIR), a DSM share the ProArt reads READ-ONLY as `pc-reader`. The session lock has a 20 s heartbeat (dead after 120 s); the PC reads it via SESSION_LOCK_REMOTE, and the task `Algo - pull NAS var` copies fills into var\nas_mirror every 2 h. Stale-lock clearing at container start stays safe only while nothing but the NAS trader writes to var/: never give the PC write access to the share.
- Trader session window is 04:00–09:30 New York.
- Current settings: TRADER_STRATEGY=mcl,mc5, TRADER_MAX_POSITIONS=3, TRADER_CAP_SCOPE=strategy (Ben: "3 positions should be to each strategy").

## NAS SSH access (W10-0017) — how Claude logs in to the DS1819+
- Host 192.168.1.109 (DS1819+, DSM 7.4.1), port 22, user `claude`, key login only. Private key: `D:\Trading\Claude outputs\.ssh\nas_claude_ed25519` (git-ignored via `Claude outputs/`). Never copy it into the repo, print it or send it anywhere.
- Test from PowerShell: `ssh -i "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" -o BatchMode=yes claude@192.168.1.109 "echo LOGIN-OK"`
- If Windows ssh refuses the key as "too open", Ben runs once: `icacls "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" /inheritance:r /grant:r "$($env:USERNAME):(R)"`
- Cloud chat sessions using the linked PC's Linux shell: copy the key to `~/.ssh/nas` with `chmod 600` first (the mounted copy's permissions are not accepted), then `ssh -i ~/.ssh/nas claude@192.168.1.109`.
- Folders: read/write `/volume1/trade-journal`, `/volume1/docker`, `/volume1/web`, `/volume1/Logs`, `/volume1/Cloud Services`, `/volume1/homes`; read-only `/volume1/ActiveBackupforBusiness`; no access to other shares. `python3` and `psql` are in /usr/bin.
- No root: `sudo` asks for a password and the Docker socket is root-only, so no `docker` / `docker compose` commands. Ben decided (2026-10-28) not to add passwordless sudo, not even docker-only: "let's leave it as it is for now". Give Ben docker commands as copy-paste for his own NAS session.
- Use it to copy and unpack release tars, read log and data files, check deployed files (checksums, RELEASE.json) and run read-only psql queries. Files written are owned by `claude` (uid 1043, group users): set permissions the container can read (an earlier owner-only tar broke journal-app). Ask Ben before editing a `.env` or deleting anything on the NAS.

## Task board (monday.com, board "Algo Trading", id 5031413876)
- Every task becomes an item "Wxx-nnnn · name"; subitems for steps. Post an Update first (dated note), then change Status/Assignee.
- Commands Ben must run go on the board as an Update inside <pre>…</pre>, one command per line.
- Results are written as a monday Doc on the item plus a short chat summary.
- If the monday connector is not available in this session, say so and give Ben the update text to paste. Full rules are in the claude.ai Project doc `claude/handover_monday_board_20260919.md` — ask Ben to paste it if needed.
