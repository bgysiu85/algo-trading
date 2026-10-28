# Paper IB Gateway on the NAS (W10-0013 sub 4)

What this adds: one container, `trader-ib-gateway`, in a new NAS project called `trader` (the second of the three
projects decided on 2026-10-28: `trade-journal`, `trader`, `edge`). It is IB Gateway plus IBC (the tool that types
the IBKR login for you), logged in to the **paper** username. Later steps add the trader (sub 5) and the portal
relay (sub 11) to the same project. Nothing here touches the recorder.

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
(`network_mode: "service:ib-gateway"`, sub 5) and talks to `127.0.0.1:4002`. Step 7 proves this on your NAS.

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
   (The last line makes you the owner of the folder so DSM's Text Editor can save `.env` in step 3.)
   (Upload the tar into `/volume1/docker` with File Station first.)
3. **NAS: fill in `.env`.** Copy it with `cp /volume1/docker/trader/.env.example /volume1/docker/trader/.env`, edit it in DSM's Text Editor (paper username, paper password,
   a VNC password), then lock it: `sudo chmod 600 /volume1/docker/trader/.env`.
   For `IB_GATEWAY_IMAGE`, copy the line the recorder uses so both Gateways are the same version:
   `sudo grep '^IB_GATEWAY_IMAGE=' /volume1/docker/trade-journal/.env`
4. **NAS: check, then start.**
   ```
   free -m
   cd /volume1/docker/trader
   sudo docker compose config > /dev/null && echo CONFIG OK
   sudo docker compose up -d
   sudo docker compose ps
   sudo docker logs --tail 60 trader-ib-gateway
   ```
   Wait two minutes. `ps` should end up `healthy`. The log should show the IBC login finishing and the API listening.
   A paper login normally needs no phone approval. If the log says "Permission denied" about `tws_settings`, run
   `sudo chmod -R 777 /volume1/trader/gateway` and `sudo docker compose restart` (this folder holds only Gateway settings).
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
7. **NAS: prove the port question** (audit risk A). From a *different* container on the project network the API port
   4002 should be closed and only the relay 4004 open, which is why the trader must share the Gateway's network:
   ```
   sudo docker run --rm --security-opt seccomp=unconfined --network trader_default \
     -v /volume1/docker/trader/probe_gateway.py:/probe.py:ro --entrypoint python \
     trade-journal-recorder:latest /probe.py --host trader-ib-gateway --port 4004 --ports 4002,4004
   ```
   Expected: `4002 is closed`, `4004 is open`, `api` PASS on 4004. (If 4002 were open here, sub 5 could use a plain
   network and the `network_mode` line would not be needed. Report what you see.)
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
- Restart the Gateway (a fresh IBKR login): `sudo docker compose restart ib-gateway`
- Stop and remove: `sudo docker compose down` (settings stay in `/volume1/trader/gateway`)
- Undo this step entirely: `sudo docker compose down` and delete `/volume1/docker/trader` and `/volume1/trader`.

## Rules a later chat must not undo

- The API (4002/4004) is never published, not even on `127.0.0.1` (Tailscale userspace mode would expose it to the tailnet). No `0.0.0.0` binding, no `network_mode: host`, no live trading mode in this project's Gateway.
- `READ_ONLY_API` stays `"no"` (the trader places orders). The recorder's Gateway keeps `"yes"`; they are different containers.
- Host VNC port 5901 (the recorder's Gateway holds 5900).
- Sub 5 adds the trader with `network_mode: "service:ib-gateway"`; any port the trader needs published would have to sit on the Gateway service, and the API is not one of them.
- Create the DSM Container Manager project `trader` from this compose file only once sub 5 has added the trader
  service (build once in DSM, as for `trade-journal`, W17-0037). Until then use the commands above.

## Not verified (no Gateway was reachable from the cloud workspace)

Everything above that needs a running Gateway: the login itself, 4002 vs 4004 inside the container, the healthcheck
(a plain TCP connect to 4002), the what-if behaviour under Read-Only API, the `config.ini` path and folder permissions on
`/volume1/trader/gateway`. The probe's logic and the compose file's safety rules are
unit-tested (`tests/deploy/`), and the compose file passes `docker compose config`.
