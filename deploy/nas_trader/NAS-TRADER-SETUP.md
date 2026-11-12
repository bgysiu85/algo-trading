# Paper IB Gateway and the trader on the NAS (W10-0013 subs 4 and 5)

Part 1 (steps 1-8) is the Gateway, done 2026-10-28. Part 2 (steps T1-T7, further down) adds the trader container.

What this adds: one container, `trader-ib-gateway`, in a new NAS project called `trader` (the second of the three
projects decided on 2026-10-28: `trade-journal`, `trader`, `edge`). It is IB Gateway plus IBC (the tool that types
the IBKR login for you), logged in to the **paper** username. Sub 5 adds the trader (part 2) and sub 11 the portal
relay to the same project. Nothing here touches the recorder.

Terms. *Paper* = IBKR's practice account. *API* = the socket the trader talks to the Gateway on. *Loopback* =
`127.0.0.1`, an address that only the machine itself can reach. *Network namespace* = the private network a container
lives in; two containers can share one, and then they see each other on `127.0.0.1`. *socat* = a small relay tool
inside the Gateway image. *Digest* = the exact fingerprint of one image version.

## The decision made here: the API is not published anywhere

The paper API has no password and can place orders. So it is reachable **only from containers that share the
Gateway's network**: the trader will (sub 5), and one-off jobs such as the probe below and the W18 desk's data script
(`docker run --network container:trader-ib-gateway ...`).

It is not published on the home network, and not on the NAS's own loopback either. The NAS runs Tailscale in
"userspace" mode, which hands every connection from the tailnet to the NAS's `127.0.0.1` (W17-0024 step 4 found
`127.0.0.1:5900` and `:5432` open to the tailnet that way). A loopback port for the API would therefore be open to every
device on the tailnet. `tests/deploy/test_nas_trader_compose.py` fails if a later edit publishes the API anywhere.

The only published port is the Gateway's VNC login screen on `127.0.0.1:5901`, like the recorder's (5900). It has a
password, but the same tailnet point applies to it; W10-0013 sub 7 reviews both.

Why 4002 and not 4004: the Gateway listens on **4002** inside its own container; the gnzsnz image adds a socat relay
on **4004** for *other* containers. The trader refuses every port except 4002/7497, so it joins the Gateway's network
(`network_mode: "container:trader-ib-gateway"`, sub 5) and talks to `127.0.0.1:4002`. Step 7 records what was measured on your NAS.

## Before you start

- **One IBKR username allows one session.** Close the paper IB Gateway on the PC, and stop the ProArt trader, before
  step 5. If anything else is logged in with the paper username (TWS on another device, IBKR Mobile in paper mode)
  one of the two sessions is kicked off.
- The NAS has 8 GB until the new memory is in. Check the room first (step 4). A second Gateway needs about 1 GB.
- Have the paper username and password to hand (1Password: Trading / Interactive Brokers (Paper)).

## Steps (all on the NAS over SSH unless it says PC)

1. **PC: commit** the new files (commands are on the board, W10-0013 sub 4).
2. **NAS: unpack** `w10_0013_sub4_nas.tar` into `/volume1/docker/trader/` and create the settings folder:
   ```
   sudo mkdir -p /volume1/docker/trader /volume1/trader/gateway
   cd /volume1/docker && sudo tar -xf w10_0013_sub4_nas.tar
   sudo chown "$(id -un)":users /volume1/docker/trader
   ```
   (The last line makes you the owner of the folder itself, not of what is in it, so step 3 can write `.env`. No `-R`:
   the tar already carries root ownership and 0644/0755 modes, and since sub 13 this folder also holds the portal's
   Postgres data, which a recursive chown or chmod would break or open up. See T3 and W10-0013 sub 18.)
   (Upload the tar into `/volume1/docker` with File Station first.)
