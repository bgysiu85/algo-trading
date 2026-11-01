# W10-0013 sub 13 (portal history database: Neon -> NAS Postgres) - RESULT, 2026-11-01

Status: **built and tested in the repo; not deployed.** Ben runs `deploy/nas_trader/NAS-TRADER-SETUP.md` part 7 (7 steps, one sitting,
outside 04:00-09:30 New York). Model/effort used: Sonnet, Medium.

## Decision (Ben, 2026-11-01): the portal gets its OWN Postgres, not a database inside `journal-db`
Why: the relay is internet-facing; sharing `journal-db` would need `journal-db` on a network the relay reaches (an edit of the Trade Journal
compose, a `journal-db` restart, and a route from the relay to the journal's database server). Cost of the choice: ~150 MB RAM (3.9 GB free)
and its own backup, built here.

## What exists
| Piece | File |
|---|---|
| `portal-db` (postgres:18, `trader-portal-db`) and `portal-db-backup`, profile `portal`; private network `portaldb` (`internal: true`: no internet, no ports) shared with the relay only | `deploy/nas_trader/compose.yaml` |
| Daily pg_dump, each dump checked with `pg_restore --list`, 14 days kept (newest 3 always) | `deploy/nas_trader/portal_db_backup.sh` |
| `.env` helper (password made on the NAS, switch to / rollback from Neon, status; prints no secret) | `deploy/nas_trader/portal_db.sh` |
| Neon -> plain SQL file (read-only, one transaction, counts + totals printed, no secret printed) | `deploy/nas_trader/neon_export.py` |
| Watcher also alerts when no portal dump is under 26 h old | `deploy/nas_trader/watch.py` (sub 12 container) |
| Guide part 7 incl. rollback; `.env.example` lines | `NAS-TRADER-SETUP.md`, `.env.example` |
| 12 tests (network isolation, helper switch/rollback in bash, export SQL, no-secret rule, backup age) | `tests/deploy/test_portal_db.py` |

`tests/deploy`: 166 passed. `neon_export.py --check` ran against real Neon (read-only): **285 closed_trades, 91 order_outcomes, 2-23 Sep 2026,
sum(net_pnl) = -1413.13, sum(n) = 1778.** A dump of it is at `Claude outputs\portal_history.sql` (376 INSERTs, LF); the guide regenerates it at cutover.

## Not verified
- The SQL file was **not loaded into a Postgres** (none on the ProArt, no docker/root on the NAS): the guide loads it in one transaction with
  `ON_ERROR_STOP` and compares counts/totals with the export before anything switches.
- `docker compose config` and the containers were not run here (guide step 3 runs `config --quiet`). `postgres:18` as `1026:100` on
  `/volume1/docker/trader/portal-db` follows the journal-db pattern; the folder is created and chowned in step 2.
- The Reporting tab against the NAS database is checked by eye in step 6 (totals must match step 4).

## Facts
- Neon's history stops at 23 Sep 2026: no session has been uploaded since (the trader has been dry / shadow), so the export is small and stable.
- Data on disk: `/volume1/docker/trader/portal-db`; dumps: `/volume1/docker/trader/portal-backups` (not on the `trader-data` share the ProArt reads).
  Neither folder is copied off the NAS yet; DSM-level backup of `/volume1/docker` is Ben's existing arrangement (not checked).
- The password is generated on the NAS and never leaves it; the relay's `RELAY_DATABASE_URL` becomes `postgresql://portal:<pw>@portal-db:5432/portal`.

## Next steps (board ids)
- W10-0013 sub 13 (2887411991): Ben runs part 7; one week later deletes the Neon project and the `NEON_DATABASE_URL` line.
- W10-0013 sub 10 (2869862618): the two stopped Fly apps can be deleted after this sub's week of clean runs.
