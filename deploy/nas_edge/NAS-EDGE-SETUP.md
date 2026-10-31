# The edge project on the NAS (W10-0013 sub 15, with the portal relay of sub 11)

What this does: moves the Cloudflare tunnel `thesiuz-nas` and the network `thesiuz-edge` out of the trade-journal
project into a new project `edge` (`/volume1/docker/edge`). The tunnel keeps its token, so the Cloudflare dashboard needs
no change for the journal. Later parts add Pocket ID (part 5) and the portal relay (trader project, part 6).

Terms. *Tunnel* = `cloudflared`, which dials out to Cloudflare so no router port is open. *Route* = "this hostname goes to
that container", set in the Cloudflare dashboard. *External network* = a Docker network another project created.

## Limits and risks (read first)
- **Journal downtime of a few seconds to a minute** while the tunnel and `journal-login` are recreated. The recorder, the
  Gateways, `journal-app` and the database are not touched. The trader is not touched.
- **Never two tunnel containers with the same token at the same time.** Part 3 stops the old one before the new one starts.
- **Quiet window:** any time outside **04:00-09:30 New York** (the trader's session), and not while a shadow-run session is
  being watched. Saturday or Sunday daytime in Sydney is the simplest.
- The network `thesiuz-edge` is owned by the trade-journal project today. Docker will not hand it over, so part 3 removes it
  (only possible once `tunnel` and `journal-login` are gone) and `edge` recreates it with the same subnet.
- Claude has no root on the NAS. Every `sudo docker` line below is for Ben's own NAS session.
- Nothing here ever attaches the Gateways or the paper API to `thesiuz-edge` (a test enforces it).

## Part 1 - copy the files to the NAS (PowerShell on the ProArt; changes only /volume1/docker/edge)
```
Set-Location D:\Trading
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/staging"
scp -O -i $k "D:\Trading\deploy\nas_edge\compose.yaml" "D:\Trading\deploy\nas_edge\.env.example" claude@192.168.1.109:/volume1/docker/edge/
scp -O -i $k "D:\Trading\Claude outputs\trade_journal_compose_sub15_NEW.yaml" claude@192.168.1.109:/volume1/docker/edge/staging/trade-journal-compose.yaml
ssh -i $k claude@192.168.1.109 "chmod -R a+rX /volume1/docker/edge"
```
`trade_journal_compose_sub15_NEW.yaml` is the Trade Journal `compose.yaml` without the `tunnel` service and with
`thesiuz-edge` as an external network. **It is not in the Trade Journal repo yet**: the Journal chat commits the same change
(`Claude outputs\trade_journal_compose_edge_sub15.patch` is the diff). Until then the repo copy and the NAS copy differ.

## Part 2 - prepare (NAS session; only the new .env is written)
```
cd /volume1/docker/edge
sudo docker network inspect thesiuz-edge -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
sudo grep -E '^(TJ_EDGE_SUBNET|CLOUDFLARED_IMAGE)=' /volume1/docker/trade-journal/.env
sudo docker ps --format '{{.Names}}  {{.Status}}' | sort
```
Check: the subnet from the first line must equal `TJ_EDGE_SUBNET` in the journal's `.env` (or `172.30.250.0/24` when that line
is absent). Then build `/volume1/docker/edge/.env` (the token is copied, never printed):
```
cd /volume1/docker/edge
sudo sh -c "grep -E '^(CLOUDFLARE_TUNNEL_TOKEN|TJ_EDGE_SUBNET|CLOUDFLARED_IMAGE)=' /volume1/docker/trade-journal/.env > /volume1/docker/edge/.env"
sudo chmod 600 /volume1/docker/edge/.env
IMG=$(sudo docker ps --filter name=tunnel --format '{{.Image}}' | head -1); echo "running tunnel image: $IMG"
echo "CLOUDFLARED_IMAGE=$IMG" | sudo tee -a /volume1/docker/edge/.env > /dev/null
sudo grep -c . /volume1/docker/edge/.env
sudo docker compose config --quiet && echo CONFIG-OK
```
The image line makes this a move, not an upgrade: the NAS's compose file defaults to `cloudflared:2026.9.3` while the repo copy says
`2026.10.3`, so the edge tunnel is pinned to whatever the old tunnel runs right now. (Upgrade later by changing that one line.)
`grep -c .` prints 2 to 4 (the token and the image, plus the subnet and a copied image line when the journal's `.env` sets them).
`CONFIG-OK` means the compose file reads. Nothing is running yet.

## Part 3 - the swap (ONE block, in this order; in the quiet window)
```
cd /volume1/docker/trade-journal
sudo cp compose.yaml compose.yaml.before-edge
sudo docker compose --profile internet stop tunnel journal-login
sudo docker compose --profile internet rm -f tunnel journal-login
sudo docker network rm thesiuz-edge
sudo cp /volume1/docker/edge/staging/trade-journal-compose.yaml /volume1/docker/trade-journal/compose.yaml
cd /volume1/docker/edge
sudo docker compose up -d
cd /volume1/docker/trade-journal
sudo docker compose --profile internet up -d --no-deps journal-login
```
Why this order: the old compose file still knows `tunnel`, so it stops and removes the old tunnel first; only then is the
network free to remove; the new compose file goes in; `edge` creates network and tunnel; `journal-login` rejoins the external
network. `--no-deps` keeps the other journal containers untouched.

If `docker network rm` says "has active endpoints", something else is on `thesiuz-edge`: stop there, run
`sudo docker network inspect thesiuz-edge -f '{{range .Containers}}{{.Name}} {{end}}'` and send Claude the output.

## Part 4 - check (NAS session, then PC)
```
sudo docker ps --format '{{.Names}}  {{.Status}}' | grep -E 'tunnel|journal-login'
sudo docker logs --tail 15 edge-tunnel
sudo docker network inspect thesiuz-edge -f '{{range .Containers}}{{.Name}} {{end}}'
```
Expect `edge-tunnel` and `journal-login` up, a few "Registered tunnel connection" lines, and exactly those two on the network.
Then open https://journal.thesiuz.com in a browser: the Pocket ID login, then the journal. On the ProArt:
```
Set-Location D:\Trading
.\.venv\Scripts\python.exe deploy\nas_trader\check_nas_exposure.py --out "D:\Trading\Claude outputs\nas_exposure_after_edge.txt"
```
Expected: ALL CHECKS PASSED (no new port is open on the home network).

Optional, DSM's Project screen: Container Manager > Project > Create, name `edge`, path `/volume1/docker/edge`, use the existing
compose.yaml, **leave "start the project once it is created" unticked** (as W17-0037), and compare the container list
before and after. The commands above work without it; the screen only registers the project for DSM.

## Undo (part 3)
```
cd /volume1/docker/edge
sudo docker compose down
sudo docker network rm thesiuz-edge
cd /volume1/docker/trade-journal
sudo docker compose --profile internet stop journal-login
sudo docker compose --profile internet rm -f journal-login
sudo cp compose.yaml.before-edge compose.yaml
sudo docker compose --profile internet up -d --no-deps tunnel journal-login
```
`down` removes the edge tunnel before the old one starts, so the same token is never used twice.

## Part 5 - Pocket ID to the NAS (a separate window; this is the one step with a login outage)
Pocket ID's users, passkeys, the `journal` group and the "Trade Journal" client live in one SQLite file in the Fly volume
`pocket_id_data`. Copy the file; re-registering is the fallback (it would lose the group and the client, and the client secret
would change). A copy keeps everything, because the passkeys are bound to the hostname `id.thesiuz.com`, not to the server. It
needs the same `ENCRYPTION_KEY` the database was written with (a Fly secret; `D:\Trading UI\infra\pocket-id\.env` is the local copy).

While Pocket ID is down nobody can sign in to the journal or the portal (existing login cookies keep working until they
expire or refresh). Keep the window short and do it in the quiet window. On the ProArt, stop Fly's copy and fetch the file:
```
Set-Location "D:\Trading UI"
fly machine list --app thesiuz-pocket-id
fly machine stop <machine-id> --app thesiuz-pocket-id
New-Item -ItemType Directory -Force "D:\Trading\Claude outputs\pocket-id-from-fly"
fly ssh sftp shell --app thesiuz-pocket-id
```
At `sftp>` run `lcd D:\Trading\Claude outputs\pocket-id-from-fly`, then `get /app/data/pocket-id.db`, plus `pocket-id.db-wal` and
`pocket-id.db-shm` if they exist, then `quit`. Keep that folder: it is the way back (`fly machine start`). Then to the NAS:
```
Set-Location D:\Trading
$k = "D:\Trading\Claude outputs\.ssh\nas_claude_ed25519"
ssh -i $k claude@192.168.1.109 "mkdir -p /volume1/docker/edge/pocket-id/data"
scp -O -i $k "D:\Trading\Claude outputs\pocket-id-from-fly\pocket-id.db" claude@192.168.1.109:/volume1/docker/edge/pocket-id/data/
```
(If the `-wal` and `-shm` files came down too, scp them the same way.) In the NAS session: add the key to the edge `.env`
(one line `POCKET_ID_ENCRYPTION_KEY=` followed by the `ENCRYPTION_KEY` value, in nano: Ctrl+O, Enter, Ctrl+X), give the folder to the
container user, start, check:
```
cd /volume1/docker/edge
sudo nano .env
sudo chmod 600 /volume1/docker/edge/.env
sudo chown -R 1026:100 /volume1/docker/edge/pocket-id/data
sudo docker compose --profile id up -d pocket-id
sudo docker logs --tail 20 edge-pocket-id
```
Then in the Cloudflare dashboard (Zero Trust > Networks > Tunnels > thesiuz-nas > Published application routes) add
`id.thesiuz.com` -> `http://pocket-id:1411`. If the DNS page already has a CNAME `id` pointing at Fly, edit that record to the
tunnel's `<tunnel-id>.cfargotunnel.com` instead (the route cannot be added while the old record exists). Sign in at
https://id.thesiuz.com with the passkey, check the group `journal` and the client "Trade Journal" exist, then open the journal.
If anything fails: point the CNAME back at Fly and run `fly machine start <machine-id> --app thesiuz-pocket-id`.

## Part 6 - the portal relay
See `deploy/nas_trader/NAS-TRADER-SETUP.md` part 5. It needs part 3 done (the network exists) and, for sign-in, part 5 done.

## Rules a later chat must not undo
- One tunnel container per token. `edge-tunnel` is the only one; the trade-journal compose has no `tunnel` service any more.
- `thesiuz-edge` is created by this project; every other project declares it `external: true`.
- Only `journal-login`, the relay and Pocket ID join `thesiuz-edge`. Never a Gateway, the trader, the recorder or a database.
- No `ports:` in this project. Every edit of a `.env` ends with `chmod 600` on that file.