3. **NAS: fill in `.env`.** Run `bash /volume1/docker/make_trader_env.sh` (also in this folder as `make_trader_env.sh`). It asks
   for the paper username, the paper password and a VNC password, copies the Gateway image pin from the recorder's `.env`
   (so both Gateways are the same version) and writes `/volume1/docker/trader/.env` with mode 600. DSM has no text editor
   for dot-files, which is why this is a script. A password containing `'` or `\` is refused.
4. **NAS: check, create the DSM project, start.** Create the project first, so Container Manager shows and manages it
   from day one (adopting a stack that was started over SSH later needed hash checks and a rebuild, W17-0037).
   ```
   free -m
   cd /volume1/docker/trader
   sudo docker compose config > /dev/null && echo CONFIG OK
   ```
   Then in DSM: **Container Manager > Project > Create**. Project name exactly `trader`, path `/volume1/docker/trader`,
   source "Use existing docker-compose.yml" (it finds `compose.yaml`; the `.env` in the same folder is used), leave the
   Web Station portal option off, tick start on creation (nothing else runs in this project yet). If the dot stays
   grey, press **Build** once, then **Start**. After this, start, stop and rebuild the Gateway from DSM, not with
   `docker compose up` (mixing the two leaves stale settings hashes, the W17-0037 lesson). Then:
   ```
   sudo docker compose ps
   sudo docker logs --tail 60 trader-ib-gateway
   ```
   Wait two minutes. `ps` should end up `healthy`. The log should show the IBC login finishing and the API listening.
   A paper login normally needs no phone approval. If the log says "Permission denied" about `tws_settings`, run
   `sudo chmod -R 777 /volume1/trader/gateway` and restart the project in DSM (this folder holds only Gateway settings).
5. **NAS: probe.** Runs inside the Gateway's network, exactly as the trader will see it (the recorder image already
   holds `ib_async` 2.1.0, the same pin as the trader):
   ```
   sudo docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway \
     -v /volume1/docker/trader/probe_gateway.py:/probe.py:ro --entrypoint python \
     trade-journal-recorder:latest /probe.py --bars SPY --check-orders
   ```
   Expected: `ports` 4002 and 4004 open; `api` PASS; `paper` PASS with a `DU...` account; `clock` PASS; `bars` PASS;
   `orders` PASS ("Read-Only API is OFF ... Nothing was placed"); `VERDICT PASS`. The `orders` line is a what-if (a
   margin preview that IBKR answers and never works); it cannot create an order. If it says INCONCLUSIVE, step 6
   settles it.
6. **NAS: read the Read-Only setting directly** (audit risk B):
   `sudo docker exec trader-ib-gateway grep -i '^ReadOnlyApi' /home/ibgateway/ibc/config.ini` should print `ReadOnlyApi=no`.
7. **NAS: the port question** (audit risk A) - measured 2026-10-28. From a *different* container on the project network
   (command below) the relay 4004 accepts an API session, and 4002 also accepts a plain TCP connection (the Gateway's Java
   process listens on all interfaces inside the container). So "4002 closed from outside" was wrong. What is still
   untested is whether the Gateway accepts an API *session* on 4002 from another container (it may refuse or ask for a
   click on its screen, because "localhost only" is a Gateway setting). Sub 5 stays with the safe design, sharing the
   Gateway's network so the trader is "localhost"; it can try 4002 over the network later if that is ever wanted.
   ```
   sudo docker run --rm --security-opt seccomp=unconfined --network trader_default \
     -v /volume1/docker/trader/probe_gateway.py:/probe.py:ro --entrypoint python \
     trade-journal-recorder:latest /probe.py --host trader-ib-gateway --port 4004 --ports 4002,4004
   ```
8. **Run something against this Gateway from a one-off container** (this is how the W18 desk's data script gets its
   price bars; the PC cannot reach the API by design). Pattern: join the Gateway's network and connect to
   `127.0.0.1:4002` as if the Gateway were on the same machine:
   `sudo docker run --rm --security-opt seccomp=unconfined --network container:trader-ib-gateway <image> <command>`
   The desk's `desk/fetch_bars.py` connects to `127.0.0.1:4002` read-only with client id 91 and passes its own
   paper-ports-only check unchanged. The image must hold `ib_async` and `pandas`; the recorder image has `ib_async` but not
   `pandas`, so use the trader image sub 5 builds, or a `deps` folder with both.
   To look at the Gateway login screen from the PC: `ssh -N -L 5901:127.0.0.1:5901 YOUR_NAS_ADMIN_USER@192.168.1.109`,
   then a VNC viewer at `localhost:5901` with the VNC password.

## Everyday commands

- Status: `cd /volume1/docker/trader && sudo docker compose ps` · log: `sudo docker logs --tail 60 trader-ib-gateway`
- Memory and CPU: `sudo docker stats --no-stream`
- Restart / stop the Gateway (a fresh IBKR login on start): DSM Container Manager > Project > trader > Stop / Start.
- Undo this step entirely: stop the project and choose Delete in DSM, then delete `/volume1/docker/trader` and `/volume1/trader`.

## Rules a later chat must not undo

- The API (4002/4004) is never published, not even on `127.0.0.1` (Tailscale userspace mode would expose it to the tailnet). No `0.0.0.0` binding, no `network_mode: host`, no live trading mode in this project's Gateway.
- `READ_ONLY_API` stays `"no"` (the trader places orders). The recorder's Gateway keeps `"yes"`; they are different containers.
- Host VNC port 5901 (the recorder's Gateway holds 5900).
- Sub 5 adds the trader with `network_mode: "container:trader-ib-gateway"` (`service:ib-gateway` failed on the NAS with `--no-deps`); any port the trader needs published would have to sit on the Gateway service, and the API is not one of them.
- The DSM Container Manager project `trader` was created in step 4. Compose changes reach it by unpacking the new tar and pressing **Build** in DSM (as for `trade-journal`), not by `docker compose up`.
- The trader service is in profile `trade`, so the project never starts it; it is started on purpose (T7, and the scheduled task in sub 9). It has no restart policy. `TRADER_MODE` is `dry` unless `.env` says `paper`; flipping it is the cutover (sub 9), never a side effect.
- The trader container runs the code from `/volume1/docker/trader/app` (read-only) and writes only to `/volume1/trader/var`. The code folder is replaced by unpacking a new `build_release.py` tar; there is no `.git` on the NAS, `RELEASE.json` says which commit it is.

## Not verified in part 1 (since measured on the NAS, 2026-10-28)

The login, the healthcheck, Read-Only API off, and the 4002/4004 behaviour were all checked on the NAS: see the sub 4 result
on the board and `claude/handover_w10_0013_sub4_gateway_20261028.md`. Folder permissions needed
`sudo chown -R 1000:1000 /volume1/trader/gateway`.

---

# Part 2 - the trader container (W10-0013 sub 5)

What this adds: a second service, `trader`, in the same project. It is a plain `python:3.12-slim` container with three
folders mounted in (Synology cannot run a RUN step in a build, so there is no custom image):

| Mounted at | Is | Comes from |
|---|---|---|
| `/app` (read-only) | the trader's code: `main.py` and the 29 modules it reaches, plus `run_trader.py` | `build_release.py` on the PC, unpacked to `/volume1/docker/trader/app` |
| `/deps` (read-only) | `ib_async 2.1.0`, `pandas 3.0.5`, `numpy 2.5.2`, `tzdata 2025.3` (the versions the ProArt runs) | `pip install --target`, step T4 |
| `/app/var` | the trader's state: watchlist, fills, session lock, archive | `/volume1/trader/var` (owned by user 1000); from sub 6 `/volume1/trader-data/var` (part 3) |

`run_trader.py` replaces `run_paper.ps1`. Settings come from `.env` (`TRADER_MODE`, `TRADER_STRATEGY`, ...), the defaults
are a dry run (no orders), and it refuses live ports and anything that is not `dry`/`paper`. `--selfcheck` proves the
image works without a Gateway. The container shares the Gateway's network, so it connects to `127.0.0.1:4002`.

Terms. *Dry run* = the trader logs what it would do and places no orders. *Selfcheck* = imports, time zone, folder
permissions and argument check, with no broker. *AVX* = a CPU feature some Python packages assume; the DS1819+ CPU may
not have it, and step T5 is the test.

## Before part 2

- Part 1 is finished and the Gateway shows `healthy`.
- Still one IBKR session per username: the PC's paper Gateway and the ProArt trader stay off.
- Disk: the packages are about 400 MB in `/volume1/docker/trader/deps`.

## Steps

T1. **PC: run the tests, then commit.** Exact commands are on the board (W10-0013 sub 5). Commit only the files listed
    there; the tree holds other unfinished work that must not go in.
T2. **PC: build the tar.** `python deploy\nas_trader\build_release.py` writes `D:\Trading\Claude outputs\w10_0013_sub5_nas.tar`
    and prints `dirty=False` when the shipped files match the commit. If it says `dirty=True`, commit first.
T3. **NAS: unpack.** Upload the tar into `/volume1/docker` (File Station), then:
    ```
    cd /volume1/docker && sudo tar --overwrite -xf w10_0013_sub5_nas.tar
    sudo chmod 600 /volume1/docker/trader/.env
    ```
    This refreshes `compose.yaml`, `.env.example`, this guide and `probe_gateway.py`, and creates `app/`. `.env` is never in the tar.
    `build_release.py` writes every entry as root with 0644 files and 0755 folders, so the unpacked code is readable by the
    container (user 1000) with no recursive chmod or chown afterwards. **Never run `chmod -R` or `chown -R` on
    `/volume1/docker/trader` itself** (W10-0013 sub 18): since sub 13 it also holds `portal-db` (the portal's Postgres data,
    owner 1026, mode 700) and `portal-backups`. A `chmod -R a+rX` left `portal-db` at 755 on 2026-11-07; a `chown -R` would
    hand the database to your user and stop Postgres at its next start. It also opened `.env` to every NAS user (sub 7
    found it at 644). Recursive commands on a subfolder the guide names (`relay`, `watch`) are fine.
    Every later unpack ends with the same `sudo chmod 600 /volume1/docker/trader/.env`. A rollback copy first is cheap:
    `sudo tar -cf /volume1/docker/edge/staging/app-before-<commit>.tar -C /volume1/docker/trader app`.
T4. **NAS: the trader's var folder, then the packages.**
    ```
    sudo mkdir -p /volume1/trader/var && sudo chown -R 1000:1000 /volume1/trader/var && sudo chmod -R 775 /volume1/trader/var
    sudo docker run --rm --security-opt seccomp=unconfined -v /volume1/docker/trader:/work -w /work python:3.12-slim pip install --no-cache-dir --target /work/deps -r /work/app/requirements.txt
    ```
    The last line should end with `Successfully installed ... ib_async-2.1.0 ... numpy-2.5.2 pandas-3.0.5 ... tzdata-2025.3`.
T5. **NAS: selfcheck** (this is audit risk C, the no-AVX test):
    ```
    sudo docker run --rm --security-opt seccomp=unconfined --user 1000:1000 -e PYTHONPATH=/deps -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -v /volume1/docker/trader/app:/app:ro -v /volume1/docker/trader/deps:/deps:ro -v /volume1/trader/var:/app/var -w /app python:3.12-slim python /app/run_trader.py --selfcheck
    ```
    Expected last line `SELFCHECK PASS`. An "Illegal instruction" crash while importing numpy or pandas means this CPU
    lacks a feature those wheels need; report it, do not retry.
T6. **NAS: put the trader service in the project.** Check, then **Build** the project in DSM (Container Manager > Project >
    trader > Build). The Gateway's own settings did not change, so it should keep running; if DSM recreates it, wait for
    `healthy` again (a paper login, no approval).
    ```
    cd /volume1/docker/trader
    sudo docker compose --profile trade config > /dev/null && echo CONFIG OK
    sudo docker ps --format '{{.Names}}  {{.Status}}'
    ```
T7. **NAS: first dry run.** `TRADER_MODE` is `dry` by default, so no orders. Outside 04:00-09:30 New York time the trader
    connects, checks the account, sees the session is over and stops by itself with exit code 0 - which is a good
    connection test. Inside that window (19:00-00:30 Sydney while New York is on daylight time) it keeps running; stop it
    with the last command.
    ```
    cd /volume1/docker/trader
    sudo docker compose --profile trade up -d --no-deps trader
    sleep 25
    sudo docker logs --tail 80 trader-trader
    sudo docker ps -a --filter name=trader-trader --format '{{.Names}}  {{.Status}}'
    ```
    Expected in the log: the "DRY RUN" banner, a `running <commit> release` line, the account (`DUM...`), and either
    "reached and flat - stopping" or "entering main loop". To stop a running one and tidy up:
    `sudo docker stop trader-trader && sudo docker rm trader-trader`.

Switching to real paper orders is not part of this step: it is `TRADER_MODE=paper` in `.env`, decided in sub 9 after
the shadow run (sub 8). Secrets (TradingView cookie, Telegram, portal token) are left empty for now; sub 8/9 add them.

---

# Part 3 - the trader's files readable from the ProArt, and a lock both machines can see (W10-0013 sub 6)

What this adds, and why. The trader's data folder (`var`: fills, archive, logs, state, the session lock) moves into a new
DSM **shared folder**, `trader-data`, which the ProArt can open **read-only**. Two things then use it:

1. **The session lock is read live.** The trader's lock now carries a *heartbeat* (a timestamp it refreshes every 20
   seconds). A backtest or `main.py` started on the ProArt reads the NAS lock straight from the share and refuses while the
   NAS trader is in session, because IB's request budget (about 60 historical-data requests per 10 minutes) is shared by
   the whole account. A lock whose heartbeat is more than 2 minutes old counts as dead, so a crash clears itself.
2. **Fills are copied, not read live.** A scheduled task on the ProArt runs `pull_nas_var.py` every 2 hours. It copies new
   or changed files from the share into `D:\Trading\var\nas_mirror\` and never deletes or overwrites anything.
   Moving fills into `var\fills` (where the journal and `db_load` look) is `--promote`, a cut-over step for sub 8/9, so two
   traders writing the same day's file cannot overwrite each other.

Terms. *SMB* = the Windows file-sharing protocol DSM speaks. *Heartbeat* = a timestamp a running process keeps refreshing,
so a reader can tell "alive" from "left behind". *Read-only share* = the ProArt's NAS user can look and copy but not change.

## Order

- **S1 and S4 can be done any time.** Nothing on the NAS trader changes.
- **S2/S3 replace the code the trader runs.** Do them after the sub 5 dry-run log has been checked (after 00:30 Sydney on
  Thu 29 Oct), so that log is from the build that was tested.

## Steps

S1. **DSM (browser): the shared folder and a read-only user.**
    - Control Panel > Shared Folder > Create > **Create new shared folder**: name `trader-data`, location Volume 1. Leave
      "Enable Recycle Bin" off and encryption off. On the permissions page grant nobody yet.
    - Control Panel > User & Group > Create: user `pc-reader` with a new password. On the permissions page tick **Read only**
      for `trader-data` and **No access** for everything else. Do not give it any application access.
    - Control Panel > File Services > SMB: SMB must be enabled (it is, if you already use `\\SiuDiskstation`).
S2. **PC: tests, commit, build the tar.** Exact commands are on the board (W10-0013 sub 6). The tar is
    `D:\Trading\Claude outputs\w10_0013_sub6_nas.tar`; the build must print `dirty=False`.
S3. **NAS: unpack, move the data, restart.** Exact commands are on the board. In short: stop `trader-trader`, unpack the
    tar, copy `/volume1/trader/var` into `/volume1/trader-data/var`, give it to user 1000 with world-read, set
    `TRADER_VAR_DIR=/volume1/trader-data/var` in `.env`, start the trader, and check the lock file's `heartbeat_epoch`
    moves between two reads 25 seconds apart.
S4. **PC: credentials, the two settings, the scheduled copy.** Exact commands are on the board. In short: `cmdkey` stores
    the `pc-reader` password in Windows, `setx SESSION_LOCK_REMOTE` and `setx NAS_TRADER_VAR` tell the tools where the
    share is, `python -m common.session_lock` shows what the ProArt sees, and `Register-ScheduledTask` creates the copy.

## Rules this part follows

- The ProArt only ever **reads** the share. `pc-reader` has read-only permission, and `pull_nas_var.py` never writes to it.
- If the NAS is off or the share is not reachable, the tools **warn and carry on** (they treat the NAS as not in session).
  A warning that says "the NAS lock was NOT checked" means a backtest could run into a NAS session; start none until the
  NAS is back or you have checked by hand.
- Both machines need correct clocks (the heartbeat is compared across them). Step S4 prints both times.
- Undo: delete the scheduled task `Algo - pull NAS var`, `setx SESSION_LOCK_REMOTE ""`, and point `TRADER_VAR_DIR` back
  to `/volume1/trader/var` (the old folder is left in place by S3, not deleted).

---

# Part 4 - security review of the trader side (W10-0013 sub 7, 2026-10-31)

Full write-up: `claude/w10_0013_sub7_security_review_RESULT_20261031.md`. What a later chat must know:

- **Who can place paper orders.** Only the trader process sends orders. The portal (when sub 11 connects it) can pause,
  resume, switch a strategy off or on, set the position cap (0-10) and the trail (0.5-20 %), on a paper account only; it
  cannot place or cancel an order. Telegram is send-only. Below the trader, anything that reaches the Gateway's API can
  place paper orders: the trader and one-off containers on its network, **and any NAS shell user without root** (the
  host reaches the Gateway container's address, `172.21.0.2:4004` on 2026-10-31). The `claude` SSH key is one of those.
  Nothing on the home network or the tailnet reaches the API.
- **`.env` is mode 600.** It holds the paper password and the VNC password. After every unpack run
  `sudo chmod 600 /volume1/docker/trader/.env`.
- **Tailscale was removed from the NAS (2026-10-31).** In userspace mode it had exposed every `127.0.0.1` service on the
  NAS to the tailnet (both VNC screens, DSM's Postgres, DNS control and DSM internals). If it is ever reinstalled, set it
  up with a TUN interface and run `check_nas_exposure.py --tailnet <its 100.x address>`. Without it, the check covers the
  home address only and passed 23/23. Reach the VNC screens through the SSH tunnel in step 8.
- **The ProArt reaches the share as `\\SiuDiskstation`, as `pc-reader`.** The name used to resolve through Tailscale; it now
  needs a hosts-file line `192.168.1.109 SiuDiskstation`. Do not switch the settings to `\\192.168.1.109`: that address
  carries Ben's `sysadmin` credential, which can write to the share.


# Part 5 - the portal relay (W10-0013 sub 11, 2026-10-31)

What this adds: the portal relay (the FastAPI app of `D:\Trading UI`) as the container `trader-relay` in the trader project,
served at `https://trader.thesiuz.com` through the tunnel of the `edge` project (`deploy/nas_edge/NAS-EDGE-SETUP.md`). Neon
stays the history database until sub 13. The portal's Reporting tab is unchanged.

