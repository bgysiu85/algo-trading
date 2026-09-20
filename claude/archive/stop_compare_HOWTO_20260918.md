# The give-back's shape against a flat daily stop — built, and it runs in seconds

2026-09-18, build chat. Bundle **`build-20260918a`** (commits `4ce32d3` the
registration, `d4d1506` the code). **Nothing has been run.** As with the
scenarios, the pass is yours to run locally — only the unit tests ran in the
cloud.

## Why this exists before the holdout

The five scenarios ended with MC5's give-back cap passing all six of H-S4's
readings, under both scopes, at every friction level — the first rule in this
project to do that. §6 of that registration says a pass is not adoptable on its
own, and the result doc named one test that belongs before the holdout is spent:

> The give-back cap fires on sessions selected for having declined, where
> stopping is close to tautologically better than continuing. What is not yet
> known is whether the *give-back shape* beats a simpler stop on the same
> sessions.

That simpler rule is the **daily loss stop** — `if realised <= -STOP, stop
entering` — an absolute drawdown from zero, no arm, no peak, no ratio. If it
captures the same 78 cents, the peak-relative rule is an ornament and the two
practitioners' 50% is a number without a mechanism. The holdout is spent once,
and this decides which rule it is spent on.

## The one design decision worth your attention

A flat stop has a free parameter and the give-back does not, so comparing them
at a `$STOP` I picked would be a search wearing a comparison's clothes. **The
threshold is solved, not chosen:** for each (strategy, scope, friction) cell,
the `STOP` that removes as close as possible to the number of trades the
give-back removed on that same book. Both rules then spend the same abstention
budget, and the only thing that differs is *which* trades they spend it on. The
count comes from the give-back's behaviour, never from either rule's P&L, so no
stop is ever selected for performing well.

FLAT-40, FLAT-100 and FLAT-200 are printed so you can see the trade-off between
threshold and removal count. **They are never scored**, and a best cell among
them is not a result — that was fixed in the registration before any code
existed, because a fixed stop that happened to win would be the most quotable
number in the report and the least earned.

The two rules are also genuinely different, which is what makes this a
comparison rather than a reparametrisation. A session that goes **+$200 then
back to +$50** trips the give-back and never trips a flat stop. A session that
goes **straight to −$150 without ever being up** trips a flat stop and can never
trip the give-back, which needs a $40 peak first.

## Run it

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260918a.bundle" main
```

```
python -m pytest tests\ -q
```

```
python -m common.stop_compare
```

It reads `var\reports\session_scenarios_trades.csv` — the exact file your
scenarios run wrote at 00:05 this morning, 14,870 trades over 550 sessions —
and writes `var\reports\stop_compare.txt`. **There is no second pass over the
tape**, so this is seconds, not minutes. If the CSV has moved or been
overwritten by a differently-parameterised run, the module refuses to start and
says why rather than printing an ordinary-looking table.

Then:

```
copy var\reports\stop_compare.txt "D:\Trading\Claude outputs\stop_compare_20260918.txt"
```

and I will read it against the registration and write the result and the
artifact page.

## What the verdict can say

Three values, fixed in §4 before the run, read at **$4.26 and $8.92**:

- **THE SHAPE SURVIVES** — the give-back beats the matched flat stop at both
  levels *and* a session-clustered bootstrap of the difference clears 95%. It
  means the peak-relative rule is worth the holdout spend, and nothing more:
  both rules still only remove trades from a book that loses per trade.
- **THE SHAPE ADDS NOTHING** — the flat stop matches or beats it at either
  level. H-S4's pass then measured "stopping on a bad day helps" rather than
  "the 50% give-back helps", and the flat stop is the rule that should be
  registered instead: simpler, with no arm, no ratio and no peak to track live.
- **UNDECIDED** — the difference positive but the bootstrap short. The holdout
  is not spent on either rule.

**My registered prediction, on the record:** the shape survives narrowly,
`D_give − D_flat` of **+0.10 to +0.50** per trade, bootstrap marginal,
confidence moderate. The two rules fire on overlapping but different session
sets, so the flat stop cannot be a perfect substitute — but both are abstention
on a losing book, and I expect it to capture most of the 78 cents.

## A stale pointer, corrected

Both this registration and the research chat's `REGISTERED_giveback_cap` cite
"`PROGRAM_INDEX` §7 item 11, the daily loss stop". **That number is stale in
both.** §7 has been rewritten three times since; item 11 is now Cameron's
breakeven stop, and the daily loss stop is not in the current list at all — it
was dropped in a rewrite and two chats have been citing its old number to each
other since. Nothing about the hypothesis changes; the rule is named rather than
numbered from here, and the index entry is created to match.

## Not decided by any of this

`holdout.json` stays shut — this decides **which** rule is worth the one
holdout spend, not the spend itself. Neither rule ships: the live trader has no
session-state rule of either kind, and H-S4 §6's parity requirement stands for
whichever survives. And the concurrency cap is still unmodelled, so a stop that
frees slots is priced by neither.
