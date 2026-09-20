# Partial exits in Closed today, and the portal/logic boundary — 2026-09-16

Two bundles, both verified fast-forward against the live repos:

| Bundle | Repo | Ref | Requires |
| --- | --- | --- | --- |
| `D:\Trading\Claude outputs\claude-ui-bridge-20260916d.bundle` | `D:\Trading` | `main` = `03e1b33` | `0e82135` |
| `D:\Trading UI\Claude outputs\claude-20260916a.bundle` | `D:\Trading UI` | `main` = `8ebacf8` | `ba1091c` |

## The ruling, verified rather than taken on trust

The strategy side ruled that a partially filled **exit** belongs in *Closed
today*. Checked against the trader before changing anything:

- A partial exit cancels the remainder, reduces `pos.qty` and leaves the
  position open (`trader.py`, `"still holding %d after partial exit"`).
- `trade_pnl` on that row is `(exit_px - entry_price) * filled - commission` —
  realised money on the shares that went, not a projection.
- No double counting: `pos.qty` falls with each partial, so quantities are
  disjoint, and `entry_price` is written once at position open
  (`trader.py:1746`) and never reassigned.

**One thing neither side mentioned, found by reading rather than reasoning from
the status name:** `common/friction.py` already defines
`FILLED = ("FILLED", "PARTIAL_FILL")`, and the trader's own position
reconstruction reads both. The portal was the *only* reader in the codebase
using `FILLED`-only. That is independent corroboration of the ruling.

## The delta: exactly $0.00

Measured across all nine sessions on record in `D:\Trading\var\fills`:
**138 buys, 138 sells, every one `FILLED`. Not a single `PARTIAL_FILL` row
exists.** Old sum and new sum are identical; the P&L column does not move, and
there is no before/after screenshot discrepancy to misread.

The corollary matters more: **this path has never been exercised by real data.**
Both the pairing fix (`55615ef`) and this widening are preventive, validated by
unit tests only. `EXIT_ABANDON_POLLS` (`971e88a`) re-prices an unfillable exit
after two polls instead of waiting out the full twenty seconds, so partial fills
become more likely from the next session — which is the first real test of any
of it. **Worth checking the fill log for `PARTIAL_FILL` rows after the next
session and confirming the portal renders them.**

## The quantity condition, and where it was actually broken

`qty` was already in the contract and already a column. The gap was elsewhere:
the column was `minor`, and `.scroll td.minor { display: none }` drops minor
columns at phone width. The one column distinguishing a partial close from a
full one was invisible on the device the portal is mostly read from. It is no
longer minor, and a Playwright test at 390px fails if it becomes so again —
verified by restoring `minor` and watching the test fail.

Their stated rationale was also slightly short: quantity **alone** cannot tell
the two apart. "40" is identical whether it closed a 40-share position or part
of a 100-share one; the only other clue is the same symbol appearing twice,
which is an inference. So contract 1.7 adds an optional `partial` boolean and
the page renders `40 · partial`.

Also fixed: the replay agent's `CONTRACT_VERSION` said `1.4` while it had been
publishing `entry_ts_et` and `bar_minutes` since 1.5/1.6 — never bumped when
those landed.

## Should the UI detach from the logic repo? No — see `docs/portal_ownership.md`

Ben asked whether the portal should live entirely outside the logic folders to
avoid commit overlap. The measurement says the overlap isn't real:

- Eight portal commits exist. All eight touch `common/ui_bridge.py` and its
  test; **no strategy-side commit has ever touched either.**
- The only shared file is `brokers/ibkr/trader.py` — four call sites out of 34
  commits.
- There has never been an overwrite or a merge conflict between the two sides.

What has gone wrong was process, not layout: a stale base, an invented
`portal-on-prod` branch, and duplicating `9fa812a`. Detaching fixes none of
those and would make the duplication *more* likely.

The cost would be real: the adapter reads `trader.strategies`,
`adapter.trail_pct`, `max_positions`, `paused`, `disabled_strategies` and the
fill-log columns, and depends on `StrategyAdapter` being frozen. Moving it out
replaces tests against the real objects with tests against a fake — this
project's recurring failure mode, and exactly how the `FrozenInstanceError`
defect was caught. Detaching only becomes reasonable if the trader first grows a
narrow published interface that the strategy side owns and tests.

Instead the boundary is written down, and the four call sites are pinned by
`tests/common/test_portal_hook_surface.py`. Every hook is optional so a dead
relay cannot disturb trading; the cost of that design is that **dropping a hook
breaks nothing loudly** — the trader trades, the suite passes, the dashboard
quietly stops updating. Removing the loop's tick now fails two tests instead
(verified by removing it).

## Tests

- `D:\Trading`: 2,811 passed, 6 failed, 49 skipped. The six are `databento`
  absent from the sandbox and fail identically on `0e82135` itself.
- `D:\Trading UI`: 152 passed.

## Housekeeping

- A stray `claude-ui-20260916a.bundle` was written to `D:\Trading\Claude outputs`
  before the UI repo's own conventions were checked. It is identical to
  `D:\Trading UI\Claude outputs\claude-20260916a.bundle`; use the latter.
- `INBOUND-DO-NOT-MERGE-tip-5ab22cc.bundle` in `D:\Trading\Claude outputs` was a
  working copy of Ben's tip and can be deleted.
- Both repos still carry fully-merged stale branches (`claude-work` in the UI
  repo; seven in `D:\Trading`). All contain zero commits not in `main`.