## Limits and risks
- **Needs the edge project first** (its part 3): the relay joins the external network `thesiuz-edge`, which edge creates.
- **The relay never touches the trader or the Gateway.** It is started alone (`--no-deps`), sits on `thesiuz-edge` only, and has
  no route to the paper API. The trader (which shares the Gateway's network) reaches it by the public address
  `https://trader.thesiuz.com`, not over Docker. The portal's commands cannot place or cancel orders (sub 7 review, item 5).
- **Nothing on the trader changes until the cutover step** (6): `UI_RELAY_URL` stays empty, so the trader keeps publishing nothing.
  Do steps 1-5 any time (also during the shadow run); do step 6 with sub 9's cutover.
- **Exactly one relay.** It keeps the last state in memory; the Fly relay and this one must not both receive the trader's pushes,
  so step 7 (the DNS switch) is what moves the portal, and only then does the Fly app stop.
- The relay's secrets live in `/volume1/docker/trader/.env` (mode 600), copied by `make_relay_env.py` and never printed.
- Claude has no root on the NAS; the `sudo docker` lines are for Ben's NAS session.

## Steps
1. **Build and copy the relay's files.** `/volume1/docker/trader` belongs to `sysadmin`, so the `claude` login cannot write there;
   the files go to a staging folder and Ben's NAS session moves them. Code is the `app`, `contract` and `history` folders of
   `D:\Trading UI`, plus its `requirements.txt`. PowerShell on the ProArt:
```
Set-Location "D:\Trading UI"
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
tar --exclude=__pycache__ -cf "D:\Trading\Claude outputs\relay_srv.tar" app contract history requirements.txt
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/staging"
scp -O -i $k "D:\Trading\Claude outputs\relay_srv.tar" "D:\Trading\deploy\nas_trader\compose.yaml" "D:\Trading\deploy\nas_trader\.env.example" claude@192.168.1.109:/volume1/docker/edge/staging/
```
   Then in the NAS session. This replaces the trader project's `compose.yaml` (the trader and Gateway sections are unchanged; the
   new text is the `relay` service and the external network) and touches no running container until a `docker compose up`
   names one. The last line closes `.env` again, as after every unpack:
