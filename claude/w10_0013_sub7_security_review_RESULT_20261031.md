# RESULT — W10-0013 sub 7: security review of the trader side on the NAS — 2026-10-31

Board: W10-0013 sub 7 (2869871634). Parent W10-0013 (2869884333) stays In progress. Worked by Claude Code (Opus) from the
board Updates on sub 7 (there is no separate handover doc). Checks were read-only: code reading, SSH as `claude`, and
TCP connects from the ProArt that send nothing. No IBKR login, no order, nothing changed on the NAS.

## In plain terms
Nothing outside the NAS can place orders. The paper Gateway's API is not reachable from the home network or the tailnet,
and the live guards (paper Gateway, live ports refused twice, `DU` account check, recorder on Read-Only API) are intact.
Two things need fixing, both by Ben with sudo:
1. The trader's `.env` (paper password, VNC password) is readable by every NAS user. The guide's own unpack command caused
   it. One `chmod` fixes it; the guide and a test now stop it coming back.
2. Tailscale on the NAS runs in "userspace" mode, so every service the NAS keeps for itself on `127.0.0.1` is open to
   every tailnet device, including both Gateway VNC screens. The fix is Tailscale with a TUN interface (a DSM boot task).

## Findings (most serious first)

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Medium | Tailscale userspace mode: from the tailnet (100.79.212.23) ports 5900 (recorder Gateway VNC, the LIVE username), 5901 (trader Gateway VNC), 5432 (DSM Postgres), 953 (DNS control), 512, 161 and 33300/33303/33304 (DSM internals) all answer, though all are bound to 127.0.0.1. On the home address (192.168.1.109) they are all closed. | Ben decides: TUN mode (recommended) or Tailscale ACLs |
| 2 | Medium | `/volume1/docker/trader/.env` is mode 644 (sysadmin:users): any NAS shell user can read the paper password and the VNC password. `make_trader_env.sh` writes it 600, but the unpack step `sudo chmod -R a+rX /volume1/docker/trader` (sub 5 T3 and later boards) re-opens it every time. trade-journal's `.env` is 600. | Ben: one chmod. Guide fixed, test added |
| 3 | Low, accepted | The paper API is reachable from the NAS host by any shell user without root: `172.21.0.2:4004` (the Gateway container on network `trader_default`) accepted a TCP connection from user `claude`. Docker always lets the host reach its bridge networks. So whoever holds a NAS admin login, or the `claude` SSH key, can place paper orders. Not reachable from the home network or the tailnet (4001–4004 closed on both). | Documented (guide Part 4, CLAUDE.md). Ben may run check C below |
| 4 | Info | The VNC screens use classic VNC password authentication, which only uses the first 8 characters (the trader's password is 20 long; 8 count). Fine once #1 is fixed; until then reach VNC only through the SSH tunnel (guide step 8). | Covered by #1 |
| 5 | Info | Portal commands (UI bridge) cannot place or cancel orders: they pause/resume entries, switch a strategy, set the cap (0–10) and the trail (0.5–20 %), and are refused on a non-paper account. The NAS `.env` has no `UI_RELAY_URL`, so this path is off until sub 11. Telegram is send-only (no `getUpdates`). | OK; sub 11 keeps the agent token in `.env` (600) |
| 6 | Info | Live guards: Gateway `TRADING_MODE: paper`; `run_trader.py` refuses 4001/4003/7496/7498 and any non-paper port; `trader.py` refuses live ports and any account not starting `DU`; recorder Gateway `READ_ONLY_API: "yes"`; tests enforce the compose rules. | OK |
| 7 | Info | DSM Postgres (127.0.0.1:5432, reachable over the tailnet) has no `pg_hba` entry for TCP: users postgres/admin/claude all get "no pg_hba.conf entry for host 127.0.0.1". No login path. | OK; closed by #1 anyway |
| 8 | Info | qbittorrent (W17-0024 carry-over): not running. No listener on 6881/9865; closed on the home and tailnet addresses. | Closed. Re-check if it is started again |
| 9 | Info | Share `trader-data`: ACL gives `administrators` full control and `pc-reader` read-only; `var/` itself is Linux mode 755 owned by uid 1000, so only the container (and root) writes inside it. `/volume1/trader` (Gateway settings) is 700 root. `/volume1/docker/trader/app` and `deps` are 755 sysadmin, not writable by `claude`. | OK |
| 10 | Info | User `claude` is in group `administrators` (DSM lets only administrators use SSH). `sudo` still asks for a password; the Docker socket is root-only. | As decided 2026-10-28 |

## Measurements
- NAS: `tailscaled --tun=userspace-networking`, no `tailscale0` interface, `AdvertiseRoutes: null`, `ShieldsUp: false`.
  Tailnet has 7 devices, all `bens85@`.
- Listeners bound to 127.0.0.1 on the NAS: 53, 161, 512, 953, 5432, 5900, 5901, 33300, 33303, 33304.
- `deploy/nas_trader/check_nas_exposure.py` (new; the W17-0024 checker extended): home address — every must-be-closed
  port closed; tailnet — 5900, 5901, 5432, 953, 512, 161, 33300, 33303, 33304 OPEN; 4001–4004, 7496/7497, 6881, 9865,
  8088, 4180 closed on both.
- VNC handshake over the tailnet: 5900 and 5901 both offer security type 2 (VNC password) only.

## Changed in the repo (not committed)
- `deploy/nas_trader/NAS-TRADER-SETUP.md`: T3 unpack now ends with `sudo chmod 600 /volume1/docker/trader/.env`; new
  Part 4 (who can place orders, `.env` 600, Tailscale).
- `deploy/nas_trader/check_nas_exposure.py` + `tests/deploy/test_check_nas_exposure.py`: the PC-side port check.
- `tests/deploy/test_nas_trader_compose.py`: fails if an upgrade unpack in the guide does not close `.env` again.
- `CLAUDE.md`: the `.env` rule and the "NAS shell reaches the paper API" fact.
- Tests: `.venv\Scripts\python.exe -m pytest tests/deploy tests/common/test_session_lock.py` → 145 passed.
  (The system Python 3.14 has no `ib_async`; 4 `test_probe_gateway` tests fail there for that reason only.)

## For Ben (NAS SSH session, as your admin user)

A. Close the trader `.env` now (no restart needed; Container Manager reads it as root, as for trade-journal's 600 file):
```
sudo chmod 600 /volume1/docker/trader/.env
ls -l /volume1/docker/trader/.env
```
Expected: `-rw------- 1 sysadmin users ...`.

B. Tailscale with a TUN interface (recommended fix for #1). DSM > Control Panel > Task Scheduler > Create > Triggered
Task > User-defined script. User `root`, event `Boot-up`, script:
```
/var/packages/Tailscale/target/bin/tailscale configure-host; synosystemctl restart pkgctl-Tailscale.service
```
Then select the task and press Run once, outside 04:00–09:30 New York. Effects: Tailscale restarts, so tailnet
connections to the NAS drop for a few seconds. Note the ProArt reaches `\\SiuDiskstation` over Tailscale (the name
resolves to 100.79.212.23), so the session-lock read and the 2-hourly pull go that way; SMB (445) listens on every
address and keeps working in TUN mode, and during the restart the lock read warns and carries on. From then on
`127.0.0.1` stays local to the NAS. If anything (containers, SMB, DSM) stops answering afterwards, undo (below).
Afterwards on the ProArt:
```
Set-Location D:\Trading
.\.venv\Scripts\python.exe deploy\nas_trader\check_nas_exposure.py --out "D:\Trading\Claude outputs\nas_exposure_after_tun.txt"
```
Expected: ALL CHECKS PASSED. To undo: delete the task and restart the Tailscale package in Package Center.
Alternative if you prefer not to change the NAS: Tailscale admin console ACLs that let tailnet devices reach the NAS only
on 22, 445, 5000, 5001. It needs keeping in step with every new NAS service, so TUN mode is the better fix.

C. Optional, read-only: can containers on the journal networks reach the paper API? (Expected: closed. If OPEN, an
internet-facing container could reach a no-password API, and that becomes a High finding.)
```
sudo docker run --rm --security-opt seccomp=unconfined --network thesiuz-edge --entrypoint python trade-journal-recorder:latest -c "import socket;s=socket.socket();s.settimeout(3);print('edge -> paper API', 'OPEN' if s.connect_ex(('172.21.0.2',4004))==0 else 'closed')"
sudo docker run --rm --security-opt seccomp=unconfined --network trade-journal_default --entrypoint python trade-journal-recorder:latest -c "import socket;s=socket.socket();s.settimeout(3);print('journal -> paper API', 'OPEN' if s.connect_ex(('172.21.0.2',4004))==0 else 'closed')"
```
(The address 172.21.0.2 was the trader Gateway on 2026-10-31; `sudo docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' trader-ib-gateway` confirms it.)

## Undo
Revert the repo changes listed above. Nothing on the NAS was changed by this step.

## Next steps (board ids)
- Ben: A now; decide B; optionally C. Then W10-0013 sub 7 (2869871634) → Done after the checker passes.
- W10-0013 sub 8 (2869862689): shadow run. Unaffected.
- W10-0013 sub 9 (2869871795): its unpack commands must end with `sudo chmod 600 /volume1/docker/trader/.env`.
- W10-0013 sub 11 (2887388263): the agent token goes in `.env`; the portal becomes a (no-orders) control path.
