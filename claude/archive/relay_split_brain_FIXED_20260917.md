# Relay split brain: two Fly machines, one in-memory state slot — FIXED

**Date:** 2026-09-17 · **Repo:** `D:\Trading UI` · **Commit:** `235ce8c`
**Status:** fixed, deployed and verified in production.

## Symptom

The portal at `trader.thesiuz.com` showed **"waiting for agent"** while the
trader on the ProArt was connected to IB Gateway and pushing `POST /api/state`
every ~5 seconds, logging success each time. Nothing errored on either side.

## Cause

Fly was running **two machines** behind the same hostname
(`d8d996d7b94138` and `080ee96da23d78`). The relay keeps the last pushed state
in memory in a single slot. The trader's push landed on one machine; the
browser's `GET /api/ui/state` was answered by the other, which had never
received a push. Neither machine was misbehaving — each did exactly what it was
asked, to a different copy of the app.

The second machine came from `fly deploy`, whose `--ha` flag **defaults to
true** and creates a spare for availability. Correct for a stateless app; a
split brain for this one.

## Immediate repair (done, verified)

```
fly scale count 1 --app thesiuz-trader-relay
```

Logs confirmed `080ee96da23d78` shut down cleanly (SIGINT → application shutdown
complete → reboot) at 07:27:21–22, and every request from 07:27:22 onward was
served by `d8d996d7b94138`.

## Why fly.toml could not prevent it

There is **no machine-ceiling key in fly.toml**. The file contained
`min_machines_running = 1`, which reads like a guarantee and is not one:

- it is a **floor**, not a ceiling; and
- it is **ignored entirely** unless `auto_stop_machines` is `"stop"` or
  `"suspend"` — which here it is not (`false` / off, deliberately).

So the line was dead config that answered the question wrongly. It was removed
rather than corrected in place, and a test now fails if it comes back.

## Permanent fix

The ceiling is enforced at deploy time by **`tools/deploy_relay.py`**:

1. counts the machines **before** deploying (reports a pre-existing split brain);
2. passes **`--ha=false`**;
3. counts them **after**, and exits non-zero unless the answer is exactly one.

Step 3 is the point — a deploy that succeeds into a split brain looks fine.
It names `--config` and the repo root explicitly, so it works from any
directory.

Deploy command is now:

```
cd "D:\Trading UI"
python tools\deploy_relay.py          # deploy with the guard
python tools\deploy_relay.py --check-only   # count without deploying
```

## Tests

`tests/test_deploy_relay.py`, 20 tests. Verified by **mutation**, not just by
passing — each of these fails a named test:

| Mutation | Test that catches it |
|---|---|
| drop `--ha=false` | `test_the_deploy_disables_high_availability` |
| disable the post-deploy count | `test_a_deploy_that_leaves_two_machines_fails` |
| count destroyed machines | `test_a_destroyed_machine_is_not_counted` |
| re-add `min_machines_running` | `test_fly_toml_does_not_claim_a_machine_ceiling_it_cannot_enforce` |

Full suite: **183 passed**.

## Verified in production, 2026-09-17 ~08:40 UTC

Deployed with `python tools\deploy_relay.py` during a live pre-market session.

- **Machine count: one.** `--check-only` reports
  `d8d996d7b94138  started  syd` — the **same machine ID** that survived the
  scale-down, so `fly deploy` updated it in place rather than adding a spare.
- **Relay healthy from outside the ProArt.** `GET /api/health` on
  `thesiuz-trader-relay.fly.dev` returned
  `{"ok":true,"contract_version":"1.7.0","has_state":true,...}` with
  `last_state_at` advancing across repeated probes.
- **Trader live throughout.** `var\fills\mcl_fills_20260917.csv` was being
  written during the checks (MC5 / DAIC, pre-market).

### One transient worth recording

A probe taken during the deploy returned `"has_state":false,
"last_state_at":null`. Three probes afterwards were all `true` with advancing
timestamps, and the machine count is one, so this was the **restart window**,
not a recurrence: `fly deploy` restarts the machine in place, the state store is
in memory, and it is empty until the trader's next push lands ~5 seconds later.

**Operational consequence:** deploying the relay mid-session is survivable but
not free — state refills in about five seconds, but anything in flight is lost.
Deploy outside session hours.

## Not fixed — the real design issue

This constraint only exists because the relay's state store is a single
in-memory slot. Moving it somewhere both machines can see (the relay's volume,
or Redis) would make the app genuinely horizontally scalable and delete the
whole problem — including the restart-window gap above, which has the same root
cause. That is a design change, not a deploy flag, and is worth doing before
anything else needs a second machine.

## Related

- `docs/fly_migration.md` → section **"The relay runs exactly one machine"**
- Milestone 4 (relay to the cloud) is complete and verified end to end:
  trader on the PC → Fly relay (syd) → Fly-hosted Pocket ID → browser, with
  nothing depending on the ProArt staying awake.