```
sudo mkdir -p /volume1/docker/trader/relay/srv /volume1/docker/trader/relay/deps
sudo cp /volume1/docker/trader/compose.yaml /volume1/docker/trader/compose.yaml.before-relay
sudo cp /volume1/docker/edge/staging/compose.yaml /volume1/docker/edge/staging/.env.example /volume1/docker/trader/
sudo tar --overwrite -xf /volume1/docker/edge/staging/relay_srv.tar -C /volume1/docker/trader/relay/srv
sudo chmod -R a+rX /volume1/docker/trader/relay
sudo chmod 600 /volume1/docker/trader/.env
```
2. **Install the packages once (NAS session).** Synology cannot run a build step, so a plain container installs them:
```
sudo docker run --rm --security-opt seccomp=unconfined -v /volume1/docker/trader/relay:/r python:3.12-slim pip install --no-cache-dir --target /r/deps -r /r/srv/requirements.txt
sudo chmod -R a+rX /volume1/docker/trader/relay
```
3. **Put the relay's settings in `.env` (PowerShell on the ProArt).** First look at what would be copied (names and short
   fingerprints only), then copy it. `RELAY_ALLOWED_SUBJECTS` is empty today, as on Fly (fine while Pocket ID has one account):
```
Set-Location D:\Trading
.\.venv\Scripts\python.exe deploy\nas_trader\make_relay_env.py --check
.\.venv\Scripts\python.exe deploy\nas_trader\make_relay_env.py | ssh -i "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519" claude@192.168.1.109 "tr -d '\r' > /volume1/docker/edge/staging/relay.env.part && chmod 600 /volume1/docker/edge/staging/relay.env.part"
```
   (`.env` belongs to `sysadmin` and is mode 600, so the lines are staged in a file only the `claude` login can read, then appended by
   the NAS session.) They include `UI_AGENT_TOKEN` (the trader's own token; the same value the Fly relay accepts), which keeps the
   trader's portal link off because `UI_RELAY_URL` is still empty. Then in the NAS session, **once**:
```
sudo sh -c "cat /volume1/docker/edge/staging/relay.env.part >> /volume1/docker/trader/.env"
sudo rm /volume1/docker/edge/staging/relay.env.part
sudo chmod 600 /volume1/docker/trader/.env
sudo grep -c -E '^(RELAY_|UI_AGENT_TOKEN)' /volume1/docker/trader/.env
cd /volume1/docker/trader && sudo docker compose --profile portal config --quiet && echo CONFIG-OK
```
   The count should be 6 or 7. If `.env` gained duplicate lines (the command was run twice), remove the older ones with nano.
4. **Start the relay alone (NAS session).**
```
cd /volume1/docker/trader
sudo docker compose --profile portal up -d --no-deps relay
sudo docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'trader|relay'
sudo docker logs --tail 15 trader-relay
sudo docker exec trader-relay python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8080/api/health', timeout=5).read())"
```
   `trader-trader` and `trader-ib-gateway` must show the same uptime as before. The health call should print a small JSON body.
5. **Add the route (Cloudflare dashboard).** Zero Trust > Networks > Tunnels > `thesiuz-nas` > Published application routes >
   add `trader.thesiuz.com` -> `http://trader-relay:8080`. The DNS record `trader` currently points at the Fly app; the route can
   only be added after that record is edited to the tunnel's `<tunnel-id>.cfargotunnel.com` (this IS the switch, so do it last, and
   see step 7). The portal keeps working on the Fly address until then. Sign-in at `trader.thesiuz.com` needs Pocket ID to answer at
   `id.thesiuz.com` (edge part 5, or still on Fly: both work).
