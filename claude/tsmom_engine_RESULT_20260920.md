# TSMOM engine (AT-42) and roll cross-check (AT-41): RESULT, 2026-09-20

**Chat:** TSMOM chat (Opus, high). **Board:** AT-42 (engine), AT-41 (cross-check),
AT-43 (the run, now unblocked once the bundle is merged), AT-112 (new, Ben).
**Bundle:** `tsmom-20260920c.bundle`, built on Ben's tip `20f6332`.
**Raw:** `claude/raw/tsmom_rollcheck_20260920.txt`, `claude/raw/tsmom_coverage_20260920.txt`.

## In plain terms

The TSMOM engine is built and its tests pass: it picks the right contract to
hold around every roll (including the metals' active-cycle rule), builds the
signal series without mixing the roll gap into P/L, sizes positions at 40%
volatility in whole micro contracts, and charges costs on every trade and roll.
Every guard was broken on purpose (49 times) and a test failed every time. The
roll calendar check on the real data passed on all 13 markets with zero
disagreements. **No return has been computed.** That's AT-43, the next and last
step before a result.

## Verdict

| | Result |
|---|---|
| AT-42 engine | **Green.** 65 synthetic tests + 4 real-archive tests (skip without `E:\`). Mutation sweep: **45 of 45** engine mutations and **4 of 4** loader mutations caught. Full repo suite 4,113 passed (8 `test_mcp_sql` failures are the sandbox missing the `mcp` package, unrelated). |
| AT-41 roll cross-check | **PASS**, 13 of 13 roots, 1,751 rolls compared, **0** disagreements of any size. |
| Holdout | Every date goes through `split_months` **before** anything is built; a spy test and a "shrink the answer" test pin it. |
| What Ben must decide | Nothing blocks AT-43. **AT-112** (optional, P3): add an exchange-rule expiry check, because AT-41's second reading isn't independent (see caveats). |

## AT-41 by root (registered stop rule: > 2% of rolls off by > 1 session)

| Root | Rolls | > 1 session | Any | Result |
|---|---:|---:|---:|---|
| ES | 65 | 0 | 0 | PASS |
| RTY | 36 | 0 | 0 | PASS |
| GC | 195 | 0 | 0 | PASS |
| SI | 195 | 0 | 0 | PASS |
| HG | 195 | 0 | 0 | PASS |
| CL | 195 | 0 | 0 | PASS |
| NG | 195 | 0 | 0 | PASS |
| 6E | 142 | 0 | 0 | PASS |
| 6A | 142 | 0 | 0 | PASS |
| 6B | 142 | 0 | 0 | PASS |
| 6J | 142 | 0 | 0 | PASS |
| ZN | 65 | 0 | 0 | PASS |
| TN | 42 | 0 | 0 | PASS |

Every bar's instrument id maps to a contract (0 unmapped), and every registry
point value matches the definition schema.

## Coverage, training side (before 2022-01-01)

| Root | Sessions | First | Rolls (held contract) | Held bar carried forward | Enters (261 returns) |
|---|---:|---|---:|---:|---|
| ES | 2,994 | 2010-06-07 | 47 | 0 | 2011-06-09 |
| RTY | 1,164 | 2017-07-10 | 18 | 0 | 2018-07-11 |
| GC | 2,998 | 2010-06-07 | 69 | 0 | 2011-06-09 |
| SI | 2,998 | 2010-06-07 | 58 | 0 | 2011-06-09 |
| HG | 2,998 | 2010-06-07 | 58 | 0 | 2011-06-09 |
| CL | 2,999 | 2010-06-07 | 139 | 0 | 2011-06-09 |
| NG | 2,999 | 2010-06-07 | 139 | 0 | 2011-06-09 |
| 6E | 2,993 | 2010-06-07 | 84 | 1 | 2011-06-09 |
| 6A | 2,992 | 2010-06-07 | 84 | 5 | 2011-06-09 |
| 6B | 2,992 | 2010-06-07 | 84 | 2 | 2011-06-09 |
| 6J | 2,991 | 2010-06-07 | 84 | 1 | 2011-06-09 |
| ZN | 2,999 | 2010-06-07 | 46 | 0 | 2011-06-09 |
| TN | 1,552 | 2016-01-11 | 24 | 0 | 2017-01-11 |

Roll counts match the registered calendars (GC 6 a year, SI/HG 5, quarterly
ES/ZN/TN/FX, monthly CL/NG). RTY and TN enter when the handover predicted.

## Found while building (before any return)

1. **The daily bars are UTC days, not CME sessions.** Each close is the price at
   00:00 UTC (the evening session), not the settlement, and most weeks have a
   **Sunday** bar (1,659 for ES). Dropped, and counted in the report. Left in,
   they'd have added ~50 "trading days" a year to the roll count and the
   volatility. Registered as amendment D item 1.
2. **Expirations get revised.** The June 2023 FX contracts moved from 19 to 16
   June (Juneteenth became a holiday), and ZNZ1 moved by a day. The loader
   refused the first read, so this was caught. It now uses the latest snapshot
   and prints every revision.
3. **Raw symbols repeat every decade** (GCZ0 = Dec 2010 and Dec 2020). Keyed by
   maturity year.
4. **A stale `.git/index.lock`.** A `git status` run through the bridge created
   one in `D:\Trading` and could not delete it. It was moved to
   `D:\Trading\_to_delete\`, which Ben deletes (command below). No git command
   is run on Ben's repo from the bridge any more; bundles are built in the
   cloud copy.

## How the engine reads the spec (amendment D, committed with the code)

Eight readings, none of which changes a registered rule: Sunday bars dropped;
the k-month sign is the dollar change of the difference-adjusted series;
decisions at the close of d use information through d−1; the ensemble is the mean
of the four signs; integer rounding is on the net book, half away from zero;
costs are charged on contract-sides actually traded; revised expirations use the
latest snapshot; P/L is in micro-contract units throughout. Full text:
`REGISTERED_tsmom.md` §0.3.

## Caveats

- **AT-41's two readings aren't independent.** Databento builds `c.0` from its
  own instrument definitions, so a perfect match is close to guaranteed by
  construction. The check shows the loader reads the calendar without error. It
  doesn't show that the vendor's expiries match the exchange's. **AT-112**
  (optional): check expiries against the published CME rules (e.g. ES on the
  third Friday, CL three business days before the 25th). Free, about an hour.
- **Closes are 00:00 UTC prices, not settlements.** Fine for a monthly signal;
  a settlement-based replication would differ by the evening session's drift.
- **Micro sizing before the micros existed** (MHG 2022, MNG 2023, MTN 2024) is
  a measurement convention (spec §2.2), not something Ben could have traded.

## Next steps (board)

1. **AT-42 subitem 6, Ben:** merge the bundle and run the suite (commands on the board).
2. **AT-43, TSMOM chat, Opus/high:** build the §3 report (net at 3 frictions, halves,
   per-year, drop-top-N by market, two cluster bootstraps, buy-and-hold, realised
   vol, turnover, rebalance-day and lookback grids, coverage, 3 arms unranked,
   capacity at $22k/$100k/$500k), run it on the training side, and write the
   Result doc. The engine already exposes the pieces: `engine.training_books`
   (all three arms), `run_book(..., signal_mode="long")` for buy-and-hold,
   `ks=` for the lookback grid and `tranche_days=` for the rebalance-day grid.
3. **AT-112, Ben (optional, P3):** decide whether to add the exchange-rule expiry check.

## Source files

`strategy/tsmom/{registry,roll,signal,book,engine,archive,rollcheck,run}.py`,
`tests/strategy/tsmom/`, `docs/research/REGISTERED_tsmom.md` §0.3.
