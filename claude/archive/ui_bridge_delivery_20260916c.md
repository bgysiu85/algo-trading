# Portal delivery 20260916c — supersedes 20260916a and 20260916b

**Bundle:** `D:\Trading\Claude outputs\claude-ui-bridge-20260916c.bundle`
**Ref:** `main` = `55615ef` · **Requires:** `5ab22cc` (Ben's current tip, tag `prod-20260916`)
Verified on Ben's machine with `git bundle verify` — prerequisite present, so the merge is a
guaranteed fast-forward. One commit, no branches created on Ben's side.

## Why two bundles were withdrawn

`20260916a` duplicated the strategy side's `9fa812a`: I built an unconditional session-open
CONFIG row and a `bridge_state` on the **bridge**, not knowing both already existed on the
**trader**. Theirs is better placed — the row records what the trader was running with, and it
gets written even when no bridge is attached. Two writers would have put two rows per adapter
in the ledger at every session start. My copies are deleted in this commit.

`20260916b` was a rebase of four commits (`9d7526f`, `7c9b132`, `4101eb8`, `a20b748`) that I
believed were orphaned. They were not: `main` was fast-forwarded to `portal-on-prod` at
`5ab22cc`, so all four are in `main` under their **original** hashes. The rebased duplicates
(`af8fe04`, `8d767bc`, `582840a`, `c6ce0b8`) are redundant. Neither bundle should be merged.

## What `55615ef` actually contains

- **Partial-fill pairing** (`common/ui_bridge.py`). A partial fill opens a real position and is
  written `PARTIAL_FILL`, so pairing an exit on `FILLED` alone left it with no opening row.
  Pairing now reads both statuses. A second partial uses `setdefault`, not assignment: it *adds*
  to the position the first one opened, so the entry time stays the first fill's. Overwriting
  would have quietly shortened every partially-filled trade while `hold_minutes`, computed from
  the real entry, sat in the next column disagreeing.
- **A loud read failure.** `_fills_today`'s catch runs in the trading path and must not raise,
  but at DEBUG it hid a `NameError` whose only symptom was an empty *Closed today*. A defect
  presenting as "no trades today" in a trading portal is the worst possible disguise. Now
  `LOG.exception`, and a test fails if it reverts to DEBUG.
- **A loud refusal** (`brokers/ibkr/trader.py`). Uses the strategy side's `trader.bridge_state()`:
  when it reads `configured-but-unattached`, a named WARNING plus a forced Telegram message. On
  2026-09-15 that condition was one WARNING inside a wall of IB logging and went unnoticed for
  two hours while the dashboard sat empty.

Tests: **2784 passed, 6 failed, 49 skipped**. The six are `databento` absent from the sandbox and
fail identically on `5ab22cc` itself — verified by checking out Ben's tip and re-running them.

## Open for the strategy side's ruling

A partially filled **exit** is written `PARTIAL_FILL`, and the portal's fills list is
`FILLED`-only, so that round trip never appears in *Closed today* at all. Pairing handles it;
visibility does not. Widening the fills list would change what the P&L column sums, so it is
their call, not mine.

## Workflow

Confirmed and followed: cut from `main`, base contains `origin/main`'s tip, no branches created
on Ben's side, `claude-ui-bridge-YYYYMMDDx` prefix kept. Fetch pattern is
`git fetch <bundle> main` + `git merge FETCH_HEAD`, which creates no branch.

**New this session:** `D:\Trading` is directly reachable from the Cowork session, so bundles are
written straight into `Claude outputs` and verified against the live repo before Ben touches
anything. Delivery is no longer a download. Caveat: that shell cannot delete files, so
index-touching git commands (`git status`) must not be run there — they leave a stale
`.git\index.lock` that blocks Ben's next git write.
