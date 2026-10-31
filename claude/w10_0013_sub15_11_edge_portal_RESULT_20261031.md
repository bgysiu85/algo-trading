# W10-0013 sub 15 (edge project) and sub 11 (portal relay) - RESULT, 2026-10-31

Status (updated 2026-11-01): **all deployed and working.** Edge project live (tunnel `edge-tunnel`, network `thesiuz-edge`), journal back, relay
`trader-relay` serving trader.thesiuz.com, Pocket ID on the NAS (`edge-pocket-id`) serving id.thesiuz.com; passkey login tested in a private
window on all three sites; exposure check 25/25 after each step. Fly Pocket ID machine stopped (not deleted); Fly relay still running.

What differed from the plan: the old tunnel and journal-login were NOT running (Cloudflare error 1033), so the "swap" was a first start; a
compose check on the NAS caught a `:?` on the Pocket ID profile that stopped the whole project (fixed, tested); `scp` needs `-O` (SFTP is off
on the NAS); `/volume1/docker/trader` is owned by sysadmin so files go via `/volume1/docker/edge/staging`; the Fly Pocket ID database has to be
copied while the machine RUNS (a stopped machine has no sftp), and Git Bash needs MSYS_NO_PATHCONV=1 for `fly ssh sftp`.

Original status line: built and tested in the repo before deployment.
Model/effort used: Sonnet, Medium (right for this).

## What exists now
| Piece | File |
|---|---|
| `edge` compose project: tunnel `edge-tunnel` (same token), network `thesiuz-edge` (edge creates it), Pocket ID in profile `id` | `deploy/nas_edge/compose.yaml`, `.env.example` |
| Guide: copy, swap (one block), check, undo, Pocket ID move, rules | `deploy/nas_edge/NAS-EDGE-SETUP.md` |
| Portal relay `trader-relay` in the trader project (profile `portal`, external network `thesiuz-edge` only, no ports) | `deploy/nas_trader/compose.yaml` |
| Relay steps (part 5): copy, install packages, secrets, start, route, cutover, undo | `deploy/nas_trader/NAS-TRADER-SETUP.md` |
| Relay secrets helper (names + fingerprints only, LF output) | `deploy/nas_trader/make_relay_env.py` |
| Exposure check: ports 8080 (relay) and 1411 (Pocket ID) must be closed on the home address | `deploy/nas_trader/check_nas_exposure.py` |
| Tests (138 pass in `tests/deploy` with `.venv`) | `test_nas_edge_compose.py`, `test_make_relay_env.py`, additions to `test_nas_trader_compose.py`, `test_check_nas_exposure.py` |
| Matching Trade Journal change (NOT in that repo) | `Claude outputs\trade_journal_compose_sub15_NEW.yaml` (full file) and `trade_journal_compose_edge_sub15.patch` (diff) |

Not committed: the task did not ask for a commit. Files to commit when Ben agrees: the ones in the table (all under `deploy/`,
`tests/deploy/`, this doc). Unrelated modified files in the tree (wick_rev, fill_realism, docs/research, futbt/holdout) are untouched.

## Facts found on the way (read-only)
- **The NAS journal `compose.yaml` differs from the repo copy in one line:** the NAS default tunnel image is `cloudflared:2026.9.3`,
  the repo says `2026.10.3`. So the edge tunnel is pinned (guide part 2) to whatever the old tunnel runs now: a move, not an upgrade.
  Otherwise the two files are identical, so replacing the NAS copy with the NEW file loses nothing.
- **`/volume1/docker/trader` and its `.env` belong to `sysadmin`** (the `claude` login cannot write there). All copies are staged in
  `/volume1/docker/edge/staging` (writable) and moved by Ben's `sudo` session; `.env` additions are staged in a file and appended.
- The NAS trader compose.yaml equals git HEAD (md5 dc25c3bd...), so the added `relay` service is the only difference.
- `trader.thesiuz.com` is a CNAME to the Fly app `thesiuz-trader-relay` today. The Cloudflare route can only be added after that DNS
  record is pointed at the tunnel; that edit IS the switch for the portal (and `id.thesiuz.com` likewise for Pocket ID).
- The trader shares the Gateway's network, so it cannot reach the relay over Docker without putting the Gateway on `thesiuz-edge`
  (which would expose the paper API to an internet-facing network; sub 7 test C checks exactly that). Design: the trader pushes to
  `https://trader.thesiuz.com` (agent token), the relay is on `thesiuz-edge` only. A test fails if the Gateway or trader gets `edge`.
- Relay on the NAS: plain `python:3.12-slim` plus mounted `srv/` (app, contract, history) and `deps/` (pip --target), because
  Synology cannot run a Dockerfile `RUN` step. The `Dockerfile` in the UI repo is not used.
- The relay is closed unless OIDC is configured (`app/auth.py`: open mode serves localhost only), so a half-set `.env` cannot publish it.

## Decisions for Ben
1. **Pocket ID: copy the Fly database (recommended) or re-register.** The copy keeps users, the `journal` group, the "Trade Journal"
   client and the passkey (bound to `id.thesiuz.com`, not the server); needs the same `ENCRYPTION_KEY`. Re-registering loses the group
   and client, and the client secret changes (journal `.env` must follow). Guide: edge part 5.
2. **When** to do the swap: a quiet window outside 04:00-09:30 New York, not during a watched shadow-run session. Weekend daytime in Sydney.
3. Whether to register the `edge` project in DSM's Project screen (guide has the unticked-box recipe; optional).

## Order for Ben
1. Edge parts 1-4 (swap, journal back up, exposure check). 2. Journal chat commits the compose change in its repo.
3. Trader part 5 steps 1-4 (relay up, nothing else touched). 4. Edge part 5 (Pocket ID) and relay step 5/7 (DNS) together, then
retire Fly. 5. Relay step 6 (`UI_RELAY_URL`) with sub 9's cutover.

## Not verified (no root, no docker here)
- No compose file was run through `docker compose config`; Ben's guide steps do (`CONFIG-OK`). Tests check the text.
- `fly` commands, Cloudflare dashboard steps and the Pocket ID startup (`user: 1026:100` on the copied SQLite) were not run.
- The exact tunnel image on the NAS (guide reads it from the running container).
- Where the ProArt trader pushes today (Fly vs a local relay) was not checked; it is unaffected until the DNS switch, after which a
  trader still using the Fly URL stops reaching the portal.

## Still open
- UI_RELAY_URL on the NAS trader with sub 9's cutover; then stop the Fly relay `thesiuz-trader-relay`; delete both Fly apps after sub 13.
- Journal chat: commit the Trade Journal compose change. Pocket ID custom logo/background images were not copied. Delete `/volume1/docker/edge/staging`
  (holds the Pocket ID database copy) when happy.

## Next steps (board ids)
- W10-0013 sub 15 (2891910299): Ben runs edge parts 1-4; Journal chat commits the compose change (W17 side).
- W10-0013 sub 11 (2887388263): after sub 15 swap; part 5; Pocket ID move; DNS; retire Fly.
- W10-0013 sub 9 (2869871795): relay step 6 (`UI_RELAY_URL`) belongs with the cutover; its unpack commands still end with `chmod 600 .env`.
- W10-0013 sub 13: Neon history to the NAS Postgres; then `RELAY_DATABASE_URL` changes.
