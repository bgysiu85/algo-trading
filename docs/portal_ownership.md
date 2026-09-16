# Who owns what between the portal and the trading logic

Decided 2026-09-16, after the question "should the UI detach from the logic
repo entirely?" The answer was no, and this file is the alternative.

## The measurement the decision rested on

Eight portal commits exist. All eight touch `common/ui_bridge.py` and
`tests/common/test_ui_bridge.py`, and **no strategy-side commit has ever
touched either file**. The only genuinely shared file is
`brokers/ibkr/trader.py`, where the portal's footprint is four call sites out
of 34 commits. There has never been an overwrite or a merge conflict between
the two sides.

What has actually gone wrong was process, not layout: building on a stale base,
inventing a `portal-on-prod` branch, and duplicating a feature the strategy side
had already written (`9fa812a`). Detaching the repo fixes none of those, and
would make the last one *more* likely, not less -- the duplicate was caught by
reading their code, which a separate repo discourages.

## Why not detach

The adapter is not loosely coupled to the trader. It reads `trader.strategies`,
`adapter.trail_pct`, `max_positions`, `paused`, `disabled_strategies`, and the
fill-log CSV columns, and it depends on `StrategyAdapter` being a frozen
dataclass. That coupling is real. Moving the adapter to another repo would not
reduce it -- it would hide it, and replace tests that run against the real
trader objects with tests that run against a fake.

That distinction is not theoretical here. The `FrozenInstanceError` defect was
caught precisely because the test used the real `StrategyAdapter`; a fake that
allowed the assignment would have passed. The recurring failure mode in this
project is a test environment more permissive than the real one. A separate
repo would institutionalise it.

The detach becomes reasonable only if the trader first grows a narrow published
interface -- a state snapshot plus a command handler -- that the strategy side
owns and tests. Until that exists, the adapter belongs next to what it reads.

## The boundary

| Owned by | Files |
| --- | --- |
| Portal | `common/ui_bridge.py`, `tests/common/test_ui_bridge.py`, `tests/common/test_config_row_is_invisible_to_readers.py`, `docs/portal_*.md`, and the whole `D:\Trading UI` repo (relay, web app, agent, contract schema) |
| Strategy | everything else, including all four portal call sites in `brokers/ibkr/trader.py` |
| Shared | `tests/common/test_portal_hook_surface.py` -- changed by agreement |

## The four call sites

1. `MCLPaperTrader.__init__` -- `self.ui = None`
2. `MCLPaperTrader.run` -- `await self.ui.tick(self, now_et)`, guarded and wrapped
3. `main_async` -- `trader.ui = ui_bridge.UIBridge.from_env(...)`
4. `main_async` -- the loud refusal on `bridge_state() == "configured-but-unattached"`

Every one is optional by design, so that a dead relay cannot disturb trading.
The cost of that design is that **dropping a hook breaks nothing loudly**: the
trader trades, the suite passes, and the dashboard just stops updating.
`tests/common/test_portal_hook_surface.py` exists to convert that silence into a
failing test. If you are changing a hook deliberately, change that test in the
same commit -- that is the mechanism working, not fighting you.

## Process rules

- One branch, `main`. No feature branches, no `portal-on-*`, no `claude-work`.
- Production is a tag plus a second working copy, never a branch.
- Bundles are cut from `main`, with a base that contains the tip of
  `origin/main`, and land in `D:\Trading\Claude outputs`.
- Fetch with `git fetch <bundle> main` then `git merge FETCH_HEAD`, which
  creates no branch.
- Before building anything on the portal side, read the strategy side's recent
  commits first. The `9fa812a` duplicate was a day of work that a `git log`
  would have prevented.