6. **Cutover of the trader's link (with sub 9).** In `.env` set `UI_RELAY_URL=https://trader.thesiuz.com` (nano), `chmod 600`
   again, and restart the trader only at a time sub 9 chooses (never 04:00-09:30 New York). A dry session publishes only when
   `UI_PUBLISH_DRY` is set, so the shadow run is unaffected.
7. **Check, then retire Fly.** Open https://trader.thesiuz.com, sign in with the passkey, confirm the state shows. When it does,
   `fly machine stop` the relay app `thesiuz-trader-relay` (keep it stopped, not destroyed, until sub 13 has moved the history).
   On the ProArt run the exposure check (`deploy\nas_trader\check_nas_exposure.py`); port 8080 must be closed on the home address.

## Undo
```
cd /volume1/docker/trader
sudo docker compose --profile portal rm -sf relay
```
and point the DNS record `trader` back at the Fly app (`thesiuz-trader-relay.fly.dev`). The relay holds no data of its own.

## Rules a later chat must not undo
- The relay is on `thesiuz-edge` only. Never add it, or anything else, to the Gateway's network or the Gateway to `thesiuz-edge`.
- The relay has no `ports:` and starts only by name (`--profile portal ... --no-deps relay`).
- Its secrets stay in `.env` (mode 600), written by `make_relay_env.py`; never typed on a command line or stored in the repo.

\\ Part 6 - the watcher: dead-man ping, portal and trader checks (W10-0013 sub 12)

What it does: one small container `trader-watch` (`deploy/nas_trader/watch.py`, standard library only) checks once a minute and
messages Telegram. (1) It pings healthchecks.io every minute: if the pings STOP, healthchecks.io messages you, which is the only way to
hear that the NAS itself, its network or Docker is down. (2) It checks `https://trader.thesiuz.com` answers (3 misses in a row). (3) On
weekdays 04:10-09:25 New York it checks the trader's session lock has a heartbeat under 120 s old. The recorder, backup, push and Flex
alerts already exist in the journal's `alerts` container (W17-0007) and are not touched.

Limits and risks:
- It reads `var/` read-only, publishes nothing, is not in the Gateway's network and not on `thesiuz-edge`. It starts alone (`--no-deps`),
  so the Gateway and the trader are not recreated. It can place no order.
- US market holidays are not known to it: on a holiday the trader check will say "no session" at 04:10. Put the date in `WATCH_SKIP_DATES`
  in `.env` (YYYY-MM-DD, comma separated). If the trader is meant to end before 09:25, the window can be changed (`TRADER_WATCH_END`).
- The healthchecks.io account is yours to create (Claude does not create accounts). The free plan is enough.
- It uses the trader's Telegram bot (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` in `.env`). Empty there = messages only in the log.

Steps:
1. **healthchecks.io (your browser).** Sign up, create a check named `NAS trader`: Period 1 minute, Grace 5 minutes. Under Integrations add
   Telegram and tick it for this check (it gives you a bot to press Start on). Copy the check's ping URL (https://hc-ping.com/...). It is a
   secret: anyone with it can fake a ping. Send it to nobody; it goes only into `.env` below.
2. **Copy the files (PowerShell on the ProArt).**
```
Set-Location D:\Trading
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/staging"
scp -O -i $k "D:\Trading\deploy\nas_trader\watch.py" "D:\Trading\deploy\nas_trader\compose.yaml" "D:\Trading\deploy\nas_trader\.env.example" claude@192.168.1.109:/volume1/docker/edge/staging/
```
   Then in the NAS session (the last line closes `.env` again, as after every copy):
```
sudo mkdir -p /volume1/docker/trader/watch
sudo cp /volume1/docker/trader/compose.yaml /volume1/docker/trader/compose.yaml.before-watch
sudo cp /volume1/docker/edge/staging/compose.yaml /volume1/docker/edge/staging/.env.example /volume1/docker/trader/
sudo cp /volume1/docker/edge/staging/watch.py /volume1/docker/trader/watch/watch.py
sudo chmod -R a+rX /volume1/docker/trader/watch
sudo chmod 600 /volume1/docker/trader/.env
```
3. **Put the ping URL in `.env` (NAS session).** `sudo nano /volume1/docker/trader/.env`, add one line `HC_PING_URL=` followed by the URL (no
   quotes, no spaces), save (Ctrl+O, Enter, Ctrl+X), then:
