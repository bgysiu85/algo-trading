# The chase gate — don't buy what has already run

2026-09-18, build chat. Bundle **`build-20260918e`**, which **supersedes
`build-20260918d`**: it carries the feed fix *and* this. Same prerequisite
(`b93a138`), so pull `e` and ignore `d`.

Commits: `5f5cd13` the registration, `eb0930a` the code, each before the next
existed. **3,799 tests pass. Mutation-tested 15/15.** Registered in
`docs/research/REGISTERED_chase_gate.md` (H-P1).

## What it tests

The pre-flight's one cell pointing the right way. On MCL the trades that die on
the next bar were entered after a median **+11.43%** five-minute move and the
survivors after **+4.90%** — AUC 0.751 against a `rand` control at 0.526. So the
Running Up idea reversed: **refuse the entry when the name has already run.**

`ret_5m <= CEIL`, five ceilings per book — **0.033, 0.050, 0.083, 0.100,
0.150** — every one a number the pre-flight printed on a pass that had no P&L in
it at all. Through the engines' existing `entry_gate` hook, so it is an AND-mask
over each strategy's own entries and the live evaluator cannot see it.

## The part worth reading before the numbers arrive

The tempting cell is the two-condition one — *near the session high **and** not
extended* — which read **3.3% one-bar on MCL against a 12.6% base** in the
ad-hoc pass I showed you. It is not registered as a cell, and here is why.

`dist_from_high` on its own separates **almost nothing**: AUC 0.494 on MCL and
0.443 on MC5, against a random control at 0.526 / 0.505. `ret_5m` reads 0.751 /
0.636. So in a two-condition cell essentially all the work is being done by one
of the two conditions — and on a book that loses money, tightening *any*
condition improves the total, so the second knob will look like it is
contributing no matter what it does.

Instead the distance condition is tested **at the same abstention budget and
instead of the ceiling**: a threshold `D` is solved so that `dist_from_high >= D`
*alone* refuses the same number of entries the ceiling refuses. Two rules, one
budget, spent on different trades. **If the distance book does not beat the
ceiling book per trade there, "near the session high" adds nothing that "not
extended" was not already carrying.**

I got this wrong first and the bundle contains the correction rather than hiding
it. My first version solved `D` for *ceiling **AND** distance* — which is a
superset of the ceiling, so it can only refuse more, so the closest possible
match to the ceiling's own count is always "no distance condition at all". The
solver returned a perfect match and the comparison would have reported "the
second condition adds nothing" as a finding without ever testing it. A unit test
asserting `D` landed among the data rather than at an infinity is what caught
it.

## Run it

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260918e.bundle" main
```

```
python -m pytest tests\ -q
```

**This one needs the pre-flight's features CSV**, which is where the solved
threshold gets its population — every baseline entry of both books, 3,908 MCL
and 6,462 MC5, with all eleven features already computed. It should still be at
`var\reports\running_up_preflight.csv` from this morning. If it is not:

```
python -m common.running_up_preflight --jobs 8
```

A 5-session smoke first:

```
python -m common.chase_gate --limit 5 --jobs 8 --out var\reports\cg_smoke.txt --csv var\reports\cg_smoke.csv
```

Then the real run:

```
python -m common.chase_gate --jobs 8
```

```
copy var\reports\chase_gate.txt "D:\Trading\Claude outputs\chase_gate_20260918.txt"
```

Fifteen books over the same 6,411 symbol-days, so expect it to be slower than
this morning's eleven — call it two to three minutes.

## What I predict, on the record

**MCL clears the abstention band at 0.083 or 0.100 and still reads REFUSED on
the denominators**, because removing a quarter of the survivors will cost more
per symbol-day than it gains per trade — the shape seven of nine cells took in
the entry sweep this morning. Low confidence that it passes.

**MC5 is the one I would bet on for a per-trade pass.** Its one-bar trades lose
**(31.95)** each and are 139% of its net, so removing a third of them is
arithmetically large. Moderate confidence.

**And the prior from the three that came before is bad.** H-B1, H-B3 and H-B4
each had a mechanism, each removed trades from a losing book, and each landed
inside random removal's band — one by four cents. This trade-off looks better
than any of theirs did, which is a reason to run it and not a reason to believe
it.

## The block I care about most, and it is not the verdict

The report prints, reported and never scored, **where the one-bar exits landed
relative to the 5% trail**.

The pre-flight named an alternative explanation that is not an entry story at
all: a name that has just run 11% in five minutes is **more volatile**, and the
trail is a *fixed* percentage, so the next bar's ordinary range is bigger and the
stop is more likely to be hit by noise than by a reversal. On that reading these
were never bad entries — they are **a stop too tight for the volatility at the
moment of entry**, and the fix is a volatility-scaled trail that keeps the
trades rather than a gate that throws them away.

Both readings predict exactly the separation the pre-flight found, and this run
cannot choose between them. But the exits can: **clustered at −5% means the stop;
well below −5% means a real reversal.** Whatever the verdict says, that block
decides what gets registered next.

## Nothing ships

`holdout.json` stays shut. `entry_gate` is a backtest parameter on both engines
and a test asserts it never appears in `evaluate_last_bar`'s signature, so this
run cannot move the trader. No strategy constant is read or written.
