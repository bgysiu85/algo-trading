# Bundle delivery: always cut the complete history

**Date:** 2026-09-18 · **Applies to:** every git bundle delivered to Ben

## The rule

```
git bundle create <name>.bundle main          # the whole branch
```

**Not** `git bundle create <name>.bundle <previous-tip>..main`.

`git bundle verify` on the result says *"The bundle records a complete
history"*, which means it has **no prerequisites**: it applies to Ben's repo
whatever state it is in, including a fresh clone. Applying an older bundle after
a newer one is a harmless "Already up to date" rather than an error.

Cost: **284 KB** for the whole UI repo, against ~10–50 KB for a delta. That is
nothing for a file copied onto the same machine.

## Why — the incident

Bundles were being cut as deltas against **the previous bundle's tip**, which
silently assumed Ben merged every one, in order, before the next arrived.

On 2026-09-18 he merged up to `1af265a` and then skipped four. The next fetch
failed with:

```
error: Repository lacks these prerequisite commits:
error: f611b4cb588c87209299caa1670d146bb4063a0e
```

In his words: *"i just always assumed that each bundle will bring in the
previous bundles' changes"* — which is the reasonable assumption, and the one
the tool should have satisfied. A complete-history bundle satisfies it exactly.

The delta approach had also been applied inconsistently: the first bundle of the
day WAS cut against his real HEAD, read from his machine. That habit was then
dropped without noticing, which is what let four bundles in a row inherit the
same broken premise.

## Secondary rule, still worth keeping

Before cutting, read his actual HEAD:

```
cd "$HOME/mnt/Trading UI" && git log --oneline -3
```

With complete-history bundles this is no longer load-bearing, but it tells you
what he has merged, which is worth knowing when writing the handover message —
and it catches the case where he is working from a different branch or a
detached HEAD.

## The commands he runs, unchanged

```
cd "D:\Trading UI"
git fetch "Claude outputs\<name>.bundle" main
git merge FETCH_HEAD
```

`git fetch` into a bundle creates no branch; `git merge FETCH_HEAD` fast-forwards.
Nothing about his side changes — only which bundle is handed to him.

## What must never change

- No history is ever rewritten. ~334 commits in `D:\Trading` are authored by Ben
  and the strategy chat; `prod-*` tags point into that history and
  `D:\TradingProd` is checked out against one.
- Delivery is by bundle because there is nowhere to push: `origin` in
  `D:\Trading UI` is a bundle **file** (git cannot push into one), the sandbox
  has no push credentials, and `D:\Trading`'s GitHub origin returns 403.
