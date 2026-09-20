# Cloud migration — stage 1 complete, 2026-09-17

Milestone 4: moving the portal off Ben's ProArt so it survives the machine
sleeping. **Nothing live changed in stage 1.** The PC still serves both
hostnames through the Cloudflare tunnel.

## What exists now

| | |
| --- | --- |
| `thesiuz-trader-relay` | Fly app, syd, `shared-cpu-1x` 256 MB, always-on |
| `thesiuz-pocket-id` | Fly app, syd, `shared-cpu-1x` 512 MB, always-on |
| `pocket_id_data` | 1 GB volume, `vol_vp2609l2kgge3pk4`, encrypted, snapshots on |
| Relay health | `{"ok":true,"contract_version":"1.7.0","has_state":false}` — verified by fetching it |
| Pocket ID | 2.14.0, **pinned by digest** `sha256:01540977…b13c4a`, database seeded |

Cost: US$5.28/month (1.94 + 3.19 + 0.15). Both machines are deliberately
always-on — a dashboard that cold-starts before answering is one you stop
trusting, and an identity provider asleep IS the outage this removes.

## What the relay needed: nothing

`app/config.py` already read everything from the environment; `run_relay.py`
merely loaded `var/auth.env` into it. So the image ships `app/` and `contract/`
and nothing else, and secrets arrive as Fly secrets. `var/` is in
`.dockerignore` — an image layer is somewhere a credential can never be removed
from.

## Things that bit, and what closed them

**`docker ps` reports only `:latest`.** That is a label the publisher can
re-point, not a version. The pin is the digest from `RepoDigests`, which names
bytes. Against the database holding the only way into the portal, a redeploy
must not be able to pull a schema migration nobody chose.

**flyctl has no winget package.** The runbook said it did, from memory rather
than documentation, and Ben hit "the term 'fly' is not recognized" on the next
command. Corrected to the PowerShell installer — plus the real trap, that the
installer edits PATH and an already-open shell keeps the PATH it started with.

**`fly ssh sftp` refuses to overwrite.** Pocket ID had already created its own
empty database on the volume. Seeded by uploading to `incoming.*`, then a single
swap that moves them into place, chowns to `1000:1000`, and deletes the `-shm`
so SQLite rebuilds it — a stale shared-memory index is the one part of a WAL-mode
copy that can cause trouble.

**Seed from the backup, not the live files.** `infra/pocket-id/data` is being
written to continuously; the backup was taken with the container stopped and
passed `integrity_check`. Proof it worked: Pocket ID's own empty database was
4,096 bytes, and after the swap `pocket-id.db` is 475,136 — byte-for-byte the
upload — with both it and the WAL touched again after restart and the `-shm`
rebuilt.

**A false alarm I caused.** `git status --porcelain` on Ben's machine left a
stale `.git/index.lock` (that shell cannot delete), and git then reported 38
files as modified because it could not refresh its index. His tree was clean all
along. Read-only git on his machine means `log`, `diff`, `rev-parse`,
`bundle verify` — **not** `status`.

## Secrets never passed through a clipboard

`tools/fly_secrets.py` reads values from `var/auth.env`, `var/agent_token.txt`
and `infra/pocket-id/.env` and pipes them to `fly secrets import` on stdin —
nothing typed, nothing echoed, nothing in PowerShell history or the process
list. It prints each secret's name and the first 8 hex of its SHA-256, so what
is on Fly can be checked against the files without either being shown. It
refuses to half-configure an app: a missing agent token means the trader could
never push; a non-https `UI_BASE_URL` means the session cookie is not marked
secure. Both are quiet at deploy time and loud only much later.

## Known, deliberate, not yet done

- The trader still pushes to `http://127.0.0.1:8000`; `has_state:false` on the
  cloud relay is correct until stage 3.
- Signing in to either Fly hostname fails. `APP_URL` is `id.thesiuz.com` and a
  passkey is bound to the domain that created it, so Pocket ID refuses on
  `*.fly.dev` — **before** it looks at any user, which is why that error does not
  by itself prove the database seeded. The file sizes do.
- `ALLOWED_SUBJECTS` is empty: anyone Pocket ID admits reaches the portal.
  Correct while it has exactly one account. Not introduced by this migration.
- Four branding images in `uploads/` were not copied; Pocket ID on Fly shows its
  defaults. Cosmetic.

## Stage 2 — the passkey test

Point `id.thesiuz.com` at Fly, leaving `trader.thesiuz.com` on the tunnel. Sign-in
then comes from the cloud while the relay is still local, so the passkey is the
only untested thing at that moment and rollback is one DNS record.

Order matters: issue the certificate via an `_acme-challenge` record **before**
moving traffic, so there is no window where the hostname resolves to Fly without
a valid certificate.
