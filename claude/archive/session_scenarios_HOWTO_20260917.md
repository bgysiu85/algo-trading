# The five scenarios — built, registered, and ready to run on your PC

2026-09-17, build chat. Bundle **`build-20260917m`** (commits `454870c` the
registrations, `5b0c4d4` the code; it also carries bundles j and k, so it is the
only one you need). **Nothing has been run.** The pass is yours to run locally —
no backtest was executed in the cloud, only the unit tests that make the code
worth your CPU time.

## What was registered, before any code existed

| scenario | rule | registration |
|---|---|---|
| 1 | enter only at **$5 or more**; the watchlist still monitors $2–20 | `docs/research/REGISTERED_price_floor.md` (H-S5) — new |
| 2 | stop the **session** once realised P&L gives back 50% of its peak | `docs/research/REGISTERED_giveback_cap.md` (H-S4) — the research chat's, + amendment A |
| 3 | the same, per **strategy**, stopping only that strategy | the same, `scope=strategy` |
| 4 | 1 and 2 together | a composition; no new hypothesis |
| 5 | 1 and 3 together | a composition; no new hypothesis |

H-S4 already existed — the research chat registered it an hour before you asked,
from Cameron and Malyarovich independently arriving at the same 50%, and handed
the build to this chat. It did not distinguish your #2 from your #3, so
**amendment A makes both scopes scored cells**, promotes MC5 from
reported-to-scored (you asked for all strategies), moves the baseline to the v2
ITCH book, restates the control so it can actually be implemented, and records
that the trip has to be recomputed at each friction level. All of it is pre-run.

## The two things worth knowing before you read the output

**The floor goes through the engine; the cap does not, and that is not laziness.**
Refusing an entry on price leaves the strategy flat, so bars it would have been
in a trade for become live signals — the floored book is **not** the baseline
minus its cheap trades, and it can contain entries the baseline never took. That
needs the tape. The cap is different: once it trips, nothing more is entered that
session, so no refused entry can free a later signal, and the kept set is exactly
the trades entered before the trip. That makes scenarios 2–5 an exact post-pass
over books already in memory — **one pass over the tape instead of five**, which
is most of why this run is minutes rather than an hour.

**A rule that removes trades from a losing book improves the total by
construction.** Every scenario here removes trades. The total P&L improving is
predicted in both registrations precisely so it cannot be reported back as a
success. What decides them is the per-trade delta against a control: random
removal for the floor, a random cut in the same sessions for the cap.

## Run it

From `D:\Trading`, one line at a time.

```
git -C D:\Trading pull "D:\Trading\Claude outputs\build-20260917m.bundle" main
```

```
python -m pytest tests\ -q
```

Then a 5-session smoke run — this exists to catch a wiring error in half a
minute rather than after the full pass:

```
python -m common.session_scenarios --limit 5 --jobs 8 --out var\reports\scen_smoke.txt --csv var\reports\scen_smoke_trades.csv
```

If that writes a report, run the real thing:

```
python -m common.session_scenarios --jobs 8
```

It defaults to `var\state\screen_pairs_pit_itch_v2.json` on `XNAS.ITCH` — the
deciding universe — and writes `var\reports\session_scenarios.txt` plus a trades
CSV. Expect roughly the time `first_entry_skip` took, since it is the same four
books over the same 6,411 symbol-days.

Then copy the report into `Claude outputs`:

```
copy var\reports\session_scenarios.txt "D:\Trading\Claude outputs\session_scenarios_20260917.txt"
```

and I will read it against the registrations and write the result doc and the
artifact page.

## What the report will contain

The books for MCL and MC5 and for all five scenarios, at $1.00 / $4.26 / $8.92,
with halves and drop-top-3. Then:

- **scenario 1** — the deltas at each friction, and its registered verdict read
  once at the measured $4.26, because the gate standard is defined there and
  printing it under three headings would be one verdict over three books;
- **scenarios 2–5** — H-S4's six readings at each friction, since the trip point
  genuinely moves with friction; where the cap armed and where it fired; per-trade
  P&L of removed against kept trades; and the **fire time by ET hour**, which is
  §5's check that the cap is not the time-of-day filter under another name — and
  time of day is closed;
- **4 and 5 read twice** — against the baseline, which is the whole change, and
  against scenario 1, which is what the cap adds *on top of* the floor. If a
  combination only looks good against the baseline, the floor was doing the work.

## The prediction, on the record

Both registrations predict **NOTHING**, for reasons already measured:
`entry_features` found no profitable price bucket in 88, and `luck_vs_edge` and
`cold_veto` both found per-trade results flat across session state. If the cap
fires late and the removed trades are worse only because they are late, it is a
time-of-day filter wearing a different name. The fire-time row is printed so that
is visible rather than inferred.

## Not decided by any of this

`holdout.json` stays shut. `strategy_adapter`'s live price band is unchanged and
the trader has no give-back rule, so neither ships from this run — either would
be its own change with its own live/backtest parity test, which the last three
splits earned. The concurrency cap is still unmodelled, and a give-back stop
frees slots this cannot price.
