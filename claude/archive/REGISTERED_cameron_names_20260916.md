# Item 1c registered, amended, and built — not yet run

**2026-09-16.** Bundle `20260916j`. Commits `f1fa64c` (registration),
`01dfd67` (amendment), `9f8f2d3` (module). Nothing has been run.

**The question:** do Ross Cameron's named symbols beat our ranking on the same
date? Runnable for the first time — 630 symbol-day mentions across 242
sessions our point-in-time universe also covers, joinable only since the
publish dates were recovered this morning.

## The trap, named before the numbers exist

He names the symbol he **traded**, in a recap published after the close. His
pick is made with the whole session known; ours is made at a tick.

This project already paid for that leak: `+$4.72/trade` on a universe chosen
with the day known against `(9.81)` on the point-in-time one. The $14.53
between them was look-ahead, not edge.

So the reading is registered as **one-directional**, in git, before any result:

> His names beating ours proves nothing — it is the expected outcome of a
> post-hoc pick. **Only a null closes item 1c.**

A favourable number cannot become a finding after the fact if the document
saying it cannot already has a commit hash.

## The amendment — my registered criterion could not pass

Before running, I checked the shape of the universe rather than trusting the
plan. The criterion I registered this morning — his names reaching
`best_rank <= 5` at a rate 15 points above the control — **is unpassable**:

| field | share of a session's OWN universe inside the top 5 | sessions where it enumerates 1..n |
|---|---:|---:|
| `best_rank` | **93.7%** | 1 of 551 |
| `first_rank` | **89.6%** | 3 of 551 |

`best_rank` is the best rank a name ever reached, and the median session
carries 11 names — almost everything touches the top 5 at some tick. Beating
93.7% by 15 points needs 108.7%.

**A criterion that cannot pass is a control whose output is indistinguishable
from the failure it detects** — this project's recurring shape, in its own
registration. Running it would have produced a null, and that null would have
closed item 1c on an instrument incapable of saying anything else.

It also killed the planned closed-form control. `min(N, n)/n` assumes the
ranks enumerate 1..n within a session; 550 of 551 have ties (2024-07-02 ranks
six names 1, 1, 3, 3, 3, 4). The assumed form gives 0.536 against a true
0.937 — **it would have fired a "the control is sampling the wrong pool" alarm
on correct data**, which is an alarm wrong in the direction that gets believed.

### The replacement

The same instrument `regime_labels` uses, for the same reason — immune to
where a cut falls and to how many names a session carries:

> For each of his named symbols in our universe, its **rank-AUC** within that
> session: the chance it outranks a randomly chosen *other* name on our list
> that day, ties at a half. Mean over his names.
>
> **0.500 is no information, exactly and by symmetry** — which also gives back
> an exact closed form in place of an assumed one.

**Pass at mean rank-AUC ≥ 0.60, both halves on the same side.** The bar is
deliberately low: only a null closes this thread, so a generous bar makes the
closure worth more, not less.

## What the module does

1. **Coverage** — does our screen carry the name at all? No look-ahead: rank
   was computed from the tape as it stood at each tick.
2. **The ordering test** — rank-AUC against a matched draw from the same
   session's universe, checked against its exact 0.500 expectation.
3. **Both halves**, disagreeing on either the bar or the direction refuses.
4. **The declined names** — counted and sent through `screen_miss.diagnose`
   for the clause that kept each out. Dropping them would compute the rank
   distribution over exactly the names our screen likes and then report that
   our screen likes them.
5. **The contaminated P/L secondary** — both arms subset from one universe
   object through `pit_h0.run_day`, all three frictions, both denominators,
   drop-top-5, with its warning printed inline.

The superseded top-5 rates are printed with their real ~90% control beside
them rather than deleted — the figure a reader already has in their head is
the one worth disarming explicitly.

Also corrects the handover's wording: our rank is **`premarket_change`
descending**, not volatility. A hypothesis naming the wrong instrument cannot
be tested against the right one.

## State

54 tests, 18 mutations killed. Full suite **2,744 passed, 4 skipped**.

Mutation testing caught one green-but-wrong fixture: it asked a single session
for twenty top-five names, got five (a session has only five such slots), and
every threshold assertion around it passed for the wrong reason.

`var/state/holdout.json` untouched and unspent.
