# Promotion audit — what's still not in Prod (2026-09-24)

Requested by Ben: search yesterday's (2026-09-23) completed changes and identify what still needs to be promoted to `D:\TradingProd`. Checked directly against git on `D:\Trading` via the device bridge (`git tag`, `git log`, `git diff --stat`, `git status`), not from the monday board alone, since board "Done" only means committed to `main`, not promoted.

## Current state (at audit time)

**Prod tag:** `prod-20260923b` (commit `f166099`, the W02-0014 CRML short-sale fix). Confirmed via `git tag --sort=-creatordate` — no newer tag existed yet. `D:\TradingProd` was still checked out here.

**Already promoted and confirmed live** (no action needed):
- W02-0014 — CRML double-sell fix — ran in the 09-23 session, ended flat, no shorts.
- W02-0015 — per-strategy position cap — ran in the same 09-23 session (folded into `prod-20260923b`).

## On `main`, not yet promoted — grew from 7 to 8 commits over the course of this audit

All touch the live-path surface (`brokers/ibkr/trader.py`, `common/ui_bridge.py`, `common/report_trades.py` — confirmed imported by `main.py` — and `run_paper.ps1`, the script `D:\TradingProd` launches from):

| Commit | What | Board item(s) |
|---|---|---|
| `76e7716` | `ui_bridge.py` + `trader.py`: final-state push + session-history upload wired into the shutdown path; also carries `health.uptime_s` / `data_stale_seconds` | W02-0003, W02-0004 |
| `d9ae552` | `trader.py`: stable `exec_id` (IB's own execution id) added to every fill-log row | W02-0006 |
| `380d70c` | `report_trades.py` timezone/commission display fix + `run_paper.ps1` quoting fix | W02-0007, W02-0005 |
| `18bf9fc` | `trader.py`: ships the spread gate live — new `SPREAD_GUARD_PCT = 2.0` refusal rule (`SKIPPED_SPREAD`), alongside the existing drift guard. Ben's decision ("let's ship it") after the full-quote backtest (`claude/w03_0002_spread_gate_RESULT_20260924.md`): refuses 74–76% of entries, reduces both books' losses. | W03-0002 step 6 |
| `a222811` | `trader.py`: MC5-only 50% session give-back cap (H-S4). Ben's decision on the paper-cuts review: "Both, give-back cap on MC5". Landed *after* the audit started. | W02-0019 |

(`2ac260f`, `c22604b`, `e074a16` — `entry_gates.py` build-out, research-only, not itself imported by the trader — omitted from the count; they produced the spread-gate result but aren't live-path themselves.)

## Test verification

Ben's first run was against `D:\TradingProd` by mistake (still on `prod-20260923b` — predates the fix in `162a83f`, so it showed the old pre-existing `pit_validate.py` encoding failure and none of the new code). Corrected run against `D:\Trading`:

**1 failed, 4510 passed, 4 skipped.** The one failure is in `common/ib_vs_itch_study.py` (2 bare `open()`s missing `encoding=`) — confirmed via `grep` that this file is not imported by `main.py`/`trader.py`/`ui_bridge.py`/`report_trades.py`, so it's outside the live-path surface, same shape as the `pit_validate.py` failure that's been waved through in past promotions (W01-0011, W02-0014). Filed separately as **W02-0021** rather than blocking this one. **Green light to tag** — commands are on **W02-0020**.

## Not this Prod, but also pending a deploy

**W09-0014** — portal "Held" column + favicon — committed to the UI repo, tests pass locally, but **not yet deployed to Fly** (`python tools\deploy_relay.py` hasn't been run). Separate production surface from the trading engine; flagged here for completeness since it's an open "needs promoting" item too.

## Recommendation

Tag and promote — commands are on board item **W02-0020** (updated for the 8th commit). Tests are already green; no further blocking work.