```
sudo chmod 600 /volume1/docker/trader/.env
sudo grep -c '^HC_PING_URL=.' /volume1/docker/trader/.env
cd /volume1/docker/trader && sudo docker compose --profile watch config --quiet && echo CONFIG-OK
```
   The count must be 1.
4. **Try it once without sending anything.** It prints the lock and the problems it sees (outside 04:10-09:25 New York: "no problems"):
```
sudo docker run --rm --security-opt seccomp=unconfined -u 1026:100 -v /volume1/docker/trader/watch:/watch:ro -v /volume1/trader-data/var:/var-data:ro python:3.12-slim python /watch/watch.py --once
```
5. **Start it alone.**
```
cd /volume1/docker/trader
sudo docker compose --profile watch up -d --no-deps watch
sudo docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'trader|watch'
sudo docker logs --tail 10 trader-watch
```
   `trader-trader` and `trader-ib-gateway` must show the same uptime as before. Telegram gets one "watcher running" message, and
   healthchecks.io shows the check green within a minute.
6. **Prove the dead-man works (once).** `sudo docker stop trader-watch`, wait about 7 minutes (period + grace): healthchecks.io must message
   Telegram "down". Then `sudo docker start trader-watch`; it goes green again by itself.

Undo: `cd /volume1/docker/trader && sudo docker compose --profile watch rm -sf watch` (and pause or delete the check on healthchecks.io).

Rules a later chat must not undo: the watcher has no `ports:`, no `networks:`, no `network_mode`, mounts `var/` read-only, and starts only by
name (`--profile watch ... --no-deps watch`). The ping URL lives only in `.env` (mode 600).

## Part 7 - the portal's history database moves from Neon to the NAS (W10-0013 sub 13)

What it does: the relay's Reporting tab reads closed trades from a Postgres database. Today that is Neon (the internet). This part adds
the portal's OWN Postgres on the NAS (`trader-portal-db`, version 18 like Neon), copies the history over (285 closed trades and 91
order-outcome rows, 2 to 23 Sep, net P&L -1,413.13 at the time of writing), points the relay at it, and adds a daily backup. The
journal's database (`journal-db`) is not used: the relay faces the internet, so it gets no route to the journal's server.

Limits and risks:
- **The relay restarts once** (the switch step): the live panel is empty until the trader's next push. Do it outside 04:00-09:30 New York.
- **Neon stays untouched** and keeps its data. Rollback is one command (below). Delete Neon only after a week of clean runs, and only you can.
- The copy is a plain SQL file made by `neon_export.py` (read-only on Neon, prints no secret). It loads in one transaction: all or nothing.
  Load it into an EMPTY database only (run once). Anything the portal uploads to Neon after the export is not in the copy, so export,
  load and switch in one sitting.
- About 150 MB of RAM for the database (3.9 GB are free). The database is on a private Docker network with no internet, shared only with the
  relay and the backup job; no port is published.
- Claude has no root on the NAS; the `sudo` lines are for your NAS session.

Steps:
1. **Make the copy and send the files (PowerShell on the ProArt).** The export prints counts and totals: note them.
```
Set-Location D:\Trading
& "C:\Program Files\Python314\python.exe" deploy\nas_trader\neon_export.py --out "D:\Trading\Claude outputs\portal_history.sql"
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
$dest = "claude@192.168.1.109:/volume1/docker/edge/staging/"
foreach ($f in "compose.yaml", ".env.example", "watch.py", "portal_db.sh", "portal_db_backup.sh") { scp -O -i $k "D:\Trading\deploy\nas_trader\$f" $dest }
scp -O -i $k "D:\Trading\Claude outputs\portal_history.sql" $dest
ssh -i $k claude@192.168.1.109 "chmod a+r /volume1/docker/edge/staging/*"
```
2. **Install the files and make the folders (NAS session).** The last line closes `.env` again, as after every copy:
```
S=/volume1/docker/edge/staging
sudo cp /volume1/docker/trader/compose.yaml /volume1/docker/trader/compose.yaml.before-portal-db
sudo cp $S/compose.yaml $S/.env.example /volume1/docker/trader/
sudo cp $S/watch.py $S/portal_db.sh $S/portal_db_backup.sh /volume1/docker/trader/watch/
sudo chmod -R a+rX /volume1/docker/trader/watch
sudo mkdir -p /volume1/docker/trader/portal-db /volume1/docker/trader/portal-backups
sudo chown 1026:100 /volume1/docker/trader/portal-db /volume1/docker/trader/portal-backups
sudo chmod 700 /volume1/docker/trader/portal-db
sudo chmod 600 /volume1/docker/trader/.env
```
3. **Make the database password (it is never shown) and start the database alone.**
```
sudo bash /volume1/docker/trader/watch/portal_db.sh password
cd /volume1/docker/trader && sudo docker compose --profile portal config --quiet && echo CONFIG-OK
sudo docker compose --profile portal up -d --no-deps portal-db
sleep 40; sudo docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'trader|portal'
```
   `trader-portal-db` must say `healthy` (wait a minute and repeat if it says `starting`). `trader-relay` and `trader-ib-gateway` keep
   their uptimes. If `portal-db` stops with a permission error, `sudo docker logs trader-portal-db` and send it to Claude.
4. **Load the history (all or nothing) and check it against the export.**
```
sudo docker exec -i trader-portal-db psql -U portal -d portal -v ON_ERROR_STOP=1 < /volume1/docker/edge/staging/portal_history.sql
sudo docker exec trader-portal-db psql -U portal -d portal -c "select count(*), min(session_date), max(session_date), sum(net_pnl) from closed_trades" -c "select count(*), min(session_date), max(session_date), sum(n) from order_outcomes"
```
   The two result rows must equal the numbers the export printed (rows, dates, totals). If not, stop and tell Claude (nothing has switched).
5. **Start the daily backup and let the watcher see it.**
```
cd /volume1/docker/trader
sudo docker compose --profile portal up -d --no-deps portal-db-backup
sleep 15; sudo docker logs --tail 5 trader-portal-db-backup
sudo docker compose --profile watch up -d --no-deps watch
```
   The backup log must say `backup ok: portal-....dump`. The watch container is recreated (it now also watches the backup age); for a
   minute the healthchecks.io ping pauses, which is fine inside its 5-minute grace.
