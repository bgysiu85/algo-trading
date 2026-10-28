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
   cd /volume1/docker && sudo tar -xf w10_0013_sub4_nas.tar && sudo chmod -R a+rX /volume1/docker/trader
   sudo chown -R "$(id -un)":users /volume1/docker/trader
   ```
   (The last line makes you the owner of the folder so step 3 can write `.env`.)
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
| `/app/var` | the trader's state: watchlist, fills, session lock, archive | `/volume1/trader/var` (owned by user 1000) |

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
    cd /volume1/docker && sudo tar --overwrite -xf w10_0013_sub5_nas.tar && sudo chmod -R a+rX /volume1/docker/trader
    sudo chown -R "$(id -un)":users /volume1/docker/trader
    ```
    This refreshes `compose.yaml`, `.env.example`, this guide and `probe_gateway.py`, and creates `app/`. `.env` is never in the tar.
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