6. **Switch the relay (outside 04:00-09:30 New York).**
```
sudo bash /volume1/docker/trader/watch/portal_db.sh switch
sudo chmod 600 /volume1/docker/trader/.env
cd /volume1/docker/trader && sudo docker compose --profile portal up -d --no-deps relay
sleep 20; sudo docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'trader|portal'
sudo docker logs --tail 15 trader-relay
sudo bash /volume1/docker/trader/watch/portal_db.sh status
```
   `status` must say `relay: portal-db (NAS)`. The old Neon line is kept as `NEON_DATABASE_URL`. Then open https://trader.thesiuz.com,
   sign in, open the Reporting tab: the totals must match step 4 (285 trades, -1,413.13 net, 2 to 23 Sep). On the ProArt run the exposure
   check (`deploy\nas_trader\check_nas_exposure.py`): ALL CHECKS PASSED.
7. **A week later:** if the Reporting tab and the nightly backups stayed fine, delete the Neon project in the Neon console (yours to do), then
   `sudo sed -i '/^NEON_DATABASE_URL=/d' /volume1/docker/trader/.env` and `sudo chmod 600 /volume1/docker/trader/.env`.

Rollback (any time before step 7):
```
sudo bash /volume1/docker/trader/watch/portal_db.sh rollback
cd /volume1/docker/trader && sudo docker compose --profile portal up -d --no-deps relay
```
The relay is back on Neon; `portal-db` can stay or go (`sudo docker compose --profile portal rm -sf portal-db portal-db-backup`; its data folder
stays until you delete it).

Rules a later chat must not undo: `portal-db` and its backup job are on the internal network `portaldb` only (shared with the relay), publish
no port, and start only by name (`--profile portal ... --no-deps`). The Gateway, the trader, the watcher and `thesiuz-edge` never join
`portaldb`. The password is made on the NAS by `portal_db.sh` and lives only in `.env` (mode 600). The relay never gets a route to `journal-db`.

## Part 8 - pre-session API check (W10-0013 sub 16, 2026-11-03)

Why: on Sun 1 Nov the Gateway refused every API session with IBKR error 10141 ("Paper trading disclaimer must first be accepted for API
connection") while Docker still showed it healthy, because the health check only tests that port 4002 accepts a TCP connection. This check
does what the trader does: it opens a real read-only API session (client id 95), asks for the accounts and the server time, and messages
Telegram if that fails (3 attempts, 20 s apart, before it speaks). Files: `api_precheck.py` (the check) and `api_precheck.sh` (for DSM Task Scheduler).

Two modes:
- `check` - one check, messages Telegram on failure (and a short "OK" while `PRECHECK_NOTIFY_OK` is `yes`, the default, so a silent task is noticed). Never restarts anything.
- `check-restart` - if the check fails, restarts the Gateway ONCE (`docker restart trader-ib-gateway`), waits 4 minutes, checks again. It refuses to restart while `trader-trader` is running; it then only messages.

Limits and risks (unverified items are marked):
- It runs inside the Gateway's network, publishes nothing, passes only the two Telegram values from `.env` (never the whole file), places or previews no order, and refuses live ports.
- NOT verified: that a restart clears error 10141 every time (it did on 1 Nov, by hand); what the dialog says (IBC's log recorded only its title "IBKR Gateway"; the next time it appears, read it on the Gateway's screen, VNC at 127.0.0.1:5901 on the NAS, and tell Claude); whether the trader reconnects by itself if the Gateway restarts under it, which is why `check-restart` runs only BEFORE the trader starts.
- A restart takes the Gateway away for a few minutes. The desk (W18) uses the same Gateway: keep the `check-restart` time away from its runs.
- If the NAS or its network is down, nothing here can say so; that is the watcher's healthchecks.io ping (part 6).
- Times are NAS clock times (Sydney/Melbourne). They follow New York: with New York on standard time, 04:00 New York is 20:00 here. When either country changes its clocks, move these two tasks together with "Algo - start trader".

Steps:
1. **Copy the files (PowerShell on the ProArt).**
```
Set-Location D:\Trading
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/staging"
scp -O -i $k "D:\Trading\deploy\nas_trader\api_precheck.py" "D:\Trading\deploy\nas_trader\api_precheck.sh" claude@192.168.1.109:/volume1/docker/edge/staging/
```
   Then in the NAS session:
```
sudo cp /volume1/docker/edge/staging/api_precheck.py /volume1/docker/edge/staging/api_precheck.sh /volume1/docker/trader/
sudo chmod 755 /volume1/docker/trader/api_precheck.sh
sudo chmod 644 /volume1/docker/trader/api_precheck.py
sudo chmod 600 /volume1/docker/trader/.env
```
2. **Run it once by hand (NAS session).** It opens one read-only API session and sends one "OK" to Telegram:
```
sudo bash /volume1/docker/trader/api_precheck.sh check
sudo tail -8 /volume1/docker/trader/precheck.log
```
   Expect `PRECHECK PASS` and a Telegram message "Gateway API check OK". Report back what it printed.
3. **Prove the alarm with a safe failure (NAS session).** It asks for the WRONG port (7497, where nothing listens), so it fails without touching the Gateway; Telegram must say FAILED with a "TEST" label:
```
sudo bash /volume1/docker/trader/api_precheck.sh check --port 7497 --attempts 1 --label "TEST - ignore"
```
4. **Two DSM tasks (DSM by hand).** Control Panel > Task Scheduler > Create > Scheduled Task > User-defined script. User `root`, Mon-Fri, "Send run details by email" off. Task settings > Run command:
   - Name `Algo - API check before start`, Schedule 16:50, command `bash /volume1/docker/trader/api_precheck.sh check-restart`
   - Name `Algo - API check before window`, Schedule 19:45, command `bash /volume1/docker/trader/api_precheck.sh check`
   After the first weekday run, `sudo tail -20 /volume1/docker/trader/precheck.log` shows both.

Undo: delete the two DSM tasks; `sudo rm /volume1/docker/trader/api_precheck.py /volume1/docker/trader/api_precheck.sh`.

Rules a later chat must not undo: the check runs only with `--network container:trader-ib-gateway` and publishes no port; the wrapper never passes `.env` as a whole (`--env-file`); `docker restart` appears once, only in `check-restart`, and never while `trader-trader` runs; the client id 95 is not shared with another tool; live ports stay refused. `tests/deploy/test_api_precheck.py` enforces these.

### Part 8b - Monday-morning check (W10-0026, 2026-11-10)

Why: on Sun 8 Nov the Gateway's daily restart (16:30 Chicago = Mon 09:30 Sydney) did not come back. IBKR invalidates the saved
restart login on Sunday at 01:00 New York, so the first restart after it cannot reuse it. IBC's log (saved in
`/volume1/docker/desk/var/gw_log_20261109.txt`) shows the quick restart start, the login window open, then an unhandled dialog titled
"Gateway" 0.8 s later and nothing after it. The container stayed "Up" with the API closed until Ben ran `docker restart` at about 16:40;
a cold start has no saved login to reuse, signs in with the paper username and was healthy in 2 minutes. The same dialog sequence
appeared on Sun 1 Nov. The 16:50 weekday check would have caught it, but only 10 minutes before the 17:00 start.
This is IBKR's weekly re-login rule, so it will recur every week and cannot be configured away.

Fix (no code change): one more DSM task, the same script, run once on Monday morning after the Sunday restart has happened.
Control Panel > Task Scheduler > Create > Scheduled Task > User-defined script, user `root`, **Monday only**, "Send run details by email" off:
- Name `Algo - API check Monday morning`, Schedule Monday 10:15, command `bash /volume1/docker/trader/api_precheck.sh check-restart`

Why 10:15: the Sunday restart lands at 09:30 Sydney with New York on standard time and Sydney on daylight time (the case now), and earlier
(07:30-08:30) in the other clock combinations, so 10:15 is always after it. Monday has no desk run (the desk runs Tue-Sat), and
`check-restart` refuses to restart while `trader-trader` is running, so nothing is disturbed. It leaves about 6.5 h before the start.
After the first Monday run, `sudo grep "check-restart" /volume1/docker/trader/precheck.log | tail` shows it.

NOT verified: the text of the "Gateway" dialog (IBC logs only the title; read it on the Gateway screen, VNC 127.0.0.1:5901, the next time
it is stuck); that a restart clears it every week (it did on 1 and 9 Nov, by hand). The 16:50 weekday check stays as the backstop.

## Part 9 - extra paper-session containers (W10-0022, 2026-11-12)

Why: one IBKR paper username allows one session, and Ben decided (W10-0019, 2026-11-05) that everything runs from the NAS. So every other
process that needs the paper account (the exit manager W15-0053, the paper runners W15-0037 sub 4 and W16-0014 sub 3, the borrow probe
W05-0022) is a container in this project that joins the Gateway's network like the trader. No second login, nothing from the PC.

The pattern (the `borrow-probe` service in compose.yaml is the first, and the model for the rest):
- `network_mode: "container:trader-ib-gateway"`, no ports, no `networks:`, `restart: "no"`, its own compose profile (never starts with the project).
- Its own client id, taken from `client_ids.py` (add the row first; a duplicate id drops the other session). Reserved: 31 exit manager, 32 W15-0037 runner, 33 W16-0014 runner.
- Writes only to `EXTRAS_OUT_DIR` (`/volume1/trader-data/extras`), never into `var/`. Order-placing ones default to dry, like `TRADER_MODE`.
- Never run one during the trader's window (04:00-09:30 New York = 20:00-00:30 here with New York on standard time): they share the Gateway's API with the trader.
- Not built yet: the exit manager and both paper runners (no code exists); each gets its service when its own item delivers the code. W16-0014 sub 3 must be re-scoped from NinjaTrader (expired 2026-10-03) to IBKR. Futures orders may be refused until IBKR restores US futures permission (W03-0017, about 22 Nov).

Limits and risks of the borrow probe (read-only, paper ports only, cannot place or preview an order):
- NOT verified: that IBKR sends a borrow FEE RATE through the API at all (generic tick 236 gives the shortable level and shares). The probe writes every tick type that arrives, so a fee-like value would show in `ticks`; if none does, the fee part of W05-0022 needs another source.
- Verified 2026-11-12 (first run, AAPL / TSLA / GME): the real `shortable` (3.0 = easy) and `shortableShares` fields arrive. The `ticks` list is only the last tick batch, so it is weak evidence about a fee rate: it showed only 46 and 89 (or 8). A fee rate was NOT seen; that does not prove IBKR has none.
- Found on the first run: `sudo mkdir` made `/volume1/docker/trader/extras` mode 700 and the container (user 1000) got "Permission denied" on the code; the Synology `trader-data/extras` folder showed mode 000 with an ACL. Step 1 now runs `chmod 755` on both.
- NOT verified: the new `extras` folder's permissions for the `pc-reader` read-only share user (step 1 sets owner 1000:1000).

Steps:
1. **Copy the files (PowerShell on the ProArt).**
```
Set-Location D:\Trading
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/staging"
scp -O -i $k "D:\Trading\deploy\nas_trader\borrow_probe.py" "D:\Trading\deploy\nas_trader\client_ids.py" "D:\Trading\deploy\nas_trader\compose.yaml" claude@192.168.1.109:/volume1/docker/edge/staging/
```
   Then in the NAS session:
```
sudo mkdir -p /volume1/docker/trader/extras /volume1/trader-data/extras
sudo chown 1000:1000 /volume1/trader-data/extras
sudo chmod 755 /volume1/trader-data/extras /volume1/docker/trader/extras
sudo cp /volume1/docker/edge/staging/borrow_probe.py /volume1/docker/edge/staging/client_ids.py /volume1/docker/trader/extras/
sudo cp /volume1/docker/edge/staging/compose.yaml /volume1/docker/trader/compose.yaml
sudo chmod 644 /volume1/docker/trader/extras/borrow_probe.py /volume1/docker/trader/extras/client_ids.py /volume1/docker/trader/compose.yaml
printf 'EXTRAS_DIR=/volume1/docker/trader/extras\nEXTRAS_OUT_DIR=/volume1/trader-data/extras\n' | sudo tee -a /volume1/docker/trader/.env >/dev/null
sudo chmod 600 /volume1/docker/trader/.env
```
2. **List a few symbols and run it once, outside the trader's window (NAS session).** It opens one read-only API session on the already logged-in Gateway:
```
cd /volume1/docker/trader
sudo docker compose --profile borrow run --rm --no-deps borrow-probe --symbols AAPL,TSLA,GME
sudo tail -3 /volume1/trader-data/extras/borrow_probe.jsonl
```
   Report back what it printed (the `ticks` list is what shows whether a fee rate exists). For a week of gappers put the symbols one per line in `/volume1/trader-data/extras/gappers.txt` and use `--symbols-file /out/gappers.txt` (50 symbols at most per run).

Undo: `sudo docker rm -f trader-borrow-probe`; remove the two `EXTRAS_*` lines from `.env`; `sudo rm -r /volume1/docker/trader/extras`.

Rules a later chat must not undo: every container that joins the Gateway does it with `container:trader-ib-gateway`, publishes nothing, has a unique id in `client_ids.py`, makes no login of its own and never writes into `var/`. `tests/deploy/test_nas_extra_clients.py` and `tests/deploy/test_borrow_probe.py` enforce these.
